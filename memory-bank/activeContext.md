# HybridRAG Active Context

**Last Updated**: 2026-02-06
**Session**: mcp-backend-metadata-2026-02-06
**Status**: Active, fully operational

## Current State

### What's Working Right Now
- :white_check_mark: **Backend Metadata**: All 8 MCP tools show which backend is serving queries
- :white_check_mark: **Registry Auto-Resolution**: `--db specstory` auto-resolves from `~/.hybridrag/registry.yaml`
- :white_check_mark: **Config Split**: Clean separation between app_config.py and backend_config.py
- :white_check_mark: **CLI Installation**: `hybridrag` command installed and working system-wide
- :white_check_mark: **PostgreSQL Backend**: Running on localhost:5433, 31K+ rows, 7K+ entities/relationships
- :white_check_mark: **Watcher Coverage**: Monitoring entire `/home/gyasisutton/dev` tree (27 SpecStory folders)
- :white_check_mark: **Delta Ingestion**: .last_specstory_watch set to 2026-01-17 for incremental processing
- :white_check_mark: **All MCP Tools Tested**: hybrid_query, local_query, global_query, multihop_query, extract_context, database_status, health_check, get_logs

### Active Backend Configuration
```yaml
Backend Type: postgresql
Host: localhost:5433
Database: hybridrag
User: hybridrag
Tables: 31K+ rows total
  - Entities: 7K+
  - Relationships: 7K+
  - Chunks: ~7K
  - Source documents tracked
```

### Recent Changes (Feb 6, 2026)

#### 1. Backend Metadata Injection (Completed)
Added `get_backend_metadata_line()` function to `hybridrag_mcp/server.py`:
- Shows active backend (postgres/json/mongo/etc) in every MCP response
- Masks credentials with urllib.parse (handles special chars in passwords)
- Displays connection details: host, port, database name
- Applied to all 8 MCP tools

#### 2. Registry Auto-Resolution (Completed)
Modified `hybridrag.py` to auto-resolve backend config:
- Read `~/.hybridrag/registry.yaml` on startup
- Match by database name (`--db specstory`) or source path
- Eliminated need for `BACKEND_TYPE` environment variable
- Added `--show-backend` CLI flag for diagnostics

#### 3. Config Module Split (Completed)
Refactored configuration structure:
- Created `src/config/app_config.py`: HybridRAGConfig, LightRAGConfig, IngestionConfig, SearchConfig, SystemConfig
- Created `src/config/backend_config.py`: BackendType enum (9 backends), BackendConfig
- Deleted old `config/config.py` and `src/config/config.py`
- Updated 13+ files with new imports

#### 4. CLI Entry Point (Completed)
Made CLI installable via pip/uv:
- Added `[build-system]` to pyproject.toml (setuptools)
- Added `[project.scripts]` entry: `hybridrag = "hybridrag:main"`
- Command available system-wide after `pip install -e .`

#### 5. Watcher Expansion (Completed)
Updated specstory watcher to cover entire dev tree:
- Changed source_folder from `/home/gyasisutton/dev/jira-issues` to `/home/gyasisutton/dev`
- Now monitors all 27 SpecStory folders across dev tree
- Set `.last_specstory_watch` to Jan 17 2026 (migration date)
- Started watcher via `hybridrag --db specstory db watch start`

#### 6. Model Precedence Chain (Completed)
Fixed model override logic:
- Precedence: CLI `--model` > model_config.yaml > db_entry.model > DEPLOYMENT_MODEL env > default (gpt-4o-mini)
- Explicit fallback chain prevents confusion
- Works for embeddings too (CLI > config > env > default)

#### 7. Git Commits (Completed)
Two commits made today:
```
10ac188 - feat: add backend metadata to MCP tools and registry auto-resolution
b5b78f6 - refactor: split config into app_config and backend_config, add CLI entry point
```

## Current Focus

### Immediate Priorities
1. Monitor watcher performance on expanded dev tree
2. Verify delta ingestion only processes new/modified files
3. Ensure MCP tools perform well with growing knowledge graph

### Next Actions (If Needed)
- Performance tuning if query times increase
- Add more specialized SpecStory preprocessing if conversation format evolves
- Consider sharding if single database becomes too large

## Known Issues / Caveats

### None Critical
All systems operational. No blocking issues.

### Minor Notes
- Ruff suggested removing unused imports (already fixed)
- Some old migration code in `src/ingestion/migrations.py` could be cleaned up (non-urgent)
- TUI monitor (textual) not actively used, but functional

## Important File Paths

### Core Entry Points
- `/home/gyasisutton/dev/tools/RAG/hybridrag/hybridrag.py` - Main CLI
- `/home/gyasisutton/dev/tools/RAG/hybridrag/hybridrag_mcp/server.py` - MCP server

### Configuration
- `~/.hybridrag/registry.yaml` - Database registry (single source of truth)
- `/home/gyasisutton/dev/tools/RAG/hybridrag/.env` - Environment variables (API keys)
- `/home/gyasisutton/dev/tools/RAG/hybridrag/src/config/app_config.py` - App settings
- `/home/gyasisutton/dev/tools/RAG/hybridrag/src/config/backend_config.py` - Backend configs

### Database
- `/home/gyasisutton/dev/tools/RAG/hybridrag/lightrag_db/` - PostgreSQL-backed LightRAG DB
- PostgreSQL container: Apache AGE + pgvector on port 5433

### Watcher State
- `/home/gyasisutton/dev/tools/RAG/hybridrag/.last_specstory_watch` - Delta timestamp
- `/run/user/1000/hybridrag_watcher_specstory.pid` - Watcher PID file

### Memory Bank
- `/home/gyasisutton/dev/tools/RAG/hybridrag/.memory/session.json` - Session state
- `/home/gyasisutton/dev/tools/RAG/hybridrag/memory-bank/` - Project documentation (this folder)

## Environment Variables in Use

```bash
# API Keys
AZURE_API_KEY=***
AZURE_API_BASE=***
OPENAI_API_KEY=***

# Optional Overrides
DEPLOYMENT_MODEL=azure/gpt-5.1  # Default model (can override with CLI --model)
LIGHTRAG_MODEL=azure/gpt-5.1    # LightRAG-specific override

# Backend Config (now optional - registry handles this)
BACKEND_TYPE=postgres  # Auto-resolved from registry, no longer required
```

## Quick Commands

```bash
# Query the specstory database
hybridrag --db specstory query --text "TIC-4376 progress" --mode hybrid

# Check database status
hybridrag --db specstory status

# Show which backend is being used
hybridrag --db specstory --show-backend query --text "test"

# Start/stop watcher
hybridrag --db specstory db watch start
hybridrag --db specstory db watch stop

# Check watcher status
hybridrag db watch status

# List all registered databases
hybridrag db list

# Interactive query mode
hybridrag --db specstory interactive
```

## Session Continuity

This session has survived 4 compactions. Key discoveries preserved in `.memory/session.json`:
- Backend metadata pattern
- Registry auto-resolution pattern
- Config split rationale
- CLI installation method
- Credential masking with urllib.parse
- Model precedence chain

All work committed to git. Memory bank now tracked in repo for cross-session continuity.
