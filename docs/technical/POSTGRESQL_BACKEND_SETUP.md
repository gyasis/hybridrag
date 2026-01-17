# PostgreSQL Backend Setup for HybridRAG

**Last Updated:** 2026-01-17
**Audience:** Developers setting up HybridRAG with PostgreSQL backend
**Difficulty:** Intermediate
**Time Required:** 10-15 minutes

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Critical Requirements](#critical-requirements)
4. [Quick Start (5 Commands)](#quick-start-5-commands)
5. [Docker Compose Setup](#docker-compose-setup)
6. [Database Registry Configuration](#database-registry-configuration)
7. [Verification Steps](#verification-steps)
8. [Troubleshooting](#troubleshooting)
9. [Migration from JSON to PostgreSQL](#migration-from-json-to-postgresql)
10. [Production Deployment Patterns](#production-deployment-patterns)
11. [Common Pitfalls](#common-pitfalls)
12. [Performance Optimization](#performance-optimization)
13. [Related Documentation](#related-documentation)

---

## Overview

HybridRAG uses [LightRAG](https://github.com/HKUDS/LightRAG) as its underlying RAG framework. LightRAG supports **dual-backend architecture**:

- **JSON backend** (default): File-based storage for small datasets
- **PostgreSQL backend**: Production-grade storage with graph + vector capabilities

This guide covers PostgreSQL backend setup, including the critical extensions required for LightRAG's graph-based retrieval.

---

## Prerequisites

Before starting, ensure you have:

- **Docker installed** (version 20.10 or higher)
- **Docker Compose installed** (version 2.0 or higher)
- **Basic PostgreSQL knowledge** (connection strings, extensions)
- **Understanding of LightRAG's architecture** (see [LightRAG documentation](https://github.com/HKUDS/LightRAG))

Optional but recommended:
- PostgreSQL client (`psql`) for manual verification
- Familiarity with vector embeddings and graph databases

---

## Critical Requirements

### 🚨 LightRAG Requires BOTH Extensions

**CRITICAL:** The official LightRAG documentation does NOT clearly state this requirement.

| Extension | Purpose | Why Required |
|-----------|---------|--------------|
| **Apache AGE** | Graph storage (nodes/edges) | LightRAG stores entity relationships as a graph structure |
| **pgvector** | Vector embeddings | LightRAG stores document/chunk embeddings for similarity search |

**Common Mistake:** Using `pgvector/pgvector:pg16` image → **FAILS** (missing AGE extension)

**Correct Approach:** Use `apache/age:latest` + install pgvector manually

### Why This Architecture?

LightRAG implements a **hybrid retrieval** strategy:

1. **Vector Search** (pgvector): Find semantically similar documents
2. **Graph Traversal** (AGE): Navigate entity relationships for context
3. **Hybrid Fusion**: Combine results for comprehensive answers

Without BOTH extensions, LightRAG initialization will fail with cryptic errors like:
```
ERROR: function create_graph(unknown) does not exist
ERROR: type "vector" does not exist
```

---

## Quick Start (5 Commands)

Get PostgreSQL running with both required extensions in under 5 minutes:

### Option 1: Direct Docker Commands (Development)

```bash
# 1. Start Apache AGE container with custom database name
docker run -d --name hybridrag-postgres \
  -e POSTGRES_USER=hybridrag \
  -e POSTGRES_PASSWORD=your_secure_password_2026 \
  -e POSTGRES_DB=specstory \
  -p 5434:5432 \
  apache/age:latest

# 2. Install pgvector extension
docker exec hybridrag-postgres bash -c \
  "apt-get update && apt-get install -y postgresql-17-pgvector"

# 3. Create both extensions in the database
docker exec hybridrag-postgres psql -U hybridrag -d specstory \
  -c "CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS age;"

# 4. Verify extensions are loaded
docker exec hybridrag-postgres psql -U hybridrag -d specstory \
  -c "SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector', 'age');"

# Expected output:
#  extname | extversion
# ---------+------------
#  vector  | 0.7.0
#  age     | 1.6.0

# 5. Configure HybridRAG
# Update ~/.hybridrag/registry.yaml with PostgreSQL connection details
# (See "Database Registry Configuration" section below)
```

**Key Points:**
- Port `5434` avoids conflicts with default PostgreSQL (5432)
- Database name `specstory` should be simple (lowercase, no special chars)
- Password should be strong (avoid default passwords in production)

### Option 2: Docker Compose (Production)

For production deployments, use Docker Compose (see next section).

---

## Docker Compose Setup

### Full Production Configuration

Create `docker-compose.yaml`:

```yaml
version: '3.8'

services:
  postgres:
    # CRITICAL: LightRAG requires BOTH Apache AGE + pgvector extensions
    # Base image: apache/age:latest (PostgreSQL 17 + AGE 1.6.0)
    # Must install pgvector separately in entrypoint
    image: apache/age:latest
    container_name: hybridrag-postgres-prod
    restart: unless-stopped

    environment:
      POSTGRES_USER: hybridrag
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: hybridrag_prod
      # UTF-8 encoding for international text
      POSTGRES_INITDB_ARGS: "--encoding=UTF8 --locale=en_US.UTF-8"

    # Install pgvector on first run
    # This runs BEFORE PostgreSQL starts, ensuring extension is available
    entrypoint: >
      bash -c "
        apt-get update &&
        apt-get install -y postgresql-17-pgvector &&
        docker-entrypoint.sh postgres
      "

    # SECURITY: NO PORTS - Internal network only!
    # Remove this section for production (apps connect via Docker network)
    # Uncomment only for development/debugging
    # ports:
    #   - "5434:5432"

    volumes:
      # Persistent database storage
      - ./data/postgres:/var/lib/postgresql/data

      # Optional: Custom initialization scripts
      # - ./init-scripts:/docker-entrypoint-initdb.d:ro

    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U hybridrag -d hybridrag_prod"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s

    networks:
      - hybridrag-net

    # PostgreSQL tuning for RAG workloads
    command:
      - "postgres"
      - "-c"
      - "shared_buffers=512MB"           # Cache for frequently accessed data
      - "-c"
      - "effective_cache_size=1536MB"    # OS cache estimation
      - "-c"
      - "maintenance_work_mem=256MB"     # Memory for VACUUM, CREATE INDEX
      - "-c"
      - "work_mem=32MB"                  # Memory per query operation
      - "-c"
      - "max_connections=100"            # Connection limit
      - "-c"
      - "random_page_cost=1.1"           # SSD optimization
      - "-c"
      - "effective_io_concurrency=200"   # SSD parallel I/O

    # Resource limits
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '2.0'
        reservations:
          memory: 512M
          cpus: '0.5'

networks:
  hybridrag-net:
    driver: bridge
    name: hybridrag-production-network
```

### Environment Variables (.env)

Create `.env` file:

```bash
# PostgreSQL Configuration
POSTGRES_PASSWORD=your_very_secure_password_2026
POSTGRES_USER=hybridrag
POSTGRES_DB=hybridrag_prod

# API Configuration (if using HybridRAG app)
AZURE_API_BASE=https://your-project.services.ai.azure.com/api/projects/your-project
AZURE_API_KEY=your-api-key-here
AZURE_API_VERSION=2024-02-15-preview

# Models
LLM_MODEL=gpt-4.1-mini
EMBEDDING_MODEL=text-embedding-3-small

# Storage Backend
BACKEND_TYPE=postgres

# Paths (for Docker deployment)
HOST_PROJECTS_PATH=/home/user/Documents/code
BATCH_SIZE=10
```

### Start and Verify

```bash
# Start PostgreSQL
docker compose up -d

# Wait for healthcheck to pass
docker compose ps

# Verify extensions are installed
docker compose exec postgres psql -U hybridrag -d hybridrag_prod \
  -c "SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector', 'age');"

# Check container logs
docker compose logs -f postgres
```

---

## Database Registry Configuration

HybridRAG uses a centralized registry to manage database configurations.

### Registry Location

By default: `~/.hybridrag/registry.yaml`

Override with:
- Environment variable: `HYBRIDRAG_CONFIG=/custom/path/registry.yaml`
- Config pointer: `~/.hybridrag/config_pointer`

### Register PostgreSQL Backend

```bash
# Using HybridRAG CLI
python hybridrag.py database register \
  --name specstory-prod \
  --path ~/databases/specstory \
  --source-folder ~/Documents/code \
  --backend postgres \
  --postgres-host localhost \
  --postgres-port 5434 \
  --postgres-user hybridrag \
  --postgres-password your_secure_password_2026 \
  --postgres-database specstory \
  --auto-watch \
  --watch-interval 300 \
  --description "SpecStory AI conversation histories (PostgreSQL backend)"
```

### Manual Registry Configuration

Edit `~/.hybridrag/registry.yaml`:

```yaml
version: 1

databases:
  specstory-prod:
    name: specstory-prod
    path: /home/user/databases/specstory
    source_folder: /home/user/Documents/code
    source_type: filesystem
    auto_watch: true
    watch_interval: 300
    recursive: true
    file_extensions:
      - .md
      - .txt
      - .json
    description: "SpecStory AI conversation histories (PostgreSQL backend)"

    # Backend Configuration (CRITICAL)
    backend_type: postgres
    backend_config:
      backend_type: postgres
      postgres_host: localhost
      postgres_port: 5434
      postgres_user: hybridrag
      postgres_password: your_secure_password_2026
      postgres_database: specstory

    created_at: "2026-01-17T10:00:00"
    last_sync: null
```

### Connection String Format

LightRAG uses this format internally:

```
postgresql://user:password@host:port/database
```

Example:
```
postgresql://hybridrag:your_secure_password_2026@localhost:5434/specstory
```

---

## Verification Steps

### 1. Check Extensions Loaded

```bash
docker exec hybridrag-postgres psql -U hybridrag -d specstory \
  -c "SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector', 'age');"
```

**Expected Output:**
```
 extname | extversion
---------+------------
 vector  | 0.7.0
 age     | 1.6.0
```

### 2. Initialize HybridRAG Backend

```bash
python hybridrag.py backend init --backend postgres
```

**Expected Output:**
```
✅ PostgreSQL backend initialized successfully!
✅ Created graph schema using Apache AGE
✅ Created vector tables using pgvector
```

### 3. Test Watcher Connection

```bash
# Start watcher (if auto_watch enabled)
python scripts/hybridrag-watcher.py start --database specstory-prod

# Check watcher status
python scripts/hybridrag-watcher.py status
```

**Expected Output:**
```
✅ Watcher running for database 'specstory-prod' (PID: 12345)
✅ PostgreSQL connection: OK
✅ Extensions: vector (0.7.0), age (1.6.0)
```

### 4. Test Ingestion

```bash
# Ingest a test file
python hybridrag.py ingest \
  --path ~/Documents/code/test.md \
  --backend postgres

# Verify data in PostgreSQL
docker exec hybridrag-postgres psql -U hybridrag -d specstory \
  -c "SELECT COUNT(*) FROM lightrag_full_entities;"
```

### 5. Test Query Functionality

```bash
# Run interactive query
python hybridrag.py interactive

# Or run single query
python hybridrag.py query \
  --text "What are the main features?" \
  --mode hybrid
```

---

## Troubleshooting

### Error: "function create_graph(unknown) does not exist"

**Cause:** Apache AGE extension not installed

**Solution:**
```bash
# Verify container has AGE extension
docker exec hybridrag-postgres psql -U hybridrag -d specstory \
  -c "SELECT extname FROM pg_extension WHERE extname = 'age';"

# If missing, create extension
docker exec hybridrag-postgres psql -U hybridrag -d specstory \
  -c "CREATE EXTENSION IF NOT EXISTS age;"
```

### Error: "type vector does not exist"

**Cause:** pgvector extension not installed

**Solution:**
```bash
# Install pgvector
docker exec hybridrag-postgres bash -c \
  "apt-get update && apt-get install -y postgresql-17-pgvector"

# Create extension
docker exec hybridrag-postgres psql -U hybridrag -d specstory \
  -c "CREATE EXTENSION IF NOT EXISTS vector;"

# Restart PostgreSQL
docker restart hybridrag-postgres
```

### Error: "could not connect to database"

**Cause:** Connection parameters incorrect

**Solution:**
```bash
# Test connection manually
docker exec hybridrag-postgres psql -U hybridrag -d specstory -c "SELECT version();"

# Check PostgreSQL is listening
docker exec hybridrag-postgres pg_isready -U hybridrag

# Verify port mapping
docker port hybridrag-postgres

# Check network connectivity (if using Docker network)
docker network inspect hybridrag-production-network
```

### Performance Degradation

**Cause:** Large JSON files causing slowdowns

**Solution:**
```bash
# Check database size
docker exec hybridrag-postgres psql -U hybridrag -d specstory \
  -c "SELECT pg_size_pretty(pg_database_size('specstory'));"

# Check table sizes
docker exec hybridrag-postgres psql -U hybridrag -d specstory \
  -c "SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
      FROM pg_tables
      WHERE schemaname = 'public'
      ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;"

# Run VACUUM to reclaim space
docker exec hybridrag-postgres psql -U hybridrag -d specstory \
  -c "VACUUM ANALYZE;"
```

### Container Won't Start

**Cause:** Entrypoint script failing

**Solution:**
```bash
# Check logs
docker logs hybridrag-postgres

# Common issues:
# 1. Port 5434 already in use → Change port
# 2. Data directory permission denied → Fix ownership
# 3. Out of memory → Increase Docker memory limit

# Fix data directory ownership
sudo chown -R 999:999 ./data/postgres
```

---

## Migration from JSON to PostgreSQL

### When to Migrate

Migrate when:
- JSON files exceed **500MB** total size
- Query performance degrades (>5s for simple queries)
- You need concurrent access from multiple processes
- You want production-grade reliability

### How to Migrate

```bash
# 1. Backup existing JSON database
python hybridrag.py backend backup \
  --backend json \
  --output ~/backups/hybridrag-json-backup-2026-01-17.tar.gz

# 2. Set up PostgreSQL backend (follow Quick Start)

# 3. Run migration
python hybridrag.py migrate json-to-postgres \
  --json-path ~/databases/specstory_json \
  --postgres-database specstory \
  --postgres-host localhost \
  --postgres-port 5434 \
  --postgres-user hybridrag \
  --postgres-password your_secure_password_2026

# 4. Verify migration
docker exec hybridrag-postgres psql -U hybridrag -d specstory \
  -c "SELECT COUNT(*) FROM lightrag_full_entities;"

# 5. Update registry to use PostgreSQL backend
python hybridrag.py database update \
  --name specstory-prod \
  --backend postgres \
  --postgres-host localhost \
  --postgres-port 5434
```

### What to Expect

**Performance Improvements:**
- Query latency: **5s → 500ms** (10x faster)
- Concurrent queries: **1 → 100** (no file locking)
- Ingestion throughput: **10 docs/s → 100 docs/s** (batch inserts)

**Data Size Comparison:**
| Storage | Size | Notes |
|---------|------|-------|
| JSON | 1.2GB | Large text files |
| PostgreSQL | 800MB | Compressed indexes |

---

## Production Deployment Patterns

### Pattern 1: Isolated Deployments

**Use Case:** Complete independence between deployments

Each deployment has its own PostgreSQL container.

**Example:**
```
/deployments/
├── hybridrag-team-a/
│   ├── docker-compose.yaml  (postgres + app)
│   └── data/postgres/
├── hybridrag-team-b/
│   ├── docker-compose.yaml  (postgres + app)
│   └── data/postgres/
```

**Benefits:**
- No shared failure points
- Simple management
- Easy to delete one deployment

**Drawbacks:**
- Higher resource usage (N × PostgreSQL overhead)
- No cross-deployment queries

See: [Isolated PostgreSQL Deployment Guide](../user-stories/isolated-postgres-deployment.md)

### Pattern 2: Shared PostgreSQL

**Use Case:** Multiple deployments with limited resources

One PostgreSQL container serves multiple apps via separate databases.

**Example:**
```
/deployments/
├── hybridrag-shared-postgres/
│   ├── docker-compose.yaml  (postgres only)
│   └── data/postgres/
│       ├── team_a/ (database)
│       ├── team_b/ (database)
│       └── team_c/ (database)
├── hybridrag-team-a/
│   └── docker-compose.yaml  (app only, connects to shared postgres)
├── hybridrag-team-b/
│   └── docker-compose.yaml  (app only, connects to shared postgres)
```

**Benefits:**
- Lower resource usage (1 PostgreSQL for all)
- Centralized management
- Cross-deployment queries possible

**Drawbacks:**
- Shared failure point
- Requires connection pooling management

See: [Shared PostgreSQL Deployment Guide](../user-stories/shared-postgres-deployment.md)

### Network Isolation Best Practices

**Development:**
```yaml
ports:
  - "5434:5432"  # Expose for psql debugging
```

**Production:**
```yaml
# NO ports section - internal network only
networks:
  - hybridrag-internal
```

**Why?**
- Security: PostgreSQL not accessible from host
- Port conflicts: Multiple deployments can coexist
- Docker network DNS: Apps connect via container name

### Security Best Practices

1. **Strong Passwords**
   ```bash
   # Generate secure password
   openssl rand -base64 32
   ```

2. **Environment Variables** (never commit to git)
   ```bash
   echo ".env" >> .gitignore
   echo "data/" >> .gitignore
   ```

3. **Read-Only Mounts** (for source data)
   ```yaml
   volumes:
     - /data/projects:/data/projects:ro  # Read-only
   ```

4. **Network Isolation** (no port exposure)
   ```yaml
   # NO ports section in production
   ```

5. **Regular Backups**
   ```bash
   # Automated backup script
   docker exec hybridrag-postgres pg_dump -U hybridrag -d specstory \
     | gzip > backups/specstory-$(date +%Y%m%d).sql.gz
   ```

---

## Common Pitfalls

### 🚨 Using pgvector/pgvector:pg16 Image

**Problem:** Missing Apache AGE extension

**Symptom:**
```
ERROR: function create_graph(unknown) does not exist
```

**Fix:** Use `apache/age:latest` + install pgvector

### 🚨 Forgetting to Install pgvector

**Problem:** AGE image doesn't include pgvector by default

**Symptom:**
```
ERROR: type "vector" does not exist
```

**Fix:** Add entrypoint to install pgvector:
```yaml
entrypoint: >
  bash -c "apt-get update && apt-get install -y postgresql-17-pgvector && docker-entrypoint.sh postgres"
```

### 🚨 Database Name Too Long/Complex

**Problem:** LightRAG may have issues with long database names

**Symptom:**
```
WARNING: Database name exceeds recommended length
```

**Fix:** Use simple names:
- ✅ `specstory`, `team_a`, `prod`
- ❌ `hybridrag-azure-specstory-production-v2`

### 🚨 Exposing PostgreSQL Port Unnecessarily

**Problem:** Port conflicts when running multiple deployments

**Symptom:**
```
Error: bind: address already in use
```

**Fix:** Remove `ports:` section in production, use Docker network

### 🚨 Incorrect Connection Host

**Problem:** Using `localhost` when connecting from Docker container

**Symptom:**
```
ERROR: could not connect to server: Connection refused
```

**Fix:** Use container name:
```yaml
environment:
  POSTGRES_HOST: postgres  # NOT localhost
```

### 🚨 Missing Extensions After Container Restart

**Problem:** Extensions not persisted if data volume is deleted

**Symptom:**
```
ERROR: extension "vector" does not exist
```

**Fix:** Always create extensions AFTER container starts:
```bash
docker exec hybridrag-postgres psql -U hybridrag -d specstory \
  -c "CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS age;"
```

---

## Performance Optimization

### PostgreSQL Tuning for RAG Workloads

```sql
-- Memory configuration (adjust based on available RAM)
ALTER SYSTEM SET shared_buffers = '512MB';
ALTER SYSTEM SET effective_cache_size = '1536MB';
ALTER SYSTEM SET maintenance_work_mem = '256MB';
ALTER SYSTEM SET work_mem = '32MB';

-- Connection limits
ALTER SYSTEM SET max_connections = 100;

-- WAL configuration
ALTER SYSTEM SET wal_level = 'replica';
ALTER SYSTEM SET max_wal_size = '1GB';
ALTER SYSTEM SET min_wal_size = '80MB';

-- Checkpoint configuration
ALTER SYSTEM SET checkpoint_completion_target = 0.9;

-- SSD optimization
ALTER SYSTEM SET random_page_cost = 1.1;
ALTER SYSTEM SET effective_io_concurrency = 200;

-- Reload configuration
SELECT pg_reload_conf();
```

### Indexing Strategies

```sql
-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_entities_name ON lightrag_full_entities(name);
CREATE INDEX IF NOT EXISTS idx_relations_src ON lightrag_full_relations(src);
CREATE INDEX IF NOT EXISTS idx_relations_tgt ON lightrag_full_relations(tgt);

-- Vector similarity index (HNSW for faster approximate search)
CREATE INDEX ON lightrag_vdb_chunks USING hnsw (embedding vector_cosine_ops);
```

### Connection Pooling

For high-traffic deployments:

```yaml
services:
  pgbouncer:
    image: pgbouncer/pgbouncer:latest
    environment:
      DATABASES_HOST: postgres
      DATABASES_PORT: 5432
      DATABASES_USER: hybridrag
      DATABASES_PASSWORD: ${POSTGRES_PASSWORD}
      DATABASES_DBNAME: specstory
      PGBOUNCER_POOL_MODE: transaction
      PGBOUNCER_MAX_CLIENT_CONN: 1000
      PGBOUNCER_DEFAULT_POOL_SIZE: 25
    networks:
      - hybridrag-net
```

---

## Related Documentation

- **User Stories:**
  - [Isolated PostgreSQL Deployment](../user-stories/isolated-postgres-deployment.md)
  - [Shared PostgreSQL Deployment](../user-stories/shared-postgres-deployment.md)

- **Deployment Guides:**
  - [Multi-Project Deployment Guide](../deployment/MULTI_PROJECT_DEPLOYMENT.md)
  - [MCP Server Integration](../MCP_SERVER_INTEGRATION.md)

- **Migration:**
  - [Migration User Stories](../MIGRATION_USER_STORIES.md)
  - [JSON to PostgreSQL Migration](../migration/json-to-postgres.md)

- **Monitoring:**
  - [HybridRAG TUI Monitor](../guides/MONITOR_GUIDE.md)
  - [Watcher Management](../guides/WATCHER_GUIDE.md)

- **External Resources:**
  - [LightRAG GitHub](https://github.com/HKUDS/LightRAG)
  - [Apache AGE Documentation](https://age.apache.org/)
  - [pgvector Documentation](https://github.com/pgvector/pgvector)
  - [PostgreSQL Docker Hub](https://hub.docker.com/_/postgres)

---

## Summary

**Key Takeaways:**

1. ✅ **MUST use Apache AGE + pgvector** (both required)
2. ✅ **Use `apache/age:latest` + install pgvector** (not pgvector/pgvector)
3. ✅ **Simple database names** (lowercase, no special characters)
4. ✅ **No port exposure in production** (use Docker networks)
5. ✅ **Verify extensions loaded** before initializing HybridRAG
6. ✅ **Regular backups** and monitoring

**Next Steps:**

1. Set up PostgreSQL using Quick Start commands
2. Configure HybridRAG registry
3. Initialize backend and verify extensions
4. Test ingestion and queries
5. Choose deployment pattern (isolated vs shared)
6. Set up monitoring and backups

**Need Help?**

- Check [Troubleshooting](#troubleshooting) section
- Review [Common Pitfalls](#common-pitfalls)
- See [Related Documentation](#related-documentation)
- Open an issue on [HybridRAG GitHub](https://github.com/yourusername/hybridrag)

---

**Document Version:** 1.0.0
**Contributors:** HybridRAG Team
**License:** MIT
