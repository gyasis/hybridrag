#!/usr/bin/env python3
"""
Folder Watcher Module
====================
Monitors folders recursively for new/modified files and queues them for ingestion.
"""

import os
import time
import hashlib
import sqlite3
import logging
from pathlib import Path
from typing import List, Set, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor
import shutil

logger = logging.getLogger(__name__)

@dataclass
class FileInfo:
    """Information about a monitored file."""
    path: str
    size: int
    modified_time: float
    hash: str
    extension: str
    status: str = "pending"  # pending, queued, processing, processed, error
    error_msg: Optional[str] = None
    ingested_at: Optional[datetime] = None

class FileTracker:
    """Tracks processed files using SQLite database."""
    
    def __init__(self, db_path: str):
        """Initialize file tracker with database."""
        self.db_path = db_path
        self._init_database()
        
    def _init_database(self):
        """Initialize SQLite database for tracking files."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS processed_files (
                    file_path TEXT PRIMARY KEY,
                    file_hash TEXT NOT NULL,
                    file_size INTEGER,
                    modified_time REAL,
                    status TEXT,
                    error_msg TEXT,
                    ingested_at TIMESTAMP,
                    last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_status ON processed_files(status)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_hash ON processed_files(file_hash)
            """)
            conn.commit()
    
    def get_file_hash(self, file_path: str, chunk_size: int = 8192) -> str:
        """Calculate SHA256 hash of file content."""
        sha256_hash = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                while chunk := f.read(chunk_size):
                    sha256_hash.update(chunk)
            return sha256_hash.hexdigest()
        except Exception as e:
            logger.error(f"Error hashing file {file_path}: {e}")
            return ""
    
    def is_file_processed(self, file_path: str, file_hash: str) -> bool:
        """Check if file has already been processed."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT file_hash, status FROM processed_files WHERE file_path = ?",
                (file_path,)
            )
            row = cursor.fetchone()
            if row:
                stored_hash, status = row
                # File is considered processed if hash matches and status is processed
                return stored_hash == file_hash and status == "processed"
            return False
    
    def mark_file_processed(self, file_info: FileInfo):
        """Mark a file as processed."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO processed_files 
                (file_path, file_hash, file_size, modified_time, status, error_msg, ingested_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                file_info.path,
                file_info.hash,
                file_info.size,
                file_info.modified_time,
                file_info.status,
                file_info.error_msg,
                file_info.ingested_at
            ))
            conn.commit()
    
    def get_pending_files(self) -> List[str]:
        """Get list of files marked as pending or error."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT file_path FROM processed_files WHERE status IN ('pending', 'error')"
            )
            return [row[0] for row in cursor.fetchall()]
    
    def cleanup_missing_files(self):
        """Remove entries for files that no longer exist."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT file_path FROM processed_files")
            missing_files = [
                row[0] for row in cursor.fetchall() 
                if not os.path.exists(row[0])
            ]
            if missing_files:
                placeholders = ','.join('?' * len(missing_files))
                conn.execute(
                    f"DELETE FROM processed_files WHERE file_path IN ({placeholders})",
                    missing_files
                )
                conn.commit()
                logger.info(f"Cleaned up {len(missing_files)} missing file entries")

class FolderWatcher:
    """Watches folders recursively for changes and queues files for ingestion."""
    
    def __init__(self, config):
        """
        Initialize folder watcher.
        
        Args:
            config: HybridRAGConfig instance
        """
        self.config = config
        self.watch_folders = [Path(f).resolve() for f in config.ingestion.watch_folders]
        self.file_extensions = set(config.ingestion.file_extensions)
        self.recursive = config.ingestion.recursive
        self.queue_dir = Path(config.ingestion.ingestion_queue_dir)
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        
        self.tracker = FileTracker(config.ingestion.processed_files_db)
        self.executor = ThreadPoolExecutor(max_workers=4)
        self._stop_event = asyncio.Event()
        
        # File size limit in bytes
        self.max_file_size = config.ingestion.max_file_size_mb * 1024 * 1024
        
        logger.info(f"FolderWatcher initialized. Watching: {self.watch_folders}")
        logger.info(f"File extensions: {self.file_extensions}")
        
    def should_process_file(self, file_path: Path) -> bool:
        """Check if file should be processed."""
        # Check extension
        if self.file_extensions and file_path.suffix not in self.file_extensions:
            return False
            
        # Check file size
        try:
            from src.utils import format_file_size
            file_size = file_path.stat().st_size
            if file_size > self.max_file_size:
                logger.warning(f"File too large: {file_path} ({format_file_size(file_size)})")
                return False
        except Exception as e:
            logger.error(f"Error checking file {file_path}: {e}")
            return False
            
        # Check if it's a hidden file (but allow hidden directories if explicitly watched)
        # Only exclude files that are themselves hidden, not files in hidden directories
        if file_path.name.startswith('.') and file_path.name not in ['.', '..']:
            return False
                
        return True
    
    def scan_folders(self) -> List[FileInfo]:
        """Scan watched folders for files to process."""
        files_to_process = []
        
        for watch_folder in self.watch_folders:
            if not watch_folder.exists():
                logger.warning(f"Watch folder does not exist: {watch_folder}")
                continue
                
            # Get all files recursively or just in the folder
            if self.recursive:
                pattern = "**/*"
            else:
                pattern = "*"
                
            for file_path in watch_folder.glob(pattern):
                if not file_path.is_file():
                    continue
                    
                if not self.should_process_file(file_path):
                    continue
                
                try:
                    stat = file_path.stat()
                    file_hash = self.tracker.get_file_hash(str(file_path))
                    
                    # Skip if already processed with same hash
                    if self.tracker.is_file_processed(str(file_path), file_hash):
                        continue
                    
                    file_info = FileInfo(
                        path=str(file_path),
                        size=stat.st_size,
                        modified_time=stat.st_mtime,
                        hash=file_hash,
                        extension=file_path.suffix
                    )
                    files_to_process.append(file_info)
                    
                except Exception as e:
                    logger.error(f"Error processing file {file_path}: {e}")
                    
        return files_to_process
    
    def queue_file(self, file_info: FileInfo) -> bool:
        """Queue a file for ingestion."""
        try:
            # Create queue entry
            queue_id = f"{int(time.time())}_{hashlib.md5(file_info.path.encode()).hexdigest()[:8]}"
            queue_file = self.queue_dir / f"{queue_id}.json"
            
            # Copy file to queue directory
            source_path = Path(file_info.path)
            if source_path.exists():
                dest_path = self.queue_dir / f"{queue_id}{file_info.extension}"
                shutil.copy2(source_path, dest_path)
                
                # Save metadata
                metadata = {
                    "original_path": file_info.path,
                    "queued_file": str(dest_path),
                    "size": file_info.size,
                    "hash": file_info.hash,
                    "extension": file_info.extension,
                    "queued_at": datetime.now().isoformat()
                }
                
                with open(queue_file, 'w') as f:
                    json.dump(metadata, f, indent=2)
                
                # Update status
                file_info.status = "queued"
                self.tracker.mark_file_processed(file_info)
                
                logger.info(f"Queued file for ingestion: {file_info.path}")
                return True
                
        except Exception as e:
            logger.error(f"Error queuing file {file_info.path}: {e}")
            file_info.status = "error"
            file_info.error_msg = str(e)
            self.tracker.mark_file_processed(file_info)
            
        return False
    
    async def watch_loop(self):
        """Main watch loop that monitors folders."""
        logger.info("Starting folder watch loop")
        
        while not self._stop_event.is_set():
            try:
                # Scan folders for new/modified files
                files_to_process = await asyncio.get_event_loop().run_in_executor(
                    self.executor, self.scan_folders
                )
                
                # Queue files for ingestion
                if files_to_process:
                    logger.info(f"Found {len(files_to_process)} files to process")
                    
                    for file_info in files_to_process[:self.config.ingestion.batch_size]:
                        await asyncio.get_event_loop().run_in_executor(
                            self.executor, self.queue_file, file_info
                        )
                
                # Cleanup missing files periodically
                await asyncio.get_event_loop().run_in_executor(
                    self.executor, self.tracker.cleanup_missing_files
                )
                
            except Exception as e:
                logger.error(f"Error in watch loop: {e}")
            
            # Wait before next scan
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.config.ingestion.poll_interval
                )
            except asyncio.TimeoutError:
                pass
    
    async def start(self):
        """Start watching folders."""
        logger.info("Starting FolderWatcher")
        self._stop_event.clear()
        await self.watch_loop()
    
    async def stop(self):
        """Stop watching folders."""
        logger.info("Stopping FolderWatcher")
        self._stop_event.set()
        self.executor.shutdown(wait=True)
    
    def get_queue_stats(self) -> Dict:
        """Get statistics about the ingestion queue."""
        queue_files = list(self.queue_dir.glob("*.json"))
        
        with sqlite3.connect(self.tracker.db_path) as conn:
            cursor = conn.execute(
                "SELECT status, COUNT(*) FROM processed_files GROUP BY status"
            )
            status_counts = dict(cursor.fetchall())
        
        return {
            "queued_files": len(queue_files),
            "status_counts": status_counts,
            "watch_folders": [str(f) for f in self.watch_folders],
            "queue_directory": str(self.queue_dir)
        }