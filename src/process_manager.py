#!/usr/bin/env python3
"""
Process Manager
===============
Manages multiple processes for folder watching, ingestion, and querying.
"""

import multiprocessing as mp
import queue
import time
import signal
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from pathlib import Path
import json
import os

logger = logging.getLogger(__name__)

@dataclass
class ProcessStatus:
    """Status information for a process."""
    name: str
    pid: Optional[int]
    status: str  # starting, running, stopping, stopped, error
    last_update: float
    stats: Dict[str, Any]
    error: Optional[str] = None

@dataclass
class IngestionProgress:
    """Progress information for ingestion."""
    total_files: int
    processed_files: int
    current_file: str
    errors: int
    processing_rate: float  # files per minute
    estimated_remaining: float  # minutes

class ProcessManager:
    """Manages all HybridRAG processes and communication."""
    
    def __init__(self):
        """Initialize process manager."""
        self.processes: Dict[str, mp.Process] = {}
        self.process_status: Dict[str, ProcessStatus] = {}
        
        # Communication queues
        self.watcher_to_ingestion = mp.Queue()  # File notifications
        self.ingestion_to_main = mp.Queue()     # Progress updates
        self.main_to_processes = mp.Queue()     # Commands
        self.status_queue = mp.Queue()          # Status updates
        
        # Shared state
        self.manager = mp.Manager()
        self.shared_state = self.manager.dict({
            'watch_folders': [],
            'total_files_found': 0,
            'total_files_processed': 0,
            'ingestion_active': False,
            'lightrag_ready': False
        })
        
        # Process control
        self.shutdown_event = mp.Event()
        self.running = False
        
        logger.info("ProcessManager initialized")
    
    def start_watcher_process(self, watch_folders: List[str], recursive: bool = True):
        """Start the folder watcher process."""
        try:
            self.shared_state['watch_folders'] = watch_folders
            
            watcher_process = mp.Process(
                target=self._watcher_worker,
                args=(
                    watch_folders,
                    recursive,
                    self.watcher_to_ingestion,
                    self.status_queue,
                    self.shutdown_event,
                    self.shared_state
                ),
                name="FolderWatcher"
            )
            
            watcher_process.start()
            self.processes['watcher'] = watcher_process
            
            self.process_status['watcher'] = ProcessStatus(
                name="FolderWatcher",
                pid=watcher_process.pid,
                status="starting",
                last_update=time.time(),
                stats={}
            )
            
            logger.info(f"Started watcher process (PID: {watcher_process.pid})")
            
        except Exception as e:
            logger.error(f"Failed to start watcher process: {e}")
            raise
    
    def start_ingestion_process(self, config):
        """Start the ingestion worker process."""
        try:
            ingestion_process = mp.Process(
                target=self._ingestion_worker,
                args=(
                    config,
                    self.watcher_to_ingestion,
                    self.ingestion_to_main,
                    self.status_queue,
                    self.shutdown_event,
                    self.shared_state
                ),
                name="IngestionWorker"
            )
            
            ingestion_process.start()
            self.processes['ingestion'] = ingestion_process
            
            self.process_status['ingestion'] = ProcessStatus(
                name="IngestionWorker",
                pid=ingestion_process.pid,
                status="starting",
                last_update=time.time(),
                stats={}
            )
            
            logger.info(f"Started ingestion process (PID: {ingestion_process.pid})")
            
        except Exception as e:
            logger.error(f"Failed to start ingestion process: {e}")
            raise
    
    def update_status(self):
        """Update process status from status queue."""
        try:
            while not self.status_queue.empty():
                try:
                    status_update = self.status_queue.get_nowait()
                    process_name = status_update.get('process')
                    
                    if process_name in self.process_status:
                        self.process_status[process_name].status = status_update.get('status', 'unknown')
                        self.process_status[process_name].last_update = time.time()
                        self.process_status[process_name].stats = status_update.get('stats', {})
                        if 'error' in status_update:
                            self.process_status[process_name].error = status_update['error']
                            
                except queue.Empty:
                    break
                    
        except Exception as e:
            logger.error(f"Error updating status: {e}")
    
    def get_ingestion_progress(self) -> Optional[IngestionProgress]:
        """Get current ingestion progress."""
        try:
            while not self.ingestion_to_main.empty():
                try:
                    progress_data = self.ingestion_to_main.get_nowait()
                    if progress_data.get('type') == 'progress':
                        return IngestionProgress(
                            total_files=progress_data.get('total_files', 0),
                            processed_files=progress_data.get('processed_files', 0),
                            current_file=progress_data.get('current_file', ''),
                            errors=progress_data.get('errors', 0),
                            processing_rate=progress_data.get('processing_rate', 0.0),
                            estimated_remaining=progress_data.get('estimated_remaining', 0.0)
                        )
                except queue.Empty:
                    break
        except Exception as e:
            logger.error(f"Error getting ingestion progress: {e}")
        
        return None
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status."""
        self.update_status()
        
        # Check if processes are alive
        for name, process in self.processes.items():
            if name in self.process_status:
                if process.is_alive():
                    # Update PID if needed
                    if self.process_status[name].pid != process.pid:
                        self.process_status[name].pid = process.pid
                else:
                    self.process_status[name].status = "stopped"
        
        return {
            'processes': {
                name: {
                    'status': status.status,
                    'pid': status.pid,
                    'last_update': status.last_update,
                    'stats': status.stats,
                    'error': status.error
                }
                for name, status in self.process_status.items()
            },
            'shared_state': dict(self.shared_state),
            'queue_sizes': {
                'watcher_to_ingestion': self.watcher_to_ingestion.qsize(),
                'ingestion_to_main': self.ingestion_to_main.qsize(),
                'status_queue': self.status_queue.qsize()
            }
        }
    
    def shutdown(self):
        """Shutdown all processes gracefully."""
        logger.info("Shutting down all processes...")
        
        # Signal shutdown
        self.shutdown_event.set()
        self.running = False
        
        # Wait for processes to finish
        for name, process in self.processes.items():
            if process.is_alive():
                logger.info(f"Waiting for {name} to shutdown...")
                process.join(timeout=10)
                
                if process.is_alive():
                    logger.warning(f"Force terminating {name}")
                    process.terminate()
                    process.join(timeout=5)
                    
                    if process.is_alive():
                        logger.error(f"Force killing {name}")
                        process.kill()
        
        logger.info("All processes shutdown complete")
    
    @staticmethod
    def _watcher_worker(
        watch_folders: List[str],
        recursive: bool,
        file_queue: mp.Queue,
        status_queue: mp.Queue,
        shutdown_event: mp.Event,
        shared_state: Dict
    ):
        """Folder watcher worker process."""
        import time
        import hashlib
        from pathlib import Path
        
        # Setup process logging
        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger("FolderWatcher")
        
        logger.info(f"Folder watcher started, watching: {watch_folders}")
        
        # Send initial status
        status_queue.put({
            'process': 'watcher',
            'status': 'running',
            'stats': {'watch_folders': watch_folders, 'recursive': recursive}
        })
        
        # Track processed files
        processed_files = set()
        scan_interval = 5.0  # seconds
        
        try:
            while not shutdown_event.is_set():
                files_found = 0
                new_files = 0
                
                for folder_path in watch_folders:
                    folder = Path(folder_path)
                    if not folder.exists():
                        logger.warning(f"Watch folder does not exist: {folder}")
                        continue
                    
                    # Scan for files
                    if recursive:
                        pattern = "**/*"
                    else:
                        pattern = "*"
                    
                    for file_path in folder.glob(pattern):
                        if not file_path.is_file():
                            continue
                        
                        # Check file extension
                        if file_path.suffix not in ['.txt', '.md', '.pdf', '.json', '.yaml', '.yml', '.py', '.js', '.html', '.csv']:
                            continue
                        
                        files_found += 1
                        
                        # Calculate file hash
                        try:
                            file_hash = hashlib.sha256()
                            with open(file_path, 'rb') as f:
                                for chunk in iter(lambda: f.read(4096), b""):
                                    file_hash.update(chunk)
                            hash_value = file_hash.hexdigest()
                            
                            file_id = f"{file_path}:{hash_value}"
                            
                            if file_id not in processed_files:
                                # New or modified file
                                file_info = {
                                    'path': str(file_path),
                                    'hash': hash_value,
                                    'size': file_path.stat().st_size,
                                    'modified': file_path.stat().st_mtime,
                                    'extension': file_path.suffix
                                }
                                
                                file_queue.put(file_info)
                                processed_files.add(file_id)
                                new_files += 1
                                
                                logger.info(f"Queued new file: {file_path}")
                                
                        except Exception as e:
                            logger.error(f"Error processing file {file_path}: {e}")
                
                # Update shared state
                shared_state['total_files_found'] = len(processed_files)
                
                # Send status update
                status_queue.put({
                    'process': 'watcher',
                    'status': 'running',
                    'stats': {
                        'files_found': files_found,
                        'new_files': new_files,
                        'total_tracked': len(processed_files),
                        'last_scan': time.time()
                    }
                })
                
                # Wait before next scan
                shutdown_event.wait(timeout=scan_interval)
                
        except Exception as e:
            logger.error(f"Watcher process error: {e}")
            status_queue.put({
                'process': 'watcher',
                'status': 'error',
                'error': str(e)
            })
        
        logger.info("Folder watcher process shutdown")
    
    @staticmethod
    def _ingestion_worker(
        config,
        file_queue: mp.Queue,
        progress_queue: mp.Queue,
        status_queue: mp.Queue,
        shutdown_event: mp.Event,
        shared_state: Dict
    ):
        """Ingestion worker process."""
        import asyncio
        import sys
        import os
        from tqdm import tqdm
        
        # Add src to path
        sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
        
        # Setup process logging
        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger("IngestionWorker")
        
        logger.info("Ingestion worker started")
        
        try:
            # Initialize LightRAG in this process
            from lightrag_core import create_lightrag_core
            from ingestion_pipeline import DocumentProcessor
            
            lightrag_core = create_lightrag_core(config)
            processor = DocumentProcessor(config)
            
            # Send initial status
            status_queue.put({
                'process': 'ingestion',
                'status': 'running',
                'stats': {}
            })
            
            # Track processing stats
            processed_count = 0
            error_count = 0
            start_time = time.time()
            
            # Progress tracking
            pending_files = []
            processing_start = None
            
            while not shutdown_event.is_set():
                # Collect files from queue
                new_files = []
                try:
                    while not file_queue.empty():
                        file_info = file_queue.get_nowait()
                        new_files.append(file_info)
                        pending_files.append(file_info)
                except:
                    pass
                
                if new_files:
                    logger.info(f"Received {len(new_files)} new files for processing")
                
                # Process files if we have any
                if pending_files:
                    if not processing_start:
                        processing_start = time.time()
                    
                    shared_state['ingestion_active'] = True
                    
                    # Process in batches
                    batch_size = min(5, len(pending_files))
                    current_batch = pending_files[:batch_size]
                    pending_files = pending_files[batch_size:]
                    
                    # Create progress bar info
                    total_files = processed_count + error_count + len(pending_files) + len(current_batch)
                    
                    for i, file_info in enumerate(current_batch):
                        if shutdown_event.is_set():
                            break
                        
                        try:
                            # Send progress update
                            elapsed_time = time.time() - processing_start
                            processing_rate = (processed_count + i) / max(elapsed_time / 60, 0.1)  # files per minute
                            remaining_files = len(pending_files) + len(current_batch) - i - 1
                            estimated_remaining = remaining_files / max(processing_rate, 0.1) if processing_rate > 0 else 0
                            
                            progress_queue.put({
                                'type': 'progress',
                                'total_files': total_files,
                                'processed_files': processed_count + i,
                                'current_file': os.path.basename(file_info['path']),
                                'errors': error_count,
                                'processing_rate': processing_rate,
                                'estimated_remaining': estimated_remaining
                            })
                            
                            # Process the file
                            logger.info(f"Processing: {file_info['path']}")
                            
                            # Read and process content
                            content = processor.read_file(file_info['path'], file_info['extension'])
                            
                            if content:
                                # Create document with metadata
                                doc_content = f"# Document: {file_info['path']}\n"
                                doc_content += f"# Type: {file_info['extension']}\n"
                                doc_content += f"# Size: {file_info['size']} bytes\n\n"
                                doc_content += content
                                
                                # Ingest into LightRAG
                                asyncio.run(lightrag_core.ainsert(doc_content))
                                
                                processed_count += 1
                                logger.info(f"Successfully processed: {file_info['path']}")
                                
                            else:
                                logger.warning(f"Empty content from: {file_info['path']}")
                                error_count += 1
                                
                        except Exception as e:
                            logger.error(f"Error processing {file_info['path']}: {e}")
                            error_count += 1
                    
                    # Update shared state
                    shared_state['total_files_processed'] = processed_count
                    
                    # Send final progress for this batch
                    progress_queue.put({
                        'type': 'progress',
                        'total_files': total_files,
                        'processed_files': processed_count,
                        'current_file': '',
                        'errors': error_count,
                        'processing_rate': processing_rate,
                        'estimated_remaining': len(pending_files) / max(processing_rate, 0.1) if processing_rate > 0 else 0
                    })
                
                if not pending_files:
                    shared_state['ingestion_active'] = False
                    processing_start = None
                
                # Send status update
                status_queue.put({
                    'process': 'ingestion',
                    'status': 'running',
                    'stats': {
                        'processed_files': processed_count,
                        'error_files': error_count,
                        'pending_files': len(pending_files),
                        'processing_active': len(pending_files) > 0
                    }
                })
                
                # Wait a bit before checking for more files
                shutdown_event.wait(timeout=2.0)
            
            # Mark LightRAG as ready
            shared_state['lightrag_ready'] = True
            
        except Exception as e:
            logger.error(f"Ingestion worker error: {e}")
            status_queue.put({
                'process': 'ingestion',
                'status': 'error',
                'error': str(e)
            })
        
        logger.info("Ingestion worker process shutdown")

def setup_signal_handlers(process_manager: ProcessManager):
    """Setup signal handlers for graceful shutdown."""
    def signal_handler(signum, frame):
        print(f"\n🛑 Received signal {signum}, shutting down...")
        process_manager.shutdown()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)