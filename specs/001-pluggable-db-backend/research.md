# Phase 0 Research: Pluggable Database Backend System

**Feature Branch**: `001-pluggable-db-backend`
**Date**: 2025-12-19
**Spec**: [spec.md](./spec.md)

## Executive Summary

**Key Finding**: LightRAG v1.4.9.8 already provides complete pluggable storage backend support. No custom abstraction layer needed - we only need to expose LightRAG's configuration through HybridRAG's config system.

## LightRAG Storage Backend Analysis

### Available Storage Implementations

Located in `/lightrag/kg/` module:

#### KV Storage (`BaseKVStorage`)
| Class | Backend | Use Case |
|-------|---------|----------|
| `JsonKVStorage` | JSON files | Default, single-user |
| `PGKVStorage` | PostgreSQL | Production, multi-user |
| `MongoKVStorage` | MongoDB | Document-oriented |
| `RedisKVStorage` | Redis | High-speed caching |

#### Vector Storage (`BaseVectorStorage`)
| Class | Backend | Use Case |
|-------|---------|----------|
| `NanoVectorDBStorage` | NanoVectorDB | Default, lightweight |
| `PGVectorStorage` | PostgreSQL + pgvector | Production, scalable |
| `MongoVectorDBStorage` | MongoDB | Document-oriented |
| `FaissVectorDBStorage` | FAISS | High-performance local |
| `MilvusVectorDBStorage` | Milvus | Enterprise vector DB |
| `QdrantVectorDBStorage` | Qdrant | Cloud-native vector |

#### Graph Storage (`BaseGraphStorage`)
| Class | Backend | Use Case |
|-------|---------|----------|
| `NetworkXStorage` | NetworkX | Default, in-memory |
| `PGGraphStorage` | PostgreSQL + AGE | Production, SQL-based |
| `MongoGraphStorage` | MongoDB | Document-oriented |
| `Neo4JStorage` | Neo4j | Enterprise graph |
| `MemgraphStorage` | Memgraph | Real-time graph |

#### Doc Status Storage (`DocStatusStorage`)
| Class | Backend | Use Case |
|-------|---------|----------|
| `JsonDocStatusStorage` | JSON files | Default |
| `PGDocStatusStorage` | PostgreSQL | Production |
| `MongoDocStatusStorage` | MongoDB | Document-oriented |
| `RedisDocStatusStorage` | Redis | High-speed |

### Full Backend Coverage Matrix

| Backend | KV | Vector | Graph | DocStatus | Production Ready |
|---------|:--:|:------:|:-----:|:---------:|:----------------:|
| **JSON/File** | ✅ | ✅ | ✅ | ✅ | Development |
| **PostgreSQL** | ✅ | ✅ | ✅ | ✅ | **Production** |
| **MongoDB** | ✅ | ✅ | ✅ | ✅ | **Production** |
| **Redis** | ✅ | ❌ | ❌ | ✅ | Caching |
| **Neo4j** | ❌ | ❌ | ✅ | ❌ | Graph-only |
| **Memgraph** | ❌ | ❌ | ✅ | ❌ | Graph-only |
| **Milvus** | ❌ | ✅ | ❌ | ❌ | Vector-only |
| **Qdrant** | ❌ | ✅ | ❌ | ❌ | Vector-only |
| **FAISS** | ❌ | ✅ | ❌ | ❌ | Vector-only |

**Decision**: Use PostgreSQL as primary alternative backend (full coverage).
**Rationale**: Only PostgreSQL and MongoDB have complete coverage. PostgreSQL is more common in enterprise environments.
**Alternatives Considered**: MongoDB (equally capable but less common), mixed backends (added complexity).

## Configuration Methods

### Method 1: Environment Variables (Recommended)

```bash
# Storage class selection
LIGHTRAG_KV_STORAGE=PGKVStorage
LIGHTRAG_VECTOR_STORAGE=PGVectorStorage
LIGHTRAG_GRAPH_STORAGE=PGGraphStorage
LIGHTRAG_DOC_STATUS_STORAGE=PGDocStatusStorage

# PostgreSQL connection
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=hybridrag
POSTGRES_PASSWORD=secret
POSTGRES_DATABASE=hybridrag
POSTGRES_WORKSPACE=production
```

### Method 2: Constructor Parameters

```python
from lightrag import LightRAG

rag = LightRAG(
    working_dir="./storage",
    kv_storage="PGKVStorage",
    vector_storage="PGVectorStorage",
    graph_storage="PGGraphStorage",
    doc_status_storage="PGDocStatusStorage",
    workspace="production"
)
```

### Method 3: config.ini File

```ini
[postgres]
host = localhost
port = 5432
user = hybridrag
password = secret
database = hybridrag
```

**Decision**: Support all three methods with priority: ENV > config.ini > constructor defaults.
**Rationale**: Aligns with 12-factor app principles, supports Docker/Kubernetes deployments.

## PostgreSQL Implementation Details

### postgres_impl.py Analysis (215KB)

#### PostgreSQLDB Class
- Connection pool management with asyncpg
- SSL/TLS support (disable, require, verify-ca, verify-full)
- Retry with exponential backoff for transient errors
- Auto-creates pgvector extension
- Auto-creates Apache AGE extension for graph

#### Key Configuration Options
```python
{
    "host": "localhost",
    "port": 5432,
    "user": "hybridrag",
    "password": "secret",
    "database": "hybridrag",
    "workspace": "default",  # Logical isolation
    "max_connections": 10,
    "ssl_mode": "require",  # Optional SSL
    "vector_index_type": "hnsw",  # or "ivfflat"
    "hnsw_m": 16,  # HNSW parameter
    "hnsw_ef": 64,  # HNSW parameter
    "connection_retry_attempts": 3,
    "connection_retry_backoff": 1.0,
}
```

#### Tables Created

**KV Storage Tables** (per namespace):
- `lightrag_kv_store` - Generic key-value storage
- `lightrag_llm_cache` - LLM response cache (major memory saver!)

**Vector Storage Tables**:
- `lightrag_vdb_chunks` - Text chunk embeddings
- `lightrag_vdb_entities` - Entity embeddings
- `lightrag_vdb_relationships` - Relationship embeddings
- Indexes: HNSW or IVFFlat for similarity search

**Graph Storage Tables** (Apache AGE):
- `graph_chunk_entity_relation` - Graph stored as AGE graph

**Doc Status Tables**:
- `lightrag_doc_status` - Document processing status

### pgvector Extension

Required for vector similarity search:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Included in `pgvector/pgvector:pg16` Docker image.

### Apache AGE Extension

Optional, for graph storage:
```sql
CREATE EXTENSION IF NOT EXISTS age;
```

Falls back to PostgreSQL tables if not available.

## Memory Analysis

### Current JSON Backend (3.5GB database)

| File | Size | Loaded to Memory |
|------|------|------------------|
| `vdb_relationships.json` | 1.3 GB | Yes - causes OOM |
| `kv_store_llm_response_cache.json` | 896 MB | Yes - major issue |
| `vdb_entities.json` | 721 MB | Yes |
| `vdb_chunks.json` | 308 MB | Yes |
| `graph.graphml` | 118 MB | Yes |
| Other | ~200 MB | Yes |
| **Total in memory** | **~3.5 GB** | **OOM at 5-7GB** |

### PostgreSQL Backend (Expected)

| Component | Memory Usage |
|-----------|--------------|
| Connection pool (10 conn) | ~50 MB |
| Query result buffers | ~100 MB |
| Application overhead | ~50 MB |
| **Total expected** | **< 500 MB** |

**Memory reduction**: 90%+ (from 5-7GB to <500MB)

## Docker Provisioning

### Recommended Image

```yaml
image: pgvector/pgvector:pg16
```

Features:
- PostgreSQL 16
- pgvector extension pre-installed
- Optimized for vector operations

### Docker Compose Configuration

```yaml
version: '3.8'
services:
  hybridrag-postgres:
    image: pgvector/pgvector:pg16
    container_name: hybridrag-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: hybridrag
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-hybridrag_default}
      POSTGRES_DB: hybridrag
    ports:
      - "5432:5432"
    volumes:
      - hybridrag-pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U hybridrag -d hybridrag"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  hybridrag-pgdata:
    driver: local
```

## Migration Strategy

### Approach: Use LightRAG's Storage Classes Directly

Since both JSON and PostgreSQL backends implement the same interface (`BaseKVStorage`, etc.), migration is straightforward:

```python
# Pseudo-code for migration
json_kv = JsonKVStorage(...)
pg_kv = PGKVStorage(...)

# Read from JSON
for key in json_kv.all_keys():
    value = json_kv.get(key)
    # Write to PostgreSQL
    pg_kv.upsert({key: value})
```

### Migration Steps

1. **Pause watcher** - Prevent concurrent writes
2. **Backup JSON files** - Safety net
3. **Initialize PostgreSQL** - Create tables/indexes
4. **Migrate KV stores** - Batch insert with progress
5. **Migrate vectors** - Batch insert embeddings
6. **Migrate graph** - Export/import GraphML or direct copy
7. **Migrate doc status** - Simple key-value copy
8. **Verify counts** - Compare source vs destination
9. **Update registry** - Point database to PostgreSQL
10. **Resume watcher** - With new backend

### Incremental/Resumable Support

Use checkpoint file:
```json
{
  "started_at": "2025-12-19T10:00:00Z",
  "current_store": "kv_store_full_docs",
  "last_key": "doc_abc123",
  "migrated_count": 15000,
  "total_count": 50000
}
```

## Decisions Summary

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Primary backend | PostgreSQL | Full coverage, enterprise standard |
| Config method | ENV vars + registry | 12-factor, flexible |
| Docker image | pgvector/pgvector:pg16 | pgvector pre-installed |
| Migration approach | Direct storage class copy | Leverages existing APIs |
| Workspace isolation | POSTGRES_WORKSPACE | Multi-tenant support |

## Open Questions (Resolved)

| Question | Resolution |
|----------|------------|
| Build custom abstraction? | No - use LightRAG's built-in |
| Which backends to support? | PostgreSQL first, MongoDB future |
| How to handle mixed backends? | Not supported in v1 (all-or-nothing) |
| Apache AGE required? | No - optional, falls back gracefully |

## Next Steps

1. **data-model.md**: Define `BackendConfig`, `BackendType` schemas
2. **contracts/**: Define CLI command interfaces
3. **quickstart.md**: Developer setup guide
4. **/speckit.tasks**: Generate implementation tasks
