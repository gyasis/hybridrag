# HybridRAG PostgreSQL Configuration Template

**Purpose:** Reusable configuration templates for setting up HybridRAG with PostgreSQL backend.
**Last Updated:** 2026-01-25

Copy and customize these templates for new projects.

---

## 1. Docker Compose (docker-compose.postgres.yaml)

```yaml
# =============================================================================
# HybridRAG PostgreSQL Backend with Apache AGE + pgvector
# =============================================================================
# CRITICAL: LightRAG requires BOTH extensions:
#   - Apache AGE:  Graph storage (nodes/edges/relationships)
#   - pgvector:    Vector embeddings for similarity search
#
# Usage:
#   docker-compose -f docker-compose.postgres.yaml up -d
#
# Verify extensions:
#   docker exec <container> psql -U <user> -d <db> \
#     -c "SELECT extname FROM pg_extension WHERE extname IN ('vector', 'age');"
# =============================================================================

services:
  hybridrag-postgres:
    # MUST use apache/age (NOT pgvector/pgvector - missing AGE extension)
    image: apache/age:latest
    container_name: ${PROJECT_NAME:-hybridrag}-postgres
    restart: unless-stopped

    environment:
      POSTGRES_USER: ${POSTGRES_USER:-hybridrag}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?POSTGRES_PASSWORD required}
      POSTGRES_DB: ${POSTGRES_DB:-hybridrag}
      POSTGRES_INITDB_ARGS: "--encoding=UTF8 --locale=en_US.UTF-8"

    # Install pgvector on startup (AGE is pre-installed in apache/age image)
    entrypoint: >
      bash -c "
        apt-get update &&
        apt-get install -y --no-install-recommends postgresql-17-pgvector &&
        rm -rf /var/lib/apt/lists/* &&
        exec docker-entrypoint.sh postgres
      "

    ports:
      # Port 5433 avoids conflict with default PostgreSQL (5432)
      - "${POSTGRES_PORT:-5433}:5432"

    volumes:
      # Persistent data - survives container restarts
      - ${PROJECT_NAME:-hybridrag}-pgdata:/var/lib/postgresql/data
      # Optional: initialization scripts
      - ./init-scripts:/docker-entrypoint-initdb.d:ro

    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-hybridrag} -d ${POSTGRES_DB:-hybridrag}"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 90s  # Allow time for pgvector installation

    # Resource limits - adjust based on your data size
    deploy:
      resources:
        limits:
          memory: 4G
        reservations:
          memory: 1G

    # Logging
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

    # PostgreSQL performance tuning
    command:
      - "postgres"
      - "-c"
      - "shared_buffers=512MB"
      - "-c"
      - "effective_cache_size=1536MB"
      - "-c"
      - "maintenance_work_mem=256MB"
      - "-c"
      - "work_mem=32MB"
      - "-c"
      - "max_connections=100"
      - "-c"
      - "wal_level=replica"
      - "-c"
      - "max_wal_size=2GB"
      - "-c"
      - "min_wal_size=256MB"

volumes:
  ${PROJECT_NAME:-hybridrag}-pgdata:
    driver: local

networks:
  default:
    name: ${PROJECT_NAME:-hybridrag}-network
```

---

## 2. Environment File (.env)

```bash
# =============================================================================
# HybridRAG Environment Configuration
# =============================================================================
# SECURITY: Never commit this file to version control!
# Add to .gitignore: .env
# =============================================================================

# -----------------------------------------------------------------------------
# Project Identification
# -----------------------------------------------------------------------------
PROJECT_NAME=myproject

# -----------------------------------------------------------------------------
# API Keys (choose your provider)
# -----------------------------------------------------------------------------

# Option A: OpenAI Direct
OPENAI_API_KEY=sk-your-openai-key-here

# Option B: Azure OpenAI (recommended for enterprise)
AZURE_API_KEY=your-azure-key-here
AZURE_API_BASE=https://your-resource.cognitiveservices.azure.com
AZURE_API_VERSION=2024-12-01-preview

# -----------------------------------------------------------------------------
# Model Configuration (LiteLLM format)
# -----------------------------------------------------------------------------
# Prefix determines routing:
#   openai/   → OpenAI API
#   azure/    → Azure OpenAI
#   ollama/   → Local Ollama

LIGHTRAG_MODEL=azure/gpt-5.1
AGENTIC_MODEL=azure/gpt-5.1
LIGHTRAG_EMBED_MODEL=azure/text-embedding-3-small

# -----------------------------------------------------------------------------
# EMBEDDING DIMENSION (CRITICAL!)
# -----------------------------------------------------------------------------
# Must match your embedding model output dimension.
# Wrong value = queries return empty results.
#
#   Azure text-embedding-3-small:  768
#   OpenAI text-embedding-3-small: 1536
#   OpenAI text-embedding-3-large: 3072
#   text-embedding-ada-002:        1536

EMBEDDING_DIM=768

# -----------------------------------------------------------------------------
# PostgreSQL Configuration
# -----------------------------------------------------------------------------
POSTGRES_HOST=localhost
POSTGRES_PORT=5433
POSTGRES_USER=hybridrag
POSTGRES_PASSWORD=your_secure_password_here
POSTGRES_DB=hybridrag

# Backend type
BACKEND_TYPE=postgres

# -----------------------------------------------------------------------------
# HybridRAG Application Settings
# -----------------------------------------------------------------------------

# Database name (for MCP server / registry)
HYBRIDRAG_DATABASE_NAME=myproject

# Logging
HYBRIDRAG_LOG_LEVEL=INFO

# Search defaults
HYBRIDRAG_DEFAULT_MODE=hybrid
HYBRIDRAG_DEFAULT_TOP_K=10
HYBRIDRAG_ENABLE_AGENTIC=true

# Performance
HYBRIDRAG_BATCH_SIZE=10
HYBRIDRAG_MAX_CONCURRENT_INGESTIONS=3
```

---

## 3. Claude Code MCP Server Config (~/.claude.json snippet)

```json
{
  "mcpServers": {
    "hybridrag-myproject": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/hybridrag",
        "run",
        "python",
        "-m",
        "hybridrag_mcp"
      ],
      "env": {
        "HYBRIDRAG_DATABASE": "/path/to/hybridrag/lightrag_db",
        "HYBRIDRAG_DATABASE_NAME": "myproject",
        "HYBRIDRAG_MODEL": "azure/gpt-5.1",
        "HYBRIDRAG_EMBED_MODEL": "azure/text-embedding-3-small",
        "EMBEDDING_DIM": "768",
        "AZURE_API_KEY": "your-azure-api-key",
        "AZURE_API_BASE": "https://your-resource.cognitiveservices.azure.com"
      }
    }
  }
}
```

**Alternative: OpenAI Provider**

```json
{
  "mcpServers": {
    "hybridrag-myproject": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/hybridrag",
        "run",
        "python",
        "-m",
        "hybridrag_mcp"
      ],
      "env": {
        "HYBRIDRAG_DATABASE": "/path/to/hybridrag/lightrag_db",
        "HYBRIDRAG_DATABASE_NAME": "myproject",
        "HYBRIDRAG_MODEL": "openai/gpt-4o-mini",
        "HYBRIDRAG_EMBED_MODEL": "openai/text-embedding-3-small",
        "EMBEDDING_DIM": "1536",
        "OPENAI_API_KEY": "sk-your-openai-key"
      }
    }
  }
}
```

---

## 4. Database Registry Entry (~/.hybridrag/registry.yaml)

```yaml
version: 1

databases:
  myproject:
    name: myproject
    path: /home/user/hybridrag_db/myproject
    source_folder: /home/user/Documents/myproject
    source_type: filesystem
    auto_watch: true
    watch_interval: 300
    recursive: true
    file_extensions:
      - .md
      - .txt
      - .json
      - .py
    description: "My Project RAG Database"

    # Backend Configuration
    backend_type: postgres
    backend_config:
      backend_type: postgres
      postgres_host: localhost
      postgres_port: 5433
      postgres_user: hybridrag
      postgres_password: ${POSTGRES_PASSWORD}  # From environment
      postgres_database: hybridrag
```

---

## 5. Initialization Script (init-scripts/01-extensions.sql)

```sql
-- =============================================================================
-- Initialize PostgreSQL Extensions for LightRAG
-- =============================================================================
-- This runs automatically when the container first starts.
-- Place in ./init-scripts/ directory.
-- =============================================================================

-- Create pgvector extension for vector similarity search
CREATE EXTENSION IF NOT EXISTS vector;

-- Create Apache AGE extension for graph storage
CREATE EXTENSION IF NOT EXISTS age;

-- Load AGE into search path (required for graph operations)
SET search_path = ag_catalog, "$user", public;

-- Verify extensions loaded
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        RAISE EXCEPTION 'pgvector extension not installed';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'age') THEN
        RAISE EXCEPTION 'Apache AGE extension not installed';
    END IF;
    RAISE NOTICE 'All required extensions installed successfully';
END $$;
```

---

## 6. Quick Setup Commands

```bash
# =============================================================================
# Quick Setup for New PostgreSQL-backed HybridRAG Project
# =============================================================================

# 1. Create project directory
mkdir -p ~/hybridrag-myproject && cd ~/hybridrag-myproject

# 2. Copy configuration files
cp /path/to/hybridrag/docker/docker-compose.postgres.yaml .
cp /path/to/hybridrag/.env.example .env
mkdir -p init-scripts

# 3. Edit environment variables
nano .env
# Set: PROJECT_NAME, POSTGRES_PASSWORD, API keys, EMBEDDING_DIM

# 4. Start PostgreSQL
docker compose -f docker-compose.postgres.yaml up -d

# 5. Wait for health check (first run takes ~90 seconds for pgvector install)
docker compose -f docker-compose.postgres.yaml ps
# Wait until Status shows "healthy"

# 6. Verify extensions
docker exec myproject-postgres psql -U hybridrag -d hybridrag \
  -c "SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector', 'age');"
# Expected: vector 0.7.0, age 1.6.0

# 7. Create extensions (if not auto-created)
docker exec myproject-postgres psql -U hybridrag -d hybridrag \
  -c "CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS age;"

# 8. Register database
python hybridrag.py database register \
  --name myproject \
  --path ~/hybridrag_db/myproject \
  --source-folder ~/Documents/myproject \
  --backend postgres \
  --postgres-host localhost \
  --postgres-port 5433 \
  --postgres-user hybridrag \
  --postgres-password "$POSTGRES_PASSWORD" \
  --postgres-database hybridrag

# 9. Initialize backend
python hybridrag.py backend init --backend postgres

# 10. Test ingestion
python hybridrag.py ingest \
  --database myproject \
  --path ~/Documents/myproject \
  --recursive \
  --pattern "**/*.md"

# 11. Test query
python hybridrag.py query \
  --database myproject \
  --text "What is this project about?"
```

---

## 7. Troubleshooting Checklist

| Issue | Check | Fix |
|-------|-------|-----|
| "function create_graph does not exist" | Missing AGE extension | Use `apache/age:latest` image |
| "type vector does not exist" | Missing pgvector | Run pgvector install in entrypoint |
| "No query context built" | EMBEDDING_DIM mismatch | Match model dimension |
| Connection refused | PostgreSQL not running | `docker compose up -d` |
| MCP returns garbled JSON | litellm.set_verbose=True | Set to False in server.py |
| Port already in use | Port 5433 occupied | Change POSTGRES_PORT |

---

## 8. Embedding Dimension Reference

| Model | Provider | Dimension | EMBEDDING_DIM |
|-------|----------|-----------|---------------|
| text-embedding-3-small | Azure | 768 | `768` |
| text-embedding-3-small | OpenAI | 1536 | `1536` |
| text-embedding-3-large | OpenAI | 3072 | `3072` |
| text-embedding-ada-002 | OpenAI | 1536 | `1536` |

---

## 9. File Checklist for New Project

```
myproject/
├── docker-compose.postgres.yaml    # PostgreSQL with AGE + pgvector
├── .env                            # Environment variables (GITIGNORE!)
├── .gitignore                      # Include: .env, data/, *.tar.gz
├── init-scripts/
│   └── 01-extensions.sql           # Extension initialization
├── data/
│   └── postgres/                   # PostgreSQL data (if using bind mount)
└── lightrag_db/                    # LightRAG local storage (for JSON fallback)
```

---

## 10. Production Recommendations

1. **Never expose PostgreSQL port** in production (remove `ports:` section)
2. **Use Docker networks** for internal communication
3. **Strong passwords** - generate with `openssl rand -base64 32`
4. **Regular backups** - `pg_dump` to secure storage
5. **Monitor resources** - `docker stats <container>`
6. **Set resource limits** - prevent runaway memory usage
