# HybridRAG Project Brief

## What is HybridRAG?

HybridRAG is a comprehensive knowledge graph-based retrieval augmented generation (RAG) system built on LightRAG. It provides semantic search capabilities over document collections, with specialized support for SpecStory conversation histories from development projects.

## Core Purpose

Enable intelligent semantic search and knowledge retrieval across:
- SpecStory conversation histories from JIRA projects
- General document collections (markdown, PDF, HTML, JSON, YAML, code)
- Multi-project development knowledge bases

## Key Capabilities

### 1. Multi-Backend Storage
Supports 9 backend types for knowledge graph storage:
- **PostgreSQL** (primary, with pgvector for embeddings)
- JSON (filesystem-based)
- MongoDB, Neo4j, Milvus, Qdrant, Faiss, Redis, Memgraph

### 2. Registry-Based Database Management
Centralized database registry at `~/.hybridrag/registry.yaml`:
- Named database references (`--db specstory` vs long paths)
- Source folder tracking and auto-watch configuration
- Per-database model configuration
- Backend-specific connection settings

### 3. Multiple Query Modes
- **Local**: Entity-focused retrieval for specific entities
- **Global**: Community-based summaries and overviews
- **Hybrid**: Combined local + global (recommended default)
- **Naive**: Simple vector similarity
- **Mix**: Comprehensive coverage
- **Multihop**: Multi-hop reasoning for complex analysis

### 4. MCP Server Integration
FastMCP server exposes 8 tools for Claude Desktop:
- `hybridrag_query` - Main query with mode selection
- `hybridrag_local_query` - Entity-focused retrieval
- `hybridrag_global_query` - Community summaries
- `hybridrag_hybrid_query` - Combined approach
- `hybridrag_multihop_query` - Multi-hop reasoning
- `hybridrag_extract_context` - Raw context extraction
- `hybridrag_database_status` - Database stats
- `hybridrag_health_check` - System health

### 5. Intelligent File Watching
- Recursive directory monitoring
- Delta-only ingestion (timestamp-based)
- SpecStory conversation extraction
- Automatic batch processing
- Systemd integration for persistent watchers

## Technical Foundation

- **Python 3.10+** with uv package manager
- **LightRAG-HKU** for knowledge graph construction
- **LiteLLM** for unified LLM interface (Azure, OpenAI, Anthropic, Gemini)
- **FastMCP** for Claude Desktop integration
- **PostgreSQL + pgvector** (Apache AGE container, port 5433)
- **Textual TUI** for monitoring
- **AsyncIO** throughout for performance

## Primary Use Case

Search and retrieve information from past development conversations stored in SpecStory format. Enables Claude Code to access historical context via the `specstory-search` skill, powered by the MCP server.

## Key Design Principles

1. **Registry as Single Source of Truth**: All database configs in one YAML file
2. **Backend Transparency**: Every MCP response shows which backend served it
3. **Model Flexibility**: Override models at CLI, env, or registry level
4. **Delta Ingestion**: Only process new/changed files since last run
5. **Multi-Project Support**: Single database can index multiple project folders
