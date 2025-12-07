"""
Alerts Panel Widget
===================

Displays system alerts with severity indicators and acknowledgement controls.
"""

from datetime import datetime
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Static, Button, DataTable
from textual.reactive import reactive
from rich.text import Text
from rich.panel import Panel
from rich.table import Table

from src.alerting import get_alert_manager, Alert, AlertSeverity


class AlertsPanel(Static):
    """Panel displaying system alerts."""

    DEFAULT_CSS = """
    AlertsPanel {
        height: 100%;
        border: solid $primary;
    }

    AlertsPanel .alerts-header {
        dock: top;
        height: 3;
        padding: 0 1;
        background: $surface;
    }

    AlertsPanel .alerts-content {
        height: 100%;
        overflow-y: auto;
    }

    AlertsPanel .alert-critical {
        background: $error 30%;
        border-left: thick $error;
    }

    AlertsPanel .alert-error {
        background: $warning 20%;
        border-left: thick $warning;
    }

    AlertsPanel .alert-warning {
        background: $warning 10%;
        border-left: thick $warning-darken-2;
    }

    AlertsPanel .alert-info {
        border-left: thick $primary;
    }

    AlertsPanel .ack-button {
        min-width: 5;
        height: 1;
    }
    """

    alerts_count = reactive(0)

    def __init__(self, database: str = None, **kwargs):
        super().__init__(**kwargs)
        self.database = database
        self.alert_manager = get_alert_manager()

    def compose(self) -> ComposeResult:
        with Vertical():
            with Horizontal(classes="alerts-header"):
                yield Static("⚠️ Alerts", id="alerts-title")
                yield Button("Ack All", id="ack-all-btn", variant="warning", classes="ack-button")
                yield Button("🔄", id="refresh-alerts-btn", classes="ack-button")
            yield Static(id="alerts-content", classes="alerts-content")

    def on_mount(self) -> None:
        """Load alerts on mount."""
        self.refresh_alerts()
        # Auto-refresh every 30 seconds
        self.set_interval(30, self.refresh_alerts)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "ack-all-btn":
            self.alert_manager.acknowledge_all(self.database)
            self.refresh_alerts()
        elif event.button.id == "refresh-alerts-btn":
            self.refresh_alerts()

    def refresh_alerts(self) -> None:
        """Refresh the alerts display."""
        alerts = self.alert_manager.get_alerts(
            database=self.database,
            include_acknowledged=False
        )
        self.alerts_count = len(alerts)

        # Update title with count
        title = self.query_one("#alerts-title", Static)
        summary = self.alert_manager.get_summary()

        severity_icons = []
        if summary["critical"] > 0:
            severity_icons.append(f"🔴 {summary['critical']}")
        if summary["error"] > 0:
            severity_icons.append(f"🟠 {summary['error']}")
        if summary["warning"] > 0:
            severity_icons.append(f"🟡 {summary['warning']}")
        if summary["info"] > 0:
            severity_icons.append(f"🔵 {summary['info']}")

        if severity_icons:
            title.update(f"⚠️ Alerts ({' '.join(severity_icons)})")
        else:
            title.update("✅ No Alerts")

        # Build alerts display
        content = self.query_one("#alerts-content", Static)

        if not alerts:
            content.update(Panel(
                "[green]No active alerts[/green]\n\nAll systems operating normally.",
                title="Status",
                border_style="green"
            ))
            return

        # Sort by severity (critical first) then by timestamp (newest first)
        severity_order = {
            AlertSeverity.CRITICAL: 0,
            AlertSeverity.ERROR: 1,
            AlertSeverity.WARNING: 2,
            AlertSeverity.INFO: 3,
        }
        alerts.sort(key=lambda a: (severity_order.get(a.severity, 99), -a.timestamp.timestamp()))

        # Build rich text for each alert
        lines = []
        for alert in alerts[:20]:  # Show max 20 alerts
            severity_icon = {
                AlertSeverity.CRITICAL: "🔴",
                AlertSeverity.ERROR: "🟠",
                AlertSeverity.WARNING: "🟡",
                AlertSeverity.INFO: "🔵",
            }.get(alert.severity, "⚪")

            severity_style = {
                AlertSeverity.CRITICAL: "bold red",
                AlertSeverity.ERROR: "bold yellow",
                AlertSeverity.WARNING: "yellow",
                AlertSeverity.INFO: "blue",
            }.get(alert.severity, "white")

            time_str = alert.timestamp.strftime("%H:%M:%S")

            line = Text()
            line.append(f"{severity_icon} ", style=severity_style)
            line.append(f"[{time_str}] ", style="dim")
            line.append(f"[{alert.database}] ", style="cyan")
            line.append(alert.message, style=severity_style)
            lines.append(line)

        if len(alerts) > 20:
            lines.append(Text(f"\n... and {len(alerts) - 20} more alerts", style="dim"))

        content.update(Panel(
            "\n".join(str(line) for line in lines),
            title=f"Active Alerts ({len(alerts)})",
            border_style="yellow"
        ))

    def set_database(self, database: str) -> None:
        """Set the database filter and refresh."""
        self.database = database
        self.refresh_alerts()


class AlertsSummaryWidget(Static):
    """Compact alerts summary for status bar."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.alert_manager = get_alert_manager()

    def on_mount(self) -> None:
        """Start refresh timer."""
        self.refresh_summary()
        self.set_interval(10, self.refresh_summary)

    def refresh_summary(self) -> None:
        """Update the summary display."""
        summary = self.alert_manager.get_summary()

        if summary["total"] == 0:
            self.update("✅")
            return

        parts = []
        if summary["critical"] > 0:
            parts.append(f"🔴{summary['critical']}")
        if summary["error"] > 0:
            parts.append(f"🟠{summary['error']}")
        if summary["warning"] > 0:
            parts.append(f"🟡{summary['warning']}")

        self.update(" ".join(parts) if parts else f"🔵{summary['info']}")
