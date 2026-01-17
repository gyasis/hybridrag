# HybridRAG Multi-Project Implementation Plan

**Version:** 1.0.0
**Created:** 2025-11-22
**Status:** Planning Complete - Ready for Implementation

---

## Executive Summary

Based on comprehensive research using **Gemini** (for MCP best practices) and **Context7** (for FastMCP and LightRAG documentation), this plan outlines the complete implementation strategy for deploying HybridRAG across multiple projects with MCP server integration.

### Key Findings from Research

1. **LightRAG Database Architecture:** Cannot switch `working_dir` at runtime → One MCP server per database (CONFIRMED via Context7 LightRAG docs)
2. **FastMCP Best Practices:** Environment variables, CLI arguments, and multi-server configs well-documented (via Context7 FastMCP docs)
3. **MCP Multi-Instance Patterns:** Industry standard patterns from Gemini research support our isolated server approach
4. **Docker Deployment:** Docker Compose is production-ready pattern for MCP servers (Gemini research)

### Research Sources

- **Gemini Research:** MCP server multi-instance setup patterns, Docker Compose configurations
- **Context7 - FastMCP (/jlowin/fastmcp):** MCP server configuration, environment variables, CLI patterns
- **Context7 - LightRAG (/hkuds/lightrag):** Database initialization, working_dir constraints, storage backends
- **Context7 - Docker Compose (/docker/compose):** Container orchestration patterns

---

## Table of Contents

1. [Project Goals](#project-goals)
2. [Architecture Overview](#architecture-overview)
3. [Minimal File Set](#minimal-file-set)
4. [Implementation Phases](#implementation-phases)
5. [Naming Conventions](#naming-conventions)
6. [Setup Scripts](#setup-scripts)
7. [Docker Deployment](#docker-deployment)
8. [Testing Strategy](#testing-strategy)
9. [Documentation Deliverables](#documentation-deliverables)
10. [Success Criteria](#success-criteria)

---

## Project Goals

### Primary Objectives

1. ✅ **Isolated Multi-Project Setup** - 3 projects + 1 PDF book, each with independent database
2. ✅ **MCP Server Integration** - Expose all databases to Claude Desktop
3. ✅ **Minimal Codebase** - Keep only essential files for production deployment
4. ✅ **Automated Setup** - Shell scripts for rapid project onboarding
5. ✅ **Docker Support** - Production-ready containerized deployment
6. ✅ **Generic Naming** - Move away from "athena-lightrag" to generic "hybridrag"
7. ✅ **Comprehensive Documentation** - Complete guides for all scenarios

### Future Enhancements

- 🔮 **HyperRAG Federated Layer** - Query across multiple databases (Phase 2)
- 🔮 **Web UI** - Visual database management dashboard
- 🔮 **Auto-Config Tool** - CLI tool to update MCP configs automatically

---

## Architecture Overview

### Confirmed Constraints

Based on **Context7 research on LightRAG**:

```python
# From LightRAG source code
class LightRAG:
    def __init__(self, working_dir: str = './rag_storage', ...):
        self.working_dir = working_dir  # FIXED AT INIT
        # Storage backends loaded from working_dir
        # NO runtime switching mechanism
```

**Implication:** Each database requires a separate LightRAG instance and MCP server process.

### Recommended Architecture

```
┌────────────────────────────────────────────────────┐
│         Claude Desktop (MCP Client)                │
└────────────────────────────────────────────────────┘
           │
           │ MCP Protocol (stdio)
           │
    ┌──────┴──────┬──────────┬──────────┐
    │             │          │          │
┌───▼────┐   ┌───▼────┐ ┌──▼────┐ ┌───▼────┐
│Proj1 KB│   │Proj2 KB│ │Proj3KB│ │Books KB│
│MCP Srv │   │MCP Srv │ │MCP Srv│ │MCP Srv │
└───┬────┘   └───┬────┘ └──┬────┘ └───┬────┘
    │             │          │          │
┌───▼────┐   ┌───▼────┐ ┌──▼────┐ ┌───▼────┐
│ proj1  │   │ proj2  │ │ proj3 │ │ books  │
│  _db/  │   │  _db/  │ │  _db/ │ │  _db/  │
│LightRAG│   │LightRAG│ │LightRAG│ │LightRAG│
└────────┘   └────────┘ └───────┘ └────────┘
```

---

## Minimal File Set

### Essential Files (Production Ready)

**Total: ~150KB of code**

```
hybridrag/
├── hybridrag.py                       # 24KB - CLI entry point
├── hybridrag_mcp_server.py            # NEW - MCP server implementation
│
├── src/
│   ├── lightrag_core.py               # 14KB - LightRAG wrapper
│   ├── database_metadata.py           # 7KB  - Database tracking
│   ├── ingestion_pipeline.py          # 15KB - Document processing
│   ├── folder_watcher.py              # 13KB - File monitoring
│   ├── search_interface.py            # 21KB - Query interface
│   ├── process_manager.py             # 21KB - Process orchestration
│   └── status_display.py              # 11KB - Status reporting
│
├── config/
│   └── config.py                      # 4KB  - Configuration dataclasses
│
├── pyproject.toml                     # 4KB  - Dependencies
├── requirements.txt                   # 4KB  - Alternative deps
├── requirements-mcp.txt               # NEW - MCP-specific deps
│
├── .env.example                       # 1KB  - Environment template
│
├── setup_project.sh                   # NEW - Project setup automation
├── setup_all_projects.sh              # NEW - Batch setup
│
├── Dockerfile                         # NEW - Docker build
├── docker-compose.yml                 # NEW - Multi-container
│
└── docs/
    ├── README.md                      # Quick start
    ├── USE_CASE_SCENARIOS.md          # ✅ Complete
    ├── MCP_SERVER_INTEGRATION.md      # ✅ Complete
    ├── IMPLEMENTATION_PLAN.md         # ✅ This document
    └── TROUBLESHOOTING.md             # NEW - Debug guide
```

### Files to Exclude (Not Required for Production)

```
examples/        # 32KB - Demo scripts
scripts/         # 20KB - Migration utilities
legacy/          # 60KB - Deprecated code
tests/           # 40KB - Development tests
memory-bank/     # 50KB - Project docs (runtime not needed)
.specstory/      # Project history (not runtime)
```

---

## Implementation Phases

### Phase 1: Core MCP Server (PRIORITY: HIGH)

**Estimated Effort:** 4-8 hours

**Tasks:**

1. ✅ **Research Complete** (DONE)
   - Gemini research on MCP patterns
   - Context7 docs for FastMCP and LightRAG
   - Architecture confirmed

2. **Create Generic MCP Server** (`hybridrag_mcp_server.py`)
   - Base on existing `athena_mcp_server.py`
   - Remove Athena/Snowflake-specific references
   - Add CLI arguments: `--working-dir`, `--name`
   - Implement 4 core tools:
     - `lightrag_local_query` - Specific entity queries
     - `lightrag_global_query` - High-level overviews
     - `lightrag_hybrid_query` - Balanced search (RECOMMENDED)
     - `get_database_info` - Database metadata

3. **Dependencies**
   - Create `requirements-mcp.txt`
   - Versions: `fastmcp>=2.0.0`, `lightrag-hku>=0.0.0.6`, `openai>=1.0.0`

4. **Testing**
   - Manual testing with test database
   - MCP Inspector validation
   - Tool discovery verification

**Deliverables:**
- `hybridrag_mcp_server.py` (functional MCP server)
- `requirements-mcp.txt` (dependencies)
- Test database for validation

**Acceptance Criteria:**
- Server starts without errors
- All 4 tools discoverable
- Query returns valid results
- Works with Claude Desktop

---

### Phase 2: Setup Automation (PRIORITY: HIGH)

**Estimated Effort:** 2-4 hours

**Tasks:**

1. **Create `setup_project.sh`**
   - Accept folder path and project name
   - Create database directory
   - Run ingestion (`hybridrag.py ingest`)
   - Generate MCP config snippet
   - Display setup summary

2. **Create `setup_all_projects.sh`**
   - Loop through multiple projects
   - Call `setup_project.sh` for each
   - Merge all MCP configs into single file
   - Validate final configuration

3. **Error Handling**
   - Validate folder exists
   - Check hybridrag installation
   - Verify environment variables
   - Provide helpful error messages

**Deliverables:**
- `setup_project.sh` (single project setup)
- `setup_all_projects.sh` (batch setup)
- Example config outputs

**Acceptance Criteria:**
- Scripts run without errors
- Databases created successfully
- MCP config snippets valid JSON
- Clear user feedback at each step

---

### Phase 3: Docker Support (PRIORITY: MEDIUM)

**Estimated Effort:** 3-6 hours

**Tasks:**

1. **Create Dockerfile**
   - Base image: `python:3.11-slim`
   - Install system dependencies
   - Copy application code
   - Set up entrypoint

2. **Create docker-compose.yml**
   - Define services for each project
   - Volume mappings for databases
   - Environment variable configuration
   - Network setup

3. **Docker Testing**
   - Build images
   - Test single container
   - Test multi-container setup
   - Verify MCP connectivity

**Deliverables:**
- `Dockerfile` (image build)
- `docker-compose.yml` (orchestration)
- `.dockerignore` (build optimization)
- Docker deployment guide in docs

**Acceptance Criteria:**
- Images build successfully
- Containers start and run stably
- MCP servers accessible from Claude Desktop
- Volume persistence working

---

### Phase 4: Documentation (PRIORITY: HIGH)

**Estimated Effort:** 4-6 hours

**Status:**
- ✅ `USE_CASE_SCENARIOS.md` - COMPLETE
- ✅ `MCP_SERVER_INTEGRATION.md` - COMPLETE
- ✅ `IMPLEMENTATION_PLAN.md` - COMPLETE (this document)

**Remaining:**

1. **TROUBLESHOOTING.md**
   - Common errors and solutions
   - Debug procedures
   - Log analysis guide
   - FAQ section

2. **README.md Updates**
   - Add MCP server quickstart
   - Link to new documentation
   - Installation instructions
   - Example commands

3. **Code Documentation**
   - Docstrings for MCP server
   - Inline comments for complex logic
   - Type hints throughout

**Deliverables:**
- `TROUBLESHOOTING.md`
- Updated `README.md`
- Comprehensive code documentation

**Acceptance Criteria:**
- All scenarios documented
- Step-by-step guides complete
- Troubleshooting covers major issues
- Examples tested and working

---

### Phase 5: Testing & Validation (PRIORITY: HIGH)

**Estimated Effort:** 2-4 hours

**Tasks:**

1. **Unit Tests**
   - MCP server tool functions
   - Database initialization
   - Query parameter validation

2. **Integration Tests**
   - End-to-end MCP workflow
   - Multi-server configuration
   - Claude Desktop integration

3. **Production Simulation**
   - Real-world data ingestion
   - Performance testing
   - Stress testing with large databases

**Deliverables:**
- Test suite for MCP server
- Integration test scripts
- Performance benchmarks

**Acceptance Criteria:**
- All tests passing
- No memory leaks
- Acceptable query latency (<5s)
- Multi-server stability verified

---

## Naming Conventions

### Transition from Athena to HybridRAG

**Current:** `athena-lightrag` (domain-specific, healthcare EHR focus)
**New:** `hybridrag` (generic, applicable to any domain)

### Naming Patterns

**MCP Server Names:**
```
{project}-{type}

Examples:
- specstory-kb
- internal-docs
- customer-support-kb
- api-reference
- legal-docs
```

**Database Directories:**
```
{project}_db

Examples:
- project1_db/
- specstory_db/
- books_db/
```

**MCP Server Configuration Keys:**
```
{project}-{type}

Examples in MCP config:
{
  "mcpServers": {
    "project1-kb": {...},
    "project2-kb": {...},
    "books-kb": {...}
  }
}
```

### Anti-Patterns (Avoid)

❌ Generic names: `database`, `kb`, `rag`, `server1`
❌ Numbers only: `db1`, `db2`, `db3`
❌ Unclear purpose: `test`, `misc`, `stuff`

✅ Descriptive names: `ecommerce-kb`, `legal-docs`, `customer-support-rag`

---

## Setup Scripts

### `setup_project.sh` Implementation

**Features (based on Gemini & FastMCP research):**

1. **Argument Validation**
   - Check folder exists
   - Validate project name format
   - Ensure hybridrag installed

2. **Database Creation**
   - Create isolated database directory
   - Run initial ingestion
   - Verify data ingested successfully

3. **MCP Config Generation**
   - Generate valid JSON snippet
   - Use absolute paths (FastMCP best practice)
   - Include environment variables
   - Support both Python and UV execution

4. **User Feedback**
   - Colored output (green=success, red=error)
   - Progress indicators
   - Summary of database info
   - Next steps guidance

**Research Insight from Gemini:**
> "Automated Setup: Use a script (e.g., `setup.sh`) to automate the setup process. This script can handle tasks such as copying environment files and adding API keys, running Docker Compose commands to start the services."

### `setup_all_projects.sh` Implementation

**Features:**

1. **Batch Processing**
   - Define projects in associative array
   - Loop through all projects
   - Handle errors gracefully

2. **Config Merging**
   - Combine all MCP snippets
   - Validate merged JSON
   - Create single config file

3. **Verification**
   - Check all databases created
   - Verify all configs valid
   - Test query on each database

---

## Docker Deployment

### Docker Compose Pattern (from Gemini Research)

**Key Findings:**

> "Docker Compose File (gordon-mcp.yml): This file configures MCP servers as Compose services. Gordon checks for this file to find MCP servers to use."

**Our Implementation:**

```yaml
version: '3.8'

services:
  project1-kb:
    build: ./hybridrag
    container_name: hybridrag-project1
    volumes:
      - ./databases/project1_db:/data:rw
      - ./project1/.specstory:/source:ro
    environment:
      - WORKING_DIR=/data
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    command: ["python", "hybridrag_mcp_server.py", "--working-dir", "/data", "--name", "project1"]
    restart: unless-stopped
```

**Research Insights:**

1. **Volume Mapping** - Separate data and source volumes (read-only source)
2. **Environment Variables** - Use `.env` file for secrets (Docker best practice)
3. **Restart Policy** - `unless-stopped` for production reliability
4. **Container Naming** - Descriptive names for easy management

### Dockerfile Optimization

**Research from Context7 Docker docs:**

```dockerfile
FROM python:3.11-slim

# Minimize layers
RUN apt-get update && apt-get install -y git \
    && rm -rf /var/lib/apt/lists/*

# Leverage build cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app last (changes most frequently)
COPY . .
```

---

## Testing Strategy

### Test Pyramid

```
              ┌─────────────┐
              │     E2E     │  ← Claude Desktop integration
              │   Tests     │
              └─────────────┘
            ┌─────────────────┐
            │   Integration   │  ← MCP protocol tests
            │     Tests       │
            └─────────────────┘
        ┌───────────────────────┐
        │     Unit Tests        │  ← Tool functions
        │                       │
        └───────────────────────┘
```

### Test Cases

**Unit Tests:**
- `test_local_query()` - Specific entity search
- `test_global_query()` - High-level overviews
- `test_hybrid_query()` - Balanced search
- `test_database_info()` - Metadata retrieval

**Integration Tests:**
- `test_mcp_server_startup()` - Server initialization
- `test_tool_discovery()` - MCP tool listing
- `test_tool_invocation()` - Query execution
- `test_multi_server_config()` - Multiple instances

**E2E Tests:**
- Manual Claude Desktop test
- Real-world query scenarios
- Performance benchmarks

---

## Documentation Deliverables

### Completed

- ✅ **USE_CASE_SCENARIOS.md** (5,500 words)
  - Scenario 1: Isolated databases
  - Scenario 2: Unified database
  - Scenario 3: MCP server setup
  - Docker deployment guide
  - Setup automation scripts
  - Naming conventions
  - FAQ & troubleshooting

- ✅ **MCP_SERVER_INTEGRATION.md** (4,200 words)
  - MCP architecture overview
  - Current state analysis
  - Creating the MCP server
  - Configuration guide
  - Deployment patterns
  - Testing & verification
  - Troubleshooting

- ✅ **IMPLEMENTATION_PLAN.md** (This document)

### To Be Created

**TROUBLESHOOTING.md:**
- Common errors and solutions
- Debug procedures
- Log analysis
- Performance tuning

**README.md Updates:**
- MCP server quickstart
- Link to documentation
- Installation guide

---

## Success Criteria

### Phase 1 Success (Core MCP Server)

- ✅ MCP server starts without errors
- ✅ All 4 tools discoverable via MCP protocol
- ✅ Queries return valid results
- ✅ Works with Claude Desktop
- ✅ Generic (no Athena-specific code)

### Phase 2 Success (Setup Automation)

- ✅ `setup_project.sh` creates working database
- ✅ MCP config snippets are valid JSON
- ✅ Batch setup processes multiple projects
- ✅ Error handling provides helpful messages

### Phase 3 Success (Docker Support)

- ✅ Docker images build successfully
- ✅ Containers run stably
- ✅ MCP servers accessible from host
- ✅ Volume persistence working

### Phase 4 Success (Documentation)

- ✅ All scenarios documented with examples
- ✅ Troubleshooting covers major issues
- ✅ Code has comprehensive docstrings
- ✅ README updated with MCP quickstart

### Phase 5 Success (Testing)

- ✅ Unit tests cover core functionality
- ✅ Integration tests validate MCP protocol
- ✅ E2E test with Claude Desktop passes
- ✅ Performance acceptable (<5s queries)

---

## Implementation Timeline

### Immediate (Phase 1) - 4-8 hours

**Priority:** Create working MCP server

1. Adapt `athena_mcp_server.py` → `hybridrag_mcp_server.py`
2. Remove Athena-specific code
3. Add CLI arguments
4. Test with MCP Inspector
5. Validate with Claude Desktop

### Short-term (Phase 2) - 2-4 hours

**Priority:** Automate setup process

1. Write `setup_project.sh`
2. Write `setup_all_projects.sh`
3. Test with real projects
4. Document usage

### Medium-term (Phase 3 & 4) - 7-12 hours

**Priority:** Production readiness

1. Create Dockerfile and docker-compose.yml
2. Write TROUBLESHOOTING.md
3. Update README.md
4. Complete code documentation

### Optional (Phase 5) - 2-4 hours

**Priority:** Validation & Quality

1. Write test suite
2. Performance testing
3. Bug fixes

---

## Research Credits

This implementation plan is based on comprehensive research from:

**Gemini Research (via gemini_mcp_server):**
- MCP server multi-instance setup patterns
- Docker Compose configurations for MCP
- Production deployment best practices
- Load balancing and failover patterns

**Context7 Documentation:**
- FastMCP (/jlowin/fastmcp) - MCP server configuration, environment variables, CLI patterns
- LightRAG (/hkuds/lightrag) - Database architecture, working_dir constraints, storage backends
- Docker Compose (/docker/compose) - Container orchestration patterns

---

## Next Actions

**Immediate Next Steps:**

1. **Review this plan** with stakeholders
2. **Begin Phase 1** - Create MCP server
3. **Test with single project** - Validate approach
4. **Iterate based on feedback**
5. **Proceed to Phase 2** - Automation

**Questions to Resolve:**

1. Proceed with adapting `athena_mcp_server.py` or build from scratch?
2. Priority: Setup scripts vs. Docker support?
3. Testing requirements: Unit tests mandatory or optional?

---

**Status:** ✅ Planning Complete - Ready for Implementation

**Created by:** Comprehensive research using Gemini AI and Context7 documentation

**Last Updated:** 2025-11-22
