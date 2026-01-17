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
from src.config.config import BackendType
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

    batch_size: int = 10  # Files per batch (normal load)
    batch_size_low: int = 2  # Files per batch (high load)
    sleep_between_batches: float = 2.0  # Seconds
    high_load_cpu_percent: float = 90.0  # Switch to 2 files if CPU above this
    high_load_memory_percent: float = 90.0  # Switch to 2 files if memory above this
    critical_cpu_percent: float = 95.0  # Pause if CPU above this
    critical_memory_percent: float = 95.0  # Pause if memory above this
    check_interval: float = 5.0  # Seconds between resource checks


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

        # Critical load - pause completely
        if cpu_percent > self.config.critical_cpu_percent:
            return "critical", f"CPU: {cpu_percent:.1f}% > {self.config.critical_cpu_percent}%"
        if memory_percent > self.config.critical_memory_percent:
            return "critical", f"Memory: {memory_percent:.1f}% > {self.config.critical_memory_percent}%"

        # High load - reduce batch size to 2
        if cpu_percent > self.config.high_load_cpu_percent:
            return "high", f"CPU: {cpu_percent:.1f}% (high load)"
        if memory_percent > self.config.high_load_memory_percent:
            return "high", f"Memory: {memory_percent:.1f}% (high load)"

        # Normal load - full batch size
        return "normal", ""

    async def wait_until_system_ready(self, logger_instance: logging.Logger) -> None:
        """Wait until system load is not critical."""
        while True:
            level, reason = self.get_load_level()
            if level != "critical":
                return

            logger_instance.info(f"⏸️  Critical load ({reason}), pausing ingestion...")
            await asyncio.sleep(30)  # Check again in 30 seconds


class PerformanceTracker:
    """Tracks ingestion performance metrics with rolling average calculation.

    Used for proactive performance monitoring (T012-T013):
    - Maintains a rolling window of recent ingestion rates (docs/minute)
    - Detects performance degradation when current rate drops below baseline
    - Warns users when ingestion is >50% slower than baseline
    """

    def __init__(self, window_size: int = 20, degradation_threshold_pct: int = 50) -> None:
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
            logger.info(f"📊 Performance baseline established: {self._baseline_rate:.1f} docs/min")

        # Check for degradation
        self._cycles_since_warning += 1
        if self._baseline_rate and len(self._rates) >= 3 and self._cycles_since_warning >= self._warning_cooldown:
            current_avg = self._calculate_recent_average()
            degradation_pct = ((self._baseline_rate - current_avg) / self._baseline_rate) * 100

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
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    ))
    log.addHandler(file_handler)

    # Also log to stderr for systemd/console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s",
    ))
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
                logger.info(f"Loaded {len(self.ingested_hashes)} existing document hashes")
            except Exception as e:
                logger.warning(f"Could not load doc status: {e}")

    def _content_hash(self, content: str) -> str:
        """Generate MD5 hash of content (matching LightRAG's approach)."""
        return hashlib.md5(content.encode()).hexdigest()

    def _is_duplicate(self, content: str) -> bool:
        """Check if content has already been ingested."""
        content_hash = self._content_hash(content)
        return content_hash in self.ingested_hashes

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
        # Use extensions from config, or default to .md if not specified
        extensions = self.entry.file_extensions if self.entry.file_extensions else [".md"]
        logger.info(f"  File extensions from config: {self.entry.file_extensions}")
        # For specstory source type, only watch .specstory folders
        specstory_only = (self.entry.source_type == "specstory")
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

        logger.info(f"  Performance tracking enabled (degradation threshold: {degradation_threshold}%)")

    def _get_pending_file_path(self) -> Path:
        """Get the path to the pending files list."""
        return Path.home() / ".hybridrag" / "batch_ingestion" / f"{self.db_name}.pending.txt"

    async def _get_document_count(self) -> int:
        """Get document count from LightRAG database.

        Returns:
            Number of documents in database, 0 if unable to determine

        """
        assert self.entry is not None, "Database entry must be loaded"
        try:
            doc_status_path = Path(self.entry.path) / "kv_store_doc_status.json"
            if doc_status_path.exists():
                with open(doc_status_path) as f:
                    doc_status = json.load(f)
                # Count document entries (doc-{hash} format)
                return sum(1 for key in doc_status if key.startswith("doc-"))
            return 0
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

                # Ingest using existing core
                success = await core.ainsert(content, str(file_path))
                if success:
                    self.ingested_hashes.add(self._content_hash(content))
                    ingested += 1
                    self.stats["total_ingested"] += 1
                    logger.info(f"  ✓ Ingested: {file_path.name}")
                else:
                    errors += 1
                    self.stats["errors"] += 1
                    logger.error(f"  ✗ Failed: {file_path.name}")

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
        logger.info(f"   Batch size: {self.batch_config.batch_size} (normal) / {self.batch_config.batch_size_low} (high load)")
        logger.info(f"   Resource thresholds: High load at {self.batch_config.high_load_cpu_percent}% CPU, Critical at {self.batch_config.critical_cpu_percent}% CPU")

        total_ingested = 0
        total_skipped = 0
        total_errors = 0
        batch_num = 0

        while pending:
            batch_num += 1

            # Wait if system is at critical load
            await self.resource_monitor.wait_until_system_ready(logger)

            # Check load level and adjust batch size
            load_level, load_reason = self.resource_monitor.get_load_level()

            if load_level == "high":
                current_batch_size = self.batch_config.batch_size_low
                logger.info(f"🐢 High load detected ({load_reason}) - using reduced batch size: {current_batch_size} files")
            else:
                current_batch_size = self.batch_config.batch_size

            # Take next batch
            batch = pending[:current_batch_size]
            remaining = pending[current_batch_size:]

            # Process batch
            logger.info(f"\n🔄 Batch {batch_num}: Processing {len(batch)} files ({len(remaining)} remaining)")
            ingested, skipped, errors = await self._process_batch(batch)

            # Update stats
            total_ingested += ingested
            total_skipped += skipped
            total_errors += errors

            # Save progress (for pause/resume)
            self._save_pending_files(pending_file, remaining)

            # Log progress
            progress_pct = ((total_files - len(remaining)) / total_files) * 100
            logger.info(f"   Batch complete: +{ingested} ingested, ~{skipped} skipped, x{errors} errors")
            logger.info(f"   Overall progress: {progress_pct:.1f}% ({total_files - len(remaining)}/{total_files})")

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
        logger.info("\n" + "="*60)
        logger.info("🎉 BATCH MODE COMPLETE!")
        logger.info(f"   Total ingested: {total_ingested}")
        logger.info(f"   Duplicates skipped: {total_skipped}")
        logger.info(f"   Errors: {total_errors}")
        logger.info("="*60)

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
            logger.error(f"Watcher already running for {self.db_name} (PID: {existing_pid})")
            return False

        # Acquire lock and write PID atomically
        self._lock_fd = acquire_watcher_lock(self.db_name, os.getpid())
        if self._lock_fd is None:
            logger.error(f"Failed to acquire lock for {self.db_name} - another instance may be starting")
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
            from config.config import HybridRAGConfig
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
        logger.info(f"Processing {total_files} changed file(s) in batches of {self.BATCH_SIZE}")

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

                logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} files)")

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
                        logger.exception(f"  [ERROR] Error ingesting {file_path.name}: {e}")
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
            logger.info(f"All batches complete: +{ingested_count} ingested, ~{skipped_count} duplicates skipped, x{error_count} errors")
            logger.info(f"Session totals: {self.stats['total_ingested']} ingested, {self.stats['duplicates_skipped']} skipped, {self.stats['errors']} errors")

            # Record ingestion to database_metadata.json for TUI monitor timeline
            if ingested_count > 0:
                try:
                    assert self.entry.source_folder is not None, "Source folder must be set"
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
        """Run the watcher daemon loop with smart detection.

        Smart detection logic:
        1. Check if pending list exists → Resume batch mode (no scan)
        2. If no pending list, check database document count:
           - Count == 0 → Run discovery, then batch mode (bulk ingestion)
           - Count > 0 → Skip to normal watch mode
        3. After batch mode completes → Transition to normal watch mode
        """
        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        # Acquire exclusive lock on PID file (prevents duplicate daemons)
        if not self._acquire_lock():
            logger.error("Failed to start - another watcher instance is running")
            return

        assert self.entry is not None, "Database entry must be loaded"
        assert self.detector is not None, "File detector must be initialized"

        self.running = True
        logger.info(f"Watcher started for: {self.db_name}")
        logger.info(f"Watch interval: {self.entry.watch_interval}s")

        try:
            # SMART DETECTION PHASE
            pending_file = self._get_pending_file_path()

            if pending_file.exists():
                # Case 1: Resume batch mode (pending list exists)
                pending_count = len(self._load_pending_files(pending_file))
                logger.info(f"📦 Pending list detected ({pending_count} files) - resuming batch mode")
                logger.info("   (No directory scan needed - using existing list)")
                await self._run_batch_mode(pending_file)
                logger.info("✓ Batch mode complete - transitioning to normal watch mode")

            else:
                # No pending list - check database state
                doc_count = await self._get_document_count()
                logger.info(f"📊 Database status: {doc_count} documents")

                if doc_count == 0:
                    # Case 2: Empty database - run discovery and batch mode
                    logger.info("🔍 Empty database detected - running initial bulk ingestion")
                    logger.info("   Step 1: Discovery (find all files)")
                    discovered = self._discover_files(pending_file)

                    if discovered > 0:
                        logger.info(f"   Step 2: Batch ingestion ({discovered} files)")
                        await self._run_batch_mode(pending_file)
                        logger.info("✓ Initial bulk ingestion complete - transitioning to normal watch mode")
                    else:
                        logger.info("   No files discovered - starting normal watch mode")
                else:
                    # Case 3: Database has documents - skip to normal mode
                    logger.info("✓ Database populated - starting normal watch mode")

            # NORMAL WATCH MODE
            # Do initial scan to establish baseline for change detection
            logger.info(f"\n{'='*60}")
            logger.info("NORMAL WATCH MODE - Monitoring for changes")
            logger.info(f"{'='*60}")
            self.detector.scan_files()
            logger.info(f"Baseline established: {len(self.detector.known_files)} file(s) tracked")
            logger.info(f"Checking for changes every {self.entry.watch_interval}s")

            # Watch loop
            while self.running:
                # Detect changes since last check
                new_files, modified_files, deleted_files = self.detector.detect_changes()

                if new_files or modified_files:
                    total_changes = len(new_files) + len(modified_files)
                    logger.info(f"Changes detected: +{len(new_files)} new, ~{len(modified_files)} modified, -{len(deleted_files)} deleted")

                    # Batch processing for multiple changes
                    if total_changes >= self.batch_config.batch_size:
                        logger.info(f"📦 Multiple changes detected - using batch mode ({total_changes} files)")
                        # Wait if system is busy
                        await self.resource_monitor.wait_until_system_ready(logger)

                    # Process changes
                    await self._ingest_changes(new_files, modified_files)
                else:
                    logger.debug("No changes detected")

                # Sleep until next check
                await asyncio.sleep(self.entry.watch_interval)

        except Exception as e:
            logger.exception(f"Watcher error: {e}")
            # Alert on unexpected watcher crash
            self.alert_manager.alert_watcher_stopped(
                self.db_name,
                f"Unexpected error: {e!s}",
                {"error": str(e), "stats": self.stats},
            )
        finally:
            self._release_lock()
            self._release_core()  # Release core on shutdown to free memory
            logger.info("Watcher stopped")
            # Alert on watcher stop (graceful or not)
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
