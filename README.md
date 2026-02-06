# HybridRAG System

A comprehensive knowledge graph-based retrieval system that combines folder watching, document ingestion, and intelligent search capabilities using LightRAG and PromptChain.

## 🚀 Features

### 📁 Intelligent Folder Monitoring
- **Recursive watching** of multiple directories
- **Real-time detection** of new and modified files
- **Smart filtering** by file extensions and size limits
- **Deduplication** using SHA256 hashing
- **SQLite tracking** of processed files

### ⚡ Advanced Document Processing
- **Multi-format support**: TXT, MD, PDF, HTML, JSON, YAML, CSV, code files
- **Intelligent chunking** with token-aware splitting
- **PDF OCR capabilities** (optional)
- **Metadata preservation** throughout pipeline
- **Batch processing** with configurable concurrency

### 🧠 Sophisticated Search Interface
- **Multi-mode queries**: Local, Global, Hybrid, Agentic
- **Simple search**: Direct LightRAG queries
- **Agentic search**: Multi-hop reasoning using PromptChain
- **Multi-query synthesis**: Combine multiple searches
- **Interactive CLI** with command history

### 🔄 Production-Ready Architecture
- **Async/await** throughout for performance
- **Graceful error handling** and recovery
- **Comprehensive logging** with rotation
- **Health monitoring** and statistics
- **Signal handling** for clean shutdown

## 📋 Prerequisites

- Python 3.10+ (3.12 recommended)
- [uv](https://docs.astral.sh/uv/) package manager (recommended) or pip
- Azure API key (preferred) or OpenAI API key
- Docker (for PostgreSQL backend)
- Optional: Other LLM provider keys (Anthropic, Gemini) for alternative models

## 🛠️ Installation

1. **Clone the repository**:
```bash
git clone <repo-url> hybridrag && cd hybridrag
```

2. **Install with uv (recommended)**:
```bash
uv sync                    # Creates .venv + installs all deps
uv pip install -e .        # Install CLI entry point
```

Or with pip:
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .           # Installs all deps + CLI
```

3. **Verify CLI**:
```bash
hybridrag --help           # Should show all commands
```

4. **Setup environment**:
```bash
cp .env.example .env
# Edit .env and add your API keys
```

5. **Setup PostgreSQL backend** (recommended for production):
```bash
docker run -d \
  --name hybridrag-postgres \
  -e POSTGRES_USER=hybridrag \
  -e POSTGRES_PASSWORD=hybridrag_secure_2026 \
  -e POSTGRES_DB=hybridrag \
  -p 5433:5432 \
  apache/age:latest
```
> **Note**: Uses port 5433 (not 5432) to avoid conflicts with existing PostgreSQL instances. The `apache/age` image includes pgvector for embeddings and Apache AGE for graph queries.

## 🎯 Quick Start

### 1. First-Time Setup
```bash
# Register a database (PostgreSQL backend)
hybridrag db register mydb \
  --path ./lightrag_db \
  --source ~/data \
  --type filesystem \
  --auto-watch

# Ingest data
hybridrag --db mydb ingest --folder ./data

# Check database status
hybridrag --db mydb status
```

### 2. Query Your Data
```bash
# Interactive mode (recommended)
hybridrag --db mydb interactive

# One-shot query
hybridrag --db mydb query --text "Find appointment tables" --mode hybrid

# Advanced query with multi-hop reasoning
hybridrag --db mydb query --text "..." --multihop --verbose
```

### 3. Manage Your System
```bash
# Check status
hybridrag --db mydb status

# Database info
hybridrag --db mydb check-db

# Start watcher (auto-ingest new files)
hybridrag --db mydb db watch start
```

## 📖 Comprehensive Usage

See [USAGE.md](docs/guides/USAGE.md) for complete documentation including:
- All available commands and flags
- Query mode explanations (local/global/hybrid/naive/mix)
- Database management
- Advanced features
- Troubleshooting guide

### Common Commands

```bash
# Ingestion
hybridrag --db mydb ingest --folder ./data
hybridrag --db mydb ingest --folder ./data --db-action fresh  # Start fresh
hybridrag --db mydb ingest --folder ./data --db-action add    # Add to existing

# Ingestion with metadata and scripting flags
hybridrag --db mydb ingest --folder ./data --metadata "project=myproject" --yes --quiet

# Queries
hybridrag --db mydb interactive                               # Interactive CLI
hybridrag --db mydb query --text "..." --mode hybrid         # One-shot query
hybridrag --db mydb query --text "..." --multihop            # Multi-hop reasoning

# Management
hybridrag --db mydb status                                    # System status
hybridrag --db mydb check-db                                  # Database info
hybridrag db list                                             # List all databases
hybridrag --help                                              # Show help
```

## 📚 Database Registry

HybridRAG includes a centralized database registry for managing multiple knowledge bases. The registry stores database configurations in `~/.hybridrag/registry.yaml` and provides:

- **Named database references** - Use `--db mydb` instead of `--working-dir /path/to/db`
- **Source folder tracking** - Remember where data came from
- **Auto-watch configuration** - Automatic file monitoring per database
- **Model configuration** - Per-database model overrides

### Registry Commands

```bash
# Register a new database
hybridrag db register specstory \
    --path ~/databases/specstory_db \
    --source ~/dev \
    --type specstory \
    --auto-watch \
    --interval 300 \
    --model azure/gpt-5.1

# List all registered databases
hybridrag db list
hybridrag db list --json

# Show database details
hybridrag db show specstory

# Update database settings
hybridrag db update specstory --auto-watch false --interval 600

# Remove from registry (doesn't delete files)
hybridrag db unregister specstory

# Force sync/re-ingest from source folder
hybridrag db sync specstory
hybridrag db sync specstory --fresh  # Start fresh
```

### Using Named Databases

Once registered, reference databases by name with `--db`. The registry auto-resolves backend configuration (PostgreSQL, JSON, etc.) from `~/.hybridrag/registry.yaml`:

```bash
# Query using database name (backend auto-resolved)
hybridrag --db specstory query --text "TIC-4376 progress"

# Ingest additional data
hybridrag --db specstory ingest --folder ~/more-data

# Check status (shows backend type)
hybridrag --db specstory status
```

### File Watching

HybridRAG can automatically watch source folders and ingest new/changed files:

```bash
# Start watcher for a database
hybridrag --db specstory db watch start

# Start watchers for ALL auto-watch databases
hybridrag db watch start --all

# Stop watcher
hybridrag --db specstory db watch stop
hybridrag db watch stop --all

# Check watcher status
hybridrag db watch status
```

#### Systemd Integration (Linux)

For persistent watchers that survive reboots:

```bash
# Start with systemd (creates user service)
hybridrag --db specstory db watch start --systemd

# Or manually install the template unit
cp scripts/hybridrag-watcher@.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now hybridrag-watcher@specstory.service
```

### Database Types

The registry supports different source types with type-specific configurations:

| Type | Description | Config Options |
|------|-------------|----------------|
| `filesystem` | General files and folders | `extensions`, `recursive` |
| `specstory` | SpecStory JIRA folders | `jira_project_key`, `folder_pattern` |
| `api` | API data sources | `api_url`, `auth_method` |
| `schema` | Database schema docs | `connection_string`, `tables` |

Example SpecStory registration:
```bash
hybridrag db register specstory \
    --path ~/databases/specstory_db \
    --source ~/dev \
    --type specstory \
    --auto-watch
```

### Registry Location

Default: `~/.hybridrag/registry.yaml`

Override with:
```bash
# Environment variable
export HYBRIDRAG_CONFIG=/path/to/registry.yaml

# Or pointer file
echo "/path/to/registry.yaml" > ~/.hybridrag/config_pointer
```

### Ingestion Flags

| Flag | Description |
|------|-------------|
| `--folder PATH` | Folder(s) to ingest (can specify multiple) |
| `--db-action {use,add,fresh}` | Database action: use existing, add to existing, or start fresh |
| `--metadata KEY=VALUE` | Add metadata (can specify multiple, e.g., `--metadata project=foo --metadata version=1`) |
| `--yes`, `-y` | Skip confirmation prompts (for scripted use) |
| `--quiet`, `-q` | Suppress verbose output, show only progress bar |
| `--recursive` | Watch folders recursively (default: true) |
| `--multiprocess` | Use multiprocess architecture |

### Multi-Project Ingestion Scripts

For ingesting multiple `.specstory` folders at once:

```bash
# Ingest all .specstory folders into a SINGLE database (recommended)
./scripts/ingest_specstory_folders.sh /path/to/jira-issues fresh

# Ingest each project into SEPARATE databases
./scripts/ingest_separate_databases.sh /path/to/projects

# Watch for changes and auto-ingest
./scripts/watch_specstory_folders.sh /path/to/jira-issues

# Use specific model (e.g., Gemini)
./scripts/ingest_specstory_folders.sh /path/to/projects fresh gemini/gemini-pro
./scripts/watch_specstory_folders.sh /path/to/projects 300 anthropic/claude-opus
```

Features:
- **Progress bar**: tqdm-based progress during ingestion
- **Restartable**: Queue-based architecture - files stay queued until processed
- **Metadata tagging**: Each project tagged with `project=NAME` and `source_path`
- **Error tracking**: Failed files moved to `ingestion_queue/errors/`

## ⚙️ Configuration

The system uses a hierarchical configuration split across two files:
- `src/config/app_config.py` — Application settings (LightRAG, ingestion, search)
- `src/config/backend_config.py` — Backend connection settings (PostgreSQL, JSON, etc.)

### LightRAG Configuration
```python
@dataclass
class LightRAGConfig:
    working_dir: str = "./lightrag_db"
    model_name: str = "azure/gpt-5.1"           # Default: Azure GPT-5.1
    embedding_model: str = "azure/text-embedding-3-small"
    chunk_size: int = 1200
    chunk_overlap: int = 100
```

**Model Override**: You can override models at runtime:
```bash
# Use Gemini instead of Azure
hybridrag --model gemini/gemini-pro --db mydb ingest --folder ./data

# Use Anthropic Claude
hybridrag --model anthropic/claude-opus --db mydb query --text "your query"

# Set via environment variable
export DEPLOYMENT_MODEL="openai/gpt-4o"
hybridrag --db mydb interactive
```

**Model Precedence Chain** (highest to lowest):
1. CLI `--model` flag
2. `model_config.yaml` file
3. Registry `model_config.llm_model`
4. `DEPLOYMENT_MODEL` env var
5. `gpt-4o-mini` (default fallback)

### Ingestion Configuration
```python
@dataclass
class IngestionConfig:
    watch_folders: List[str] = ["./data"]
    file_extensions: List[str] = [".txt", ".md", ".pdf", ".json", ...]
    recursive: bool = True
    batch_size: int = 10
    max_file_size_mb: float = 50.0
```

### Search Configuration
```python
@dataclass
class SearchConfig:
    default_mode: str = "hybrid"
    default_top_k: int = 10
    enable_reranking: bool = True
    enable_context_accumulation: bool = True
```

## 📊 Query Modes

HybridRAG supports six query modes for different retrieval needs:

| Mode | Type | Best For |
|------|------|----------|
| `local` | Native LightRAG | Specific entities, relationships |
| `global` | Native LightRAG | Overviews, summaries, patterns |
| `hybrid` | Native LightRAG | Balanced queries (default) |
| `naive` | Native LightRAG | Simple vector similarity |
| `mix` | Native LightRAG | Comprehensive coverage |
| `multihop` | PromptChain | Complex analysis, comparisons |

### Quick Examples

```bash
# Native LightRAG modes
hybridrag --db mydb query --text "APPOINTMENT table" --mode local
hybridrag --db mydb query --text "billing overview" --mode global
hybridrag --db mydb query --text "patient flow" --mode hybrid

# Multi-hop reasoning (uses LightRAG as tools)
hybridrag --db mydb query --text "Compare registration and billing workflows" --multihop
hybridrag --db mydb query --text "Trace patient data flow" --multihop --verbose
```

### Interactive Mode

```bash
hybridrag --db mydb interactive

> :local                  # Switch to local mode
> :multihop               # Enable multi-hop reasoning
> :verbose                # Show reasoning steps
> Compare appointment and billing workflows
```

**See [docs/QUERY_MODES.md](docs/QUERY_MODES.md) for comprehensive mode documentation.**

## 🔧 Advanced Features

### Custom Document Processing
Extend the `DocumentProcessor` class to handle additional file types:

```python
class CustomDocumentProcessor(DocumentProcessor):
    def read_file(self, file_path: str, extension: str) -> str:
        if extension == '.custom':
            return self._read_custom_format(file_path)
        return super().read_file(file_path, extension)
```

### Custom Search Tools
Add domain-specific tools for agentic search:

```python
def custom_search_tool(query: str) -> str:
    # Your custom search logic
    return results

# Register with search interface
search_interface.register_tool(custom_search_tool)
```

### Monitoring and Metrics
The system provides comprehensive monitoring:

```python
# Get detailed statistics
stats = await system.get_system_status()

# Monitor ingestion progress
watcher_stats = folder_watcher.get_queue_stats()
ingestion_stats = ingestion_pipeline.get_stats()

# Track search performance
search_stats = search_interface.get_stats()
```

## 🔌 MCP Server (Claude Desktop Integration)

HybridRAG includes a Model Context Protocol (MCP) server for seamless integration with Claude Desktop. This allows Claude to directly query your knowledge bases.

### Quick Setup

1. **Find your Claude config**:
   - Claude Desktop: `~/.claude_desktop/config.json`
   - Claude Code: `~/.claude/settings.json` (mcpServers section)

2. **Add HybridRAG server**:
```json
{
  "mcpServers": {
    "hybridrag-specstory": {
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
        "HYBRIDRAG_DATABASE": "/path/to/lightrag_db",
        "AZURE_API_KEY": "${AZURE_API_KEY}",
        "AZURE_API_BASE": "${AZURE_API_BASE}"
      }
    }
  }
}
```

3. **Restart Claude** to load the new server

The MCP server auto-resolves the backend from `~/.hybridrag/registry.yaml`. Every tool response includes backend metadata confirming which database and backend is active (e.g., `Backend: postgres (localhost:5433/hybridrag)`).

### Multiple Instances

Run multiple HybridRAG instances for different knowledge bases:

```json
{
  "mcpServers": {
    "hybridrag-specstory": {
      "command": "uv",
      "args": ["--directory", "/path/to/hybridrag", "run", "python", "-m", "hybridrag_mcp"],
      "env": {
        "HYBRIDRAG_DATABASE": "/path/to/specstory_lightrag_db",
        "AZURE_API_KEY": "${AZURE_API_KEY}",
        "AZURE_API_BASE": "${AZURE_API_BASE}"
      }
    },
    "hybridrag-code": {
      "command": "uv",
      "args": ["--directory", "/path/to/hybridrag", "run", "python", "-m", "hybridrag_mcp"],
      "env": {
        "HYBRIDRAG_DATABASE": "/path/to/code_lightrag_db",
        "HYBRIDRAG_MODEL": "azure/gpt-4o"
      }
    }
  }
}
```

### Available MCP Tools

| Tool | Description |
|------|-------------|
| `hybridrag_query` | Main query with mode selection (local/global/hybrid/naive/mix) |
| `hybridrag_local_query` | Entity-focused retrieval for specific entities |
| `hybridrag_global_query` | Community-based summaries and overviews |
| `hybridrag_hybrid_query` | Combined local + global (recommended default) |
| `hybridrag_multihop_query` | Multi-hop reasoning for complex analysis |
| `hybridrag_extract_context` | Raw context extraction without LLM generation |
| `hybridrag_database_status` | Get database stats and configuration |
| `hybridrag_health_check` | Verify system health |

### Environment Variables

| Variable | Description |
|----------|-------------|
| `HYBRIDRAG_DATABASE` | **Required.** Path to the LightRAG database directory |
| `HYBRIDRAG_MODEL` | Optional LLM model override (e.g., `azure/gpt-4o`) |
| `HYBRIDRAG_EMBED_MODEL` | Optional embedding model override |

### Example Config

See `hybridrag_mcp/claude_desktop_config.example.json` for a complete multi-instance example.

## 📁 Project Structure

```
hybridrag/
├── hybridrag.py              # Main CLI entry point (installed as `hybridrag` command)
├── pyproject.toml            # Dependencies, build config, CLI entry point
├── .env                      # API keys (not committed)
├── .env.example              # Environment template
├── hybridrag_mcp/            # MCP server for Claude Desktop/Code
│   ├── __init__.py           # Module metadata
│   ├── __main__.py           # Entry point for python -m
│   ├── server.py             # 8 MCP tools with backend metadata
│   └── claude_desktop_config.example.json
├── src/                      # Core system components
│   ├── config/
│   │   ├── app_config.py      # HybridRAGConfig, LightRAGConfig, IngestionConfig
│   │   ├── backend_config.py  # BackendType enum, BackendConfig
│   │   └── __init__.py        # Re-exports from both config modules
│   ├── database_registry.py   # Registry CRUD (~/.hybridrag/registry.yaml)
│   ├── lightrag_core.py       # LightRAG interface wrapper
│   ├── ingestion/
│   │   ├── file_watcher.py    # Folder monitoring
│   │   └── document_processor.py  # Multi-format parsing
│   ├── search_interface.py    # Search functionality
│   └── health_check.py        # System health monitoring
├── scripts/                  # Utility scripts
│   ├── hybridrag-watcher.py   # Watcher daemon (started by CLI)
│   ├── ingest_specstory_folders.sh
│   ├── watch_specstory_folders.sh
│   └── README.md
├── tests/                    # Test suite
├── memory-bank/             # Project documentation (tracked in git)
│   ├── projectbrief.md
│   ├── activeContext.md
│   ├── techContext.md
│   ├── systemPatterns.md
│   ├── progress.md
│   ├── productContext.md
│   └── CLAUDE.md
├── docs/                    # Extended documentation
│   └── user-stories/
│       └── specstory-setup-guide.md  # Full SpecStory setup walkthrough
├── lightrag_db/            # LightRAG working directory (PostgreSQL metadata)
├── .last_specstory_watch   # Delta ingestion timestamp
└── ~/.hybridrag/
    └── registry.yaml       # Database registry (single source of truth)
```

**Note:** Use the `hybridrag` CLI command (installed via `pip install -e .`). Scripts in `legacy/` are deprecated.

## 🚨 Error Handling

The system implements comprehensive error handling:

- **File Processing Errors**: Files with errors are moved to `ingestion_queue/errors/`
- **API Rate Limits**: Built-in retry logic with exponential backoff
- **Network Issues**: Graceful degradation and fallback mechanisms
- **Resource Exhaustion**: Memory and disk usage monitoring
- **Graceful Shutdown**: Signal handling for clean termination

## 📈 Performance Tuning

### Ingestion Performance
- Adjust `batch_size` for throughput vs. memory usage
- Configure `max_concurrent_ingestions` based on system resources
- Set appropriate `poll_interval` for responsiveness vs. CPU usage

### Search Performance
- Use `local` mode for specific entity queries
- Use `global` mode for broad overviews
- Use `hybrid` mode for balanced results
- Enable `reranking` for improved relevance

### Memory Management
- Configure `chunk_size` and `chunk_overlap` for optimal indexing
- Set `max_file_size_mb` to prevent memory issues
- Monitor LightRAG database size and consider periodic cleanup

## 🔍 Troubleshooting

### Common Issues

1. **Import Errors**: Ensure PromptChain is installed for agentic features
2. **API Rate Limits**: Reduce batch sizes and increase delays
3. **Memory Issues**: Lower chunk sizes and concurrent processing
4. **File Processing**: Check file permissions and encoding
5. **LightRAG Errors**: Verify API key for your model provider (AZURE_API_KEY, OPENAI_API_KEY, etc.)

### Debug Mode
Enable verbose logging:
```bash
export HYBRIDRAG_LOG_LEVEL=DEBUG
hybridrag --db mydb interactive
```

### Health Checks
Regular system health monitoring:
```bash
hybridrag --db mydb status
hybridrag db watch status
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- **LightRAG**: Knowledge graph construction and querying
- **PromptChain**: Multi-hop reasoning and agent orchestration
- **LiteLLM**: Unified interface for multiple LLM providers (Azure, OpenAI, Anthropic, Gemini)
- **Community**: Various document processing libraries

---

**Happy Searching! 🔍✨**