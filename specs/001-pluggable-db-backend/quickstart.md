# Quickstart Guide: Pluggable Database Backend

**Feature Branch**: `001-pluggable-db-backend`
**Date**: 2025-12-19

## Overview

This guide helps developers set up and test the PostgreSQL backend for HybridRAG.

## Prerequisites

- Python 3.8+ (3.11+ recommended)
- Docker Desktop or Docker Engine
- HybridRAG installed (`pip install -e .`)
- LightRAG 1.4.9.8+ (`pip install lightrag-hku>=1.4.9.8`)

## Quick Start (5 minutes)

### 1. Start PostgreSQL with pgvector

```bash
# Auto-provision PostgreSQL container
hybridrag backend setup-docker

# Or manually with docker-compose
cd docker/
docker-compose -f docker-compose.postgres.yaml up -d
```

### 2. Create a Database with PostgreSQL Backend

```bash
# Create new database using PostgreSQL
hybridrag db create mydb --backend postgres

# Or migrate existing JSON database
hybridrag migrate specstory --to postgres
```

### 3. Verify Backend Status

```bash
hybridrag backend status mydb
```

## Manual Setup

### Docker Compose Configuration

```yaml
# docker/docker-compose.postgres.yaml
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

### Environment Variables

```bash
# Required for PostgreSQL backend
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export POSTGRES_USER=hybridrag
export POSTGRES_PASSWORD=your_secure_password
export POSTGRES_DATABASE=hybridrag
export POSTGRES_WORKSPACE=default
```

### Database Registry Configuration

```yaml
# ~/.hybridrag/databases.yaml
databases:
  mydb:
    name: mydb
    path: /home/user/databases/mydb
    backend_type: postgres
    backend_config:
      postgres_host: localhost
      postgres_port: 5432
      postgres_user: hybridrag
      postgres_database: hybridrag
      postgres_workspace: mydb
```

## Development Workflow

### Running Tests

```bash
# Unit tests for backend config
pytest tests/unit/test_backend_config.py -v

# Integration tests (requires PostgreSQL)
pytest tests/integration/test_postgres_backend.py -v

# Contract tests (JSON vs PostgreSQL parity)
pytest tests/contract/test_storage_interface.py -v
```

### Testing with a Local Database

```python
from src.config.config import BackendConfig, BackendType
from src.lightrag_core import HybridLightRAGCore

# Create config for PostgreSQL
config = BackendConfig(
    backend_type=BackendType.POSTGRESQL,
    postgres_host="localhost",
    postgres_port=5432,
    postgres_user="hybridrag",
    postgres_password="your_password",
    postgres_database="hybridrag",
    postgres_workspace="test"
)

# Initialize core with PostgreSQL backend
core = HybridLightRAGCore(
    working_dir="/tmp/test_db",
    backend_config=config
)

# Insert a document
await core.insert("Test document content")

# Query
result = await core.query("What is the test about?")
print(result)
```

### Migration Testing

```bash
# Create a test JSON database
hybridrag db create test_json --path /tmp/test_json

# Insert some test data
echo "Test document" | hybridrag insert test_json --stdin

# Migrate to PostgreSQL
hybridrag migrate test_json --to postgres --verify

# Verify data
hybridrag backend status test_json --verbose
```

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    HybridRAG CLI                        │
├─────────────────────────────────────────────────────────┤
│                 HybridLightRAGCore                      │
│                                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │BackendConfig│  │DatabaseEntry│  │MigrationJob │     │
│  └─────────────┘  └─────────────┘  └─────────────┘     │
├─────────────────────────────────────────────────────────┤
│                    LightRAG v1.4.9.8                    │
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │              Storage Factory                      │  │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌────────┐ │  │
│  │  │KVStorage│ │VectorDB │ │GraphDB  │ │DocStatus│ │  │
│  │  └────┬────┘ └────┬────┘ └────┬────┘ └───┬────┘ │  │
│  └───────┼──────────┼──────────┼──────────┼───────┘  │
├──────────┼──────────┼──────────┼──────────┼──────────┤
│          ▼          ▼          ▼          ▼          │
│  ┌─────────────────────────────────────────────────┐ │
│  │              JSON Backend (Default)              │ │
│  │  JsonKVStorage │ NanoVectorDB │ NetworkX │ JSON  │ │
│  └─────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────┐ │
│  │            PostgreSQL Backend                    │ │
│  │  PGKVStorage │ PGVectorStorage │ PGGraphStorage │ │
│  │              (pgvector)        │ (AGE optional)  │ │
│  └─────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

## Troubleshooting

### Common Issues

**1. Connection refused**
```bash
# Check if PostgreSQL is running
docker ps | grep hybridrag-postgres

# Check logs
docker logs hybridrag-postgres
```

**2. pgvector extension not found**
```sql
-- Connect to PostgreSQL and create extension
CREATE EXTENSION IF NOT EXISTS vector;
```

**3. Permission denied**
```bash
# Ensure user has proper permissions
docker exec -it hybridrag-postgres psql -U hybridrag -d hybridrag -c "GRANT ALL ON SCHEMA public TO hybridrag;"
```

**4. Migration checkpoint recovery**
```bash
# Resume interrupted migration
hybridrag migrate mydb --to postgres --resume
```

### Getting Help

```bash
# CLI help
hybridrag backend --help
hybridrag migrate --help

# Check backend status
hybridrag backend status --verbose --json
```

## Next Steps

1. Read the full [Implementation Plan](./plan.md)
2. Review [Data Models](./data-model.md)
3. Check [API Contracts](./contracts/)
4. Run `/speckit.tasks` to generate implementation tasks
