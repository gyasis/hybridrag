#!/usr/bin/env python3
"""
Batch Ingestion Controller
===========================
Solves the "large initial ingestion" pain point by:
1. Quick discovery phase (finds all files in minutes)
2. Slow feeding phase (processes in batches with resource monitoring)
3. Uses existing watcher duplicate detection (no overlap!)

Works with ALL backends (JSON, PostgreSQL, MongoDB) - just feeds files to existing code.
"""

import os
import sys
import time
import asyncio
import logging
import argparse
import psutil
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database_registry import DatabaseRegistry


@dataclass
class BatchConfig:
    """Configuration for batch processing."""
    batch_size: int = 10  # Files per batch
    sleep_between_batches: float = 2.0  # Seconds
    max_cpu_percent: float = 80.0  # Pause if CPU above this
    max_memory_percent: float = 85.0  # Pause if memory above this
    check_interval: float = 5.0  # Seconds between resource checks


class ResourceMonitor:
    """Monitor system resources and throttle when busy."""

    def __init__(self, config: BatchConfig):
        self.config = config

    def is_system_busy(self) -> tuple[bool, str]:
        """
        Check if system is too busy for ingestion.

        Returns:
            (is_busy, reason)
        """
        cpu_percent = psutil.cpu_percent(interval=1)
        memory_percent = psutil.virtual_memory().percent

        if cpu_percent > self.config.max_cpu_percent:
            return True, f"CPU: {cpu_percent:.1f}% > {self.config.max_cpu_percent}%"

        if memory_percent > self.config.max_memory_percent:
            return True, f"Memory: {memory_percent:.1f}% > {self.config.max_memory_percent}%"

        return False, ""

    async def wait_until_system_ready(self, logger: logging.Logger):
        """Wait until system resources are available."""
        while True:
            is_busy, reason = self.is_system_busy()
            if not is_busy:
                return

            logger.info(f"⏸️  System busy ({reason}), pausing ingestion...")
            await asyncio.sleep(30)  # Check again in 30 seconds


class BatchIngestionController:
    """
    Controls batch ingestion of files without blocking the system.

    Uses existing watcher logic for actual ingestion (duplicate detection, etc.).
    """

    def __init__(
        self,
        db_name: str,
        pending_file: Path,
        config: BatchConfig = None,
        logger: logging.Logger = None
    ):
        self.db_name = db_name
        self.pending_file = pending_file
        self.config = config or BatchConfig()
        self.logger = logger or logging.getLogger(__name__)
        self.resource_monitor = ResourceMonitor(self.config)
        self.registry = DatabaseRegistry()

        # Load database entry
        self.entry = self.registry.get(db_name)
        if not self.entry:
            raise ValueError(f"Database '{db_name}' not found in registry")

    def discover_files(self, source_path: Path) -> int:
        """
        Discovery phase: Find all .specstory/*.md files quickly.

        Writes to pending_file for later processing.

        Returns:
            Number of files discovered
        """
        self.logger.info(f"🔍 Discovery phase: Scanning {source_path}")
        discovered = []

        # Find all .specstory/history/*.md files recursively
        for specstory_dir in source_path.rglob(".specstory"):
            history_dir = specstory_dir / "history"
            if not history_dir.exists():
                continue

            # Find all .md files
            for md_file in history_dir.rglob("*.md"):
                if md_file.is_file():
                    discovered.append(str(md_file.resolve()))

        # Write to pending file
        self.pending_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.pending_file, 'w') as f:
            f.write('\n'.join(discovered))

        self.logger.info(f"✅ Discovery complete: {len(discovered)} files found")
        self.logger.info(f"📝 Saved to: {self.pending_file}")

        return len(discovered)

    def load_pending_files(self) -> List[str]:
        """Load list of pending files."""
        if not self.pending_file.exists():
            return []

        with open(self.pending_file, 'r') as f:
            return [line.strip() for line in f if line.strip()]

    def save_pending_files(self, files: List[str]):
        """Save remaining pending files."""
        with open(self.pending_file, 'w') as f:
            f.write('\n'.join(files))

    async def process_batch(self, batch: List[str]) -> tuple[int, int, int]:
        """
        Process a batch of files using existing watcher logic.

        Returns:
            (ingested, skipped, errors)
        """
        import hashlib
        import importlib.util

        # Load watcher module dynamically (filename has hyphen)
        watcher_path = Path(__file__).parent / "hybridrag-watcher.py"
        spec = importlib.util.spec_from_file_location("hybridrag_watcher", watcher_path)
        watcher_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(watcher_module)

        IngestionWatcher = watcher_module.IngestionWatcher

        # Create temporary watcher instance (reuses existing logic)
        watcher = IngestionWatcher(self.db_name)

        # Load existing hashes (for duplicate detection)
        watcher._load_ingested_hashes()

        # Get or create core
        core = await watcher._get_core()

        ingested = 0
        skipped = 0
        errors = 0

        for file_path_str in batch:
            try:
                file_path = Path(file_path_str)
                if not file_path.exists():
                    self.logger.warning(f"  File not found: {file_path.name}")
                    errors += 1
                    continue

                # Read content
                content = file_path.read_text(encoding='utf-8', errors='ignore')
                if not content.strip():
                    self.logger.debug(f"  Skipped empty: {file_path.name}")
                    skipped += 1
                    continue

                # Check for duplicate (uses existing watcher logic!)
                if watcher._is_duplicate(content):
                    self.logger.debug(f"  Skipped duplicate: {file_path.name}")
                    skipped += 1
                    continue

                # Ingest using existing core
                success = await core.ainsert(content, str(file_path))
                if success:
                    watcher.ingested_hashes.add(watcher._content_hash(content))
                    ingested += 1
                    self.logger.info(f"  ✓ Ingested: {file_path.name}")
                else:
                    errors += 1
                    self.logger.error(f"  ✗ Failed: {file_path.name}")

            except Exception as e:
                errors += 1
                self.logger.error(f"  ✗ Error processing {file_path_str}: {e}")

        return ingested, skipped, errors

    async def run(self, resume: bool = True):
        """
        Run the batch ingestion controller.

        Args:
            resume: If True, continue from where we left off
        """
        # Load pending files
        pending = self.load_pending_files()
        if not pending:
            self.logger.info("✅ No pending files - bulk ingestion already complete!")
            self.logger.info("\n💡 For ongoing file monitoring, start the watcher:")
            self.logger.info(f"   python hybridrag.py db watch start {self.db_name}")
            self.logger.info("\n   The watcher handles:")
            self.logger.info("   • New files as they're created")
            self.logger.info("   • File modifications (content changes)")
            self.logger.info("   • 1-2 files at a time (lightweight)")
            return

        total_files = len(pending)
        self.logger.info(f"📦 Batch ingestion starting: {total_files} files pending")
        self.logger.info(f"   Batch size: {self.config.batch_size}")
        self.logger.info(f"   Resource limits: CPU {self.config.max_cpu_percent}%, Memory {self.config.max_memory_percent}%")

        total_ingested = 0
        total_skipped = 0
        total_errors = 0
        batch_num = 0

        while pending:
            batch_num += 1

            # Wait if system is busy
            await self.resource_monitor.wait_until_system_ready(self.logger)

            # Take next batch
            batch = pending[:self.config.batch_size]
            remaining = pending[self.config.batch_size:]

            # Process batch
            self.logger.info(f"\n🔄 Batch {batch_num}: Processing {len(batch)} files ({len(remaining)} remaining)")
            ingested, skipped, errors = await self.process_batch(batch)

            # Update stats
            total_ingested += ingested
            total_skipped += skipped
            total_errors += errors

            # Save progress (for pause/resume)
            self.save_pending_files(remaining)

            # Log progress
            progress_pct = ((total_files - len(remaining)) / total_files) * 100
            self.logger.info(f"   Batch complete: +{ingested} ingested, ~{skipped} skipped, x{errors} errors")
            self.logger.info(f"   Overall progress: {progress_pct:.1f}% ({total_files - len(remaining)}/{total_files})")

            # Update pending list
            pending = remaining

            # Sleep between batches (unless we're done)
            if pending:
                self.logger.debug(f"   Sleeping {self.config.sleep_between_batches}s before next batch...")
                await asyncio.sleep(self.config.sleep_between_batches)

        # Final summary
        self.logger.info("\n" + "="*60)
        self.logger.info("🎉 BATCH INGESTION COMPLETE!")
        self.logger.info(f"   Total ingested: {total_ingested}")
        self.logger.info(f"   Duplicates skipped: {total_skipped}")
        self.logger.info(f"   Errors: {total_errors}")
        self.logger.info("="*60)

        # Clean up pending file
        if self.pending_file.exists():
            self.pending_file.unlink()
            self.logger.info("✓ Cleaned up pending file")

        # Check if watcher should be started for ongoing monitoring
        self.logger.info("\n📌 NEXT STEPS:")
        self.logger.info("   Bulk ingestion is complete. For ongoing monitoring:")
        self.logger.info(f"   python hybridrag.py db watch start {self.db_name}")
        self.logger.info("")
        self.logger.info("   The watcher will:")
        self.logger.info("   • Monitor for new files (every 24 hours)")
        self.logger.info("   • Detect file modifications")
        self.logger.info("   • Use same duplicate detection")
        self.logger.info("   • Process 1-2 files at a time (not thousands!)")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Batch Ingestion Controller - Process large ingestion jobs without blocking the system"
    )
    parser.add_argument("db_name", help="Database name from registry")
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Run discovery phase only (find files, don't ingest)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Files per batch (default: 10)"
    )
    parser.add_argument(
        "--max-cpu",
        type=float,
        default=80.0,
        help="Max CPU percent before pausing (default: 80)"
    )
    parser.add_argument(
        "--max-memory",
        type=float,
        default=85.0,
        help="Max memory percent before pausing (default: 85)"
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

    # Load database entry
    registry = DatabaseRegistry()
    entry = registry.get(args.db_name)
    if not entry:
        logger.error(f"Database '{args.db_name}' not found in registry")
        sys.exit(1)

    # Setup paths
    pending_file = Path.home() / ".hybridrag" / "batch_ingestion" / f"{args.db_name}.pending.txt"

    # Create config
    config = BatchConfig(
        batch_size=args.batch_size,
        max_cpu_percent=args.max_cpu,
        max_memory_percent=args.max_memory
    )

    # Create controller
    controller = BatchIngestionController(
        db_name=args.db_name,
        pending_file=pending_file,
        config=config,
        logger=logger
    )

    # Run discovery or full ingestion
    if args.discover:
        # Discovery only
        source_path = Path(entry.source_folder)
        count = controller.discover_files(source_path)
        logger.info(f"\n✅ Discovery complete! Run without --discover to start ingestion:")
        logger.info(f"   python scripts/batch-ingestion-controller.py {args.db_name}")
    else:
        # Check if discovery was done
        if not pending_file.exists():
            logger.info("Running discovery first...")
            source_path = Path(entry.source_folder)
            controller.discover_files(source_path)

        # Run batch ingestion
        await controller.run()


if __name__ == "__main__":
    asyncio.run(main())
