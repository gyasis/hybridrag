# HybridRAG SpecStory Setup Guide

Complete documentation for setting up HybridRAG with SpecStory conversation history.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Configuration System](#configuration-system)
3. [Environment Variables](#environment-variables)
4. [MCP Server Setup](#mcp-server-setup)
5. [Ingestion Workflow](#ingestion-workflow)
6. [Query Tools](#query-tools)
7. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           YOUR PROJECTS                                      │
│  /home/user/dev/                                                            │
│  ├── project-alpha/.specstory/history/*.md                                  │
│  ├── project-beta/.specstory/history/*.md                                   │
│  └── jira-issues/TIC-123/.specstory/history/*.md                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         INGESTION LAYER                                      │
│  Scripts:                                                                    │
│  • ingest_specstory_folders.sh  → Auto-finds .specstory folders             │
│  • ingest_recursive.sh          → Generic folder/file patterns              │
│  • hybridrag-watcher.py         → Continuous monitoring daemon              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         LIGHTRAG DATABASE                                    │
│  ./lightrag_db/                                                             │
│  ├── Entities (nodes in knowledge graph)                                    │
│  ├── Relationships (edges between entities)                                 │
│  ├── Text chunks (source content)                                           │
│  └── Vector embeddings (for semantic search)                                │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          MCP SERVER                                          │
│  hybridrag_mcp/server.py                                                    │
│  • Exposes query tools to Claude Desktop/Claude Code                        │
│  • local_query, global_query, hybrid_query, multihop_query                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        CLAUDE CODE / CLAUDE DESKTOP                          │
│  Uses MCP tools: hybridrag_hybrid_query, hybridrag_local_query, etc.       │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Configuration System

HybridRAG has **TWO configuration modules** that serve different purposes:

### 1. Main Config: `config/config.py`

**Purpose:** LLM settings, ingestion, search behavior

```python
# config/config.py - Main configuration classes

@dataclass
class LightRAGConfig:
    """LightRAG-specific settings."""
    working_dir: str = "./lightrag_db"
    model_name: str = "azure/gpt-5.1"           # From LIGHTRAG_MODEL env
    embedding_model: str = "azure/text-embedding-3-small"  # From LIGHTRAG_EMBED_MODEL
    embedding_dim: int = 1536
    max_async: int = 4
    enable_cache: bool = True
    chunk_size: int = 1200
    chunk_overlap: int = 100

@dataclass
class IngestionConfig:
    """Document ingestion settings."""
    watch_folders: List[str] = ["./data"]
    file_extensions: List[str] = [".txt", ".md", ".pdf", ".json", ".py", ...]
    recursive: bool = True
    batch_size: int = 10
    poll_interval: float = 5.0  # seconds
    max_file_size_mb: float = 50.0

@dataclass
class SearchConfig:
    """Query/search behavior."""
    default_mode: str = "hybrid"  # local, global, hybrid, naive
    default_top_k: int = 10
    max_entity_tokens: int = 6000
    max_relation_tokens: int = 8000
    enable_reranking: bool = True

@dataclass
class SystemConfig:
    """System-wide settings."""
    log_dir: str = "./logs"
    log_level: str = "INFO"
    enable_monitoring: bool = True
    max_concurrent_ingestions: int = 3

@dataclass
class HybridRAGConfig:
    """Complete config combining all above."""
    lightrag: LightRAGConfig
    ingestion: IngestionConfig
    search: SearchConfig
    system: SystemConfig
```

**Usage:**
```python
from config.config import load_config, HybridRAGConfig

# Load defaults (uses environment variables)
config = load_config()

# Access settings
print(config.lightrag.model_name)  # "azure/gpt-5.1"
print(config.search.default_mode)   # "hybrid"
```

### 2. Backend Config: `src/config/config.py`

**Purpose:** Storage backend selection (JSON files vs PostgreSQL)

```python
# src/config/config.py - Storage backend configuration

class BackendType(str, Enum):
    """Supported storage backends."""
    JSON = "json"           # Default: JSON files + NanoVectorDB + NetworkX
    POSTGRESQL = "postgres" # PostgreSQL + pgvector + AGE
    MONGODB = "mongodb"     # Future support

@dataclass
class BackendConfig:
    """Storage backend settings."""
    backend_type: BackendType = BackendType.JSON

    # PostgreSQL settings (only used if backend_type=POSTGRESQL)
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "hybridrag"
    postgres_password: Optional[str] = None
    postgres_database: str = "hybridrag"

    # Vector index type
    vector_index_type: str = "hnsw"  # hnsw or ivfflat
```

### Why Two Configs Don't Interfere

| Config File | Handles | Imported By |
|-------------|---------|-------------|
| `config/config.py` | LLM, ingestion, search, system | hybridrag.py, MCP server, tests |
| `src/config/config.py` | Storage backend only | Database registry, backend selection |

They're **separate concerns**:
- `config/config.py` = "How to process and query"
- `src/config/config.py` = "Where to store data"

---

## Environment Variables

Create a `.env` file in the project root:

```bash
# =============================================================================
# API KEYS (Required - pick one provider)
# =============================================================================

# Azure OpenAI (PREFERRED)
AZURE_API_KEY=your-azure-key
AZURE_API_BASE=https://your-resource.openai.azure.com
AZURE_API_VERSION=2025-01-01-preview

# OpenAI (fallback)
OPENAI_API_KEY=sk-...

# Anthropic (for PromptChain features)
ANTHROPIC_API_KEY=sk-ant-...

# =============================================================================
# MODEL CONFIGURATION (LiteLLM format)
# =============================================================================

# Main RAG model - used for generating answers
LIGHTRAG_MODEL=azure/gpt-5.1

# Agentic reasoning model - used for multihop queries
AGENTIC_MODEL=azure/gpt-5.1

# Embedding model - used for vector search
LIGHTRAG_EMBED_MODEL=azure/text-embedding-3-small

# Model format examples:
#   OpenAI:  openai/gpt-4o-mini, openai/gpt-4-turbo
#   Azure:   azure/<deployment_name>
#   Ollama:  ollama/llama2, ollama/mistral

# Enable LiteLLM for multi-provider support
LIGHTRAG_USE_LITELLM=true

# =============================================================================
# OPTIONAL SETTINGS
# =============================================================================

# Logging
LOG_LEVEL=INFO

# Default model settings
MAX_TOKENS=16000
TEMPERATURE=0.7

# MCP development
DANGEROUSLY_OMIT_AUTH=true
```

---

## MCP Server Setup

### Claude Desktop Configuration

Add to `~/.config/claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "hybridrag-specstory": {
      "command": "uv",
      "args": [
        "--directory",
        "/home/user/dev/tools/RAG/hybridrag",
        "run",
        "python",
        "-m",
        "hybridrag_mcp"
      ],
      "env": {
        "HYBRIDRAG_DATABASE": "/home/user/dev/tools/RAG/hybridrag/lightrag_db",
        "HYBRIDRAG_MODEL": "azure/gpt-5.1",
        "AZURE_API_KEY": "${AZURE_API_KEY}",
        "AZURE_API_BASE": "${AZURE_API_BASE}"
      }
    }
  }
}
```

### Environment Variables for MCP Server

| Variable | Required | Description |
|----------|----------|-------------|
| `HYBRIDRAG_DATABASE` | **Yes** | Path to LightRAG database directory |
| `HYBRIDRAG_MODEL` | No | Override LLM model (default: from .env) |
| `HYBRIDRAG_EMBED_MODEL` | No | Override embedding model |
| `AZURE_API_KEY` | Yes* | Azure API key (*or OPENAI_API_KEY) |
| `AZURE_API_BASE` | Yes* | Azure endpoint URL |

### MCP Server Startup Flow

```
1. Server reads HYBRIDRAG_DATABASE env var
2. Validates database path exists (warns if not)
3. Creates HybridRAGConfig from config/config.py
4. Applies model overrides from env vars
5. Lazy-initializes HybridLightRAGCore on first query
6. Exposes tools via FastMCP
```

---

## Ingestion Workflow

### Step 1: Initial Ingestion

```bash
cd /home/user/dev/tools/RAG/hybridrag

# SpecStory-specific (auto-finds .specstory folders)
./scripts/ingest_specstory_folders.sh /home/user/dev fresh

# OR generic (custom folder/file patterns)
./scripts/ingest_recursive.sh /home/user/dev fresh \
    --folders ".specstory,docs" \
    --files "*.md"
```

### Step 2: Register Database (Optional)

```bash
python hybridrag.py db register specstory \
    --path ./lightrag_db \
    --source /home/user/dev \
    --type specstory \
    --auto-watch \
    --interval 300
```

### Step 3: Start Watcher (Continuous Monitoring)

```bash
# Manual watcher
python hybridrag.py db watch start specstory

# Or systemd service
python hybridrag.py db watch start specstory --systemd
```

### Step 4: Add More Sources Later

```bash
# Always use 'add' to preserve existing data
./scripts/ingest_specstory_folders.sh /home/user/work add
./scripts/ingest_recursive.sh /mnt/external add --folders "docs"
```

---

## Query Tools

### Available MCP Tools

| Tool | Mode | Use When |
|------|------|----------|
| `hybridrag_local_query` | local | Specific entities, names, functions |
| `hybridrag_global_query` | global | Overviews, summaries, patterns |
| `hybridrag_hybrid_query` | hybrid | **Default** - combines both |
| `hybridrag_query` | configurable | Full control over mode |
| `hybridrag_multihop_query` | agentic | Complex multi-step reasoning |
| `hybridrag_extract_context` | raw | Get chunks without LLM synthesis |
| `hybridrag_database_status` | - | Check DB stats and config |
| `hybridrag_health_check` | - | Verify system health |
| `hybridrag_get_logs` | - | View recent server logs |

### Mode Selection Guide

```
DECISION TREE:

1. Asking about a specific named thing?
   → Use "local" (hybridrag_local_query)

2. Asking for overview/summary/patterns?
   → Use "global" (hybridrag_global_query)

3. Need both specifics AND context?
   → Use "hybrid" (hybridrag_hybrid_query) ← DEFAULT

4. Complex analysis requiring multiple steps?
   → Use "multihop" (hybridrag_multihop_query)

5. Want raw chunks for custom processing?
   → Use extract_context
```

### Example Queries

```python
# Local: Find specific entity
"What is the TIC-4376 ticket about?"

# Global: Get overview
"What are the main patterns in our ETL pipelines?"

# Hybrid: General question (DEFAULT)
"How did we implement authentication?"

# Multihop: Complex analysis
"Compare the approaches used in TIC-4376 vs RAF-TRANSITION-2026"
```

---

## Troubleshooting

### MCP Server Not Starting

```bash
# Check if database path exists
ls -la /path/to/lightrag_db

# Check environment variables
env | grep HYBRIDRAG

# Test server manually
cd /path/to/hybridrag
python -m hybridrag_mcp
```

### Queries Timing Out

- Multihop queries can take 2-10 minutes
- Use simpler modes (hybrid, local) for faster results
- Check `hybridrag_get_logs` for progress

### Config Not Loading

```bash
# Verify .env file exists and has API keys
cat .env | grep -E "(AZURE|OPENAI)_API_KEY"

# Test config loading
python -c "from config.config import load_config; c = load_config(); print(c.lightrag.model_name)"
```

### Database Issues

```bash
# Check database status
python hybridrag.py check-db

# View detailed stats
python hybridrag.py db show specstory --stats

# Force re-initialization
python hybridrag.py status
```

---

## Quick Reference

### Files

| File | Purpose |
|------|---------|
| `.env` | API keys and model config |
| `config/config.py` | Main config classes |
| `src/config/config.py` | Backend config classes |
| `hybridrag_mcp/server.py` | MCP server implementation |
| `scripts/ingest_specstory_folders.sh` | SpecStory ingestion |
| `scripts/ingest_recursive.sh` | Generic ingestion |

### Commands

```bash
# Ingest
./scripts/ingest_specstory_folders.sh /path fresh|add
./scripts/ingest_recursive.sh /path fresh|add --folders "..." --files "..."

# Database management
python hybridrag.py check-db
python hybridrag.py db list
python hybridrag.py db show <name> --stats

# Watcher
python hybridrag.py db watch start <name>
python hybridrag.py db watch status

# Interactive query
python hybridrag.py interactive
python hybridrag.py query "your question" --mode hybrid
```

---

## Summary

1. **Config system**: Two files, separate concerns (LLM vs storage)
2. **Environment**: API keys + model names in `.env`
3. **MCP Server**: Configured in Claude Desktop config, needs `HYBRIDRAG_DATABASE`
4. **Ingestion**: Use scripts to find and ingest .specstory folders
5. **Queries**: Use hybrid mode by default, multihop for complex questions
