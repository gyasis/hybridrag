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
import os
import sys
import signal
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Set, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database_registry import (
    get_registry, DatabaseEntry,
    get_watcher_pid_file, get_watcher_lock_file
)

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
        extensions: Optional[list] = None
    ):
        """
        Initialize the change detector.

        Args:
            folder: Root folder to watch
            recursive: Watch subdirectories
            extensions: Optional list of file extensions to track
        """
        self.folder = Path(folder)
        self.recursive = recursive
        self.extensions = set(extensions) if extensions else None
        self.last_check: Optional[float] = None
        self.known_files: Set[Path] = set()
        self.file_mtimes: dict = {}

    def should_include(self, path: Path) -> bool:
        """Check if a file should be included based on extension filter."""
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
    """

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
        self.lock_file: Optional[Path] = None

        # Load database entry
        self._load_entry()

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
        self.lock_file = get_watcher_lock_file(self.db_name)

        # Initialize change detector
        self.detector = FileChangeDetector(
            folder=self.entry.source_folder,
            recursive=self.entry.recursive,
            extensions=self.entry.file_extensions
        )

        logger.info(f"Loaded database entry: {self.db_name}")
        logger.info(f"  Source: {self.entry.source_folder}")
        logger.info(f"  Interval: {self.entry.watch_interval}s")
        logger.info(f"  Recursive: {self.entry.recursive}")

    def _write_pid(self):
        """Write PID file."""
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        self.pid_file.write_text(str(os.getpid()))
        logger.info(f"PID file: {self.pid_file}")

    def _cleanup_pid(self):
        """Remove PID file."""
        if self.pid_file and self.pid_file.exists():
            self.pid_file.unlink()
        if self.lock_file and self.lock_file.exists():
            self.lock_file.unlink()

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False

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

        logger.info(f"Ingesting {len(all_changed)} changed file(s)")

        # Import here to avoid circular imports
        from config.config import HybridRAGConfig
        from src.lightrag_core import HybridLightRAGCore

        try:
            # Initialize config
            config = HybridRAGConfig()
            config.lightrag.working_dir = self.entry.path

            if self.entry.model:
                config.lightrag.model_name = self.entry.model

            # Initialize core
            core = HybridLightRAGCore(config)
            await core._ensure_initialized()

            # Ingest each changed file
            for file_path in all_changed:
                try:
                    content = file_path.read_text(encoding='utf-8', errors='ignore')
                    if content.strip():
                        await core.insert(content)
                        logger.info(f"  Ingested: {file_path.name}")
                except Exception as e:
                    logger.error(f"  Failed to ingest {file_path.name}: {e}")

            # Update last_sync in registry
            self.registry.update_last_sync(self.db_name)
            logger.info("Ingestion complete")

        except Exception as e:
            logger.error(f"Ingestion failed: {e}")

    async def run(self):
        """Run the watcher daemon loop."""
        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        # Write PID file
        self._write_pid()

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
        finally:
            self._cleanup_pid()
            logger.info("Watcher stopped")


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
