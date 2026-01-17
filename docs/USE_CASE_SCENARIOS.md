# HybridRAG Use Case Scenarios

**Version:** 1.0.0
**Last Updated:** 2025-11-22
**Purpose:** Comprehensive guide for multi-project and multi-source HybridRAG setup patterns

---

## Table of Contents

1. [Overview](#overview)
2. [Scenario 1: Multiple Projects with Isolated Databases](#scenario-1-multiple-projects-with-isolated-databases)
3. [Scenario 2: Unified Knowledge Base](#scenario-2-unified-knowledge-base)
4. [Scenario 3: Multi-Project MCP Server Setup](#scenario-3-multi-project-mcp-server-setup)
5. [Advanced: Docker Compose Deployment](#advanced-docker-compose-deployment)
6. [Setup Automation Scripts](#setup-automation-scripts)
7. [Naming Conventions](#naming-conventions)
8. [FAQ & Troubleshooting](#faq--troubleshooting)

---

## Overview

HybridRAG is a knowledge graph-based RAG system combining **LightRAG** (knowledge graph + multi-hop reasoning) with **DeepLake** (vector storage). This guide covers real-world deployment scenarios for managing multiple knowledge bases.

### Key Capabilities

- ✅ **Multi-format ingestion:** Markdown, PDF, TXT, JSON, YAML, CSV, code files
- ✅ **Isolated databases:** Each project can have its own knowledge graph
- ✅ **Unified databases:** Combine multiple sources into one knowledge base
- ✅ **MCP Server ready:** Expose databases to Claude Desktop and other MCP clients
- ✅ **Incremental updates:** Re-ingest without duplicates using document ID tracking

### Architecture Constraint

**IMPORTANT:** LightRAG requires **one instance per database**. The `working_dir` parameter is set at initialization and cannot be changed at runtime. This means:

```
❌ Single MCP Server → Multiple Databases (NOT POSSIBLE)
✅ One MCP Server Instance = One Database (REQUIRED)
```

---

## Scenario 1: Multiple Projects with Isolated Databases

**Use Case:** You have 3 projects (each with a `.specstory` folder) and 1 PDF book. You want to keep each knowledge base separate and query them independently.

### Benefits

- Clean separation of concerns
- Update projects independently
- Best for project-specific queries
- No context contamination between projects

### Trade-offs

- Cannot search across all sources simultaneously
- Need to decide which database to query
- More management overhead

### Setup Steps

#### Step 1: Create Isolated Databases

```bash
# Project 1 Knowledge Base
python hybridrag.py \
    --working-dir ./databases/project1_db \
    ingest \
    --folder /path/to/project1/.specstory \
    --db-action fresh

# Project 2 Knowledge Base
python hybridrag.py \
    --working-dir ./databases/project2_db \
    ingest \
    --folder /path/to/project2/.specstory \
    --db-action fresh

# Project 3 Knowledge Base
python hybridrag.py \
    --working-dir ./databases/project3_db \
    ingest \
    --folder /path/to/project3/.specstory \
    --db-action fresh

# Book Knowledge Base
python hybridrag.py \
    --working-dir ./databases/book_db \
    ingest \
    --folder /path/to/books \
    --file-extensions .pdf \
    --db-action fresh
```

#### Step 2: Query Specific Database

```bash
# Query Project 1
python hybridrag.py \
    --working-dir ./databases/project1_db \
    query \
    --text "Find authentication patterns in this project"

# Interactive mode
python hybridrag.py \
    --working-dir ./databases/project2_db \
    interactive
```

#### Step 3: Database Management

```bash
# List all databases (run from each working_dir)
python hybridrag.py --working-dir ./databases/project1_db db-info
python hybridrag.py --working-dir ./databases/project2_db db-info

# Update specific database
python hybridrag.py \
    --working-dir ./databases/project1_db \
    ingest \
    --folder /path/to/project1/.specstory \
    --db-action add  # Incremental update
```

### Directory Structure

```
your-workspace/
├── databases/
│   ├── project1_db/
│   │   ├── vdb_chunks.json
│   │   ├── vdb_entities.json
│   │   ├── graph_chunk_entity_relation.graphml
│   │   └── ...
│   ├── project2_db/
│   ├── project3_db/
│   └── book_db/
└── hybridrag/  # Clone of hybridrag repository
```

---

## Scenario 2: Unified Knowledge Base

**Use Case:** You want all 3 projects + 1 PDF book in a single knowledge base to find connections and patterns across all sources.

### Benefits

- Cross-project insights automatically
- Single query searches everything
- Knowledge graph finds hidden connections
- Simpler management

### Trade-offs

- All documents mixed together
- Cannot isolate project-specific contexts
- Updates require careful db-action selection

### Setup Steps

#### Step 1: Create Unified Database

```bash
# Initialize with first source
python hybridrag.py ingest \
    --folder /path/to/project1/.specstory \
    --db-action fresh

# Add remaining sources incrementally
python hybridrag.py ingest \
    --folder /path/to/project2/.specstory \
    --db-action add

python hybridrag.py ingest \
    --folder /path/to/project3/.specstory \
    --db-action add

python hybridrag.py ingest \
    --folder /path/to/books \
    --file-extensions .pdf \
    --db-action add
```

#### Step 2: Query Unified Database

```bash
# Search across all sources
python hybridrag.py query \
    --text "How do all my projects handle authentication?" \
    --mode hybrid

# Interactive mode
python hybridrag.py interactive
```

#### Step 3: Verify Database Status

```bash
# Check database info
python hybridrag.py db-info

# Should show all 4 source folders
# Sample output:
# Database Metadata
# ================
# Working Directory: ./lightrag_db
# Ingestion Count: 4
# Total Documents: 342
# Source Folders:
#   - /path/to/project1/.specstory (152 documents)
#   - /path/to/project2/.specstory (98 documents)
#   - /path/to/project3/.specstory (75 documents)
#   - /path/to/books (17 documents)
```

### Directory Structure

```
your-workspace/
├── lightrag_db/  # Default working_dir
│   ├── vdb_chunks.json
│   ├── vdb_entities.json
│   ├── graph_chunk_entity_relation.graphml
│   ├── kv_store_full_docs.json
│   ├── kv_store_text_chunks.json
│   └── metadata.json  # Tracks all source folders
└── hybridrag/
```

---

## Scenario 3: Multi-Project MCP Server Setup

**Use Case:** Make all 4 knowledge bases (3 projects + 1 book) available to Claude Desktop as separate MCP servers.

### Architecture Overview

```
Claude Desktop (MCP Client)
    │
    ├─── project1-kb (MCP Server) → ./databases/project1_db
    ├─── project2-kb (MCP Server) → ./databases/project2_db
    ├─── project3-kb (MCP Server) → ./databases/project3_db
    └─── books-kb (MCP Server)    → ./databases/book_db
```

### Prerequisites

1. **HybridRAG MCP Server** must be created (see [MCP_SERVER_INTEGRATION.md](./MCP_SERVER_INTEGRATION.md))
2. Databases already ingested (from Scenario 1)
3. Claude Desktop installed

### MCP Configuration

**Location:** `~/.config/claude/claude_desktop_config.json` (macOS/Linux) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows)

```json
{
  "mcpServers": {
    "project1-kb": {
      "command": "python",
      "args": [
        "/home/user/hybridrag/hybridrag_mcp_server.py",
        "--working-dir",
        "/home/user/databases/project1_db"
      ],
      "env": {
        "OPENAI_API_KEY": "${OPENAI_API_KEY}",
        "OPENAI_API_BASE": "https://api.openai.com/v1"
      }
    },
    "project2-kb": {
      "command": "python",
      "args": [
        "/home/user/hybridrag/hybridrag_mcp_server.py",
        "--working-dir",
        "/home/user/databases/project2_db"
      ],
      "env": {
        "OPENAI_API_KEY": "${OPENAI_API_KEY}"
      }
    },
    "project3-kb": {
      "command": "python",
      "args": [
        "/home/user/hybridrag/hybridrag_mcp_server.py",
        "--working-dir",
        "/home/user/databases/project3_db"
      ],
      "env": {
        "OPENAI_API_KEY": "${OPENAI_API_KEY}"
      }
    },
    "books-kb": {
      "command": "python",
      "args": [
        "/home/user/hybridrag/hybridrag_mcp_server.py",
        "--working-dir",
        "/home/user/databases/book_db"
      ],
      "env": {
        "OPENAI_API_KEY": "${OPENAI_API_KEY}"
      }
    }
  }
}
```

### Using UV for Better Performance

**Recommended:** Use `uv` for faster startup and better dependency management:

```json
{
  "mcpServers": {
    "project1-kb": {
      "command": "uv",
      "args": [
        "run",
        "--with",
        "fastmcp",
        "--with",
        "lightrag-hku",
        "--with",
        "openai",
        "python",
        "/home/user/hybridrag/hybridrag_mcp_server.py",
        "--working-dir",
        "/home/user/databases/project1_db"
      ],
      "env": {
        "OPENAI_API_KEY": "${OPENAI_API_KEY}"
      }
    }
  }
}
```

### Restart Claude Desktop

After updating the configuration:

```bash
# macOS
pkill -9 "Claude"
open -a "Claude"

# Linux
pkill -9 claude
claude &

# Windows
taskkill /F /IM Claude.exe
start Claude
```

### Verify MCP Server Connection

In Claude Desktop, you should see:
- 4 new servers in the MCP servers list
- Tools from each server (namespaced by server name):
  - `project1-kb_lightrag_query_local`
  - `project1-kb_lightrag_query_global`
  - `project1-kb_lightrag_query_hybrid`
  - (Same tools for project2-kb, project3-kb, books-kb)

---

## Advanced: Docker Compose Deployment

**Use Case:** Production deployment with container isolation, reproducible environments, and easy scaling.

### Docker Compose Configuration

**File:** `docker-compose.yml`

```yaml
version: '3.8'

services:
  project1-kb:
    build:
      context: ./hybridrag
      dockerfile: Dockerfile
    container_name: hybridrag-project1
    volumes:
      - ./databases/project1_db:/data:rw
      - ./project1/.specstory:/source:ro
    environment:
      - WORKING_DIR=/data
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - OPENAI_API_BASE=${OPENAI_API_BASE:-https://api.openai.com/v1}
    command: ["python", "hybridrag_mcp_server.py", "--working-dir", "/data"]
    restart: unless-stopped
    networks:
      - hybridrag-net

  project2-kb:
    build:
      context: ./hybridrag
      dockerfile: Dockerfile
    container_name: hybridrag-project2
    volumes:
      - ./databases/project2_db:/data:rw
      - ./project2/.specstory:/source:ro
    environment:
      - WORKING_DIR=/data
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    command: ["python", "hybridrag_mcp_server.py", "--working-dir", "/data"]
    restart: unless-stopped
    networks:
      - hybridrag-net

  project3-kb:
    build:
      context: ./hybridrag
      dockerfile: Dockerfile
    container_name: hybridrag-project3
    volumes:
      - ./databases/project3_db:/data:rw
      - ./project3/.specstory:/source:ro
    environment:
      - WORKING_DIR=/data
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    command: ["python", "hybridrag_mcp_server.py", "--working-dir", "/data"]
    restart: unless-stopped
    networks:
      - hybridrag-net

  books-kb:
    build:
      context: ./hybridrag
      dockerfile: Dockerfile
    container_name: hybridrag-books
    volumes:
      - ./databases/book_db:/data:rw
      - ./books:/source:ro
    environment:
      - WORKING_DIR=/data
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    command: ["python", "hybridrag_mcp_server.py", "--working-dir", "/data"]
    restart: unless-stopped
    networks:
      - hybridrag-net

networks:
  hybridrag-net:
    driver: bridge
```

### Dockerfile

**File:** `hybridrag/Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory
RUN mkdir -p /data

EXPOSE 8000

# Default command (can be overridden)
CMD ["python", "hybridrag_mcp_server.py", "--working-dir", "/data"]
```

### Environment File

**File:** `.env`

```bash
OPENAI_API_KEY=sk-your-openai-api-key
OPENAI_API_BASE=https://api.openai.com/v1
```

### Docker Deployment Commands

```bash
# Build and start all services
docker compose up -d

# View logs
docker compose logs -f project1-kb

# Stop all services
docker compose down

# Rebuild after code changes
docker compose up -d --build

# Check service status
docker compose ps
```

### MCP Configuration for Docker

```json
{
  "mcpServers": {
    "project1-kb": {
      "command": "docker",
      "args": [
        "exec",
        "hybridrag-project1",
        "python",
        "hybridrag_mcp_server.py"
      ]
    }
  }
}
```

---

## Setup Automation Scripts

### Automated Project Setup Script

**File:** `setup_project.sh`

```bash
#!/bin/bash

# HybridRAG Project Setup Script
# Usage: ./setup_project.sh <folder_path> <project_name>

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Functions
print_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
print_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Arguments
FOLDER=$1
PROJECT_NAME=$2

# Validation
if [ -z "$FOLDER" ] || [ -z "$PROJECT_NAME" ]; then
    print_error "Usage: ./setup_project.sh <folder> <project_name>"
    echo ""
    echo "Examples:"
    echo "  ./setup_project.sh /path/to/project1/.specstory project1-kb"
    echo "  ./setup_project.sh ./docs/reports reports-kb"
    exit 1
fi

if [ ! -d "$FOLDER" ]; then
    print_error "Folder does not exist: $FOLDER"
    exit 1
fi

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HYBRIDRAG_DIR="$SCRIPT_DIR"
DB_DIR="./databases/${PROJECT_NAME}_db"
CONFIG_FILE="${PROJECT_NAME}_mcp_config.json"

print_info "Setting up HybridRAG for: $PROJECT_NAME"
print_info "Source folder: $FOLDER"
print_info "Database directory: $DB_DIR"

# Create database directory
print_info "Creating database directory..."
mkdir -p "$DB_DIR"

# Run ingestion
print_info "Starting ingestion process..."
python "$HYBRIDRAG_DIR/hybridrag.py" ingest \
    --folder "$FOLDER" \
    --working-dir "$DB_DIR" \
    --db-action fresh

if [ $? -ne 0 ]; then
    print_error "Ingestion failed!"
    exit 1
fi

print_info "Ingestion completed successfully"

# Generate MCP config snippet
print_info "Generating MCP configuration..."
cat > "$CONFIG_FILE" <<EOF
{
  "${PROJECT_NAME}": {
    "command": "python",
    "args": [
      "$(realpath "$HYBRIDRAG_DIR/hybridrag_mcp_server.py")",
      "--working-dir",
      "$(realpath "$DB_DIR")"
    ],
    "env": {
      "OPENAI_API_KEY": "\${OPENAI_API_KEY}"
    }
  }
}
EOF

# Summary
echo ""
print_info "✓ Setup completed successfully!"
echo ""
echo "Database Info:"
echo "  Directory: $DB_DIR"
python "$HYBRIDRAG_DIR/hybridrag.py" --working-dir "$DB_DIR" db-info | grep -E "Total Documents|Source Folders"
echo ""
print_info "MCP Configuration generated: $CONFIG_FILE"
echo ""
echo "Next steps:"
echo "  1. Review the generated config: cat $CONFIG_FILE"
echo "  2. Add to Claude Desktop config (~/.config/claude/claude_desktop_config.json):"
echo "     cat $CONFIG_FILE >> ~/.config/claude/claude_desktop_config.json"
echo "  3. Restart Claude Desktop"
echo ""
print_info "Query your database:"
echo "  python $HYBRIDRAG_DIR/hybridrag.py --working-dir $DB_DIR interactive"
```

### Batch Setup Script

**File:** `setup_all_projects.sh`

```bash
#!/bin/bash

# Setup multiple projects at once
# Usage: ./setup_all_projects.sh

set -e

# Project definitions
declare -A PROJECTS=(
    ["project1-kb"]="/path/to/project1/.specstory"
    ["project2-kb"]="/path/to/project2/.specstory"
    ["project3-kb"]="/path/to/project3/.specstory"
    ["books-kb"]="/path/to/books"
)

# Setup each project
for PROJECT_NAME in "${!PROJECTS[@]}"; do
    FOLDER="${PROJECTS[$PROJECT_NAME]}"
    echo "Setting up $PROJECT_NAME..."
    ./setup_project.sh "$FOLDER" "$PROJECT_NAME"
    echo ""
done

# Merge all configs
echo "Merging all MCP configurations..."
cat > all_projects_mcp_config.json <<EOF
{
  "mcpServers": {
EOF

# Add each project config
FIRST=true
for CONFIG_FILE in *_mcp_config.json; do
    if [ "$CONFIG_FILE" != "all_projects_mcp_config.json" ]; then
        if [ "$FIRST" = true ]; then
            FIRST=false
        else
            echo "," >> all_projects_mcp_config.json
        fi
        # Remove outer braces and add content
        sed '1d;$d' "$CONFIG_FILE" >> all_projects_mcp_config.json
    fi
done

cat >> all_projects_mcp_config.json <<EOF

  }
}
EOF

echo "✓ All projects setup complete!"
echo "✓ Combined config: all_projects_mcp_config.json"
```

---

## Naming Conventions

### Recommended Patterns

#### MCP Server Names

**Pattern:** `{project-name}-{type}`

**Examples:**
- `specstory-kb` - SpecStory knowledge base
- `internal-docs` - Internal documentation
- `customer-support-kb` - Customer support knowledge
- `api-reference` - API documentation
- `legal-docs` - Legal documentation

#### Database Directory Names

**Pattern:** `{project-name}_db`

**Examples:**
- `project1_db/`
- `specstory_db/`
- `books_db/`

#### Avoid Generic Names

❌ Bad:
- `database`
- `kb`
- `rag`
- `server1`

✅ Good:
- `ecommerce-kb`
- `medical-records-rag`
- `fintech-docs`

---

## FAQ & Troubleshooting

### Q: Can I switch databases in a single MCP server instance?

**A:** No. LightRAG's `working_dir` is set at initialization and cannot be changed at runtime. Each database requires its own MCP server process.

### Q: How do I search across multiple databases?

**A:** Currently not supported out-of-the-box. You have two options:
1. Use **Scenario 2** (Unified Database) to combine all sources
2. Future enhancement: HyperRAG federated layer (in development)

### Q: Can I update a database after initial ingestion?

**A:** Yes! Use `--db-action add` for incremental updates:

```bash
python hybridrag.py \
    --working-dir ./databases/project1_db \
    ingest \
    --folder /path/to/new/documents \
    --db-action add
```

### Q: What file formats are supported?

**A:**
- Documents: `.md`, `.txt`, `.pdf`
- Data: `.json`, `.yaml`, `.yml`, `.csv`
- Code: `.py`, `.js`, `.ts`, `.java`, `.go`, etc.

Use `--file-extensions` to filter:
```bash
--file-extensions .md .pdf .txt
```

### Q: How do I remove old documents?

**A:** Currently, you must re-ingest with `--db-action fresh` (destructive):

```bash
# WARNING: This deletes the entire database!
python hybridrag.py \
    --working-dir ./databases/project1_db \
    ingest \
    --folder /path/to/project1 \
    --db-action fresh
```

### Q: MCP server not appearing in Claude Desktop?

**Checklist:**
1. ✓ Verify config file location
2. ✓ Check JSON syntax (use `jq . < config.json`)
3. ✓ Ensure absolute paths (not relative)
4. ✓ Verify environment variables are set
5. ✓ Restart Claude Desktop completely
6. ✓ Check Claude Desktop logs

**Logs Location:**
- macOS: `~/Library/Logs/Claude/`
- Linux: `~/.local/share/claude/logs/`
- Windows: `%APPDATA%\Claude\logs\`

### Q: How do I monitor MCP server health?

**A:** Add health check endpoint to MCP server or use process monitoring:

```bash
# Check if server process is running
ps aux | grep hybridrag_mcp_server

# Monitor logs in real-time
tail -f /path/to/mcp_server.log
```

### Q: Can I use Docker and native setup simultaneously?

**A:** Yes! Docker and native setups are independent. You can have:
- Native MCP servers for development
- Docker containers for production

Just ensure different port mappings and database directories.

### Q: What's the recommended query mode?

**Query Modes:**

- `local` - Specific entity/relationship queries, fastest, most precise
- `global` - High-level overviews, comprehensive summaries
- `hybrid` - **Recommended default** - Balanced approach, best for general queries

```bash
# Recommended for most queries
python hybridrag.py query --text "..." --mode hybrid
```

---

## Next Steps

1. **Choose your scenario** (Isolated vs. Unified)
2. **Set up databases** using the CLI
3. **Configure MCP servers** (optional)
4. **Automate with scripts** for recurring tasks
5. **Monitor and maintain** your knowledge bases

For MCP server setup details, see [MCP_SERVER_INTEGRATION.md](./MCP_SERVER_INTEGRATION.md)

For troubleshooting, see [TROUBLESHOOTING.md](./TROUBLESHOOTING.md)

---

**Questions or issues?** Open an issue on GitHub or check the documentation.
