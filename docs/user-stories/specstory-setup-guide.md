# Setting Up SpecStory Database with HybridRAG — Complete Guide

## Overview

**As a** developer using Claude Code with SpecStory conversations
**I want to** set up HybridRAG from scratch on a new machine
**So that** I can query my entire conversation history across all projects via MCP tools

This guide walks through every step from clone to working MCP server with PostgreSQL backend.

---

## Prerequisites

- Python 3.10+ (3.12 recommended)
- [uv](https://docs.astral.sh/uv/) package manager (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Docker (for PostgreSQL backend)
- Projects with `.specstory` folders (created by Claude Code)
- An LLM API key (Azure, OpenAI, Anthropic, or Gemini)

---

## Step 1: Clone and Install HybridRAG

```bash
# Clone the repository
git clone <repo-url> ~/dev/tools/RAG/hybridrag
cd ~/dev/tools/RAG/hybridrag

# Install with uv (creates .venv + installs all dependencies)
uv sync

# Install CLI entry point (makes `hybridrag` command available)
uv pip install -e .

# Verify installation
hybridrag --help
```

**Expected output**: Help text showing all available commands (`ingest`, `query`, `interactive`, `db`, etc.)

---

## Step 2: Configure Environment Variables

```bash
# Copy the example env file
cp .env.example .env

# Edit with your API keys
nano .env
```

**Required keys** (at least one LLM provider):
```bash
# Azure (recommended — used as default)
AZURE_API_KEY=your-azure-key
AZURE_API_BASE=https://your-endpoint.openai.azure.com/

# OR OpenAI
OPENAI_API_KEY=your-openai-key

# OR Anthropic
ANTHROPIC_API_KEY=your-anthropic-key

# OR Gemini
GEMINI_API_KEY=your-gemini-key
```

---

## Step 3: Start PostgreSQL Backend

HybridRAG uses PostgreSQL with pgvector (for embeddings) and Apache AGE (for graph queries).

```bash
# Start the container (port 5433 to avoid conflicts with existing PostgreSQL)
docker run -d \
  --name hybridrag-postgres \
  -e POSTGRES_USER=hybridrag \
  -e POSTGRES_PASSWORD=hybridrag_secure_2026 \
  -e POSTGRES_DB=hybridrag \
  -p 5433:5432 \
  apache/age:latest

# Verify it's running
docker ps | grep hybridrag-postgres
```

**Important**: Port is **5433** (not 5432). This avoids conflicts with other PostgreSQL instances.

**Verify connection**:
```bash
psql -h localhost -p 5433 -U hybridrag -d hybridrag -c "SELECT 1"
# Password: hybridrag_secure_2026
```

---

## Step 4: Register the SpecStory Database

Create a registry entry that tells HybridRAG where your data is and how to connect.

```bash
hybridrag db register specstory \
  --path ~/dev/tools/RAG/hybridrag/lightrag_db \
  --source ~/dev \
  --type specstory \
  --auto-watch \
  --interval 300 \
  --description "SpecStory conversation history from all dev projects"
```

**Parameters explained:**

| Parameter | Value | Description |
|-----------|-------|-------------|
| `specstory` | name | Friendly name to reference this DB |
| `--path` | `./lightrag_db` | LightRAG working directory |
| `--source` | `~/dev` | Parent folder containing all projects with `.specstory` dirs |
| `--type` | `specstory` | Enables SpecStory-specific preprocessing |
| `--auto-watch` | flag | Enable automatic file watching |
| `--interval` | `300` | Check for changes every 5 minutes |

Now manually add the PostgreSQL backend config to the registry:

```bash
nano ~/.hybridrag/registry.yaml
```

Add/update the `backend_type` and `backend_config` fields:

```yaml
version: 1
databases:
  specstory:
    name: specstory
    path: /home/$USER/dev/tools/RAG/hybridrag/lightrag_db
    source_folder: /home/$USER/dev
    source_type: specstory
    auto_watch: true
    watch_interval: 300
    recursive: true
    file_extensions:
    - .md
    preprocessing_pipeline:
    - specstory_conversation_extraction
    description: SpecStory conversation history from all dev projects
    backend_type: postgres
    backend_config:
      postgres_host: localhost
      postgres_port: 5433
      postgres_user: hybridrag
      postgres_password: hybridrag_secure_2026
      postgres_database: hybridrag
    model_config:
      llm_model: azure/gpt-5.1
      embedding_model: azure/text-embedding-3-small
      embedding_dim: 1536
      api_keys:
        openai: ${OPENAI_API_KEY}
        azure: ${AZURE_API_KEY}
```

**Verify registration**:
```bash
hybridrag db show specstory
```

---

## Step 5: Initial Ingestion

Ingest all existing `.specstory` folders from your projects:

```bash
# Fresh ingestion (first time)
hybridrag --db specstory ingest --folder ~/dev --db-action fresh --yes

# Or use the batch script for more control
./scripts/ingest_specstory_folders.sh ~/dev fresh
```

**What happens:**
- Recursively finds all `.specstory/history/*.md` files
- Extracts conversation content, entities, and relationships
- Builds knowledge graph in PostgreSQL
- Creates vector embeddings for semantic search

**Check progress:**
```bash
hybridrag --db specstory status
```

---

## Step 6: Start the Watcher Daemon

Set up automatic ingestion of new conversations:

```bash
# Start watcher via CLI
hybridrag --db specstory db watch start

# Verify it's running
hybridrag db watch status
```

**Expected output**:
```
Watcher Status
============================================================
   [✓] specstory            🟢 PID 12345
============================================================
Running: 1/1
```

The watcher checks for new/modified `.specstory` files every 5 minutes and auto-ingests them.

### Delta Ingestion

The watcher uses a timestamp file (`.last_specstory_watch`) to track what's already been ingested. Only files modified after this timestamp are processed.

If you need to set the timestamp manually (e.g., after a migration):
```bash
# Set to a specific date (epoch seconds)
python -c "from datetime import datetime; print(int(datetime(2026, 1, 17).timestamp()))" > .last_specstory_watch
```

### Persistent Watcher (survives reboots)

```bash
# With systemd
hybridrag --db specstory db watch start --systemd

# Manage
systemctl --user status hybridrag-watcher@specstory.service
systemctl --user stop hybridrag-watcher@specstory.service
journalctl --user -u hybridrag-watcher@specstory.service -f
```

---

## Step 7: Configure MCP Server (Claude Desktop / Claude Code)

### For Claude Code

Add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "hybridrag-specstory": {
      "command": "uv",
      "args": [
        "--directory",
        "/home/$USER/dev/tools/RAG/hybridrag",
        "run",
        "python",
        "-m",
        "hybridrag_mcp"
      ],
      "env": {
        "HYBRIDRAG_DATABASE": "/home/$USER/dev/tools/RAG/hybridrag/lightrag_db",
        "AZURE_API_KEY": "${AZURE_API_KEY}",
        "AZURE_API_BASE": "${AZURE_API_BASE}"
      }
    }
  }
}
```

### For Claude Desktop

Add to `~/.claude_desktop/config.json` (same structure as above).

### Restart Claude to load the server.

---

## Step 8: Verify MCP Tools

All 8 MCP tools should be available. Test them:

```bash
# Quick status check
hybridrag --db specstory status
```

### Available MCP Tools

| Tool | Tier | Description |
|------|------|-------------|
| `hybridrag_database_status` | T1 (<1s) | Database stats and configuration |
| `hybridrag_health_check` | T1 (<1s) | System health verification |
| `hybridrag_local_query` | T2 (<30s) | Entity-focused retrieval |
| `hybridrag_extract_context` | T2 (<10s) | Raw context without LLM generation |
| `hybridrag_global_query` | T3 (<120s) | Community-based summaries |
| `hybridrag_hybrid_query` | T3 (<120s) | Combined local + global |
| `hybridrag_query` | T3 (<120s) | Main query with mode selection |
| `hybridrag_multihop_query` | T4 (<900s) | Multi-hop reasoning |

Every tool response includes a backend metadata footer confirming the active backend:
```
Database: /path/to/lightrag_db | Backend: postgres (localhost:5433/hybridrag)
```

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                  Your Projects Directory                     │
│  ~/dev/                                                     │
│  ├── project-alpha/.specstory/history/*.md                  │
│  ├── project-beta/.specstory/history/*.md                   │
│  ├── jira-issues/TIC-4116/.specstory/history/*.md           │
│  └── ... (27+ projects)                                     │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                 HybridRAG Watcher Daemon                    │
│  hybridrag --db specstory db watch start                    │
│  - Polls every 5 minutes                                    │
│  - Detects new/modified .specstory files                    │
│  - Auto-ingests via delta timestamp                         │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   Database Registry                          │
│  ~/.hybridrag/registry.yaml                                 │
│  - Single source of truth for all databases                 │
│  - Auto-resolves backend: postgres (localhost:5433)         │
│  - Model config: azure/gpt-5.1 + text-embedding-3-small    │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              PostgreSQL + pgvector + Apache AGE              │
│  hybridrag-postgres container (port 5433)                   │
│  - Entities, relationships, chunks with embeddings          │
│  - 31K+ rows (scales to 100K+)                             │
│  - Vector similarity search via pgvector                    │
│  - Graph queries via Apache AGE                             │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    MCP Server (FastMCP)                      │
│  python -m hybridrag_mcp                                    │
│  - 8 tools exposed to Claude                                │
│  - Backend metadata on every response                       │
│  - Credential masking in all outputs                        │
│  - Background tasks for long-running queries                │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                Claude Desktop / Claude Code                  │
│  Query: "How did we implement the ETL pipeline?"            │
│  → hybridrag_hybrid_query → PostgreSQL → LLM → Answer      │
└─────────────────────────────────────────────────────────────┘
```

---

## Quick Reference

### Daily Workflow

```bash
# Check watcher is running
hybridrag db watch status

# Query your history
hybridrag --db specstory query --text "How did we fix the auth bug?" --mode hybrid

# Interactive mode
hybridrag --db specstory interactive

# Check database stats
hybridrag --db specstory status
```

### Maintenance

```bash
# Restart watcher if stopped
hybridrag --db specstory db watch start

# Restart PostgreSQL if stopped
docker start hybridrag-postgres

# View watcher logs
tail -f logs/watcher_specstory.log

# Force re-sync
hybridrag db sync specstory
```

---

## Troubleshooting

### `hybridrag` command not found
```bash
# Reinstall CLI
cd ~/dev/tools/RAG/hybridrag
uv pip install -e .
# Or run directly
uv run python hybridrag.py --help
```

### PostgreSQL connection refused
```bash
# Check container is running
docker ps | grep hybridrag-postgres

# Start if stopped
docker start hybridrag-postgres

# Verify connectivity
psql -h localhost -p 5433 -U hybridrag -d hybridrag -c "SELECT 1"
```

### Watcher not ingesting files
```bash
# Check watcher status
hybridrag db watch status

# Check delta timestamp
cat .last_specstory_watch

# Check source folder
hybridrag db show specstory  # verify source_folder

# View logs
tail -f logs/watcher_specstory.log
```

### MCP tools returning empty results
```bash
# Verify database has data
hybridrag --db specstory status

# Test CLI query first
hybridrag --db specstory query --text "test" --mode local

# Check MCP logs
ls /tmp/hybridrag_mcp_logs/
```

### Wrong backend being used
```bash
# Check registry
cat ~/.hybridrag/registry.yaml

# Verify backend in status
hybridrag --db specstory status
# Look for: Backend: postgres (localhost:5433/hybridrag)
```

---

## Summary Checklist

| Step | Command | Verify |
|------|---------|--------|
| 1. Install HybridRAG | `uv sync && uv pip install -e .` | `hybridrag --help` |
| 2. Configure API keys | Edit `.env` | Keys are set |
| 3. Start PostgreSQL | `docker run ...` | `docker ps` shows container |
| 4. Register database | `hybridrag db register specstory ...` | `hybridrag db show specstory` |
| 5. Edit registry YAML | Add `backend_type: postgres` + config | `cat ~/.hybridrag/registry.yaml` |
| 6. Initial ingestion | `hybridrag --db specstory ingest ...` | `hybridrag --db specstory status` |
| 7. Start watcher | `hybridrag --db specstory db watch start` | `hybridrag db watch status` |
| 8. Configure MCP | Edit Claude settings JSON | Tools appear in Claude |

**Your setup is complete!** New SpecStory conversations will be automatically ingested every 5 minutes, and all 8 MCP tools will query from PostgreSQL.
