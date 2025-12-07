# User Story: Setting Up SpecStory Database with HybridRAG Registry

## Overview

**As a** developer using Claude Code with SpecStory conversations
**I want to** automatically ingest my `.specstory` folders into HybridRAG
**So that** I can query my entire conversation history across all projects

---

## Prerequisites

- HybridRAG installed and working
- Projects with `.specstory` folders (created by Claude Code)
- Python 3.10+ with virtual environment

---

## Step 1: Initial Ingestion (One-Time)

First, ingest all existing `.specstory` folders from your projects directory:

```bash
cd /home/$USER/dev/tools/RAG/hybridrag

# Fresh ingestion (creates new database)
./scripts/ingest_specstory_folders.sh /home/$USER/dev/jira-issues fresh

# Or add to existing database
./scripts/ingest_specstory_folders.sh /home/$USER/dev/jira-issues add
```

**What happens:**
- Script finds all `.specstory` folders recursively
- Each project's conversation history is ingested
- Metadata tags each file with `project=<name>` and `source_path=<path>`

**Output:**
```
Found 6 .specstory folder(s):
  → TIC-4116 (.specstory)
  → DE-2 (.specstory)
  → pseudo-jira-12 (.specstory)
  ...

✅ Ingestion complete:
   Files found:     42
   Files processed: 42
   Files failed:    0
```

---

## Step 2: Register Database in Registry

Now register your database so you can reference it by name:

```bash
python hybridrag.py db register specstory \
    --path ./lightrag_db \
    --source /home/$USER/dev/jira-issues \
    --type specstory \
    --auto-watch \
    --interval 300 \
    --description "SpecStory conversation history from jira-issues projects"
```

**Parameters explained:**
| Parameter | Value | Description |
|-----------|-------|-------------|
| `specstory` | name | Friendly name to reference this DB |
| `--path` | `./lightrag_db` | Where the database files are stored |
| `--source` | `/home/.../jira-issues` | Parent folder containing projects |
| `--type` | `specstory` | Enables SpecStory-specific processing |
| `--auto-watch` | flag | Enable automatic file watching |
| `--interval` | `300` | Check for changes every 5 minutes |

**Verify registration:**
```bash
python hybridrag.py db show specstory
```

**Output:**
```
📊 Database: specstory
======================================================================
   Path:         /home/$USER/dev/tools/RAG/hybridrag/lightrag_db
   Source:       /home/$USER/dev/jira-issues
   Type:         specstory
   Auto-watch:   True
   Interval:     300s
   Recursive:    True
   Description:  SpecStory conversation history from jira-issues projects
======================================================================
```

---

## Step 3: Start the Watcher Daemon

Start automatic file watching to ingest new conversations:

```bash
python hybridrag.py db watch start specstory
```

**Output:**
```
✅ Started watcher for specstory (PID: 3774591)
```

**Check status anytime:**
```bash
python hybridrag.py db watch status
```

**Output:**
```
🔍 Watcher Status
============================================================
   [✓] specstory            🟢 PID 3774591
============================================================
Running: 1/1
```

---

## Step 4: Query Your SpecStory History

Now you can query using the `--db` flag:

```bash
# Single query
python hybridrag.py --db specstory query "How did we implement the ETL pipeline?"

# Interactive mode
python hybridrag.py --db specstory interactive

# Hybrid search mode
python hybridrag.py --db specstory query "database migration patterns" --mode hybrid
```

---

## Optional: Systemd Service (Persistent Watcher)

For watchers that survive reboots:

```bash
# Start with systemd integration
python hybridrag.py db watch start specstory --systemd

# Or install systemd units for all auto-watch databases
python hybridrag.py db watch install-systemd
```

**Manage with systemctl:**
```bash
systemctl --user status hybridrag-watcher@specstory.service
systemctl --user stop hybridrag-watcher@specstory.service
systemctl --user restart hybridrag-watcher@specstory.service

# View logs
journalctl --user -u hybridrag-watcher@specstory.service -f
```

---

## Common Commands Reference

### Database Management
```bash
# List all registered databases
python hybridrag.py db list

# Show database details
python hybridrag.py db show specstory

# Update settings
python hybridrag.py db update specstory --interval 600  # 10 min interval

# Force re-sync from source
python hybridrag.py db sync specstory

# Remove from registry (keeps data)
python hybridrag.py db unregister specstory
```

### Watcher Control
```bash
# Start watcher
python hybridrag.py db watch start specstory

# Stop watcher
python hybridrag.py db watch stop specstory

# Check all watchers
python hybridrag.py db watch status

# View watcher logs
tail -f logs/watcher_specstory.log
```

### Querying
```bash
# Query with database name
python hybridrag.py --db specstory query "your question"

# Interactive mode
python hybridrag.py --db specstory interactive

# Check database stats
python hybridrag.py --db specstory status
```

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     Your Projects Directory                      │
│  /home/$USER/dev/jira-issues/                             │
│  ├── TIC-4116/.specstory/history/*.md                           │
│  ├── DE-2/.specstory/history/*.md                               │
│  ├── TIC-3162/.specstory/history/*.md                           │
│  └── ...                                                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    HybridRAG Watcher Daemon                      │
│  scripts/hybridrag-watcher.py                                   │
│  - Polls every 5 minutes                                        │
│  - Detects new/modified .specstory files                        │
│  - Auto-ingests changes                                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Database Registry                             │
│  ~/.hybridrag/registry.yaml                                     │
│  - Tracks: specstory → ./lightrag_db                            │
│  - Source: /home/$USER/dev/jira-issues                    │
│  - Auto-watch: enabled                                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    LightRAG Database                             │
│  ./lightrag_db/                                                 │
│  - 44,990 entities                                              │
│  - 80,123 relationships                                         │
│  - 16,111 text chunks                                           │
│  - Vector embeddings for semantic search                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Query Interface                          │
│  python hybridrag.py --db specstory query "..."                 │
│  - Local, global, hybrid, naive search modes                    │
│  - Graph-based knowledge retrieval                              │
│  - Full conversation context                                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Troubleshooting

### Watcher not starting
```bash
# Check for existing watcher
ps aux | grep hybridrag-watcher

# Remove stale PID file
rm ~/.hybridrag/watchers/specstory.pid

# Try again
python hybridrag.py db watch start specstory
```

### Database not found
```bash
# Verify registration
python hybridrag.py db list

# Re-register if needed
python hybridrag.py db register specstory --path ./lightrag_db --source /path/to/projects
```

### No files being ingested
```bash
# Check source folder exists
ls /home/$USER/dev/jira-issues

# Check for .specstory folders
find /home/$USER/dev/jira-issues -type d -name ".specstory"

# View watcher logs
tail -f logs/watcher_specstory.log
```

---

## Summary

| Step | Command | Purpose |
|------|---------|---------|
| 1 | `./scripts/ingest_specstory_folders.sh <path>` | Initial bulk ingestion |
| 2 | `python hybridrag.py db register specstory ...` | Save config to registry |
| 3 | `python hybridrag.py db watch start specstory` | Start auto-ingestion daemon |
| 4 | `python hybridrag.py --db specstory query "..."` | Query your history |

**Your setup is complete!** New SpecStory conversations will be automatically ingested every 5 minutes.
