"""
History Panel Widget
====================

Shows 24-hour timeline of when files were last processed each hour.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from textual.widgets import Static
from textual.reactive import reactive
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from ..data_collector import LogEntry


class HistoryPanel(Static, can_focus=True):
    """
    Panel showing 24-hour timeline of file processing activity.

    For each hour in the last 24 hours, shows:
    - Whether any files were processed
    - Count of files processed
    - The last file processed in that hour
    - Timestamp of last processing
    """

    entries: reactive[List[LogEntry]] = reactive([])
    filter_database: reactive[str | None] = reactive(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._hourly_data: Dict[int, Dict] = {}  # hour (0-23) -> data

    def on_mount(self) -> None:
        """Initialize with empty timeline."""
        self._compute_24h_timeline()
        self.refresh_display()

    def update_entries(self, entries: List[LogEntry]) -> None:
        """Update with new log entries."""
        self.entries = entries
        self._compute_24h_timeline()
        self.refresh_display()

    def _compute_24h_timeline(self) -> None:
        """Build 48-hour timeline of activity from logs AND database metadata."""
        now = datetime.now()

        # Initialize all 48 hours (show 30 most recent with activity)
        self._hourly_data = {}
        for i in range(48):
            hour_start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=i)
            self._hourly_data[i] = {
                "hour_start": hour_start,
                "count": 0,
                "last_file": None,
                "last_time": None,
                "databases": set()
            }

        cutoff = now - timedelta(hours=48)

        # Source 1: Log entries
        for entry in self.entries:
            # Skip entries older than 48 hours
            if entry.timestamp < cutoff:
                continue

            # Filter by database if set
            if self.filter_database and entry.database != self.filter_database:
                continue

            # Count file processing and success messages
            msg_lower = entry.message.lower()

            # Negative keywords - skip error/failure messages
            negative_keywords = ["error", "failed", "exception", "traceback", "not found", "missing", "cannot", "unable"]
            if any(neg in msg_lower for neg in negative_keywords):
                continue

            # Positive keywords indicating actual file processing
            keywords = ["ingest", "processed", "added", "chunk", "success", "complete", "queued", "extracted"]
            # More specific patterns that indicate actual file activity
            specific_patterns = ["ingested", "✓", "✅", "files processed", "file processed", "[OK]", "batch complete"]

            if not any(kw in msg_lower for kw in keywords) and not any(p in entry.message for p in specific_patterns):
                continue

            # Calculate which hour bucket (0 = current hour, 47 = 48 hours ago)
            hours_ago = int((now - entry.timestamp).total_seconds() / 3600)
            if hours_ago < 0 or hours_ago >= 48:
                continue

            data = self._hourly_data[hours_ago]
            data["count"] += 1
            data["databases"].add(entry.database)

            # Track the most recent file in this hour
            if data["last_time"] is None or entry.timestamp > data["last_time"]:
                data["last_time"] = entry.timestamp
                data["last_file"] = self._extract_filename(entry.message) or entry.message[:50]

        # Source 2: database_metadata.json ingestion history (captures watcher activity)
        self._add_metadata_history(cutoff, now)

    def _extract_filename(self, message: str) -> Optional[str]:
        """Extract filename from log message."""
        import re

        patterns = [
            r'Ingested\s+([^\s]+)',
            r'Processed\s+([^\s]+)',
            r'Added\s+([^\s]+)',
            r'file[:\s]+([^\s]+)',
            r'([^\s/\\]+\.(?:md|txt|json|py|js|ts|yaml|yml))',
        ]

        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    def _add_metadata_history(self, cutoff: datetime, now: datetime) -> None:
        """Add history from database_metadata.json files for watcher activity."""
        try:
            # Get the registry to find database paths
            from src.database_registry import get_registry
            registry = get_registry()

            entries = registry.list_all()
            # Handle both dict and list formats
            if isinstance(entries, dict):
                entry_list = list(entries.values())
            else:
                entry_list = entries

            for entry in entry_list:
                name = entry.name
                # Skip if filtering to a different database
                if self.filter_database and name != self.filter_database:
                    continue

                # Check for metadata file
                metadata_path = Path(entry.path) / "database_metadata.json"
                if not metadata_path.exists():
                    continue

                try:
                    with open(metadata_path, 'r') as f:
                        metadata = json.load(f)

                    # Look for ingestion history in metadata
                    ingestion_history = metadata.get("ingestion_history", [])
                    for record in ingestion_history:
                        try:
                            timestamp = datetime.fromisoformat(record.get("timestamp", ""))
                            if timestamp < cutoff:
                                continue

                            hours_ago = int((now - timestamp).total_seconds() / 3600)
                            if hours_ago < 0 or hours_ago >= 48:
                                continue

                            data = self._hourly_data[hours_ago]
                            data["count"] += record.get("files_processed", 1)
                            data["databases"].add(name)

                            if data["last_time"] is None or timestamp > data["last_time"]:
                                data["last_time"] = timestamp
                                # Extract source folder name or use notes as fallback
                                source = record.get("source_folder", "")
                                data["last_file"] = Path(source).name if source else record.get("notes", "watcher activity")
                        except (ValueError, KeyError):
                            continue

                except (json.JSONDecodeError, IOError):
                    continue
        except Exception:
            # Silently fail if registry not available
            pass

    def refresh_display(self) -> None:
        """Refresh the panel display."""
        now = datetime.now()

        table = Table(
            show_header=True,
            header_style="bold cyan",
            expand=True,
            box=None,
            padding=(0, 1)
        )

        table.add_column("Hour", style="dim", width=14)
        table.add_column("Status", width=8, justify="center")
        table.add_column("Files", style="green", justify="right", width=6)
        table.add_column("Last Processed", style="white", overflow="ellipsis")

        total_files = 0
        active_hours = 0
        rows_shown = 0
        max_rows = 30  # Show up to 30 most recent entries

        # Collect all hour data first to count totals
        for hours_ago in range(48):
            data = self._hourly_data.get(hours_ago, {"count": 0})
            count = data.get("count", 0)
            total_files += count
            if count > 0:
                active_hours += 1

        # Show hours in order (current hour first), limited to 30 rows
        for hours_ago in range(48):
            if rows_shown >= max_rows:
                break

            data = self._hourly_data.get(hours_ago, {"count": 0})
            hour_start = data.get("hour_start", now - timedelta(hours=hours_ago))
            count = data.get("count", 0)

            # Skip hours with no activity after first 6 hours
            if hours_ago >= 6 and count == 0:
                continue

            # Format hour label
            if hours_ago == 0:
                hour_label = f"[bold green]Now ({hour_start.strftime('%H:00')})[/bold green]"
            elif hours_ago < 6:
                hour_label = f"{hour_start.strftime('%H:00')} ({hours_ago}h ago)"
            elif hour_start.date() == now.date():
                hour_label = f"Today {hour_start.strftime('%H:00')}"
            elif hour_start.date() == (now - timedelta(days=1)).date():
                hour_label = f"Yesterday {hour_start.strftime('%H:00')}"
            else:
                hour_label = hour_start.strftime("%m/%d %H:00")

            if count > 0:
                status = "[green]●[/green]"  # Active
                count_str = f"[green]{count}[/green]"

                last_file = data.get("last_file", "-")
                last_time = data.get("last_time")
                if last_time:
                    time_str = last_time.strftime("%H:%M:%S")
                    last_display = f"[dim]{time_str}[/dim] {last_file[:30]}"
                else:
                    last_display = last_file[:40] if last_file else "-"
            else:
                status = "[dim]○[/dim]"  # Inactive
                count_str = "[dim]-[/dim]"
                last_display = "[dim]No activity[/dim]"

            table.add_row(hour_label, status, count_str, last_display)
            rows_shown += 1

        from rich.box import SIMPLE
        self.update(Panel(
            table,
            border_style="dim",
            box=SIMPLE,
            title=f"Processing Timeline | [bold green]{total_files} files[/bold green] processed in {active_hours} hours",
            subtitle=f"[dim]{self.filter_database or 'All databases'} | ● active ○ idle | 48h window[/dim]"
        ))

    def set_filter(self, db_name: Optional[str]) -> None:
        """Set database filter."""
        self.filter_database = db_name
        self._compute_24h_timeline()
        self.refresh_display()

    def watch_filter_database(self, old_value: str | None, new_value: str | None) -> None:
        """Called when filter changes."""
        # Only recompute if we have entries
        if self.entries:
            self._compute_24h_timeline()
            self.refresh_display()
