"""
Watcher Panel Widget
====================

Shows detailed watcher status for the selected database.
Enhanced to show KG stats, progress, file warnings matching `db show --stats`.
"""

from textual.widgets import Static
from textual.reactive import reactive
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.box import SIMPLE
from rich.progress_bar import ProgressBar
from rich.console import Group
from rich.columns import Columns

from ..data_collector import DatabaseStats


class WatcherPanel(Static, can_focus=True):
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
            box=SIMPLE
        )

    def _render_watcher(self, db: DatabaseStats) -> Panel:
        """Render watcher details for a database with KG stats and progress."""
        sections = []

        # --- Section 1: Watcher Status ---
        status_table = Table.grid(padding=(0, 2))
        status_table.add_column(style="bold cyan", width=12)
        status_table.add_column()

        # Status line
        if db.watcher_running:
            status = Text(f"🟢 Running", style="green bold")
            if db.watcher_pid:
                status.append(f" (PID {db.watcher_pid})", style="green")
        else:
            status = Text("⚪ Stopped", style="dim")

        status_table.add_row("Status:", status)

        # Mode
        if db.watcher_mode:
            mode_text = db.watcher_mode
        else:
            mode_text = "standalone" if db.watcher_running else "-"
        status_table.add_row("Mode:", mode_text)

        # Interval
        interval_min = db.watch_interval // 60
        interval_sec = db.watch_interval % 60
        if interval_sec:
            interval_str = f"{interval_min}m {interval_sec}s"
        else:
            interval_str = f"{interval_min}m"
        status_table.add_row("Interval:", f"{db.watch_interval}s ({interval_str})")

        # Source folder (truncated if long)
        if db.source_folder:
            source = db.source_folder
            if len(source) > 35:
                source = "..." + source[-32:]
            status_table.add_row("Source:", source)
        else:
            status_table.add_row("Source:", Text("-", style="dim"))

        # Auto-watch
        if db.auto_watch:
            auto_text = Text("✓ Enabled", style="green")
        else:
            auto_text = Text("✗ Disabled", style="dim")
        status_table.add_row("Auto-watch:", auto_text)

        sections.append(status_table)

        # --- Section 2: KG Stats (like db show --stats) ---
        if db.entity_count > 0 or db.relation_count > 0 or db.chunk_count > 0:
            sections.append(Text(""))  # Spacer
            sections.append(Text("📈 Knowledge Graph Stats", style="bold cyan"))

            kg_table = Table.grid(padding=(0, 2))
            kg_table.add_column(style="dim", width=12)
            kg_table.add_column(style="green", justify="right", width=10)

            kg_table.add_row("  Entities:", f"{db.entity_count:,}")
            kg_table.add_row("  Relations:", f"{db.relation_count:,}")
            kg_table.add_row("  Chunks:", f"{db.chunk_count:,}")
            kg_table.add_row("  Documents:", f"{db.document_count:,}")

            sections.append(kg_table)

        # --- Section 3: File Warnings ---
        if db.file_warnings:
            sections.append(Text(""))  # Spacer
            for warning in db.file_warnings[:3]:  # Limit to 3 warnings
                sections.append(Text(f"  ⚠️  {warning}", style="yellow"))

        # --- Section 4: Processing Progress ---
        progress = db.processing_progress
        if progress and (progress.get("current_chunk", 0) > 0 or progress.get("current_batch", 0) > 0):
            sections.append(Text(""))  # Spacer

            # Batch progress
            if progress.get("current_batch"):
                batch_cur = progress.get("current_batch", 0)
                batch_total = progress.get("total_batches", 0)
                batch_files = progress.get("batch_files", 0)
                sections.append(Text(f"📦 Batch {batch_cur}/{batch_total} ({batch_files} files)", style="cyan"))

            # Chunk progress with bar
            current = progress.get("current_chunk", 0)
            total = progress.get("total_chunks", 0)
            current_file = progress.get("current_file", "")

            if total > 0:
                pct = int((current / total) * 100)
                bar_filled = pct // 5  # 20 chars total
                bar_empty = 20 - bar_filled
                bar = f"[green]{'█' * bar_filled}[/green][dim]{'░' * bar_empty}[/dim]"
                sections.append(Text.from_markup(f"⏳ Chunks: {bar} {pct}% ({current:,}/{total:,})"))
                if current_file:
                    short_file = current_file[-30:] if len(current_file) > 30 else current_file
                    sections.append(Text(f"   → {short_file}", style="dim"))

        # --- Section 5: Processing Files ---
        if db.processing_files:
            sections.append(Text(""))  # Spacer
            sections.append(Text(f"⏳ Processing ({len(db.processing_files)} files):", style="yellow"))
            for f in db.processing_files[:3]:
                short_f = f[-35:] if len(f) > 35 else f
                sections.append(Text(f"   → {short_f}", style="dim yellow"))

        # --- Section 6: Recent Files ---
        if db.recent_files:
            sections.append(Text(""))  # Spacer
            sections.append(Text("📂 Recent Files:", style="bold cyan"))
            for f in db.recent_files[:5]:
                fname = f.get("filename", "?")[-30:]
                ts = f.get("timestamp", "")
                chunks = f.get("chunks", 0)
                status_icon = "✓" if f.get("status") == "processed" else "○"
                sections.append(Text(f"   {status_icon} {ts[:16]} {fname} ({chunks} chunks)", style="dim"))

        return Panel(
            Group(*sections),
            title=f"Watcher: {db.name}",
            border_style="dim",
            box=SIMPLE
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
