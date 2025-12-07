"""
HybridRAG Monitor Application
=============================

Main Textual application for the HybridRAG monitoring dashboard.
"""

from pathlib import Path
import sys
import atexit

from textual.app import App
from textual.binding import Binding

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def _reset_terminal_mouse():
    """Reset terminal mouse tracking modes on exit."""
    try:
        # Disable all mouse tracking escape sequences
        sys.stdout.write('\x1b[?1000l')  # Disable mouse click tracking
        sys.stdout.write('\x1b[?1002l')  # Disable mouse button tracking
        sys.stdout.write('\x1b[?1003l')  # Disable all mouse tracking
        sys.stdout.write('\x1b[?1006l')  # Disable SGR mouse mode
        sys.stdout.write('\x1b[?1015l')  # Disable urxvt mouse mode
        sys.stdout.flush()
    except Exception:
        pass  # Ignore errors if stdout is already closed

from src.monitor.screens.dashboard import DashboardScreen
from src.monitor.screens.wizard import WizardScreen


class HybridRAGMonitor(App):
    """
    HybridRAG Monitor - Interactive TUI for managing databases and watchers.

    Features:
    - Real-time dashboard showing database health, watcher status, live logs
    - Interactive wizard for creating new databases
    - Watcher controls (start/stop, toggle auto-watch, force sync)
    - Pattern presets for common use cases
    """

    TITLE = "HybridRAG Monitor"
    SUB_TITLE = "Database & Watcher Management"

    # Disable mouse to prevent terminal lock-up issues in WSL/some terminals
    ENABLE_COMMAND_PALETTE = False

    CSS = """
    Screen {
        background: $surface;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=False),
        Binding("ctrl+q", "quit", "Quit", show=False),
    ]

    def __init__(
        self,
        refresh_interval: int = 2,
        start_wizard: bool = False,
        **kwargs
    ):
        """
        Initialize the monitor application.

        Args:
            refresh_interval: Seconds between auto-refresh (default: 2)
            start_wizard: If True, open wizard immediately instead of dashboard
        """
        super().__init__(**kwargs)
        self.refresh_interval = refresh_interval
        self.start_wizard = start_wizard

    def on_mount(self) -> None:
        """Called when app is mounted."""
        if self.start_wizard:
            # Start with wizard screen
            self.push_screen(WizardScreen())
        else:
            # Start with dashboard
            self.push_screen(DashboardScreen(refresh_interval=self.refresh_interval))

    def on_wizard_screen_wizard_complete(self, event: WizardScreen.WizardComplete) -> None:
        """Handle wizard completion - switch to dashboard."""
        self.notify(f"✓ Database '{event.db_name}' created successfully!", severity="information")
        # Dashboard will auto-refresh and show the new database

    def on_wizard_screen_wizard_cancelled(self, event: WizardScreen.WizardCancelled) -> None:
        """Handle wizard cancellation."""
        self.notify("Database creation cancelled", severity="warning")


def run_monitor(refresh_interval: int = 2, start_wizard: bool = False, mouse: bool = False) -> None:
    """
    Run the HybridRAG monitor application.

    Args:
        refresh_interval: Seconds between auto-refresh (default: 2)
        start_wizard: If True, open wizard immediately
        mouse: Enable mouse support (default: False to prevent terminal lock-up)
    """
    # Register cleanup to ensure mouse tracking is disabled on exit
    atexit.register(_reset_terminal_mouse)

    app = HybridRAGMonitor(
        refresh_interval=refresh_interval,
        start_wizard=start_wizard
    )
    try:
        # Disable mouse to prevent terminal lock-up in WSL/some terminals
        app.run(mouse=mouse)
    finally:
        # Also call directly in case atexit doesn't fire
        _reset_terminal_mouse()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="HybridRAG Monitor")
    parser.add_argument(
        "--refresh", "-r",
        type=int,
        default=2,
        help="Refresh interval in seconds (default: 2)"
    )
    parser.add_argument(
        "--new", "-n",
        action="store_true",
        help="Start with new database wizard"
    )
    parser.add_argument(
        "--mouse", "-m",
        action="store_true",
        help="Enable mouse support (disabled by default to prevent terminal issues)"
    )

    args = parser.parse_args()
    run_monitor(refresh_interval=args.refresh, start_wizard=args.new, mouse=args.mouse)
