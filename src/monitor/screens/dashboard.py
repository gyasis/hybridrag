"""
Dashboard Screen
================

Main monitoring dashboard showing databases, watchers, and activity.
"""

from pathlib import Path
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static, Footer
from textual.containers import Container, Horizontal
from textual.binding import Binding
from textual.reactive import reactive

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
from src.monitor.widgets.alerts_panel import AlertsSummaryWidget


class DashboardScreen(Screen):
    """
    Main monitoring dashboard.

    Layout:
    ┌─────────────────────────────────────────────────────────────────────────┐
    │  🔮 HybridRAG Monitor                                   [q]uit [r]efresh │
    ├─────────────────────────────────────────────────────────────────────────┤
    │ ┌─ 24-Hour Processing Timeline ────────────────────────────────────────┐│
    │ │ Hour │ Status │ Files │ Last Processed                               ││
    │ └──────────────────────────────────────────────────────────────────────┘│
    │ ┌─ Databases ──────────────────────────────────────────────────────────┐│
    │ │ NAME  │ STATUS │ ENTITIES │ RELATIONS │ SIZE │ LAST SYNC             ││
    │ └──────────────────────────────────────────────────────────────────────┘│
    │ ┌─ Watcher ────────────────────┐ ┌─ Actions ──────────────────────────┐ │
    │ │ Watcher: Running (PID: 1234) │ │ [n] New  [s] Start  [x] Stop       │ │
    │ └──────────────────────────────┘ └────────────────────────────────────┘ │
    │ ┌─ Source Files ───────────────┐ ┌─ Activity Log ─────────────────────┐ │
    │ │ file.md     │ 5m ago │ 2KB  │ │ [17:24:07] specstory: Ingested ... │ │
    │ └──────────────────────────────┘ └────────────────────────────────────┘ │
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
        Binding("m", "toggle_maximize", "Maximize"),
        Binding("escape", "restore_layout", "Restore", show=False),
        Binding("tab", "focus_next_panel", "Tab", show=False),
        Binding("shift+tab", "focus_prev_panel", "Back Tab", show=False),
    ]

    # Panel IDs for Tab navigation (in order matching new layout)
    PANEL_IDS = [
        "history-panel",      # Timeline at top (full-width)
        "database-table",     # Top-left
        "watcher-panel",      # Top-right (top)
        "action-panel",       # Top-right (bottom)
        "source-files-panel", # Bottom-left
        "activity-log",       # Bottom-right
    ]

    CSS = """
    DashboardScreen {
        layout: grid;
        grid-size: 1;
        grid-rows: auto 12 10 12 1fr auto auto;
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

    #alerts-summary {
        dock: right;
        width: auto;
        padding: 0 2;
    }

    /* Row 2: Full-width timeline section */
    #timeline-section {
        height: 100%;
        padding: 0 1;
    }

    /* Row 3: Full-width database table section */
    #database-section {
        height: 100%;
        padding: 0 1;
    }

    /* Row 4: Watcher + Actions row: 1x2 side by side */
    #watcher-actions-row {
        height: 100%;
        layout: grid;
        grid-size: 2 1;
        grid-columns: 1fr 1fr;
        padding: 0 1;
    }

    #watcher-cell {
        height: 100%;
        width: 100%;
    }

    #action-cell {
        height: 100%;
        width: 100%;
    }

    /* Row 5: Bottom row: Source Files + Activity Log */
    #bottom-row {
        height: 100%;
        layout: grid;
        grid-size: 2 1;
        grid-columns: 1fr 1fr;
        padding: 0 1;
    }

    #source-files-cell {
        height: 100%;
        width: 100%;
    }

    #activity-log-cell {
        height: 100%;
        width: 100%;
    }

    /* When a cell is maximized, it takes full width */
    .maximized-cell {
        grid-columns: 1fr;
        grid-size: 1 1;
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

    #activity-log {
        height: 100%;
    }

    #history-panel {
        height: 100%;
    }

    #database-table {
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

    .panel-hidden {
        display: none;
    }

    /* Maximized mode: panel takes full height */
    .maximized-mode {
        grid-rows: auto 1fr auto auto;
    }

    /* Visual highlight when panels are focused */
    WatcherPanel:focus,
    SourceFilesPanel:focus,
    ActionPanel:focus,
    HistoryPanel:focus {
        border: solid cyan;
    }

    DatabaseTable:focus {
        border: solid cyan;
    }

    ActivityLog:focus {
        border: solid cyan;
    }
    """

    selected_database: reactive[DatabaseStats | None] = reactive(None)
    snapshot: reactive[MonitorSnapshot | None] = reactive(None)
    maximized_panel: reactive[str | None] = reactive(None)

    def __init__(self, refresh_interval: int = 2, **kwargs):
        super().__init__(**kwargs)
        self.refresh_interval = refresh_interval
        self.collector = DataCollector()
        self._refreshing = False  # Guard against concurrent refreshes

    def compose(self) -> ComposeResult:
        # Header with alerts summary
        yield Horizontal(
            Static("🔮 [bold]HybridRAG Monitor[/bold]", id="header-title"),
            AlertsSummaryWidget(id="alerts-summary"),
            id="header-row"
        )

        # Full-width 24-hour timeline at top
        yield Container(
            HistoryPanel(id="history-panel"),
            id="timeline-section"
        )

        # Full-width database table
        yield Container(
            DatabaseTable(id="database-table"),
            id="database-section"
        )

        # Watcher + Actions row: side by side (1x2)
        yield Horizontal(
            Container(
                WatcherPanel(id="watcher-panel"),
                id="watcher-cell"
            ),
            Container(
                ActionPanel(id="action-panel"),
                id="action-cell"
            ),
            id="watcher-actions-row"
        )

        # Bottom row: Source Files + Activity Log
        yield Horizontal(
            Container(
                SourceFilesPanel(id="source-files-panel"),
                id="source-files-cell"
            ),
            Container(
                ActivityLog(id="activity-log"),
                id="activity-log-cell"
            ),
            id="bottom-row"
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
        # Guard against concurrent refreshes
        if self._refreshing:
            return
        self._refreshing = True

        try:
            snapshot = self.collector.refresh()
            self.snapshot = snapshot

            # Update database table
            table = self.query_one("#database-table", DatabaseTable)
            table.update_databases(snapshot.databases)

            # Update status bar
            status_bar = self.query_one("#status-bar", StatusBar)
            status_bar.snapshot = snapshot

            # Update activity log (copy list to prevent shared mutation)
            log = self.query_one("#activity-log", ActivityLog)
            log.update_entries(list(snapshot.recent_logs))

            # Update history panel (copy list to prevent shared mutation)
            history = self.query_one("#history-panel", HistoryPanel)
            history.update_entries(list(snapshot.recent_logs))

            # Explicitly update panels with selected database
            # This ensures panels get data even if message wasn't received
            selected_db = table.get_selected_database()
            if selected_db:
                self._update_panels_for_database(selected_db)
            elif snapshot.databases:
                # Fallback: use first database if selection not working
                self._update_panels_for_database(snapshot.databases[0])

        except Exception as e:
            self.notify(f"Refresh error: {e}", severity="error")
        finally:
            self._refreshing = False

    def _update_panels_for_database(self, db: DatabaseStats) -> None:
        """Update all panels with selected database info."""
        self.selected_database = db

        # Update watcher panel
        watcher_panel = self.query_one("#watcher-panel", WatcherPanel)
        watcher_panel.database = db

        # Update source files panel
        source_files_panel = self.query_one("#source-files-panel", SourceFilesPanel)
        source_files_panel.database = db

        # Update action panel
        action_panel = self.query_one("#action-panel", ActionPanel)
        action_panel.database = db

    def on_database_table_database_selected(self, event: DatabaseTable.DatabaseSelected) -> None:
        """Handle database selection."""
        self._update_panels_for_database(event.database)

    def action_quit(self) -> None:
        """Quit the application."""
        self.app.exit()

    def _get_current_panel_index(self) -> int:
        """Get index of currently focused panel, or -1 if none."""
        focused = self.focused
        if focused:
            for idx, panel_id in enumerate(self.PANEL_IDS):
                try:
                    panel = self.query_one(f"#{panel_id}")
                    if focused == panel or focused in panel.query("*"):
                        return idx
                except Exception:
                    pass
        return -1

    def action_focus_next_panel(self) -> None:
        """Focus the next panel in order."""
        current_idx = self._get_current_panel_index()
        next_idx = (current_idx + 1) % len(self.PANEL_IDS)
        try:
            panel = self.query_one(f"#{self.PANEL_IDS[next_idx]}")
            panel.focus()
        except Exception:
            pass

    def action_focus_prev_panel(self) -> None:
        """Focus the previous panel in order."""
        current_idx = self._get_current_panel_index()
        prev_idx = (current_idx - 1) % len(self.PANEL_IDS)
        try:
            panel = self.query_one(f"#{self.PANEL_IDS[prev_idx]}")
            panel.focus()
        except Exception:
            pass

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

        # BUG-007 fix: Show symlink targets for path display
        def format_path(path: str | None) -> str:
            if not path:
                return "N/A"
            p = Path(path)
            if p.is_symlink():
                try:
                    target = p.resolve()
                    return f"{path} → {target}"
                except (OSError, RuntimeError):
                    return f"{path} [symlink]"
            return path

        info_lines = [
            f"[bold]Database: {db.name}[/bold]",
            f"Path: {format_path(db.path)}",
            f"Source: {format_path(db.source_folder)}",
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

    def _get_focused_panel_id(self) -> str | None:
        """Get the ID of the currently focused panel."""
        focused = self.focused
        if focused:
            for panel_id in self.PANEL_IDS:
                try:
                    panel = self.query_one(f"#{panel_id}")
                    if focused == panel or focused in panel.query("*"):
                        return panel_id
                except Exception:
                    pass
        return None

    def _get_panel_section_id(self, panel_id: str) -> str | None:
        """Get the main section ID for a panel."""
        section_map = {
            "history-panel": "timeline-section",
            "database-table": "database-section",
            "watcher-panel": "watcher-actions-row",
            "action-panel": "watcher-actions-row",
            "source-files-panel": "bottom-row",
            "activity-log": "bottom-row",
        }
        return section_map.get(panel_id)

    def _get_panel_cell_id(self, panel_id: str) -> str | None:
        """Get the cell ID for panels in split rows."""
        cell_map = {
            "watcher-panel": "watcher-cell",
            "action-panel": "action-cell",
            "source-files-panel": "source-files-cell",
            "activity-log": "activity-log-cell",
        }
        return cell_map.get(panel_id)

    def action_toggle_maximize(self) -> None:
        """Toggle maximize for the currently focused panel."""
        if self.maximized_panel:
            # Already maximized - restore
            self.action_restore_layout()
            return

        # Get focused panel
        panel_id = self._get_focused_panel_id()
        if not panel_id:
            self.notify("Focus a panel first (use Tab)", severity="warning")
            return

        self.maximized_panel = panel_id
        self.add_class("maximized-mode")

        # Get the section containing this panel
        panel_section = self._get_panel_section_id(panel_id)
        panel_cell = self._get_panel_cell_id(panel_id)

        # All main sections (rows in the grid)
        all_sections = ["timeline-section", "database-section", "watcher-actions-row", "bottom-row"]

        # Hide all sections except the one containing our panel
        for section_id in all_sections:
            if section_id != panel_section:
                try:
                    section = self.query_one(f"#{section_id}")
                    section.styles.display = "none"
                except Exception:
                    pass

        # KEY FIX: Change the screen's grid-rows to collapse hidden rows
        # Normal: auto 12 10 12 1fr auto auto (header, timeline, db, watcher, bottom, status, footer)
        # Maximized: auto 1fr auto auto (header, maximized-section, status, footer)
        self.styles.grid_rows = "auto 1fr auto auto"

        # Make the visible section expand to fill available space
        try:
            section = self.query_one(f"#{panel_section}")
            section.styles.height = "100%"
        except Exception:
            pass

        # If panel is in a split row, hide sibling and expand this cell
        if panel_cell:
            sibling_cells = {
                "watcher-cell": "action-cell",
                "action-cell": "watcher-cell",
                "source-files-cell": "activity-log-cell",
                "activity-log-cell": "source-files-cell",
            }
            sibling = sibling_cells.get(panel_cell)
            if sibling:
                try:
                    self.query_one(f"#{sibling}").styles.display = "none"
                except Exception:
                    pass
            # Make the row use single column
            try:
                row = self.query_one(f"#{panel_section}")
                row.styles.grid_size_columns = 1
            except Exception:
                pass

        self.notify(f"Maximized: {panel_id} (press 'm' or Escape to restore)")

    def action_restore_layout(self) -> None:
        """Restore the normal layout from maximized state."""
        if not self.maximized_panel:
            return

        self.maximized_panel = None
        self.remove_class("maximized-mode")

        # KEY FIX: Restore the screen's grid-rows to original value
        # Normal: auto 12 10 12 1fr auto auto (header, timeline, db, watcher, bottom, status, footer)
        self.styles.grid_rows = "auto 12 10 12 1fr auto auto"

        # Restore all sections - show them and reset height
        sections = ["timeline-section", "database-section", "watcher-actions-row", "bottom-row"]
        for section_id in sections:
            try:
                section = self.query_one(f"#{section_id}")
                section.styles.display = "block"
                section.styles.height = "100%"
            except Exception:
                pass

        # Restore all cells - show them
        cells = ["watcher-cell", "action-cell", "source-files-cell", "activity-log-cell"]
        for cell_id in cells:
            try:
                cell = self.query_one(f"#{cell_id}")
                cell.styles.display = "block"
            except Exception:
                pass

        # Restore grid columns for split rows
        for row_id in ["watcher-actions-row", "bottom-row"]:
            try:
                row = self.query_one(f"#{row_id}")
                row.styles.grid_size_columns = 2
            except Exception:
                pass

        self.notify("Layout restored")
