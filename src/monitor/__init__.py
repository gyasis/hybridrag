"""
HybridRAG Interactive Monitor & Setup Wizard
=============================================

A Textual-based TUI application for real-time database monitoring,
watcher management, and interactive database setup wizards.

Features:
- Real-time dashboard with database health, watcher status, live activity
- Interactive wizard for creating new databases
- Pattern presets (SpecStory, Documentation, Code, etc.)
- Watcher controls (start/stop/toggle auto-watch)
"""

from .app import HybridRAGMonitor, run_monitor

__all__ = ['HybridRAGMonitor', 'run_monitor']
