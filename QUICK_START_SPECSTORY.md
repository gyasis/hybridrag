# HybridRAG .specstory Deployment - Quick Start

**Goal**: Clone HybridRAG to a new location and process multiple projects' `.specstory` folders.

---

## 🎯 Two Ingestion Scripts

| Script | Use Case |
|--------|----------|
| `ingest_specstory_folders.sh` | **SpecStory ONLY** - auto-finds `.specstory` folders |
| `ingest_recursive.sh` | **Generic** - any folder patterns, file types, file names |

---

## 📁 SpecStory Workflow (Recommended)

Point to your **top-level dev folder** and let the script recursively find all `.specstory` folders:

```bash
# Your folder structure:
# /home/user/dev/
# ├── project-alpha/.specstory/history/*.md
# ├── project-beta/.specstory/history/*.md
# ├── jira-issues/
# │   ├── TIC-123/.specstory/history/*.md
# │   └── TIC-456/.specstory/history/*.md
# └── research/.specstory/history/*.md

# One command finds ALL .specstory folders recursively:
./scripts/ingest_specstory_folders.sh /home/user/dev fresh
```

**What happens:**
1. Recursively searches `/home/user/dev` for ALL `.specstory` folders
2. Auto-tags each with `project=<folder-name>` metadata
3. Ingests all files from each `.specstory` folder
4. Creates unified searchable knowledge base

---

## 🔧 Generic Recursive Workflow

For more control over what gets ingested:

```bash
# Find specific folder patterns
./scripts/ingest_recursive.sh /home/user/dev fresh \
    --folders ".specstory,docs,.memory"

# Find only .md files (anywhere)
./scripts/ingest_recursive.sh /home/user/dev fresh \
    --files "*.md"

# Find .md files ONLY in .specstory/history folders
./scripts/ingest_recursive.sh /home/user/dev fresh \
    --folders "history" \
    --exclude "node_modules,.git,.venv"

# Combine: specific folders + file types + custom tag
./scripts/ingest_recursive.sh /home/user/dev fresh \
    --folders ".specstory" \
    --files "*.md" \
    --tag "conversation-history"
```

---

## 🔄 Multi-Location Database Building

### Add folders from different locations:
```bash
# First location - creates NEW database
./scripts/ingest_specstory_folders.sh /home/user/dev fresh

# Second location - ADDS to same database
./scripts/ingest_specstory_folders.sh /home/user/work add

# Third location - ADDS more
./scripts/ingest_recursive.sh /mnt/external/projects add \
    --folders ".specstory,docs" \
    --tag "external"
```

### Add another folder weeks later:
```bash
# Always use 'add' to preserve existing data
./scripts/ingest_specstory_folders.sh /home/user/new-project add
```

| Action | What It Does |
|--------|--------------|
| `fresh` | **Wipes database**, starts new |
| `add` | **Appends** to existing database |

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
nano .env  # Add your AZURE_API_KEY (preferred) or OPENAI_API_KEY
```

**Supported Providers** (via LiteLLM):
- `AZURE_API_KEY` - Azure OpenAI (default)
- `OPENAI_API_KEY` - OpenAI
- `ANTHROPIC_API_KEY` - Anthropic Claude
- `GEMINI_API_KEY` - Google Gemini

### 4. Find & Ingest .specstory Folders (15 min)

```bash
# One command to find and ingest all .specstory folders
./scripts/ingest_specstory_folders.sh /home/gyasis/Documents/code fresh

# Output shows:
# Found 3 .specstory folder(s):
#   → hybridrag (.specstory)
#   → project-alpha (.specstory)
#   → project-beta (.specstory)
#
# Progress bar: Ingesting files: 45%|████████    | 25/56 [01:23<01:42]
```

**Features:**
- ✅ tqdm progress bar during ingestion
- ✅ Queue-based architecture (restartable on failure)
- ✅ Automatic metadata tagging per project

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
python hybridrag.py check-db      # Quick database check
python hybridrag.py db-info       # Detailed info with source folders
python hybridrag.py list-dbs      # List all databases in directory
python hybridrag.py status        # System status
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

### Advanced Ingestion (Direct CLI)

For fine-grained control, use the CLI directly:

```bash
# With custom metadata
python hybridrag.py ingest --folder ./my-project/.specstory \
    --db-action add \
    --metadata "project=myproject" \
    --metadata "version=2.0"

# Scripted (no prompts, quiet output)
python hybridrag.py ingest --folder ./data --db-action fresh --yes --quiet
```

| Flag | Description |
|------|-------------|
| `--metadata KEY=VALUE` | Add custom metadata (can use multiple times) |
| `--yes`, `-y` | Skip confirmation prompts |
| `--quiet`, `-q` | Suppress verbose output, show only progress bar |

---

## 📂 SpecStory Scripts vs Regular Folder Ingestion

HybridRAG can ingest **any folder**, not just `.specstory` folders. Here's when to use each approach:

### SpecStory Scripts (This Guide)

Use the shell scripts when processing **Claude Code / SpecStory conversation history**:

```bash
# Auto-discovers ALL .specstory folders recursively
./scripts/ingest_specstory_folders.sh /path/to/projects fresh
```

**Benefits:**
- ✅ Auto-discovers `.specstory` folders across many projects
- ✅ Auto-adds metadata (`project=name`, `source_path=...`)
- ✅ Watcher script for continuous monitoring
- ✅ One command for multi-project ingestion

### Regular Folder Ingestion

Use the CLI directly when processing **any other documents** (PDFs, markdown, code, etc.):

```bash
# Ingest any folder directly
python hybridrag.py ingest --folder /path/to/my/documents

# Multiple folders
python hybridrag.py ingest --folder ./docs --folder ./notes

# With custom metadata
python hybridrag.py ingest --folder ./project-docs \
    --metadata "project=myproject" \
    --metadata "team=engineering" \
    --db-action add
```

**Use cases:**
- 📄 Documentation folders
- 📚 Research papers / PDFs
- 💻 Code repositories
- 📝 Meeting notes, wikis

### Comparison Table

| Feature | SpecStory Scripts | Regular `--folder` |
|---------|-------------------|-------------------|
| **Auto-discover** | Finds all `.specstory` recursively | You specify exact folder(s) |
| **Auto-metadata** | Adds project name & path | You add metadata manually |
| **Multi-project** | Handles many at once | One command per folder |
| **Watcher** | `watch_specstory_folders.sh` | No built-in watcher |
| **Best for** | Claude Code history | Any other documents |

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
# Check .env file for Azure (preferred) or OpenAI key
cat .env | grep -E "(AZURE|OPENAI)_API_KEY"

# Test key is loaded
python -c "from dotenv import load_dotenv; import os; load_dotenv(); key = os.getenv('AZURE_API_KEY') or os.getenv('OPENAI_API_KEY'); print(key[:10] if key else 'No key found')"
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
