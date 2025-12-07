"""
Status Bar Widget
=================

Bottom status bar showing summary statistics.
"""

from textual.widgets import Static
from textual.reactive import reactive
from rich.text import Text
from rich.console import Group
from rich.columns import Columns

from ..data_collector import MonitorSnapshot


class StatusBar(Static):
    """
    Status bar displaying summary statistics.

    Shows:
    - Number of databases
    - Watchers running/total
    - Total entities
    - Total size
    - Refresh interval
    - Error count
    """

    snapshot: reactive[MonitorSnapshot | None] = reactive(None)

    def __init__(self, refresh_interval: int = 2, **kwargs):
        super().__init__(**kwargs)
        self.refresh_interval = refresh_interval

    def _render_status(self, snapshot: MonitorSnapshot | None) -> Text:
        """Render status bar content."""
        if not snapshot:
            return Text("Loading...", style="dim italic")

        parts = []

        # Databases count
        db_count = len(snapshot.databases)
        parts.append(Text(f"Databases: {db_count}", style="cyan"))

        # Watchers
        if snapshot.watchers_running == snapshot.watchers_total and snapshot.watchers_total > 0:
            watcher_style = "green"
        elif snapshot.watchers_running > 0:
            watcher_style = "yellow"
        else:
            watcher_style = "dim"
        parts.append(Text(
            f"Watchers: {snapshot.watchers_running}/{snapshot.watchers_total}",
            style=watcher_style
        ))

        # Entities
        if snapshot.total_entities > 0:
            parts.append(Text(f"Entities: {snapshot.total_entities:,}", style="white"))

        # Size
        parts.append(Text(f"Size: {snapshot.total_size_human}", style="white"))

        # Refresh interval
        parts.append(Text(f"Refresh: {self.refresh_interval}s", style="dim"))

        # Errors
        error_count = len(snapshot.errors)
        if error_count > 0:
            parts.append(Text(f"Errors: {error_count}", style="red bold"))
        else:
            parts.append(Text("Errors: 0", style="green"))

        # Join with separators
        result = Text()
        for i, part in enumerate(parts):
            if i > 0:
                result.append(" │ ", style="dim")
            result.append_text(part)

        return result

    def watch_snapshot(self, snapshot: MonitorSnapshot | None) -> None:
        """Called when snapshot reactive changes."""
        self.update(self._render_status(snapshot))

    def on_mount(self) -> None:
        """Initialize with loading state."""
        self.update(Text("Initializing...", style="dim italic"))
