"""
History Panel Widget
====================

Shows 24-hour timeline of when files were last processed each hour.
"""

from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Optional

from textual.widgets import Static
from textual.reactive import reactive
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from ..data_collector import LogEntry


class HistoryPanel(Static):
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

    def update_entries(self, entries: List[LogEntry]) -> None:
        """Update with new log entries."""
        self.entries = entries
        self._compute_24h_timeline()
        self.refresh_display()

    def _compute_24h_timeline(self) -> None:
        """Build 24-hour timeline of activity."""
        now = datetime.now()

        # Initialize all 24 hours
        self._hourly_data = {}
        for i in range(24):
            hour_start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=i)
            self._hourly_data[i] = {
                "hour_start": hour_start,
                "count": 0,
                "last_file": None,
                "last_time": None,
                "databases": set()
            }

        cutoff = now - timedelta(hours=24)

        for entry in self.entries:
            # Skip entries older than 24 hours
            if entry.timestamp < cutoff:
                continue

            # Filter by database if set
            if self.filter_database and entry.database != self.filter_database:
                continue

            # Only count file processing messages
            msg_lower = entry.message.lower()
            if not any(kw in msg_lower for kw in ["ingest", "processed", "added", "file", "chunk"]):
                continue

            # Calculate which hour bucket (0 = current hour, 23 = 24 hours ago)
            hours_ago = int((now - entry.timestamp).total_seconds() / 3600)
            if hours_ago < 0 or hours_ago >= 24:
                continue

            data = self._hourly_data[hours_ago]
            data["count"] += 1
            data["databases"].add(entry.database)

            # Track the most recent file in this hour
            if data["last_time"] is None or entry.timestamp > data["last_time"]:
                data["last_time"] = entry.timestamp
                data["last_file"] = self._extract_filename(entry.message) or entry.message[:50]

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

        # Show hours in order (current hour first)
        for hours_ago in range(24):
            data = self._hourly_data.get(hours_ago, {"count": 0})
            hour_start = data.get("hour_start", now - timedelta(hours=hours_ago))

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

            count = data.get("count", 0)
            total_files += count

            if count > 0:
                active_hours += 1
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

            # Only show first 12 hours in compact view, or all if there's activity
            if hours_ago < 12 or count > 0:
                table.add_row(hour_label, status, count_str, last_display)

        # Summary
        summary = Text()
        summary.append(f"\n📈 {total_files} files", style="bold")
        summary.append(f" in ", style="dim")
        summary.append(f"{active_hours}/24 hours", style="bold cyan")

        self.update(Panel(
            table,
            border_style="blue",
            title="📅 24-Hour Processing Timeline",
            subtitle=f"[dim]{self.filter_database or 'All databases'} | ● active ○ idle[/dim]"
        ))

    def set_filter(self, db_name: Optional[str]) -> None:
        """Set database filter."""
        self.filter_database = db_name
        self._compute_24h_timeline()
        self.refresh_display()

    def watch_filter_database(self, old_value: str | None, new_value: str | None) -> None:
        """Called when filter changes."""
        self._compute_24h_timeline()
        self.refresh_display()
