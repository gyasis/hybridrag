# HybridRAG Machine State & Setup Guide

> **Generated**: 2026-02-06
> **Source Machine**: WSL2 (Linux 5.15.167.4-microsoft-standard-WSL2)
> **Branch**: `master` (2 commits ahead of origin)
> **Last Commit**: `857b14f` - feat: enhance HybridRAG with diagnostic logging and improved config (2026-01-30)

---

## 1. Git Status Summary

**Branch**: `master`
**Remote**: `https://github.com/gyasis/hybridrag.git`
**State**: 2 commits ahead of `origin/master` (need `git push`)

### Recent Commits (Latest First)
```
857b14f feat: enhance HybridRAG with diagnostic logging and improved config
d22f838 fix: add dotenv loading and env var fallback chain for model override
9372a2d docs: add reusable PostgreSQL config template
73ec985 docs: consolidate HybridRAG documentation and fix conflicts
1147a55 feat: add database migration tools and batch ingestion controller
1e817d6 docs: add deployment guides, PRD, and technical documentation
7924378 docs: add comprehensive project documentation and LICENSE
da94f12 docs(postgres): clarify Apache AGE + pgvector dual requirement
1c38a29 feat(watcher): add adaptive batch processing with resource monitoring
0938d77 fix: upgrade LightRAG and fix type safety issues
```

### Modified (Unstaged)
- `.memory/session.json` (internal session state - do not commit)

### Untracked Files (Need Decision)
| File/Dir | Purpose | Commit? |
|----------|---------|---------|
| `DEV_TESTING_GUIDE.md` | Development testing documentation | Yes |
| `OPTIMIZATION_STRATEGY.md` | Optimization notes | Yes |
| `context-knight/` | Context-Knight subproject vendored locally | No (separate repo) |
| `lightrag_db_backup_20260117_164525.tar.gz` | DB backup (3.2GB) | NO - too large |
| `prd/` | Product requirements docs | Yes |
| `scripts/alter_vector_dimension.py` | Utility script | Yes |
| `scripts/fix_embeddings.py` | Embedding fix utility | Yes |
| `scripts/migration/` | Migration tools | Yes |
| `scripts/regenerate_embeddings.py` | Embedding regeneration | Yes |
| `scripts/restore_embeddings_from_matrix.py` | Embedding restore utility | Yes |
| `scripts/start_mcp_server.sh` | MCP server launcher script | Yes |
| `specs/` | SpecKit specifications | Yes |
| `.specify/` | SpecKit artifacts | Yes |
| `test_json_db_direct.py` | Direct JSON DB test | Yes |
| `.memory/` files | Session memory (auto-generated) | No |

---

## 2. System Prerequisites

### Tool Versions (Current Machine)
| Tool | Version | Install Method |
|------|---------|----------------|
| Python | 3.13.2 | System |
| uv | 0.9.4 | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node.js | v24.2.0 | nvm |
| Bun | 1.3.0 | `curl -fsSL https://bun.sh/install \| bash` |
| Docker | 28.1.1 | apt / Docker Desktop |
| Git | 2.43.0 | apt |

### Python Version
The project uses **Python 3.12.5** (specified in `.python-version`), managed by `uv`.

---

## 3. Repository Structure

```
hybridrag/
├── .claude/                    # Project-level Claude Code settings
│   ├── commands/               # SpecKit slash commands
│   └── settings.local.json     # Project permissions
├── .env                        # ACTIVE env config (DO NOT COMMIT)
├── .env.example                # Template for .env
├── .env.docker.example         # Docker-specific env template
├── .gitignore
├── .memory/                    # Session memory (auto-generated)
├── .python-version             # Python 3.12.5
├── .specify/                   # SpecKit artifacts
├── .specstory/                 # SpecStory conversation history
├── .venv/                      # UV-managed virtual environment
│
├── config/
│   ├── config.py               # Runtime configuration module
│   ├── claude_desktop_config.example.json
│   ├── claude_desktop_config.multi_project.json
│   └── claude_desktop_config.uv.json
│
├── docker/                     # Docker build files
├── docker-compose.yml          # Container orchestration
├── Dockerfile
│
├── docs/                       # Documentation
├── hybridrag.py                # Main CLI entry point (132KB)
├── hybridrag_mcp/              # MCP Server Package
│   ├── __init__.py
│   ├── __main__.py             # Entry: python -m hybridrag_mcp
│   ├── diagnostic_logging.py   # MCP debug logging
│   └── server.py               # FastMCP server implementation
│
├── lightrag_db/                # LightRAG Knowledge Base (9.8GB)
│   ├── database_metadata.json
│   ├── graph_chunk_entity_relation.graphml
│   ├── kv_store_*.json         # Key-value stores
│   └── vdb_*.json              # Vector database files
│
├── migrations/                 # Database migration scripts
├── pyproject.toml              # Project config & dependencies
├── requirements.txt            # Core requirements
├── requirements-mcp.txt        # MCP server requirements
│
├── scripts/                    # Utility scripts
│   ├── alter_vector_dimension.py
│   ├── fix_embeddings.py
│   ├── migration/
│   ├── regenerate_embeddings.py
│   ├── restore_embeddings_from_matrix.py
│   └── start_mcp_server.sh
│
├── src/                        # Core library
│   ├── agentic_rag.py          # Multi-step reasoning with circuit breaker
│   ├── alerting.py             # Alert system
│   ├── config/config.py        # Configuration management
│   ├── database_metadata.py    # DB metadata handling
│   ├── database_registry.py    # Multi-DB registry
│   ├── folder_watcher.py       # File system watcher
│   ├── ingestion_pipeline.py   # Document ingestion
│   ├── lightrag_core.py        # LightRAG wrapper (Azure/LiteLLM)
│   ├── migration/              # JSON-to-Postgres migration
│   │   ├── backup.py
│   │   ├── json_to_postgres.py
│   │   └── verify.py
│   ├── monitor/                # TUI monitoring dashboard
│   │   ├── app.py
│   │   ├── data_collector.py
│   │   ├── screens/
│   │   └── widgets/
│   ├── process_manager.py
│   ├── search_interface.py
│   ├── utils.py
│   ├── watch_manager.py
│   └── watcher_control.py
│
├── tests/                      # Test suite
├── uv.lock                     # UV lock file
│
├── DEV_TESTING_GUIDE.md
├── LICENSE                     # MIT
├── OPTIMIZATION_STRATEGY.md
├── QUICK_START_SPECSTORY.md
├── README.md
└── SPECSTORY_CHEATSHEET.md
```

---

## 4. Environment Setup (New Machine)

### Step 1: Clone the Repo
```bash
git clone https://github.com/gyasis/hybridrag.git
cd hybridrag
```

### Step 2: Install UV (Python Package Manager)
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Step 3: Create Virtual Environment & Install Dependencies
```bash
uv sync
```
This reads `pyproject.toml` + `uv.lock` and creates `.venv/` with all dependencies.

### Step 4: Configure Environment
```bash
cp .env.example .env
# Edit .env with your API keys and settings
```

**Critical `.env` variables:**
```bash
# LLM Provider (LiteLLM format)
LIGHTRAG_MODEL=azure/gpt-5.1           # or openai/gpt-4o-mini
AGENTIC_MODEL=azure/gpt-5.1
LIGHTRAG_EMBED_MODEL=azure/text-embedding-3-small

# Embedding dimension - MUST match your model
EMBEDDING_DIM=768    # Azure text-embedding-3-small = 768
                     # OpenAI text-embedding-3-small = 1536

# API Keys
OPENAI_API_KEY=your_key
AZURE_API_KEY=your_key
AZURE_API_BASE=https://your-resource.openai.azure.com
AZURE_API_VERSION=2025-01-01-preview

# Storage backend
BACKEND_TYPE=json    # or postgres

# MCP Server
HYBRIDRAG_DATABASE_NAME=specstory
HYBRIDRAG_LOG_LEVEL=INFO
```

### Step 5: Verify Installation
```bash
# Activate venv
source .venv/bin/activate

# Test CLI
python hybridrag.py check-db

# Test MCP server startup
python -m hybridrag_mcp
```

---

## 5. MCP Server Configuration for Claude Code

The MCP servers are configured in `~/.claude.json` under the `mcpServers` key. Below is the **hybridrag-specstory** entry and all related MCP servers used in this project.

### HybridRAG MCP Server Entry
```json
{
  "hybridrag-specstory": {
    "command": "uv",
    "args": [
      "--directory",
      "/home/gyasisutton/dev/tools/RAG/hybridrag",
      "run",
      "python",
      "-m",
      "hybridrag_mcp"
    ],
    "env": {
      "HYBRIDRAG_DATABASE": "/home/gyasisutton/dev/tools/RAG/hybridrag/lightrag_db",
      "HYBRIDRAG_DATABASE_NAME": "specstory",
      "HYBRIDRAG_MODEL": "openai/gpt-4o-mini",
      "HYBRIDRAG_EMBED_MODEL": "azure/text-embedding-3-small",
      "EMBEDDING_DIM": "1536",
      "OPENAI_API_KEY": "<YOUR_OPENAI_KEY>",
      "AZURE_API_KEY": "<YOUR_AZURE_KEY>",
      "AZURE_API_BASE": "<YOUR_AZURE_ENDPOINT>"
    }
  }
}
```

### Full MCP Server List (All Servers in `~/.claude.json`)

**To replicate the full environment**, add ALL of the following to `~/.claude.json` under `"mcpServers"`:

```json
{
  "mcpServers": {
    "sequential-thinking": {
      "command": "<NODE_PATH>/npx",
      "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]
    },
    "context7-mcp": {
      "command": "<BUN_PATH>/bunx",
      "args": ["-y", "@upstash/context7-mcp@latest"]
    },
    "gemini-mcp": {
      "command": "<GEMINI_MCP_DIR>/.venv/bin/python",
      "args": ["<GEMINI_MCP_DIR>/server.py"],
      "cwd": "<GEMINI_MCP_DIR>",
      "env": {},
      "enabled": true
    },
    "playwright": {
      "command": "<NODE_PATH>/node",
      "args": ["<PLAYWRIGHT_MCP_DIR>/cli.js", "--browser", "chromium"]
    },
    "hybridrag-specstory": {
      "command": "uv",
      "args": ["--directory", "<HYBRIDRAG_DIR>", "run", "python", "-m", "hybridrag_mcp"],
      "env": {
        "HYBRIDRAG_DATABASE": "<HYBRIDRAG_DIR>/lightrag_db",
        "HYBRIDRAG_DATABASE_NAME": "specstory",
        "HYBRIDRAG_MODEL": "openai/gpt-4o-mini",
        "HYBRIDRAG_EMBED_MODEL": "azure/text-embedding-3-small",
        "EMBEDDING_DIM": "1536",
        "OPENAI_API_KEY": "<YOUR_OPENAI_KEY>",
        "AZURE_API_KEY": "<YOUR_AZURE_KEY>",
        "AZURE_API_BASE": "<YOUR_AZURE_ENDPOINT>"
      }
    },
    "graphiti": {
      "command": "uv",
      "args": [
        "--directory", "<GRAPHITI_MCP_DIR>",
        "run", "python", "main.py",
        "--config", "config/config-litellm-azure-balanced.yaml",
        "--transport", "stdio"
      ],
      "env": {
        "FALKORDB_URI": "redis://localhost:6379",
        "FALKORDB_DATABASE": "graphiti_memory",
        "AZURE_OPENAI_ENDPOINT": "<YOUR_AZURE_ENDPOINT>",
        "AZURE_OPENAI_API_KEY": "<YOUR_AZURE_KEY>",
        "AZURE_OPENAI_API_VERSION": "2024-12-01-preview",
        "AZURE_OPENAI_DEPLOYMENT": "model-router",
        "AZURE_OPENAI_EMBEDDING_DEPLOYMENT": "text-embedding-3-small",
        "GRAPHITI_GROUP_ID": "developer-gyasisutton"
      }
    },
    "context-knight": {
      "command": "uv",
      "args": ["run", "--directory", "<CK_DIR>", "python", "-m", "context_knight.server"],
      "cwd": "<CK_DIR>"
    },
    "duckdb-local": {
      "command": "uvx",
      "args": ["mcp-server-duckdb", "--db-path", ":memory:", "--keep-connection"],
      "env": {}
    },
    "gx-mcp-server": {
      "type": "http",
      "url": "http://localhost:8765/mcp"
    }
  }
}
```

> **NOTE**: Replace `<PLACEHOLDER>` values with actual paths/keys for your machine. API keys are intentionally redacted.

### Per-Project Disabled Servers

In `~/.claude.json` under `projects["/home/gyasisutton/dev/tools/RAG/hybridrag"]`:
```json
{
  "disabledMcpServers": [
    "vizro-mcp",
    "tableau-mcp",
    "superset",
    "playwright",
    "mcp-atlassian",
    "duckdb-local",
    "brand-vision-rag",
    "atlassian-remote",
    "athena-lightrag"
  ]
}
```

Only these servers are **active** for the hybridrag project:
- `hybridrag-specstory` - The HybridRAG MCP server itself
- `graphiti` - Permanent memory (knowledge graph)
- `context-knight` - Gemini delegation proxy
- `gemini-mcp` - Gemini AI tools
- `context7-mcp` - Library documentation lookup
- `sequential-thinking` - Reasoning tool
- `gx-mcp-server` - Great Expectations data quality

---

## 6. Claude Code Global Settings

### `~/.claude/settings.json`
```json
{
  "alwaysThinkingEnabled": true,
  "env": {
    "MCP_TOOL_TIMEOUT": "600000",
    "MCP_TIMEOUT": "30000"
  },
  "hooks": {
    "PreCompact": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${HOME}/.claude/hooks/unified-memory/pre-compact.sh",
            "timeout": 30
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${HOME}/.claude/hooks/unified-memory/check-post-compact.sh",
            "timeout": 5
          },
          {
            "type": "command",
            "command": "python3 ${HOME}/.claude/hooks/memory-orchestrator/memory-orchestrator.py",
            "timeout": 3
          }
        ]
      }
    ]
  }
}
```

**Key settings**:
- `MCP_TOOL_TIMEOUT=600000` (10 min) - Required for long-running multihop queries
- `MCP_TIMEOUT=30000` (30s) - MCP server startup timeout
- PreCompact hook - Auto-saves session state before context compression
- UserPromptSubmit hooks - Memory orchestration + post-compact recovery

---

## 7. LightRAG Database

**Location**: `./lightrag_db/`
**Size**: 9.8 GB
**Backend**: JSON (file-based)
**Contents**:
- `graph_chunk_entity_relation.graphml` - Knowledge graph
- `kv_store_*.json` - Key-value stores (docs, entities, relations, chunks, cache)
- `vdb_*.json` - Vector database files (chunks, entities, relationships)
- `database_metadata.json` - Database metadata

**Backup**: `lightrag_db_backup_20260117_164525.tar.gz` (3.2GB compressed)

> **WARNING**: The lightrag_db is 9.8GB. Do NOT commit to git. Transfer separately or rebuild from source data.

---

## 8. Key Dependencies

### From `pyproject.toml`
```
lightrag-hku>=0.1.0       # LightRAG knowledge graph engine
deeplake>=4.0.0            # DeepLake vector store
openai>=1.0.0              # OpenAI/Azure API client
litellm>=1.0.0             # Multi-LLM routing
fastmcp>=2.14.2            # MCP server framework (task=True support)
python-dotenv>=1.0.0       # Environment management
textual>=0.40.0            # TUI dashboard
asyncpg>=0.31.0            # PostgreSQL async driver
pypdf>=4.0.0               # PDF processing
beautifulsoup4>=4.12.0     # HTML parsing
tiktoken>=0.5.0            # Token counting
promptchain                # Custom (from github.com/gyasis/PromptChain)
```

### Custom Source
```toml
[tool.uv.sources]
promptchain = { git = "https://github.com/gyasis/PromptChain.git", branch = "main" }
```

---

## 9. How the MCP Server Works

### Startup Flow
1. Claude Code launches: `uv --directory <path> run python -m hybridrag_mcp`
2. `hybridrag_mcp/__main__.py` calls `server.main()`
3. Server reads env vars: `HYBRIDRAG_DATABASE`, `HYBRIDRAG_MODEL`, `HYBRIDRAG_EMBED_MODEL`
4. Initializes LightRAG core with the specified database
5. Creates temp log dir at `/tmp/hybridrag_mcp_logs/`
6. Registers MCP tools and starts stdio transport

### Available MCP Tools
| Tool | Description | Speed |
|------|-------------|-------|
| `hybridrag_local_query` | Entity-specific search | Fast |
| `hybridrag_global_query` | Overview/pattern search | Medium (background) |
| `hybridrag_hybrid_query` | Combined local+global | Medium (background) |
| `hybridrag_multihop_query` | Multi-step reasoning | Slow (background, up to 10min) |
| `hybridrag_extract_context` | Raw context retrieval | Fast |
| `hybridrag_health_check` | System health status | Fast |
| `hybridrag_get_logs` | View server logs | Fast |
| `hybridrag_database_status` | Database info | Fast |

### Background Tasks
- `global_query`, `hybrid_query`, and `multihop_query` use `@mcp.tool(task=True)` for background execution
- Multihop has a 600s (10 min) internal timeout with `asyncio.shield()` protection
- Requires `fastmcp>=2.14.2` for task support

---

## 10. Replication Checklist

To set up on a new machine:

- [ ] Install Python 3.12+, uv, Node.js, Bun, Docker, Git
- [ ] Clone repo: `git clone https://github.com/gyasis/hybridrag.git`
- [ ] Run `uv sync` in repo root
- [ ] Copy `.env.example` to `.env` and fill in API keys
- [ ] Transfer `lightrag_db/` from backup or rebuild from source
- [ ] Install Claude Code: `npm install -g @anthropic-ai/claude-code`
- [ ] Copy `~/.claude.json` MCP config (redact and re-fill keys)
- [ ] Copy `~/.claude/settings.json` for hooks and timeout config
- [ ] Copy `~/.claude/hooks/unified-memory/` directory for memory hooks
- [ ] Copy `~/.claude/hooks/memory-orchestrator/` for orchestration
- [ ] Install FalkorDB (Redis) for Graphiti: `docker run -p 6379:6379 falkordb/falkordb`
- [ ] Clone and set up sibling MCP repos:
  - `graphiti-mcp` - Permanent memory
  - `context-knight` - Gemini delegation
  - `gemini-mcp` - Gemini AI tools
- [ ] Run `claude mcp list` to verify all servers connect
- [ ] Run `python -m hybridrag_mcp` to test MCP server standalone

---

## 11. Known Issues & Gotchas

1. **EMBEDDING_DIM mismatch**: If you get "No query context could be built" errors, check that `EMBEDDING_DIM` matches your actual embedding model output (Azure=768, OpenAI=1536)
2. **LiteLLM verbose mode**: NEVER enable in production MCP server - it corrupts stdio protocol
3. **lightrag_db size**: 9.8GB - don't commit to git, use backup/restore
4. **uv.lock in .gitignore**: The lock file IS tracked by git despite being listed in .gitignore (already committed)
5. **Multihop timeouts**: If multihop queries get cancelled, check `MCP_TOOL_TIMEOUT` is set to 600000 in Claude settings
6. **2 unpushed commits**: Run `git push` to sync `857b14f` and `d22f838` to origin
