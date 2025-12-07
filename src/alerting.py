#!/usr/bin/env python3
"""
HybridRAG Alerting System
=========================

Provides alerting for ingestion failures, watcher issues, and system problems.
Supports multiple notification channels: file logging, desktop notifications,
and webhook integrations.

Author: HybridRAG System
Date: 2025-12-07
"""

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional, Dict, Any, Callable
import subprocess

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertType(Enum):
    """Types of alerts."""
    INGESTION_FAILED = "ingestion_failed"
    INGESTION_PARTIAL = "ingestion_partial"
    WATCHER_STOPPED = "watcher_stopped"
    WATCHER_ERROR = "watcher_error"
    DATABASE_ERROR = "database_error"
    CONFIG_ERROR = "config_error"
    SYSTEM_ERROR = "system_error"


@dataclass
class Alert:
    """Represents an alert event."""
    alert_type: AlertType
    severity: AlertSeverity
    message: str
    database: str
    timestamp: datetime = field(default_factory=datetime.now)
    details: Dict[str, Any] = field(default_factory=dict)
    acknowledged: bool = False
    id: str = field(default="")

    def __post_init__(self):
        if not self.id:
            self.id = f"{self.alert_type.value}-{self.timestamp.strftime('%Y%m%d%H%M%S')}-{hash(self.message) % 10000:04d}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "alert_type": self.alert_type.value,
            "severity": self.severity.value,
            "message": self.message,
            "database": self.database,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details,
            "acknowledged": self.acknowledged,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Alert":
        return cls(
            id=data.get("id", ""),
            alert_type=AlertType(data["alert_type"]),
            severity=AlertSeverity(data["severity"]),
            message=data["message"],
            database=data["database"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            details=data.get("details", {}),
            acknowledged=data.get("acknowledged", False),
        )


class AlertStore:
    """Persistent storage for alerts."""

    def __init__(self, alerts_file: Optional[Path] = None):
        self.alerts_file = alerts_file or Path.home() / ".hybridrag" / "alerts.json"
        self.alerts_file.parent.mkdir(parents=True, exist_ok=True)
        self._alerts: List[Alert] = []
        self._load()

    def _load(self):
        """Load alerts from file."""
        if self.alerts_file.exists():
            try:
                with open(self.alerts_file, 'r') as f:
                    data = json.load(f)
                self._alerts = [Alert.from_dict(a) for a in data.get("alerts", [])]
            except Exception as e:
                logger.warning(f"Could not load alerts: {e}")
                self._alerts = []

    def _save(self):
        """Save alerts to file."""
        try:
            with open(self.alerts_file, 'w') as f:
                json.dump({"alerts": [a.to_dict() for a in self._alerts]}, f, indent=2)
        except Exception as e:
            logger.error(f"Could not save alerts: {e}")

    def add(self, alert: Alert):
        """Add a new alert."""
        self._alerts.append(alert)
        # Keep only last 1000 alerts
        if len(self._alerts) > 1000:
            self._alerts = self._alerts[-1000:]
        self._save()

    def get_all(self, include_acknowledged: bool = False) -> List[Alert]:
        """Get all alerts, optionally including acknowledged ones."""
        if include_acknowledged:
            return list(self._alerts)
        return [a for a in self._alerts if not a.acknowledged]

    def get_by_database(self, database: str, include_acknowledged: bool = False) -> List[Alert]:
        """Get alerts for a specific database."""
        alerts = self.get_all(include_acknowledged)
        return [a for a in alerts if a.database == database]

    def get_by_severity(self, severity: AlertSeverity, include_acknowledged: bool = False) -> List[Alert]:
        """Get alerts of a specific severity."""
        alerts = self.get_all(include_acknowledged)
        return [a for a in alerts if a.severity == severity]

    def acknowledge(self, alert_id: str) -> bool:
        """Acknowledge an alert."""
        for alert in self._alerts:
            if alert.id == alert_id:
                alert.acknowledged = True
                self._save()
                return True
        return False

    def acknowledge_all(self, database: Optional[str] = None):
        """Acknowledge all alerts, optionally for a specific database."""
        for alert in self._alerts:
            if database is None or alert.database == database:
                alert.acknowledged = True
        self._save()

    def clear_old(self, days: int = 7):
        """Clear alerts older than specified days."""
        cutoff = datetime.now().timestamp() - (days * 24 * 60 * 60)
        self._alerts = [a for a in self._alerts if a.timestamp.timestamp() > cutoff]
        self._save()

    def get_summary(self) -> Dict[str, int]:
        """Get summary of unacknowledged alerts by severity."""
        alerts = self.get_all(include_acknowledged=False)
        return {
            "critical": len([a for a in alerts if a.severity == AlertSeverity.CRITICAL]),
            "error": len([a for a in alerts if a.severity == AlertSeverity.ERROR]),
            "warning": len([a for a in alerts if a.severity == AlertSeverity.WARNING]),
            "info": len([a for a in alerts if a.severity == AlertSeverity.INFO]),
            "total": len(alerts),
        }


class AlertNotifier:
    """Handles alert notifications through various channels."""

    def __init__(self):
        self._handlers: List[Callable[[Alert], None]] = []
        # Register default handlers
        self._handlers.append(self._log_handler)

    def add_handler(self, handler: Callable[[Alert], None]):
        """Add a notification handler."""
        self._handlers.append(handler)

    def notify(self, alert: Alert):
        """Send alert through all registered handlers."""
        for handler in self._handlers:
            try:
                handler(alert)
            except Exception as e:
                logger.error(f"Alert handler failed: {e}")

    def _log_handler(self, alert: Alert):
        """Log alert to standard logger."""
        level_map = {
            AlertSeverity.INFO: logging.INFO,
            AlertSeverity.WARNING: logging.WARNING,
            AlertSeverity.ERROR: logging.ERROR,
            AlertSeverity.CRITICAL: logging.CRITICAL,
        }
        level = level_map.get(alert.severity, logging.INFO)
        logger.log(level, f"[ALERT] [{alert.database}] {alert.message}")

    @staticmethod
    def desktop_notification_handler(alert: Alert):
        """Send desktop notification (Linux/macOS)."""
        try:
            title = f"HybridRAG {alert.severity.value.upper()}"
            message = f"[{alert.database}] {alert.message}"

            # Try notify-send (Linux)
            if os.path.exists("/usr/bin/notify-send"):
                urgency_map = {
                    AlertSeverity.INFO: "low",
                    AlertSeverity.WARNING: "normal",
                    AlertSeverity.ERROR: "critical",
                    AlertSeverity.CRITICAL: "critical",
                }
                subprocess.run([
                    "notify-send",
                    "-u", urgency_map.get(alert.severity, "normal"),
                    title, message
                ], capture_output=True)
            # Try osascript (macOS)
            elif os.path.exists("/usr/bin/osascript"):
                subprocess.run([
                    "osascript", "-e",
                    f'display notification "{message}" with title "{title}"'
                ], capture_output=True)
        except Exception as e:
            logger.debug(f"Desktop notification failed: {e}")


class AlertManager:
    """
    Main alerting interface for the HybridRAG system.

    Usage:
        alert_manager = AlertManager()
        alert_manager.alert_ingestion_failed("specstory", "file.md", "Parse error")
    """

    _instance: Optional["AlertManager"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.store = AlertStore()
        self.notifier = AlertNotifier()
        self._initialized = True
        logger.info("AlertManager initialized")

    def _create_and_send(
        self,
        alert_type: AlertType,
        severity: AlertSeverity,
        message: str,
        database: str,
        details: Optional[Dict[str, Any]] = None
    ) -> Alert:
        """Create, store, and send an alert."""
        alert = Alert(
            alert_type=alert_type,
            severity=severity,
            message=message,
            database=database,
            details=details or {},
        )
        self.store.add(alert)
        self.notifier.notify(alert)
        return alert

    # Convenience methods for common alerts

    def alert_ingestion_failed(
        self,
        database: str,
        file_name: str,
        error: str,
        details: Optional[Dict[str, Any]] = None
    ) -> Alert:
        """Alert for a failed file ingestion."""
        return self._create_and_send(
            AlertType.INGESTION_FAILED,
            AlertSeverity.ERROR,
            f"Failed to ingest '{file_name}': {error}",
            database,
            {"file_name": file_name, "error": error, **(details or {})},
        )

    def alert_ingestion_partial(
        self,
        database: str,
        total: int,
        failed: int,
        details: Optional[Dict[str, Any]] = None
    ) -> Alert:
        """Alert for partial ingestion completion."""
        severity = AlertSeverity.WARNING if failed < total / 2 else AlertSeverity.ERROR
        return self._create_and_send(
            AlertType.INGESTION_PARTIAL,
            severity,
            f"Ingestion completed with errors: {failed}/{total} files failed",
            database,
            {"total": total, "failed": failed, **(details or {})},
        )

    def alert_watcher_stopped(
        self,
        database: str,
        reason: str = "Unknown",
        details: Optional[Dict[str, Any]] = None
    ) -> Alert:
        """Alert when watcher stops unexpectedly."""
        return self._create_and_send(
            AlertType.WATCHER_STOPPED,
            AlertSeverity.CRITICAL,
            f"Watcher stopped: {reason}",
            database,
            {"reason": reason, **(details or {})},
        )

    def alert_watcher_error(
        self,
        database: str,
        error: str,
        details: Optional[Dict[str, Any]] = None
    ) -> Alert:
        """Alert for watcher errors."""
        return self._create_and_send(
            AlertType.WATCHER_ERROR,
            AlertSeverity.ERROR,
            f"Watcher error: {error}",
            database,
            {"error": error, **(details or {})},
        )

    def alert_database_error(
        self,
        database: str,
        error: str,
        details: Optional[Dict[str, Any]] = None
    ) -> Alert:
        """Alert for database errors."""
        return self._create_and_send(
            AlertType.DATABASE_ERROR,
            AlertSeverity.ERROR,
            f"Database error: {error}",
            database,
            {"error": error, **(details or {})},
        )

    def alert_info(
        self,
        database: str,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ) -> Alert:
        """Create an info-level alert."""
        return self._create_and_send(
            AlertType.SYSTEM_ERROR,
            AlertSeverity.INFO,
            message,
            database,
            details,
        )

    # Query methods

    def get_alerts(
        self,
        database: Optional[str] = None,
        severity: Optional[AlertSeverity] = None,
        include_acknowledged: bool = False
    ) -> List[Alert]:
        """Get alerts with optional filtering."""
        alerts = self.store.get_all(include_acknowledged)
        if database:
            alerts = [a for a in alerts if a.database == database]
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        return alerts

    def get_summary(self) -> Dict[str, int]:
        """Get alert summary."""
        return self.store.get_summary()

    def acknowledge(self, alert_id: str) -> bool:
        """Acknowledge an alert."""
        return self.store.acknowledge(alert_id)

    def acknowledge_all(self, database: Optional[str] = None):
        """Acknowledge all alerts."""
        self.store.acknowledge_all(database)

    def enable_desktop_notifications(self):
        """Enable desktop notifications."""
        self.notifier.add_handler(AlertNotifier.desktop_notification_handler)
        logger.info("Desktop notifications enabled")


# Global instance accessor
def get_alert_manager() -> AlertManager:
    """Get the global AlertManager instance."""
    return AlertManager()
