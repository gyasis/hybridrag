"""
Watch Manager for HybridRAG Database Watchers
==============================================

Provides a control layer for managing database file watchers in two modes:
1. Standalone mode - Python daemon process with PID file management
2. Systemd mode - Integration with systemd user units

Author: HybridRAG System
Date: 2025-12-06
"""

import os
import sys
import signal
import subprocess
import logging
from pathlib import Path
from typing import List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum, auto

from .database_registry import (
    DatabaseRegistry, DatabaseEntry,
    get_registry, get_watcher_pid_file,
    is_watcher_running
)

logger = logging.getLogger(__name__)


class WatcherMode(Enum):
    """Watcher operation mode."""
    STANDALONE = auto()  # Python daemon with PID file
    SYSTEMD = auto()     # systemd user unit


@dataclass
class WatcherStatus:
    """Status of a watcher for a database."""
    db_name: str
    running: bool
    pid: Optional[int] = None
    mode: Optional[WatcherMode] = None
    auto_watch: bool = False
    source_folder: Optional[str] = None
    watch_interval: int = 300


class WatchManager:
    """
    Manages database watchers for HybridRAG.

    Supports two modes:
    - Standalone: Python daemon process with PID file management
    - Systemd: Integration with systemd user units

    Usage:
        manager = WatchManager()

        # Start watcher for a single database
        manager.start_watcher("specstory")

        # Start all auto-watch databases
        manager.start_all_auto_watch()

        # Get status
        statuses = manager.status()

        # Stop watcher
        manager.stop_watcher("specstory")
    """

    # BUG-013 fix: Use robust path resolution with validation
    # Instead of fragile Path(__file__).parent.parent, we validate the path exists
    @classmethod
    def _get_hybridrag_dir(cls) -> Path:
        """Get HybridRAG base directory with validation."""
        # Try relative to this module first
        candidate = Path(__file__).parent.parent
        if (candidate / "scripts" / "hybridrag-watcher.py").exists():
            return candidate

        # Try from current working directory
        cwd_candidate = Path.cwd()
        if (cwd_candidate / "scripts" / "hybridrag-watcher.py").exists():
            return cwd_candidate

        # Try common installation paths
        for path in [
            Path.home() / "dev" / "tools" / "RAG" / "hybridrag",
            Path.home() / ".local" / "share" / "hybridrag",
        ]:
            if (path / "scripts" / "hybridrag-watcher.py").exists():
                return path

        # Fall back to module-relative path (original behavior)
        return candidate

    @classmethod
    def _get_scripts_dir(cls) -> Path:
        """Get scripts directory."""
        return cls._get_hybridrag_dir() / "scripts"

    @classmethod
    def _get_watcher_script(cls) -> Path:
        """Get watcher script path."""
        return cls._get_scripts_dir() / "hybridrag-watcher.py"

    # Legacy class attributes for backward compatibility
    HYBRIDRAG_DIR = Path(__file__).parent.parent
    SCRIPTS_DIR = HYBRIDRAG_DIR / "scripts"
    WATCHER_SCRIPT = SCRIPTS_DIR / "hybridrag-watcher.py"

    # Systemd user unit directory
    SYSTEMD_USER_DIR = Path.home() / ".config" / "systemd" / "user"
    SYSTEMD_UNIT_NAME = "hybridrag-watcher@.service"

    def __init__(self, registry: Optional[DatabaseRegistry] = None):
        """
        Initialize the watch manager.

        Args:
            registry: Optional registry instance. If not provided, uses default.
        """
        self.registry = registry or get_registry()

    def start_watcher(
        self,
        db_name: str,
        mode: WatcherMode = WatcherMode.STANDALONE,
        force: bool = False
    ) -> Tuple[bool, str]:
        """
        Start watcher for a database.

        Args:
            db_name: Database name from registry
            mode: Watcher mode (standalone or systemd)
            force: Force restart if already running

        Returns:
            Tuple of (success, message)
        """
        # Get database entry
        entry = self.registry.get(db_name)
        if not entry:
            return False, f"Database not found: {db_name}"

        if not entry.source_folder:
            return False, f"No source folder configured for: {db_name}"

        if not os.path.exists(entry.source_folder):
            return False, f"Source folder does not exist: {entry.source_folder}"

        # Check if already running
        running, pid = is_watcher_running(db_name)
        if running and not force:
            return False, f"Watcher already running (PID: {pid}). Use force=True to restart."

        # Stop existing watcher if force
        if running and force:
            self.stop_watcher(db_name)

        # Start based on mode
        if mode == WatcherMode.SYSTEMD:
            return self._start_systemd_watcher(entry)
        else:
            return self._start_standalone_watcher(entry)

    def _start_standalone_watcher(self, entry: DatabaseEntry) -> Tuple[bool, str]:
        """Start a standalone Python watcher daemon."""

        # BUG-013 fix: Use validated path methods instead of fragile class attributes
        watcher_script = self._get_watcher_script()
        scripts_dir = self._get_scripts_dir()
        hybridrag_dir = self._get_hybridrag_dir()

        # Check if watcher script exists
        if not watcher_script.exists():
            # Fall back to legacy bash script for specstory
            legacy_script = scripts_dir / "watch_specstory_folders.sh"
            if legacy_script.exists() and entry.source_type == 'specstory':
                return self._start_legacy_watcher(entry, legacy_script)
            return False, f"Watcher script not found: {watcher_script}"

        log_dir = hybridrag_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"watcher_{entry.name}.log"

        try:
            # Start the watcher process
            # Note: The watcher script handles PID file creation with proper flock locking
            # to prevent race conditions. We do NOT write the PID file here.
            with open(log_file, 'a') as log:
                proc = subprocess.Popen(
                    [sys.executable, str(watcher_script), entry.name],
                    stdout=log,
                    stderr=log,
                    start_new_session=True
                )

            logger.info(f"Started watcher for {entry.name} (PID: {proc.pid})")
            return True, f"Started watcher (PID: {proc.pid})"

        except Exception as e:
            logger.error(f"Failed to start watcher for {entry.name}: {e}")
            return False, f"Failed to start watcher: {e}"

    def _start_legacy_watcher(
        self,
        entry: DatabaseEntry,
        script_path: Path
    ) -> Tuple[bool, str]:
        """Start the legacy bash watcher script."""

        # BUG-013 fix: Use validated path methods
        log_dir = self._get_hybridrag_dir() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"watcher_{entry.name}_legacy.log"

        try:
            cmd = [
                str(script_path),
                entry.source_folder,
                str(entry.watch_interval),
            ]
            if entry.model:
                cmd.append(entry.model)

            with open(log_file, 'a') as log:
                proc = subprocess.Popen(
                    cmd,
                    stdout=log,
                    stderr=log,
                    start_new_session=True
                )

            # BUG-005 fix: DO NOT write PID file here - the legacy watcher script
            # handles its own PID file creation with proper flock locking.
            # Writing it here creates a race condition and potential double-writes.

            logger.info(f"Started legacy watcher for {entry.name} (PID: {proc.pid})")
            return True, f"Started legacy watcher (PID: {proc.pid})"

        except Exception as e:
            logger.error(f"Failed to start legacy watcher for {entry.name}: {e}")
            return False, f"Failed to start legacy watcher: {e}"

    def _start_systemd_watcher(self, entry: DatabaseEntry) -> Tuple[bool, str]:
        """Start a systemd watcher unit."""

        # Ensure unit file exists
        if not self._ensure_systemd_unit():
            return False, "Failed to install systemd unit file"

        unit_name = f"hybridrag-watcher@{entry.name}.service"

        try:
            # Enable and start the unit
            subprocess.run(
                ["systemctl", "--user", "enable", "--now", unit_name],
                check=True,
                capture_output=True
            )

            logger.info(f"Started systemd watcher for {entry.name}")
            return True, f"Started systemd unit: {unit_name}"

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            logger.error(f"Failed to start systemd watcher: {error_msg}")
            return False, f"Failed to start systemd unit: {error_msg}"

    def _ensure_systemd_unit(self) -> bool:
        """Ensure the systemd template unit file is installed."""

        self.SYSTEMD_USER_DIR.mkdir(parents=True, exist_ok=True)
        unit_path = self.SYSTEMD_USER_DIR / self.SYSTEMD_UNIT_NAME

        if unit_path.exists():
            return True

        # Generate unit file content
        venv_python = sys.executable
        # BUG-013 fix: Use validated path methods
        watcher_script = self._get_watcher_script()

        unit_content = f"""[Unit]
Description=HybridRAG Watcher for %i
After=network.target

[Service]
Type=simple
ExecStart={venv_python} {watcher_script} %i
Restart=on-failure
RestartSec=10
Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=default.target
"""

        try:
            unit_path.write_text(unit_content)

            # Reload systemd
            subprocess.run(
                ["systemctl", "--user", "daemon-reload"],
                check=True,
                capture_output=True
            )

            logger.info(f"Installed systemd unit: {unit_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to install systemd unit: {e}")
            return False

    def stop_watcher(self, db_name: str) -> Tuple[bool, str]:
        """
        Stop watcher for a database.

        Args:
            db_name: Database name

        Returns:
            Tuple of (success, message)
        """
        running, pid = is_watcher_running(db_name)

        if not running:
            return False, f"No watcher running for: {db_name}"

        # Try to stop standalone process first
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
                pid_file = get_watcher_pid_file(db_name)
                if pid_file.exists():
                    pid_file.unlink()
                logger.info(f"Stopped watcher for {db_name} (PID: {pid})")
                return True, f"Stopped watcher (was PID: {pid})"
            except ProcessLookupError:
                # Process already gone
                pid_file = get_watcher_pid_file(db_name)
                if pid_file.exists():
                    pid_file.unlink()
                return True, "Watcher was already stopped"
            except PermissionError:
                return False, f"Permission denied to stop process {pid}"

        # Try systemd unit
        unit_name = f"hybridrag-watcher@{db_name}.service"
        try:
            subprocess.run(
                ["systemctl", "--user", "stop", unit_name],
                check=True,
                capture_output=True
            )
            return True, f"Stopped systemd unit: {unit_name}"
        except subprocess.CalledProcessError:
            pass

        return False, "Failed to stop watcher"

    def status(self, db_name: Optional[str] = None) -> List[WatcherStatus]:
        """
        Get status of watchers.

        Args:
            db_name: Optional specific database name. If None, returns all.

        Returns:
            List of WatcherStatus objects
        """
        statuses = []

        if db_name:
            entry = self.registry.get(db_name)
            if entry:
                statuses.append(self._get_status(entry))
        else:
            for entry in self.registry.list_all():
                statuses.append(self._get_status(entry))

        return statuses

    def _get_status(self, entry: DatabaseEntry) -> WatcherStatus:
        """Get status for a single database entry."""
        running, pid = is_watcher_running(entry.name)

        # Try to detect mode
        mode = None
        if running:
            # Check if it's a systemd unit
            unit_name = f"hybridrag-watcher@{entry.name}.service"
            try:
                result = subprocess.run(
                    ["systemctl", "--user", "is-active", unit_name],
                    capture_output=True,
                    text=True
                )
                if result.stdout.strip() == "active":
                    mode = WatcherMode.SYSTEMD
                else:
                    mode = WatcherMode.STANDALONE
            except (subprocess.SubprocessError, OSError):
                mode = WatcherMode.STANDALONE

        return WatcherStatus(
            db_name=entry.name,
            running=running,
            pid=pid,
            mode=mode,
            auto_watch=entry.auto_watch,
            source_folder=entry.source_folder,
            watch_interval=entry.watch_interval
        )

    def start_all_auto_watch(
        self,
        mode: WatcherMode = WatcherMode.STANDALONE
    ) -> List[Tuple[str, bool, str]]:
        """
        Start watchers for all databases with auto_watch enabled.

        Args:
            mode: Watcher mode to use

        Returns:
            List of (db_name, success, message) tuples
        """
        results = []
        auto_watch_dbs = self.registry.get_auto_watch_databases()

        for entry in auto_watch_dbs:
            success, msg = self.start_watcher(entry.name, mode=mode)
            results.append((entry.name, success, msg))

        return results

    def stop_all(self) -> int:
        """
        Stop all running watchers.

        Returns:
            Number of watchers stopped
        """
        stopped = 0

        for entry in self.registry.list_all():
            running, _ = is_watcher_running(entry.name)
            if running:
                success, _ = self.stop_watcher(entry.name)
                if success:
                    stopped += 1

        return stopped

    def install_systemd_units(self) -> Tuple[bool, str]:
        """
        Install systemd template unit and enable all auto-watch databases.

        Returns:
            Tuple of (success, message)
        """
        if not self._ensure_systemd_unit():
            return False, "Failed to install systemd unit template"

        auto_watch_dbs = self.registry.get_auto_watch_databases()

        if not auto_watch_dbs:
            return True, "No auto-watch databases to enable"

        enabled = []
        failed = []

        for entry in auto_watch_dbs:
            unit_name = f"hybridrag-watcher@{entry.name}.service"
            try:
                subprocess.run(
                    ["systemctl", "--user", "enable", unit_name],
                    check=True,
                    capture_output=True
                )
                enabled.append(entry.name)
            except subprocess.CalledProcessError:
                failed.append(entry.name)

        if failed:
            return False, f"Enabled: {enabled}, Failed: {failed}"

        return True, f"Enabled systemd units for: {enabled}"

    def uninstall_systemd_units(self) -> Tuple[bool, str]:
        """
        Disable and remove all systemd watcher units.

        Returns:
            Tuple of (success, message)
        """
        # Stop all watchers first
        self.stop_all()

        # Disable and remove units for all databases
        for entry in self.registry.list_all():
            unit_name = f"hybridrag-watcher@{entry.name}.service"
            try:
                subprocess.run(
                    ["systemctl", "--user", "disable", unit_name],
                    capture_output=True
                )
            except (subprocess.SubprocessError, OSError):
                pass

        # Remove template unit
        unit_path = self.SYSTEMD_USER_DIR / self.SYSTEMD_UNIT_NAME
        if unit_path.exists():
            unit_path.unlink()

        # Reload systemd
        try:
            subprocess.run(
                ["systemctl", "--user", "daemon-reload"],
                capture_output=True
            )
        except (subprocess.SubprocessError, OSError):
            pass

        return True, "Uninstalled systemd units"
