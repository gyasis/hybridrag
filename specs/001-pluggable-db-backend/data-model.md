# Data Model: Pluggable Database Backend System

**Feature Branch**: `001-pluggable-db-backend`
**Date**: 2025-12-19

## Entity Definitions

### BackendType (Enum)

Enumeration of supported storage backend types.

```python
from enum import Enum

class BackendType(str, Enum):
    """Supported storage backend types."""
    JSON = "json"           # Default - JSON files + NanoVectorDB + NetworkX
    POSTGRESQL = "postgres" # PostgreSQL + pgvector + AGE
    MONGODB = "mongodb"     # MongoDB (future)

    @classmethod
    def default(cls) -> "BackendType":
        return cls.JSON
```

**Validation Rules**:
- Must be one of defined enum values
- Case-insensitive matching on input

### BackendConfig (Dataclass)

Configuration for storage backend connection.

```python
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

@dataclass
class BackendConfig:
    """Configuration for a storage backend."""

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
    file_size_warning_mb: int = 500        # Warn when any file exceeds this
    total_size_warning_mb: int = 2048      # Warn when total exceeds 2GB
    performance_degradation_pct: int = 50  # Warn when ingestion slows by this %

    def get_storage_classes(self) -> Dict[str, str]:
        """Return LightRAG storage class names for this backend."""
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
        """Return environment variables for LightRAG configuration."""
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

    @classmethod
    def from_connection_string(cls, conn_str: str) -> "BackendConfig":
        """Parse PostgreSQL connection string."""
        # postgresql://user:pass@host:port/database
        import urllib.parse
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
```

**Validation Rules**:
- `postgres_port`: 1-65535
- `postgres_max_connections`: 1-100
- `vector_index_type`: Must be "hnsw" or "ivfflat"
- `connection_string`: Must be valid PostgreSQL URI if provided

### DatabaseEntry (Extended)

Extension to existing `DatabaseEntry` in `database_registry.py`.

```python
@dataclass
class DatabaseEntry:
    """Registry entry for a HybridRAG database."""

    # Existing fields
    name: str
    path: str
    source_folder: Optional[str] = None
    source_type: str = "filesystem"
    auto_watch: bool = False
    watch_interval: int = 300

    # NEW: Backend configuration
    backend_type: BackendType = BackendType.JSON
    backend_config: Optional[Dict[str, Any]] = None

    def get_backend_config(self) -> BackendConfig:
        """Construct BackendConfig from stored settings."""
        if self.backend_config is None:
            return BackendConfig(backend_type=self.backend_type)
        return BackendConfig(
            backend_type=self.backend_type,
            **self.backend_config
        )
```

**YAML Serialization**:
```yaml
databases:
  specstory:
    name: specstory
    path: /home/user/databases/specstory_db
    source_folder: /home/user/jira-issues
    source_type: specstory
    auto_watch: true
    # NEW fields
    backend_type: postgres
    backend_config:
      postgres_host: localhost
      postgres_port: 5432
      postgres_user: hybridrag
      postgres_database: hybridrag
      postgres_workspace: specstory
```

### MigrationJob (Dataclass)

Represents a data migration operation.

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List
from enum import Enum

class MigrationStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"

@dataclass
class MigrationCheckpoint:
    """Checkpoint for resumable migration."""
    store_name: str           # e.g., "kv_store_full_docs"
    last_key: Optional[str]   # Last successfully migrated key
    migrated_count: int       # Keys migrated in this store
    total_count: int          # Total keys in source store

@dataclass
class MigrationJob:
    """Represents a migration operation."""

    job_id: str
    database_name: str
    source_backend: BackendType
    target_backend: BackendType

    # Progress tracking
    status: MigrationStatus = MigrationStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Checkpoint for resume
    checkpoints: List[MigrationCheckpoint] = field(default_factory=list)
    current_store: Optional[str] = None

    # Statistics
    total_records: int = 0
    migrated_records: int = 0
    failed_records: int = 0

    # Error tracking
    last_error: Optional[str] = None

    @property
    def progress_percent(self) -> float:
        if self.total_records == 0:
            return 0.0
        return (self.migrated_records / self.total_records) * 100

    @property
    def is_resumable(self) -> bool:
        return self.status in (MigrationStatus.PAUSED, MigrationStatus.FAILED)
```

**State Transitions**:
```
PENDING → IN_PROGRESS → COMPLETED
                ↓
              FAILED → IN_PROGRESS (resume)
                ↓
              PAUSED → IN_PROGRESS (resume)
```

### StorageMetrics (Dataclass)

Storage statistics for backend status command.

```python
@dataclass
class StorageMetrics:
    """Storage statistics for a database."""

    backend_type: BackendType

    # File sizes (JSON backend)
    file_sizes: Dict[str, int] = field(default_factory=dict)
    total_size_bytes: int = 0

    # Record counts
    entity_count: int = 0
    relation_count: int = 0
    chunk_count: int = 0
    doc_count: int = 0

    # Health status
    is_connected: bool = True
    connection_latency_ms: Optional[float] = None

    # Warnings
    warnings: List[str] = field(default_factory=list)

    # Migration threshold (default 500MB)
    MIGRATION_WARNING_THRESHOLD = 500 * 1024 * 1024

    def check_migration_warnings(self) -> None:
        """Add warnings if files exceed threshold."""
        for filename, size in self.file_sizes.items():
            if size > self.MIGRATION_WARNING_THRESHOLD:
                self.warnings.append(
                    f"{filename}: {size / (1024*1024):.1f}MB exceeds threshold. "
                    "Consider migrating to PostgreSQL backend."
                )

    def to_human_readable(self) -> Dict[str, str]:
        """Convert sizes to human-readable format."""
        def human_size(bytes_val: int) -> str:
            for unit in ['B', 'KB', 'MB', 'GB']:
                if bytes_val < 1024:
                    return f"{bytes_val:.1f} {unit}"
                bytes_val /= 1024
            return f"{bytes_val:.1f} TB"

        return {
            filename: human_size(size)
            for filename, size in self.file_sizes.items()
        }
```

## Entity Relationships

```
┌─────────────────┐     1:1      ┌───────────────────┐
│  DatabaseEntry  │─────────────▶│   BackendConfig   │
└─────────────────┘              └───────────────────┘
        │                                 │
        │ 1:N                             │
        ▼                                 ▼
┌─────────────────┐              ┌───────────────────┐
│  MigrationJob   │              │   BackendType     │
└─────────────────┘              │   (Enum)          │
        │                        └───────────────────┘
        │ 1:N
        ▼
┌─────────────────────┐
│ MigrationCheckpoint │
└─────────────────────┘
```

## Database Schema (PostgreSQL)

### Configuration Tables (HybridRAG-specific)

```sql
-- Migration job tracking
CREATE TABLE IF NOT EXISTS hybridrag_migration_jobs (
    job_id VARCHAR(64) PRIMARY KEY,
    database_name VARCHAR(255) NOT NULL,
    source_backend VARCHAR(32) NOT NULL,
    target_backend VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    total_records INTEGER DEFAULT 0,
    migrated_records INTEGER DEFAULT 0,
    failed_records INTEGER DEFAULT 0,
    last_error TEXT,
    checkpoints JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for status queries
CREATE INDEX idx_migration_status ON hybridrag_migration_jobs(status);
```

### LightRAG Tables (Created automatically)

LightRAG creates these tables when using PostgreSQL backend:

```sql
-- Key-Value storage (per workspace)
CREATE TABLE lightrag_kv_store (
    workspace VARCHAR(255),
    namespace VARCHAR(255),
    key VARCHAR(512),
    value JSONB,
    PRIMARY KEY (workspace, namespace, key)
);

-- LLM cache (replaces JSON cache file)
CREATE TABLE lightrag_llm_cache (
    id VARCHAR(512) PRIMARY KEY,
    workspace VARCHAR(255),
    original_prompt TEXT,
    return_value TEXT,
    chunk_id VARCHAR(255),
    cache_type VARCHAR(32),
    queryparam JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Vector storage with pgvector
CREATE TABLE lightrag_vdb_chunks (
    id VARCHAR(512) PRIMARY KEY,
    workspace VARCHAR(255),
    content TEXT,
    embedding vector(1536),  -- Dimension matches model
    metadata JSONB
);

-- HNSW index for fast similarity search
CREATE INDEX idx_chunks_embedding ON lightrag_vdb_chunks
USING hnsw (embedding vector_cosine_ops);

-- Similar tables for entities and relationships
```

## Validation Rules Summary

| Entity | Field | Rule |
|--------|-------|------|
| BackendConfig | postgres_port | 1-65535 |
| BackendConfig | postgres_max_connections | 1-100 |
| BackendConfig | vector_index_type | "hnsw" or "ivfflat" |
| BackendConfig | connection_string | Valid PostgreSQL URI |
| MigrationJob | source_backend | Must differ from target_backend |
| MigrationJob | status | Valid MigrationStatus enum |
| StorageMetrics | file_sizes | Non-negative values |
