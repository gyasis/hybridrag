"""
Database Table Widget
=====================

DataTable widget showing all registered databases with their stats.
"""

from textual.widgets import DataTable
from textual.binding import Binding
from textual.message import Message
from rich.text import Text

from ..data_collector import DatabaseStats


class DatabaseTable(DataTable):
    """
    Interactive table displaying database information.

    Columns:
    - Name: Database name
    - Status: Health indicator (🟢/⚪/🔴)
    - Size: Total database size
    - Entities: Entity count
    - Relations: Relation count
    - Last Sync: Human-readable last sync time
    - Watcher: Watcher status indicator
    """

    BINDINGS = [
        Binding("up", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("enter", "select_cursor", "Select", show=False),
    ]

    class DatabaseSelected(Message):
        """Posted when a database is selected."""
        def __init__(self, database: DatabaseStats) -> None:
            self.database = database
            super().__init__()

    def __init__(self, **kwargs):
        super().__init__(
            cursor_type="row",
            zebra_stripes=True,
            **kwargs
        )
        self._databases: dict[str, DatabaseStats] = {}

    def on_mount(self) -> None:
        """Set up table columns."""
        self.add_column("Name", key="name", width=16)
        self.add_column("Status", key="status", width=8)
        self.add_column("Size", key="size", width=10)
        self.add_column("Entities", key="entities", width=10)
        self.add_column("Relations", key="relations", width=10)
        self.add_column("Last Sync", key="sync", width=14)
        self.add_column("Watcher", key="watcher", width=12)

    def update_databases(self, databases: list[DatabaseStats]) -> None:
        """Update table with new database stats."""
        # Remember currently selected database before clearing
        selected_db_name = None
        if self.cursor_row is not None and self.row_count > 0:
            try:
                row_key = self.get_row_at(self.cursor_row)
                if row_key:
                    selected_db_name = row_key.value
            except Exception:
                pass

        # Store for later access
        self._databases = {db.name: db for db in databases}

        # Clear and repopulate
        self.clear()

        selected_row_index = None
        for idx, db in enumerate(databases):
            # Status icon
            if not db.exists:
                status = Text("🔴 GONE", style="red")
            elif not db.healthy:
                status = Text("⚠️ ERR", style="yellow")
            elif db.watcher_running:
                status = Text("🟢 UP", style="green")
            else:
                status = Text("⚪ --", style="dim")

            # Watcher column
            if db.watcher_running:
                watcher = Text(f"🟢 {db.watcher_pid}", style="green")
            elif db.auto_watch:
                watcher = Text("⏸ auto", style="yellow")
            else:
                watcher = Text("⚪ off", style="dim")

            # Format numbers
            entities = f"{db.entity_count:,}" if db.entity_count else "-"
            relations = f"{db.relation_count:,}" if db.relation_count else "-"

            # Track index if this is the previously selected database
            if db.name == selected_db_name:
                selected_row_index = idx

            self.add_row(
                db.name,
                status,
                db.total_size_human,
                entities,
                relations,
                db.last_sync_human,
                watcher,
                key=db.name
            )

        # Restore cursor position to previously selected database
        if selected_row_index is not None and self.row_count > 0:
            self.move_cursor(row=selected_row_index)
        elif self.row_count > 0:
            # Auto-select first database if none was selected
            self.move_cursor(row=0)

        # Get the database directly from the index since cursor_row may not be updated yet
        target_row = selected_row_index if selected_row_index is not None else 0
        if databases and target_row < len(databases):
            db = databases[target_row]
            self.post_message(self.DatabaseSelected(db))

    def get_selected_database(self) -> DatabaseStats | None:
        """Get the currently selected database."""
        if self.cursor_row is not None and self.row_count > 0:
            row_key = self.get_row_at(self.cursor_row)
            if row_key and row_key.value in self._databases:
                return self._databases[row_key.value]
        return None

    def action_select_cursor(self) -> None:
        """Handle row selection."""
        db = self.get_selected_database()
        if db:
            self.post_message(self.DatabaseSelected(db))

    def watch_cursor_row(self, old_value: int | None, new_value: int | None) -> None:
        """Called when cursor row changes."""
        db = self.get_selected_database()
        if db:
            self.post_message(self.DatabaseSelected(db))
