# User Story: Isolated PostgreSQL Deployment Pattern

## Overview

**As a** developer needing multiple independent HybridRAG instances
**I want to** deploy each instance with its own isolated PostgreSQL container
**So that** I can manage, scale, and troubleshoot each deployment independently without conflicts

---

## When to Use This Pattern

✅ **Use isolated deployments when:**
- You want complete independence between deployments
- You need different configurations per instance (Azure AI Foundry, OpenAI, etc.)
- You want to delete one deployment without affecting others
- You're following the MCP server pattern (multiple instances, same codebase)
- Resources are not a constraint
- You need simple, straightforward management

❌ **Don't use when:**
- You have 10+ deployments and resources are limited
- You need cross-deployment queries
- You want centralized PostgreSQL management

---

## Architecture

```
/home/user/Documents/code/
├── hybridrag/                        # Main project (source code)
│   ├── Dockerfile
│   └── hybridrag.py
│
├── hybridrag-azure-specstory/        # Deployment 1 (isolated)
│   ├── docker-compose.yaml           # Defines postgres + app
│   ├── .env                          # Azure AI Foundry config
│   ├── data/
│   │   └── postgres/                 # Own PostgreSQL data
│   └── logs/
│
├── hybridrag-team-a/                 # Deployment 2 (isolated)
│   ├── docker-compose.yaml           # Defines postgres + app
│   ├── .env                          # OpenAI config
│   ├── data/
│   │   └── postgres/                 # Own PostgreSQL data
│   └── logs/
│
└── hybridrag-personal-notes/         # Deployment 3 (isolated)
    ├── docker-compose.yaml
    ├── .env
    └── data/
```

**Key characteristics:**
- Each deployment has its own PostgreSQL container
- NO port exposure (internal Docker network only)
- Unique container names prevent conflicts
- Independent Docker networks per deployment

---

## Step-by-Step Setup

### Step 1: Build HybridRAG Image (One-Time)

```bash
cd /home/user/Documents/code/hybridrag
docker build -t hybridrag:latest .
```

### Step 2: Create Deployment Folder

```bash
cd /home/user/Documents/code
mkdir hybridrag-azure-specstory
cd hybridrag-azure-specstory
```

### Step 3: Create `docker-compose.yaml`

```yaml
version: '3.8'

services:
  postgres:
    # CRITICAL: LightRAG requires BOTH Apache AGE + pgvector extensions
    # Base image: apache/age:latest (PostgreSQL 17 + AGE 1.6.0)
    # Must install pgvector separately in entrypoint
    image: apache/age:latest
    container_name: hybridrag-postgres-azure-specstory
    restart: unless-stopped

    environment:
      POSTGRES_USER: hybridrag
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: specstory
      POSTGRES_INITDB_ARGS: "--encoding=UTF8 --locale=en_US.UTF-8"

    # Install pgvector on first run
    entrypoint: >
      bash -c "apt-get update && apt-get install -y postgresql-17-pgvector && docker-entrypoint.sh postgres"

    # NO PORTS - Internal network only!

    volumes:
      - ./data/postgres:/var/lib/postgresql/data

    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U hybridrag"]
      interval: 10s
      timeout: 5s
      retries: 5

    networks:
      - hybridrag-net

  app:
    image: hybridrag:latest
    container_name: hybridrag-azure-specstory-app

    depends_on:
      postgres:
        condition: service_healthy

    env_file:
      - .env

    environment:
      POSTGRES_HOST: postgres
      POSTGRES_PORT: 5432

    volumes:
      - ${HOST_PROJECTS_PATH}:/data/projects:ro
      - ./data/lightrag_db:/app/lightrag_db
      - ./logs:/app/logs

    restart: unless-stopped

    networks:
      - hybridrag-net

    command: tail -f /dev/null

networks:
  hybridrag-net:
    driver: bridge
    name: hybridrag-azure-specstory-network
```

### Step 4: Create `.env`

```bash
# Azure AI Foundry Configuration
AZURE_API_BASE=https://your-project.services.ai.azure.com/api/projects/your-project
AZURE_API_KEY=your-api-key-here
AZURE_API_VERSION=2024-02-15-preview

# Models
LLM_MODEL=gpt-4.1-mini
EMBEDDING_MODEL=text-embedding-3-small

# PostgreSQL (Apache AGE backend - REQUIRED for graph storage)
POSTGRES_PASSWORD=secure_password_here
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=specstory
POSTGRES_USER=hybridrag
BACKEND_TYPE=postgres

# Paths
HOST_PROJECTS_PATH=/home/user/Documents/code
BATCH_SIZE=10
```

### Step 5: Create `.gitignore`

```bash
echo ".env" > .gitignore
echo "data/" >> .gitignore
echo "logs/" >> .gitignore
```

### Step 6: Start Deployment

```bash
docker compose up -d

# Verify containers running
docker compose ps

# Verify NO port exposure
docker port hybridrag-postgres-azure-specstory
# Should return nothing (internal network only)
```

### Step 7: Initialize Database

```bash
docker compose exec app python hybridrag.py backend init --backend postgres
```

### Step 8: Ingest Data

```bash
docker compose exec app python hybridrag.py ingest \
  --path /data/projects \
  --recursive \
  --pattern "**/.specstory/.history/*.md" \
  --backend postgres
```

### Step 9: Test Query

```bash
docker compose exec app python hybridrag.py query \
  --text "What are the main features?" \
  --mode hybrid
```

---

## Creating Additional Deployments

```bash
# Copy the structure
cp -r hybridrag-azure-specstory hybridrag-team-a

# Customize new deployment
cd hybridrag-team-a

# Edit docker-compose.yaml
# - Change: container_name: hybridrag-postgres-team-a
# - Change: container_name: hybridrag-team-a-app
# - Change: network name: hybridrag-team-a-network

# Edit .env
# - Change API keys, models, paths as needed
# - Change POSTGRES_PASSWORD

# Start independently
docker compose up -d
```

---

## Management

```bash
# View logs
docker compose logs -f

# Check status
docker compose exec app python hybridrag.py status

# Stop deployment
docker compose down

# Stop and remove all data
docker compose down -v

# Restart
docker compose restart
```

---

## Benefits

### ✅ Complete Isolation
- Each deployment is independent
- No shared failure points
- Delete one without affecting others

### ✅ No Port Conflicts
- PostgreSQL port 5432 NOT exposed to host
- Internal Docker network only
- Multiple deployments can coexist

### ✅ Simple Management
- One command to start everything
- Easy to understand architecture
- No coordination needed

### ✅ Flexible Configuration
- Different API providers per deployment
- Different models per deployment
- Different source paths per deployment

### ✅ MCP Server Pattern
- Each deployment like an MCP server
- Can expose as Claude Desktop MCP server
- Follows documented patterns

---

## Resource Usage

**Per Deployment:**
- PostgreSQL: ~512MB-2GB RAM
- App: ~2GB-4GB RAM
- Disk: ~100MB-1GB (depends on data)

**For 3 deployments:**
- Total RAM: ~6-12GB
- Total disk: ~300MB-3GB

---

## Troubleshooting

### Container won't start
```bash
# Check logs
docker compose logs

# Verify image exists
docker images | grep hybridrag

# Rebuild if needed
cd /home/user/Documents/code/hybridrag
docker build -t hybridrag:latest .
```

### PostgreSQL connection errors
```bash
# Check PostgreSQL health
docker compose exec postgres pg_isready -U hybridrag

# View logs
docker compose logs postgres
```

### Port conflicts
```bash
# Verify NO port exposure (should return nothing)
docker port hybridrag-postgres-azure-specstory

# If ports shown, check docker-compose.yaml has NO ports: section
```

---

## Example: Azure SpecStory Deployment

Real-world example ingesting `.specstory/.history` folders:

```bash
# Setup
cd /home/gyasis/Documents/code
mkdir hybridrag-azure-specstory
cd hybridrag-azure-specstory

# Create files (docker-compose.yaml, .env)
# ...

# Start
docker compose up -d

# Initialize
docker compose exec app python hybridrag.py backend init --backend postgres

# Ingest
docker compose exec app python hybridrag.py ingest \
  --path /data/projects \
  --recursive \
  --pattern "**/.specstory/.history/*.md" \
  --backend postgres

# Query
docker compose exec app python hybridrag.py interactive
```

---

## See Also

- [Shared PostgreSQL Deployment Pattern](./shared-postgres-deployment.md)
- [Multi-Project Deployment Guide](../deployment/MULTI_PROJECT_DEPLOYMENT.md)
- [MCP Server Integration](../MCP_SERVER_INTEGRATION.md)
