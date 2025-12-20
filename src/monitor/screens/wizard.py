"""
Database Setup Wizard Screen
============================

Multi-step wizard for creating new databases.
"""

from pathlib import Path
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import (
    Static, Button, Input, Select, Checkbox,
    TextArea, Label
)
from textual.containers import Container, Horizontal, ScrollableContainer
from textual.binding import Binding
from textual.message import Message
from textual.reactive import reactive

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.database_registry import get_registry
from src.monitor.presets import PRESETS, get_preset


class WizardStep(Static):
    """Base class for wizard steps."""

    step_number: int = 0
    step_title: str = "Step"

    def is_valid(self) -> bool:
        """Check if this step's input is valid."""
        return True

    def get_values(self) -> dict:
        """Get values from this step."""
        return {}


class StepDatabaseName(WizardStep):
    """Step 1: Database name input."""

    step_number = 1
    step_title = "Database Name"

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold]Step 1 of 5: Database Name[/bold]\n"
            "Enter a name for your database (lowercase, alphanumeric, hyphens):",
            classes="step-description"
        )
        yield Input(
            placeholder="my-project-docs",
            id="db_name",
            validators=[]
        )
        yield Static("", id="name_error", classes="error-text")

    def is_valid(self) -> bool:
        name_input = self.query_one("#db_name", Input)
        name = name_input.value.strip().lower()

        error_widget = self.query_one("#name_error", Static)

        if not name:
            error_widget.update("[red]Name is required[/red]")
            return False

        # BUG-001 fix: Check for lowercase explicitly (not just alphanumeric)
        if not all(c.islower() or c.isdigit() or c == '-' for c in name):
            error_widget.update("[red]Only lowercase letters, numbers, and hyphens allowed[/red]")
            return False

        if name.startswith('-') or name.endswith('-'):
            error_widget.update("[red]Cannot start or end with hyphen[/red]")
            return False

        # Check if name already exists
        registry = get_registry()
        if registry.exists(name):
            error_widget.update(f"[red]Database '{name}' already exists[/red]")
            return False

        error_widget.update("")
        return True

    def get_values(self) -> dict:
        name_input = self.query_one("#db_name", Input)
        return {"name": name_input.value.strip().lower()}


class StepLocation(WizardStep):
    """Step 2: Database storage location."""

    step_number = 2
    step_title = "Database Location"

    DEFAULT_KEY = "default"

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold]Step 2 of 5: Database Location[/bold]\n"
            "Where should the database files be stored?",
            classes="step-description"
        )

        yield Checkbox("Use default location (~/.hybridrag/databases/)", value=True, id="use_default")
        yield Input(
            placeholder="/path/to/database",
            id="custom_path",
            disabled=True
        )
        yield Static("", id="path_error", classes="error-text")

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if event.checkbox.id == "use_default":
            path_input = self.query_one("#custom_path", Input)
            path_input.disabled = event.value

    def is_valid(self) -> bool:
        use_default = self.query_one("#use_default", Checkbox).value
        error_widget = self.query_one("#path_error", Static)

        if not use_default:
            path_input = self.query_one("#custom_path", Input)
            path = path_input.value.strip()

            if not path:
                error_widget.update("[red]Path is required when not using default[/red]")
                return False

            # Check if parent directory exists
            parent = Path(path).expanduser().parent
            if not parent.exists():
                error_widget.update(f"[yellow]Parent directory will be created: {parent}[/yellow]")

        error_widget.update("")
        return True

    def get_values(self) -> dict:
        use_default = self.query_one("#use_default", Checkbox).value

        if use_default:
            return {"path": None}  # Will be set based on name later

        path_input = self.query_one("#custom_path", Input)
        return {"path": path_input.value.strip()}


class StepSourceFolder(WizardStep):
    """Step 3: Source folder to watch."""

    step_number = 3
    step_title = "Source Folder"

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold]Step 3 of 5: Source Folder[/bold]\n"
            "What folder should be watched for files to ingest?",
            classes="step-description"
        )

        yield Input(
            placeholder="/home/user/dev/my-project",
            id="source_folder"
        )
        yield Static("", id="source_error", classes="error-text")

        yield Static("\n[bold]Scan Options:[/bold]")
        yield Checkbox("Recursive (include subfolders)", value=True, id="recursive")
        yield Checkbox("Follow symlinks", value=False, id="follow_symlinks")

        yield Horizontal(
            Label("Max depth: "),
            Input(value="10", id="max_depth", type="integer"),
            classes="input-row"
        )

    def is_valid(self) -> bool:
        source_input = self.query_one("#source_folder", Input)
        source = source_input.value.strip()
        error_widget = self.query_one("#source_error", Static)

        if not source:
            error_widget.update("[red]Source folder is required[/red]")
            return False

        path = Path(source).expanduser()
        if not path.exists():
            error_widget.update(f"[red]Folder does not exist: {source}[/red]")
            return False

        if not path.is_dir():
            error_widget.update("[red]Path is not a directory[/red]")
            return False

        error_widget.update("")
        return True

    def get_values(self) -> dict:
        source = self.query_one("#source_folder", Input).value.strip()
        recursive = self.query_one("#recursive", Checkbox).value

        return {
            "source_folder": str(Path(source).expanduser()),
            "recursive": recursive,
        }


class StepPatterns(WizardStep):
    """Step 4: File patterns."""

    step_number = 4
    step_title = "File Patterns"

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold]Step 4 of 5: File Patterns[/bold]\n"
            "Which files should be ingested?",
            classes="step-description"
        )

        # Preset selector
        preset_options = [(p.display_name, p.name) for p in PRESETS.values()]
        yield Horizontal(
            Label("Preset: "),
            Select(preset_options, value="documentation", id="preset_select"),
            classes="input-row"
        )

        yield Static("\n[bold]Include patterns[/bold] (one per line):")
        yield TextArea(
            "**/*.md\n**/*.txt",
            id="include_patterns",
            classes="pattern-input"
        )

        yield Static("\n[bold]Exclude patterns[/bold] (one per line):")
        yield TextArea(
            "node_modules/**\n.git/**\n__pycache__/**",
            id="exclude_patterns",
            classes="pattern-input"
        )

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "preset_select":
            preset = get_preset(event.value)
            if preset:
                include_area = self.query_one("#include_patterns", TextArea)
                exclude_area = self.query_one("#exclude_patterns", TextArea)

                include_area.load_text("\n".join(preset.include_patterns))
                exclude_area.load_text("\n".join(preset.exclude_patterns))

    def is_valid(self) -> bool:
        # Patterns are optional
        return True

    def get_values(self) -> dict:
        preset_select = self.query_one("#preset_select", Select)
        include_area = self.query_one("#include_patterns", TextArea)
        exclude_area = self.query_one("#exclude_patterns", TextArea)

        include = [p.strip() for p in include_area.text.split("\n") if p.strip()]
        exclude = [p.strip() for p in exclude_area.text.split("\n") if p.strip()]

        preset = get_preset(str(preset_select.value))
        source_type = preset.source_type if preset else "filesystem"

        return {
            "preset": str(preset_select.value),
            "include_patterns": include,
            "exclude_patterns": exclude,
            "source_type": source_type,
        }


class StepWatcher(WizardStep):
    """Step 5: Watcher settings."""

    step_number = 5
    step_title = "Watcher Settings"

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold]Step 5 of 5: Watcher Settings[/bold]\n",
            classes="step-description"
        )

        yield Checkbox("Enable auto-watch (automatically start watcher)", value=True, id="auto_watch")

        yield Horizontal(
            Label("Watch interval (seconds): "),
            Input(value="300", id="interval", type="integer"),
            classes="input-row"
        )

        yield Static("\n[bold]Model:[/bold]")
        yield Checkbox("Use default model", value=True, id="use_default_model")
        yield Input(placeholder="azure/gpt-4o", id="custom_model", disabled=True)

        # BUG-009 fix: Add backend selection
        yield Static("\n[bold]Storage Backend:[/bold]")
        backend_options = [
            ("JSON (File-based)", "json"),
            ("PostgreSQL (pgvector)", "postgres"),
        ]
        yield Horizontal(
            Label("Backend: "),
            Select(backend_options, value="json", id="backend_select"),
            classes="input-row"
        )
        yield Input(
            placeholder="postgresql://user:pass@localhost:5432/hybridrag",
            id="pg_connection",
            disabled=True
        )
        yield Static("", id="backend_error", classes="error-text")

        yield Static("\n[bold]Description:[/bold]")
        yield Input(placeholder="Optional description for this database", id="description")

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if event.checkbox.id == "use_default_model":
            model_input = self.query_one("#custom_model", Input)
            model_input.disabled = event.value

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "backend_select":
            pg_input = self.query_one("#pg_connection", Input)
            pg_input.disabled = event.value != "postgres"

    def is_valid(self) -> bool:
        interval_input = self.query_one("#interval", Input)
        try:
            interval = int(interval_input.value)
            if interval < 10:
                return False
        except ValueError:
            return False

        # Validate PostgreSQL connection string if selected
        backend_select = self.query_one("#backend_select", Select)
        error_widget = self.query_one("#backend_error", Static)

        if backend_select.value == "postgres":
            pg_input = self.query_one("#pg_connection", Input)
            conn_str = pg_input.value.strip()
            if not conn_str:
                error_widget.update("[red]PostgreSQL connection string required[/red]")
                return False
            if not conn_str.startswith("postgresql://"):
                error_widget.update("[red]Connection string must start with postgresql://[/red]")
                return False
            error_widget.update("")

        return True

    def get_values(self) -> dict:
        auto_watch = self.query_one("#auto_watch", Checkbox).value
        interval = int(self.query_one("#interval", Input).value)
        use_default_model = self.query_one("#use_default_model", Checkbox).value
        model = None if use_default_model else self.query_one("#custom_model", Input).value.strip()
        description = self.query_one("#description", Input).value.strip()

        # Backend configuration
        backend_select = self.query_one("#backend_select", Select)
        backend_type = str(backend_select.value)
        backend_config = None

        if backend_type == "postgres":
            pg_input = self.query_one("#pg_connection", Input)
            backend_config = {"connection_string": pg_input.value.strip()}

        return {
            "auto_watch": auto_watch,
            "watch_interval": interval,
            "model": model if model else None,
            "description": description if description else None,
            "backend_type": backend_type,
            "backend_config": backend_config,
        }


class WizardScreen(Screen):
    """
    Multi-step wizard screen for creating new databases.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "next_step", "Next", show=False),
    ]

    CSS = """
    WizardScreen {
        align: center middle;
    }

    #wizard-container {
        width: 80%;
        max-width: 100;
        height: auto;
        max-height: 90%;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }

    .step-description {
        margin-bottom: 1;
    }

    .error-text {
        color: $error;
        margin-top: 1;
    }

    .input-row {
        margin-top: 1;
        height: 3;
    }

    .pattern-input {
        height: 6;
        margin-top: 1;
    }

    #button-row {
        margin-top: 2;
        height: 3;
        align: right middle;
    }

    #button-row Button {
        margin-left: 1;
    }
    """

    current_step: reactive[int] = reactive(1)

    class WizardComplete(Message):
        """Posted when wizard completes successfully."""
        def __init__(self, db_name: str) -> None:
            self.db_name = db_name
            super().__init__()

    class WizardCancelled(Message):
        """Posted when wizard is cancelled."""
        pass

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._values: dict = {}

    def compose(self) -> ComposeResult:
        yield Container(
            Static("🧙 [bold]HybridRAG Setup Wizard[/bold]", id="wizard-title"),
            ScrollableContainer(
                StepDatabaseName(id="step1"),
                StepLocation(id="step2", classes="hidden"),
                StepSourceFolder(id="step3", classes="hidden"),
                StepPatterns(id="step4", classes="hidden"),
                StepWatcher(id="step5", classes="hidden"),
                id="step-container"
            ),
            Horizontal(
                Button("Cancel", id="cancel-btn", variant="error"),
                Button("Back", id="back-btn", disabled=True),
                Button("Next", id="next-btn", variant="primary"),
                id="button-row"
            ),
            id="wizard-container"
        )

    def _get_current_step(self) -> WizardStep:
        """Get the current step widget."""
        return self.query_one(f"#step{self.current_step}", WizardStep)

    def _show_step(self, step_num: int) -> None:
        """Show a specific step and hide others."""
        for i in range(1, 6):
            step = self.query_one(f"#step{i}", WizardStep)
            if i == step_num:
                step.remove_class("hidden")
            else:
                step.add_class("hidden")

        # Update button states
        back_btn = self.query_one("#back-btn", Button)
        next_btn = self.query_one("#next-btn", Button)

        back_btn.disabled = step_num == 1
        next_btn.label = "Create" if step_num == 5 else "Next"

    def watch_current_step(self, step: int) -> None:
        """Called when current step changes."""
        self._show_step(step)

    def action_next_step(self) -> None:
        """Move to next step or complete wizard."""
        self._on_next()

    def action_cancel(self) -> None:
        """Cancel the wizard."""
        self.post_message(self.WizardCancelled())
        self.app.pop_screen()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.action_cancel()
        elif event.button.id == "back-btn":
            if self.current_step > 1:
                self.current_step -= 1
        elif event.button.id == "next-btn":
            self._on_next()

    def _on_next(self) -> None:
        """Handle next button press."""
        current = self._get_current_step()

        if not current.is_valid():
            return

        # Store values from current step
        self._values.update(current.get_values())

        if self.current_step < 5:
            self.current_step += 1
        else:
            # Complete wizard
            self._create_database()

    def _create_database(self) -> None:
        """Create the database from collected values."""
        try:
            registry = get_registry()

            # Set default path if needed
            if self._values.get("path") is None:
                default_dir = Path.home() / ".hybridrag" / "databases" / self._values["name"]
                self._values["path"] = str(default_dir)

            # BUG-002 fix: Normalize paths consistently using Path.expanduser().resolve()
            path = str(Path(self._values["path"]).expanduser().resolve())
            source_folder = self._values.get("source_folder")
            if source_folder:
                source_folder = str(Path(source_folder).expanduser().resolve())

            # BUG-004 fix: Extract file_extensions from include_patterns
            file_extensions = None
            include_patterns = self._values.get("include_patterns", [])
            if include_patterns:
                # Extract extensions from patterns like "**/*.md", "**/*.txt"
                extensions = []
                for pattern in include_patterns:
                    if "*." in pattern:
                        ext = pattern.split("*.")[-1]
                        # Handle patterns like "*.{md,txt}" or clean extensions
                        if ext and not any(c in ext for c in "{},/\\"):
                            ext = "." + ext if not ext.startswith(".") else ext
                            extensions.append(ext)
                if extensions:
                    file_extensions = extensions

            # Create database entry (BUG-009 fix: include backend_type and backend_config)
            registry.register(
                name=self._values["name"],
                path=path,
                source_folder=source_folder,
                source_type=self._values.get("source_type", "filesystem"),
                auto_watch=self._values.get("auto_watch", False),
                watch_interval=self._values.get("watch_interval", 300),
                model=self._values.get("model"),
                recursive=self._values.get("recursive", True),
                file_extensions=file_extensions,
                description=self._values.get("description"),
                backend_type=self._values.get("backend_type", "json"),
                backend_config=self._values.get("backend_config"),
            )

            # Post success message and close
            self.post_message(self.WizardComplete(self._values["name"]))
            self.app.pop_screen()

        except Exception as e:
            self.notify(f"Error creating database: {e}", severity="error")
