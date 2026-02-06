# HybridRAG MCP Server - Dev Testing Guide

## Quick Start: FastMCP Dev Mode

FastMCP provides a web-based inspector for manually testing MCP tools.

### Required Environment Variable

```bash
# The database path (NOT the registry path!)
export HYBRIDRAG_DATABASE=/home/gyasisutton/dev/tools/RAG/hybridrag/lightrag_db
```

**IMPORTANT:** The database is at `lightrag_db/`, NOT `~/.hybridrag/specstory`.
The `~/.hybridrag/registry.yaml` only stores configuration metadata.

---

## Running the Dev Server

### Option 1: Inline Environment Variable (Recommended)

```bash
cd /home/gyasisutton/dev/tools/RAG/hybridrag

HYBRIDRAG_DATABASE=/home/gyasisutton/dev/tools/RAG/hybridrag/lightrag_db \
  uv run fastmcp dev hybridrag_mcp/server.py
```

### Option 2: Export First, Then Run

```bash
cd /home/gyasisutton/dev/tools/RAG/hybridrag

export HYBRIDRAG_DATABASE=/home/gyasisutton/dev/tools/RAG/hybridrag/lightrag_db
uv run fastmcp dev hybridrag_mcp/server.py
```

### Option 3: With Model Override

```bash
cd /home/gyasisutton/dev/tools/RAG/hybridrag

HYBRIDRAG_DATABASE=/home/gyasisutton/dev/tools/RAG/hybridrag/lightrag_db \
HYBRIDRAG_MODEL=azure/gpt-4o \
  uv run fastmcp dev hybridrag_mcp/server.py
```

---

## What the Dev Server Provides

Once started, the FastMCP dev server opens a web UI (usually `http://localhost:5173`) with:

1. **Tool Inspector** - Lists all available tools with their schemas
2. **Manual Testing** - Enter inputs and execute tools interactively
3. **Real-time Logs** - See server logs and responses live
4. **Schema Validation** - Validates inputs before sending

---

## Environment Variables Reference

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `HYBRIDRAG_DATABASE` | **Yes** | Path to LightRAG database directory | `/home/gyasisutton/dev/tools/RAG/hybridrag/lightrag_db` |
| `HYBRIDRAG_MODEL` | No | LLM model override | `azure/gpt-4o` |
| `HYBRIDRAG_EMBED_MODEL` | No | Embedding model override | `text-embedding-3-small` |

---

## Database Path vs Registry Path

```
~/.hybridrag/registry.yaml     <- Configuration file (NOT the database)
~/.hybridrag/watchers/         <- Watcher state files

/path/to/hybridrag/lightrag_db/  <- ACTUAL DATABASE (use this!)
  ├── graph_chunk_entity_relation.graphml
  ├── vdb_entities.json
  ├── vdb_relationships.json
  └── kv_store_*/
```

The registry at `~/.hybridrag/registry.yaml` contains metadata about databases:
```yaml
databases:
  specstory:
    name: specstory
    path: /home/gyasisutton/dev/tools/RAG/hybridrag/lightrag_db  # <- Use THIS path
    source_folder: /home/gyasisutton/dev/jira-issues
```

---

## Troubleshooting

### Error: "HYBRIDRAG_DATABASE environment variable not set"

You forgot to set the environment variable. Use:
```bash
HYBRIDRAG_DATABASE=/home/gyasisutton/dev/tools/RAG/hybridrag/lightrag_db uv run fastmcp dev hybridrag_mcp/server.py
```

### Error: "Database path does not exist"

You're using the wrong path. Check the actual database location:
```bash
cat ~/.hybridrag/registry.yaml | grep path
```

### Tool Timeouts in Dev Mode

The dev server may have different timeout behavior than production. Check:
1. Server logs in `/tmp/hybridrag_mcp_logs/`
2. LiteLLM logs for API issues
3. Database size (large DBs = slower queries)

---

## Tool Tiers for Testing

When testing, follow the tiered approach:

| Tier | Tools | Expected Speed |
|------|-------|----------------|
| T1 (Instant) | `database_status`, `health_check`, `get_logs` | <5s |
| T2 (Fast) | `local_query`, `extract_context` | <30s |
| T3 (Medium) | `global_query`, `hybrid_query`, `query` | 30-180s |
| T4 (Slow) | `multihop_query` | 2-15 min |

**Test T1 first** to verify the server is working before testing slower tools.

---

## Checking Logs After Testing

```bash
# View HybridRAG logs
cat /tmp/hybridrag_mcp_logs/hybridrag_*.log | tail -100

# View LiteLLM logs (for LLM API issues)
cat /tmp/hybridrag_mcp_logs/litellm_*.log | tail -100
```
