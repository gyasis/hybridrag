"""
Watcher Control Module (T024)
==============================

Provides utilities for pausing and resuming database watchers during migration
or other operations that require exclusive access to the database.

Uses file-based signaling to communicate with running watcher processes:
- .pause file: Signals watcher to pause
- .resume file: Signals watcher to resume
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default location for watcher control files
CONTROL_DIR = Path.home() / '.hybridrag' / 'watcher_control'


def _get_control_file(db_name: str, signal_type: str) -> Path:
    """Get the path to a control signal file."""
    CONTROL_DIR.mkdir(parents=True, exist_ok=True)
    return CONTROL_DIR / f"{db_name}.{signal_type}"


def _get_pid_file(db_name: str) -> Path:
    """Get the path to the watcher PID file."""
    return CONTROL_DIR / f"{db_name}.pid"


async def is_watcher_running(db_name: str) -> bool:
    """
    Check if a watcher is running for the specified database.

    Args:
        db_name: Database name to check

    Returns:
        True if watcher is running, False otherwise
    """
    import os

    pid_file = _get_pid_file(db_name)
    if not pid_file.exists():
        return False

    try:
        pid = int(pid_file.read_text().strip())
        # Check if process is running (signal 0 doesn't kill, just checks)
        os.kill(pid, 0)
        return True
    except (ValueError, ProcessLookupError, PermissionError):
        # PID file exists but process is not running
        pid_file.unlink(missing_ok=True)
        return False


async def pause_watcher(db_name: str, timeout: float = 30.0) -> bool:
    """
    Pause the watcher for a database.

    Creates a pause signal file that the watcher checks periodically.
    Waits for the watcher to acknowledge the pause.

    Args:
        db_name: Database name to pause
        timeout: Maximum time to wait for acknowledgment

    Returns:
        True if watcher was running and is now paused, False if no watcher running
    """
    # Check if watcher is running
    if not await is_watcher_running(db_name):
        logger.debug(f"No watcher running for {db_name}")
        return False

    # Create pause signal
    pause_file = _get_control_file(db_name, 'pause')
    ack_file = _get_control_file(db_name, 'pause_ack')

    # Remove any stale ack file
    ack_file.unlink(missing_ok=True)

    # Create pause signal
    pause_file.write_text("pause_requested")
    logger.info(f"Pause signal sent to watcher for {db_name}")

    # Wait for acknowledgment
    start_time = asyncio.get_event_loop().time()
    while asyncio.get_event_loop().time() - start_time < timeout:
        if ack_file.exists():
            logger.info(f"Watcher acknowledged pause for {db_name}")
            return True
        await asyncio.sleep(0.5)

    logger.warning(f"Timeout waiting for watcher to acknowledge pause for {db_name}")
    # Leave pause file in place - watcher will see it eventually
    return True


async def resume_watcher(db_name: str) -> bool:
    """
    Resume a paused watcher.

    Removes the pause signal file and creates a resume signal.

    Args:
        db_name: Database name to resume

    Returns:
        True if resume signal was sent, False if no watcher to resume
    """
    pause_file = _get_control_file(db_name, 'pause')
    ack_file = _get_control_file(db_name, 'pause_ack')

    # Remove pause signals
    pause_file.unlink(missing_ok=True)
    ack_file.unlink(missing_ok=True)

    # Check if watcher exists to resume
    if not await is_watcher_running(db_name):
        logger.debug(f"No watcher running for {db_name} to resume")
        return False

    logger.info(f"Resume signal sent to watcher for {db_name}")
    return True


def check_pause_signal(db_name: str) -> bool:
    """
    Check if a pause signal exists for the database.

    Called by watcher processes to check if they should pause.

    Args:
        db_name: Database name to check

    Returns:
        True if pause signal exists, False otherwise
    """
    pause_file = _get_control_file(db_name, 'pause')
    return pause_file.exists()


def acknowledge_pause(db_name: str) -> None:
    """
    Acknowledge receipt of pause signal.

    Called by watcher after it has paused operations.

    Args:
        db_name: Database name to acknowledge
    """
    ack_file = _get_control_file(db_name, 'pause_ack')
    ack_file.write_text("paused")
    logger.info(f"Watcher acknowledged pause for {db_name}")


def register_watcher_pid(db_name: str, pid: Optional[int] = None) -> None:
    """
    Register the PID of a running watcher.

    Args:
        db_name: Database name
        pid: Process ID (uses current process if not specified)
    """
    import os
    if pid is None:
        pid = os.getpid()

    pid_file = _get_pid_file(db_name)
    pid_file.write_text(str(pid))
    logger.debug(f"Registered watcher PID {pid} for {db_name}")


def unregister_watcher_pid(db_name: str) -> None:
    """
    Remove the watcher PID registration.

    Args:
        db_name: Database name
    """
    pid_file = _get_pid_file(db_name)
    pid_file.unlink(missing_ok=True)

    # Also clean up any stale control files
    for signal_type in ['pause', 'pause_ack']:
        _get_control_file(db_name, signal_type).unlink(missing_ok=True)

    logger.debug(f"Unregistered watcher PID for {db_name}")


class WatcherPauseContext:
    """
    Context manager for pausing watcher during operations.

    Usage:
        async with WatcherPauseContext("mydb") as ctx:
            if ctx.was_running:
                # Watcher is paused
                pass
            # Do work here
        # Watcher automatically resumed
    """

    def __init__(self, db_name: str):
        self.db_name = db_name
        self.was_running = False

    async def __aenter__(self):
        self.was_running = await pause_watcher(self.db_name)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.was_running:
            await resume_watcher(self.db_name)
        return False  # Don't suppress exceptions
