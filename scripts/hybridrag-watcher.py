#!/usr/bin/env python3
"""
HybridRAG Standalone Watcher Daemon
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
import gc
import os
import sys
import signal
import time
import logging
import hashlib
import json
from pathlib import Path
from datetime import datetime
from typing import Set, Optional, Dict, List

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from collections import OrderedDict
from src.database_registry import (
    get_registry, DatabaseEntry,
    get_watcher_pid_file, acquire_watcher_lock, release_watcher_lock,
    is_watcher_running
)
from src.alerting import get_alert_manager, AlertSeverity
from src.config.config import BackendConfig, BackendType


class PerformanceTracker:
    """
    Tracks ingestion performance metrics with rolling average calculation.

    Used for proactive performance monitoring (T012-T013):
    - Maintains a rolling window of recent ingestion rates (docs/minute)
    - Detects performance degradation when current rate drops below baseline
    - Warns users when ingestion is >50% slower than baseline
    """

    def __init__(self, window_size: int = 20, degradation_threshold_pct: int = 50):
        """
        Initialize performance tracker.

        Args:
            window_size: Number of ingestion cycles to include in rolling average
            degradation_threshold_pct: Warn when performance drops by this percentage
        """
        self._window_size = window_size
        self._degradation_threshold_pct = degradation_threshold_pct
        self._rates: List[float] = []  # docs/minute for each cycle
        self._baseline_rate: Optional[float] = None
        self._cycles_since_warning = 0
        self._warning_cooldown = 5  # Only warn every N cycles

    def record_ingestion(self, docs_count: int, duration_seconds: float) -> Optional[Dict]:
        """
        Record an ingestion cycle and check for performance degradation.

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
                    'baseline_rate': self._baseline_rate,
                    'current_rate': current_avg,
                    'degradation_pct': degradation_pct,
                    'threshold_pct': self._degradation_threshold_pct
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

    def get_stats(self) -> Dict:
        """Get current performance statistics."""
        return {
            'baseline_rate': self._baseline_rate,
            'current_avg': self._calculate_recent_average() if self._rates else None,
            'sample_count': len(self._rates),
            'window_size': self._window_size,
            'degradation_threshold_pct': self._degradation_threshold_pct
        }


class BoundedSet:
    """
    A set with a maximum size that evicts oldest items when full.

    Uses OrderedDict internally to maintain insertion order and provide
    O(1) membership testing while bounding memory usage.
    """

    def __init__(self, max_size: int = 100000):
        """
        Initialize bounded set.

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


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class FileChangeDetector:
    """
    Detects file changes in a directory.

    Tracks modification times and new files to determine what needs processing.
    """

    def __init__(
        self,
        folder: str,
        recursive: bool = True,
        extensions: Optional[list] = None,
        specstory_only: bool = False
    ):
        """
        Initialize the change detector.

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
        self.last_check: Optional[float] = None
        self.known_files: Set[Path] = set()
        self.file_mtimes: dict = {}

    def should_include(self, path: Path) -> bool:
        """Check if a file should be included based on filters."""
        # Check specstory folder filter first
        if self.specstory_only:
            # Only include files that are in a .specstory folder path
            path_parts = path.parts
            if not any(part == '.specstory' for part in path_parts):
                return False

        # Then check extension filter
        if self.extensions is None:
            return True
        return path.suffix.lower() in self.extensions

    def scan_files(self) -> Set[Path]:
        """Scan folder for all matching files."""
        files = set()

        if self.recursive:
            for file_path in self.folder.rglob('*'):
                if file_path.is_file() and self.should_include(file_path):
                    files.add(file_path)
        else:
            for file_path in self.folder.iterdir():
                if file_path.is_file() and self.should_include(file_path):
                    files.add(file_path)

        return files

    def detect_changes(self) -> tuple[Set[Path], Set[Path], Set[Path]]:
        """
        Detect file changes since last check.

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
                try:
                    self.file_mtimes[file_path] = file_path.stat().st_mtime
                except OSError:
                    pass

        self.last_check = current_time

        return new_files, modified_files, deleted_files


class WatcherDaemon:
    """
    Daemon process for watching a registered database.

    Polls for file changes and triggers ingestion when changes detected.
    Uses lazy initialization and batch processing to prevent OOM on large graphs.
    """

    # Maximum files to process in a single batch to prevent OOM
    BATCH_SIZE = 10

    # Maximum number of content hashes to track (prevents unbounded memory growth)
    # 100k MD5 hashes = ~3.2MB memory (32 chars * 100k)
    MAX_INGESTED_HASHES = 100000

    def __init__(self, db_name: str):
        """
        Initialize the watcher daemon.

        Args:
            db_name: Name of the registered database to watch
        """
        self.db_name = db_name
        self.registry = get_registry()
        self.entry: Optional[DatabaseEntry] = None
        self.detector: Optional[FileChangeDetector] = None
        self.running = False
        self.pid_file: Optional[Path] = None
        self._lock_fd: Optional[int] = None  # File descriptor for PID file lock
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
        self.performance_tracker: Optional[PerformanceTracker] = None

        # Load database entry (must be done first)
        self._load_entry()

        # Initialize performance tracker with threshold from backend config
        self._init_performance_tracker()

    def _load_ingested_hashes(self):
        """Load existing document hashes from the database's doc_status store."""
        doc_status_path = Path(self.entry.path) / "kv_store_doc_status.json"
        if doc_status_path.exists():
            try:
                with open(doc_status_path, 'r') as f:
                    doc_status = json.load(f)
                # Extract document hashes (doc-{hash} format)
                for doc_id in doc_status.keys():
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

    def _load_entry(self):
        """Load database entry from registry."""
        self.entry = self.registry.get(self.db_name)
        if not self.entry:
            raise ValueError(f"Database not found in registry: {self.db_name}")

        if not self.entry.source_folder:
            raise ValueError(f"No source folder configured for: {self.db_name}")

        if not os.path.exists(self.entry.source_folder):
            raise ValueError(f"Source folder does not exist: {self.entry.source_folder}")

        self.pid_file = get_watcher_pid_file(self.db_name)

        # Initialize change detector
        # Use extensions from config, or default to .md if not specified
        extensions = self.entry.file_extensions if self.entry.file_extensions else ['.md']
        logger.info(f"  File extensions from config: {self.entry.file_extensions}")
        # For specstory source type, only watch .specstory folders
        specstory_only = (self.entry.source_type == 'specstory')
        self.detector = FileChangeDetector(
            folder=self.entry.source_folder,
            recursive=self.entry.recursive,
            extensions=extensions,
            specstory_only=specstory_only
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

    def _init_performance_tracker(self):
        """
        Initialize performance tracker with thresholds from backend config.

        T014: Load configurable thresholds from registry backend_config.
        """
        backend_config = self.entry.get_backend_config()
        degradation_threshold = backend_config.performance_degradation_pct

        self.performance_tracker = PerformanceTracker(
            window_size=20,
            degradation_threshold_pct=degradation_threshold
        )

        logger.info(f"  Performance tracking enabled (degradation threshold: {degradation_threshold}%)")

    def _acquire_lock(self) -> bool:
        """
        Acquire exclusive lock on PID file to prevent duplicate daemons.

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

    def _release_lock(self):
        """Release PID file lock and clean up."""
        release_watcher_lock(self._lock_fd, self.db_name)
        self._lock_fd = None

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False

    async def _get_core(self):
        """
        Get or create the LightRAG core instance (lazy initialization).

        Reuses the same core instance across batches to avoid reloading
        the entire graph (56k nodes, 104k edges) on each batch.

        Uses backend configuration from registry to determine storage backend:
        - JSON backend (default): NanoVectorDB + NetworkX
        - PostgreSQL backend: pgvector + Apache AGE
        """
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
                    f"{backend_config.postgres_port}/{backend_config.postgres_database}"
                )

            # Initialize core with backend configuration
            self._core = HybridLightRAGCore(self._config, backend_config=backend_config)
            await self._core._ensure_initialized()
            logger.info("LightRAG core initialized successfully")

        return self._core

    def _release_core(self):
        """Release the core instance to free memory if needed."""
        if self._core is not None:
            logger.info("Releasing LightRAG core to free memory...")
            self._core = None
            self._config = None
            gc.collect()

    def _check_json_file_sizes(self) -> None:
        """
        Check JSON storage file sizes against thresholds.

        Proactive monitoring for JSON backend to warn users before OOM crashes.
        Skips checks if using PostgreSQL backend (not applicable).

        Thresholds from BackendConfig:
        - file_size_warning_mb: Warn when any file exceeds this (default 500MB)
        - total_size_warning_mb: Warn when total exceeds this (default 2GB)
        """
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
                f"(threshold: {backend_config.file_size_warning_mb}MB)"
            )
            logger.warning(
                f"   Consider migrating to PostgreSQL: "
                f"hybridrag backend migrate --from json --to postgres {self.db_name}"
            )

        # Warn about total size
        if total_size >= total_threshold_bytes:
            total_mb = total_size / (1024 * 1024)
            logger.warning(
                f"🚨 TOTAL SIZE: {len(json_files)} JSON files using {total_mb:.1f}MB "
                f"(threshold: {backend_config.total_size_warning_mb}MB)"
            )
            logger.warning(
                f"   Database '{self.db_name}' approaching memory limits. "
                f"Consider migrating to PostgreSQL:"
            )
            logger.warning(
                f"   hybridrag backend migrate --from json --to postgres {self.db_name}"
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
                        "recommendation": "Migrate to PostgreSQL backend"
                    }
                )

    async def _ingest_changes(
        self,
        new_files: Set[Path],
        modified_files: Set[Path]
    ):
        """
        Ingest changed files into the database.

        Args:
            new_files: Set of new file paths
            modified_files: Set of modified file paths
        """
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
            file_list: List[Path] = list(all_changed)

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
                        content = file_path.read_text(encoding='utf-8', errors='ignore')
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
                        self.stats["last_error"] = f"{file_path.name}: {str(e)}"
                        logger.error(f"  [ERROR] Error ingesting {file_path.name}: {e}")
                        # Create alert for failed ingestion
                        self.alert_manager.alert_ingestion_failed(
                            self.db_name,
                            file_path.name,
                            str(e),
                            {"file_path": str(file_path)}
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

            # T012-T013: Record performance metrics and check for degradation
            ingest_duration = time.time() - ingest_start_time
            if ingested_count > 0 and self.performance_tracker:
                degradation_warning = self.performance_tracker.record_ingestion(
                    docs_count=ingested_count,
                    duration_seconds=ingest_duration
                )

                # T013: Warn on performance degradation
                if degradation_warning:
                    logger.warning(
                        f"🚨 PERFORMANCE DEGRADATION DETECTED: "
                        f"Current rate {degradation_warning['current_rate']:.1f} docs/min "
                        f"is {degradation_warning['degradation_pct']:.0f}% slower than "
                        f"baseline {degradation_warning['baseline_rate']:.1f} docs/min"
                    )
                    logger.warning(
                        f"   This may indicate JSON storage files are too large. "
                        f"Consider migrating to PostgreSQL: "
                        f"hybridrag backend migrate --from json --to postgres {self.db_name}"
                    )

                    # Alert via alerting system
                    self.alert_manager.alert_watcher_error(
                        self.db_name,
                        f"Performance degraded by {degradation_warning['degradation_pct']:.0f}%",
                        degradation_warning
                    )

            # Create alert if there were errors in the batch
            if error_count > 0:
                self.alert_manager.alert_ingestion_partial(
                    self.db_name,
                    total=total_files,
                    failed=error_count,
                    details={"ingested": ingested_count, "skipped": skipped_count}
                )

            # Proactive monitoring: check JSON file sizes after each ingest cycle
            # Warns users before OOM crashes if files are too large
            self._check_json_file_sizes()

        except Exception as e:
            self.stats["errors"] += 1
            self.stats["last_error"] = str(e)
            logger.error(f"Ingestion batch failed: {e}")
            # Create critical alert for batch failure
            self.alert_manager.alert_watcher_error(
                self.db_name,
                f"Batch ingestion failed: {str(e)}",
                {"files_attempted": total_files}
            )
            # On critical failure, release core to free memory
            self._release_core()

    async def run(self):
        """Run the watcher daemon loop."""
        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        # Acquire exclusive lock on PID file (prevents duplicate daemons)
        if not self._acquire_lock():
            logger.error("Failed to start - another watcher instance is running")
            return

        self.running = True
        logger.info(f"Watcher started for: {self.db_name}")
        logger.info(f"Checking every {self.entry.watch_interval}s")

        # Do initial scan to establish baseline
        self.detector.scan_files()
        logger.info(f"Initial scan: {len(self.detector.known_files)} file(s)")

        try:
            while self.running:
                # Check for changes
                new_files, modified_files, deleted_files = self.detector.detect_changes()

                if new_files or modified_files:
                    logger.info(f"Changes detected: +{len(new_files)} ~{len(modified_files)} -{len(deleted_files)}")
                    await self._ingest_changes(new_files, modified_files)
                else:
                    logger.debug("No changes detected")

                # Sleep until next check
                await asyncio.sleep(self.entry.watch_interval)

        except Exception as e:
            logger.error(f"Watcher error: {e}")
            # Alert on unexpected watcher crash
            self.alert_manager.alert_watcher_stopped(
                self.db_name,
                f"Unexpected error: {str(e)}",
                {"error": str(e), "stats": self.stats}
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
                    self.stats
                )


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: hybridrag-watcher.py <database_name>")
        print("\nThe database must be registered in the HybridRAG registry.")
        sys.exit(1)

    db_name = sys.argv[1]

    try:
        daemon = WatcherDaemon(db_name)
        asyncio.run(daemon.run())
    except KeyboardInterrupt:
        print("\nShutdown requested")
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
