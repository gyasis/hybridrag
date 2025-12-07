"""
Watcher Panel Widget
====================

Shows detailed watcher status for the selected database.
"""

from textual.widgets import Static
from textual.reactive import reactive
from rich.panel import Panel
from rich.text import Text
from rich.table import Table

from ..data_collector import DatabaseStats


class WatcherPanel(Static):
    """
    Panel displaying watcher details for the selected database.

    Shows:
    - Watcher status (running/stopped)
    - PID if running
    - Mode (standalone/systemd)
    - Watch interval
    - Source folder
    - Auto-watch status
    """

    database: reactive[DatabaseStats | None] = reactive(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._default_content = self._render_empty()

    def _render_empty(self) -> Panel:
        """Render panel when no database selected."""
        return Panel(
            Text("Select a database to view watcher details", style="dim italic"),
            title="Watcher",
            border_style="dim",
            box=None
        )

    def _render_watcher(self, db: DatabaseStats) -> Panel:
        """Render watcher details for a database."""
        table = Table.grid(padding=(0, 2))
        table.add_column(style="bold cyan", width=12)
        table.add_column()

        # Status line
        if db.watcher_running:
            status = Text(f"🟢 Running", style="green bold")
            if db.watcher_pid:
                status.append(f" (PID {db.watcher_pid})", style="green")
        else:
            status = Text("⚪ Stopped", style="dim")

        table.add_row("Status:", status)

        # Mode
        if db.watcher_mode:
            mode_text = db.watcher_mode
        else:
            mode_text = "standalone" if db.watcher_running else "-"
        table.add_row("Mode:", mode_text)

        # Interval
        interval_min = db.watch_interval // 60
        interval_sec = db.watch_interval % 60
        if interval_sec:
            interval_str = f"{interval_min}m {interval_sec}s"
        else:
            interval_str = f"{interval_min}m"
        table.add_row("Interval:", f"{db.watch_interval}s ({interval_str})")

        # Source folder (truncated if long)
        if db.source_folder:
            source = db.source_folder
            if len(source) > 35:
                source = "..." + source[-32:]
            table.add_row("Source:", source)
        else:
            table.add_row("Source:", Text("-", style="dim"))

        # Auto-watch
        if db.auto_watch:
            auto_text = Text("✓ Enabled", style="green")
        else:
            auto_text = Text("✗ Disabled", style="dim")
        table.add_row("Auto-watch:", auto_text)

        # Model
        if db.model:
            table.add_row("Model:", db.model)

        # Type
        table.add_row("Type:", db.source_type)

        return Panel(
            table,
            title=f"Watcher: {db.name}",
            border_style="dim",
            box=None
        )

    def watch_database(self, database: DatabaseStats | None) -> None:
        """Called when database reactive changes."""
        if database:
            self.update(self._render_watcher(database))
        else:
            self.update(self._default_content)

    def on_mount(self) -> None:
        """Initialize with empty content."""
        self.update(self._default_content)
