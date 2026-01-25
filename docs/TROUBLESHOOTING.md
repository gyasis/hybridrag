# HybridRAG Troubleshooting Guide

**Last Updated:** 2026-01-25

This guide consolidates all known issues and their solutions. Issues are organized by category, with the most critical problems listed first.

---

## Table of Contents

1. [Critical Issues](#critical-issues)
2. [MCP Server Issues](#mcp-server-issues)
3. [Query/Search Issues](#querysearch-issues)
4. [PostgreSQL Issues](#postgresql-issues)
5. [Ingestion Issues](#ingestion-issues)
6. [Docker Issues](#docker-issues)
7. [Performance Issues](#performance-issues)
8. [Diagnostic Commands](#diagnostic-commands)

---

## Critical Issues

### MCP Server Returns Garbled/Invalid JSON

**Severity:** Critical - Completely breaks MCP integration

**Symptoms:**
- Claude Code shows "Error: Invalid JSON in MCP response"
- Tool calls fail with parse errors
- MCP server appears to work but responses are corrupted

**Root Cause:** `litellm.set_verbose = True` in server code writes debug output to stdout, corrupting the MCP stdio protocol.

**Solution:**
```python
# In hybridrag_mcp/server.py (around line 152)

# WRONG - corrupts MCP stdio protocol
litellm.set_verbose = True

# CORRECT - MCP works properly
litellm.set_verbose = False
```

**Verification:**
```bash
# Test MCP server manually
echo '{"jsonrpc":"2.0","method":"tools/list","id":1}' | \
  python -m hybridrag_mcp.server

# Should return clean JSON, no debug text
```

---

### EMBEDDING_DIM Mismatch

**Severity:** Critical - Queries return no results

**Symptoms:**
- "No query context could be built" in responses
- Queries return empty results despite ingested data
- Vector similarity search fails silently

**Root Cause:** `EMBEDDING_DIM` environment variable doesn't match your embedding model's output dimension.

**Common Dimensions:**

| Model | Dimension |
|-------|-----------|
| Azure text-embedding-3-small | 768 |
| OpenAI text-embedding-3-small | 1536 |
| OpenAI text-embedding-3-large | 3072 |
| text-embedding-ada-002 | 1536 |

**Solution:**
```bash
# In .env or environment
EMBEDDING_DIM=768  # Match your model!

# In .claude.json for MCP
"env": {
  "EMBEDDING_DIM": "768"
}
```

**Detect Your Dimension:**
```python
# From existing JSON data
import json, base64, zlib
with open('lightrag_db/vdb_chunks.json') as f:
    data = json.load(f)
    chunk = data['data'][0]
    decoded = base64.b64decode(chunk['vector'])
    decompressed = zlib.decompress(decoded)
    print(f'Dimension: {len(decompressed) // 4}')
```

**After Fixing:** You must re-ingest all documents.

---

## MCP Server Issues

### Server Fails to Start

**Symptoms:**
- "ERROR: OPENAI_API_KEY not found in environment"
- Server exits immediately

**Solution:**
```bash
# Check environment variables
env | grep -E "(OPENAI|AZURE|HYBRIDRAG)"

# Ensure .env is loaded or variables are exported
source .env
export AZURE_API_KEY=your-key
```

### Server Starts but Tools Don't Work

**Symptoms:**
- Tools appear in Claude Code
- Calling tools returns errors or empty results

**Debug Steps:**
1. Check server logs:
   ```bash
   tail -f ~/.hybridrag/logs/mcp_server.log
   ```

2. Test query directly:
   ```bash
   python hybridrag.py query \
     --database specstory \
     --text "test query"
   ```

3. Verify database has data:
   ```bash
   python hybridrag.py database status --name specstory
   ```

### MCP Server Timeout

**Symptoms:**
- Tools hang for 30+ seconds
- "Tool timed out" errors

**Causes & Solutions:**
1. **Large result sets:** Reduce `top_k` parameter
2. **Slow LLM API:** Check API latency
3. **PostgreSQL connection issues:** Verify database is responsive

---

## Query/Search Issues

### "No Query Context Could Be Built"

**Causes:**
1. EMBEDDING_DIM mismatch (see Critical Issues)
2. Empty database
3. Query unrelated to ingested content

**Diagnostic:**
```bash
# Check database has documents
python hybridrag.py database status --name specstory

# Check vector store has embeddings
# For JSON backend:
ls -la lightrag_db/vdb_*.json

# For PostgreSQL:
docker exec hybridrag-postgres psql -U hybridrag -d hybridrag \
  -c "SELECT COUNT(*) FROM lightrag_vdb_chunks;"
```

### Queries Return Irrelevant Results

**Causes:**
1. Wrong search mode for query type
2. Insufficient context in documents

**Solution:**
```bash
# Try different modes
python hybridrag.py query --mode local --text "..."   # Entity-focused
python hybridrag.py query --mode global --text "..."  # Topic-focused
python hybridrag.py query --mode hybrid --text "..."  # Combined
```

### Agentic Mode Fails

**Symptoms:**
- Multi-hop reasoning doesn't work
- Agent returns partial results

**Check:**
```bash
# Verify agentic model is set
echo $AGENTIC_MODEL

# Should be a capable model like gpt-4 or gpt-5
AGENTIC_MODEL=azure/gpt-5.1
```

---

## PostgreSQL Issues

### "function create_graph(unknown) does not exist"

**Cause:** Apache AGE extension not installed

**Solution:**
```bash
docker exec hybridrag-postgres psql -U hybridrag -d hybridrag \
  -c "CREATE EXTENSION IF NOT EXISTS age;"
```

### "type vector does not exist"

**Cause:** pgvector extension not installed

**Solution:**
```bash
# Install pgvector package
docker exec hybridrag-postgres bash -c \
  "apt-get update && apt-get install -y postgresql-17-pgvector"

# Create extension
docker exec hybridrag-postgres psql -U hybridrag -d hybridrag \
  -c "CREATE EXTENSION IF NOT EXISTS vector;"

# Restart container
docker restart hybridrag-postgres
```

### Connection Refused

**Causes:**
1. PostgreSQL not running
2. Wrong port
3. Firewall blocking

**Diagnostic:**
```bash
# Check container status
docker ps | grep hybridrag

# Check port mapping
docker port hybridrag-postgres

# Test connection
docker exec hybridrag-postgres pg_isready -U hybridrag
```

### Wrong Image Used (pgvector/pgvector:pg16)

**Cause:** Using pgvector-only image instead of AGE image

**Symptom:** Missing `create_graph` function

**Solution:** Use `apache/age:latest` image with pgvector installed:
```yaml
services:
  postgres:
    image: apache/age:latest  # NOT pgvector/pgvector:pg16
    entrypoint: >
      bash -c "
        apt-get update &&
        apt-get install -y postgresql-17-pgvector &&
        docker-entrypoint.sh postgres
      "
```

### Too Many Connections

**Symptom:** "FATAL: too many connections for role"

**Solution:**
```bash
# Check connections
docker exec hybridrag-postgres psql -U hybridrag -c \
  "SELECT count(*) FROM pg_stat_activity;"

# Increase limit
docker exec hybridrag-postgres psql -U hybridrag -c \
  "ALTER SYSTEM SET max_connections = 200;"

# Restart
docker restart hybridrag-postgres
```

---

## Ingestion Issues

### Files Not Being Ingested

**Check:**
1. File extension is supported
2. File path matches pattern
3. Watcher is running (if using auto-watch)

```bash
# Check watcher status
python hybridrag.py watcher status

# Manual ingest with verbose
python hybridrag.py ingest \
  --path /path/to/files \
  --pattern "**/*.md" \
  --verbose
```

### Ingestion Very Slow

**Causes:**
1. Large files
2. Rate limiting on API
3. Inefficient batch size

**Solutions:**
```bash
# Increase batch size
HYBRIDRAG_BATCH_SIZE=20

# Check rate limiting
# Look for 429 errors in logs

# Use incremental mode
python hybridrag.py ingest --incremental
```

### Duplicate Documents

**Cause:** Re-ingesting without checking existing

**Solution:**
```bash
# Use incremental mode
python hybridrag.py ingest --incremental

# Or clear and re-ingest
python hybridrag.py database clear --name mydb
python hybridrag.py ingest --database mydb --path /source
```

---

## Docker Issues

### Container Won't Start

**Check logs:**
```bash
docker logs hybridrag-postgres
```

**Common issues:**
1. **Port in use:**
   ```bash
   lsof -i :5433
   # Change port in docker-compose if needed
   ```

2. **Data directory permissions:**
   ```bash
   sudo chown -R 999:999 ./data/postgres
   ```

3. **Insufficient memory:**
   ```bash
   # Increase Docker memory limit
   # Docker Desktop: Settings > Resources > Memory
   ```

### Extension Installation Fails

**Symptom:** "E: Unable to locate package postgresql-17-pgvector"

**Cause:** Package cache outdated

**Solution:**
```bash
# Run apt-get update first
docker exec hybridrag-postgres bash -c \
  "apt-get update && apt-get install -y postgresql-17-pgvector"
```

---

## Performance Issues

### Slow Queries

**Diagnostic:**
```bash
# Check database size
docker exec hybridrag-postgres psql -U hybridrag -d hybridrag \
  -c "SELECT pg_size_pretty(pg_database_size('hybridrag'));"

# Check for slow queries
docker exec hybridrag-postgres psql -U hybridrag -c \
  "SELECT query, calls, mean_exec_time
   FROM pg_stat_statements
   ORDER BY mean_exec_time DESC LIMIT 5;"
```

**Solutions:**
1. Add indexes:
   ```sql
   CREATE INDEX ON lightrag_vdb_chunks USING hnsw (embedding vector_cosine_ops);
   ```

2. Run VACUUM:
   ```bash
   docker exec hybridrag-postgres psql -U hybridrag -d hybridrag \
     -c "VACUUM ANALYZE;"
   ```

3. Tune PostgreSQL:
   ```bash
   # Edit docker-compose command section
   - "shared_buffers=1GB"
   - "work_mem=64MB"
   ```

### High Memory Usage

**Diagnostic:**
```bash
docker stats hybridrag-postgres
```

**Solution:** Set resource limits in docker-compose:
```yaml
deploy:
  resources:
    limits:
      memory: 2G
```

---

## Diagnostic Commands

### Quick Health Check

```bash
# Check all components
echo "=== Docker ===" && docker ps | grep hybridrag
echo "=== Database ===" && python hybridrag.py database list
echo "=== PostgreSQL ===" && docker exec hybridrag-postgres pg_isready -U hybridrag
echo "=== Extensions ===" && docker exec hybridrag-postgres psql -U hybridrag -d hybridrag \
  -c "SELECT extname FROM pg_extension WHERE extname IN ('vector', 'age');"
```

### MCP Server Debug

```bash
# Start with debug logging
HYBRIDRAG_LOG_LEVEL=DEBUG python -m hybridrag_mcp.server
```

### Database Statistics

```bash
# For PostgreSQL
docker exec hybridrag-postgres psql -U hybridrag -d hybridrag -c "
  SELECT
    'Documents' as type, COUNT(*) as count FROM lightrag_doc_full
  UNION ALL
  SELECT
    'Chunks' as type, COUNT(*) as count FROM lightrag_vdb_chunks
  UNION ALL
  SELECT
    'Entities' as type, COUNT(*) as count FROM lightrag_full_entities
  UNION ALL
  SELECT
    'Relations' as type, COUNT(*) as count FROM lightrag_full_relations;
"
```

### Log Locations

| Component | Log Path |
|-----------|----------|
| MCP Server | `~/.hybridrag/logs/mcp_server.log` |
| Watcher | `~/.hybridrag/logs/watcher.log` |
| Ingestion | `~/.hybridrag/logs/ingestion.log` |
| PostgreSQL | `docker logs hybridrag-postgres` |

---

## Getting Help

If your issue isn't covered here:

1. Check [GitHub Issues](https://github.com/yourusername/hybridrag/issues)
2. Review related documentation:
   - [FRESH_INSTALL.md](./FRESH_INSTALL.md)
   - [POSTGRESQL_BACKEND_SETUP.md](./technical/POSTGRESQL_BACKEND_SETUP.md)
3. Gather diagnostic info using commands above
4. Open a new issue with:
   - Error messages
   - Steps to reproduce
   - Environment details (OS, Python version, Docker version)
   - Relevant log output
