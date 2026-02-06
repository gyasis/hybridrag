# CLAUDE.md - HybridRAG Project Intelligence

**Purpose**: This file captures project-specific intelligence, patterns, user preferences, and critical implementation paths that improve future work effectiveness on the HybridRAG project.

---

## User Preferences (Gyasi)

### Communication Style
- **Direct and technical**: No hand-holding, assume technical competency
- **Show, don't tell**: Prefer code examples over verbose explanations
- **Results-oriented**: Focus on what works, not theoretical discussions

### Code Preferences
- **Python 3.12**: Modern Python features (match/case, type hints, etc.)
- **Async/await**: Prefer async architecture where appropriate
- **Type hints**: Use them, but not dogmatic about 100% coverage
- **Ruff over flake8**: Fast linting, auto-fixes when possible
- **Black formatting**: Standard line length (88 chars)

### Git Workflow
- **Descriptive commits**: Use conventional commit format (feat:, fix:, docs:, refactor:)
- **Co-authored commits**: Always add "Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
- **Squash when messy**: OK to squash multiple commits if history is messy
- **Never force push to main**: Seriously, don't

### Documentation Preferences
- **Markdown everywhere**: README, USAGE, docs in markdown
- **Examples over theory**: Show commands, then explain
- **Architecture diagrams**: ASCII art is fine, Mermaid if complex
- **Keep it updated**: Better to delete stale docs than leave them wrong

---

## Critical Implementation Paths

### 1. Adding a New MCP Tool

**Pattern**: Follow existing tool structure in `hybridrag_mcp/server.py`

```python
@mcp.tool(task=True)  # Use task=True for long-running queries
async def hybridrag_new_tool(
    ctx: Context,  # Required for task=True
    query: str,
    param: int = 10,
) -> str:
    """
    Brief tool description.

    Tier: T2 Tactical (estimate: <10s)

    Args:
        query: What to search for
        param: Optional parameter

    Returns:
        Formatted result with backend metadata
    """
    try:
        # Set trace ID for diagnostics
        set_trace_id(f"new_tool_{hash(query)}")

        # Implement tool logic here
        result = await some_async_operation(query, param)

        # Append backend metadata
        backend_metadata = get_backend_metadata_line()

        return f"{result}{backend_metadata}"

    except Exception as e:
        logger.error(f"new_tool failed: {e}", exc_info=True)
        return f"Error: {str(e)}"

    finally:
        clear_trace_id()
```

**Checklist**:
- [ ] Add to `hybridrag_mcp/server.py`
- [ ] Use `task=True` if >10s expected
- [ ] Add trace ID for diagnostics
- [ ] Append backend metadata
- [ ] Test with real data
- [ ] Update `docs/technical/MCP_README.md`

---

### 2. Adding a New Backend Type

**Pattern**: Implement backend adapter interface

**Steps**:
1. Add to `BackendType` enum in `src/config/backend_config.py`:
```python
class BackendType(Enum):
    NEWBACKEND = "newbackend"
```

2. Implement adapter in `src/backends/newbackend_adapter.py`:
```python
class NewBackendAdapter(BackendAdapter):
    def __init__(self, config: BackendConfig):
        self.config = config
        # Initialize connection

    def insert_entity(self, entity: Entity) -> None:
        # Implementation
        pass

    def query_local(self, query: str, top_k: int) -> List[Entity]:
        # Implementation
        pass

    # ... other methods
```

3. Add backend detection to `get_backend_metadata_line()` in `hybridrag_mcp/server.py`:
```python
elif backend_type == "newbackend":
    host = os.getenv("NEWBACKEND_HOST", "localhost")
    return f"\n\n---\n*Backend: NewBackend ({host})*"
```

4. Add migration support in `src/ingestion/migrations.py`

5. Test with real data:
```bash
hybridrag db register test_newbackend \
  --path ~/test_db \
  --source ~/test_data \
  --backend newbackend
```

---

### 3. Config Changes

**Pattern**: Separate app config from backend config

**App Config** (`src/config/app_config.py`):
- LightRAG settings (chunk size, overlap, etc.)
- Ingestion settings (batch size, extensions, etc.)
- Search settings (default mode, top_k, etc.)
- System settings (log level, temp dir, etc.)

**Backend Config** (`src/config/backend_config.py`):
- Backend type enum
- Connection parameters (host, port, db, etc.)
- Credentials (user, password, API keys, etc.)

**Registry Config** (`~/.hybridrag/registry.yaml`):
- Database entries (name, path, source, etc.)
- Per-database backend config override
- Per-database model config override

**Precedence**:
```
CLI flags > registry.yaml > .env > config/*.py defaults
```

---

### 4. Model Override Chain

**Pattern**: Explicit 5-level fallback for model selection

**Implementation** (in `hybridrag.py` or `src/lightrag_core.py`):
```python
def resolve_model(cli_model, db_entry) -> str:
    # 1. CLI --model flag (highest)
    if cli_model:
        return cli_model

    # 2. model_config.yaml
    if Path("model_config.yaml").exists():
        config = yaml.safe_load(open("model_config.yaml"))
        if config.get("llm_model"):
            return config["llm_model"]

    # 3. Registry db_entry.model_config
    if db_entry and db_entry.model_config:
        if db_entry.model_config.get("llm_model"):
            return db_entry.model_config["llm_model"]

    # 4. DEPLOYMENT_MODEL env var
    if os.getenv("DEPLOYMENT_MODEL"):
        return os.getenv("DEPLOYMENT_MODEL")

    # 5. Default fallback
    return "gpt-4o-mini"
```

**Remember**: Same pattern for embeddings (use `embedding_model` field)

---

### 5. Registry Operations

**Pattern**: Use `database_registry.py` functions

**Common operations**:
```python
from src.database_registry import (
    get_registry,
    resolve_database,
    register_database,
    update_database,
)

# Get registry
registry = get_registry()

# Resolve by name or path
db_entry = resolve_database("specstory")
db_entry = resolve_database("/home/gyasisutton/dev/jira-issues")

# Register new database
register_database(
    name="newdb",
    path="/path/to/db",
    source_folder="/path/to/source",
    backend_type="postgres",
    backend_config={...},
    model_config={...},
)

# Update existing
update_database("specstory", auto_watch=True, watch_interval=300)
```

**CLI equivalents**:
```bash
hybridrag db register newdb --path /path/to/db --source /path/to/source
hybridrag db list
hybridrag db show specstory
hybridrag db update specstory --auto-watch true
```

---

## Project-Specific Quirks

### 1. LightRAG Database Path vs Registry Path

**Quirk**: LightRAG's `working_dir` must match registry `path`

**Why**: LightRAG stores graph data in `working_dir`, registry tracks database location in `path`. If they diverge, queries will fail silently or create duplicate databases.

**Solution**: Always use registry `path` as LightRAG `working_dir`:
```python
db_entry = resolve_database("specstory")
rag = HybridLightRAGCore(working_dir=db_entry.path)
```

---

### 2. Backend Metadata Credential Masking

**Quirk**: Must use `urllib.parse` for credential masking, not regex

**Why**: Passwords can contain special chars (!, @, #, etc.) and IPv6 hosts break regex patterns.

**Solution**: Use `mask_credentials()` from `src/utils/backend_utils.py`:
```python
from src.utils.backend_utils import mask_credentials

conn_str = "postgresql://user:p@ssw0rd!@localhost:5433/db"
masked = mask_credentials(conn_str)
# Result: "postgresql://user:****@localhost:5433/db"
```

---

### 3. Delta Ingestion Timestamp Reset

**Quirk**: `.last_specstory_watch` file controls delta ingestion start date

**Why**: Watcher only processes files modified after this timestamp. If set incorrectly, may skip or reprocess files.

**Solution**: Manually set to migration date or specific time:
```bash
echo "2026-01-17T00:00:00Z" > lightrag_db/.last_specstory_watch
```

Then start watcher:
```bash
hybridrag --db specstory db watch start
```

---

### 4. MCP Tool Timeouts

**Quirk**: Long-running tools (multihop, hybrid) need `task=True` or Claude timeouts

**Why**: Claude Desktop has ~60s default timeout. Multihop queries can take 15+ minutes.

**Solution**: Always use `@mcp.tool(task=True)` for queries >10s:
```python
@mcp.tool(task=True)  # Enables background task
async def hybridrag_multihop_query(ctx: Context, query: str) -> str:
    # Long-running query...
    pass
```

---

### 5. Registry vs Environment Variables

**Quirk**: Registry can override environment variables, but not always

**Why**: Registry is parsed on CLI startup, env vars are global. Backend metadata fetches env vars at runtime.

**Solution**: Ensure consistency:
1. Set backend config in registry
2. Export env vars that match registry values
3. Or use `--show-backend` to verify what's active:
```bash
hybridrag --db specstory --show-backend status
```

---

### 6. SpecStory Folder Structure

**Quirk**: SpecStory folders have specific structure: `{PROJECT}/.specstory/*.md`

**Why**: Watcher looks for `.specstory` directories with markdown files inside.

**Solution**: Ensure source_folder points to parent of `.specstory` folders:
```yaml
databases:
  specstory:
    source_folder: /home/gyasisutton/dev/jira-issues  # Parent of TIC-1234/.specstory, TIC-5678/.specstory, etc.
```

Not:
```yaml
source_folder: /home/gyasisutton/dev/jira-issues/TIC-1234/.specstory  # Too specific
```

---

### 7. PostgreSQL Port 5433 (Not 5432)

**Quirk**: HybridRAG uses PostgreSQL on port 5433, not standard 5432

**Why**: Avoid conflicts with other PostgreSQL instances on the machine.

**Solution**: Always specify port in connection strings:
```yaml
backend_config:
  postgres_host: localhost
  postgres_port: 5433  # NOT 5432
```

---

### 8. uv vs pip

**Quirk**: Project uses `uv` package manager, not standard `pip`

**Why**: uv is faster (Rust-based), handles virtual envs automatically.

**Commands**:
```bash
# Install dependencies
uv sync  # NOT: pip install -r requirements.txt

# Run script
uv run python hybridrag.py  # NOT: python hybridrag.py

# Add dependency
uv add <package>  # NOT: pip install <package>
```

However, `pip install -e .` works fine for editable installs.

---

## Debugging Strategies

### 1. MCP Tool Not Returning Results

**Symptoms**:
- "I can't find any results"
- Empty response
- No backend metadata

**Debug steps**:
1. Check backend metadata appears: `hybridrag --db X --show-backend status`
2. Verify database has data: `hybridrag --db X db show X --stats`
3. Test query directly via CLI: `hybridrag --db X query --text "test"`
4. Check MCP logs: `hybridrag_get_logs(limit=20)` in Claude Desktop
5. Verify model/API keys: `echo $AZURE_API_KEY`, `echo $DEPLOYMENT_MODEL`

---

### 2. Watcher Not Ingesting Files

**Symptoms**:
- File count not increasing
- New files not appearing in queries

**Debug steps**:
1. Check watcher is running: `hybridrag db watch status`
2. Verify source_folder is correct: `hybridrag db show specstory`
3. Check last run timestamp: `cat lightrag_db/.last_specstory_watch`
4. Look for errors in logs: `tail -f logs/hybridrag.log`
5. Manually trigger ingestion: `hybridrag --db specstory ingest --folder <path>`

---

### 3. Registry Resolution Failing

**Symptoms**:
- "Database not found: specstory"
- Wrong backend being used

**Debug steps**:
1. Check registry exists: `cat ~/.hybridrag/registry.yaml`
2. List databases: `hybridrag db list`
3. Show specific database: `hybridrag db show specstory`
4. Verify path matches: `ls /home/gyasisutton/dev/tools/RAG/hybridrag/lightrag_db`
5. Check permissions: `ls -l ~/.hybridrag/registry.yaml`

---

### 4. Query Performance Issues

**Symptoms**:
- Queries taking >60s
- MCP timeouts in Claude Desktop

**Debug steps**:
1. Check database size: `hybridrag --db X db show X --stats`
2. Verify PostgreSQL indexes: `psql -h localhost -p 5433 -U hybridrag -d hybridrag -c "\d+"`
3. Use faster query mode: Try `local` instead of `hybrid` or `multihop`
4. Reduce top_k: Try `top_k=5` instead of `top_k=20`
5. Check backend load: `htop` or `docker stats` for PostgreSQL container

---

### 5. Credential Masking Not Working

**Symptoms**:
- Passwords visible in logs or MCP responses
- Security concern

**Debug steps**:
1. Verify using `mask_credentials()`: grep for `urlparse` in code
2. Check environment variable values: `env | grep POSTGRES_PASSWORD`
3. Test masking directly:
```python
from src.utils.backend_utils import mask_credentials
print(mask_credentials("postgresql://user:secret@localhost:5433/db"))
# Should output: postgresql://user:****@localhost:5433/db
```
4. Ensure backend metadata uses masking:
```python
# In get_backend_metadata_line():
conn_str = mask_credentials(f"postgresql://{user}:{password}@{host}:{port}/{db}")
```

---

## Common Mistakes to Avoid

### 1. Forgetting to Append Backend Metadata

**Mistake**:
```python
@mcp.tool()
def my_tool(query: str) -> str:
    result = do_query(query)
    return result  # WRONG: No backend metadata
```

**Correct**:
```python
@mcp.tool()
def my_tool(query: str) -> str:
    result = do_query(query)
    backend_metadata = get_backend_metadata_line()
    return f"{result}{backend_metadata}"  # RIGHT
```

---

### 2. Using Regex for Credential Masking

**Mistake**:
```python
import re
masked = re.sub(r'://(.*?):(.*?)@', r'://\1:****@', conn_str)  # FRAGILE
```

**Correct**:
```python
from src.utils.backend_utils import mask_credentials
masked = mask_credentials(conn_str)  # ROBUST
```

---

### 3. Hardcoding Database Paths

**Mistake**:
```python
rag = HybridLightRAGCore(working_dir="./lightrag_db")  # WRONG: Hardcoded
```

**Correct**:
```python
db_entry = resolve_database(args.db)
rag = HybridLightRAGCore(working_dir=db_entry.path)  # RIGHT: Registry-sourced
```

---

### 4. Not Using task=True for Long Queries

**Mistake**:
```python
@mcp.tool()  # WRONG: Multihop can take 15 minutes
async def hybridrag_multihop_query(query: str) -> str:
    # Long-running query...
    pass
```

**Correct**:
```python
@mcp.tool(task=True)  # RIGHT: Enables background task
async def hybridrag_multihop_query(ctx: Context, query: str) -> str:
    # Long-running query...
    pass
```

---

### 5. Mixing Model Override Sources

**Mistake**:
Setting `DEPLOYMENT_MODEL` env var AND CLI `--model` flag AND registry `model_config`, then being confused about which model is used.

**Correct**:
Pick one override method. If confused, check precedence:
```
CLI --model > model_config.yaml > registry > env > default
```

Or use diagnostic:
```bash
hybridrag --db specstory --show-backend status
```

---

## Performance Optimization Tips

### 1. Use Local Queries for Specific Entities
**Why**: Local mode is faster than hybrid (2-10s vs 10-60s)

**Example**:
```bash
# Fast (2-5s):
hybridrag --db specstory query --text "TIC-4376" --mode local

# Slower (10-30s):
hybridrag --db specstory query --text "TIC-4376" --mode hybrid
```

---

### 2. Reduce top_k for Faster Results
**Why**: Processing 20 results takes longer than 5

**Example**:
```python
# Slower:
hybridrag_hybrid_query(query="test", top_k=20)

# Faster:
hybridrag_hybrid_query(query="test", top_k=5)
```

---

### 3. Use extract_context Instead of Full Query
**Why**: Skips LLM generation, just returns raw context

**Example**:
```bash
# Full query with LLM synthesis (slow):
hybridrag --db specstory query --text "test"

# Just context extraction (fast):
hybridrag_extract_context(query="test", top_k=5)
```

---

### 4. Index PostgreSQL Tables
**Why**: Vector similarity search is slow without indexes

**Check indexes**:
```sql
psql -h localhost -p 5433 -U hybridrag -d hybridrag -c "\d+ entities"
```

**Add index if missing**:
```sql
CREATE INDEX idx_entity_embedding ON entities USING ivfflat (embedding vector_cosine_ops);
```

---

### 5. Monitor watcher resource usage
**Why**: Large directory trees can consume lots of memory

**Monitor**:
```bash
ps aux | grep hybridrag
htop -p <pid>
```

**Optimize**:
- Reduce `watch_interval` (less frequent checks)
- Use more specific `source_folder` (fewer files to monitor)
- Enable `recursive=false` if flat structure

---

## Integration Patterns

### Claude Desktop Integration
**Location**: `~/.claude_desktop/config.json`

**Pattern**: One MCP server per database
```json
{
  "mcpServers": {
    "hybridrag-specstory": {
      "command": "uv",
      "args": [
        "--directory", "/home/gyasisutton/dev/tools/RAG/hybridrag",
        "run", "python", "-m", "hybridrag_mcp"
      ],
      "env": {
        "HYBRIDRAG_DATABASE": "/home/gyasisutton/dev/tools/RAG/hybridrag/lightrag_db"
      }
    }
  }
}
```

**Restart Claude Desktop** after changing config.

---

### Systemd Integration (Linux)
**Location**: `~/.config/systemd/user/hybridrag-watcher@.service`

**Pattern**: Template service for any database
```ini
[Unit]
Description=HybridRAG File Watcher for %i
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/uv --directory /home/gyasisutton/dev/tools/RAG/hybridrag run python hybridrag.py --db %i db watch start
Restart=always

[Install]
WantedBy=default.target
```

**Usage**:
```bash
systemctl --user enable --now hybridrag-watcher@specstory.service
systemctl --user status hybridrag-watcher@specstory.service
```

---

## Best Practices

1. **Always use registry for multi-database setups**: Eliminates env var hell
2. **Always append backend metadata to MCP responses**: Transparency is key
3. **Always use urllib.parse for credential masking**: Robust against edge cases
4. **Always use task=True for queries >10s**: Prevents MCP timeouts
5. **Always test MCP tools with real data**: Integration tests catch issues
6. **Always update CLAUDE.md when discovering patterns**: Future you will thank you
7. **Always commit with co-author tag**: `Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>`
