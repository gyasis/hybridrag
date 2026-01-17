# User Story: Shared PostgreSQL Deployment Pattern

## Overview

**As a** developer managing multiple HybridRAG instances with limited resources
**I want to** deploy multiple instances sharing a single PostgreSQL container
**So that** I can reduce resource usage while maintaining logical isolation between deployments

---

## When to Use This Pattern

✅ **Use shared PostgreSQL when:**
- You have 5-10+ deployments and resources are limited
- You want centralized PostgreSQL management and monitoring
- You need cross-deployment queries or analytics
- You want to minimize memory footprint (PostgreSQL ~512MB vs 512MB × N instances)
- You're comfortable with shared infrastructure patterns
- Database-level isolation is sufficient for your security needs

❌ **Don't use when:**
- You need complete independence between deployments
- You want zero shared failure points
- Resources are not a constraint
- You prefer simple, isolated management
- Different PostgreSQL versions/configurations needed per deployment

---

## Architecture

```
/home/user/Documents/code/
├── hybridrag/                        # Main project (source code)
│   ├── Dockerfile
│   └── hybridrag.py
│
├── hybridrag-shared-postgres/        # Shared PostgreSQL container
│   ├── docker-compose.yaml           # Single PostgreSQL container
│   └── data/
│       └── postgres/                 # Shared PostgreSQL data
│
├── hybridrag-azure-specstory/        # Deployment 1 (app only)
│   ├── docker-compose.yaml           # App only (no postgres)
│   ├── .env                          # Azure AI Foundry config
│   └── logs/
│
├── hybridrag-team-a/                 # Deployment 2 (app only)
│   ├── docker-compose.yaml           # App only (no postgres)
│   ├── .env                          # OpenAI config
│   └── logs/
│
└── hybridrag-personal-notes/         # Deployment 3 (app only)
    ├── docker-compose.yaml
    ├── .env
    └── logs/
```

**Key characteristics:**
- ONE PostgreSQL container serves multiple deployments
- Each deployment has its own database within PostgreSQL
- Apps connect via shared Docker network
- NO port exposure (internal Docker network only)
- Reduced memory footprint (1 PostgreSQL vs N PostgreSQL instances)

---

## Isolation Options

### Option 1: Database-Level Isolation (Recommended)

Each deployment gets its own database within PostgreSQL:

```
PostgreSQL Container (hybridrag-shared-postgres)
├── Database: azure_specstory
│   ├── LIGHTRAG_FULL_ENTITIES
│   ├── LIGHTRAG_FULL_RELATIONS
│   └── LIGHTRAG_VDB_*
│
├── Database: team_a
│   ├── LIGHTRAG_FULL_ENTITIES
│   ├── LIGHTRAG_FULL_RELATIONS
│   └── LIGHTRAG_VDB_*
│
└── Database: personal_notes
    └── (same table structure)
```

**Benefits:**
- Strong isolation (cannot query across databases without explicit connections)
- Each deployment has separate tables
- Easy backup/restore per deployment
- Clear separation for monitoring

### Option 2: Workspace-Level Isolation

All deployments use ONE database with workspace column separation:

```
PostgreSQL Container (hybridrag-shared-postgres)
└── Database: hybridrag_shared
    ├── LIGHTRAG_FULL_ENTITIES (workspace column: azure_specstory, team_a, personal_notes)
    ├── LIGHTRAG_FULL_RELATIONS (workspace column: azure_specstory, team_a, personal_notes)
    └── LIGHTRAG_VDB_* (workspace column filter)
```

**Benefits:**
- Lighter weight (one set of tables)
- Cross-deployment queries possible
- Simpler schema management
- LightRAG built-in workspace support

---

## Step-by-Step Setup

### Step 1: Build HybridRAG Image (One-Time)

```bash
cd /home/user/Documents/code/hybridrag
docker build -t hybridrag:latest .
```

### Step 2: Create Shared PostgreSQL Deployment

```bash
cd /home/user/Documents/code
mkdir hybridrag-shared-postgres
cd hybridrag-shared-postgres
```

Create `docker-compose.yaml`:

```yaml
version: '3.8'

services:
  postgres:
    image: pgvector/pgvector:pg16
    container_name: hybridrag-shared-postgres
    restart: unless-stopped

    environment:
      POSTGRES_USER: hybridrag
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      # No specific database - we'll create multiple
      POSTGRES_INITDB_ARGS: "--encoding=UTF8 --locale=en_US.UTF-8"

    # NO PORTS - Internal network only!

    volumes:
      - ./data/postgres:/var/lib/postgresql/data

    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U hybridrag"]
      interval: 10s
      timeout: 5s
      retries: 5

    networks:
      - hybridrag-shared-net

networks:
  hybridrag-shared-net:
    driver: bridge
    name: hybridrag-shared-network
```

Create `.env`:

```bash
# Shared PostgreSQL Configuration
POSTGRES_PASSWORD=shared_secure_password_2026
POSTGRES_USER=hybridrag
```

### Step 3: Start Shared PostgreSQL

```bash
cd hybridrag-shared-postgres
docker compose up -d

# Verify PostgreSQL is running
docker compose ps

# Verify NO port exposure
docker port hybridrag-shared-postgres
# Should return nothing (internal network only)
```

### Step 4: Create Databases (One-Time)

```bash
# Create database for each deployment
docker exec hybridrag-shared-postgres psql -U hybridrag -c "CREATE DATABASE azure_specstory;"
docker exec hybridrag-shared-postgres psql -U hybridrag -c "CREATE DATABASE team_a;"
docker exec hybridrag-shared-postgres psql -U hybridrag -c "CREATE DATABASE personal_notes;"

# Verify databases created
docker exec hybridrag-shared-postgres psql -U hybridrag -c "\l"
```

### Step 5: Create First App Deployment (Azure SpecStory)

```bash
cd /home/user/Documents/code
mkdir hybridrag-azure-specstory
cd hybridrag-azure-specstory
```

Create `docker-compose.yaml`:

```yaml
version: '3.8'

services:
  app:
    image: hybridrag:latest
    container_name: hybridrag-azure-specstory-app

    env_file:
      - .env

    environment:
      # Point to shared PostgreSQL container
      POSTGRES_HOST: hybridrag-shared-postgres
      POSTGRES_PORT: 5432

    volumes:
      - ${HOST_PROJECTS_PATH}:/data/projects:ro
      - ./data/lightrag_db:/app/lightrag_db
      - ./logs:/app/logs

    restart: unless-stopped

    # Join the shared network
    networks:
      - hybridrag-shared-net

    command: tail -f /dev/null

networks:
  hybridrag-shared-net:
    external: true
    name: hybridrag-shared-network
```

Create `.env`:

```bash
# Azure AI Foundry Configuration
AZURE_API_BASE=https://your-project.services.ai.azure.com/api/projects/your-project
AZURE_API_KEY=your-api-key-here
AZURE_API_VERSION=2024-02-15-preview

# Models
LLM_MODEL=gpt-4.1-mini
EMBEDDING_MODEL=text-embedding-3-small

# PostgreSQL (Shared)
POSTGRES_HOST=hybridrag-shared-postgres
POSTGRES_PORT=5432
POSTGRES_DB=azure_specstory          # ← Unique database name
POSTGRES_USER=hybridrag
POSTGRES_PASSWORD=shared_secure_password_2026
BACKEND_TYPE=postgres

# Workspace Isolation (Optional, Additional Layer)
LIGHTRAG_WORKSPACE=azure_specstory

# Paths
HOST_PROJECTS_PATH=/home/user/Documents/code
BATCH_SIZE=10
```

### Step 6: Start App and Initialize

```bash
cd hybridrag-azure-specstory
docker compose up -d

# Initialize database schema
docker compose exec app python hybridrag.py backend init --backend postgres

# Ingest data
docker compose exec app python hybridrag.py ingest \
  --path /data/projects \
  --recursive \
  --pattern "**/.specstory/.history/*.md" \
  --backend postgres
```

### Step 7: Create Additional Deployments

```bash
# Create second deployment
cd /home/user/Documents/code
mkdir hybridrag-team-a
cd hybridrag-team-a

# Copy docker-compose.yaml from azure-specstory
cp ../hybridrag-azure-specstory/docker-compose.yaml .

# Edit docker-compose.yaml
# - Change: container_name: hybridrag-team-a-app

# Create .env with different configuration
cat > .env << 'EOF'
# OpenAI Configuration (different from Azure)
OPENAI_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini
EMBEDDING_MODEL=text-embedding-3-small

# PostgreSQL (Shared)
POSTGRES_HOST=hybridrag-shared-postgres
POSTGRES_PORT=5432
POSTGRES_DB=team_a                   # ← Different database
POSTGRES_USER=hybridrag
POSTGRES_PASSWORD=shared_secure_password_2026
BACKEND_TYPE=postgres

# Workspace Isolation
LIGHTRAG_WORKSPACE=team_a

# Different source path
HOST_PROJECTS_PATH=/mnt/team-a-projects
EOF

# Start and initialize
docker compose up -d
docker compose exec app python hybridrag.py backend init --backend postgres
```

---

## Management

### Managing Shared PostgreSQL

```bash
cd hybridrag-shared-postgres

# View logs
docker compose logs -f

# Restart PostgreSQL
docker compose restart

# Stop PostgreSQL (stops all deployments!)
docker compose down

# Backup all databases
docker exec hybridrag-shared-postgres pg_dumpall -U hybridrag > backup-all.sql

# Backup specific database
docker exec hybridrag-shared-postgres pg_dump -U hybridrag -d azure_specstory > backup-azure.sql
```

### Managing Individual Deployments

```bash
cd hybridrag-azure-specstory

# View logs
docker compose logs -f

# Check status
docker compose exec app python hybridrag.py status

# Stop deployment (PostgreSQL keeps running)
docker compose down

# Restart deployment
docker compose restart
```

### Database Maintenance

```bash
# List all databases
docker exec hybridrag-shared-postgres psql -U hybridrag -c "\l"

# List connections per database
docker exec hybridrag-shared-postgres psql -U hybridrag -c "
  SELECT datname, count(*) as connections
  FROM pg_stat_activity
  GROUP BY datname;"

# Check database sizes
docker exec hybridrag-shared-postgres psql -U hybridrag -c "
  SELECT datname, pg_size_pretty(pg_database_size(datname)) as size
  FROM pg_database
  WHERE datname NOT IN ('postgres', 'template0', 'template1');"

# Vacuum specific database
docker exec hybridrag-shared-postgres psql -U hybridrag -d azure_specstory -c "VACUUM ANALYZE;"
```

---

## Benefits

### ✅ Resource Efficiency
- **Memory**: ~512MB-2GB total (vs 512MB × N for isolated)
- **Disk**: Shared PostgreSQL overhead
- **CPU**: Single PostgreSQL process handles all connections

### ✅ Centralized Management
- One PostgreSQL to monitor
- Unified backup/restore strategy
- Single upgrade path for PostgreSQL version
- Centralized performance tuning

### ✅ Cross-Deployment Capabilities
- Query across deployments (database-level isolation)
- Centralized analytics and reporting
- Shared monitoring dashboards

### ✅ Simplified Operations
- Start PostgreSQL once, all deployments connect
- Single point for database configuration
- Easier troubleshooting (one PostgreSQL log)

---

## Trade-offs

### ⚠️ Shared Failure Point
- If PostgreSQL fails, all deployments affected
- Requires careful capacity planning
- Connection pool management across deployments

### ⚠️ Security Considerations
- All deployments trust same PostgreSQL credentials
- Database-level isolation (not container-level)
- Requires careful permission management

### ⚠️ Resource Contention
- Deployments compete for PostgreSQL resources
- Heavy query on one deployment affects others
- Requires connection pooling configuration

---

## Resource Usage

**Shared PostgreSQL Pattern (3 deployments):**
- PostgreSQL: ~512MB-2GB RAM (shared)
- App 1: ~2GB-4GB RAM
- App 2: ~2GB-4GB RAM
- App 3: ~2GB-4GB RAM
- **Total**: ~6.5-14GB RAM

**Isolated Pattern (3 deployments):**
- Total: ~7.5-18GB RAM (3 × PostgreSQL overhead)

**Savings**: ~1-4GB RAM for 3 deployments

---

## Troubleshooting

### PostgreSQL connection errors from app

```bash
# Check app can reach PostgreSQL
docker exec hybridrag-azure-specstory-app ping -c 2 hybridrag-shared-postgres

# Check app is on shared network
docker inspect hybridrag-azure-specstory-app | grep NetworkMode

# Verify database exists
docker exec hybridrag-shared-postgres psql -U hybridrag -c "\l"
```

### Database does not exist

```bash
# Create missing database
docker exec hybridrag-shared-postgres psql -U hybridrag -c "CREATE DATABASE azure_specstory;"

# Re-initialize schema
cd hybridrag-azure-specstory
docker compose exec app python hybridrag.py backend init --backend postgres
```

### Too many connections

```bash
# Check connection count per database
docker exec hybridrag-shared-postgres psql -U hybridrag -c "
  SELECT datname, count(*)
  FROM pg_stat_activity
  GROUP BY datname;"

# Increase max_connections (if needed)
docker exec hybridrag-shared-postgres psql -U hybridrag -c "ALTER SYSTEM SET max_connections = 200;"
docker restart hybridrag-shared-postgres
```

### Performance issues

```bash
# Check slow queries
docker exec hybridrag-shared-postgres psql -U hybridrag -c "
  SELECT pid, datname, usename, state, query
  FROM pg_stat_activity
  WHERE state = 'active' AND query NOT LIKE '%pg_stat_activity%';"

# Check database sizes
docker exec hybridrag-shared-postgres psql -U hybridrag -c "
  SELECT datname, pg_size_pretty(pg_database_size(datname))
  FROM pg_database
  WHERE datname NOT IN ('postgres', 'template0', 'template1');"

# Run VACUUM on heavy databases
docker exec hybridrag-shared-postgres psql -U hybridrag -d azure_specstory -c "VACUUM ANALYZE;"
```

---

## Migration: Isolated → Shared

### Step 1: Backup Existing Data

```bash
# For each isolated deployment
cd hybridrag-azure-specstory
docker compose exec postgres pg_dump -U hybridrag -d hybridrag_specstory > backup-azure.sql
```

### Step 2: Set Up Shared PostgreSQL

Follow steps 2-4 in setup section.

### Step 3: Restore Data

```bash
# Create database in shared PostgreSQL
docker exec hybridrag-shared-postgres psql -U hybridrag -c "CREATE DATABASE azure_specstory;"

# Restore backup
cat backup-azure.sql | docker exec -i hybridrag-shared-postgres psql -U hybridrag -d azure_specstory
```

### Step 4: Update App Configuration

```bash
# Edit docker-compose.yaml
# - Remove postgres service
# - Change network to external: hybridrag-shared-network

# Edit .env
# - Change POSTGRES_HOST=hybridrag-shared-postgres
# - Change POSTGRES_DB=azure_specstory

# Restart app
docker compose down
docker compose up -d
```

### Step 5: Verify and Cleanup

```bash
# Test queries
docker compose exec app python hybridrag.py query --text "test" --mode hybrid

# If successful, remove old isolated PostgreSQL
cd hybridrag-azure-specstory
docker compose down -v  # Removes old postgres container and volume
```

---

## Example: Multi-Team Deployment

Real-world example with 4 teams sharing one PostgreSQL:

```bash
# Setup shared PostgreSQL
cd /home/user/Documents/code
mkdir hybridrag-shared-postgres
cd hybridrag-shared-postgres
# Create docker-compose.yaml and .env
docker compose up -d

# Create databases
docker exec hybridrag-shared-postgres psql -U hybridrag -c "CREATE DATABASE team_frontend;"
docker exec hybridrag-shared-postgres psql -U hybridrag -c "CREATE DATABASE team_backend;"
docker exec hybridrag-shared-postgres psql -U hybridrag -c "CREATE DATABASE team_mobile;"
docker exec hybridrag-shared-postgres psql -U hybridrag -c "CREATE DATABASE team_devops;"

# Deploy team instances
for team in frontend backend mobile devops; do
  cd /home/user/Documents/code
  mkdir hybridrag-team-${team}
  cd hybridrag-team-${team}

  # Create config pointing to shared PostgreSQL
  # POSTGRES_DB=team_${team}

  docker compose up -d
  docker compose exec app python hybridrag.py backend init --backend postgres
done

# All teams query their own data, PostgreSQL shared
```

---

## Monitoring

### Resource Usage Dashboard

```bash
# Create monitoring script
cat > monitor-shared.sh << 'EOF'
#!/bin/bash
echo "=== Shared PostgreSQL Resource Usage ==="
docker stats hybridrag-shared-postgres --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}"

echo -e "\n=== Database Sizes ==="
docker exec hybridrag-shared-postgres psql -U hybridrag -c "
  SELECT datname, pg_size_pretty(pg_database_size(datname)) as size
  FROM pg_database
  WHERE datname NOT IN ('postgres', 'template0', 'template1');"

echo -e "\n=== Active Connections ==="
docker exec hybridrag-shared-postgres psql -U hybridrag -c "
  SELECT datname, count(*) as connections
  FROM pg_stat_activity
  GROUP BY datname;"
EOF

chmod +x monitor-shared.sh
./monitor-shared.sh
```

---

## See Also

- [Isolated PostgreSQL Deployment Pattern](./isolated-postgres-deployment.md)
- [Multi-Project Deployment Guide](../deployment/MULTI_PROJECT_DEPLOYMENT.md)
- [MCP Server Integration](../MCP_SERVER_INTEGRATION.md)
