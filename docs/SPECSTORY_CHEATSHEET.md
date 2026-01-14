# SpecStory Cheatsheet

> Quick reference for SpecStory-specific HybridRAG commands

---

## Setup Commands

```bash
# Initial bulk ingestion
./scripts/ingest_specstory_folders.sh ~/dev/projects fresh   # New DB
./scripts/ingest_specstory_folders.sh ~/dev/projects add     # Add to existing

# Register database
python hybridrag.py db register specstory \
    --path ./lightrag_db \
    --source ~/dev/projects \
    --type specstory \
    --auto-watch \
    --interval 300 \
    --jira-project PROJ              # Optional: JIRA integration
```

---

## Watcher Management

```bash
# Start/Stop
python hybridrag.py db watch start specstory
python hybridrag.py db watch stop specstory

# Status
python hybridrag.py db watch status           # All watchers
python hybridrag.py db watch status specstory # Specific

# Systemd (persistent)
python hybridrag.py db watch start specstory --systemd
systemctl --user status hybridrag-watcher@specstory.service
journalctl --user -u hybridrag-watcher@specstory.service -f
```

---

## Query Commands

```bash
# Basic query
python hybridrag.py --db specstory query "your question"

# Query modes
python hybridrag.py --db specstory query "..." --mode local    # Specific entities
python hybridrag.py --db specstory query "..." --mode global   # Overviews
python hybridrag.py --db specstory query "..." --mode hybrid   # Balanced (default)
python hybridrag.py --db specstory query "..." --mode naive    # Simple search
python hybridrag.py --db specstory query "..." --mode mix      # All strategies

# Multi-hop reasoning (complex queries)
python hybridrag.py --db specstory query "Compare X with Y" --multihop
python hybridrag.py --db specstory query "..." --multihop --verbose

# Interactive mode
python hybridrag.py --db specstory interactive
```

### Interactive Mode Commands

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

## Database Management

```bash
# List/Show
python hybridrag.py db list
python hybridrag.py db show specstory

# Update settings
python hybridrag.py db update specstory --interval 600        # 10 min
python hybridrag.py db update specstory --model azure/gpt-4o
python hybridrag.py db update specstory --auto-watch false

# Sync/Re-ingest
python hybridrag.py db sync specstory                         # Incremental
python hybridrag.py db sync specstory --fresh                 # Full re-ingest

# Remove (keeps data files)
python hybridrag.py db unregister specstory
```

---

## Query Mode Selection

| Query Type | Mode | Example |
|------------|------|---------|
| Specific function/class | `local` | "getUserById implementation" |
| Architecture overview | `global` | "How does auth work?" |
| General question | `hybrid` | "Database patterns used" |
| Simple keyword search | `naive` | "error handling" |
| Comprehensive research | `mix` | "All ETL approaches" |
| Complex comparison | `multihop` | "Compare v1 vs v2 API" |

---

## PostgreSQL Backend

```bash
# Setup Docker
python hybridrag.py backend setup-docker --password mypass

# Register with PostgreSQL
python hybridrag.py db register specstory-pg \
    --path ./pg_db \
    --source ~/dev/projects \
    --type specstory \
    --backend postgres \
    --connection-string "postgresql://hybridrag:mypass@localhost:5432/hybridrag"

# Migrate existing JSON to PostgreSQL
python hybridrag.py backend migrate specstory \
    --connection-string "postgresql://..." \
    --staged                              # Safe 4-phase migration
```

---

## MCP Server (Claude Desktop)

```bash
# Start server
HYBRIDRAG_DATABASE=./lightrag_db python -m hybridrag_mcp.server

# Or with uv
uv run python -m hybridrag_mcp.server
```

**Claude Desktop config.json:**
```json
{
  "mcpServers": {
    "hybridrag": {
      "command": "uv",
      "args": ["--directory", "/path/to/hybridrag", "run", "python", "-m", "hybridrag_mcp.server"],
      "env": {
        "HYBRIDRAG_DATABASE": "/path/to/lightrag_db"
      }
    }
  }
}
```

---

## Monitoring

```bash
# TUI Dashboard
python hybridrag.py monitor
python hybridrag.py monitor --new      # Start with wizard

# Quick status
python hybridrag.py --db specstory status
python hybridrag.py --db specstory check-db
```

---

## Files & Paths

| Item | Location |
|------|----------|
| Registry | `~/.hybridrag/registry.yaml` |
| PID files | `~/.hybridrag/watchers/<name>.pid` |
| Watcher logs | `./logs/watcher_<name>.log` |
| Database files | `<path>/kv_store_*.json`, `vdb_*.json`, `*.graphml` |

---

## Common Issues

```bash
# Stale PID file
rm ~/.hybridrag/watchers/specstory.pid

# Force re-registration
python hybridrag.py db unregister specstory
python hybridrag.py db register specstory --path ./lightrag_db --source ~/dev/projects --type specstory

# Check .specstory folders exist
find ~/dev/projects -type d -name ".specstory" | head -10

# View detailed logs
tail -100 logs/watcher_specstory.log
```
