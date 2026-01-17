# HybridRAG MCP Server Integration Guide

**Version:** 1.0.0
**Last Updated:** 2025-11-22
**Purpose:** Complete guide for creating and configuring HybridRAG MCP servers

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Current State Analysis](#current-state-analysis)
4. [Creating the MCP Server](#creating-the-mcp-server)
5. [Configuration Guide](#configuration-guide)
6. [Deployment Patterns](#deployment-patterns)
7. [Testing & Verification](#testing--verification)
8. [Troubleshooting](#troubleshooting)

---

## Overview

This guide explains how to expose HybridRAG knowledge bases as **Model Context Protocol (MCP) servers**, making them accessible to Claude Desktop and other MCP-compatible clients.

### What is MCP?

**Model Context Protocol (MCP)** is a standardized protocol that allows AI models to access external tools, fetch data, and interact with services. Think of it as "USB-C for AI" - a universal interface for connecting LLMs to external resources.

### MCP Server Capabilities

When you expose HybridRAG as an MCP server, you gain:

- **Natural language querying** from Claude Desktop
- **Tool discovery** - LLMs can see available query modes
- **Stateless operation** - Each query is independent
- **Multi-client support** - Any MCP client can connect
- **Namespace isolation** - Multiple servers don't conflict

---

## Architecture

### Component Relationships

```
┌─────────────────────────────────────────────────────┐
│          Claude Desktop (MCP Client)                │
│  - Discovers MCP servers                            │
│  - Presents tools to user                           │
│  - Routes queries to appropriate server             │
└─────────────────────────────────────────────────────┘
                    │
                    │ MCP Protocol (stdio)
                    │
        ┌───────────┴───────────┬────────────────┐
        │                       │                │
┌───────▼─────────┐  ┌─────────▼──────┐  ┌─────▼─────────┐
│  project1-kb    │  │  project2-kb   │  │   books-kb    │
│  MCP Server     │  │  MCP Server    │  │  MCP Server   │
│                 │  │                │  │               │
│ Tools:          │  │ Tools:         │  │ Tools:        │
│ - local_query   │  │ - local_query  │  │ - local_query │
│ - global_query  │  │ - global_query │  │ - global_query│
│ - hybrid_query  │  │ - hybrid_query │  │ - hybrid_query│
└─────────────────┘  └────────────────┘  └───────────────┘
        │                    │                   │
        │                    │                   │
┌───────▼─────────┐  ┌───────▼──────┐  ┌────────▼──────┐
│  ./databases/   │  │ ./databases/ │  │ ./databases/  │
│  project1_db/   │  │ project2_db/ │  │  book_db/     │
│                 │  │              │  │               │
│  LightRAG       │  │  LightRAG    │  │  LightRAG     │
│  Database       │  │  Database    │  │  Database     │
└─────────────────┘  └──────────────┘  └───────────────┘
```

### Key Architectural Points

1. **One Server = One Database**: Each MCP server instance connects to exactly one LightRAG database (`working_dir`)
2. **Independent Processes**: Each server runs in its own process
3. **Namespace Prefix**: Tools are prefixed with server name (e.g., `project1-kb_local_query`)
4. **Stdio Transport**: Communication via standard input/output (stdin/stdout)

---

## Current State Analysis

### Existing Implementation

**Location:** `/home/gyasis/Documents/code/PromptChain/athena-lightrag/athena_mcp_server.py`

**Status:** ✅ Fully implemented MCP server exists

**Key Features:**
- Built with **FastMCP 2.0**
- Implements 6 query tools
- Configured for Athena Health EHR database (Snowflake-specific)
- Comprehensive documentation in `/docs`

### What Exists vs. What's Needed

| Component | Athena-LightRAG | HybridRAG | Action Required |
|-----------|-----------------|-----------|-----------------|
| MCP Server | ✅ Implemented | ❌ Missing | Adapt/refactor |
| LightRAG Core | ✅ Working | ✅ Working | None |
| Query Tools | ✅ 6 tools | ❌ Not exposed | Port tools |
| Configuration | Athena-specific | Generic needed | Refactor |
| Documentation | ✅ Excellent | ⚠️ Basic | This document |

### Gap Analysis

**What Needs to be Built:**

1. **Generic MCP Server** (`hybridrag_mcp_server.py`)
   - Remove Athena-specific references
   - Make `working_dir` configurable via CLI args
   - Support generic project naming
   - Simplify tool descriptions

2. **Configuration Templates**
   - Generic MCP config snippets
   - Environment variable documentation
   - Multi-instance setup examples

3. **Testing Framework**
   - MCP server health checks
   - Tool invocation tests
   - Multi-instance validation

---

## Creating the MCP Server

### Option 1: Adapt Existing Athena MCP Server

**Recommended for rapid deployment**

```bash
# Copy and adapt athena_mcp_server.py
cp /home/gyasis/Documents/code/PromptChain/athena-lightrag/athena_mcp_server.py \
   /home/gyasis/Documents/code/hybridrag/hybridrag_mcp_server.py

# Required modifications:
# 1. Remove Athena/Snowflake-specific references
# 2. Make working_dir a CLI argument
# 3. Genericize tool descriptions
# 4. Update server name to be configurable
```

### Option 2: Build from Scratch with FastMCP

**File:** `hybridrag/hybridrag_mcp_server.py`

```python
#!/usr/bin/env python3
"""
HybridRAG MCP Server
Exposes LightRAG knowledge base as MCP tools
"""

import asyncio
import argparse
import sys
from pathlib import Path
from typing import Optional

from fastmcp import FastMCP
from lightrag import LightRAG
from lightrag.llm.openai import gpt_4o_mini_complete, openai_embed

# Initialize FastMCP
mcp = FastMCP("HybridRAG Server")

# Global LightRAG instance
rag_instance: Optional[LightRAG] = None
project_name: str = "default"


def initialize_lightrag(working_dir: str, name: str = "default") -> LightRAG:
    """Initialize LightRAG instance with given working directory"""
    global rag_instance, project_name

    project_name = name

    rag_instance = LightRAG(
        working_dir=working_dir,
        llm_model_func=gpt_4o_mini_complete,
        embedding_func=openai_embed
    )

    return rag_instance


@mcp.tool()
async def lightrag_local_query(
    query: str,
    top_k: int = 60,
    max_entity_tokens: int = 6000
) -> dict:
    """
    Query the knowledge base for specific entity relationships and detailed information.

    Best for: Finding specific connections, detailed entity information, targeted searches.

    Args:
        query: Search query for specific entities or relationships
        top_k: Number of top entities to retrieve (default: 60)
        max_entity_tokens: Maximum tokens for entity context (default: 6000)

    Returns:
        Query results with relevant entities and relationships
    """
    if not rag_instance:
        return {"error": "LightRAG not initialized"}

    try:
        result = await rag_instance.aquery(
            query,
            param={
                "mode": "local",
                "top_k": top_k,
                "max_token_for_text_unit": max_entity_tokens
            }
        )

        return {
            "success": True,
            "mode": "local",
            "query": query,
            "result": result,
            "project": project_name
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "query": query
        }


@mcp.tool()
async def lightrag_global_query(
    query: str,
    top_k: int = 60,
    max_relation_tokens: int = 8000
) -> dict:
    """
    Get high-level overviews and comprehensive summaries from the knowledge base.

    Best for: Broad questions, discovering patterns, understanding overall structure.

    Args:
        query: Search query for high-level overviews
        top_k: Number of top relationships to retrieve (default: 60)
        max_relation_tokens: Maximum tokens for relationship context (default: 8000)

    Returns:
        Query results with broad patterns and relationships
    """
    if not rag_instance:
        return {"error": "LightRAG not initialized"}

    try:
        result = await rag_instance.aquery(
            query,
            param={
                "mode": "global",
                "top_k": top_k,
                "max_token_for_global_context": max_relation_tokens
            }
        )

        return {
            "success": True,
            "mode": "global",
            "query": query,
            "result": result,
            "project": project_name
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "query": query
        }


@mcp.tool()
async def lightrag_hybrid_query(
    query: str,
    top_k: int = 60,
    max_entity_tokens: int = 6000,
    max_relation_tokens: int = 8000
) -> dict:
    """
    Balanced search combining specific details with broader context.

    Best for: General queries, balanced exploration, most use cases.
    This is the RECOMMENDED default mode.

    Args:
        query: Search query combining specific and broad context
        top_k: Number of top items to retrieve (default: 60)
        max_entity_tokens: Maximum tokens for entity details (default: 6000)
        max_relation_tokens: Maximum tokens for relationships (default: 8000)

    Returns:
        Query results with balanced entity and relationship information
    """
    if not rag_instance:
        return {"error": "LightRAG not initialized"}

    try:
        result = await rag_instance.aquery(
            query,
            param={
                "mode": "hybrid",
                "top_k": top_k,
                "max_token_for_text_unit": max_entity_tokens,
                "max_token_for_global_context": max_relation_tokens
            }
        )

        return {
            "success": True,
            "mode": "hybrid",
            "query": query,
            "result": result,
            "project": project_name
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "query": query
        }


@mcp.tool()
async def get_database_info() -> dict:
    """
    Get information about the current LightRAG database.

    Returns:
        Database metadata including working directory, project name, and status
    """
    if not rag_instance:
        return {"error": "LightRAG not initialized"}

    try:
        # Read metadata if available
        working_dir = Path(rag_instance.working_dir)
        metadata_file = working_dir / "metadata.json"

        info = {
            "success": True,
            "working_dir": str(working_dir),
            "project_name": project_name,
            "metadata_exists": metadata_file.exists()
        }

        if metadata_file.exists():
            import json
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
                info["metadata"] = metadata

        return info
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def main():
    """Main entry point for MCP server"""
    parser = argparse.ArgumentParser(description="HybridRAG MCP Server")
    parser.add_argument(
        "--working-dir",
        type=str,
        required=True,
        help="Path to LightRAG working directory (database)"
    )
    parser.add_argument(
        "--name",
        type=str,
        default="default",
        help="Project name for this knowledge base"
    )

    args = parser.parse_args()

    # Validate working directory
    working_dir = Path(args.working_dir)
    if not working_dir.exists():
        print(f"Error: Working directory does not exist: {working_dir}", file=sys.stderr)
        sys.exit(1)

    # Initialize LightRAG
    print(f"Initializing HybridRAG MCP Server...", file=sys.stderr)
    print(f"  Working Directory: {working_dir}", file=sys.stderr)
    print(f"  Project Name: {args.name}", file=sys.stderr)

    initialize_lightrag(str(working_dir), args.name)

    print(f"✓ LightRAG initialized successfully", file=sys.stderr)
    print(f"✓ Starting MCP server...", file=sys.stderr)

    # Run MCP server
    mcp.run()


if __name__ == "__main__":
    main()
```

### Dependencies

**File:** `hybridrag/requirements-mcp.txt`

```txt
fastmcp>=2.0.0
lightrag-hku>=0.0.0.6
openai>=1.0.0
pydantic>=2.0.0
```

---

## Configuration Guide

### Environment Variables

**Required:**

- `OPENAI_API_KEY` - OpenAI API key for LLM and embeddings
- `OPENAI_API_BASE` - (Optional) Custom OpenAI endpoint

**Optional:**

- `LIGHTRAG_LOG_LEVEL` - Logging level (DEBUG, INFO, WARNING, ERROR)
- `LIGHTRAG_TIMEOUT` - Query timeout in seconds (default: 300)

### Claude Desktop Configuration

**Location:**
- macOS/Linux: `~/.config/claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

**Single Server Example:**

```json
{
  "mcpServers": {
    "my-project-kb": {
      "command": "python",
      "args": [
        "/absolute/path/to/hybridrag/hybridrag_mcp_server.py",
        "--working-dir",
        "/absolute/path/to/databases/project_db",
        "--name",
        "my-project"
      ],
      "env": {
        "OPENAI_API_KEY": "sk-your-api-key-here"
      }
    }
  }
}
```

**Multi-Server Example:**

```json
{
  "mcpServers": {
    "project1-kb": {
      "command": "python",
      "args": [
        "/home/user/hybridrag/hybridrag_mcp_server.py",
        "--working-dir",
        "/home/user/databases/project1_db",
        "--name",
        "project1"
      ],
      "env": {
        "OPENAI_API_KEY": "${OPENAI_API_KEY}"
      }
    },
    "project2-kb": {
      "command": "python",
      "args": [
        "/home/user/hybridrag/hybridrag_mcp_server.py",
        "--working-dir",
        "/home/user/databases/project2_db",
        "--name",
        "project2"
      ],
      "env": {
        "OPENAI_API_KEY": "${OPENAI_API_KEY}"
      }
    }
  }
}
```

### Using UV for Better Performance

```json
{
  "mcpServers": {
    "my-project-kb": {
      "command": "uv",
      "args": [
        "run",
        "--with", "fastmcp",
        "--with", "lightrag-hku",
        "--with", "openai",
        "python",
        "/path/to/hybridrag_mcp_server.py",
        "--working-dir", "/path/to/database",
        "--name", "my-project"
      ],
      "env": {
        "OPENAI_API_KEY": "${OPENAI_API_KEY}"
      }
    }
  }
}
```

---

## Deployment Patterns

### Pattern 1: Development (Direct Python)

**Best for:** Local development, quick testing

```bash
# Terminal 1: Start MCP server
python hybridrag_mcp_server.py \
    --working-dir ./databases/project1_db \
    --name project1

# Terminal 2: Test with MCP client
# Or configure in Claude Desktop
```

**Pros:**
- Fast iteration
- Easy debugging
- Direct log access

**Cons:**
- Manual process management
- No automatic restart
- Environment management

### Pattern 2: Production (UV + systemd)

**Best for:** Linux servers, always-on services

**File:** `/etc/systemd/system/hybridrag-project1.service`

```ini
[Unit]
Description=HybridRAG MCP Server - Project 1
After=network.target

[Service]
Type=simple
User=hybridrag
WorkingDirectory=/home/hybridrag/hybridrag
Environment="OPENAI_API_KEY=sk-your-key"
ExecStart=/usr/local/bin/uv run \
    --with fastmcp \
    --with lightrag-hku \
    python /home/hybridrag/hybridrag/hybridrag_mcp_server.py \
    --working-dir /home/hybridrag/databases/project1_db \
    --name project1
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Commands:**

```bash
# Enable and start service
sudo systemctl enable hybridrag-project1
sudo systemctl start hybridrag-project1

# Check status
sudo systemctl status hybridrag-project1

# View logs
sudo journalctl -u hybridrag-project1 -f
```

### Pattern 3: Docker Deployment

See [USE_CASE_SCENARIOS.md - Docker Compose Deployment](./USE_CASE_SCENARIOS.md#advanced-docker-compose-deployment)

---

## Testing & Verification

### Manual Testing

```bash
# 1. Start MCP server
python hybridrag_mcp_server.py \
    --working-dir ./databases/test_db \
    --name test-project

# Expected stderr output:
# Initializing HybridRAG MCP Server...
#   Working Directory: ./databases/test_db
#   Project Name: test-project
# ✓ LightRAG initialized successfully
# ✓ Starting MCP server...
```

### Using MCP Inspector

```bash
# Install MCP Inspector
npm install -g @modelcontextprotocol/inspector

# Test server
npx @modelcontextprotocol/inspector \
    python hybridrag_mcp_server.py \
    --working-dir ./databases/project1_db
```

### Automated Test Script

**File:** `test_mcp_server.py`

```python
"""Test HybridRAG MCP Server"""

import asyncio
import subprocess
import json
from pathlib import Path

async def test_mcp_server():
    """Test MCP server tool discovery and invocation"""

    # Start MCP server
    proc = subprocess.Popen(
        [
            "python", "hybridrag_mcp_server.py",
            "--working-dir", "./databases/test_db",
            "--name", "test"
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    try:
        # Send list_tools request
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "list_tools",
            "params": {}
        }

        proc.stdin.write(json.dumps(request) + "\n")
        proc.stdin.flush()

        # Read response
        response = proc.stdout.readline()
        data = json.loads(response)

        print("Available tools:")
        for tool in data.get("result", {}).get("tools", []):
            print(f"  - {tool['name']}")

        assert len(data.get("result", {}).get("tools", [])) == 4
        print("\n✓ All 4 tools discovered")

    finally:
        proc.terminate()
        proc.wait()

if __name__ == "__main__":
    asyncio.run(test_mcp_server())
```

---

## Troubleshooting

### Server Not Starting

**Symptom:** MCP server doesn't appear in Claude Desktop

**Checks:**
1. Validate JSON syntax: `jq . < claude_desktop_config.json`
2. Check absolute paths (not relative)
3. Verify working directory exists
4. Ensure OPENAI_API_KEY is set
5. Check Claude Desktop logs

**Logs Location:**
- macOS: `~/Library/Logs/Claude/mcp*.log`
- Linux: `~/.local/share/claude/logs/`
- Windows: `%APPDATA%\Claude\logs\`

### Tools Not Discovered

**Symptom:** Server starts but no tools visible

**Debug:**

```bash
# Check stderr output
python hybridrag_mcp_server.py \
    --working-dir ./databases/test_db \
    2>&1 | grep -i error

# Test with MCP Inspector
npx @modelcontextprotocol/inspector \
    python hybridrag_mcp_server.py \
    --working-dir ./databases/test_db
```

### Query Errors

**Symptom:** Tool invocation fails

**Common Causes:**
1. LightRAG not initialized
2. Working directory empty (no ingested data)
3. OpenAI API key invalid
4. Network issues

**Fix:**

```bash
# Verify database has data
python hybridrag.py --working-dir ./databases/test_db db-info

# Test query directly
python hybridrag.py \
    --working-dir ./databases/test_db \
    query --text "test query"
```

### Multiple Servers Conflict

**Symptom:** Only one server works

**Solution:** Ensure unique server names in config:

```json
{
  "mcpServers": {
    "unique-name-1": {...},
    "unique-name-2": {...}  // ← Must be different
  }
}
```

---

## Next Steps

1. **Create MCP Server** - Implement `hybridrag_mcp_server.py`
2. **Test Locally** - Verify server starts and tools work
3. **Configure Claude Desktop** - Add to MCP config
4. **Deploy to Production** - Choose deployment pattern
5. **Monitor & Maintain** - Set up logging and health checks

---

**Related Documentation:**
- [USE_CASE_SCENARIOS.md](./USE_CASE_SCENARIOS.md) - Multi-project setup patterns
- [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) - Comprehensive troubleshooting

**Questions?** Open an issue or check the FAQ.
