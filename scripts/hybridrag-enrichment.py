#!/usr/bin/env python3
"""HybridRAG Enrichment Job.

================================

Retroactively builds the entity/knowledge graph for files that were
fast-inserted (embed-only) by the watcher's bulk drain worker.

Fast-inserted docs are immediately queryable via vector search (naive/mix
mode) but lack entity/relation data for graph-based queries (local/global/
hybrid). This job calls ainsert() (full pipeline) on each pending file,
which extracts entities and relations and merges them into the graph.

Usage:
    uv run python scripts/hybridrag-enrichment.py <database_name>
    uv run python scripts/hybridrag-enrichment.py <database_name> --limit 50
    uv run python scripts/hybridrag-enrichment.py <database_name> --dry-run
    uv run python scripts/hybridrag-enrichment.py <database_name> --status

Safety:
    - LightRAG's ainsert() is idempotent for docs already in doc_status DONE.
    - Crash-safe: progress is written per file; re-running skips done paths.
    - Never touches files processed by the realtime worker (they're already
      fully enriched and not in enrichment_pending).
"""

import argparse
import asyncio
import gc
import hashlib
import json
import logging
import signal
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

import psutil

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config.backend_config import BackendType
from src.database_registry import get_registry

logger = logging.getLogger(__name__)


# ── Paths ──────────────────────────────────────────────────────────────────


def _pending_path(db_name: str) -> Path:
    return Path.home() / ".hybridrag" / "enrichment_pending" / f"{db_name}.txt"


def _done_path(db_name: str) -> Path:
    return Path.home() / ".hybridrag" / "enrichment_done" / f"{db_name}.txt"


# ── I/O helpers ────────────────────────────────────────────────────────────


def load_paths(path: Path) -> list[str]:
    if not path.exists():
        return []
    with open(path) as f:
        return [line.strip() for line in f if line.strip()]


def load_path_set(path: Path) -> set[str]:
    return set(load_paths(path))


def append_path(path: Path, file_path_str: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(file_path_str + "\n")


def save_paths(path: Path, paths: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write("\n".join(paths))


# ── Doc-status check ───────────────────────────────────────────────────────


def _is_fully_enriched_in_doc_status(db_path: str, file_path_str: str) -> bool:
    """Check LightRAG doc_status for DONE state.

    LightRAG sets doc_status to 'DONE' after full ainsert() completes.
    Fast-inserted docs (ainsert_fast) are NOT in doc_status at all.

    This is a filesystem check — avoids initializing the full LightRAG core
    just to skip an already-done doc.
    """
    try:
        status_file = Path(db_path) / "kv_store_doc_status.json"
        if not status_file.exists():
            return False
        with open(status_file) as f:
            doc_status = json.load(f)

        import hashlib

        fp = Path(file_path_str)
        if not fp.exists():
            return False
        content = fp.read_text(encoding="utf-8", errors="ignore")
        doc_key = "doc-" + hashlib.md5(content.encode()).hexdigest()

        entry = doc_status.get(doc_key)
        if entry is None:
            return False
        # LightRAG stores status as dict with "status" key or as string
        if isinstance(entry, dict):
            return entry.get("status") == "done"
        return str(entry).lower() == "done"
    except Exception:
        return False


# ── Core initializer ───────────────────────────────────────────────────────


async def _init_core(entry):
    """Initialize HybridLightRAGCore from a registry entry."""
    from src.config.app_config import HybridRAGConfig
    from src.lightrag_core import HybridLightRAGCore

    config = HybridRAGConfig()
    config.lightrag.working_dir = entry.path

    if entry.model:
        config.lightrag.model_name = entry.model

    backend_config = entry.get_backend_config()
    logger.info(f"Backend: {backend_config.backend_type.value}")
    if backend_config.backend_type == BackendType.POSTGRESQL:
        logger.info(
            f"  PostgreSQL: {backend_config.postgres_host}:"
            f"{backend_config.postgres_port}/{backend_config.postgres_database}"
        )

    core = HybridLightRAGCore(config, backend_config=backend_config)
    await core._ensure_initialized()
    return core


# ── Main enrichment job ────────────────────────────────────────────────────


class EnrichmentJob:
    """Retroactively builds entity graph for fast-inserted documents.

    Processing order:
        1. Load enrichment_pending — all paths needing graph extraction
        2. Subtract enrichment_done — paths already processed
        3. Subtract doc_status DONE — paths enriched outside this job
        4. For each remaining path: run ainsert() then mark_done()
        5. Save progress after each file (crash-safe resume)
    """

    def __init__(self, db_name: str, limit: int | None, dry_run: bool) -> None:
        self.db_name = db_name
        self.limit = limit
        self.dry_run = dry_run
        self.running = True

        self.stats = {
            "enriched": 0,
            "skipped_done": 0,
            "skipped_missing": 0,
            "errors": 0,
            "start_time": time.time(),
        }

        registry = get_registry()
        self.entry = registry.get(db_name)
        if not self.entry:
            raise ValueError(f"Database not found in registry: {db_name}")

        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum, _frame) -> None:
        logger.info(f"Signal {signum} received — stopping after current file")
        self.running = False

    def _mark_done(self, file_path_str: str) -> None:
        """Record a path as fully enriched in the done file and pending cleanup."""
        append_path(_done_path(self.db_name), file_path_str)

    def _build_work_list(self) -> list[str]:
        """Compute the ordered list of paths that still need enrichment."""
        pending = load_paths(_pending_path(self.db_name))
        if not pending:
            logger.info("enrichment_pending is empty — nothing to do")
            return []

        done = load_path_set(_done_path(self.db_name))
        logger.info(f"Pending: {len(pending)}  |  Already done: {len(done)}")

        # Deduplicate preserving order; subtract done set
        seen: set[str] = set()
        work: list[str] = []
        for p in pending:
            if p in seen or p in done:
                continue
            seen.add(p)
            work.append(p)

        logger.info(f"Remaining to enrich: {len(work)}")
        if self.limit:
            work = work[: self.limit]
            logger.info(f"--limit applied: processing {len(work)} files this run")

        return work

    def _check_system_load(self) -> str:
        """Return 'ok', 'high', or 'critical' based on current CPU/memory."""
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory().percent
        if cpu >= 98 or mem >= 95:
            return "critical"
        if cpu >= 90 or mem >= 90:
            return "high"
        return "ok"

    def print_status(self) -> None:
        """Print current enrichment queue status and exit."""
        pending = load_paths(_pending_path(self.db_name))
        done = load_path_set(_done_path(self.db_name))
        unique_pending = len({p for p in pending if p not in done})

        print(f"\n── Enrichment status: {self.db_name} ──")
        print(f"  enrichment_pending entries : {len(pending)}")
        print(f"  enrichment_done entries    : {len(done)}")
        print(f"  unique paths still pending : {unique_pending}")
        print(f"  pending file               : {_pending_path(self.db_name)}")
        print(f"  done file                  : {_done_path(self.db_name)}")
        if pending:
            print(f"\n  Oldest pending:")
            for p in pending[:3]:
                if p not in done:
                    print(f"    {p}")

    async def run(self) -> None:
        work = self._build_work_list()
        if not work:
            return

        if self.dry_run:
            logger.info(f"[dry-run] Would enrich {len(work)} files:")
            for p in work[:10]:
                logger.info(f"  {p}")
            if len(work) > 10:
                logger.info(f"  ... and {len(work) - 10} more")
            return

        logger.info("Initializing LightRAG core...")
        core = await _init_core(self.entry)
        logger.info("Core ready — starting enrichment\n")

        total = len(work)

        for idx, file_path_str in enumerate(work, 1):
            if not self.running:
                logger.info("Stopping on signal")
                break

            file_path = Path(file_path_str)
            prefix = f"[{idx}/{total}]"

            # Skip missing files
            if not file_path.exists():
                logger.warning(f"{prefix} File gone, skipping: {file_path.name}")
                self._mark_done(file_path_str)  # won't come back
                self.stats["skipped_missing"] += 1
                continue

            # Skip if already fully enriched in doc_status (idempotency guard)
            if _is_fully_enriched_in_doc_status(self.entry.path, file_path_str):
                logger.info(
                    f"{prefix} Already in doc_status DONE, marking done: "
                    f"{file_path.name}"
                )
                self._mark_done(file_path_str)
                self.stats["skipped_done"] += 1
                continue

            # Throttle on high system load
            load = self._check_system_load()
            if load == "critical":
                logger.warning(f"{prefix} Critical system load — pausing 30s")
                await asyncio.sleep(30)
            elif load == "high":
                logger.info(f"{prefix} High load — pausing 5s before next file")
                await asyncio.sleep(5)

            # Run full pipeline (entity + relation extraction + graph merge)
            logger.info(f"{prefix} 🔬 Enriching: {file_path.name}")
            t0 = time.time()
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                if not content.strip():
                    logger.warning(f"{prefix} Empty file, skipping")
                    self._mark_done(file_path_str)
                    self.stats["skipped_missing"] += 1
                    continue

                success = await core.ainsert(content, str(file_path))
                elapsed = time.time() - t0

                if success:
                    self._mark_done(file_path_str)
                    self.stats["enriched"] += 1
                    pct = (idx / total) * 100
                    logger.info(
                        f"{prefix} ✓ Enriched in {elapsed:.1f}s "
                        f"({pct:.1f}% complete)"
                    )
                else:
                    self.stats["errors"] += 1
                    logger.error(
                        f"{prefix} ✗ ainsert() returned False: {file_path.name}"
                    )

            except Exception as e:
                elapsed = time.time() - t0
                self.stats["errors"] += 1
                logger.exception(
                    f"{prefix} ✗ Error after {elapsed:.1f}s: {file_path.name}: {e}"
                )

            # GC between files to prevent memory buildup
            gc.collect()

            # Brief yield between files
            await asyncio.sleep(0.5)

        # ── Final summary ──────────────────────────────────────────────────
        total_time = time.time() - self.stats["start_time"]
        processed = (
            self.stats["enriched"]
            + self.stats["skipped_done"]
            + self.stats["skipped_missing"]
        )
        logger.info("")
        logger.info("=" * 60)
        logger.info("ENRICHMENT JOB COMPLETE")
        logger.info(f"  Enriched       : {self.stats['enriched']}")
        logger.info(f"  Skipped (done) : {self.stats['skipped_done']}")
        logger.info(f"  Skipped (gone) : {self.stats['skipped_missing']}")
        logger.info(f"  Errors         : {self.stats['errors']}")
        logger.info(f"  Total time     : {total_time:.0f}s")
        if self.stats["enriched"] > 0:
            avg = total_time / self.stats["enriched"]
            remaining = len(work) - processed
            eta_hours = (remaining * avg) / 3600
            logger.info(f"  Avg per file   : {avg:.1f}s")
            logger.info(f"  Est. remaining : {eta_hours:.1f}h ({remaining} files)")
        logger.info("=" * 60)

        # Compact enrichment_pending: rewrite without completed paths
        self._compact_pending()

    def _compact_pending(self) -> None:
        """Rewrite enrichment_pending removing all paths now in done set.

        Safe to call at end of each run. Keeps the pending file from
        growing unboundedly across restarts.
        """
        pending_p = _pending_path(self.db_name)
        done = load_path_set(_done_path(self.db_name))
        all_pending = load_paths(pending_p)

        remaining = [p for p in all_pending if p not in done]
        save_paths(pending_p, remaining)

        removed = len(all_pending) - len(remaining)
        logger.info(
            f"Compacted enrichment_pending: removed {removed} done entries, "
            f"{len(remaining)} still pending"
        )


# ── Logging setup ──────────────────────────────────────────────────────────


def setup_logging(db_name: str) -> None:
    log_dir = Path(__file__).parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"enrichment_{db_name}.log"

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()

    fh = RotatingFileHandler(
        log_file, maxBytes=100 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fh.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    root.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    root.addHandler(ch)


# ── Entry point ────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Retroactively enrich fast-inserted HybridRAG docs with entity graph"
    )
    parser.add_argument("db_name", help="Registered database name")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Process at most N files this run (for incremental enrichment)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be processed without calling ainsert()",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print enrichment queue status and exit",
    )
    args = parser.parse_args()

    setup_logging(args.db_name)
    logger.info(f"Enrichment job starting for: {args.db_name}")

    try:
        job = EnrichmentJob(
            db_name=args.db_name,
            limit=args.limit,
            dry_run=args.dry_run,
        )

        if args.status:
            job.print_status()
            return

        asyncio.run(job.run())

    except KeyboardInterrupt:
        logger.info("Interrupted")
    except ValueError as e:
        logger.error(f"Config error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Fatal: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
