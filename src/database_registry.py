#!/usr/bin/env python3
"""
Database Registry Management
=============================
Centralized registry for tracking all HybridRAG database instances.
Stores database configurations in ~/.hybridrag/registry.yaml with
support for config pointers to alternate locations.

Supports multiple source types:
- filesystem: Standard folder watching
- specstory: SpecStory AI conversation histories (JIRA-linked)
- api: Data sourced from REST APIs (Confluence, Jira, etc.)
- schema: Database schema extraction (Snowflake, Athena, etc.)
"""

import os
import re
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Literal
from datetime import datetime
from enum import Enum

import yaml


# Database naming pattern: alphanumeric + hyphens, must start/end with alphanumeric
DATABASE_NAME_PATTERN = re.compile(r'^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$')


class SourceType(str, Enum):
    """Types of data sources for databases."""
    FILESYSTEM = "filesystem"      # Standard folder watching
    SPECSTORY = "specstory"        # SpecStory AI conversation files
    API = "api"                    # REST API sources (Confluence, Jira)
    SCHEMA = "schema"              # Database schema extraction


@dataclass
class SpecStoryConfig:
    """Configuration for SpecStory-type databases."""
    jira_project_key: Optional[str] = None  # e.g., "PROJ"
    specstory_file_pattern: str = r".*\.specstory$"
    extract_conversations: bool = True
    jira_api_url: Optional[str] = None  # For JIRA enrichment
    folder_pattern: str = r"^[A-Z]+-\d+$"  # JIRA ticket folder naming

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SpecStoryConfig':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class APIConfig:
    """Configuration for API-type databases."""
    api_url: str
    auth_type: Literal["none", "basic", "oauth2", "api_key"] = "none"
    auth_config: Optional[Dict[str, str]] = None
    api_params: Optional[Dict[str, Any]] = None
    data_path: Optional[str] = None  # JSON path to data
    extraction_strategy: Literal["full_text", "metadata_only", "custom"] = "full_text"

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'APIConfig':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class SchemaConfig:
    """Configuration for Schema-type databases."""
    db_type: Literal["snowflake", "athena", "postgres", "mysql"] = "snowflake"
    connection_name: Optional[str] = None  # Named connection (e.g., snowsql connection)
    schema_name: Optional[str] = None
    table_patterns: Optional[List[str]] = None
    column_inclusion_rules: Optional[Dict[str, List[str]]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SchemaConfig':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class DatabaseEntry:
    """Configuration for a registered database."""

    name: str
    path: str
    source_folder: Optional[str] = None  # Optional for API/Schema types
    source_type: str = "filesystem"  # filesystem, specstory, api, schema
    auto_watch: bool = False
    watch_interval: int = 300  # seconds
    model: Optional[str] = None
    recursive: bool = True
    file_extensions: Optional[List[str]] = None
    preprocessing_pipeline: Optional[List[str]] = None  # Ordered list of preprocessors
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_sync: Optional[str] = None
    description: Optional[str] = None

    # Type-specific configurations (stored as dicts, converted on access)
    specstory_config: Optional[Dict[str, Any]] = None
    api_config: Optional[Dict[str, Any]] = None
    schema_config: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        """Validate and normalize fields."""
        # Normalize paths to absolute (if provided)
        self.path = str(Path(self.path).expanduser().resolve())
        if self.source_folder:
            self.source_folder = str(Path(self.source_folder).expanduser().resolve())

        # Validate name
        if not DATABASE_NAME_PATTERN.match(self.name):
            raise ValueError(
                f"Invalid database name '{self.name}'. "
                "Must be lowercase alphanumeric with hyphens only, "
                "starting and ending with alphanumeric character."
            )

        # Validate source_type
        valid_types = [t.value for t in SourceType]
        if self.source_type not in valid_types:
            raise ValueError(f"Invalid source_type '{self.source_type}'. Must be one of: {valid_types}")

        # Set default preprocessing pipelines based on source type
        if self.preprocessing_pipeline is None:
            self._set_default_preprocessing()

    def _set_default_preprocessing(self):
        """Set default preprocessing pipeline based on source type."""
        defaults = {
            SourceType.FILESYSTEM.value: None,
            SourceType.SPECSTORY.value: ["specstory_conversation_extraction"],
            SourceType.API.value: ["api_response_extraction"],
            SourceType.SCHEMA.value: ["schema_documentation_extraction"],
        }
        self.preprocessing_pipeline = defaults.get(self.source_type)

    def get_specstory_config(self) -> Optional[SpecStoryConfig]:
        """Get typed SpecStory configuration."""
        if self.specstory_config:
            return SpecStoryConfig.from_dict(self.specstory_config)
        return None

    def get_api_config(self) -> Optional[APIConfig]:
        """Get typed API configuration."""
        if self.api_config:
            return APIConfig.from_dict(self.api_config)
        return None

    def get_schema_config(self) -> Optional[SchemaConfig]:
        """Get typed Schema configuration."""
        if self.schema_config:
            return SchemaConfig.from_dict(self.schema_config)
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for YAML storage."""
        data = asdict(self)
        # Remove None values for cleaner YAML
        return {k: v for k, v in data.items() if v is not None}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DatabaseEntry':
        """Create from dictionary (YAML load)."""
        return cls(**data)

    def update_last_sync(self) -> None:
        """Update last_sync to current time."""
        self.last_sync = datetime.now().isoformat()


class DatabaseRegistry:
    """
    Manages the centralized database registry.

    Registry location priority:
    1. HYBRIDRAG_CONFIG environment variable
    2. ~/.hybridrag/config_pointer file contents
    3. ~/.hybridrag/registry.yaml (default)
    """

    DEFAULT_DIR = Path.home() / ".hybridrag"
    DEFAULT_REGISTRY = DEFAULT_DIR / "registry.yaml"
    CONFIG_POINTER = DEFAULT_DIR / "config_pointer"
    ENV_VAR = "HYBRIDRAG_CONFIG"

    def __init__(self, registry_path: Optional[str] = None):
        """
        Initialize the registry.

        Args:
            registry_path: Optional explicit path to registry file.
                          If not provided, uses priority-based resolution.
        """
        if registry_path:
            self.registry_path = Path(registry_path).expanduser().resolve()
        else:
            self.registry_path = self._resolve_registry_path()

        self._ensure_registry_dir()
        self.data = self._load()

    def _resolve_registry_path(self) -> Path:
        """Resolve registry path using priority order."""
        # 1. Environment variable
        env_path = os.environ.get(self.ENV_VAR)
        if env_path:
            return Path(env_path).expanduser().resolve()

        # 2. Config pointer file
        if self.CONFIG_POINTER.exists():
            pointer_content = self.CONFIG_POINTER.read_text().strip()
            if pointer_content:
                return Path(pointer_content).expanduser().resolve()

        # 3. Default location
        return self.DEFAULT_REGISTRY

    def _ensure_registry_dir(self) -> None:
        """Ensure registry directory exists."""
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> Dict[str, Any]:
        """Load registry from YAML file."""
        if self.registry_path.exists():
            with open(self.registry_path, 'r') as f:
                data = yaml.safe_load(f) or {}
                return data
        return {"version": 1, "databases": {}}

    def _save(self) -> None:
        """Save registry to YAML file."""
        with open(self.registry_path, 'w') as f:
            yaml.dump(self.data, f, default_flow_style=False, sort_keys=False)

    def register(
        self,
        name: str,
        path: str,
        source_folder: Optional[str] = None,
        source_type: str = "filesystem",
        auto_watch: bool = False,
        watch_interval: int = 300,
        model: Optional[str] = None,
        recursive: bool = True,
        file_extensions: Optional[List[str]] = None,
        description: Optional[str] = None,
        specstory_config: Optional[Dict[str, Any]] = None,
        api_config: Optional[Dict[str, Any]] = None,
        schema_config: Optional[Dict[str, Any]] = None,
        preprocessing_pipeline: Optional[List[str]] = None
    ) -> DatabaseEntry:
        """
        Register a new database.

        Args:
            name: Unique database name (lowercase alphanumeric + hyphens)
            path: Path to LightRAG database directory
            source_folder: Path to source data folder (optional for API/Schema types)
            source_type: Type of source ('filesystem', 'specstory', 'api', 'schema')
            auto_watch: Enable automatic file watching
            watch_interval: Seconds between watch checks
            model: Model to use (e.g., 'azure/gpt-4o')
            recursive: Watch source folder recursively
            file_extensions: List of file extensions to watch
            description: Human-readable description
            specstory_config: SpecStory-specific settings (for source_type='specstory')
            api_config: API-specific settings (for source_type='api')
            schema_config: Schema-specific settings (for source_type='schema')
            preprocessing_pipeline: Ordered list of preprocessing steps

        Returns:
            DatabaseEntry for the registered database

        Raises:
            ValueError: If name is invalid or already exists
        """
        name = name.lower()

        if name in self.data.get("databases", {}):
            raise ValueError(f"Database '{name}' is already registered. Use update() to modify.")

        entry = DatabaseEntry(
            name=name,
            path=path,
            source_folder=source_folder,
            source_type=source_type,
            auto_watch=auto_watch,
            watch_interval=watch_interval,
            model=model,
            recursive=recursive,
            file_extensions=file_extensions,
            description=description,
            specstory_config=specstory_config,
            api_config=api_config,
            schema_config=schema_config,
            preprocessing_pipeline=preprocessing_pipeline
        )

        if "databases" not in self.data:
            self.data["databases"] = {}

        self.data["databases"][name] = entry.to_dict()
        self._save()

        return entry

    def unregister(self, name: str) -> bool:
        """
        Remove a database from the registry.

        Note: This does NOT delete the database files.

        Args:
            name: Database name to unregister

        Returns:
            True if removed, False if not found
        """
        name = name.lower()

        if name in self.data.get("databases", {}):
            del self.data["databases"][name]
            self._save()
            return True
        return False

    def get(self, name: str) -> Optional[DatabaseEntry]:
        """
        Get a database entry by name.

        Args:
            name: Database name

        Returns:
            DatabaseEntry if found, None otherwise
        """
        name = name.lower()

        db_data = self.data.get("databases", {}).get(name)
        if db_data:
            return DatabaseEntry.from_dict(db_data)
        return None

    def list_all(self) -> List[DatabaseEntry]:
        """
        Get all registered databases.

        Returns:
            List of DatabaseEntry objects
        """
        databases = []
        for name, data in self.data.get("databases", {}).items():
            try:
                databases.append(DatabaseEntry.from_dict(data))
            except Exception as e:
                # Log but don't fail on corrupt entries
                print(f"Warning: Failed to load database '{name}': {e}")
        return databases

    def update(self, name: str, **kwargs) -> DatabaseEntry:
        """
        Update a database entry.

        Args:
            name: Database name to update
            **kwargs: Fields to update

        Returns:
            Updated DatabaseEntry

        Raises:
            ValueError: If database not found
        """
        name = name.lower()

        if name not in self.data.get("databases", {}):
            raise ValueError(f"Database '{name}' not found in registry.")

        # Load current data
        current = self.data["databases"][name]

        # Apply updates
        for key, value in kwargs.items():
            if key == "name":
                # Handle rename
                new_name = value.lower()
                if not DATABASE_NAME_PATTERN.match(new_name):
                    raise ValueError(f"Invalid database name '{new_name}'")
                if new_name != name and new_name in self.data["databases"]:
                    raise ValueError(f"Database '{new_name}' already exists")
                current["name"] = new_name
            elif key in ("path", "source_folder"):
                # Normalize paths
                current[key] = str(Path(value).expanduser().resolve())
            elif value is not None:
                current[key] = value

        # Handle rename in registry
        if current.get("name", name) != name:
            new_name = current["name"]
            self.data["databases"][new_name] = current
            del self.data["databases"][name]
        else:
            self.data["databases"][name] = current

        self._save()
        return DatabaseEntry.from_dict(current)

    def update_last_sync(self, name: str) -> None:
        """
        Update the last_sync timestamp for a database.

        Args:
            name: Database name
        """
        name = name.lower()

        if name in self.data.get("databases", {}):
            self.data["databases"][name]["last_sync"] = datetime.now().isoformat()
            self._save()

    def get_auto_watch_databases(self) -> List[DatabaseEntry]:
        """
        Get all databases with auto_watch enabled.

        Returns:
            List of DatabaseEntry objects with auto_watch=True
        """
        return [db for db in self.list_all() if db.auto_watch]

    def exists(self, name: str) -> bool:
        """Check if a database is registered."""
        return name.lower() in self.data.get("databases", {})

    def set_config_pointer(self, path: str) -> None:
        """
        Set the config pointer to an alternate registry location.

        Args:
            path: Path to alternate registry file
        """
        self.DEFAULT_DIR.mkdir(parents=True, exist_ok=True)
        self.CONFIG_POINTER.write_text(str(Path(path).expanduser().resolve()))

    def clear_config_pointer(self) -> None:
        """Remove the config pointer, reverting to default location."""
        if self.CONFIG_POINTER.exists():
            self.CONFIG_POINTER.unlink()

    def get_registry_path(self) -> str:
        """Get the current registry file path."""
        return str(self.registry_path)


# Convenience functions
def get_registry(registry_path: Optional[str] = None) -> DatabaseRegistry:
    """Get a DatabaseRegistry instance."""
    return DatabaseRegistry(registry_path)


def resolve_database(name_or_path: str) -> tuple[str, Optional[DatabaseEntry]]:
    """
    Resolve a database name or path to actual path and entry.

    Args:
        name_or_path: Database name (e.g., 'specstory') or path

    Returns:
        Tuple of (resolved_path, DatabaseEntry or None)
    """
    # Check if it looks like a registered name (no path separators)
    if '/' not in name_or_path and '\\' not in name_or_path:
        registry = get_registry()
        entry = registry.get(name_or_path)
        if entry:
            return entry.path, entry

    # Treat as path
    return str(Path(name_or_path).expanduser().resolve()), None


# ============================================================================
# Script Integration Helpers
# ============================================================================
# These functions help existing scripts (like watch_specstory_folders.sh)
# integrate with the registry while maintaining backwards compatibility.

def get_config_for_script(db_name: str) -> Optional[Dict[str, Any]]:
    """
    Get configuration for a script, with fallback to environment variables.

    This function supports backwards compatibility:
    1. First checks the registry for the database
    2. Falls back to environment variables if not found

    Args:
        db_name: Database name to look up

    Returns:
        Dict with configuration or None if not found

    Environment variables for fallback:
        HYBRIDRAG_{DB_NAME}_SOURCE_FOLDER
        HYBRIDRAG_{DB_NAME}_DATABASE_PATH
        HYBRIDRAG_{DB_NAME}_MODEL
        HYBRIDRAG_{DB_NAME}_WATCH_INTERVAL
    """
    # Try registry first
    try:
        registry = get_registry()
        entry = registry.get(db_name)
        if entry:
            return {
                "name": entry.name,
                "path": entry.path,
                "source_folder": entry.source_folder,
                "source_type": entry.source_type,
                "auto_watch": entry.auto_watch,
                "watch_interval": entry.watch_interval,
                "model": entry.model,
                "recursive": entry.recursive,
                "file_extensions": entry.file_extensions,
                "specstory_config": entry.specstory_config,
                "api_config": entry.api_config,
                "schema_config": entry.schema_config,
            }
    except Exception:
        pass  # Registry not available, fall back to env vars

    # Fallback to environment variables
    env_prefix = f"HYBRIDRAG_{db_name.upper().replace('-', '_')}"
    source_folder = os.environ.get(f"{env_prefix}_SOURCE_FOLDER")
    database_path = os.environ.get(f"{env_prefix}_DATABASE_PATH")

    if source_folder and database_path:
        return {
            "name": db_name,
            "path": database_path,
            "source_folder": source_folder,
            "source_type": "filesystem",
            "auto_watch": os.environ.get(f"{env_prefix}_AUTO_WATCH", "false").lower() == "true",
            "watch_interval": int(os.environ.get(f"{env_prefix}_WATCH_INTERVAL", "300")),
            "model": os.environ.get(f"{env_prefix}_MODEL"),
            "recursive": True,
            "file_extensions": None,
        }

    return None


def register_specstory_database(
    name: str,
    path: str,
    source_folder: str,
    jira_project_key: Optional[str] = None,
    auto_watch: bool = True,
    watch_interval: int = 300,
    model: Optional[str] = None
) -> DatabaseEntry:
    """
    Convenience function to register a SpecStory-type database.

    Args:
        name: Database name (e.g., 'specstory')
        path: Path to database directory
        source_folder: Path to folder containing JIRA project folders
        jira_project_key: Optional JIRA project key (e.g., 'PROJ')
        auto_watch: Enable auto-watch (default: True)
        watch_interval: Watch interval in seconds (default: 300)
        model: Model to use (optional)

    Returns:
        DatabaseEntry for the registered database
    """
    registry = get_registry()

    specstory_config = {
        "jira_project_key": jira_project_key,
        "folder_pattern": r"^[A-Z]+-\d+$",
        "specstory_file_pattern": r".*\.specstory$",
        "extract_conversations": True,
    }

    return registry.register(
        name=name,
        path=path,
        source_folder=source_folder,
        source_type=SourceType.SPECSTORY.value,
        auto_watch=auto_watch,
        watch_interval=watch_interval,
        model=model,
        file_extensions=[".specstory", ".json"],
        specstory_config=specstory_config,
        description=f"SpecStory AI conversation histories{f' for {jira_project_key}' if jira_project_key else ''}"
    )


def register_schema_database(
    name: str,
    path: str,
    db_type: str = "snowflake",
    connection_name: Optional[str] = None,
    schema_name: Optional[str] = None,
    table_patterns: Optional[List[str]] = None,
    model: Optional[str] = None,
    description: Optional[str] = None
) -> DatabaseEntry:
    """
    Convenience function to register a Schema-type database.

    Args:
        name: Database name (e.g., 'athena-schema')
        path: Path to database directory
        db_type: Database type ('snowflake', 'athena', 'postgres', 'mysql')
        connection_name: Named connection (e.g., snowsql connection name)
        schema_name: Schema to extract
        table_patterns: List of table name patterns to include
        model: Model to use (optional)
        description: Human-readable description

    Returns:
        DatabaseEntry for the registered database
    """
    registry = get_registry()

    schema_config = {
        "db_type": db_type,
        "connection_name": connection_name,
        "schema_name": schema_name,
        "table_patterns": table_patterns,
    }

    return registry.register(
        name=name,
        path=path,
        source_type=SourceType.SCHEMA.value,
        auto_watch=False,  # Schema databases typically don't auto-watch
        model=model,
        schema_config=schema_config,
        description=description or f"{db_type.title()} schema database"
    )


def get_watcher_pid_file(db_name: str) -> Path:
    """Get the path to a watcher's PID file."""
    return DatabaseRegistry.DEFAULT_DIR / "watchers" / f"{db_name}.pid"


def get_watcher_lock_file(db_name: str) -> Path:
    """Get the path to a watcher's lock file."""
    return DatabaseRegistry.DEFAULT_DIR / "locks" / f"{db_name}.lock"


def is_watcher_running(db_name: str) -> tuple[bool, Optional[int]]:
    """
    Check if a watcher is running for a database.

    Args:
        db_name: Database name

    Returns:
        Tuple of (is_running, pid)
    """
    pid_file = get_watcher_pid_file(db_name)

    if not pid_file.exists():
        return False, None

    try:
        pid = int(pid_file.read_text().strip())
        # Check if process is running (Unix-specific)
        os.kill(pid, 0)
        return True, pid
    except (ValueError, OSError, ProcessLookupError):
        # Process not running, clean up stale PID file
        try:
            pid_file.unlink()
        except FileNotFoundError:
            pass
        return False, None


# Example usage
if __name__ == "__main__":
    registry = DatabaseRegistry()

    print(f"Registry location: {registry.get_registry_path()}")
    print(f"Registered databases: {len(registry.list_all())}")

    # List all databases
    for db in registry.list_all():
        running, pid = is_watcher_running(db.name)
        status = f"[WATCHING pid={pid}]" if running else ""
        print(f"  {db.name}: {db.source_type} {status}")
        print(f"    Path: {db.path}")
        if db.source_folder:
            print(f"    Source: {db.source_folder}")

    # Example: Register a specstory database
    # entry = register_specstory_database(
    #     name="specstory",
    #     path="~/databases/specstory_db",
    #     source_folder="~/dev/jira-issues",
    #     jira_project_key="TIC",
    #     auto_watch=True
    # )
    # print(f"Registered: {entry.name}")
