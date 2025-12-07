#!/usr/bin/env python3
"""
HybridRAG Utility Functions
===========================
Common utility functions for the HybridRAG system.
"""


def format_file_size(size_bytes: int) -> str:
    """
    Convert bytes to human-readable format with auto-unit selection.

    Args:
        size_bytes: Size in bytes (can be int or float)

    Returns:
        Human-readable string like "1.5 MB", "256 KB", "2.3 GB"

    Examples:
        >>> format_file_size(1024)
        '1.0 KB'
        >>> format_file_size(1536000)
        '1.5 MB'
        >>> format_file_size(0)
        '0 B'
    """
    if size_bytes == 0:
        return "0 B"

    size = float(size_bytes)
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(size) < 1024.0:
            # Use no decimal for bytes, one decimal for larger units
            if unit == 'B':
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def format_duration(seconds: float) -> str:
    """
    Convert seconds to human-readable duration.

    Args:
        seconds: Duration in seconds

    Returns:
        Human-readable string like "2.5s", "1m 30s", "2h 15m"
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncate text to a maximum length with suffix.

    Args:
        text: Text to truncate
        max_length: Maximum length including suffix
        suffix: Suffix to append when truncated

    Returns:
        Truncated text with suffix if exceeded max_length
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix
