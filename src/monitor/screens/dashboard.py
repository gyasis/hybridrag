"""
Dashboard Screen
================

Main monitoring dashboard showing databases, watchers, and activity.
"""

from pathlib import Path
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static, Footer, Header
from textual.containers import Container, Horizontal, Vertical
from textual.binding import Binding
from textual.reactive import reactive
from rich.panel import Panel

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.monitor.data_collector import DataCollector, DatabaseStats, MonitorSnapshot
from src.monitor.widgets.database_table import DatabaseTable
from src.monitor.widgets.watcher_panel import WatcherPanel
from src.monitor.widgets.activity_log import ActivityLog
from src.monitor.widgets.action_panel import ActionPanel
from src.monitor.widgets.status_bar import StatusBar
from src.monitor.widgets.history_panel import HistoryPanel
from src.monitor.widgets.source_files_panel import SourceFilesPanel


class DashboardScreen(Screen):
    """
    Main monitoring dashboard.

    Layout:
    ┌─────────────────────────────────────────────────────────────────────────┐
    │  🔮 HybridRAG Monitor                                   [q]uit [r]efresh │
    ├─────────────────────────────────────────────────────────────────────────┤
    │ ┌─ Databases ──────────────────────────────────────────────────────────┐│
    │ │ NAME       │ STATUS │ SIZE   │ ENTITIES │ RELATIONS │ LAST SYNC     ││
    │ └──────────────────────────────────────────────────────────────────────┘│
    │ ┌─ Watcher ───────────────────┐ ┌─ Actions ──────────────────────────┐ │
    │ │ ...                         │ │ [n] New database                   │ │
    │ └─────────────────────────────┘ └────────────────────────────────────┘ │
    │ ┌─ Activity Log ───────────────────────────────────────────────────────┐│
    │ │ [17:24:07] specstory: Ingested file.md                               ││
    │ └──────────────────────────────────────────────────────────────────────┘│
    │ Databases: 2 │ Watchers: 1/2 │ Entities: 44,990 │ Size: 3.7 GB          │
    └─────────────────────────────────────────────────────────────────────────┘
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("n", "new_database", "New"),
        Binding("s", "start_watcher", "Start"),
        Binding("x", "stop_watcher", "Stop"),
        Binding("a", "toggle_auto_watch", "Auto-watch"),
        Binding("y", "force_sync", "Sync"),
        Binding("l", "view_logs", "Logs"),
        Binding("t", "toggle_log_scope", "Toggle Logs"),
        Binding("h", "toggle_history", "History"),
        Binding("i", "show_info", "Info"),
    ]

    CSS = """
    DashboardScreen {
        layout: grid;
        grid-size: 1;
        grid-rows: auto 1fr auto auto auto;
    }

    #header-row {
        height: 3;
        background: $surface;
        color: $text;
        padding: 0 2;
    }

    #header-title {
        text-style: bold;
    }

    #main-content {
        layout: grid;
        grid-size: 1;
        grid-rows: 1fr 1fr 1fr;
        padding: 0 1;
    }

    #database-section {
        height: 100%;
    }

    #middle-section {
        layout: grid;
        grid-size: 3 1;
        grid-columns: 1fr 1fr 1fr;
        height: 100%;
    }

    #watcher-panel {
        height: 100%;
    }

    #source-files-panel {
        height: 100%;
    }

    #action-panel {
        height: 100%;
    }

    #log-section {
        layout: grid;
        grid-size: 2 1;
        grid-columns: 1fr 1fr;
        height: 100%;
    }

    #activity-log {
        height: 100%;
    }

    #history-panel {
        height: 100%;
    }

    #status-bar {
        height: 1;
        background: $surface;
        padding: 0 1;
    }

    DatabaseTable {
        height: 100%;
        border: none;
    }

    WatcherPanel {
        height: 100%;
    }

    ActionPanel {
        height: 100%;
    }

    ActivityLog {
        height: 100%;
        border: none;
    }

    HistoryPanel {
        height: 100%;
    }

    SourceFilesPanel {
        height: 100%;
    }

    .hidden {
        display: none;
    }
    """

    selected_database: reactive[DatabaseStats | None] = reactive(None)
    snapshot: reactive[MonitorSnapshot | None] = reactive(None)

    def __init__(self, refresh_interval: int = 2, **kwargs):
        super().__init__(**kwargs)
        self.refresh_interval = refresh_interval
        self.collector = DataCollector()

    def compose(self) -> ComposeResult:
        # Header
        yield Horizontal(
            Static("🔮 [bold]HybridRAG Monitor[/bold]", id="header-title"),
            id="header-row"
        )

        # Main content area
        yield Container(
            # Database table section
            Container(
                DatabaseTable(id="database-table"),
                id="database-section"
            ),

            # Middle section: Watcher + Source Files + Actions
            Horizontal(
                WatcherPanel(id="watcher-panel"),
                SourceFilesPanel(id="source-files-panel"),
                ActionPanel(id="action-panel"),
                id="middle-section"
            ),

            # Activity log + History section (side by side)
            Horizontal(
                ActivityLog(id="activity-log"),
                HistoryPanel(id="history-panel"),
                id="log-section"
            ),

            id="main-content"
        )

        # Status bar
        yield StatusBar(refresh_interval=self.refresh_interval, id="status-bar")

        # Footer with keybindings
        yield Footer()

    def on_mount(self) -> None:
        """Initialize dashboard on mount."""
        self.action_refresh()
        # Set up auto-refresh timer
        self.set_interval(self.refresh_interval, self._auto_refresh)

    def _auto_refresh(self) -> None:
        """Auto-refresh callback."""
        self.action_refresh()

    def action_refresh(self) -> None:
        """Refresh all data."""
        try:
            snapshot = self.collector.refresh()
            self.snapshot = snapshot

            # Update database table
            table = self.query_one("#database-table", DatabaseTable)
            table.update_databases(snapshot.databases)

            # Update status bar
            status_bar = self.query_one("#status-bar", StatusBar)
            status_bar.snapshot = snapshot

            # Update activity log
            log = self.query_one("#activity-log", ActivityLog)
            log.update_entries(snapshot.recent_logs)

            # Update history panel
            history = self.query_one("#history-panel", HistoryPanel)
            history.update_entries(snapshot.recent_logs)

        except Exception as e:
            self.notify(f"Refresh error: {e}", severity="error")

    def on_database_table_database_selected(self, event: DatabaseTable.DatabaseSelected) -> None:
        """Handle database selection."""
        self.selected_database = event.database

        # Update watcher panel
        watcher_panel = self.query_one("#watcher-panel", WatcherPanel)
        watcher_panel.database = event.database

        # Update source files panel
        source_files_panel = self.query_one("#source-files-panel", SourceFilesPanel)
        source_files_panel.database = event.database

        # Update action panel
        action_panel = self.query_one("#action-panel", ActionPanel)
        action_panel.database = event.database

    def action_quit(self) -> None:
        """Quit the application."""
        self.app.exit()

    def action_new_database(self) -> None:
        """Open new database wizard."""
        from .wizard import WizardScreen
        self.app.push_screen(WizardScreen())

    def action_start_watcher(self) -> None:
        """Start watcher for selected database."""
        if not self.selected_database:
            self.notify("Select a database first", severity="warning")
            return

        success, msg = self.collector.start_watcher(self.selected_database.name)
        if success:
            self.notify(f"✓ {msg}", severity="information")
        else:
            self.notify(f"✗ {msg}", severity="error")

        self.action_refresh()

    def action_stop_watcher(self) -> None:
        """Stop watcher for selected database."""
        if not self.selected_database:
            self.notify("Select a database first", severity="warning")
            return

        success, msg = self.collector.stop_watcher(self.selected_database.name)
        if success:
            self.notify(f"✓ {msg}", severity="information")
        else:
            self.notify(f"✗ {msg}", severity="error")

        self.action_refresh()

    def action_toggle_auto_watch(self) -> None:
        """Toggle auto-watch for selected database."""
        if not self.selected_database:
            self.notify("Select a database first", severity="warning")
            return

        success, msg = self.collector.toggle_auto_watch(self.selected_database.name)
        if success:
            self.notify(f"✓ {msg}", severity="information")
        else:
            self.notify(f"✗ {msg}", severity="error")

        self.action_refresh()

    def action_force_sync(self) -> None:
        """Force sync for selected database."""
        if not self.selected_database:
            self.notify("Select a database first", severity="warning")
            return

        success, msg = self.collector.force_sync(self.selected_database.name)
        if success:
            self.notify(f"✓ {msg}", severity="information")
        else:
            self.notify(f"✗ {msg}", severity="error")

        self.action_refresh()

    def action_toggle_log_scope(self) -> None:
        """Toggle between all logs and selected database logs."""
        log = self.query_one("#activity-log", ActivityLog)

        if log.show_all:
            # Switch to filtered
            if self.selected_database:
                log.set_filter(self.selected_database.name)
                self.notify(f"Showing logs for: {self.selected_database.name}")
            else:
                self.notify("Select a database to filter logs", severity="warning")
        else:
            # Switch to all
            log.show_all = True
            self.notify("Showing all logs")

    def action_view_logs(self) -> None:
        """View detailed logs (could open a modal in future)."""
        self.action_toggle_log_scope()

    def action_show_info(self) -> None:
        """Show detailed info for selected database."""
        if not self.selected_database:
            self.notify("Select a database first", severity="warning")
            return

        db = self.selected_database
        info_lines = [
            f"[bold]Database: {db.name}[/bold]",
            f"Path: {db.path}",
            f"Source: {db.source_folder or 'N/A'}",
            f"Type: {db.source_type}",
            f"Size: {db.total_size_human}",
            f"Entities: {db.entity_count:,}",
            f"Relations: {db.relation_count:,}",
            f"Chunks: {db.chunk_count:,}",
            f"Last Sync: {db.last_sync_human}",
            f"Auto-watch: {'Yes' if db.auto_watch else 'No'}",
            f"Model: {db.model or 'default'}",
        ]

        if db.errors:
            info_lines.append("\n[red]Errors:[/red]")
            for err in db.errors:
                info_lines.append(f"  - {err}")

        self.notify("\n".join(info_lines), title=f"Database: {db.name}")

    def action_toggle_history(self) -> None:
        """Toggle history panel filter for selected database."""
        history = self.query_one("#history-panel", HistoryPanel)

        if history.filter_database:
            # Switch to all databases
            history.set_filter(None)
            self.notify("History: showing all databases")
        else:
            # Filter to selected database
            if self.selected_database:
                history.set_filter(self.selected_database.name)
                self.notify(f"History: showing {self.selected_database.name}")
            else:
                self.notify("Select a database to filter history", severity="warning")
