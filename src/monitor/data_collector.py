"""
Data Collector for HybridRAG Monitor
====================================

Collects and aggregates data from various sources:
- Database registry (configurations)
- Database files (sizes, entity counts)
- PID files (watcher status)
- Log files (recent activity)
"""

import json
import psutil
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import re

# Import from parent package
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.database_registry import (
    DatabaseRegistry, DatabaseEntry,
    get_registry, is_watcher_running
)
from src.watch_manager import WatchManager


@dataclass
class DatabaseStats:
    """Statistics for a single database."""
    name: str
    path: str
    source_folder: Optional[str]
    source_type: str

    # Status
    exists: bool = True
    healthy: bool = True

    # Size metrics
    total_size_bytes: int = 0
    total_size_human: str = "0 B"

    # Entity counts (from database_metadata.json)
    entity_count: int = 0
    relation_count: int = 0
    chunk_count: int = 0
    document_count: int = 0

    # Processing info (from doc_status.json and logs)
    processing_files: List[str] = field(default_factory=list)  # Files currently being processed
    recent_files: List[Dict[str, Any]] = field(default_factory=list)  # Last 5 processed files
    file_warnings: List[str] = field(default_factory=list)  # Size warnings for large files
    processing_progress: Dict[str, Any] = field(default_factory=dict)  # {current_chunk, total_chunks, current_file}

    # Sync info
    last_sync: Optional[datetime] = None
    last_sync_human: str = "Never"

    # Watcher info
    watcher_running: bool = False
    watcher_pid: Optional[int] = None
    watcher_mode: Optional[str] = None
    auto_watch: bool = False
    watch_interval: int = 300

    # Configuration
    model: Optional[str] = None
    recursive: bool = True
    description: Optional[str] = None

    # Errors
    errors: List[str] = field(default_factory=list)


@dataclass
class LogEntry:
    """A single log entry."""
    timestamp: datetime
    level: str
    database: str
    message: str
    raw: str


@dataclass
class MonitorSnapshot:
    """Complete snapshot of monitor state."""
    timestamp: datetime
    databases: List[DatabaseStats]
    watchers_running: int
    watchers_total: int
    total_entities: int
    total_relations: int
    total_size_bytes: int
    total_size_human: str
    recent_logs: List[LogEntry]
    errors: List[str]


def humanize_bytes(size_bytes: int) -> str:
    """Convert bytes to human readable format."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def humanize_timedelta(dt: Optional[datetime]) -> str:
    """Convert datetime to human-readable relative time."""
    if not dt:
        return "Never"

    now = datetime.now()
    if dt.tzinfo:
        dt = dt.replace(tzinfo=None)

    delta = now - dt

    if delta < timedelta(seconds=60):
        return "Just now"
    elif delta < timedelta(hours=1):
        mins = int(delta.total_seconds() / 60)
        return f"{mins}m ago"
    elif delta < timedelta(days=1):
        hours = int(delta.total_seconds() / 3600)
        return f"{hours}h ago"
    elif delta < timedelta(days=30):
        days = delta.days
        return f"{days}d ago"
    else:
        return dt.strftime("%Y-%m-%d")


def get_directory_size(path: Path) -> int:
    """Get total size of a directory recursively."""
    total = 0
    try:
        for entry in path.rglob('*'):
            if entry.is_file():
                try:
                    total += entry.stat().st_size
                except (OSError, PermissionError):
                    pass
    except (OSError, PermissionError):
        pass
    return total


def parse_database_metadata(db_path: Path) -> Dict[str, int]:
    """Parse database metadata for entity/relation counts.

    Gets ACCURATE counts directly from GraphML file using fast grep.
    Previous method used stale log entries which caused TUI to show outdated stats.

    Methods:
    1. Use subprocess grep to count <node> and <edge> tags in GraphML (fast even for 200MB+ files)
    2. Fall back to Python read for small files if grep fails
    3. Count chunks from kv_store_text_chunks.json
    """
    import subprocess
    counts = {"entities": 0, "relations": 0, "chunks": 0}

    # Method 1: Count nodes/edges in GraphML using fast grep (works for any file size)
    graphml_file = db_path / "graph_chunk_entity_relation.graphml"
    if graphml_file.exists():
        try:
            # Use grep -c for fast counting (handles 200MB+ files in <1 second)
            node_result = subprocess.run(
                ['grep', '-c', '<node ', str(graphml_file)],
                capture_output=True, text=True, timeout=10
            )
            if node_result.returncode == 0:
                counts["entities"] = int(node_result.stdout.strip())

            edge_result = subprocess.run(
                ['grep', '-c', '<edge ', str(graphml_file)],
                capture_output=True, text=True, timeout=10
            )
            if edge_result.returncode == 0:
                counts["relations"] = int(edge_result.stdout.strip())
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, ValueError, FileNotFoundError):
            # Fallback: Python read for small files only
            try:
                file_size = graphml_file.stat().st_size
                if file_size < 50 * 1024 * 1024:  # 50MB limit for Python fallback
                    with open(graphml_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                        counts["entities"] = content.count('<node ')
                        counts["relations"] = content.count('<edge ')
            except (IOError, OSError):
                pass

    # Method 2: Count chunks from kv_store_text_chunks.json
    if counts["chunks"] == 0:
        chunks_file = db_path / "kv_store_text_chunks.json"
        if chunks_file.exists():
            try:
                with open(chunks_file, 'r') as f:
                    data = json.load(f)
                    counts["chunks"] = len(data) if isinstance(data, dict) else len(data)
            except (IOError, json.JSONDecodeError):
                pass

    return counts


def get_database_stats(entry: DatabaseEntry) -> DatabaseStats:
    """Get comprehensive stats for a database entry."""
    db_path = Path(entry.path)
    errors = []

    # Check if path exists
    exists = db_path.exists()
    if not exists:
        errors.append(f"Database path not found: {entry.path}")

    # Get size
    size_bytes = get_directory_size(db_path) if exists else 0

    # Get entity counts
    counts = parse_database_metadata(db_path) if exists else {"entities": 0, "relations": 0, "chunks": 0}

    # Parse last_sync
    last_sync = None
    if entry.last_sync:
        try:
            last_sync = datetime.fromisoformat(entry.last_sync)
        except ValueError:
            pass

    # Get watcher status
    running, pid = is_watcher_running(entry.name)
    watcher_mode = None
    if running:
        # Detect mode (simplified - assume standalone for now)
        watcher_mode = "standalone"

    # Check source folder exists
    if entry.source_folder and not Path(entry.source_folder).exists():
        errors.append(f"Source folder not found: {entry.source_folder}")

    # Get document count, processing files, and recent files from doc_status.json
    document_count = 0
    processing_files = []
    recent_files = []
    doc_status_file = db_path / "doc_status.json"
    if exists and doc_status_file.exists():
        try:
            with open(doc_status_file, 'r') as f:
                doc_status = json.load(f)
                # Count completed documents
                completed = [k for k, v in doc_status.items() if v.get("status") == "processed"]
                document_count = len(completed)
                # Get processing files
                processing_files = [k for k, v in doc_status.items() if v.get("status") == "processing"]
                # Get recent files (last 5 processed, sorted by timestamp)
                processed_items = []
                for k, v in doc_status.items():
                    if v.get("status") == "processed":
                        ts_str = v.get("content_summary", {}).get("chunks_created_at") or v.get("status_updated")
                        if ts_str:
                            try:
                                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00").replace("+00:00", ""))
                            except ValueError:
                                ts = datetime.min
                        else:
                            ts = datetime.min
                        processed_items.append({
                            "name": Path(k).name,
                            "path": k,
                            "timestamp": ts,
                            "chunks": v.get("content_summary", {}).get("num_chunks", 0)
                        })
                processed_items.sort(key=lambda x: x["timestamp"], reverse=True)
                recent_files = processed_items[:5]
        except (IOError, json.JSONDecodeError):
            pass

    # Check for file size warnings (>500MB threshold)
    file_warnings = []
    SIZE_THRESHOLD = 500 * 1024 * 1024  # 500MB
    TOTAL_THRESHOLD = 2048 * 1024 * 1024  # 2GB
    if exists:
        for json_file in db_path.glob("*.json"):
            try:
                file_size = json_file.stat().st_size
                if file_size > SIZE_THRESHOLD:
                    file_warnings.append(f"{json_file.name}: {humanize_bytes(file_size)}")
            except OSError:
                pass
        if size_bytes > TOTAL_THRESHOLD:
            file_warnings.append(f"Total: {humanize_bytes(size_bytes)} (consider PostgreSQL)")

    # Get processing progress from recent log entries
    processing_progress = {}
    log_file = Path("logs") / f"watcher_{entry.name}.log"
    if log_file.exists():
        try:
            # Read last 100 lines of log for more context
            with open(log_file, 'r') as f:
                lines = f.readlines()[-100:]

            # Patterns to match
            chunk_pattern = re.compile(r'Chunk (\d+) of (\d+)')
            batch_pattern = re.compile(r'Processing batch (\d+)/(\d+) \((\d+) files?\)')
            file_pattern = re.compile(r'(?:Extracting|Merging) stage \d+/\d+: (.+)')
            ingested_pattern = re.compile(r'\[OK\] Ingested: (.+)')

            current_file = ""
            current_batch = 0
            total_batches = 0
            batch_files = 0

            for line in reversed(lines):
                # Look for chunk progress (highest priority)
                if not processing_progress.get("current_chunk"):
                    match = chunk_pattern.search(line)
                    if match:
                        processing_progress["current_chunk"] = int(match.group(1))
                        processing_progress["total_chunks"] = int(match.group(2))
                        processing_progress["percent"] = int(100 * int(match.group(1)) / int(match.group(2)))

                # Look for batch progress
                if not current_batch:
                    match = batch_pattern.search(line)
                    if match:
                        current_batch = int(match.group(1))
                        total_batches = int(match.group(2))
                        batch_files = int(match.group(3))

                # Look for current file being processed
                if not current_file:
                    match = file_pattern.search(line)
                    if match:
                        current_file = Path(match.group(1)).name
                    else:
                        match = ingested_pattern.search(line)
                        if match:
                            current_file = match.group(1)

                # Stop if we have all info
                if processing_progress.get("current_chunk") and current_file and current_batch:
                    break

            # Add batch and file info to progress
            if current_file:
                processing_progress["current_file"] = current_file
            if current_batch:
                processing_progress["current_batch"] = current_batch
                processing_progress["total_batches"] = total_batches
                processing_progress["batch_files"] = batch_files

        except (IOError, OSError):
            pass

    return DatabaseStats(
        name=entry.name,
        path=entry.path,
        source_folder=entry.source_folder,
        source_type=entry.source_type,
        exists=exists,
        healthy=len(errors) == 0,
        total_size_bytes=size_bytes,
        total_size_human=humanize_bytes(size_bytes),
        entity_count=counts["entities"],
        relation_count=counts["relations"],
        chunk_count=counts["chunks"],
        document_count=document_count,
        processing_files=processing_files,
        recent_files=recent_files,
        file_warnings=file_warnings,
        processing_progress=processing_progress,
        last_sync=last_sync,
        last_sync_human=humanize_timedelta(last_sync),
        watcher_running=running,
        watcher_pid=pid,
        watcher_mode=watcher_mode,
        auto_watch=entry.auto_watch,
        watch_interval=entry.watch_interval,
        model=entry.model,
        recursive=entry.recursive,
        description=entry.description,
        errors=errors
    )


def get_all_database_stats(registry: Optional[DatabaseRegistry] = None) -> List[DatabaseStats]:
    """Get stats for all registered databases."""
    if registry is None:
        registry = get_registry()

    stats = []
    for entry in registry.list_all():
        try:
            stats.append(get_database_stats(entry))
        except Exception as e:
            # Create error entry
            stats.append(DatabaseStats(
                name=entry.name,
                path=entry.path,
                source_folder=entry.source_folder,
                source_type=entry.source_type,
                exists=False,
                healthy=False,
                errors=[f"Failed to get stats: {e}"]
            ))

    return stats


# Multiple log patterns to match different formats
LOG_PATTERNS = [
    # Format: [2025-12-06 17:24:11] message
    re.compile(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\s*(.+)'),
    # Format: 2025-12-06 17:23:47,421 - module - LEVEL - message
    re.compile(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ - .+ - (INFO|WARNING|ERROR|DEBUG) - (.+)'),
    # Format: INFO: [module] message (LightRAG format)
    re.compile(r'(INFO|WARNING|ERROR|DEBUG):\s*\[([^\]]+)\]\s*(.+)'),
    # Format: 2025-12-06 17:24:11 - message (simple timestamp)
    re.compile(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+-\s+(.+)'),
]

def parse_log_line(line: str, default_db: str = "system") -> Optional[LogEntry]:
    """Parse a log line into a LogEntry."""
    line = line.strip()
    if not line:
        return None

    # Skip progress bar lines and ANSI escape sequences
    if '\x1b[' in line or '█' in line or '|' in line and '%' in line:
        return None

    timestamp = None
    message = None
    level = "INFO"

    # Try first pattern: [2025-12-06 17:24:11] message
    match = LOG_PATTERNS[0].match(line)
    if match:
        timestamp_str, message = match.groups()
        try:
            timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            timestamp = datetime.now()
    else:
        # Try second pattern: 2025-12-06 17:23:47,421 - module - LEVEL - message
        match = LOG_PATTERNS[1].match(line)
        if match:
            timestamp_str, level_str, message = match.groups()
            try:
                timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                timestamp = datetime.now()
            level = level_str
        else:
            # Try third pattern: INFO: [module] message (LightRAG format)
            match = LOG_PATTERNS[2].match(line)
            if match:
                level_str, module, message = match.groups()
                level = level_str
                timestamp = datetime.now()  # LightRAG logs often don't have timestamps
                # Include module in message for context
                message = f"[{module}] {message}"
            else:
                # Try fourth pattern: 2025-12-06 17:24:11 - message
                match = LOG_PATTERNS[3].match(line)
                if match:
                    timestamp_str, message = match.groups()
                    try:
                        timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        timestamp = datetime.now()

    if not timestamp or not message:
        return None

    # Detect database from message
    db_name = default_db
    if ":" in message:
        parts = message.split(":", 1)
        # Check if first part looks like a database name (no spaces, reasonable length)
        potential_db = parts[0].strip()
        if potential_db and " " not in potential_db and len(potential_db) < 30:
            # Skip common prefixes that aren't database names
            skip_prefixes = [
                # Log levels
                "SUCCESS", "FAILED", "INFO", "WARNING", "ERROR", "DEBUG", "CRITICAL",
                # Common module/path prefixes
                "src", "nano-vectordb", "lightrag", "hybridrag", "http", "https",
                # Common log message starters
                "File", "Path", "Processing", "Loading", "Saving", "Starting", "Stopping",
                "Created", "Updated", "Deleted", "Found", "Missing", "Added", "Removed",
                "Exception", "Traceback", "Error", "Warning", "Note",
                # Time-related
                "Elapsed", "Duration", "Time", "Timestamp",
            ]
            # Also skip if it looks like a path component or number
            skip_patterns = potential_db.startswith(("/", ".", "[")) or potential_db.isdigit()
            if potential_db not in skip_prefixes and not skip_patterns:
                db_name = potential_db
                message = parts[1].strip()

    # Detect level from message content
    msg_lower = message.lower()
    if "error" in msg_lower or "failed" in msg_lower or "✗" in message:
        level = "ERROR"
    elif "warning" in msg_lower or "⚠" in message:
        level = "WARNING"
    elif "success" in msg_lower or "✓" in message or "✅" in message or "ingested" in msg_lower:
        level = "SUCCESS"

    return LogEntry(
        timestamp=timestamp,
        level=level,
        database=db_name,
        message=message,
        raw=line
    )


def _build_path_to_db_map() -> Dict[str, str]:
    """Build a mapping from database paths to database names from the registry."""
    path_to_db = {}
    try:
        registry = get_registry()
        entries = registry.list_all()
        # Handle both dict and list formats
        if isinstance(entries, dict):
            entry_list = list(entries.values())
        else:
            entry_list = entries

        for entry in entry_list:
            if entry.path:
                # Normalize path for matching
                path_to_db[str(Path(entry.path).resolve())] = entry.name
                # Also add the raw path
                path_to_db[entry.path] = entry.name
    except Exception:
        pass
    return path_to_db


def _extract_db_from_log_content(file_lines: List[str], path_to_db: Dict[str, str]) -> str:
    """Extract database name from log content by matching paths to registry entries."""
    # Look for working directory patterns in the log content
    for line in file_lines[:50]:  # Check first 50 lines for working dir
        # Match patterns like "working dir: /path/to/db" or "Working directory: /path/to/db"
        # Also match paths in general context
        for path, db_name in path_to_db.items():
            if path in line:
                return db_name
    return "system"


def get_recent_logs(
    db_name: Optional[str] = None,
    lines: int = 50,
    log_dir: Optional[Path] = None
) -> List[LogEntry]:
    """Get recent log entries.

    Uses grep to efficiently extract relevant entries from large log files
    (watcher logs can be 100k+ lines with many LLM operation entries).
    """
    import subprocess

    if log_dir is None:
        log_dir = Path(__file__).parent.parent.parent / "logs"

    entries = []

    if not log_dir.exists():
        return entries

    # Build path-to-database mapping from registry
    path_to_db = _build_path_to_db_map()

    # Collect log files
    log_files = []

    if db_name:
        # Specific database logs
        patterns = [
            f"watcher_{db_name}*.log",
            "ingestion_*.log"
        ]
        for pattern in patterns:
            log_files.extend(log_dir.glob(pattern))
    else:
        # All logs
        log_files = list(log_dir.glob("*.log"))

    # Sort by modification time (newest first)
    log_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

    # Patterns for relevant log entries (ingestion/processing activity)
    # Use grep to efficiently filter large log files
    grep_patterns = [
        r"\[OK\]",           # Successful ingestion
        r"Ingested:",        # Ingestion messages
        r"Processing batch", # Batch progress
        r"Chunk \d+ of",     # Chunk progress
        r"Complete",         # Completion messages
        r"Started",          # Watcher start
        r"Stopped",          # Watcher stop
        r"ERROR",            # Errors
        r"WARNING",          # Warnings
    ]
    combined_pattern = "|".join(grep_patterns)

    all_lines = []
    for log_file in log_files[:5]:  # Limit to 5 most recent files
        try:
            # Determine default database name from filename
            if log_file.stem.startswith("watcher_"):
                default_db = log_file.stem.replace("watcher_", "").split("_")[0]
            else:
                default_db = "system"

            # Use grep to efficiently extract relevant lines from large log files
            # Then take last N lines of the filtered output
            try:
                result = subprocess.run(
                    ['grep', '-E', combined_pattern, str(log_file)],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0 and result.stdout:
                    # Take last 200 relevant lines
                    relevant_lines = result.stdout.strip().split('\n')[-200:]
                    for line in relevant_lines:
                        entry = parse_log_line(line, default_db)
                        if entry:
                            if db_name is None or entry.database == db_name:
                                all_lines.append(entry)
            except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
                # Fallback: read last 500 lines if grep fails
                with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                    file_lines = f.readlines()[-500:]
                    for line in file_lines:
                        entry = parse_log_line(line, default_db)
                        if entry:
                            if db_name is None or entry.database == db_name:
                                all_lines.append(entry)
        except (OSError, IOError):
            pass

    # Sort by timestamp (newest first)
    all_lines.sort(key=lambda e: e.timestamp, reverse=True)
    # Take newest entries, then reverse so oldest is first (newest at bottom)
    return list(reversed(all_lines[:lines]))


def get_watcher_process_info(pid: int) -> Optional[Dict[str, Any]]:
    """Get detailed process info for a watcher."""
    try:
        proc = psutil.Process(pid)
        return {
            "pid": pid,
            "cpu_percent": proc.cpu_percent(),
            "memory_mb": proc.memory_info().rss / (1024 * 1024),
            "create_time": datetime.fromtimestamp(proc.create_time()),
            "status": proc.status(),
            "cmdline": proc.cmdline()
        }
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None


def collect_snapshot(registry: Optional[DatabaseRegistry] = None) -> MonitorSnapshot:
    """Collect a complete monitoring snapshot."""
    if registry is None:
        registry = get_registry()

    databases = get_all_database_stats(registry)
    logs = get_recent_logs(lines=100)

    # Aggregate stats
    watchers_running = sum(1 for db in databases if db.watcher_running)
    watchers_total = len(databases)
    total_entities = sum(db.entity_count for db in databases)
    total_relations = sum(db.relation_count for db in databases)
    total_size = sum(db.total_size_bytes for db in databases)

    # Collect errors
    errors = []
    for db in databases:
        errors.extend(db.errors)

    return MonitorSnapshot(
        timestamp=datetime.now(),
        databases=databases,
        watchers_running=watchers_running,
        watchers_total=watchers_total,
        total_entities=total_entities,
        total_relations=total_relations,
        total_size_bytes=total_size,
        total_size_human=humanize_bytes(total_size),
        recent_logs=logs,
        errors=errors
    )


class DataCollector:
    """
    Continuous data collector for the monitor.

    Maintains cached state and provides efficient updates.
    """

    def __init__(self, registry: Optional[DatabaseRegistry] = None):
        self.registry = registry or get_registry()
        self.watch_manager = WatchManager(self.registry)
        self._last_snapshot: Optional[MonitorSnapshot] = None

    def reload(self) -> None:
        """Reload registry from disk to pick up external changes.

        BUG-011 fix: Provides a way to refresh the registry when
        external processes may have modified the database configuration.
        """
        self.registry = get_registry()  # Get fresh instance from disk
        self.watch_manager = WatchManager(self.registry)
        self._last_snapshot = None  # Clear cached snapshot

    def refresh(self) -> MonitorSnapshot:
        """Collect fresh snapshot.

        BUG-006 fix: Always reload registry from disk before collecting snapshot
        to ensure we capture changes from external processes (watcher, CLI).
        """
        self.reload()  # Reload registry from disk first
        self._last_snapshot = collect_snapshot(self.registry)
        return self._last_snapshot

    def get_snapshot(self) -> Optional[MonitorSnapshot]:
        """Get last collected snapshot."""
        return self._last_snapshot

    def get_database(self, name: str) -> Optional[DatabaseStats]:
        """Get stats for a specific database."""
        entry = self.registry.get(name)
        if entry:
            return get_database_stats(entry)
        return None

    def get_logs(self, db_name: Optional[str] = None, lines: int = 50) -> List[LogEntry]:
        """Get recent logs, optionally filtered by database."""
        return get_recent_logs(db_name=db_name, lines=lines)

    def start_watcher(self, db_name: str) -> Tuple[bool, str]:
        """Start watcher for a database."""
        return self.watch_manager.start_watcher(db_name)

    def stop_watcher(self, db_name: str) -> Tuple[bool, str]:
        """Stop watcher for a database."""
        return self.watch_manager.stop_watcher(db_name)

    def toggle_auto_watch(self, db_name: str) -> Tuple[bool, str]:
        """Toggle auto-watch for a database."""
        entry = self.registry.get(db_name)
        if not entry:
            return False, f"Database not found: {db_name}"

        new_value = not entry.auto_watch
        try:
            self.registry.update(db_name, auto_watch=new_value)
            return True, f"Auto-watch {'enabled' if new_value else 'disabled'}"
        except Exception as e:
            return False, f"Failed to update: {e}"

    def force_sync(self, db_name: str) -> Tuple[bool, str]:
        """Force a sync/re-ingestion for a database.

        Triggers actual ingestion by starting the watcher process if not running,
        or signaling a re-scan if the watcher is already active.
        """
        entry = self.registry.get(db_name)
        if not entry:
            return False, f"Database not found: {db_name}"

        if not entry.source_folder:
            return False, "No source folder configured"

        try:
            # Check if watcher is running (use sync version from database_registry)
            from ..database_registry import is_watcher_running

            watcher_running, pid = is_watcher_running(db_name)

            if watcher_running:
                # Signal watcher to re-scan by touching a trigger file
                from pathlib import Path
                trigger_file = Path.home() / ".hybridrag" / "watcher_control" / f"{db_name}.rescan"
                trigger_file.parent.mkdir(parents=True, exist_ok=True)
                trigger_file.touch()
                self.registry.update_last_sync(db_name)
                return True, f"Re-scan triggered for running watcher (PID: {pid})"
            else:
                # Start a one-shot ingestion process
                import subprocess
                import sys

                cmd = [
                    sys.executable,
                    "-m", "hybridrag",
                    "ingest",
                    db_name,
                    "--source", entry.source_folder,
                ]

                # Run in background
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )

                self.registry.update_last_sync(db_name)
                return True, f"Ingestion started (PID: {proc.pid})"

        except Exception as e:
            return False, f"Failed to trigger sync: {e}"
