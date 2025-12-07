"""
Action Panel Widget
===================

Shows available keyboard shortcuts and actions.
"""

from textual.widgets import Static
from textual.reactive import reactive
from rich.panel import Panel
from rich.text import Text
from rich.table import Table

from ..data_collector import DatabaseStats


class ActionPanel(Static):
    """
    Panel showing available actions for the selected database.

    Updates based on current context:
    - Different actions when watcher running vs stopped
    - Different actions based on database type
    """

    database: reactive[DatabaseStats | None] = reactive(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def _render_actions(self, db: DatabaseStats | None) -> Panel:
        """Render available actions."""
        table = Table.grid(padding=(0, 1))
        table.add_column(style="bold yellow", width=4)
        table.add_column()

        # Database management actions
        table.add_row("[n]", "New database (wizard)")
        if db:
            table.add_row("[e]", "Edit settings")
            table.add_row("[d]", "Delete database")
            table.add_row("─", "─" * 22)

            # Watcher actions
            if db.watcher_running:
                table.add_row("[x]", Text("Stop watcher", style="red"))
            else:
                table.add_row("[s]", Text("Start watcher", style="green"))

            table.add_row("[y]", "Force sync")

            if db.auto_watch:
                table.add_row("[a]", "Disable auto-watch")
            else:
                table.add_row("[a]", "Enable auto-watch")

            table.add_row("─", "─" * 22)
            table.add_row("[l]", "View logs")
            table.add_row("[t]", "Toggle log scope")
            table.add_row("[i]", "Database info")
        else:
            table.add_row("", "")
            table.add_row("", Text("Select a database", style="dim italic"))
            table.add_row("", Text("to see more actions", style="dim italic"))

        table.add_row("─", "─" * 22)
        table.add_row("[r]", "Refresh")
        table.add_row("[q]", "Quit")

        return Panel(
            table,
            title="[bold]Actions[/bold]",
            border_style="blue"
        )

    def watch_database(self, database: DatabaseStats | None) -> None:
        """Called when database reactive changes."""
        self.update(self._render_actions(database))

    def on_mount(self) -> None:
        """Initialize with default actions."""
        self.update(self._render_actions(None))
