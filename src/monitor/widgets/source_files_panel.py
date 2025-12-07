"""
Source Files Panel Widget
=========================

Shows list of source files with last modified times for debugging.
"""

from datetime import datetime
from pathlib import Path
from typing import List, Optional
import os

from textual.widgets import Static
from textual.reactive import reactive
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from ..data_collector import DatabaseStats


class SourceFilesPanel(Static):
    """
    Panel showing source files and their last modified times.

    Helps debug whether files are being processed by showing:
    - File name
    - Last modified time
    - Size
    """

    database: reactive[DatabaseStats | None] = reactive(None)
    max_files: int = 15

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def _get_source_files(self, source_folder: str) -> List[dict]:
        """Get files from source folder with metadata."""
        files = []
        source_path = Path(source_folder)

        if not source_path.exists():
            return files

        try:
            # Get all files recursively
            for file_path in source_path.rglob('*'):
                if file_path.is_file():
                    try:
                        stat = file_path.stat()
                        files.append({
                            "name": file_path.name,
                            "path": str(file_path),
                            "size": stat.st_size,
                            "modified": datetime.fromtimestamp(stat.st_mtime),
                            "relative": str(file_path.relative_to(source_path))
                        })
                    except (OSError, PermissionError):
                        pass
        except (OSError, PermissionError):
            pass

        # Sort by modified time (most recent first)
        files.sort(key=lambda f: f["modified"], reverse=True)
        return files[:self.max_files]

    def _humanize_size(self, size_bytes: int) -> str:
        """Convert bytes to human readable."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if abs(size_bytes) < 1024.0:
                return f"{size_bytes:.0f}{unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.0f}TB"

    def _humanize_time(self, dt: datetime) -> str:
        """Convert datetime to relative time."""
        now = datetime.now()
        delta = now - dt

        if delta.total_seconds() < 60:
            return "just now"
        elif delta.total_seconds() < 3600:
            mins = int(delta.total_seconds() / 60)
            return f"{mins}m ago"
        elif delta.total_seconds() < 86400:
            hours = int(delta.total_seconds() / 3600)
            return f"{hours}h ago"
        else:
            days = delta.days
            return f"{days}d ago"

    def _render_empty(self) -> Panel:
        """Render when no database selected."""
        return Panel(
            Text("Select a database to view source files", style="dim italic"),
            title="Source Files",
            border_style="dim",
            box=None
        )

    def _render_files(self, db: DatabaseStats) -> Panel:
        """Render file list for database."""
        if not db.source_folder:
            return Panel(
                Text("No source folder configured", style="dim italic"),
                title=f"Source Files: {db.name}",
                border_style="dim",
                box=None
            )

        files = self._get_source_files(db.source_folder)

        if not files:
            return Panel(
                Text("No files found in source folder", style="dim italic"),
                title=f"Source Files: {db.name}",
                border_style="dim",
                box=None
            )

        table = Table(
            show_header=True,
            header_style="bold",
            expand=True,
            box=None,
            padding=(0, 1)
        )

        table.add_column("File", style="white", overflow="ellipsis", max_width=30)
        table.add_column("Modified", style="cyan", width=10)
        table.add_column("Size", style="dim", justify="right", width=8)

        for f in files:
            # Color based on recency
            mod_time = self._humanize_time(f["modified"])
            if "just now" in mod_time or "m ago" in mod_time:
                time_style = "green bold"
            elif "h ago" in mod_time:
                time_style = "yellow"
            else:
                time_style = "dim"

            table.add_row(
                f["name"][:30],
                Text(mod_time, style=time_style),
                self._humanize_size(f["size"])
            )

        # Summary
        source_short = db.source_folder
        if len(source_short) > 40:
            source_short = "..." + source_short[-37:]

        return Panel(
            table,
            title=f"Source Files ({len(files)} shown)",
            subtitle=f"[dim]{source_short}[/dim]",
            border_style="dim",
            box=None
        )

    def watch_database(self, database: DatabaseStats | None) -> None:
        """Called when database changes."""
        if database:
            self.update(self._render_files(database))
        else:
            self.update(self._render_empty())

    def on_mount(self) -> None:
        """Initialize with empty content."""
        self.update(self._render_empty())

    def refresh_files(self) -> None:
        """Refresh the file list."""
        if self.database:
            self.update(self._render_files(self.database))
