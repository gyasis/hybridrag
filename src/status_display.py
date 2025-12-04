#!/usr/bin/env python3
"""
Status Display Module
====================
Enhanced status display with progress bars and real-time updates.
"""

import time
import threading
from typing import Dict, Optional, Any
from dataclasses import dataclass
import os
import sys

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

@dataclass
class ProcessMetrics:
    """Metrics for a single process."""
    name: str
    status: str
    pid: Optional[int]
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    last_activity: float = 0.0
    error_count: int = 0
    custom_stats: Dict[str, Any] = None

class StatusDisplay:
    """Enhanced status display with progress tracking."""
    
    def __init__(self):
        """Initialize status display."""
        self.processes: Dict[str, ProcessMetrics] = {}
        self.progress_bars: Dict[str, Any] = {}
        self.last_update = time.time()
        self.display_thread = None
        self.running = False
        self.console_width = self._get_console_width()
        
    def _get_console_width(self) -> int:
        """Get console width for formatting."""
        try:
            return os.get_terminal_size().columns
        except:
            return 80
    
    def update_process_status(self, name: str, metrics: ProcessMetrics):
        """Update status for a process."""
        self.processes[name] = metrics
        self.last_update = time.time()
    
    def show_ingestion_progress(
        self, 
        total_files: int, 
        processed_files: int, 
        current_file: str,
        processing_rate: float,
        errors: int = 0
    ):
        """Show ingestion progress with progress bar."""
        if not TQDM_AVAILABLE:
            # Fallback to simple text display
            percent = (processed_files / max(total_files, 1)) * 100
            bar_length = 30
            filled_length = int(bar_length * processed_files / max(total_files, 1))
            bar = '█' * filled_length + '-' * (bar_length - filled_length)
            
            print(f"\r📊 Ingestion: [{bar}] {percent:.1f}% ({processed_files}/{total_files})", end='', flush=True)
            if current_file:
                print(f" | {os.path.basename(current_file)}", end='', flush=True)
            return
        
        # Use tqdm for better progress display
        progress_id = "ingestion"
        
        if progress_id not in self.progress_bars:
            self.progress_bars[progress_id] = tqdm(
                total=total_files,
                desc="📊 Ingesting",
                unit="files",
                bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
                dynamic_ncols=True,
                leave=False
            )
        
        pbar = self.progress_bars[progress_id]
        
        # Update progress bar
        if pbar.total != total_files:
            pbar.total = total_files
            pbar.refresh()
        
        pbar.n = processed_files
        
        # Update description with current file
        if current_file:
            filename = os.path.basename(current_file)
            if len(filename) > 30:
                filename = filename[:27] + "..."
            pbar.set_description(f"📊 Ingesting: {filename}")
        
        # Update rate
        if processing_rate > 0:
            pbar.set_postfix(rate=f"{processing_rate:.1f} files/min", errors=errors)
        
        pbar.refresh()
    
    def clear_progress_bars(self):
        """Clear all progress bars."""
        for pbar in self.progress_bars.values():
            if hasattr(pbar, 'close'):
                pbar.close()
        self.progress_bars.clear()
    
    def print_system_overview(self):
        """Print a system overview."""
        print("\n" + "="*self.console_width)
        print("🖥️  HybridRAG System Overview".center(self.console_width))
        print("="*self.console_width)
        
        if not self.processes:
            print("No process information available.".center(self.console_width))
            return
        
        # Process status table
        print(f"{'Process':<15} {'Status':<10} {'PID':<8} {'Activity':<20}")
        print("-" * 60)
        
        for name, metrics in self.processes.items():
            status_icon = {
                'running': '✅',
                'starting': '🔄',
                'error': '❌',
                'stopped': '⚪'
            }.get(metrics.status, '❓')
            
            last_activity = time.time() - metrics.last_activity if metrics.last_activity else 0
            activity_str = f"{last_activity:.0f}s ago" if last_activity < 300 else "inactive"
            
            print(f"{name:<15} {status_icon} {metrics.status:<9} {metrics.pid or 'N/A':<8} {activity_str:<20}")
            
            # Show custom stats if available
            if metrics.custom_stats:
                for key, value in metrics.custom_stats.items():
                    if key in ['files_found', 'processed_files', 'pending_files']:
                        print(f"  └─ {key}: {value}")
        
        print("-" * 60)
        print(f"Last updated: {time.strftime('%H:%M:%S', time.localtime(self.last_update))}")
    
    def print_compact_status(self):
        """Print a compact one-line status."""
        if not self.processes:
            return
        
        status_parts = []
        for name, metrics in self.processes.items():
            icon = {
                'running': '✅',
                'starting': '🔄', 
                'error': '❌',
                'stopped': '⚪'
            }.get(metrics.status, '❓')
            status_parts.append(f"{name}:{icon}")
        
        status_line = " | ".join(status_parts)
        timestamp = time.strftime('%H:%M:%S')
        
        # Clear line and print status
        print(f"\r[{timestamp}] {status_line}{'':20}", end='', flush=True)
    
    def start_background_display(self, update_interval: float = 30.0):
        """Start background status display thread."""
        def display_worker():
            last_overview = 0
            
            while self.running:
                current_time = time.time()
                
                # Show full overview every 30 seconds
                if current_time - last_overview > update_interval:
                    print()  # New line
                    self.print_system_overview()
                    last_overview = current_time
                else:
                    # Show compact status more frequently
                    self.print_compact_status()
                
                time.sleep(5)
        
        self.running = True
        self.display_thread = threading.Thread(target=display_worker, daemon=True)
        self.display_thread.start()
    
    def stop_background_display(self):
        """Stop background status display."""
        self.running = False
        if self.display_thread and self.display_thread.is_alive():
            self.display_thread.join(timeout=2)
        self.clear_progress_bars()
    
    def show_startup_banner(self):
        """Show startup banner."""
        banner = [
            "🚀 HybridRAG Multiprocess System",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "📁 Folder Watcher → 📊 Ingestion → 🧠 LightRAG",
            "",
            "Starting processes..."
        ]
        
        print("\n")
        for line in banner:
            print(line.center(self.console_width))
        print("\n")
    
    def show_ready_message(self):
        """Show system ready message."""
        print("\n" + "🎉 SYSTEM READY 🎉".center(self.console_width))
        print("Type your questions below:".center(self.console_width))
        print("-" * self.console_width)
    
    def format_search_result(self, result, query: str):
        """Format and display search result."""
        # Header
        print(f"\n{'='*self.console_width}")
        print(f"🔍 Query: {query}")
        print(f"📊 Mode: {result.mode} | Time: {result.execution_time:.2f}s | Confidence: {result.confidence_score:.1%}")
        print(f"{'='*self.console_width}")
        
        if result.error:
            print(f"❌ Error: {result.error}")
            return
        
        # Result content
        print(result.result)
        
        # Sources
        if result.sources:
            print(f"\n📚 Sources ({len(result.sources)}):")
            for i, source in enumerate(result.sources[:5], 1):
                print(f"  {i}. {source}")
        
        # Agentic steps
        if result.agentic_steps:
            print(f"\n🧠 Reasoning Steps: {len(result.agentic_steps)}")
            for i, step in enumerate(result.agentic_steps[:3], 1):
                step_preview = str(step)[:100] + "..." if len(str(step)) > 100 else str(step)
                print(f"  {i}. {step_preview}")
        
        print(f"{'='*self.console_width}")
    
    def show_error(self, message: str, error: Exception = None):
        """Show formatted error message."""
        print(f"\n❌ Error: {message}")
        if error:
            print(f"    Details: {str(error)}")
    
    def show_warning(self, message: str):
        """Show formatted warning message."""
        print(f"\n⚠️  Warning: {message}")
    
    def show_info(self, message: str):
        """Show formatted info message."""
        print(f"\nℹ️  {message}")
    
    def show_success(self, message: str):
        """Show formatted success message."""
        print(f"\n✅ {message}")

class ProgressReporter:
    """Helper class for reporting progress to the display."""
    
    def __init__(self, status_display: StatusDisplay):
        """Initialize progress reporter."""
        self.display = status_display
        self.start_time = time.time()
        self.last_report = 0
    
    def report_ingestion_progress(
        self,
        total_files: int,
        processed_files: int, 
        current_file: str = "",
        errors: int = 0
    ):
        """Report ingestion progress."""
        current_time = time.time()
        
        # Calculate processing rate
        elapsed_time = current_time - self.start_time
        processing_rate = (processed_files / max(elapsed_time / 60, 0.1)) if elapsed_time > 0 else 0
        
        # Show progress (throttle updates)
        if current_time - self.last_report > 1.0:  # Update every second
            self.display.show_ingestion_progress(
                total_files=total_files,
                processed_files=processed_files,
                current_file=current_file,
                processing_rate=processing_rate,
                errors=errors
            )
            self.last_report = current_time
    
    def finish_ingestion(self):
        """Mark ingestion as finished."""
        self.display.clear_progress_bars()
        elapsed = time.time() - self.start_time
        self.display.show_success(f"Ingestion completed in {elapsed:.1f} seconds")