"""Backend configuration for HybridRAG storage systems.

This module defines the configuration dataclasses for pluggable storage backends,
allowing HybridRAG to use JSON files, PostgreSQL, or other database backends.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional
import urllib.parse


class BackendType(str, Enum):
    """Supported storage backend types."""

    JSON = "json"  # Default - JSON files + NanoVectorDB + NetworkX
    POSTGRESQL = "postgres"  # PostgreSQL + pgvector + AGE
    MONGODB = "mongodb"  # MongoDB (future)

    @classmethod
    def default(cls) -> "BackendType":
        """Return the default backend type."""
        return cls.JSON

    @classmethod
    def from_string(cls, value: str) -> "BackendType":
        """Parse backend type from string (case-insensitive)."""
        value_lower = value.lower().strip()
        for member in cls:
            if member.value == value_lower:
                return member
        raise ValueError(
            f"Invalid backend type: {value}. "
            f"Valid types: {[m.value for m in cls]}"
        )


@dataclass
class BackendConfig:
    """Configuration for a storage backend.

    Supports JSON (default), PostgreSQL, and MongoDB backends.
    PostgreSQL configuration can be provided via individual parameters
    or a connection string.

    Attributes:
        backend_type: Type of storage backend (json, postgres, mongodb)
        postgres_*: PostgreSQL-specific connection parameters
        connection_string: Alternative to individual params for PostgreSQL
        vector_index_type: Vector index type (hnsw or ivfflat)
        file_size_warning_mb: Warn when any JSON file exceeds this size
        total_size_warning_mb: Warn when total JSON storage exceeds this size
        performance_degradation_pct: Warn when ingestion slows by this percentage
    """

    # Backend type selection
    backend_type: BackendType = BackendType.JSON

    # PostgreSQL-specific settings
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "hybridrag"
    postgres_password: Optional[str] = None  # From env or secrets
    postgres_database: str = "hybridrag"
    postgres_workspace: str = "default"  # Logical isolation
    postgres_ssl_mode: str = "prefer"  # disable, require, verify-ca, verify-full
    postgres_max_connections: int = 10

    # Connection string (alternative to individual params)
    connection_string: Optional[str] = None

    # Vector index configuration
    vector_index_type: str = "hnsw"  # hnsw or ivfflat
    hnsw_m: int = 16
    hnsw_ef: int = 64

    # Extra backend-specific options
    extra_options: Dict[str, Any] = field(default_factory=dict)

    # Monitoring thresholds (for JSON backend warnings)
    file_size_warning_mb: int = 500  # Warn when any file exceeds this
    total_size_warning_mb: int = 2048  # Warn when total exceeds 2GB
    performance_degradation_pct: int = 50  # Warn when ingestion slows by this %

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        # Convert string backend_type to enum if needed
        if isinstance(self.backend_type, str):
            self.backend_type = BackendType.from_string(self.backend_type)

        # Validate port range
        if not 1 <= self.postgres_port <= 65535:
            raise ValueError(f"postgres_port must be 1-65535, got {self.postgres_port}")

        # Validate max connections
        if not 1 <= self.postgres_max_connections <= 100:
            raise ValueError(
                f"postgres_max_connections must be 1-100, got {self.postgres_max_connections}"
            )

        # Validate vector index type
        if self.vector_index_type not in ("hnsw", "ivfflat"):
            raise ValueError(
                f"vector_index_type must be 'hnsw' or 'ivfflat', got {self.vector_index_type}"
            )

    def get_storage_classes(self) -> Dict[str, str]:
        """Return LightRAG storage class names for this backend.

        Returns:
            Dict mapping storage type to LightRAG class name
        """
        if self.backend_type == BackendType.JSON:
            return {
                "kv_storage": "JsonKVStorage",
                "vector_storage": "NanoVectorDBStorage",
                "graph_storage": "NetworkXStorage",
                "doc_status_storage": "JsonDocStatusStorage",
            }
        elif self.backend_type == BackendType.POSTGRESQL:
            return {
                "kv_storage": "PGKVStorage",
                "vector_storage": "PGVectorStorage",
                "graph_storage": "PGGraphStorage",
                "doc_status_storage": "PGDocStatusStorage",
            }
        elif self.backend_type == BackendType.MONGODB:
            return {
                "kv_storage": "MongoKVStorage",
                "vector_storage": "MongoVectorDBStorage",
                "graph_storage": "MongoGraphStorage",
                "doc_status_storage": "MongoDocStatusStorage",
            }
        else:
            raise ValueError(f"Unsupported backend type: {self.backend_type}")

    def get_env_vars(self) -> Dict[str, str]:
        """Return environment variables for LightRAG configuration.

        Returns:
            Dict of environment variable names to values
        """
        if self.backend_type == BackendType.POSTGRESQL:
            env = {
                "POSTGRES_HOST": self.postgres_host,
                "POSTGRES_PORT": str(self.postgres_port),
                "POSTGRES_USER": self.postgres_user,
                "POSTGRES_DATABASE": self.postgres_database,
                "POSTGRES_WORKSPACE": self.postgres_workspace,
            }
            if self.postgres_password:
                env["POSTGRES_PASSWORD"] = self.postgres_password
            return env
        return {}

    def get_connection_string(self) -> Optional[str]:
        """Build PostgreSQL connection string from parameters.

        Returns:
            Connection string or None if not PostgreSQL backend
        """
        if self.backend_type != BackendType.POSTGRESQL:
            return None

        if self.connection_string:
            return self.connection_string

        # Build from individual parameters
        password_part = f":{self.postgres_password}" if self.postgres_password else ""
        return (
            f"postgresql://{self.postgres_user}{password_part}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_database}"
        )

    @classmethod
    def from_connection_string(cls, conn_str: str) -> "BackendConfig":
        """Parse PostgreSQL connection string.

        Args:
            conn_str: PostgreSQL URI (postgresql://user:pass@host:port/database)

        Returns:
            BackendConfig configured for PostgreSQL
        """
        parsed = urllib.parse.urlparse(conn_str)
        return cls(
            backend_type=BackendType.POSTGRESQL,
            postgres_host=parsed.hostname or "localhost",
            postgres_port=parsed.port or 5432,
            postgres_user=parsed.username or "hybridrag",
            postgres_password=parsed.password,
            postgres_database=parsed.path.lstrip("/") or "hybridrag",
            connection_string=conn_str,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BackendConfig":
        """Create BackendConfig from dictionary.

        Args:
            data: Dictionary with configuration values

        Returns:
            BackendConfig instance
        """
        # Handle backend_type conversion
        if "backend_type" in data and isinstance(data["backend_type"], str):
            data = data.copy()
            data["backend_type"] = BackendType.from_string(data["backend_type"])
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization.

        Returns:
            Dict with configuration values (password excluded)
        """
        result = {
            "backend_type": self.backend_type.value,
            "postgres_host": self.postgres_host,
            "postgres_port": self.postgres_port,
            "postgres_user": self.postgres_user,
            "postgres_database": self.postgres_database,
            "postgres_workspace": self.postgres_workspace,
            "postgres_ssl_mode": self.postgres_ssl_mode,
            "postgres_max_connections": self.postgres_max_connections,
            "vector_index_type": self.vector_index_type,
            "hnsw_m": self.hnsw_m,
            "hnsw_ef": self.hnsw_ef,
            "file_size_warning_mb": self.file_size_warning_mb,
            "total_size_warning_mb": self.total_size_warning_mb,
            "performance_degradation_pct": self.performance_degradation_pct,
        }
        if self.extra_options:
            result["extra_options"] = self.extra_options
        # Note: password is intentionally excluded for security
        return result
