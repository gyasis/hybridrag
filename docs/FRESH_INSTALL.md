# Fresh Installation Guide

**Audience:** Developers setting up HybridRAG for the first time
**Last Updated:** 2026-01-25

---

## Quick Decision: JSON vs PostgreSQL

| Factor | JSON Backend | PostgreSQL Backend |
|--------|--------------|-------------------|
| **Best for** | Development, small datasets | Production, large datasets |
| **Setup time** | 2 minutes | 10 minutes |
| **Data size** | < 500MB | Unlimited |
| **Dependencies** | None | Docker |
| **Concurrent access** | No | Yes |
| **When to use** | Testing, personal projects | Teams, production |

**Recommendation:** Start with JSON. Migrate to PostgreSQL when needed.

---

## Prerequisites

### Required

- **Python 3.10+**
  ```bash
  python --version  # Should be 3.10 or higher
  ```

- **UV package manager** (recommended) or pip
  ```bash
  # Install uv
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

- **API Key** (one of the following):
  - OpenAI API key
  - Azure OpenAI deployment
  - Ollama (local LLM)

### For PostgreSQL Backend

- **Docker** (version 20.10+)
  ```bash
  docker --version
  ```

- **Docker Compose** (version 2.0+)
  ```bash
  docker compose version
  ```

---

## Path A: JSON Backend (Recommended for Beginners)

### Step 1: Clone and Install

```bash
# Clone the repository
git clone https://github.com/yourusername/hybridrag.git
cd hybridrag

# Create virtual environment and install
uv venv
source .venv/bin/activate  # Linux/Mac
# OR: .venv\Scripts\activate  # Windows

uv pip install -e .
```

### Step 2: Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit with your API key
nano .env  # or your preferred editor
```

**Minimum configuration:**

```bash
# .env
OPENAI_API_KEY=sk-your-key-here

# OR for Azure:
AZURE_API_KEY=your-azure-key
AZURE_API_BASE=https://your-resource.openai.azure.com
LIGHTRAG_MODEL=azure/gpt-5.1
LIGHTRAG_EMBED_MODEL=azure/text-embedding-3-small
EMBEDDING_DIM=768
```

### Step 3: Initialize Database

```bash
# Create a database for your documents
python hybridrag.py database register \
  --name myproject \
  --path ~/hybridrag_db/myproject \
  --source-folder ~/Documents/myproject \
  --backend json
```

### Step 4: Ingest Documents

```bash
# Ingest files from source folder
python hybridrag.py ingest \
  --database myproject \
  --recursive \
  --pattern "**/*.md"
```

### Step 5: Query Your Data

```bash
# Interactive mode
python hybridrag.py interactive --database myproject

# Single query
python hybridrag.py query \
  --database myproject \
  --text "What are the main topics?"
```

### Step 6: (Optional) Set Up MCP Server

For Claude Code integration:

```bash
# Add to ~/.claude.json
{
  "mcpServers": {
    "hybridrag": {
      "command": "uv",
      "args": ["run", "python", "-m", "hybridrag_mcp.server"],
      "cwd": "/path/to/hybridrag",
      "env": {
        "HYBRIDRAG_DATABASE_NAME": "myproject",
        "AZURE_API_KEY": "your-key",
        "EMBEDDING_DIM": "768"
      }
    }
  }
}
```

---

## Path B: PostgreSQL Backend (Production)

### Step 1: Clone and Install

Same as Path A, Steps 1-2.

### Step 2: Start PostgreSQL

```bash
# Navigate to hybridrag directory
cd hybridrag

# Start PostgreSQL with AGE + pgvector
docker compose -f docker/docker-compose.postgres.yaml up -d

# Wait for container to be healthy (90 seconds for first run)
docker compose -f docker/docker-compose.postgres.yaml ps

# Verify extensions are installed
docker exec hybridrag-postgres psql -U hybridrag -d hybridrag \
  -c "SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector', 'age');"
```

**Expected output:**
```
 extname | extversion
---------+------------
 vector  | 0.7.0
 age     | 1.6.0
```

### Step 3: Create Extensions in Database

```bash
# Create extensions (one-time setup)
docker exec hybridrag-postgres psql -U hybridrag -d hybridrag \
  -c "CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS age;"
```

### Step 4: Configure Environment

```bash
# Edit .env with PostgreSQL settings
nano .env
```

**PostgreSQL configuration:**

```bash
# .env

# API Keys
AZURE_API_KEY=your-azure-key
AZURE_API_BASE=https://your-resource.openai.azure.com

# Models
LIGHTRAG_MODEL=azure/gpt-5.1
LIGHTRAG_EMBED_MODEL=azure/text-embedding-3-small

# CRITICAL: Must match your embedding model!
EMBEDDING_DIM=768

# Backend
BACKEND_TYPE=postgres

# PostgreSQL Connection
POSTGRES_HOST=localhost
POSTGRES_PORT=5433
POSTGRES_USER=hybridrag
POSTGRES_PASSWORD=hybridrag_secure_2026
POSTGRES_DB=hybridrag
```

### Step 5: Register Database

```bash
python hybridrag.py database register \
  --name myproject \
  --path ~/hybridrag_db/myproject \
  --source-folder ~/Documents/myproject \
  --backend postgres \
  --postgres-host localhost \
  --postgres-port 5433 \
  --postgres-user hybridrag \
  --postgres-password hybridrag_secure_2026 \
  --postgres-database hybridrag
```

### Step 6: Initialize Backend

```bash
python hybridrag.py backend init --backend postgres
```

### Step 7: Ingest and Query

Same as Path A, Steps 4-5.

---

## Verification Checklist

### JSON Backend

- [ ] `.env` file created with API key
- [ ] Database registered: `python hybridrag.py database list`
- [ ] Documents ingested: Check `lightrag_db/` folder has data
- [ ] Query works: `python hybridrag.py query --text "test"`

### PostgreSQL Backend

- [ ] Docker container running: `docker ps | grep hybridrag`
- [ ] Extensions installed: Check with psql command above
- [ ] EMBEDDING_DIM matches your model
- [ ] Database registered with postgres backend
- [ ] Backend initialized: `python hybridrag.py backend status`
- [ ] Query works: Check tables have data

---

## Common Issues

### "No query context could be built"

**Cause:** EMBEDDING_DIM mismatch

**Fix:**
1. Check your embedding model's dimension
2. Set `EMBEDDING_DIM` correctly in `.env`
3. Re-ingest documents after fixing

### "Connection refused" (PostgreSQL)

**Cause:** PostgreSQL not running or wrong port

**Fix:**
```bash
# Check container status
docker ps

# Check logs
docker logs hybridrag-postgres

# Verify port
docker port hybridrag-postgres
```

### "function create_graph does not exist"

**Cause:** Apache AGE extension not installed

**Fix:**
```bash
docker exec hybridrag-postgres psql -U hybridrag -d hybridrag \
  -c "CREATE EXTENSION IF NOT EXISTS age;"
```

### MCP Server Returns Invalid JSON

**Cause:** `litellm.set_verbose = True` in server code

**Fix:** Set to `False` in `hybridrag_mcp/server.py` (line ~152)

---

## Next Steps

1. **Set up file watching** for automatic ingestion:
   ```bash
   python hybridrag.py watcher start --database myproject
   ```

2. **Configure MCP server** for Claude Code integration

3. **Review troubleshooting guide** for common issues:
   [TROUBLESHOOTING.md](./TROUBLESHOOTING.md)

4. **Production deployment:**
   - [PostgreSQL Backend Setup](./technical/POSTGRESQL_BACKEND_SETUP.md)
   - [Multi-Project Deployment](./deployment/MULTI_PROJECT_DEPLOYMENT.md)

---

## See Also

- [.env.example](../.env.example) - Environment variable reference
- [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) - Common issues and fixes
- [PostgreSQL Backend Setup](./technical/POSTGRESQL_BACKEND_SETUP.md) - Detailed PostgreSQL guide
- [MCP Server Integration](./MCP_SERVER_INTEGRATION.md) - Claude Code setup
