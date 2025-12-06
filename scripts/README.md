# Scripts Directory

Utility scripts for HybridRAG data ingestion, monitoring, and deployment.

---

## 📁 Script Categories

### 🔄 .specstory Ingestion Scripts (NEW)

Specialized scripts for processing multiple projects' `.specstory` folders.

#### `ingest_specstory_folders.sh`
**Purpose**: Find and ingest ALL `.specstory` folders from a parent directory into unified database

**Usage**:
```bash
# Fresh ingestion (create new database)
./scripts/ingest_specstory_folders.sh /home/gyasis/Documents/code fresh

# Add to existing database
./scripts/ingest_specstory_folders.sh /home/gyasis/Documents/code add

# Use specific model (third argument)
./scripts/ingest_specstory_folders.sh /home/gyasis/Documents/code fresh gemini/gemini-pro
./scripts/ingest_specstory_folders.sh /home/gyasis/Documents/code add anthropic/claude-opus
```

**Arguments**:
| Argument | Description |
|----------|-------------|
| `parent_path` | Directory to search for `.specstory` folders |
| `db_action` | `fresh` (new DB) or `add` (append to existing) |
| `model` | Optional LLM model override (e.g., `gemini/gemini-pro`, `openai/gpt-4o`) |

**Features**:
- ✅ Searches recursively for `.specstory` folders
- ✅ Unified database (cross-project queries)
- ✅ Automatic metadata tagging (project name, source path)
- ✅ Interactive confirmation prompts (or `--yes` for scripted use)
- ✅ tqdm progress bar during ingestion
- ✅ Queue-based architecture (restartable on failure)
- ✅ Quiet mode (`--quiet`) for clean output
- ✅ Detailed logging with timestamps

**Example Output**:
```
Found 3 .specstory folder(s):
  → hybridrag (.specstory)
  → project-alpha (.specstory)
  → project-beta (.specstory)

Proceed with ingestion? [y/N]
```

---

#### `ingest_separate_databases.sh`
**Purpose**: Create SEPARATE database for each project (strict isolation)

**Usage**:
```bash
./scripts/ingest_separate_databases.sh /home/gyasis/Documents/code

# Use specific model
./scripts/ingest_separate_databases.sh /home/gyasis/Documents/code gemini/gemini-pro
```

**Arguments**:
| Argument | Description |
|----------|-------------|
| `parent_path` | Directory to search for `.specstory` folders |
| `model` | Optional LLM model override (e.g., `gemini/gemini-pro`, `anthropic/claude-opus`) |

**Creates**:
```
lightrag_db_project1/    ← Isolated database
lightrag_db_project2/    ← Isolated database
lightrag_db_project3/    ← Isolated database
```

**Query specific database**:
```bash
LIGHTRAG_WORKING_DIR="./lightrag_db_project1" python hybridrag.py interactive
```

**Use Cases**:
- Client data separation (compliance)
- Different retention policies per project
- Failure isolation

---

#### `watch_specstory_folders.sh`
**Purpose**: Continuously monitor `.specstory` folders for changes and auto-ingest

**Usage**:
```bash
# Watch with 5-minute interval (default)
./scripts/watch_specstory_folders.sh /home/gyasis/Documents/code

# Watch with 1-minute interval
./scripts/watch_specstory_folders.sh /home/gyasis/Documents/code 60

# Use specific model (third argument)
./scripts/watch_specstory_folders.sh /home/gyasis/Documents/code 300 gemini/gemini-pro

# Run in background
nohup ./scripts/watch_specstory_folders.sh /home/gyasis/Documents/code > watcher.log 2>&1 &
```

**Arguments**:
| Argument | Description |
|----------|-------------|
| `parent_path` | Directory to search for `.specstory` folders |
| `interval` | Check interval in seconds (default: 300 = 5 minutes) |
| `model` | Optional LLM model override (e.g., `gemini/gemini-pro`, `anthropic/claude-opus`) |

**Features**:
- ✅ Real-time monitoring of file changes
- ✅ Automatic re-ingestion on modifications
- ✅ Configurable check interval
- ✅ Process locking (prevents duplicate watchers)
- ✅ Comprehensive logging

**Outputs**:
- PID file: `/tmp/hybridrag_watcher.pid`
- Lock file: `/tmp/hybridrag_watcher.lock`
- Log file: `logs/watcher_YYYYMMDD.log`

**Stop watcher**:
```bash
# Find PID
cat /tmp/hybridrag_watcher.pid

# Kill process
kill $(cat /tmp/hybridrag_watcher.pid)
```

---

#### `setup_systemd_watcher.sh`
**Purpose**: Setup systemd service for automatic startup and monitoring

**Usage**:
```bash
# Setup service (requires sudo)
sudo ./scripts/setup_systemd_watcher.sh /home/gyasis/Documents/code 300
```

**Creates**:
- Service file: `/etc/systemd/system/hybridrag-watcher.service`
- Auto-starts on boot
- Restarts automatically if crashed

**Management Commands**:
```bash
# Check status
sudo systemctl status hybridrag-watcher

# View live logs
sudo journalctl -u hybridrag-watcher -f

# Stop service
sudo systemctl stop hybridrag-watcher

# Restart service
sudo systemctl restart hybridrag-watcher

# Disable auto-start
sudo systemctl disable hybridrag-watcher
```

---

### 📊 Legacy Data Ingestion Scripts

#### `deeplake_to_lightrag.py`
Batch ingestion from DeepLake to LightRAG
```bash
python scripts/deeplake_to_lightrag.py
```

#### `deeplake_to_lightrag_incremental.py`
Incremental updates to existing database
```bash
python scripts/deeplake_to_lightrag_incremental.py
```

#### `folder_to_lightrag.py`
Ingest documents from folder into LightRAG
```bash
python scripts/folder_to_lightrag.py --folder ./data
```

**Note**: For most use cases, prefer the unified entry point:
```bash
python hybridrag.py ingest --folder ./data
```

---

## 🎯 Common Workflows

### Initial Setup

```bash
# 1. Clone HybridRAG to new location
git clone https://github.com/yourusername/hybridrag.git
cd hybridrag

# 2. Install dependencies
source .venv/bin/activate
pip install -r requirements.txt

# 3. Ingest all .specstory folders
./scripts/ingest_specstory_folders.sh /home/gyasis/Documents/code fresh
```

### Production Deployment

```bash
# 1. Setup systemd service for auto-monitoring
sudo ./scripts/setup_systemd_watcher.sh /home/gyasis/Documents/code 300

# 2. Check service is running
sudo systemctl status hybridrag-watcher

# 3. Monitor logs
sudo journalctl -u hybridrag-watcher -f
```

### Docker Deployment

```bash
# 1. Build image
docker compose build

# 2. Start with auto-watch
docker compose up -d

# 3. View logs
docker compose logs -f hybridrag
```

### Scheduled Updates (Cron)

```bash
# Add to crontab
crontab -e

# Run every 5 minutes
*/5 * * * * cd /path/to/hybridrag && ./scripts/ingest_specstory_folders.sh /home/gyasis/Documents/code add >> /var/log/hybridrag-cron.log 2>&1

# Run daily at 2 AM
0 2 * * * cd /path/to/hybridrag && ./scripts/ingest_specstory_folders.sh /home/gyasis/Documents/code add >> /var/log/hybridrag-cron.log 2>&1
```

---

## 📝 Script Permissions

All scripts should be executable:

```bash
# Make all scripts executable
chmod +x scripts/*.sh

# Or individually:
chmod +x scripts/ingest_specstory_folders.sh
chmod +x scripts/ingest_separate_databases.sh
chmod +x scripts/watch_specstory_folders.sh
chmod +x scripts/setup_systemd_watcher.sh
```

---

## 🐛 Troubleshooting

### Script not found / Permission denied

```bash
# Make executable
chmod +x scripts/ingest_specstory_folders.sh

# Run with explicit bash
bash scripts/ingest_specstory_folders.sh /path/to/projects fresh
```

### Watcher not detecting changes

```bash
# Check if watcher is running
ps aux | grep watch_specstory

# Check logs
tail -f logs/watcher_*.log

# Restart watcher
kill $(cat /tmp/hybridrag_watcher.pid)
./scripts/watch_specstory_folders.sh /path/to/projects &
```

### Multiple watchers running

```bash
# Find all watcher processes
ps aux | grep watch_specstory

# Kill specific PID
kill <PID>

# Or kill from lock file
kill $(cat /tmp/hybridrag_watcher.lock)
```

### Systemd service fails to start

```bash
# Check service status
sudo systemctl status hybridrag-watcher

# View detailed logs
sudo journalctl -u hybridrag-watcher -xe

# Check script permissions
ls -la scripts/watch_specstory_folders.sh

# Test script manually
sudo -u $USER bash scripts/watch_specstory_folders.sh /path/to/projects 300
```

---

## 🔍 Log Files

| Log Type | Location | Purpose |
|----------|----------|---------|
| Ingestion logs | `logs/ingestion_*.log` | Manual ingestion operations |
| Watcher logs | `logs/watcher_*.log` | Continuous monitoring activity |
| Systemd logs | `journalctl -u hybridrag-watcher` | Service management logs |
| Cron logs | `/var/log/hybridrag-cron.log` | Scheduled ingestion logs |
| Separate DB logs | `logs/separate_ingestion_*.log` | Per-project database creation |

**View logs**:
```bash
# Recent ingestion
tail -f logs/ingestion_*.log

# Watcher activity
tail -f logs/watcher_*.log

# Systemd service
sudo journalctl -u hybridrag-watcher -f

# All logs (last 100 lines)
tail -n 100 logs/*.log
```

---

## 📚 Documentation

- **[Quick Start Guide](../QUICK_START_SPECSTORY.md)** - 30-minute setup
- **[Full Deployment Guide](../docs/deployment/MULTI_PROJECT_DEPLOYMENT.md)** - Comprehensive documentation
- **[Usage Guide](../docs/guides/USAGE.md)** - All commands and features
- **[Main README](../README.md)** - Project overview

---

## 🎯 Quick Reference

| Task | Command |
|------|---------|
| **One-time ingestion** | `./scripts/ingest_specstory_folders.sh /path fresh` |
| **Add to existing** | `./scripts/ingest_specstory_folders.sh /path add` |
| **With specific model** | `./scripts/ingest_specstory_folders.sh /path fresh gemini/gemini-pro` |
| **Separate databases** | `./scripts/ingest_separate_databases.sh /path` |
| **Start watcher** | `./scripts/watch_specstory_folders.sh /path 300` |
| **Watcher with model** | `./scripts/watch_specstory_folders.sh /path 300 anthropic/claude-opus` |
| **Setup systemd** | `sudo ./scripts/setup_systemd_watcher.sh /path 300` |
| **Stop watcher** | `kill $(cat /tmp/hybridrag_watcher.pid)` |
| **View logs** | `tail -f logs/watcher_*.log` |

### Supported Model Formats (LiteLLM)

| Provider | Model Format Example |
|----------|---------------------|
| Azure (default) | `azure/gpt-5.1` |
| OpenAI | `openai/gpt-4o`, `openai/gpt-4o-mini` |
| Anthropic | `anthropic/claude-opus`, `anthropic/claude-sonnet` |
| Gemini | `gemini/gemini-pro`, `gemini/gemini-flash` |

---

**Need help?** See [troubleshooting guide](../docs/deployment/MULTI_PROJECT_DEPLOYMENT.md#troubleshooting) or open an issue.
