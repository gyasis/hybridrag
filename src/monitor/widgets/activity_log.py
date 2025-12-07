"""
Activity Log Widget
===================

Real-time scrolling log viewer for ingestion/watcher activity.
"""

from textual.widgets import RichLog
from textual.reactive import reactive
from rich.text import Text

from ..data_collector import LogEntry


class ActivityLog(RichLog):
    """
    Scrolling log viewer showing recent activity.

    Features:
    - Color-coded log levels
    - Auto-scroll to bottom
    - Filter by database
    - Split view toggle (selected db vs all)
    """

    filter_database: reactive[str | None] = reactive(None)
    show_all: reactive[bool] = reactive(True)

    LEVEL_STYLES = {
        "INFO": "white",
        "SUCCESS": "green",
        "WARNING": "yellow",
        "ERROR": "red bold",
        "DEBUG": "dim",
    }

    def __init__(self, **kwargs):
        super().__init__(
            highlight=True,
            markup=True,
            wrap=True,
            auto_scroll=True,
            max_lines=500,
            **kwargs
        )
        self._entries: list[LogEntry] = []

    def on_mount(self) -> None:
        """Initialize log."""
        self.write("[dim italic]Activity log ready...[/dim italic]")

    def add_entry(self, entry: LogEntry) -> None:
        """Add a single log entry."""
        self._entries.append(entry)
        self._render_entry(entry)

    def _render_entry(self, entry: LogEntry) -> None:
        """Render a log entry to the log view."""
        # Check filter
        if not self.show_all and self.filter_database:
            if entry.database != self.filter_database:
                return

        style = self.LEVEL_STYLES.get(entry.level, "white")

        # Format timestamp
        timestamp = entry.timestamp.strftime("%H:%M:%S")

        # Build the log line
        line = Text()
        line.append(f"[{timestamp}] ", style="dim")
        line.append(f"{entry.database}: ", style="cyan bold")

        # For errors, show full message with wrapping for debugging
        if entry.level == "ERROR":
            line.append(entry.message, style=style)
            self.write(line)
            # If there's a path in the raw message, show it on next line
            if "/" in entry.raw and len(entry.raw) > 80:
                detail_line = Text()
                detail_line.append("           └─ ", style="dim")
                detail_line.append(entry.raw[-100:] if len(entry.raw) > 100 else entry.raw, style="dim red")
                self.write(detail_line)
        else:
            line.append(entry.message, style=style)
            self.write(line)

    def update_entries(self, entries: list[LogEntry]) -> None:
        """Update with a list of log entries."""
        self._entries = entries
        self.refresh_view()

    def refresh_view(self) -> None:
        """Refresh the log view with current entries and filters."""
        self.clear()

        # Filter entries
        if self.show_all:
            visible = self._entries
        elif self.filter_database:
            visible = [e for e in self._entries if e.database == self.filter_database]
        else:
            visible = self._entries

        # Render all visible entries
        for entry in visible:
            self._render_entry(entry)

    def watch_filter_database(self, old_value: str | None, new_value: str | None) -> None:
        """Called when filter changes."""
        self.refresh_view()

    def watch_show_all(self, old_value: bool, new_value: bool) -> None:
        """Called when show_all changes."""
        self.refresh_view()

    def toggle_view(self) -> None:
        """Toggle between all logs and filtered logs."""
        self.show_all = not self.show_all

    def set_filter(self, db_name: str | None) -> None:
        """Set database filter."""
        self.filter_database = db_name
        if db_name:
            self.show_all = False
