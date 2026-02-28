#!/usr/bin/env python3
"""HybridRAG Standalone Watcher Daemon.

====================================

Watches a registered database's source folder for changes and auto-ingests.
Designed to run as a background daemon process or systemd service.

Usage:
    python scripts/hybridrag-watcher.py <database_name>

The database must be registered in the HybridRAG registry.
Configuration (source folder, interval, model) is read from the registry.

Author: HybridRAG System
Date: 2025-12-06
"""

import asyncio
import contextlib
import gc
import hashlib
import json
import logging
import os
import signal
import sys
import time
from collections import OrderedDict
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path

import psutil

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.alerting import get_alert_manager
from src.config.backend_config import BackendType
from src.database_metadata import DatabaseMetadata
from src.database_registry import (
    DatabaseEntry,
    acquire_watcher_lock,
    get_registry,
    get_watcher_pid_file,
    is_watcher_running,
    release_watcher_lock,
)


@dataclass
class BatchConfig:
    """Configuration for batch processing."""

    batch_size: int = 5  # Files per batch (normal load, CPU < 90%)
    batch_size_low: int = 2  # Files per batch (high load, 90–98% CPU)
    batch_size_critical: int = 1  # Files per batch (critical load, CPU >= 98%)
    sleep_between_batches: float = 2.0  # Seconds
    high_load_cpu_percent: float = 90.0  # Switch to 2 files if CPU above this
    high_load_memory_percent: float = 90.0  # Switch to 2 files if memory above this
    critical_cpu_percent: float = (
        98.0  # Switch to 1 file if CPU above this (never blocks)
    )
    critical_memory_percent: float = 95.0  # Switch to 1 file if memory above this
    check_interval: float = 5.0  # Seconds between resource checks
    bulk_cutoff_days: int = 30  # Files older than this (mtime) use ainsert_fast
    bulk_worker_pause_sec: float = (
        1.0  # Pause between historical files (yield to realtime)
    )


class ResourceMonitor:
    """Monitor system resources and throttle when busy."""

    def __init__(self, config: BatchConfig) -> None:
        self.config = config

    def get_load_level(self) -> tuple[str, str]:
        """Check system load level.

        Returns:
            (level, reason) where level is 'normal', 'high', or 'critical'

        """
        cpu_percent = psutil.cpu_percent(interval=1)
        memory_percent = psutil.virtual_memory().percent

        # Critical load (>=98%) — 1 file at a time, never blocks
        if cpu_percent > self.config.critical_cpu_percent:
            return (
                "critical",
                f"CPU: {cpu_percent:.1f}% > {self.config.critical_cpu_percent}%",
            )
        if memory_percent > self.config.critical_memory_percent:
            return (
                "critical",
                f"Memory: {memory_percent:.1f}% > {self.config.critical_memory_percent}%",
            )

        # High load (90-98%) — reduce to batch_size_low
        if cpu_percent > self.config.high_load_cpu_percent:
            return "high", f"CPU: {cpu_percent:.1f}% (high load)"
        if memory_percent > self.config.high_load_memory_percent:
            return "high", f"Memory: {memory_percent:.1f}% (high load)"

        # Normal load (<90%) — full batch size
        return "normal", ""

    async def wait_until_system_ready(self, logger_instance: logging.Logger) -> None:
        """No-op: blocking pause removed. Throttling is done via batch size only."""
        return


class PerformanceTracker:
    """Tracks ingestion performance metrics with rolling average calculation.

    Used for proactive performance monitoring (T012-T013):
    - Maintains a rolling window of recent ingestion rates (docs/minute)
    - Detects performance degradation when current rate drops below baseline
    - Warns users when ingestion is >50% slower than baseline
    """

    def __init__(
        self, window_size: int = 20, degradation_threshold_pct: int = 50
    ) -> None:
        """Initialize performance tracker.

        Args:
            window_size: Number of ingestion cycles to include in rolling average
            degradation_threshold_pct: Warn when performance drops by this percentage

        """
        self._window_size = window_size
        self._degradation_threshold_pct = degradation_threshold_pct
        self._rates: list[float] = []  # docs/minute for each cycle
        self._baseline_rate: float | None = None
        self._cycles_since_warning = 0
        self._warning_cooldown = 5  # Only warn every N cycles

    def record_ingestion(self, docs_count: int, duration_seconds: float) -> dict | None:
        """Record an ingestion cycle and check for performance degradation.

        Args:
            docs_count: Number of documents ingested
            duration_seconds: Time taken for ingestion

        Returns:
            Dict with warning details if degradation detected, None otherwise

        """
        if duration_seconds <= 0 or docs_count <= 0:
            return None

        # Calculate rate (docs/minute)
        docs_per_minute = (docs_count / duration_seconds) * 60.0

        # Add to rolling window
        self._rates.append(docs_per_minute)
        if len(self._rates) > self._window_size:
            self._rates.pop(0)

        # Update baseline after sufficient data
        if len(self._rates) >= 5 and self._baseline_rate is None:
            self._baseline_rate = self._calculate_average()
            logger.info(
                f"📊 Performance baseline established: {self._baseline_rate:.1f} docs/min"
            )

        # Check for degradation
        self._cycles_since_warning += 1
        if (
            self._baseline_rate
            and len(self._rates) >= 3
            and self._cycles_since_warning >= self._warning_cooldown
        ):
            current_avg = self._calculate_recent_average()
            degradation_pct = (
                (self._baseline_rate - current_avg) / self._baseline_rate
            ) * 100

            if degradation_pct >= self._degradation_threshold_pct:
                self._cycles_since_warning = 0
                return {
                    "baseline_rate": self._baseline_rate,
                    "current_rate": current_avg,
                    "degradation_pct": degradation_pct,
                    "threshold_pct": self._degradation_threshold_pct,
                }

        return None

    def _calculate_average(self) -> float:
        """Calculate average of all recorded rates."""
        if not self._rates:
            return 0.0
        return sum(self._rates) / len(self._rates)

    def _calculate_recent_average(self) -> float:
        """Calculate average of most recent 3 rates."""
        if len(self._rates) < 3:
            return self._calculate_average()
        return sum(self._rates[-3:]) / 3

    def get_stats(self) -> dict:
        """Get current performance statistics."""
        return {
            "baseline_rate": self._baseline_rate,
            "current_avg": self._calculate_recent_average() if self._rates else None,
            "sample_count": len(self._rates),
            "window_size": self._window_size,
            "degradation_threshold_pct": self._degradation_threshold_pct,
        }


class BoundedSet:
    """A set with a maximum size that evicts oldest items when full.

    Uses OrderedDict internally to maintain insertion order and provide
    O(1) membership testing while bounding memory usage.
    """

    def __init__(self, max_size: int = 100000) -> None:
        """Initialize bounded set.

        Args:
            max_size: Maximum number of items to store (default 100000)

        """
        self._data: OrderedDict[str, None] = OrderedDict()
        self._max_size = max_size

    def add(self, item: str) -> None:
        """Add item to set, evicting oldest if at capacity."""
        if item in self._data:
            # Move to end (most recently added)
            self._data.move_to_end(item)
            return
        # Evict oldest items if at capacity
        while len(self._data) >= self._max_size:
            self._data.popitem(last=False)
        self._data[item] = None

    def __contains__(self, item: str) -> bool:
        return item in self._data

    def __len__(self) -> int:
        return len(self._data)

    def clear(self) -> None:
        """Clear all items."""
        self._data.clear()

    def update(self, items) -> None:
        """Add multiple items."""
        for item in items:
            self.add(item)


# Configure logging with rotation


def setup_logging(db_name: str) -> logging.Logger:
    """Setup logging with size-based rotation.

    - Max 200MB per file
    - Keep 5 backup files (total ~1GB max per database)
    - Also cleans up logs older than 7 days on startup
    """
    log_dir = Path(__file__).parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"watcher_{db_name}.log"

    # Clean old log backups (older than 7 days)
    cleanup_old_logs(log_dir, days=7)

    # Create logger
    log = logging.getLogger(f"watcher.{db_name}")
    log.setLevel(logging.INFO)

    # Remove existing handlers to avoid duplicates
    log.handlers.clear()

    # Rotating file handler: 200MB max, keep 5 backups
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=200 * 1024 * 1024,  # 200MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
    )
    log.addHandler(file_handler)

    # Also log to stderr for systemd/console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s",
        )
    )
    log.addHandler(console_handler)

    return log


def cleanup_old_logs(log_dir: Path, days: int = 7) -> int:
    """Remove log files older than specified days.

    Returns count of files removed.
    """
    import time as time_module

    cutoff = time_module.time() - (days * 24 * 60 * 60)
    removed = 0

    for log_file in log_dir.glob("*.log*"):
        try:
            if log_file.stat().st_mtime < cutoff:
                log_file.unlink()
                removed += 1
        except Exception:
            pass  # Skip files we can't delete

    return removed


# Default logger until setup_logging is called
logger = logging.getLogger(__name__)


class FileChangeDetector:
    """Detects file changes in a directory.

    Tracks modification times and new files to determine what needs processing.
    """

    def __init__(
        self,
        folder: str,
        recursive: bool = True,
        extensions: list | None = None,
        specstory_only: bool = False,
    ) -> None:
        """Initialize the change detector.

        Args:
            folder: Root folder to watch
            recursive: Watch subdirectories
            extensions: Optional list of file extensions to track
            specstory_only: Only watch .specstory folders (for specstory source type)

        """
        self.folder = Path(folder)
        self.recursive = recursive
        self.extensions = set(extensions) if extensions else None
        self.specstory_only = specstory_only
        self.last_check: float | None = None
        self.known_files: set[Path] = set()
        self.file_mtimes: dict = {}

    def should_include(self, path: Path) -> bool:
        """Check if a file should be included based on filters."""
        # Check specstory folder filter first
        if self.specstory_only:
            # Only include files that are in a .specstory folder path
            path_parts = path.parts
            if not any(part == ".specstory" for part in path_parts):
                return False

        # Then check extension filter
        if self.extensions is None:
            return True
        return path.suffix.lower() in self.extensions

    def scan_files(self) -> set[Path]:
        """Scan folder for all matching files."""
        files = set()

        if self.recursive:
            for file_path in self.folder.rglob("*"):
                if file_path.is_file() and self.should_include(file_path):
                    files.add(file_path)
        else:
            for file_path in self.folder.iterdir():
                if file_path.is_file() and self.should_include(file_path):
                    files.add(file_path)

        return files

    def detect_changes(self) -> tuple[set[Path], set[Path], set[Path]]:
        """Detect file changes since last check.

        Returns:
            Tuple of (new_files, modified_files, deleted_files)

        """
        current_files = self.scan_files()
        current_time = time.time()

        new_files = set()
        modified_files = set()
        deleted_files = set()

        # Find new and modified files
        for file_path in current_files:
            if file_path not in self.known_files:
                new_files.add(file_path)
            else:
                # Check if modified
                try:
                    mtime = file_path.stat().st_mtime
                    if mtime > self.file_mtimes.get(file_path, 0):
                        modified_files.add(file_path)
                        self.file_mtimes[file_path] = mtime
                except OSError:
                    pass

        # Find deleted files
        deleted_files = self.known_files - current_files

        # Update tracking
        self.known_files = current_files

        # Clean up file_mtimes for deleted files to prevent memory leak
        for deleted_path in deleted_files:
            self.file_mtimes.pop(deleted_path, None)

        # Add mtimes for new files
        for file_path in current_files:
            if file_path not in self.file_mtimes:
                with contextlib.suppress(OSError):
                    self.file_mtimes[file_path] = file_path.stat().st_mtime

        self.last_check = current_time

        return new_files, modified_files, deleted_files


class WatcherDaemon:
    """Daemon process for watching a registered database.

    Polls for file changes and triggers ingestion when changes detected.
    Uses lazy initialization and batch processing to prevent OOM on large graphs.
    """

    # Maximum files to process in a single batch to prevent OOM
    BATCH_SIZE = 10

    # Maximum number of content hashes to track (prevents unbounded memory growth)
    # 100k MD5 hashes = ~3.2MB memory (32 chars * 100k)
    MAX_INGESTED_HASHES = 100000

    def __init__(self, db_name: str) -> None:
        """Initialize the watcher daemon.

        Args:
            db_name: Name of the registered database to watch

        """
        self.db_name = db_name
        self.registry = get_registry()
        self.entry: DatabaseEntry | None = None
        self.detector: FileChangeDetector | None = None
        self.running = False
        self.pid_file: Path | None = None
        self._lock_fd: int | None = None  # File descriptor for PID file lock
        # Use BoundedSet to prevent unbounded memory growth
        self.ingested_hashes = BoundedSet(max_size=self.MAX_INGESTED_HASHES)
        self.stats = {
            "total_ingested": 0,
            "duplicates_skipped": 0,
            "errors": 0,
            "last_error": None,
        }
        self.alert_manager = get_alert_manager()

        # Reusable core instance - lazy initialized to save memory
        self._core = None
        self._config = None

        # Performance tracker for proactive monitoring (T012-T013)
        # Threshold is loaded from backend_config after entry is loaded
        self.performance_tracker: PerformanceTracker | None = None

        # Resource monitor for batch mode
        self.batch_config = BatchConfig()
        self.resource_monitor = ResourceMonitor(self.batch_config)

        # Dual-queue priority architecture: realtime (high-priority) + bulk (background)
        # asyncio.Queue / Lock are safe to construct outside an event loop in Python 3.10+
        self._realtime_queue: asyncio.Queue = asyncio.Queue()
        self._ingest_lock: asyncio.Lock = asyncio.Lock()

        # Enrichment tracking: paths fully enriched (entity graph built).
        # Loaded at startup so _process_one_historical skips re-adding them.
        self._enrichment_done: set[str] = self._load_enrichment_done()

        # Load database entry (must be done first)
        self._load_entry()

        # Initialize performance tracker with threshold from backend config
        self._init_performance_tracker()

    def _load_ingested_hashes(self) -> None:
        """Load existing document hashes from the database's doc_status store."""
        assert self.entry is not None, "Database entry must be loaded"
        doc_status_path = Path(self.entry.path) / "kv_store_doc_status.json"
        if doc_status_path.exists():
            try:
                with open(doc_status_path) as f:
                    doc_status = json.load(f)
                # Extract document hashes (doc-{hash} format)
                for doc_id in doc_status:
                    if doc_id.startswith("doc-"):
                        self.ingested_hashes.add(doc_id[4:])  # Remove "doc-" prefix
                logger.info(
                    f"Loaded {len(self.ingested_hashes)} existing document hashes"
                )
            except Exception as e:
                logger.warning(f"Could not load doc status: {e}")

    def _content_hash(self, content: str) -> str:
        """Generate MD5 hash of content (matching LightRAG's approach)."""
        return hashlib.md5(content.encode()).hexdigest()

    def _is_duplicate(self, content: str) -> bool:
        """Check if content has already been ingested."""
        content_hash = self._content_hash(content)
        return content_hash in self.ingested_hashes

    def _enrichment_pending_path(self) -> Path:
        return Path.home() / ".hybridrag" / "enrichment_pending" / f"{self.db_name}.txt"

    def _enrichment_done_path(self) -> Path:
        return Path.home() / ".hybridrag" / "enrichment_done" / f"{self.db_name}.txt"

    def _load_enrichment_done(self) -> set[str]:
        """Load the set of file paths already fully enriched (entity graph built).

        Called at startup so _process_one_historical never re-adds a path
        that has already been enriched by the enrichment job.
        """
        done_path = (
            Path.home() / ".hybridrag" / "enrichment_done" / f"{self.db_name}.txt"
        )
        if not done_path.exists():
            return set()
        try:
            with open(done_path) as f:
                paths = {line.strip() for line in f if line.strip()}
            logger.info(f"Loaded {len(paths)} enrichment-done paths")
            return paths
        except Exception as e:
            logger.warning(f"Could not load enrichment_done: {e}")
            return set()

    def mark_enrichment_done(self, file_path: str) -> None:
        """Mark a file as fully enriched (entity graph extracted).

        Called by the enrichment job after successfully running ainsert()
        on a fast-inserted doc. Adds path to enrichment_done file and
        in-memory set so it won't be re-queued for enrichment.

        Args:
            file_path: Absolute path string of the enriched file
        """
        self._enrichment_done.add(file_path)
        done_path = self._enrichment_done_path()
        done_path.parent.mkdir(parents=True, exist_ok=True)
        with open(done_path, "a") as f:
            f.write(file_path + "\n")

    def _load_entry(self) -> None:
        """Load database entry from registry."""
        self.entry = self.registry.get(self.db_name)
        if not self.entry:
            msg = f"Database not found in registry: {self.db_name}"
            raise ValueError(msg)

        if not self.entry.source_folder:
            msg = f"No source folder configured for: {self.db_name}"
            raise ValueError(msg)

        if not os.path.exists(self.entry.source_folder):
            msg = f"Source folder does not exist: {self.entry.source_folder}"
            raise ValueError(msg)

        self.pid_file = get_watcher_pid_file(self.db_name)

        # Initialize change detector
        # Normalize extensions: registry stores 'md' without dot, path.suffix returns '.md'
        raw_exts = self.entry.file_extensions if self.entry.file_extensions else [".md"]
        extensions = [e if e.startswith(".") else f".{e}" for e in raw_exts]
        logger.info(f"  File extensions from config: {self.entry.file_extensions}")
        # For specstory source type, only watch .specstory folders
        specstory_only = self.entry.source_type == "specstory"
        self.detector = FileChangeDetector(
            folder=self.entry.source_folder,
            recursive=self.entry.recursive,
            extensions=extensions,
            specstory_only=specstory_only,
        )

        logger.info(f"Loaded database entry: {self.db_name}")
        logger.info(f"  Source: {self.entry.source_folder}")
        logger.info(f"  Interval: {self.entry.watch_interval}s")
        logger.info(f"  Recursive: {self.entry.recursive}")
        logger.info(f"  Source type: {self.entry.source_type}")
        logger.info(f"  SpecStory only: {specstory_only}")
        logger.info(f"  Extensions: {extensions}")

        # Load existing document hashes from database
        self._load_ingested_hashes()

    def _init_performance_tracker(self) -> None:
        """Initialize performance tracker with thresholds from backend config.

        T014: Load configurable thresholds from registry backend_config.
        """
        assert self.entry is not None, "Database entry must be loaded"
        backend_config = self.entry.get_backend_config()
        degradation_threshold = backend_config.performance_degradation_pct

        self.performance_tracker = PerformanceTracker(
            window_size=20,
            degradation_threshold_pct=degradation_threshold,
        )

        logger.info(
            f"  Performance tracking enabled (degradation threshold: {degradation_threshold}%)"
        )

    def _get_pending_file_path(self) -> Path:
        """Get the path to the pending files list."""
        return (
            Path.home()
            / ".hybridrag"
            / "batch_ingestion"
            / f"{self.db_name}.pending.txt"
        )

    async def _get_document_count(self) -> int:
        """Get document count from LightRAG database.

        Checks both kv_store_doc_status.json (full ainsert) AND
        kv_store_full_docs.json (ainsert_fast embed-only) so that
        fast-inserted docs are counted and don't trigger re-discovery
        on every restart.

        Returns:
            Number of documents in database, 0 if unable to determine

        """
        assert self.entry is not None, "Database entry must be loaded"
        try:
            db_path = Path(self.entry.path)
            total = 0

            # Count fully-processed docs (ainsert path)
            doc_status_path = db_path / "kv_store_doc_status.json"
            if doc_status_path.exists():
                with open(doc_status_path) as f:
                    doc_status = json.load(f)
                total += sum(1 for key in doc_status if key.startswith("doc-"))

            # Also count fast-inserted docs (ainsert_fast path — not in doc_status)
            full_docs_path = db_path / "kv_store_full_docs.json"
            if full_docs_path.exists() and total == 0:
                with open(full_docs_path) as f:
                    full_docs = json.load(f)
                total += sum(1 for key in full_docs if key.startswith("doc-"))

            return total
        except Exception as e:
            logger.warning(f"Could not get document count: {e}")
            return 0

    def _discover_files(self, pending_file: Path) -> int:
        """Discovery phase: Find all matching files quickly.

        For SpecStory type, finds all .specstory/history/*.md files.
        For other types, uses configured extensions and filters.

        Writes discovered files to pending_file for batch processing.

        Returns:
            Number of files discovered

        """
        assert self.entry is not None, "Database entry must be loaded"
        assert self.detector is not None, "File detector must be initialized"

        logger.info(f"🔍 Discovery phase: Scanning {self.entry.source_folder}")
        discovered = []

        # Use detector's scan_files method which already handles filters
        discovered_paths = self.detector.scan_files()
        discovered = [str(path.resolve()) for path in discovered_paths]

        # Write to pending file
        pending_file.parent.mkdir(parents=True, exist_ok=True)
        with open(pending_file, "w") as f:
            f.write("\n".join(discovered))

        logger.info(f"✅ Discovery complete: {len(discovered)} files found")
        logger.info(f"📝 Saved to: {pending_file}")

        return len(discovered)

    def _load_pending_files(self, pending_file: Path) -> list[str]:
        """Load list of pending files."""
        if not pending_file.exists():
            return []

        with open(pending_file) as f:
            return [line.strip() for line in f if line.strip()]

    def _save_pending_files(self, pending_file: Path, files: list[str]) -> None:
        """Save remaining pending files."""
        with open(pending_file, "w") as f:
            f.write("\n".join(files))

    def _split_pending_by_age(self, paths: list[str]) -> tuple[list[str], list[str]]:
        """Partition file paths into (historical, recent) by mtime.

        Historical (mtime > bulk_cutoff_days old) → ainsert_fast via bulk worker.
        Recent (mtime <= bulk_cutoff_days old) → ainsert via realtime queue.
        OSError on stat → treated as recent (safe default: full pipeline).

        Returns:
            (historical_paths, recent_paths)
        """
        cutoff_ts = time.time() - (self.batch_config.bulk_cutoff_days * 86400)
        historical: list[str] = []
        recent: list[str] = []

        for path_str in paths:
            try:
                mtime = Path(path_str).stat().st_mtime
                if mtime < cutoff_ts:
                    historical.append(path_str)
                else:
                    recent.append(path_str)
            except OSError:
                recent.append(path_str)  # can't stat → full pipeline

        logger.info(
            f"Age split: {len(historical)} historical "
            f"(>{self.batch_config.bulk_cutoff_days}d old → ⚡fast), "
            f"{len(recent)} recent (≤{self.batch_config.bulk_cutoff_days}d → 🔬full)"
        )
        return historical, recent

    async def _process_one_historical(self, file_path_str: str) -> None:
        """Process a single historical file with ainsert_fast (embed-only).

        Must be called while holding self._ingest_lock.
        Tracks enrichment-pending for later graph backfill.
        """
        core = await self._get_core()
        try:
            file_path = Path(file_path_str)
            if not file_path.exists():
                logger.warning(f"  [bulk] File not found: {file_path.name}")
                self.stats["errors"] += 1
                return

            content = file_path.read_text(encoding="utf-8", errors="ignore")
            if not content.strip():
                logger.debug(f"  [bulk] Skipped empty: {file_path.name}")
                return

            if self._is_duplicate(content):
                logger.debug(f"  [bulk] Skipped duplicate: {file_path.name}")
                self.stats["duplicates_skipped"] += 1
                return

            success = await core.ainsert_fast(content, str(file_path))
            if success:
                self.ingested_hashes.add(self._content_hash(content))
                self.stats["total_ingested"] += 1
                logger.info(f"  ✓ [⚡bulk]: {file_path.name}")
                # Track for future enrichment only if not already done
                fp_str = str(file_path)
                if fp_str not in self._enrichment_done:
                    pending_path = self._enrichment_pending_path()
                    pending_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(pending_path, "a") as ef:
                        ef.write(fp_str + "\n")
                else:
                    logger.debug(
                        f"  [bulk] Skipped enrichment_pending (already done): "
                        f"{file_path.name}"
                    )
            else:
                self.stats["errors"] += 1
                logger.error(f"  ✗ [⚡bulk] Failed: {file_path.name}")

        except Exception as e:
            self.stats["errors"] += 1
            self.stats["last_error"] = f"{file_path_str}: {e!s}"
            logger.exception(f"  ✗ [bulk] Error processing {file_path_str}: {e}")

    async def _bulk_drain_worker(
        self, historical: list[str], pending_file: Path
    ) -> None:
        """Background worker: drains historical backlog with ainsert_fast.

        Priority logic: before each file, waits until _realtime_queue is empty.
        This guarantees realtime (new/modified) files are always processed first.

        Holds _ingest_lock per-file so LightRAG is never written concurrently.
        Saves progress every 10 files for crash recovery.
        """
        if not historical:
            logger.info("[bulk] No historical files — bulk worker idle")
            return

        total = len(historical)
        logger.info(f"📦 Bulk drain worker: {total} historical files to process")

        remaining = list(historical)
        processed = 0

        while remaining and self.running:
            # Yield priority: wait until realtime queue is drained
            while not self._realtime_queue.empty() and self.running:
                logger.debug("[bulk] Realtime queue active — yielding (200ms)")
                await asyncio.sleep(0.2)

            if not self.running:
                break

            file_path_str = remaining[0]

            # One file at a time under the lock so realtime can interleave between files
            async with self._ingest_lock:
                await self._process_one_historical(file_path_str)

            remaining.pop(0)
            processed += 1

            # Checkpoint every 10 files
            if processed % 10 == 0:
                self._save_pending_files(pending_file, remaining)
                pct = (processed / total) * 100
                logger.info(f"[bulk] Progress: {processed}/{total} ({pct:.1f}%)")

            if processed % 50 == 0:
                gc.collect()

            if processed % 10 == 0:
                self.registry.update_last_sync(self.db_name)

            # Pause to yield the event loop between files
            await asyncio.sleep(self.batch_config.bulk_worker_pause_sec)

        # Cleanup
        if not remaining:
            if pending_file.exists():
                pending_file.unlink()
                logger.info("[bulk] Pending file removed — drain complete")
        else:
            self._save_pending_files(pending_file, remaining)
            logger.info(f"[bulk] Interrupted at {processed}/{total} — progress saved")

        self.registry.update_last_sync(self.db_name)
        logger.info(f"✅ Bulk drain complete: {processed}/{total} files processed")

    async def _realtime_watch_worker(self) -> None:
        """Priority worker: detects and ingests new/modified files immediately.

        Drains _realtime_queue first (pre-seeded recent files + newly detected),
        then polls the filesystem for changes at watch_interval.

        Uses _ingest_lock per-file to interleave safely with _bulk_drain_worker.
        Graph extraction (entity/relations) runs for every file here — full pipeline.
        """
        assert self.entry is not None
        assert self.detector is not None

        logger.info(f"\n{'='*60}")
        logger.info("REALTIME WATCH WORKER — monitoring for new/modified files")
        logger.info(f"{'='*60}")

        # Establish filesystem baseline (so detect_changes knows what's "new")
        self.detector.scan_files()
        logger.info(f"Baseline: {len(self.detector.known_files)} files tracked")
        logger.info(f"Polling every {self.entry.watch_interval}s")

        while self.running:
            # --- Drain pre-seeded + newly detected items from realtime queue ---
            while not self._realtime_queue.empty():
                try:
                    file_path_str = self._realtime_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

                file_path = Path(file_path_str)
                if not file_path.exists():
                    logger.debug(f"[realtime] File gone: {file_path.name}")
                    continue

                # Lock ensures we don't overlap with bulk worker
                async with self._ingest_lock:
                    await self._ingest_changes(
                        new_files={file_path},
                        modified_files=set(),
                    )

            # --- Detect new filesystem changes ---
            new_files, modified_files, deleted_files = self.detector.detect_changes()

            if new_files or modified_files:
                n_changes = len(new_files) + len(modified_files)
                logger.info(
                    f"Changes: +{len(new_files)} new, ~{len(modified_files)} modified, "
                    f"-{len(deleted_files)} deleted"
                )
                if n_changes >= self.batch_config.batch_size:
                    logger.info(
                        f"📦 Multiple changes ({n_changes}) — queued for priority processing"
                    )
                for fp in new_files | modified_files:
                    await self._realtime_queue.put(str(fp))
            else:
                logger.debug("No changes detected")

            await asyncio.sleep(self.entry.watch_interval)

    async def _process_batch(self, batch: list[str]) -> tuple[int, int, int]:
        """Process a batch of files using existing ingestion logic.

        Returns:
            (ingested, skipped, errors)

        """
        # Get or create core
        core = await self._get_core()

        ingested = 0
        skipped = 0
        errors = 0

        for file_path_str in batch:
            try:
                file_path = Path(file_path_str)
                if not file_path.exists():
                    logger.warning(f"  File not found: {file_path.name}")
                    errors += 1
                    continue

                # Read content
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                if not content.strip():
                    logger.debug(f"  Skipped empty: {file_path.name}")
                    skipped += 1
                    continue

                # Check for duplicate
                if self._is_duplicate(content):
                    logger.debug(f"  Skipped duplicate: {file_path.name}")
                    skipped += 1
                    self.stats["duplicates_skipped"] += 1
                    continue

                # Route by file age: old files → fast (embed only), recent → full pipeline
                cutoff_ts = time.time() - (self.batch_config.bulk_cutoff_days * 86400)
                try:
                    is_old = file_path.stat().st_mtime < cutoff_ts
                except OSError:
                    is_old = False  # if can't stat, default to full mode

                if is_old:
                    success = await core.ainsert_fast(content, str(file_path))
                    mode_label = "⚡fast"
                else:
                    success = await core.ainsert(content, str(file_path))
                    mode_label = "🔬full"

                if success:
                    self.ingested_hashes.add(self._content_hash(content))
                    ingested += 1
                    self.stats["total_ingested"] += 1
                    logger.info(f"  ✓ Ingested [{mode_label}]: {file_path.name}")
                    if is_old:
                        enrichment_file = (
                            Path.home()
                            / ".hybridrag"
                            / "enrichment_pending"
                            / f"{self.db_name}.txt"
                        )
                        enrichment_file.parent.mkdir(parents=True, exist_ok=True)
                        with open(enrichment_file, "a") as ef:
                            ef.write(str(file_path) + "\n")
                else:
                    errors += 1
                    self.stats["errors"] += 1
                    logger.error(f"  ✗ Failed [{mode_label}]: {file_path.name}")

            except Exception as e:
                errors += 1
                self.stats["errors"] += 1
                logger.exception(f"  ✗ Error processing {file_path_str}: {e}")

        return ingested, skipped, errors

    async def _run_batch_mode(self, pending_file: Path) -> None:
        """Run batch ingestion mode with resource monitoring.

        Processes pending files in batches until complete, then returns.
        """
        assert self.entry is not None, "Database entry must be loaded"

        # Load pending files
        pending = self._load_pending_files(pending_file)
        if not pending:
            logger.info("✅ No pending files - batch mode skipped")
            return

        total_files = len(pending)
        logger.info(f"📦 Batch mode starting: {total_files} files pending")
        logger.info(
            f"   Batch sizes: {self.batch_config.batch_size} (normal <{self.batch_config.high_load_cpu_percent}% CPU) / "
            f"{self.batch_config.batch_size_low} (high {self.batch_config.high_load_cpu_percent}-{self.batch_config.critical_cpu_percent}% CPU) / "
            f"{self.batch_config.batch_size_critical} (critical >{self.batch_config.critical_cpu_percent}% CPU — never blocks)"
        )

        total_ingested = 0
        total_skipped = 0
        total_errors = 0
        batch_num = 0

        while pending:
            batch_num += 1

            # Check load level and adjust batch size (no blocking — always continues)
            load_level, load_reason = self.resource_monitor.get_load_level()

            if load_level == "critical":
                current_batch_size = self.batch_config.batch_size_critical
                logger.info(
                    f"🔴 Critical load ({load_reason}) - 1 file at a time (no pause)"
                )
            elif load_level == "high":
                current_batch_size = self.batch_config.batch_size_low
                logger.info(
                    f"🐢 High load ({load_reason}) - reduced batch size: {current_batch_size} files"
                )
            else:
                current_batch_size = self.batch_config.batch_size

            # Take next batch
            batch = pending[:current_batch_size]
            remaining = pending[current_batch_size:]

            # Process batch
            logger.info(
                f"\n🔄 Batch {batch_num}: Processing {len(batch)} files ({len(remaining)} remaining)"
            )
            ingested, skipped, errors = await self._process_batch(batch)

            # Update stats
            total_ingested += ingested
            total_skipped += skipped
            total_errors += errors

            # Save progress (for pause/resume)
            self._save_pending_files(pending_file, remaining)

            # Log progress
            progress_pct = ((total_files - len(remaining)) / total_files) * 100
            logger.info(
                f"   Batch complete: +{ingested} ingested, ~{skipped} skipped, x{errors} errors"
            )
            logger.info(
                f"   Overall progress: {progress_pct:.1f}% ({total_files - len(remaining)}/{total_files})"
            )

            # Update pending list
            pending = remaining

            # Update last_sync after each batch
            self.registry.update_last_sync(self.db_name)

            # Force garbage collection
            gc.collect()

            # Sleep between batches (unless we're done)
            if pending:
                await asyncio.sleep(self.batch_config.sleep_between_batches)

        # Final summary
        logger.info("\n" + "=" * 60)
        logger.info("🎉 BATCH MODE COMPLETE!")
        logger.info(f"   Total ingested: {total_ingested}")
        logger.info(f"   Duplicates skipped: {total_skipped}")
        logger.info(f"   Errors: {total_errors}")
        logger.info("=" * 60)

        # Clean up pending file
        if pending_file.exists():
            pending_file.unlink()
            logger.info("✓ Cleaned up pending file")

        # Record to database metadata
        if total_ingested > 0:
            try:
                assert self.entry.source_folder is not None, "Source folder must be set"
                db_metadata = DatabaseMetadata(self.entry.path)
                db_metadata.record_ingestion(
                    folder_path=self.entry.source_folder,
                    files_processed=total_ingested,
                    success=(total_errors == 0),
                    notes=f"Batch mode: +{total_ingested} ingested, ~{total_skipped} skipped, x{total_errors} errors",
                )
            except Exception as e:
                logger.warning(f"Failed to record ingestion metadata: {e}")

    def _acquire_lock(self) -> bool:
        """Acquire exclusive lock on PID file to prevent duplicate daemons.

        Uses fcntl.flock() for proper file locking. The lock is held for
        the lifetime of the process (via the file descriptor).

        Returns:
            True if lock acquired, False if another watcher is running

        """
        # Check if already running (with lock verification)
        running, existing_pid = is_watcher_running(self.db_name)
        if running:
            logger.error(
                f"Watcher already running for {self.db_name} (PID: {existing_pid})"
            )
            return False

        # Acquire lock and write PID atomically
        self._lock_fd = acquire_watcher_lock(self.db_name, os.getpid())
        if self._lock_fd is None:
            logger.error(
                f"Failed to acquire lock for {self.db_name} - another instance may be starting"
            )
            return False

        logger.info(f"PID file: {self.pid_file} (locked)")
        return True

    def _release_lock(self) -> None:
        """Release PID file lock and clean up."""
        if self._lock_fd is not None:
            release_watcher_lock(self._lock_fd, self.db_name)
            self._lock_fd = None

    def _signal_handler(self, signum, _frame) -> None:
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False

    async def _get_core(self):
        """Get or create the LightRAG core instance (lazy initialization).

        Reuses the same core instance across batches to avoid reloading
        the entire graph (56k nodes, 104k edges) on each batch.

        Uses backend configuration from registry to determine storage backend:
        - JSON backend (default): NanoVectorDB + NetworkX
        - PostgreSQL backend: pgvector + Apache AGE
        """
        assert self.entry is not None, "Database entry must be loaded"

        if self._core is None:
            logger.info("Lazy-initializing LightRAG core (first use)...")
            from src.config.app_config import HybridRAGConfig
            from src.lightrag_core import HybridLightRAGCore

            self._config = HybridRAGConfig()
            self._config.lightrag.working_dir = self.entry.path

            if self.entry.model:
                self._config.lightrag.model_name = self.entry.model

            # Get backend configuration from registry entry
            backend_config = self.entry.get_backend_config()
            logger.info(f"Using backend: {backend_config.backend_type.value}")

            if backend_config.backend_type == BackendType.POSTGRESQL:
                logger.info(
                    f"  PostgreSQL: {backend_config.postgres_host}:"
                    f"{backend_config.postgres_port}/{backend_config.postgres_database}",
                )

            # Initialize core with backend configuration
            self._core = HybridLightRAGCore(self._config, backend_config=backend_config)
            await self._core._ensure_initialized()
            logger.info("LightRAG core initialized successfully")

        return self._core

    def _release_core(self) -> None:
        """Release the core instance to free memory if needed."""
        if self._core is not None:
            logger.info("Releasing LightRAG core to free memory...")
            self._core = None
            self._config = None
            gc.collect()

    def _check_json_file_sizes(self) -> None:
        """Check JSON storage file sizes against thresholds.

        Proactive monitoring for JSON backend to warn users before OOM crashes.
        Skips checks if using PostgreSQL backend (not applicable).

        Thresholds from BackendConfig:
        - file_size_warning_mb: Warn when any file exceeds this (default 500MB)
        - total_size_warning_mb: Warn when total exceeds this (default 2GB)
        """
        assert self.entry is not None, "Database entry must be loaded"

        # Skip if not using JSON backend
        backend_config = self.entry.get_backend_config()
        if backend_config.backend_type != BackendType.JSON:
            logger.debug("Skipping file size check - not using JSON backend")
            return

        # Get thresholds from config
        file_threshold_bytes = backend_config.file_size_warning_mb * 1024 * 1024
        total_threshold_bytes = backend_config.total_size_warning_mb * 1024 * 1024

        # Scan JSON files in database directory
        db_path = Path(self.entry.path)
        if not db_path.exists():
            return

        json_files = list(db_path.glob("*.json"))
        total_size = 0
        large_files = []

        for json_file in json_files:
            try:
                file_size = json_file.stat().st_size
                total_size += file_size

                if file_size >= file_threshold_bytes:
                    large_files.append((json_file.name, file_size))
            except OSError as e:
                logger.warning(f"Could not stat {json_file}: {e}")

        # Warn about individual large files
        for filename, size in large_files:
            size_mb = size / (1024 * 1024)
            logger.warning(
                f"🚨 LARGE FILE: {filename} is {size_mb:.1f}MB "
                f"(threshold: {backend_config.file_size_warning_mb}MB)",
            )
            logger.warning(
                f"   Consider migrating to PostgreSQL: "
                f"hybridrag backend migrate --from json --to postgres {self.db_name}",
            )

        # Warn about total size
        if total_size >= total_threshold_bytes:
            total_mb = total_size / (1024 * 1024)
            logger.warning(
                f"🚨 TOTAL SIZE: {len(json_files)} JSON files using {total_mb:.1f}MB "
                f"(threshold: {backend_config.total_size_warning_mb}MB)",
            )
            logger.warning(
                f"   Database '{self.db_name}' approaching memory limits. "
                f"Consider migrating to PostgreSQL:",
            )
            logger.warning(
                f"   hybridrag backend migrate --from json --to postgres {self.db_name}",
            )

            # Alert via alerting system for severe size issues
            if total_size >= total_threshold_bytes * 1.5:  # 50% over threshold
                self.alert_manager.alert_watcher_error(
                    self.db_name,
                    f"JSON storage at {total_mb:.0f}MB - risk of OOM crash",
                    {
                        "total_size_mb": round(total_mb, 1),
                        "threshold_mb": backend_config.total_size_warning_mb,
                        "file_count": len(json_files),
                        "recommendation": "Migrate to PostgreSQL backend",
                    },
                )

    async def _ingest_changes(
        self,
        new_files: set[Path],
        modified_files: set[Path],
    ) -> None:
        """Ingest changed files into the database.

        Args:
            new_files: Set of new file paths
            modified_files: Set of modified file paths

        """
        assert self.entry is not None, "Database entry must be loaded"

        all_changed = new_files | modified_files
        if not all_changed:
            return

        total_files = len(all_changed)
        logger.info(
            f"Processing {total_files} changed file(s) in batches of {self.BATCH_SIZE}"
        )

        # T012: Track ingestion timing for performance monitoring
        ingest_start_time = time.time()

        try:
            # Get or create the reusable core instance (lazy initialization)
            # This avoids reloading the 56k node graph on every batch
            core = await self._get_core()

            ingested_count = 0
            skipped_count = 0
            error_count = 0

            # Convert to list for batch processing
            file_list: list[Path] = list(all_changed)

            # Process files in batches to prevent memory buildup
            for batch_start in range(0, total_files, self.BATCH_SIZE):
                batch_end = min(batch_start + self.BATCH_SIZE, total_files)
                batch = file_list[batch_start:batch_end]
                batch_num = (batch_start // self.BATCH_SIZE) + 1
                total_batches = (total_files + self.BATCH_SIZE - 1) // self.BATCH_SIZE

                logger.info(
                    f"Processing batch {batch_num}/{total_batches} ({len(batch)} files)"
                )

                # Process each file in the batch
                for file_path in batch:
                    try:
                        content = file_path.read_text(encoding="utf-8", errors="ignore")
                        if not content.strip():
                            logger.debug(f"  Skipped empty file: {file_path.name}")
                            continue

                        # Check for duplicate content
                        content_hash = self._content_hash(content)
                        if content_hash in self.ingested_hashes:
                            logger.debug(f"  Skipped duplicate: {file_path.name}")
                            skipped_count += 1
                            self.stats["duplicates_skipped"] += 1
                            continue

                        # Ingest the file
                        success = await core.ainsert(content, str(file_path))
                        if success:
                            self.ingested_hashes.add(content_hash)
                            ingested_count += 1
                            self.stats["total_ingested"] += 1
                            logger.info(f"  [OK] Ingested: {file_path.name}")
                        else:
                            error_count += 1
                            self.stats["errors"] += 1
                            logger.error(f"  [FAIL] Failed: {file_path.name}")

                    except Exception as e:
                        error_count += 1
                        self.stats["errors"] += 1
                        self.stats["last_error"] = f"{file_path.name}: {e!s}"
                        logger.exception(
                            f"  [ERROR] Error ingesting {file_path.name}: {e}"
                        )
                        # Create alert for failed ingestion
                        self.alert_manager.alert_ingestion_failed(
                            self.db_name,
                            file_path.name,
                            str(e),
                            {"file_path": str(file_path)},
                        )

                # Force garbage collection after each batch to prevent memory buildup
                gc.collect()
                logger.debug(f"Batch {batch_num} complete, gc.collect() called")

                # Update last_sync after each batch (not just at end)
                # This ensures sync timestamp stays current even with continuous file changes
                self.registry.update_last_sync(self.db_name)

            # Log summary
            logger.info(
                f"All batches complete: +{ingested_count} ingested, ~{skipped_count} duplicates skipped, x{error_count} errors"
            )
            logger.info(
                f"Session totals: {self.stats['total_ingested']} ingested, {self.stats['duplicates_skipped']} skipped, {self.stats['errors']} errors"
            )

            # Record ingestion to database_metadata.json for TUI monitor timeline
            if ingested_count > 0:
                try:
                    assert (
                        self.entry.source_folder is not None
                    ), "Source folder must be set"
                    db_metadata = DatabaseMetadata(self.entry.path)
                    db_metadata.record_ingestion(
                        folder_path=self.entry.source_folder,
                        files_processed=ingested_count,
                        success=(error_count == 0),
                        notes=f"Watcher batch: +{ingested_count} ingested, ~{skipped_count} skipped, x{error_count} errors",
                    )
                    logger.debug(f"Recorded ingestion history: {ingested_count} files")
                except Exception as e:
                    logger.warning(f"Failed to record ingestion metadata: {e}")

            # T012-T013: Record performance metrics and check for degradation
            ingest_duration = time.time() - ingest_start_time
            if ingested_count > 0 and self.performance_tracker:
                degradation_warning = self.performance_tracker.record_ingestion(
                    docs_count=ingested_count,
                    duration_seconds=ingest_duration,
                )

                # T013: Warn on performance degradation
                if degradation_warning:
                    logger.warning(
                        f"🚨 PERFORMANCE DEGRADATION DETECTED: "
                        f"Current rate {degradation_warning['current_rate']:.1f} docs/min "
                        f"is {degradation_warning['degradation_pct']:.0f}% slower than "
                        f"baseline {degradation_warning['baseline_rate']:.1f} docs/min",
                    )
                    logger.warning(
                        f"   This may indicate JSON storage files are too large. "
                        f"Consider migrating to PostgreSQL: "
                        f"hybridrag backend migrate --from json --to postgres {self.db_name}",
                    )

                    # Alert via alerting system
                    self.alert_manager.alert_watcher_error(
                        self.db_name,
                        f"Performance degraded by {degradation_warning['degradation_pct']:.0f}%",
                        degradation_warning,
                    )

            # Create alert if there were errors in the batch
            if error_count > 0:
                self.alert_manager.alert_ingestion_partial(
                    self.db_name,
                    total=total_files,
                    failed=error_count,
                    details={"ingested": ingested_count, "skipped": skipped_count},
                )

            # Proactive monitoring: check JSON file sizes after each ingest cycle
            # Warns users before OOM crashes if files are too large
            self._check_json_file_sizes()

        except Exception as e:
            self.stats["errors"] += 1
            self.stats["last_error"] = str(e)
            logger.exception(f"Ingestion batch failed: {e}")
            # Create critical alert for batch failure
            self.alert_manager.alert_watcher_error(
                self.db_name,
                f"Batch ingestion failed: {e!s}",
                {"files_attempted": total_files},
            )
            # On critical failure, release core to free memory
            self._release_core()

    async def run(self) -> None:
        """Run the watcher daemon with dual-queue priority architecture.

        Startup logic (unchanged smart detection):
        1. Pending list exists  → split by age, resume
        2. Empty DB             → discover, split by age
        3. DB has docs          → watch mode only

        Dual workers (concurrent asyncio tasks):
        - _realtime_watch_worker: detects new/modified files, ingests with full
          pipeline (ainsert + entity extraction). Highest priority.
        - _bulk_drain_worker: drains historical backlog with ainsert_fast
          (embed-only, no graph). Pauses whenever realtime queue is non-empty.

        Both workers share _ingest_lock (one file at a time to LightRAG).
        Files never lost: enrichment_pending tracks fast-inserted docs for
        future graph backfill via apipeline_process_enqueue_documents().
        """
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        if not self._acquire_lock():
            logger.error("Failed to start - another watcher instance is running")
            return

        assert self.entry is not None, "Database entry must be loaded"
        assert self.detector is not None, "File detector must be initialized"

        self.running = True
        logger.info(f"Watcher started for: {self.db_name}")
        logger.info(f"Watch interval: {self.entry.watch_interval}s")
        logger.info(
            f"Dual-queue mode: realtime (🔬full) + bulk (⚡fast, "
            f"cutoff={self.batch_config.bulk_cutoff_days}d)"
        )

        try:
            # ── SMART DETECTION PHASE ─────────────────────────────────────────
            pending_file = self._get_pending_file_path()
            historical: list[str] = []

            if pending_file.exists():
                # Case 1: Resume from existing pending list
                pending = self._load_pending_files(pending_file)
                logger.info(
                    f"📦 Pending list detected ({len(pending)} files) — resuming"
                )
                historical, recent = self._split_pending_by_age(pending)
                for fp in recent:
                    await self._realtime_queue.put(fp)
                logger.info(f"   Seeded realtime queue: {len(recent)} recent files")

            else:
                doc_count = await self._get_document_count()
                logger.info(f"📊 Database: {doc_count} documents")

                if doc_count == 0:
                    # Case 2: Empty DB — discover and split
                    logger.info("🔍 Empty database — initial bulk ingestion")
                    discovered = self._discover_files(pending_file)

                    if discovered > 0:
                        pending = self._load_pending_files(pending_file)
                        historical, recent = self._split_pending_by_age(pending)
                        for fp in recent:
                            await self._realtime_queue.put(fp)
                        logger.info(
                            f"   Seeded realtime queue: {len(recent)} recent files"
                        )
                    else:
                        logger.info("   No files discovered — watch mode only")
                else:
                    # Case 3: DB populated — jump straight to watch mode
                    logger.info("✓ Database populated — starting watch mode")

            # ── DUAL-WORKER PHASE ─────────────────────────────────────────────
            # bulk_drain_worker   → background, historical files, ainsert_fast
            # realtime_watch_worker → priority, new/modified files, ainsert
            bulk_task = asyncio.create_task(
                self._bulk_drain_worker(historical, pending_file),
                name="bulk_drain_worker",
            )
            realtime_task = asyncio.create_task(
                self._realtime_watch_worker(),
                name="realtime_watch_worker",
            )

            results = await asyncio.gather(
                bulk_task, realtime_task, return_exceptions=True
            )

            task_names = ["bulk_drain_worker", "realtime_watch_worker"]
            for task_name, result in zip(task_names, results):
                if isinstance(result, Exception):
                    logger.exception(f"Task '{task_name}' raised: {result}")
                    self.alert_manager.alert_watcher_error(
                        self.db_name,
                        f"Task {task_name} failed: {result!s}",
                        {"task": task_name},
                    )

        except Exception as e:
            logger.exception(f"Watcher error: {e}")
            self.alert_manager.alert_watcher_stopped(
                self.db_name,
                f"Unexpected error: {e!s}",
                {"error": str(e), "stats": self.stats},
            )
        finally:
            self._release_lock()
            self._release_core()
            logger.info("Watcher stopped")
            if self.stats["errors"] > 0:
                self.alert_manager.alert_info(
                    self.db_name,
                    f"Watcher stopped with {self.stats['errors']} total errors",
                    self.stats,
                )


def main() -> None:
    """Main entry point."""
    global logger

    if len(sys.argv) < 2:
        sys.exit(1)

    db_name = sys.argv[1]

    # Setup logging with rotation (200MB max, 5 backups, 7-day cleanup)
    logger = setup_logging(db_name)
    logger.info(f"Starting watcher for database: {db_name}")

    try:
        daemon = WatcherDaemon(db_name)
        asyncio.run(daemon.run())
    except KeyboardInterrupt:
        logger.info("Shutdown requested")
    except ValueError as e:
        logger.exception(f"Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
