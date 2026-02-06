# HybridRAG System Patterns

## Architecture Overview

HybridRAG follows a modular architecture with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│                   Entry Points                               │
│  hybridrag.py (CLI)  │  hybridrag_mcp/server.py (MCP)       │
└───────────────┬─────────────────────────┬───────────────────┘
                │                         │
┌───────────────▼─────────────────────────▼───────────────────┐
│              Configuration Layer                             │
│  registry.yaml  │  app_config.py  │  backend_config.py      │
└───────────────┬─────────────────────────┬───────────────────┘
                │                         │
┌───────────────▼─────────────────────────▼───────────────────┐
│                  Core Systems                                │
│  LightRAG Core  │  Ingestion  │  Watcher  │  Query Engine   │
└───────────────┬─────────────────────────┬───────────────────┘
                │                         │
┌───────────────▼─────────────────────────▼───────────────────┐
│                Backend Adapters                              │
│  PostgreSQL  │  JSON  │  MongoDB  │  Neo4j  │  Others       │
└─────────────────────────────────────────────────────────────┘
```

## Key Design Patterns

### 1. Registry-Based Configuration Resolution

**Pattern**: Single YAML file as source of truth for multi-database configs

**Location**: `src/database_registry.py`, `~/.hybridrag/registry.yaml`

**Implementation**:
```python
def resolve_database(db_name_or_path: str) -> DatabaseEntry:
    """
    Auto-resolve database config by name or path.

    Precedence:
    1. Exact name match in registry
    2. Source folder path match
    3. Working directory path match
    """
    registry = get_registry()

    # Try exact name match
    if db_name_or_path in registry.databases:
        return registry.databases[db_name_or_path]

    # Try path matching
    for db_entry in registry.databases.values():
        if db_entry.source_folder == db_name_or_path:
            return db_entry
        if db_entry.path == db_name_or_path:
            return db_entry

    raise ValueError(f"Database not found: {db_name_or_path}")
```

**Benefits**:
- Eliminates env var configuration hell
- Single file to edit for all database settings
- Portable across machines (just copy registry.yaml)
- Enables `--db specstory` instead of long paths

---

### 2. Backend Metadata Injection

**Pattern**: Append backend details to every MCP tool response

**Location**: `hybridrag_mcp/server.py`

**Implementation**:
```python
def get_backend_metadata_line() -> str:
    """
    Generate metadata line showing which backend is active.
    Masks credentials for security.
    """
    backend_type = os.getenv("BACKEND_TYPE", "json").lower()

    if backend_type == "postgres":
        host = os.getenv("POSTGRES_HOST", "localhost")
        port = os.getenv("POSTGRES_PORT", "5432")
        db = os.getenv("POSTGRES_DB", "lightrag")

        # Build connection string
        user = os.getenv("POSTGRES_USER", "user")
        password = os.getenv("POSTGRES_PASSWORD", "")

        if password:
            conn_str = f"postgresql://{user}:****@{host}:{port}/{db}"
        else:
            conn_str = f"postgresql://{user}@{host}:{port}/{db}"

        return f"\n\n---\n*Backend: PostgreSQL ({conn_str})*"

    elif backend_type == "json":
        db_path = os.getenv("HYBRIDRAG_DATABASE", "./lightrag_db")
        return f"\n\n---\n*Backend: JSON (filesystem at {db_path})*"

    # ... other backends ...

    return f"\n\n---\n*Backend: {backend_type}*"
```

**Benefits**:
- Transparency: users always know which backend served query
- Debugging: immediately see if wrong backend is active
- Security: credentials masked with `****`
- Consistent format across all MCP tools

---

### 3. Config Module Split by Concern

**Pattern**: Separate app configuration from backend configuration

**Structure**:
```
src/config/
├── __init__.py           # Re-exports for backward compatibility
├── app_config.py         # Application-level settings
└── backend_config.py     # Backend connection configs
```

**app_config.py**:
```python
@dataclass
class HybridRAGConfig:
    """Main application configuration."""
    lightrag: LightRAGConfig
    ingestion: IngestionConfig
    search: SearchConfig
    system: SystemConfig

@dataclass
class LightRAGConfig:
    """LightRAG-specific settings."""
    working_dir: str
    model_name: str
    embedding_model: str
    chunk_size: int
    chunk_overlap: int
```

**backend_config.py**:
```python
class BackendType(Enum):
    """Supported backend types."""
    JSON = "json"
    POSTGRES = "postgres"
    MONGODB = "mongodb"
    NEO4J = "neo4j"
    MILVUS = "milvus"
    QDRANT = "qdrant"
    FAISS = "faiss"
    REDIS = "redis"
    MEMGRAPH = "memgraph"

@dataclass
class BackendConfig:
    """Backend connection configuration."""
    type: BackendType
    host: Optional[str] = None
    port: Optional[int] = None
    database: Optional[str] = None
    # ... connection params
```

**Benefits**:
- Clear separation of concerns
- Easier to maintain and test
- Backend configs can be registry-sourced or env-sourced
- App configs are environment-agnostic

---

### 4. Model Override Precedence Chain

**Pattern**: Explicit fallback chain for model selection

**Location**: `hybridrag.py`, `src/lightrag_core.py`

**Precedence**:
```
1. CLI --model flag (highest priority)
2. model_config.yaml file
3. db_entry.model_config.llm_model (from registry)
4. DEPLOYMENT_MODEL environment variable
5. gpt-4o-mini (default fallback)
```

**Implementation**:
```python
def resolve_model(
    cli_model: Optional[str],
    db_entry: Optional[DatabaseEntry],
) -> str:
    """Resolve which model to use via precedence chain."""

    # 1. CLI flag wins
    if cli_model:
        return cli_model

    # 2. Check model_config.yaml (if exists)
    model_config_path = Path("model_config.yaml")
    if model_config_path.exists():
        with open(model_config_path) as f:
            config = yaml.safe_load(f)
            if config.get("llm_model"):
                return config["llm_model"]

    # 3. Database registry model config
    if db_entry and db_entry.model_config:
        if db_entry.model_config.get("llm_model"):
            return db_entry.model_config["llm_model"]

    # 4. Environment variable
    if os.getenv("DEPLOYMENT_MODEL"):
        return os.getenv("DEPLOYMENT_MODEL")

    # 5. Default fallback
    return "gpt-4o-mini"
```

**Benefits**:
- Predictable: clear order of precedence
- Flexible: override at multiple levels
- Explicit: no hidden defaults
- Testable: easy to verify which source was used

---

### 5. Credential Masking with urllib.parse

**Pattern**: Use URL parsing instead of regex for credential masking

**Location**: `src/utils/backend_utils.py`

**Implementation**:
```python
from urllib.parse import urlparse, urlunparse

def mask_credentials(connection_string: str) -> str:
    """
    Mask password in connection string using URL parsing.
    Handles special characters better than regex.
    """
    try:
        parsed = urlparse(connection_string)

        # If no password, return as-is
        if not parsed.password:
            return connection_string

        # Replace password with ****
        masked_netloc = f"{parsed.username}:****@{parsed.hostname}"
        if parsed.port:
            masked_netloc += f":{parsed.port}"

        # Rebuild URL
        masked = urlunparse((
            parsed.scheme,
            masked_netloc,
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment
        ))

        return masked
    except Exception:
        # Fallback: mask everything after ://
        return connection_string.split("://")[0] + "://****"
```

**Benefits**:
- Handles special chars in passwords (!, @, #, etc.)
- Handles IPv6 addresses correctly
- More robust than fragile regex patterns
- Standard library (no dependencies)

**Replaces Fragile Regex**:
```python
# OLD (brittle):
import re
masked = re.sub(r'://(.*?):(.*?)@', r'://\1:****@', conn_str)

# NEW (robust):
from urllib.parse import urlparse, urlunparse
masked = mask_credentials(conn_str)
```

---

### 6. Delta Ingestion with Timestamp Tracking

**Pattern**: Only process files newer than last ingestion

**Location**: `src/ingestion/file_watcher.py`

**Implementation**:
```python
class FileWatcher:
    def __init__(self, db_path: Path):
        self.timestamp_file = db_path / ".last_specstory_watch"

    def get_last_run_time(self) -> datetime:
        """Read last ingestion timestamp."""
        if self.timestamp_file.exists():
            timestamp_str = self.timestamp_file.read_text().strip()
            return datetime.fromisoformat(timestamp_str)
        return datetime.min  # Process all files if first run

    def update_last_run_time(self):
        """Update timestamp to current time."""
        now = datetime.now(timezone.utc)
        self.timestamp_file.write_text(now.isoformat())

    def should_process_file(self, file_path: Path) -> bool:
        """Check if file is newer than last run."""
        last_run = self.get_last_run_time()
        file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)
        return file_mtime > last_run
```

**Benefits**:
- Efficient: only process changed files
- Fast restarts: watcher doesn't reprocess everything
- Simple: just compare modification times
- Reliable: uses filesystem timestamps

---

### 7. MCP Tool Tiered Architecture

**Pattern**: Organize tools by speed tier to guide LLM query patterns

**Location**: `hybridrag_mcp/server.py`

**Tiers**:
```
T1 (Recon) - Instant (<1s):
  - database_status: Get DB stats
  - health_check: Verify system health
  - get_logs: View ingestion history

T2 (Tactical) - Fast (<10s):
  - local_query: Entity-focused retrieval
  - extract_context: Raw context without LLM

T3 (Strategic) - Medium (10-60s):
  - global_query: Community summaries
  - hybrid_query: Combined local+global (recommended)
  - query: Flexible mode selection

T4 (Deep Intel) - Slow (60-900s):
  - multihop_query: Multi-hop reasoning with sub-queries
```

**Implementation**:
```python
# T1 tools: synchronous, no task flag
@mcp.tool()
def hybridrag_database_status() -> str:
    """T1 Recon: Get database stats (instant)."""
    # ... synchronous implementation ...

# T2 tools: synchronous, fast
@mcp.tool()
def hybridrag_local_query(query: str, top_k: int = 10) -> str:
    """T2 Tactical: Entity-focused query (<10s)."""
    # ... fast synchronous query ...

# T3 tools: async, background task
@mcp.tool(task=True)
async def hybridrag_hybrid_query(ctx: Context, query: str, top_k: int = 15) -> str:
    """T3 Strategic: Combined query (10-60s). Run as background task."""
    # ... async implementation with task progress ...

# T4 tools: async, long timeout, background task
@mcp.tool(task=True)
async def hybridrag_multihop_query(ctx: Context, query: str, max_hops: int = 3) -> str:
    """T4 Deep Intel: Multi-hop reasoning (60-900s). Background task required."""
    # ... complex async implementation ...
```

**Benefits**:
- Guides LLM to use faster tools first
- Background tasks prevent timeout failures
- Clear expectations for query complexity
- Progressive enhancement: start simple, escalate if needed

---

### 8. CLI Installability Pattern

**Pattern**: Make CLI command available system-wide via pyproject.toml

**Location**: `pyproject.toml`

**Implementation**:
```toml
[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.build_meta"

[project.scripts]
hybridrag = "hybridrag:main"

[tool.setuptools]
py-modules = ["hybridrag"]

[tool.setuptools.packages.find]
where = ["."]
include = ["src*", "hybridrag_mcp*"]
```

**Installation**:
```bash
# Install in editable mode
pip install -e .
# or
uv pip install -e .

# Now 'hybridrag' command is available:
hybridrag --db specstory query --text "test"
```

**Benefits**:
- No need to type `python hybridrag.py`
- Works from any directory
- Standard Python packaging approach
- Easy to distribute as package

---

### 9. Diagnostic Logging for MCP Tools

**Pattern**: Rotating log buffer for MCP request/response debugging

**Location**: `hybridrag_mcp/diagnostic_logging.py`, `hybridrag_mcp/server.py`

**Implementation**:
```python
from collections import deque

class DiagnosticStore:
    """Rotating buffer for MCP tool logs."""
    def __init__(self, maxlen: int = 100):
        self.logs = deque(maxlen=maxlen)

    def add(self, entry: dict):
        self.logs.append(entry)

    def get_recent(self, n: int = 10) -> list:
        return list(self.logs)[-n:]

# Initialize store
DIAGNOSTIC_STORE = DiagnosticStore(maxlen=100)

# Install handler that captures tool calls
install_diagnostic_handler(logger, DIAGNOSTIC_STORE)

# Retrieve via MCP tool
@mcp.tool()
def hybridrag_get_logs(limit: int = 10) -> str:
    """Get recent diagnostic logs."""
    logs = DIAGNOSTIC_STORE.get_recent(limit)
    return format_logs_as_markdown(logs)
```

**Benefits**:
- Debug MCP tool issues without restarting Claude
- See full request/response history
- No filesystem I/O (in-memory buffer)
- Auto-rotating (oldest entries dropped)

---

## Multi-Backend Support Pattern

HybridRAG's architecture allows 9 different backend types with a unified interface:

**Backend Adapter Interface**:
```python
class BackendAdapter(ABC):
    @abstractmethod
    def insert_entity(self, entity: Entity) -> None:
        pass

    @abstractmethod
    def insert_relationship(self, rel: Relationship) -> None:
        pass

    @abstractmethod
    def query_local(self, query: str, top_k: int) -> List[Entity]:
        pass

    @abstractmethod
    def query_global(self, query: str) -> str:
        pass
```

**Backends Implemented**:
1. **JSON** (filesystem, default)
2. **PostgreSQL** (pgvector + Apache AGE)
3. **MongoDB** (document store)
4. **Neo4j** (native graph)
5. **Milvus** (vector search)
6. **Qdrant** (vector search)
7. **Faiss** (vector index)
8. **Redis** (in-memory)
9. **Memgraph** (graph DB)

**Selection via Registry**:
```yaml
databases:
  specstory:
    backend_type: postgres
    backend_config:
      postgres_host: localhost
      postgres_port: 5433
      # ...
```

---

## Testing Patterns

### Integration Test Pattern
**Location**: `tests/test_hybridrag.py`

Test all MCP tools end-to-end with real database:
```python
@pytest.mark.asyncio
async def test_all_mcp_tools():
    """Test all 8 MCP tools with real PostgreSQL backend."""

    # 1. Setup backend
    os.environ["BACKEND_TYPE"] = "postgres"
    os.environ["POSTGRES_HOST"] = "localhost"
    # ...

    # 2. Test each tool
    result = await hybridrag_hybrid_query("test query", top_k=5)
    assert "Backend: PostgreSQL" in result

    result = await hybridrag_database_status()
    assert "Entities:" in result

    # ...
```

**Benefits**:
- Catch integration issues early
- Verify backend metadata appears
- Test real query performance
- Ensure all tools work together

---

## Architecture Decision Records (ADRs)

### ADR-001: Registry Over Environment Variables
**Decision**: Use YAML registry as single source of truth instead of env vars
**Rationale**: Easier to manage multiple databases, portable across machines
**Trade-offs**: Requires registry file, but eliminates env var hell

### ADR-002: Config Split by Concern
**Decision**: Separate app_config.py and backend_config.py
**Rationale**: Backend configs are registry-sourced, app configs are not
**Trade-offs**: More files, but clearer responsibilities

### ADR-003: Backend Metadata Injection
**Decision**: Append backend info to every MCP response
**Rationale**: Transparency and debugging without separate status calls
**Trade-offs**: Slight increase in response size (~50 chars)

### ADR-004: urllib.parse Over Regex
**Decision**: Use URL parsing for credential masking
**Rationale**: Handles edge cases (special chars, IPv6) better than regex
**Trade-offs**: None, standard library, more robust

### ADR-005: Model Precedence Chain
**Decision**: Explicit 5-level fallback chain for model selection
**Rationale**: Predictability and flexibility at multiple override levels
**Trade-offs**: More complex logic, but avoids confusion

### ADR-006: Timestamp-Based Delta Ingestion
**Decision**: Track last run time, only process newer files
**Rationale**: Efficient incremental updates without reprocessing everything
**Trade-offs**: Relies on filesystem mtimes (which can be reset)
