# HybridRAG Setup Verification Guide

**Purpose:** Verify your HybridRAG installation is working correctly
**When to use:** After initial setup, after updates, when troubleshooting
**Time required:** 5 minutes

---

## Quick Verification Checklist

- [ ] Watcher is running
- [ ] PostgreSQL is receiving data
- [ ] MCP tools respond (not hang)
- [ ] Queries return relevant results
- [ ] Workspace isolation is correct

---

## 1. Check Watcher Status

### Verify Watcher is Running

```bash
python hybridrag.py db watch status
```

**Expected Output:**
```
🔍 Watcher Status: azure-specstory
==================================================
   Status: 🟢 Running (PID: 1234567)
   Auto-watch: True
   Interval: 300s
   Source: /home/user/Documents/code
```

✅ **PASS:** Status shows "🟢 Running"
❌ **FAIL:** Status shows "🔴 Stopped" → Run: `python hybridrag.py db watch start <database-name>`

### Check Watcher Progress

```bash
# Count total source files
find ~/Documents/code -path "*/.specstory/history/*.md" 2>/dev/null | wc -l

# Count ingested documents (PostgreSQL)
docker exec hybridrag-postgres-<workspace> psql -U hybridrag -d <dbname> -c \
  "SELECT COUNT(*) FROM lightrag_doc_full WHERE workspace = '<workspace>';"
```

**Example Output:**
```
Total source files: 3,128
Ingested documents: 1,237
Progress: 40% (1,237 / 3,128)
```

**Notes:**
- Watcher processes files every 5 minutes (default interval: 300s)
- Initial ingestion takes time: ~5-10 files/minute depending on size
- For 3,000+ files, expect several hours for complete ingestion

---

## 2. Verify PostgreSQL Backend

### Check Database Connection

```bash
docker ps | grep hybridrag-postgres
```

**Expected:** Container running, ports mapped (e.g., `0.0.0.0:5434->5432/tcp`)

### Verify Data is Being Stored

```bash
# Get database statistics
docker exec hybridrag-postgres-<workspace> psql -U hybridrag -d <dbname> -c "
SELECT
  COUNT(*) as total_docs,
  MAX(create_time) as latest_ingestion
FROM lightrag_doc_full
WHERE workspace = '<workspace>';
"
```

**Expected Output:**
```
 total_docs |  latest_ingestion
------------+---------------------
       1237 | 2026-02-08 16:29:15
```

✅ **PASS:**
- `total_docs` > 0
- `latest_ingestion` is recent (within last hour if watcher is active)

❌ **FAIL:**
- `total_docs` = 0 → Check watcher logs, verify source folder path
- Old timestamp → Watcher may have stopped

### Check Vector Embeddings

```bash
# Count vector embeddings
docker exec hybridrag-postgres-<workspace> psql -U hybridrag -d <dbname> -c \
  "SELECT COUNT(*) FROM lightrag_vdb_chunks WHERE workspace = '<workspace>';"
```

**Expected:** Should be much higher than document count (one doc = many chunks)

**Example:**
- Documents: 1,237
- Vector chunks: 41,362
- Ratio: ~33 chunks per document

### Verify Workspace Isolation (CRITICAL!)

```bash
# Check all workspaces in database
docker exec hybridrag-postgres-<workspace> psql -U hybridrag -d <dbname> -c \
  "SELECT workspace, COUNT(*) FROM lightrag_vdb_chunks GROUP BY workspace;"
```

**Expected Output:**
```
    workspace    | count
-----------------+-------
 azure-specstory | 41362
```

✅ **PASS:** Only shows YOUR workspace(s), NOT "default"
❌ **FAIL:** Shows "default" workspace → **DATA CORRUPTION RISK!** See [CRITICAL_CONFIGURATION.md](CRITICAL_CONFIGURATION.md)

---

## 3. Test MCP Tools

### Prerequisites

1. **Restart MCP server** after any code changes:
   ```bash
   # In Claude Code
   /mcp
   ```

2. **Use queries that match your actual data**

### ❌ Common Mistake: Testing with Random Queries

```bash
# DON'T DO THIS - will return "no-context" even if setup is correct!
mcp__hybridrag-specstory__hybridrag_local_query(query="docker")
```

**Result:** `Sorry, I'm not able to provide an answer to that question.[no-context]`

**Why this happens:**
- This is NOT a failure!
- "docker" may not exist in your specstory data
- The tool is working correctly - it just doesn't have matching content

### ✅ Correct Testing Approach

**Step 1:** Find topics that exist in your data

```bash
# List recent specstory files to see what topics you have
ls -lt ~/Documents/code/*/.specstory/history/*.md | head -10
```

**Example topics you might find:**
- promptchain
- API development
- database setup
- error debugging
- Any project names you work on

**Step 2:** Test with known topics

```bash
# Test with a topic you KNOW exists
mcp__hybridrag-specstory__hybridrag_local_query(query="promptchain")
```

**Expected:** Returns actual content about promptchain, NOT "no-context"

### Test All Tools (5-Minute Smoke Test)

| Tool | Test Query | Expected Time | Pass Criteria |
|------|------------|---------------|---------------|
| `hybridrag_health_check` | (no params) | <1s | Status: ✅ HEALTHY |
| `hybridrag_database_status` | (no params) | <1s | Shows backend: postgres |
| `hybridrag_local_query` | query="<known-topic>" | 10-30s | Returns content (not no-context) |
| `hybridrag_extract_context` | query="<known-topic>" | 10-30s | Returns chunks (not no-context) |
| `hybridrag_global_query` | query="main topics" | 30-60s | Returns overview |
| `hybridrag_get_logs` | limit=10 | <1s | Shows recent logs |

**Pass Threshold:**
- ✅ All tools complete within expected time (no 7-hour hangs!)
- ✅ At least one query returns actual content (not all "no-context")

### What "no-context" Means

| Scenario | Meaning | Action |
|----------|---------|--------|
| All queries return "no-context" | Setup problem | Check watcher, verify PostgreSQL data |
| Random queries return "no-context" | Normal behavior | Query doesn't match your data |
| Known topics return "no-context" | Data not indexed | Check embedding dimension, workspace |

---

## 4. Common Issues & Solutions

### Issue: Tools Hang for Minutes/Hours

**Symptoms:**
- Query runs for 5+ minutes
- No timeout after 60 seconds
- MCP tool never returns

**Causes:**
1. Using old/broken code version
2. MCP server not restarted after code changes
3. Actual query complexity (multihop can take 2-15 minutes)

**Solutions:**
```bash
# 1. Pull latest working code
git fetch origin
git reset --hard origin/master

# 2. Restart MCP server
# In Claude Code: /mcp

# 3. For complex queries, use background tasks (multihop, global)
# These run async and return task IDs
```

### Issue: Watcher Not Processing Files

**Check:**
```bash
# 1. Is watcher running?
python hybridrag.py db watch status

# 2. Check watcher logs
tail -f ~/.hybridrag/logs/watcher-*.log

# 3. Check for errors in source folder access
ls -la /path/to/source/folder/.specstory/history/
```

**Common causes:**
- Source folder path incorrect in registry
- Permission issues accessing .specstory folders
- Watcher crashed (check PID exists: `ps aux | grep <PID>`)

**Solution:**
```bash
# Restart watcher
python hybridrag.py db watch stop <database>
python hybridrag.py db watch start <database>
```

### Issue: PostgreSQL Shows No Data

**Diagnostic steps:**

```bash
# 1. Check container is running
docker ps | grep postgres

# 2. Check database exists
docker exec <container> psql -U hybridrag -l

# 3. Check tables exist
docker exec <container> psql -U hybridrag -d <dbname> -c "\dt"

# 4. Check workspace configuration
grep "postgres_workspace" ~/.hybridrag/registry.yaml
```

**Expected workspace config:**
```yaml
backend_config:
  postgres_workspace: azure-specstory  # Must be unique!
```

### Issue: Wrong Embedding Dimension

**Symptoms:**
- Queries return "no query context could be built"
- Embeddings stored but queries fail
- Vector search returns 0 results

**Check:**
```bash
grep "EMBEDDING_DIM" .env
```

**Must match your model:**
- `text-embedding-3-small`: 1536 (Azure & OpenAI)
- `text-embedding-3-large`: 3072
- `text-embedding-ada-002`: 1536

**Solution:**
```bash
# Fix in .env
EMBEDDING_DIM=1536

# Rebuild embeddings (if wrong dimension was used)
# WARNING: This re-ingests ALL documents!
python hybridrag.py db rebuild-embeddings <database>
```

---

## 5. Performance Benchmarks

### Expected Query Times (for reference)

| Query Type | Typical Time | Max Acceptable | Tool |
|------------|--------------|----------------|------|
| Health check | <1s | 2s | hybridrag_health_check |
| Database status | <1s | 2s | hybridrag_database_status |
| Local query | 8-15s | 60s | hybridrag_local_query |
| Global query | 20-40s | 120s | hybridrag_global_query |
| Hybrid query | 30-60s | 180s | hybridrag_hybrid_query |
| Extract context | 8-15s | 60s | hybridrag_extract_context |
| Multihop | 2-15min | 15min | hybridrag_multihop_query (background) |

**Note:** Times vary based on:
- Dataset size (more docs = slower)
- Azure API latency
- Query complexity
- PostgreSQL performance

### Ingestion Performance

**Expected rates:**
- Small files (<50KB): ~10 files/minute
- Medium files (50-200KB): ~5 files/minute
- Large files (>200KB): ~2 files/minute

**For 3,000 files:**
- Estimated time: 6-10 hours
- Progress: Check every 30 minutes
- Formula: `(ingested / total) * 100 = progress %`

---

## 6. Verification Script (Copy-Paste)

Save this as `verify_hybridrag.sh`:

```bash
#!/bin/bash
set -e

echo "=== HybridRAG Verification Script ==="
echo ""

# Configuration (EDIT THESE!)
WORKSPACE="azure-specstory"
DB_NAME="specstory"
CONTAINER="hybridrag-postgres-azure-specstory"
SOURCE_FOLDER="$HOME/Documents/code"

echo "1. Checking watcher status..."
python hybridrag.py db watch status | grep -E "Status|Running" || echo "❌ Watcher not running!"
echo ""

echo "2. Counting source files..."
TOTAL_FILES=$(find "$SOURCE_FOLDER" -path "*/.specstory/history/*.md" 2>/dev/null | wc -l)
echo "   Total .specstory files: $TOTAL_FILES"
echo ""

echo "3. Checking PostgreSQL data..."
INGESTED=$(docker exec "$CONTAINER" psql -U hybridrag -d "$DB_NAME" -tAc \
  "SELECT COUNT(*) FROM lightrag_doc_full WHERE workspace = '$WORKSPACE';")
echo "   Ingested documents: $INGESTED"
echo ""

echo "4. Calculating progress..."
if [ "$TOTAL_FILES" -gt 0 ]; then
  PROGRESS=$(( INGESTED * 100 / TOTAL_FILES ))
  echo "   Progress: $PROGRESS% ($INGESTED / $TOTAL_FILES)"
else
  echo "   ⚠️  No source files found!"
fi
echo ""

echo "5. Checking latest ingestion..."
LATEST=$(docker exec "$CONTAINER" psql -U hybridrag -d "$DB_NAME" -tAc \
  "SELECT MAX(create_time) FROM lightrag_doc_full WHERE workspace = '$WORKSPACE';")
echo "   Latest ingestion: $LATEST"
echo ""

echo "6. Verifying workspace isolation..."
docker exec "$CONTAINER" psql -U hybridrag -d "$DB_NAME" -c \
  "SELECT workspace, COUNT(*) FROM lightrag_vdb_chunks GROUP BY workspace;"
echo ""

echo "=== Verification Complete ==="
echo ""
echo "Next steps:"
echo "  - If progress < 100%, wait for watcher to finish"
echo "  - Test MCP tools with queries matching your data"
echo "  - Check that workspace shows '$WORKSPACE' (not 'default')"
```

**Usage:**
```bash
chmod +x verify_hybridrag.sh
./verify_hybridrag.sh
```

---

## Summary: How to Know Everything is Working

✅ **Your setup is working correctly if:**

1. **Watcher shows:** 🟢 Running
2. **PostgreSQL has:** Documents > 0, recent timestamp
3. **Workspace is:** Your workspace name (NOT "default")
4. **MCP tools:** Complete in <60s (no infinite hangs)
5. **Queries about known topics:** Return actual content

❌ **You have a problem if:**

1. Watcher shows: 🔴 Stopped
2. PostgreSQL has: 0 documents, or old timestamp
3. Workspace is: "default" (data corruption!)
4. MCP tools: Hang for 5+ minutes
5. All queries: Return "no-context" (even known topics)

---

## Next Steps After Verification

### If Everything Works ✅
- Start using MCP tools in Claude Code
- Let watcher continue ingesting (check progress periodically)
- See [USAGE_PATTERNS.md](USAGE_PATTERNS.md) for query best practices

### If Issues Found ❌
- Check [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- Review [CRITICAL_CONFIGURATION.md](CRITICAL_CONFIGURATION.md)
- Check watcher logs: `~/.hybridrag/logs/watcher-*.log`

### For SpecStory-Specific Setup
- See [SPECSTORY_QUICKSTART.md](SPECSTORY_QUICKSTART.md)
- See [YOUR_AZURE_SPECSTORY_CONFIG.md](YOUR_AZURE_SPECSTORY_CONFIG.md)

---

**Last Updated:** 2026-02-08
**Tested On:** Azure-based SpecStory setup with PostgreSQL backend
