# HybridRAG Cheatsheet

> Complete command reference for HybridRAG

---

## Ingestion

```bash
# Basic ingestion
python hybridrag.py ingest --folder ./docs

# Multiple folders
python hybridrag.py ingest --folder ./docs --folder ./code --folder ./notes

# With options
python hybridrag.py ingest --folder ./docs \
    --recursive                           # Recursive scan (default: true)
    --db-action fresh                     # fresh|use|add
    --metadata project=myproject          # Add metadata
    --quiet                               # Suppress output
    --yes                                 # Skip confirmations
```

---

## Database Registry

### Register

```bash
# Basic registration
python hybridrag.py db register mydb --path ./db_data --source ./docs

# Full options
python hybridrag.py db register mydb \
    --path ./db_data \
    --source ./docs \
    --type filesystem                     # filesystem|specstory|api|schema
    --auto-watch \
    --interval 300 \
    --model azure/gpt-4o \
    --description "Project documentation" \
    --extensions ".md,.txt,.py" \
    --backend json                        # json|postgres
    --connection-string "postgresql://..."  # For postgres backend
```

### Manage

```bash
python hybridrag.py db list                    # List all databases
python hybridrag.py db show mydb               # Show details
python hybridrag.py db update mydb --interval 600
python hybridrag.py db sync mydb               # Incremental sync
python hybridrag.py db sync mydb --fresh       # Full re-ingest
python hybridrag.py db unregister mydb         # Remove (keeps files)
```

---

## Watcher Management

```bash
# Control
python hybridrag.py db watch start mydb
python hybridrag.py db watch stop mydb
python hybridrag.py db watch status
python hybridrag.py db watch status mydb

# Systemd integration
python hybridrag.py db watch start mydb --systemd
python hybridrag.py db watch install-systemd   # All auto-watch DBs
python hybridrag.py db watch uninstall-systemd

# Systemctl commands
systemctl --user status hybridrag-watcher@mydb.service
systemctl --user restart hybridrag-watcher@mydb.service
journalctl --user -u hybridrag-watcher@mydb.service -f
```

---

## Query Commands

### Basic Queries

```bash
python hybridrag.py query "your question"
python hybridrag.py --db mydb query "your question"
```

### Query Modes

```bash
python hybridrag.py query "..." --mode local     # Specific entities
python hybridrag.py query "..." --mode global    # Overviews/summaries
python hybridrag.py query "..." --mode hybrid    # Balanced (default)
python hybridrag.py query "..." --mode naive     # Simple vector search
python hybridrag.py query "..." --mode mix       # All strategies combined
```

### Advanced Queries

```bash
# Multi-hop reasoning (complex analysis)
python hybridrag.py query "Compare X with Y" --multihop
python hybridrag.py query "Trace flow from A to B" --multihop --verbose

# Agentic mode
python hybridrag.py query "..." --agentic

# Context-only (raw chunks, no LLM synthesis)
python hybridrag.py query "..." --context-only
```

### Interactive Mode

```bash
python hybridrag.py interactive
python hybridrag.py --db mydb interactive
```

**Interactive Commands:**
```
:local, :global, :hybrid, :naive, :mix   # Switch mode
:multihop                                 # Toggle multi-hop
:verbose                                  # Toggle verbose
:context                                  # Context-only mode
:stats                                    # Database stats
:help                                     # Help
:quit                                     # Exit
```

---

## Query Mode Selection Guide

| Use Case | Mode | Example Query |
|----------|------|---------------|
| Find specific function/class | `local` | "getUserById implementation" |
| Architecture overview | `global` | "How does the system work?" |
| General question | `hybrid` | "Best practices for error handling" |
| Keyword search | `naive` | "authentication" |
| Comprehensive research | `mix` | "All caching strategies used" |
| Compare/analyze | `multihop` | "Differences between v1 and v2" |
| Trace flow/lineage | `multihop` | "How data flows from API to DB" |

---

## Backend Management

### JSON Backend (Default)

```bash
python hybridrag.py db register mydb --path ./db --source ./docs
# Files: kv_store_*.json, vdb_*.json, *.graphml
```

### PostgreSQL Backend

```bash
# Setup Docker PostgreSQL
python hybridrag.py backend setup-docker \
    --port 5432 \
    --password mypass \
    --data-dir ~/.hybridrag/pg-data

# Register with PostgreSQL
python hybridrag.py db register mydb \
    --path ./db \
    --source ./docs \
    --backend postgres \
    --connection-string "postgresql://hybridrag:mypass@localhost:5432/hybridrag"

# Or with individual params
python hybridrag.py db register mydb \
    --backend postgres \
    --postgres-host localhost \
    --postgres-port 5432 \
    --postgres-user hybridrag \
    --postgres-password mypass \
    --postgres-database hybridrag
```

### Migration (JSON → PostgreSQL)

```bash
# Preview migration
python hybridrag.py backend migrate mydb --connection-string "..." --dry-run

# Safe staged migration
python hybridrag.py backend migrate mydb \
    --connection-string "postgresql://..." \
    --staged \
    --batch-size 1000

# Backup management
python hybridrag.py backend migrate mydb --backup-only
python hybridrag.py backend migrate mydb --list-backups
python hybridrag.py backend migrate mydb --rollback BACKUP_ID

# Check status
python hybridrag.py backend status mydb
```

---

## Monitoring

```bash
# TUI Dashboard
python hybridrag.py monitor
python hybridrag.py monitor --refresh 5      # Custom refresh rate
python hybridrag.py monitor --new            # Start with wizard
python hybridrag.py monitor --mouse          # Enable mouse support

# Quick status
python hybridrag.py status
python hybridrag.py check-db
python hybridrag.py snapshot
python hybridrag.py db-info
```

---

## MCP Server (Claude Desktop)

### Start Server

```bash
HYBRIDRAG_DATABASE=./lightrag_db python -m hybridrag_mcp.server

# With uv
uv run python -m hybridrag_mcp.server
```

### Claude Desktop Configuration

**~/.config/Claude/claude_desktop_config.json:**
```json
{
  "mcpServers": {
    "hybridrag": {
      "command": "uv",
      "args": ["--directory", "/path/to/hybridrag", "run", "python", "-m", "hybridrag_mcp.server"],
      "env": {
        "HYBRIDRAG_DATABASE": "/path/to/lightrag_db",
        "LIGHTRAG_MODEL": "azure/gpt-4o"
      }
    }
  }
}
```

### MCP Tools Available

| Tool | Description |
|------|-------------|
| `hybridrag_query` | Main query with mode selection |
| `hybridrag_local_query` | Entity-focused queries |
| `hybridrag_global_query` | Overview/pattern queries |
| `hybridrag_hybrid_query` | Balanced queries (recommended) |
| `hybridrag_multihop_query` | Complex multi-step analysis |
| `hybridrag_extract_context` | Raw chunks without LLM |
| `hybridrag_database_status` | Database health check |

---

## Global Options

```bash
python hybridrag.py [global-opts] command [command-opts]

# Global options
--config PATH              # Config file
--working-dir PATH         # Database directory (default: ./lightrag_db)
--db NAME                  # Use registered database by name
--model MODEL              # Override LLM model
--embed-model MODEL        # Override embedding model
```

---

## Environment Variables

```bash
# Database
export HYBRIDRAG_DATABASE=./lightrag_db
export HYBRIDRAG_CONFIG=~/.hybridrag/custom-registry.yaml

# Models (via LiteLLM)
export LIGHTRAG_MODEL=azure/gpt-4o
export LIGHTRAG_EMBED_MODEL=azure/text-embedding-3-small

# Azure OpenAI
export AZURE_API_KEY=xxx
export AZURE_API_BASE=https://xxx.openai.azure.com

# OpenAI
export OPENAI_API_KEY=xxx

# Anthropic
export ANTHROPIC_API_KEY=xxx

# Google
export GEMINI_API_KEY=xxx
```

---

## Supported Models

```bash
# Azure OpenAI
--model azure/gpt-4o
--model azure/gpt-5.1

# OpenAI
--model openai/gpt-4o
--model openai/gpt-4-turbo

# Anthropic
--model anthropic/claude-opus
--model anthropic/claude-sonnet

# Google
--model gemini/gemini-pro
--model gemini/gemini-2.0-flash

# Ollama (local)
--model ollama/llama2
--model ollama/mixtral
```

---

## File Locations

| Item | Path |
|------|------|
| Registry | `~/.hybridrag/registry.yaml` |
| Config pointer | `~/.hybridrag/config_pointer` |
| PID files | `~/.hybridrag/watchers/<name>.pid` |
| Watcher logs | `./logs/watcher_<name>.log` |
| Ingestion queue | `./ingestion_queue/` |
| JSON DB files | `<path>/kv_store_*.json`, `vdb_*.json`, `*.graphml` |

---

## Troubleshooting

```bash
# Stale PID file
rm ~/.hybridrag/watchers/mydb.pid

# Re-register database
python hybridrag.py db unregister mydb
python hybridrag.py db register mydb --path ./db --source ./docs

# Check database health
python hybridrag.py --db mydb check-db

# View logs
tail -f logs/watcher_mydb.log

# Test query
python hybridrag.py --db mydb query "test" --verbose

# Verify file types
find ./docs -type f | head -20
```

---

## Source Types

| Type | Use Case | Extra Options |
|------|----------|---------------|
| `filesystem` | Documents, code, notes | `--extensions` |
| `specstory` | Claude Code conversations | `--jira-project` |
| `api` | REST API sources | `--api-config` |
| `schema` | Database schemas | `--schema-config` |

---

## Performance Tips

1. **Use hybrid mode** for most queries (best balance)
2. **Use local mode** when you know the specific entity name
3. **Use global mode** for "how does X work?" questions
4. **Use multihop** only for complex comparisons/analysis
5. **PostgreSQL backend** for databases > 1GB
6. **Batch ingestion** with `--quiet` for large imports
