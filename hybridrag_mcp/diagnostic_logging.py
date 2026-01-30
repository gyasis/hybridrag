#!/usr/bin/env python3
"""
Diagnostic Logging Module for HybridRAG MCP Server
===================================================
Provides structured, in-memory logging with categorization and filtering
to expose errors and debug information via MCP tools.

Features:
- Thread-safe rotating buffer (last N entries)
- Category-based filtering (db, embedding, llm, query, system)
- Trace ID support for grouping related log entries
- Integration with Python's standard logging module
- Markdown-formatted output for MCP tool responses

Usage:
    from hybridrag_mcp.diagnostic_logging import (
        DiagnosticLogStore, MCPBufferHandler, trace_step, get_trace_id, set_trace_id
    )

    # Initialize the global store
    log_store = DiagnosticLogStore(maxlen=100)

    # Add handler to logger
    handler = MCPBufferHandler(log_store)
    logging.getLogger().addHandler(handler)

    # Use trace_step decorator
    @trace_step("db")
    async def query_database():
        ...
"""

import asyncio
import contextvars
import functools
import logging
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Deque, Dict, List, Literal, Optional, TypeVar

# =============================================================================
# TYPE DEFINITIONS
# =============================================================================

# Log categories for filtering
LogCategory = Literal["db", "embedding", "llm", "query", "system", "init", "error"]

# Log levels (matching Python logging)
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


@dataclass
class LogEntry:
    """
    Structured log entry for diagnostic logging.

    Attributes:
        timestamp: ISO 8601 formatted timestamp (UTC)
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        category: Category for filtering (db, embedding, llm, query, system, init, error)
        message: The log message
        metadata: Optional dict of additional context (e.g., duration, error details)
        trace_id: Optional trace ID to group related log entries
        logger_name: Name of the logger that created this entry
    """
    timestamp: str
    level: LogLevel
    category: LogCategory
    message: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    trace_id: Optional[str] = None
    logger_name: str = "hybridrag"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp,
            "level": self.level,
            "category": self.category,
            "message": self.message,
            "metadata": self.metadata,
            "trace_id": self.trace_id,
            "logger_name": self.logger_name,
        }

    def to_markdown_row(self) -> str:
        """Format as a markdown table row."""
        # Truncate message for table display
        msg = self.message[:80] + "..." if len(self.message) > 80 else self.message
        msg = msg.replace("|", "\\|").replace("\n", " ")

        # Format metadata compactly
        meta_str = ""
        if self.metadata:
            meta_items = []
            for k, v in list(self.metadata.items())[:3]:  # Limit to 3 items
                if isinstance(v, float):
                    meta_items.append(f"{k}={v:.2f}")
                else:
                    v_str = str(v)[:20]
                    meta_items.append(f"{k}={v_str}")
            meta_str = "; ".join(meta_items)

        # Extract time part from timestamp
        time_part = self.timestamp.split("T")[1][:12] if "T" in self.timestamp else self.timestamp

        return f"| {time_part} | {self.level:8} | {self.category:9} | {msg} | {meta_str} |"


# =============================================================================
# CONTEXT VARIABLES FOR TRACE ID
# =============================================================================

# Context variable for trace ID (survives across async calls)
_trace_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "trace_id", default=None
)


def get_trace_id() -> Optional[str]:
    """Get the current trace ID from context."""
    return _trace_id_var.get()


def set_trace_id(trace_id: Optional[str] = None) -> str:
    """
    Set or generate a trace ID in context.

    Args:
        trace_id: Optional trace ID to set. If None, generates a new UUID.

    Returns:
        The trace ID that was set.
    """
    if trace_id is None:
        trace_id = str(uuid.uuid4())[:8]  # Short UUID for readability
    _trace_id_var.set(trace_id)
    return trace_id


def clear_trace_id() -> None:
    """Clear the trace ID from context."""
    _trace_id_var.set(None)


# =============================================================================
# DIAGNOSTIC LOG STORE
# =============================================================================

class DiagnosticLogStore:
    """
    Thread-safe rotating buffer for diagnostic log entries.

    Uses collections.deque with maxlen for automatic rotation -
    when capacity is reached, oldest entries are automatically dropped.

    Attributes:
        maxlen: Maximum number of entries to store (default 100)
    """

    def __init__(self, maxlen: int = 100):
        """
        Initialize the log store.

        Args:
            maxlen: Maximum number of entries to store
        """
        self._buffer: Deque[LogEntry] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._maxlen = maxlen

    def append(self, entry: LogEntry) -> None:
        """
        Append a log entry to the buffer (thread-safe).

        Args:
            entry: LogEntry to append
        """
        with self._lock:
            self._buffer.append(entry)

    def get_all(self) -> List[LogEntry]:
        """
        Get all log entries as a list (thread-safe).

        Returns:
            List of LogEntry objects, oldest first
        """
        with self._lock:
            return list(self._buffer)

    def get_filtered(
        self,
        category: Optional[LogCategory] = None,
        min_level: Optional[LogLevel] = None,
        trace_id: Optional[str] = None,
        search_text: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[LogEntry]:
        """
        Get filtered log entries.

        Args:
            category: Filter by category (db, embedding, llm, query, system, init, error)
            min_level: Minimum log level (DEBUG < INFO < WARNING < ERROR < CRITICAL)
            trace_id: Filter by trace ID
            search_text: Search for text in message (case-insensitive)
            limit: Maximum number of entries to return

        Returns:
            List of matching LogEntry objects, oldest first
        """
        level_order = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
        min_level_value = level_order.get(min_level, 0) if min_level else 0

        with self._lock:
            entries = list(self._buffer)

        # Apply filters
        result = []
        for entry in entries:
            # Category filter
            if category and entry.category != category:
                continue

            # Level filter
            entry_level_value = level_order.get(entry.level, 0)
            if entry_level_value < min_level_value:
                continue

            # Trace ID filter
            if trace_id and entry.trace_id != trace_id:
                continue

            # Text search filter
            if search_text and search_text.lower() not in entry.message.lower():
                continue

            result.append(entry)

        # Apply limit (from end, most recent)
        if limit and len(result) > limit:
            result = result[-limit:]

        return result

    def get_recent_errors(self, limit: int = 10) -> List[LogEntry]:
        """
        Get recent ERROR and CRITICAL level entries.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of error entries, most recent first
        """
        entries = self.get_filtered(min_level="ERROR", limit=limit)
        return list(reversed(entries))  # Most recent first

    def get_by_trace_id(self, trace_id: str) -> List[LogEntry]:
        """
        Get all entries for a specific trace ID.

        Args:
            trace_id: The trace ID to filter by

        Returns:
            List of entries with the given trace ID, oldest first
        """
        return self.get_filtered(trace_id=trace_id)

    def clear(self) -> None:
        """Clear all entries from the buffer."""
        with self._lock:
            self._buffer.clear()

    def __len__(self) -> int:
        """Return number of entries in buffer."""
        with self._lock:
            return len(self._buffer)

    @property
    def maxlen(self) -> int:
        """Return maximum buffer size."""
        return self._maxlen

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the log store.

        Returns:
            Dict with count, maxlen, and category/level breakdowns
        """
        with self._lock:
            entries = list(self._buffer)

        # Count by category
        category_counts: Dict[str, int] = {}
        level_counts: Dict[str, int] = {}

        for entry in entries:
            category_counts[entry.category] = category_counts.get(entry.category, 0) + 1
            level_counts[entry.level] = level_counts.get(entry.level, 0) + 1

        return {
            "total_entries": len(entries),
            "max_entries": self._maxlen,
            "by_category": category_counts,
            "by_level": level_counts,
        }


# =============================================================================
# LOGGING HANDLER
# =============================================================================

class MCPBufferHandler(logging.Handler):
    """
    Python logging handler that captures logs to DiagnosticLogStore.

    Integrates with Python's standard logging module to capture logs
    from both our code and third-party libraries (like asyncpg, litellm).

    Usage:
        store = DiagnosticLogStore(maxlen=100)
        handler = MCPBufferHandler(store)
        handler.setLevel(logging.INFO)
        logging.getLogger().addHandler(handler)
    """

    # Mapping of logger names to categories
    LOGGER_CATEGORY_MAP = {
        "asyncpg": "db",
        "psycopg": "db",
        "litellm": "llm",
        "LiteLLM": "llm",
        "openai": "llm",
        "anthropic": "llm",
        "lightrag": "query",
        "hybridrag": "system",
        "hybridrag_mcp": "system",
    }

    def __init__(self, store: DiagnosticLogStore):
        """
        Initialize the handler.

        Args:
            store: DiagnosticLogStore to write entries to
        """
        super().__init__()
        self.store = store

    def emit(self, record: logging.LogRecord) -> None:
        """
        Emit a log record to the store.

        Args:
            record: Python logging LogRecord
        """
        try:
            # Extract category from record's 'extra' or infer from logger name
            category = self._get_category(record)

            # Extract metadata from record's 'extra'
            metadata = getattr(record, "metadata", {})
            if not isinstance(metadata, dict):
                metadata = {}

            # Add exception info if present
            if record.exc_info and record.exc_info[1]:
                exc = record.exc_info[1]
                metadata["exception_type"] = type(exc).__name__
                metadata["exception_msg"] = str(exc)[:200]

            # Get trace ID from context or record
            trace_id = getattr(record, "trace_id", None) or get_trace_id()

            # Create entry
            entry = LogEntry(
                timestamp=datetime.now(timezone.utc).isoformat(),
                level=record.levelname,
                category=category,
                message=self.format(record) if self.formatter else record.getMessage(),
                metadata=metadata,
                trace_id=trace_id,
                logger_name=record.name,
            )

            self.store.append(entry)

        except Exception:
            # Don't let logging errors crash the application
            self.handleError(record)

    def _get_category(self, record: logging.LogRecord) -> LogCategory:
        """
        Determine category from log record.

        Priority:
        1. Explicit 'category' in record's extra
        2. Logger name mapping
        3. Default to 'system'
        """
        # Check for explicit category
        explicit = getattr(record, "category", None)
        if explicit and explicit in ("db", "embedding", "llm", "query", "system", "init", "error"):
            return explicit

        # Infer from logger name
        logger_name = record.name.lower()
        for prefix, cat in self.LOGGER_CATEGORY_MAP.items():
            if logger_name.startswith(prefix.lower()):
                return cat

        # Check for keywords in message
        msg_lower = record.getMessage().lower()
        if any(kw in msg_lower for kw in ["postgres", "asyncpg", "connection", "pool"]):
            return "db"
        if any(kw in msg_lower for kw in ["embed", "vector", "dimension"]):
            return "embedding"
        if any(kw in msg_lower for kw in ["llm", "litellm", "completion", "synthesis"]):
            return "llm"
        if any(kw in msg_lower for kw in ["query", "search", "retrieval"]):
            return "query"

        # Default
        return "system"


# =============================================================================
# TRACE STEP DECORATOR
# =============================================================================

# Type variable for decorated function
F = TypeVar("F", bound=Callable[..., Any])


def trace_step(
    category: LogCategory,
    operation_name: Optional[str] = None,
) -> Callable[[F], F]:
    """
    Decorator to trace function execution with logging.

    Logs the start, completion (with duration), and any errors for a function.
    Works with both sync and async functions.

    Args:
        category: Log category (db, embedding, llm, query, system, init, error)
        operation_name: Optional operation name (defaults to function name)

    Returns:
        Decorated function

    Usage:
        @trace_step("db")
        async def query_postgres():
            ...

        @trace_step("llm", "LLM Synthesis")
        async def generate_response():
            ...
    """
    def decorator(func: F) -> F:
        name = operation_name or func.__name__
        logger = logging.getLogger(f"hybridrag.{category}")

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            trace_id = get_trace_id()
            start_time = time.perf_counter()

            logger.info(
                f"Starting {name}",
                extra={"category": category, "trace_id": trace_id}
            )

            try:
                result = await func(*args, **kwargs)
                duration = time.perf_counter() - start_time

                logger.info(
                    f"Completed {name}",
                    extra={
                        "category": category,
                        "trace_id": trace_id,
                        "metadata": {"duration_sec": round(duration, 3)},
                    }
                )
                return result

            except Exception as e:
                duration = time.perf_counter() - start_time
                logger.error(
                    f"Failed {name}: {type(e).__name__}: {str(e)[:200]}",
                    extra={
                        "category": category,
                        "trace_id": trace_id,
                        "metadata": {
                            "duration_sec": round(duration, 3),
                            "error_type": type(e).__name__,
                        },
                    },
                    exc_info=True,
                )
                raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            trace_id = get_trace_id()
            start_time = time.perf_counter()

            logger.info(
                f"Starting {name}",
                extra={"category": category, "trace_id": trace_id}
            )

            try:
                result = func(*args, **kwargs)
                duration = time.perf_counter() - start_time

                logger.info(
                    f"Completed {name}",
                    extra={
                        "category": category,
                        "trace_id": trace_id,
                        "metadata": {"duration_sec": round(duration, 3)},
                    }
                )
                return result

            except Exception as e:
                duration = time.perf_counter() - start_time
                logger.error(
                    f"Failed {name}: {type(e).__name__}: {str(e)[:200]}",
                    extra={
                        "category": category,
                        "trace_id": trace_id,
                        "metadata": {
                            "duration_sec": round(duration, 3),
                            "error_type": type(e).__name__,
                        },
                    },
                    exc_info=True,
                )
                raise

        # Return appropriate wrapper
        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        return sync_wrapper  # type: ignore

    return decorator


# =============================================================================
# HELPER FUNCTIONS FOR MCP TOOL OUTPUT
# =============================================================================

def format_logs_as_markdown(
    entries: List[LogEntry],
    title: str = "Diagnostic Logs",
    include_stats: bool = True,
) -> str:
    """
    Format log entries as a Markdown document.

    Args:
        entries: List of LogEntry objects
        title: Title for the output
        include_stats: Whether to include summary statistics

    Returns:
        Markdown-formatted string
    """
    lines = [f"# {title}", ""]

    if include_stats and entries:
        # Summary stats
        error_count = sum(1 for e in entries if e.level in ("ERROR", "CRITICAL"))
        warning_count = sum(1 for e in entries if e.level == "WARNING")

        lines.append(f"**Total Entries:** {len(entries)}")
        if error_count:
            lines.append(f"**Errors:** {error_count}")
        if warning_count:
            lines.append(f"**Warnings:** {warning_count}")
        lines.append("")

    if not entries:
        lines.append("_No log entries found._")
        return "\n".join(lines)

    # Table header
    lines.append("| Time | Level | Category | Message | Metadata |")
    lines.append("|------|-------|----------|---------|----------|")

    # Table rows
    for entry in entries:
        lines.append(entry.to_markdown_row())

    return "\n".join(lines)


def format_logs_as_json(entries: List[LogEntry]) -> List[Dict[str, Any]]:
    """
    Format log entries as JSON-serializable list.

    Args:
        entries: List of LogEntry objects

    Returns:
        List of dictionaries
    """
    return [entry.to_dict() for entry in entries]


# =============================================================================
# GLOBAL INSTANCE (Singleton Pattern)
# =============================================================================

# Global diagnostic log store - initialized on first import
_diagnostic_store: Optional[DiagnosticLogStore] = None
_handler_installed: bool = False


def get_diagnostic_store(maxlen: int = 100) -> DiagnosticLogStore:
    """
    Get or create the global diagnostic log store.

    Args:
        maxlen: Maximum entries (only used on first call)

    Returns:
        DiagnosticLogStore instance
    """
    global _diagnostic_store
    if _diagnostic_store is None:
        _diagnostic_store = DiagnosticLogStore(maxlen=maxlen)
    return _diagnostic_store


def install_diagnostic_handler(
    level: int = logging.INFO,
    store: Optional[DiagnosticLogStore] = None,
) -> MCPBufferHandler:
    """
    Install the diagnostic handler on the root logger.

    This should be called once during server initialization.

    Args:
        level: Minimum log level to capture (default INFO)
        store: Optional DiagnosticLogStore (uses global if None)

    Returns:
        The installed MCPBufferHandler
    """
    global _handler_installed

    store = store or get_diagnostic_store()
    handler = MCPBufferHandler(store)
    handler.setLevel(level)

    # Use a simple format for the handler
    formatter = logging.Formatter('%(name)s - %(message)s')
    handler.setFormatter(formatter)

    # Add to root logger
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)

    _handler_installed = True

    return handler
