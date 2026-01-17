ye# Multi-Project HybridRAG Deployment Guide

Complete guide for deploying HybridRAG to process multiple project `.specstory` folders with selective path recursion.

## Table of Contents
1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Quick Start (30 Minutes)](#quick-start-30-minutes)
4. [Deployment Scenarios](#deployment-scenarios)
5. [Docker Deployment](#docker-deployment)
6. [Troubleshooting](#troubleshooting)

---

## Overview

This guide shows how to:
- Clone HybridRAG to a new environment
- Configure it to process ONLY `.specstory` folders from multiple projects
- Use either **unified database** (recommended) or **separate databases** per project
- Deploy with Docker (optional) for production environments

### Architecture Decision

**Unified Database Approach (Recommended)**
- ✅ Cross-project queries ("How did we solve auth in ANY project?")
- ✅ Simpler management (one database, one backup)
- ✅ Resource efficient (shared embeddings, deduplication)
- ✅ Perfect for project history correlation

**Separate Database Approach**
- ✅ Strict isolation (compliance, client data separation)
- ✅ Independent scaling per project
- ✅ Failure isolation

---

## Prerequisites

### System Requirements
- **Python**: 3.8+ (3.12 recommended)
- **Git**: For cloning repositories
- **Disk Space**: ~500MB for HybridRAG + ~100MB per project database
- **Memory**: 2GB minimum, 4GB+ recommended

### API Keys Required
- **OpenAI API Key**: For embeddings and LLM (required)
- **Anthropic API Key**: For advanced agentic features (optional)

### Installation Tools
Choose one:
- **Option A**: `pip` + `venv` (standard)
- **Option B**: `uv` (faster, recommended)
- **Option C**: Docker (production deployments)

---

## Quick Start (30 Minutes)

### Step 1: Clone HybridRAG (5 min)

```bash
# Clone to your deployment location
cd /path/to/deployment/location
git clone https://github.com/yourusername/hybridrag.git
cd hybridrag

# Verify clone
ls -la
# Should see: hybridrag.py, config/, docs/, etc.
```

### Step 2: Setup Environment (10 min)

**Option A: Using venv + pip**
```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install PromptChain (for agentic features)
pip install git+https://github.com/gyasis/PromptChain.git
```

**Option B: Using uv (faster)**
```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create environment and install dependencies
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
uv pip install git+https://github.com/gyasis/PromptChain.git
```

**Configure API Keys**
```bash
# Copy example env file
cp .env.example .env

# Edit .env and add your keys
nano .env
```

Add to `.env`:
```env
OPENAI_API_KEY=sk-your-key-here
ANTHROPIC_API_KEY=sk-ant-your-key-here  # Optional
```

### Step 3: Verify Installation (2 min)

```bash
# Test the installation
python hybridrag.py --help

# Should show:
# Usage: hybridrag.py [OPTIONS] COMMAND [ARGS]...
# ...

# Check database (should be empty)
python hybridrag.py check-db
```

### Step 4: Create Selective Ingestion Script (8 min)

Create `scripts/ingest_specstory_folders.sh`:

```bash
#!/bin/bash
#
# Selective .specstory folder ingestion script
# Finds and ingests ONLY .specstory folders from specified parent path
#

set -e  # Exit on error

# Configuration
PARENT_PATH="${1:-/home/gyasis/Documents/code}"  # Parent path to search
DB_ACTION="${2:-add}"  # 'fresh' or 'add' (default: add)
HYBRIDRAG_DIR="$(cd "$(dirname "$0")/.." && pwd)"  # Path to hybridrag.py
TEMP_FILE="/tmp/specstory_paths_$$.txt"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  HybridRAG Multi-Project Ingestion${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Validate parent path exists
if [ ! -d "$PARENT_PATH" ]; then
    echo -e "${RED}Error: Parent path does not exist: $PARENT_PATH${NC}"
    exit 1
fi

echo -e "${GREEN}Searching for .specstory folders in:${NC}"
echo -e "  ${PARENT_PATH}"
echo ""

# Find all .specstory folders
echo -e "${YELLOW}Scanning directory tree...${NC}"
find "$PARENT_PATH" -type d -name ".specstory" > "$TEMP_FILE"

# Count folders found
FOLDER_COUNT=$(wc -l < "$TEMP_FILE")

if [ "$FOLDER_COUNT" -eq 0 ]; then
    echo -e "${YELLOW}No .specstory folders found in $PARENT_PATH${NC}"
    rm -f "$TEMP_FILE"
    exit 0
fi

echo -e "${GREEN}Found ${FOLDER_COUNT} .specstory folder(s):${NC}"
echo ""

# Display found folders with parent project name
cat "$TEMP_FILE" | while IFS= read -r folder; do
    PROJECT_NAME=$(dirname "$folder" | xargs basename)
    echo -e "  ${BLUE}→${NC} $PROJECT_NAME ${YELLOW}(.specstory)${NC}"
    echo -e "    $folder"
done

echo ""
echo -e "${YELLOW}Database action: ${DB_ACTION}${NC}"
echo ""

# Confirm before proceeding
read -p "Proceed with ingestion? [y/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Ingestion cancelled.${NC}"
    rm -f "$TEMP_FILE"
    exit 0
fi

echo ""
echo -e "${GREEN}Starting ingestion...${NC}"
echo ""

# Process each folder
COUNTER=0
while IFS= read -r folder; do
    COUNTER=$((COUNTER + 1))
    PROJECT_NAME=$(dirname "$folder" | xargs basename)

    echo -e "${BLUE}[$COUNTER/$FOLDER_COUNT]${NC} Processing: ${YELLOW}$PROJECT_NAME${NC}"
    echo -e "  Path: $folder"

    # Ingest with metadata tagging
    if python "$HYBRIDRAG_DIR/hybridrag.py" ingest \
        --folder "$folder" \
        --db-action "$DB_ACTION" \
        --metadata "project=$PROJECT_NAME" 2>&1 | grep -v "^$"; then
        echo -e "  ${GREEN}✓ Success${NC}"
    else
        echo -e "  ${RED}✗ Failed${NC}"
    fi

    echo ""

    # Only use 'fresh' for first folder, then switch to 'add'
    if [ "$DB_ACTION" == "fresh" ]; then
        DB_ACTION="add"
    fi
done < "$TEMP_FILE"

# Cleanup
rm -f "$TEMP_FILE"

echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}Ingestion complete!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "Next steps:"
echo -e "  ${BLUE}1.${NC} Check database: ${YELLOW}python hybridrag.py check-db${NC}"
echo -e "  ${BLUE}2.${NC} Start querying: ${YELLOW}python hybridrag.py interactive${NC}"
echo ""
```

Make executable:
```bash
chmod +x scripts/ingest_specstory_folders.sh
```

### Step 5: Run Initial Ingestion (5 min)

```bash
# Ingest all .specstory folders from /home/gyasis/Documents/code
./scripts/ingest_specstory_folders.sh /home/gyasis/Documents/code fresh

# Example output:
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#   HybridRAG Multi-Project Ingestion
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# Found 3 .specstory folder(s):
#   → hybridrag (.specstory)
#     /home/gyasis/Documents/code/hybridrag/.specstory
#   → project-alpha (.specstory)
#     /home/gyasis/Documents/code/project-alpha/.specstory
#   → project-beta (.specstory)
#     /home/gyasis/Documents/code/project-beta/.specstory
#
# Proceed with ingestion? [y/N] y
```

### Step 6: Start Querying!

```bash
# Interactive mode (recommended)
python hybridrag.py interactive

# Try cross-project queries:
> How did we implement authentication across all projects?
> Show me all database migrations from project history
> What API patterns appear in our codebase?
```

**🎉 You're done! HybridRAG is now processing your multi-project .specstory folders.**

---

## Deployment Scenarios

### Scenario 1: Clone to New Server

If deploying to a remote server (e.g., AWS EC2, DigitalOcean):

```bash
# SSH into server
ssh user@your-server.com

# Clone HybridRAG
cd /opt  # or /home/user/apps
git clone https://github.com/yourusername/hybridrag.git
cd hybridrag

# Follow Quick Start steps 2-6 above
```

### Scenario 2: Multiple Teams/Departments

Create separate HybridRAG instances for isolation:

```bash
# Team A deployment
cd /opt/hybridrag-team-a
git clone https://github.com/yourusername/hybridrag.git .
./scripts/ingest_specstory_folders.sh /data/team-a-projects fresh

# Team B deployment
cd /opt/hybridrag-team-b
git clone https://github.com/yourusername/hybridrag.git .
./scripts/ingest_specstory_folders.sh /data/team-b-projects fresh
```

### Scenario 3: Shared Database Across Multiple Paths

Process multiple parent paths into one unified database:

```bash
# Ingest from multiple root paths
./scripts/ingest_specstory_folders.sh /home/gyasis/Documents/code fresh
./scripts/ingest_specstory_folders.sh /mnt/projects add
./scripts/ingest_specstory_folders.sh /external/repos add

# Now query across ALL paths
python hybridrag.py interactive
```

---

## Docker Deployment

For production environments, containerize HybridRAG:

### Step 1: Create Dockerfile

Create `Dockerfile` in project root:

```dockerfile
FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first (for caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install PromptChain
RUN pip install --no-cache-dir git+https://github.com/gyasis/PromptChain.git

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p lightrag_db ingestion_queue

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python hybridrag.py status || exit 1

# Default command
CMD ["python", "hybridrag.py", "interactive"]
```

### Step 2: Create docker-compose.yml

For multi-instance or production deployment:

```yaml
version: '3.8'

services:
  # Single instance deployment
  hybridrag:
    build: .
    container_name: hybridrag-main
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    volumes:
      # Mount .specstory folders (read-only)
      - /home/gyasis/Documents/code:/data/projects:ro
      # Persistent database
      - ./lightrag_db:/app/lightrag_db
      # Ingestion queue
      - ./ingestion_queue:/app/ingestion_queue
    restart: unless-stopped
    command: >
      bash -c "
        ./scripts/ingest_specstory_folders.sh /data/projects fresh &&
        python hybridrag.py interactive
      "

  # Multi-instance example (Team A)
  hybridrag-team-a:
    build: .
    container_name: hybridrag-team-a
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    volumes:
      - /data/team-a-projects:/data/projects:ro
      - ./team-a-db:/app/lightrag_db
    restart: unless-stopped

  # Multi-instance example (Team B)
  hybridrag-team-b:
    build: .
    container_name: hybridrag-team-b
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    volumes:
      - /data/team-b-projects:/data/projects:ro
      - ./team-b-db:/app/lightrag_db
    restart: unless-stopped
```

### Step 3: Deploy with Docker

```bash
# Build image
docker compose build

# Start services
docker compose up -d

# View logs
docker compose logs -f hybridrag

# Check status
docker compose exec hybridrag python hybridrag.py check-db

# Interactive shell
docker compose exec -it hybridrag bash
```

### Step 4: Production Configuration

Create `.env` for Docker:

```env
# .env file for docker-compose
OPENAI_API_KEY=sk-your-key-here
ANTHROPIC_API_KEY=sk-ant-your-key-here

# Resource limits (optional)
MEMORY_LIMIT=4g
CPU_LIMIT=2.0
```

Update `docker-compose.yml` with resource limits:

```yaml
services:
  hybridrag:
    # ... other config ...
    deploy:
      resources:
        limits:
          memory: ${MEMORY_LIMIT:-4g}
          cpus: '${CPU_LIMIT:-2.0}'
        reservations:
          memory: 2g
          cpus: '1.0'
```

---

## Advanced Configurations

### Cron-Based Periodic Ingestion

Auto-update database daily:

```bash
# Add to crontab
crontab -e

# Add this line (runs daily at 2 AM)
0 2 * * * cd /opt/hybridrag && ./scripts/ingest_specstory_folders.sh /data/projects add >> /var/log/hybridrag-cron.log 2>&1
```

### Separate Databases Per Project

If you need strict isolation:

Create `scripts/ingest_separate_databases.sh`:

```bash
#!/bin/bash
# Ingest each .specstory folder into its own database

PARENT_PATH="$1"
HYBRIDRAG_DIR="$(cd "$(dirname "$0")/.." && pwd)"

find "$PARENT_PATH" -type d -name ".specstory" | while IFS= read -r folder; do
    PROJECT_NAME=$(dirname "$folder" | xargs basename)
    DB_PATH="./lightrag_db_${PROJECT_NAME}"

    echo "Processing: $PROJECT_NAME → $DB_PATH"

    # Create separate database for this project
    LIGHTRAG_WORKING_DIR="$DB_PATH" \
        python "$HYBRIDRAG_DIR/hybridrag.py" ingest \
        --folder "$folder" \
        --db-action fresh
done

echo ""
echo "Created separate databases:"
ls -d ./lightrag_db_*
```

Query specific database:
```bash
# Query Team A's database only
LIGHTRAG_WORKING_DIR="./lightrag_db_team-a" python hybridrag.py interactive
```

### Nginx Load Balancer for Multi-Instance

If running multiple Docker instances, add nginx:

`nginx.conf`:
```nginx
upstream hybridrag_backends {
    server hybridrag-team-a:8000;
    server hybridrag-team-b:8000;
}

server {
    listen 80;

    location / {
        proxy_pass http://hybridrag_backends;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## Troubleshooting

### Issue: "No .specstory folders found"

**Cause**: Parent path doesn't contain `.specstory` subdirectories

**Solution**:
```bash
# Verify path exists
ls -la /home/gyasis/Documents/code

# Manually search for .specstory folders
find /home/gyasis/Documents/code -type d -name ".specstory"

# If empty, create test folder
mkdir -p /home/gyasis/Documents/code/test-project/.specstory
echo "Test content" > /home/gyasis/Documents/code/test-project/.specstory/test.md
```

### Issue: "OpenAI API Key not found"

**Cause**: `.env` file not loaded or missing

**Solution**:
```bash
# Check .env file exists
ls -la .env

# Verify key is set
grep OPENAI_API_KEY .env

# Test API key manually
python -c "import os; from dotenv import load_dotenv; load_dotenv(); print(os.getenv('OPENAI_API_KEY')[:10])"
```

### Issue: Docker container exits immediately

**Cause**: Command fails or API keys not passed

**Solution**:
```bash
# Check logs
docker compose logs hybridrag

# Run interactively to debug
docker compose run --rm hybridrag bash

# Verify env vars inside container
docker compose exec hybridrag env | grep API_KEY
```

### Issue: Out of memory during ingestion

**Cause**: Too many large files or insufficient memory

**Solution**:
```bash
# Reduce batch size in config/config.py
# Edit: batch_size = 5  (default is 10)

# Or skip large files
# Edit .env:
MAX_FILE_SIZE_MB=10

# Or increase Docker memory limit
# Edit docker-compose.yml:
deploy:
  resources:
    limits:
      memory: 8g
```

### Issue: Database corruption

**Cause**: Interrupted ingestion or disk full

**Solution**:
```bash
# Backup current database
cp -r lightrag_db lightrag_db.backup

# Start fresh
python hybridrag.py ingest --folder /path/to/.specstory --db-action fresh

# Or restore from backup
rm -rf lightrag_db
mv lightrag_db.backup lightrag_db
```

---

## Performance Optimization

### For Large Codebases (100+ projects)

1. **Use database partitioning**: Separate databases per team/department
2. **Increase chunk size**: Edit `config/config.py` → `chunk_size = 2000`
3. **Enable batch processing**: Edit `config/config.py` → `batch_size = 20`
4. **Use faster embeddings**: Switch to `text-embedding-3-small` (default)

### For Faster Queries

1. **Use local mode** for specific entity queries: `--mode local`
2. **Use hybrid mode** for balanced results: `--mode hybrid` (default)
3. **Enable reranking**: Already enabled by default in config
4. **Reduce top_k**: `--top-k 5` instead of default 10

---

## Next Steps

1. **Read Full Documentation**:
   - [USAGE.md](../guides/USAGE.md) - Complete usage guide
   - [DATABASE_MANAGEMENT.md](../guides/DATABASE_MANAGEMENT.md) - Database operations

2. **Explore Advanced Features**:
   - Agentic search with multi-hop reasoning
   - Custom document processors
   - API integration

3. **Set Up Monitoring**:
   - Configure log rotation
   - Set up alerting for errors
   - Monitor API usage and costs

4. **Production Hardening**:
   - Enable SSL/TLS for API endpoints
   - Implement authentication
   - Set up automated backups

---

## Summary

You now have HybridRAG deployed with:
- ✅ Selective `.specstory` folder ingestion
- ✅ Unified or separate database configurations
- ✅ Docker deployment option for production
- ✅ Cross-project query capabilities
- ✅ Automated ingestion scripts

**Total deployment time**: 30 minutes (manual) or 4-8 hours (Docker + production hardening)

**Questions?** Check [docs/](../) or open an issue on GitHub.
