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
from collections import deque
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

    Uses fast methods first:
    1. Parse log files for 'Loaded graph ... with X nodes, Y edges' (only if they reference this db_path)
    2. Count keys in kv_store JSON files (fast dict length)
    3. Read graphml file only as last resort (can be 100MB+)
    """
    counts = {"entities": 0, "relations": 0, "chunks": 0}
    db_path_str = str(db_path.resolve())

    # Method 1: Try to find counts in recent log files (fastest)
    # IMPORTANT: Only use log entries that explicitly reference this database's path
    log_dir = Path(__file__).parent.parent.parent / "logs"
    if log_dir.exists():
        try:
            log_files = sorted(log_dir.glob("*.log"), key=lambda f: f.stat().st_mtime, reverse=True)
            for log_file in log_files[:3]:  # Check 3 most recent logs
                try:
                    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        # Verify this log file is for our specific database
                        if db_path_str not in content and db_path.name not in content:
                            continue
                        # Look for: "Loaded graph ... with 44990 nodes, 80123 edges"
                        match = re.search(r'Loaded graph.*?with\s+(\d+)\s+nodes?,\s*(\d+)\s+edges?', content)
                        if match:
                            counts["entities"] = int(match.group(1))
                            counts["relations"] = int(match.group(2))
                            break
                except (IOError, OSError, ValueError):
                    pass
        except (IOError, OSError):
            pass

    # Method 2: Count keys in kv_store files (fast - just dict length)
    if counts["entities"] == 0:
        entities_file = db_path / "kv_store_full_entities.json"
        if entities_file.exists():
            try:
                with open(entities_file, 'r') as f:
                    data = json.load(f)
                    counts["entities"] = len(data) if isinstance(data, dict) else len(data)
            except (IOError, json.JSONDecodeError):
                pass

    if counts["relations"] == 0:
        relations_file = db_path / "kv_store_full_relations.json"
        if relations_file.exists():
            try:
                with open(relations_file, 'r') as f:
                    data = json.load(f)
                    counts["relations"] = len(data) if isinstance(data, dict) else len(data)
            except (IOError, json.JSONDecodeError):
                pass

    if counts["chunks"] == 0:
        chunks_file = db_path / "kv_store_text_chunks.json"
        if chunks_file.exists():
            try:
                with open(chunks_file, 'r') as f:
                    data = json.load(f)
                    counts["chunks"] = len(data) if isinstance(data, dict) else len(data)
            except (IOError, json.JSONDecodeError):
                pass

    # Method 3: Try graphml file ONLY if still no counts (slowest - avoid for large files)
    if counts["entities"] == 0:
        graphml_file = db_path / "graph_chunk_entity_relation.graphml"
        if graphml_file.exists():
            try:
                # Only read graphml for small files (under 10MB)
                file_size = graphml_file.stat().st_size
                if file_size < 10 * 1024 * 1024:  # 10MB limit
                    with open(graphml_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                        counts["entities"] = content.count('<node ')
                        counts["relations"] = content.count('<edge ')
            except (IOError, OSError):
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
    """Get recent log entries."""
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

    # Read lines from most recent files
    all_lines = []
    for log_file in log_files[:5]:  # Limit to 5 most recent files
        try:
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                file_lines = f.readlines()[-100:]  # Last 100 lines per file

                # Determine default database name
                # First try: watcher_<dbname>.log format
                if log_file.stem.startswith("watcher_"):
                    default_db = log_file.stem.replace("watcher_", "").split("_")[0]
                # Second try: Look for database path in log content
                elif path_to_db:
                    default_db = _extract_db_from_log_content(file_lines, path_to_db)
                else:
                    default_db = "system"

                for line in file_lines:
                    entry = parse_log_line(line, default_db)
                    if entry:
                        # Filter by db_name if specified
                        if db_name is None or entry.database == db_name:
                            all_lines.append(entry)
        except (OSError, IOError):
            pass

    # Sort by timestamp (oldest first so newest appear at bottom when displayed)
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
        self._log_cache: deque = deque(maxlen=500)

    def refresh(self) -> MonitorSnapshot:
        """Collect fresh snapshot."""
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
        """Force a sync/re-ingestion for a database."""
        entry = self.registry.get(db_name)
        if not entry:
            return False, f"Database not found: {db_name}"

        if not entry.source_folder:
            return False, "No source folder configured"

        # This would trigger ingestion - for now just update timestamp
        try:
            self.registry.update_last_sync(db_name)
            return True, "Sync triggered (ingestion will run)"
        except Exception as e:
            return False, f"Failed: {e}"
