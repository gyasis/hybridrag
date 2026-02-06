# HybridRAG Technical Context

## Technology Stack

### Core Runtime
- **Python**: 3.10+ (3.12 in active use)
- **Package Manager**: uv (fast, Rust-based pip alternative)
- **Async Framework**: asyncio + asyncpg for PostgreSQL

### Key Dependencies

#### LightRAG & RAG Core
```toml
lightrag-hku = ">=0.1.0"  # Knowledge graph construction
deeplake = ">=4.0.0"      # Vector storage (legacy, not actively used)
```

#### LLM Integration
```toml
litellm = ">=1.0.0"       # Unified interface: Azure, OpenAI, Anthropic, Gemini, Ollama
openai = ">=1.0.0"        # OpenAI API client
tiktoken = ">=0.5.0"      # Token counting
```

#### MCP Server
```toml
fastmcp = ">=2.14.2"      # Model Context Protocol server for Claude Desktop
```

#### Database & Storage
```toml
asyncpg = ">=0.31.0"      # PostgreSQL async driver
pyyaml = ">=6.0.0"        # Registry file parsing
```

#### Document Processing
```toml
pypdf = ">=4.0.0"         # PDF reading
beautifulsoup4 = ">=4.12.0"  # HTML parsing
```

#### Monitoring & TUI
```toml
textual = ">=0.40.0"      # Terminal UI framework
psutil = ">=5.9.0"        # System resource monitoring
tqdm = ">=4.65.0"         # Progress bars
```

#### Development Tools
```toml
pytest = ">=7.0.0"        # Testing
pytest-asyncio = ">=0.21.0"  # Async test support
black = ">=23.0.0"        # Code formatting
ruff = "Latest"           # Linting (fast, Rust-based)
```

### Custom Dependencies
```toml
promptchain = { git = "https://github.com/gyasis/PromptChain.git", branch = "main" }
```
Used for multi-hop agentic search (multihop_query tool).

---

## Backend Infrastructure

### PostgreSQL (Primary Backend)

#### Container Setup
- **Image**: Apache AGE with pgvector
- **Port**: 5433 (non-standard to avoid conflicts)
- **Database**: `hybridrag`
- **User**: `hybridrag`
- **Password**: `hybridrag_secure_2026`

#### Extensions
- **pgvector**: Vector similarity search (embedding storage)
- **Apache AGE**: Graph database capabilities (entities + relationships)

#### Connection String
```
postgresql://hybridrag:****@localhost:5433/hybridrag
```

#### Schema Overview
```sql
-- Entities table (AGE graph nodes)
-- Stores extracted entities (Person, Organization, Concept, etc.)

-- Relationships table (AGE graph edges)
-- Stores relationships between entities

-- Chunks table
-- Stores document chunks with embeddings

-- Documents table (metadata)
-- Tracks source files and ingestion status
```

#### Current Scale
- **Total Rows**: 31K+
- **Entities**: 7K+
- **Relationships**: 7K+
- **Chunks**: ~7K
- **Source Documents**: 27 SpecStory projects

### JSON Backend (Fallback)
- **Storage**: Filesystem-based JSON files
- **Location**: `{working_dir}/graph_data.json`
- **Use Case**: Development, small datasets, no DB setup needed

### Other Supported Backends
Not actively used but supported:
- MongoDB, Neo4j, Milvus, Qdrant, Faiss, Redis, Memgraph

---

## Key File Paths

### Entry Points
```
/home/gyasisutton/dev/tools/RAG/hybridrag/
├── hybridrag.py                  # Main CLI entry point
├── hybridrag_mcp/
│   ├── __main__.py               # MCP server entry (python -m hybridrag_mcp)
│   └── server.py                 # MCP tool implementations
```

### Configuration
```
~/.hybridrag/
├── registry.yaml                 # Database registry (SINGLE SOURCE OF TRUTH)
└── config_pointer                # Optional: custom registry location

/home/gyasisutton/dev/tools/RAG/hybridrag/
├── .env                          # Environment variables (API keys)
├── pyproject.toml                # Project metadata, dependencies
├── src/config/
│   ├── app_config.py             # Application settings
│   └── backend_config.py         # Backend connection configs
```

### Core Source Code
```
src/
├── config/
│   ├── app_config.py             # HybridRAGConfig, LightRAGConfig, IngestionConfig, SearchConfig
│   └── backend_config.py         # BackendType enum, BackendConfig
├── lightrag_core.py              # LightRAG interface wrapper
├── database_registry.py          # Registry CRUD operations
├── database_metadata.py          # Database stats and metadata
├── ingestion/
│   ├── file_watcher.py           # Folder monitoring
│   ├── document_processor.py    # Multi-format parsing
│   └── migrations.py             # Schema migrations
├── batch_ingestion_controller.py # Batch processing coordination
├── health_check.py               # System health monitoring
└── utils/
    └── backend_utils.py          # Credential masking, backend helpers
```

### Database & State
```
/home/gyasisutton/dev/tools/RAG/hybridrag/
├── lightrag_db/                  # LightRAG working directory
│   ├── .last_specstory_watch     # Delta ingestion timestamp
│   └── <backend-specific files>
├── ingestion_queue/              # Processing queue
│   ├── pending/
│   └── errors/
└── .memory/
    ├── session.json              # Session state (survives 2-3 sessions)
    ├── .pre-compact-discoveries.json
    └── .post-compact-flag.json
```

### Runtime State
```
/run/user/1000/
└── hybridrag_watcher_specstory.pid  # Watcher PID file
```

### Logs
```
/tmp/hybridrag_mcp_logs/          # MCP diagnostic logs (temp, cleared on restart)
/home/gyasisutton/dev/tools/RAG/hybridrag/logs/  # Application logs (rotated)
```

---

## Model Configuration

### LLM Models (via LiteLLM)

#### Primary Model
```yaml
llm_model: azure/gpt-5.1
```
Used for query generation and response synthesis.

#### Embedding Model
```yaml
embedding_model: azure/text-embedding-3-small
embedding_dim: 1536
```
Used for chunk vectorization.

#### Model Override Chain
```
1. CLI --model flag (highest)
2. model_config.yaml file
3. registry.yaml db_entry.model_config.llm_model
4. DEPLOYMENT_MODEL env var
5. gpt-4o-mini (default fallback)
```

#### Provider Support
- **Azure**: `azure/gpt-5.1`, `azure/gpt-4o`, etc.
- **OpenAI**: `openai/gpt-4o`, `gpt-4o` (bare names default to OpenAI)
- **Anthropic**: `anthropic/claude-opus`, `anthropic/claude-sonnet`
- **Gemini**: `gemini/gemini-pro`, `google/gemini-pro`
- **Ollama**: `ollama/llama3` (local, no API key)

#### API Keys
Set in `.env`:
```bash
AZURE_API_KEY=...
AZURE_API_BASE=...
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
GEMINI_API_KEY=...
```

---

## Installation & Setup

### Initial Installation
```bash
# Clone repo
git clone <repo> hybridrag
cd hybridrag

# Install with uv (recommended)
uv sync

# Or with pip
pip install -e .

# Verify installation
hybridrag --version
```

### Environment Setup
```bash
# Copy example env file
cp .env.example .env

# Edit with your API keys
nano .env

# Test configuration
hybridrag --db specstory --show-backend status
```

### PostgreSQL Backend Setup
```bash
# Start Apache AGE + pgvector container
docker run -d \
  --name hybridrag-postgres \
  -e POSTGRES_USER=hybridrag \
  -e POSTGRES_PASSWORD=hybridrag_secure_2026 \
  -e POSTGRES_DB=hybridrag \
  -p 5433:5432 \
  apache/age:latest

# Run migrations (if needed)
python -m src.ingestion.migrations
```

### Registry Setup
```bash
# Register a new database
hybridrag db register specstory \
  --path ~/databases/specstory_db \
  --source ~/dev/jira-issues \
  --type specstory \
  --auto-watch \
  --interval 300 \
  --model azure/gpt-5.1

# Verify registry
hybridrag db list
```

---

## Development Environment

### Python Version
```bash
python --version
# Python 3.12.x
```

### Virtual Environment
Using uv (creates `.venv` automatically):
```bash
uv sync  # Install dependencies + create venv
uv run hybridrag --version  # Run within venv
```

Or traditional venv:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Code Quality Tools

#### Linting with Ruff
```bash
ruff check src/ hybridrag_mcp/
ruff check --fix src/  # Auto-fix issues
```

#### Formatting with Black
```bash
black src/ hybridrag_mcp/
```

#### Type Checking with mypy
```bash
mypy src/ hybridrag_mcp/
```

#### Testing with pytest
```bash
pytest tests/
pytest tests/ -v  # Verbose
pytest tests/test_hybridrag.py::test_all_mcp_tools  # Specific test
```

---

## Constraints & Limitations

### Technical Constraints

#### 1. Filesystem Dependencies
- Delta ingestion relies on file modification times (mtimes)
- If files are touched/reset, may reingest unnecessarily
- Solution: Manual timestamp reset if needed

#### 2. Model Context Limits
- LightRAG chunks limited by model context window
- Chunk size: 1200 tokens, overlap: 100 tokens
- Trade-off: smaller chunks = more granular but more queries

#### 3. Embedding Dimensionality
- Azure text-embedding-3-small: 1536 dimensions
- Different embedding models require schema migration
- Can't mix embedding models in same database

#### 4. PostgreSQL Connection Limits
- Default max connections: 100
- Watch watchers with many concurrent queries
- Solution: Connection pooling if needed

### Operational Constraints

#### 1. Watcher Resource Usage
- Watching large directory trees can be memory-intensive
- Currently watching `/home/gyasisutton/dev` (27 projects)
- Monitor with `ps aux | grep hybridrag`

#### 2. Ingestion Rate Limits
- LLM API rate limits (varies by provider)
- Azure: ~3500 TPM (tokens per minute) on gpt-5.1
- Built-in retry with exponential backoff

#### 3. Query Timeouts
- Multihop queries can take 60-900 seconds
- Strategic queries (hybrid/global): 10-60 seconds
- MCP tools use background tasks to avoid Claude timeouts

### Security Constraints

#### 1. Credential Storage
- API keys in `.env` file (not committed to git)
- Credentials masked in logs and MCP responses
- PostgreSQL password stored in registry (file permissions: 600)

#### 2. Registry Security
- `~/.hybridrag/registry.yaml` contains connection strings
- Recommended: `chmod 600 ~/.hybridrag/registry.yaml`

---

## Performance Characteristics

### Query Performance (Approximate)

| Query Type | Latency | Tokens | Backend Load |
|------------|---------|--------|--------------|
| database_status | <1s | ~500 | Read-only |
| local_query | 2-10s | 2K-5K | Vector search + LLM |
| extract_context | 1-5s | 1K-3K | Vector search only |
| global_query | 10-30s | 5K-10K | Community detection + LLM |
| hybrid_query | 10-60s | 5K-15K | Local + Global + LLM |
| multihop_query | 60-900s | 10K-50K | Recursive queries + reasoning |

### Ingestion Performance

- **Single file**: 1-5 seconds (depends on file size, chunking)
- **Batch (10 files)**: 10-60 seconds (parallelized)
- **Full project (1000 files)**: 30-60 minutes (with rate limiting)

### Database Growth

- **1K documents** → ~3K entities, ~3K relationships, ~10K chunks
- **10K documents** → ~30K entities, ~30K relationships, ~100K chunks
- PostgreSQL handles 100K+ rows efficiently with proper indexing

---

## Monitoring & Observability

### Health Check
```bash
hybridrag --db specstory health_check
```

Returns:
- LightRAG status
- Backend connectivity
- Model availability
- System resources

### Database Stats
```bash
hybridrag --db specstory db show specstory --stats
```

Returns:
- Entity count
- Relationship count
- Chunk count
- Last sync time
- Backend type and config

### Watcher Status
```bash
hybridrag db watch status
```

Returns:
- Active watchers
- PIDs
- Database names
- Source folders

### MCP Diagnostic Logs
From Claude Desktop (via MCP tool):
```
hybridrag_get_logs(limit=20)
```

Returns last 20 MCP tool calls with:
- Tool name
- Parameters
- Response summary
- Timestamp
- Backend used

---

## Deployment Patterns

### Local Development
```bash
# Use JSON backend (no PostgreSQL needed)
export BACKEND_TYPE=json
hybridrag ingest --folder ./test_data
hybridrag query --text "test query"
```

### Production (Single Machine)
```bash
# PostgreSQL backend with systemd watcher
hybridrag db register prod_db --auto-watch
hybridrag db watch start prod_db --systemd
```

### Production (Multi-Machine)
- PostgreSQL on dedicated server
- Multiple HybridRAG instances point to same DB
- Load balancing via HAProxy/nginx (if needed)
- Shared registry file (NFS or S3)

### Claude Desktop Integration
Add to `~/.claude_desktop/config.json`:
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

Restart Claude Desktop to load server.

---

## Future Technical Considerations

### Scalability
- **Sharding**: Split large databases by project or date range
- **Caching**: Redis cache for frequent queries
- **Read replicas**: PostgreSQL read replicas for query load balancing

### Advanced Features
- **Incremental embeddings**: Only re-embed changed chunks
- **Streaming responses**: Stream MCP tool responses for long queries
- **Query optimization**: Cache query plans, precompute common searches

### Integration Opportunities
- **Git hooks**: Auto-ingest on commit
- **CI/CD**: Ingest test results, logs, deployment notes
- **Slack/Discord**: Real-time conversation ingestion
- **Notion/Confluence**: Documentation sync
