# HybridRAG .specstory Deployment - Quick Start

**Goal**: Clone HybridRAG to a new location and process multiple projects' `.specstory` folders.

---

## ⚡ 30-Minute Setup

### 1. Clone HybridRAG (2 min)

```bash
# Clone to deployment location
git clone https://github.com/yourusername/hybridrag.git
cd hybridrag
```

### 2. Install Dependencies (5 min)

**Option A: Using pip**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install git+https://github.com/gyasis/PromptChain.git
```

**Option B: Using uv (faster)**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt
uv pip install git+https://github.com/gyasis/PromptChain.git
```

### 3. Configure API Keys (2 min)

```bash
cp .env.example .env
nano .env  # Add your OPENAI_API_KEY
```

### 4. Find & Ingest .specstory Folders (15 min)

```bash
# One command to find and ingest all .specstory folders
./scripts/ingest_specstory_folders.sh /home/gyasis/Documents/code fresh

# Output shows:
# Found 3 .specstory folder(s):
#   → hybridrag (.specstory)
#   → project-alpha (.specstory)
#   → project-beta (.specstory)
```

### 5. Start Querying! (1 min)

```bash
python hybridrag.py interactive

# Try:
> How did we implement authentication across all projects?
> Show me all API patterns from project history
```

**🎉 Done!** You now have a unified knowledge base across all your `.specstory` folders.

---

## 🔄 Auto-Watch for Changes

The `.specstory` folders change frequently (new history entries). Auto-monitor them:

### Option A: Manual Watch (Terminal)

```bash
# Start watcher (checks every 5 minutes)
./scripts/watch_specstory_folders.sh /home/gyasis/Documents/code 300

# Run in background
nohup ./scripts/watch_specstory_folders.sh /home/gyasis/Documents/code > watcher.log 2>&1 &
```

### Option B: Systemd Service (Production)

```bash
# Setup automatic startup on boot
sudo ./scripts/setup_systemd_watcher.sh /home/gyasis/Documents/code 300

# Check status
sudo systemctl status hybridrag-watcher

# View live logs
sudo journalctl -u hybridrag-watcher -f
```

### Option C: Cron Job (Scheduled)

```bash
# Add to crontab (runs every 5 minutes)
crontab -e

# Add this line:
*/5 * * * * cd /path/to/hybridrag && ./scripts/ingest_specstory_folders.sh /home/gyasis/Documents/code add >> /var/log/hybridrag-cron.log 2>&1
```

---

## 📦 Docker Deployment

For production or multi-environment setup:

### Build & Run

```bash
# Copy Docker env file
cp .env.docker.example .env

# Edit .env with your API keys and paths
nano .env

# Build and start
docker compose build
docker compose up -d

# View logs
docker compose logs -f hybridrag

# Enter container for interactive queries
docker compose exec hybridrag python hybridrag.py interactive
```

### Auto-Ingest on Container Start

Edit `docker-compose.yml`, change command to:

```yaml
command: >
  bash -c "
    ./scripts/ingest_specstory_folders.sh /data/projects fresh &&
    ./scripts/watch_specstory_folders.sh /data/projects 300
  "
```

---

## 🗂️ Database Architecture

### Unified Database (Default - Recommended)

✅ **Cross-project queries**: "Show auth patterns from ANY project"
✅ **Simpler management**: One database, one backup
✅ **Resource efficient**: Shared embeddings

```bash
# All .specstory folders → one database
./scripts/ingest_specstory_folders.sh /home/gyasis/Documents/code fresh

# Query across ALL projects
python hybridrag.py interactive
```

**Database location**: `./lightrag_db/`

### Separate Databases (Strict Isolation)

✅ **Per-project isolation**: Compliance, client separation
✅ **Independent scaling**: Different retention policies

```bash
# Create separate DB for each project
./scripts/ingest_separate_databases.sh /home/gyasis/Documents/code

# Creates:
#   lightrag_db_project1/
#   lightrag_db_project2/
#   lightrag_db_project3/

# Query specific project
LIGHTRAG_WORKING_DIR="./lightrag_db_project1" python hybridrag.py interactive
```

---

## 📝 Common Workflows

### Add New Project Path

```bash
# Add another parent directory to existing database
./scripts/ingest_specstory_folders.sh /mnt/external-projects add
```

### Check Database Status

```bash
python hybridrag.py check-db
python hybridrag.py status
```

### Query Modes

```bash
# Interactive (recommended)
python hybridrag.py interactive

# One-shot queries
python hybridrag.py query --text "your question" --mode hybrid

# Agentic multi-hop reasoning
python hybridrag.py query --text "complex question" --agentic
```

### Update Existing Data

```bash
# Re-ingest with changes (incremental)
./scripts/ingest_specstory_folders.sh /home/gyasis/Documents/code add

# Or start fresh
./scripts/ingest_specstory_folders.sh /home/gyasis/Documents/code fresh
```

---

## 🐛 Troubleshooting

### No .specstory folders found

```bash
# Verify folders exist
find /home/gyasis/Documents/code -type d -name ".specstory"

# If empty, check your path or create test folder
mkdir -p ~/Documents/code/test-project/.specstory
echo "Test content" > ~/Documents/code/test-project/.specstory/test.md
```

### API Key errors

```bash
# Check .env file
cat .env | grep OPENAI_API_KEY

# Test key is loaded
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print(os.getenv('OPENAI_API_KEY')[:10])"
```

### Docker container exits

```bash
# Check logs
docker compose logs hybridrag

# Run interactively to debug
docker compose run --rm hybridrag bash
```

### Watcher not detecting changes

```bash
# Check watcher is running
ps aux | grep watch_specstory

# Check logs
tail -f logs/watcher_*.log

# Manually trigger ingestion
./scripts/ingest_specstory_folders.sh /home/gyasis/Documents/code add
```

---

## 📚 Complete Documentation

- **[Full Deployment Guide](docs/deployment/MULTI_PROJECT_DEPLOYMENT.md)** - Comprehensive setup
- **[Usage Guide](docs/guides/USAGE.md)** - All commands and features
- **[Database Management](docs/guides/DATABASE_MANAGEMENT.md)** - DB operations
- **[Main README](README.md)** - Project overview

---

## 🎯 Architecture Summary

```
Parent Path: /home/gyasis/Documents/code/
│
├── project-alpha/
│   └── .specstory/              ← Monitored & ingested
│       ├── 2025-01-15.md
│       └── 2025-01-16.md
│
├── project-beta/
│   └── .specstory/              ← Monitored & ingested
│       └── history.md
│
└── project-gamma/
    └── .specstory/              ← Monitored & ingested
        ├── notes.md
        └── decisions.md

                ↓
         [Ingestion Script]
                ↓
    ┌─────────────────────────┐
    │   LightRAG Database     │  ← Unified knowledge graph
    │   (./lightrag_db/)      │
    └─────────────────────────┘
                ↓
      [Query Interface]
                ↓
    "How did we solve X across
     all projects?"
```

---

## ⚙️ Configuration Files

| File | Purpose |
|------|---------|
| `Dockerfile` | Container image definition |
| `docker-compose.yml` | Multi-instance orchestration |
| `.env.docker.example` | Docker environment template |
| `scripts/ingest_specstory_folders.sh` | One-time/manual ingestion |
| `scripts/ingest_separate_databases.sh` | Per-project isolation |
| `scripts/watch_specstory_folders.sh` | Continuous monitoring |
| `scripts/setup_systemd_watcher.sh` | Auto-start on boot |

---

## 🚀 Next Steps

1. ✅ Clone & setup (30 min)
2. ✅ Ingest .specstory folders
3. ✅ Start querying
4. 📊 Optional: Setup auto-watch for continuous updates
5. 🐳 Optional: Dockerize for production
6. 🔄 Optional: Setup systemd service for automatic monitoring

**Questions?** See [full documentation](docs/deployment/MULTI_PROJECT_DEPLOYMENT.md) or open an issue.
