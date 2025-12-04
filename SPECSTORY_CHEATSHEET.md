# HybridRAG SpecStory Processing Cheatsheet

Quick reference for processing all your `.specstory` folders with HybridRAG.

---

## 🚀 Quick Start (One-Time Setup)

### 1. Navigate to HybridRAG Directory
```bash
cd /home/gyasisutton/dev/tools/RAG/hybridrag
```

### 2. Activate Environment
```bash
# Option A: Using UV (recommended)
source .venv/bin/activate
# OR
uv run python hybridrag.py ...

# Option B: Using activate script
source activate_env.sh
```

### 3. Verify Environment
```bash
python hybridrag.py check-db
```

---

## 📥 Ingest All SpecStory Folders

### One-Time Ingestion (Fresh Start)
```bash
# Find and ingest ALL .specstory folders from a parent directory
./scripts/ingest_specstory_folders.sh /home/gyasisutton/dev fresh

# Example: Process all projects in your dev folder
./scripts/ingest_specstory_folders.sh /home/gyasisutton/dev fresh
```

### Add to Existing Database
```bash
# Add new .specstory folders to existing database
./scripts/ingest_specstory_folders.sh /home/gyasisutton/dev add
```

### What It Does:
- ✅ Finds all `.specstory` folders recursively
- ✅ Shows you which projects will be processed
- ✅ Ingests each folder into LightRAG database
- ✅ Tags with project name and source path
- ✅ Shows tqdm progress bar during ingestion
- ✅ Restartable: queue-based architecture resumes on failure

---

## 🔄 Continuous Monitoring (Auto-Update)

### Manual Watcher (Terminal)
```bash
# Watch for changes every 5 minutes (300 seconds)
./scripts/watch_specstory_folders.sh /home/gyasisutton/dev 300

# Run in background
nohup ./scripts/watch_specstory_folders.sh /home/gyasisutton/dev 300 > watcher.log 2>&1 &
```

### Stop Watcher
```bash
# Find and kill the watcher process
ps aux | grep watch_specstory
kill <PID>
```

---

## 🔍 Query Your Data

### Interactive Mode (Recommended)
```bash
python hybridrag.py interactive

# Example queries:
# > How did we implement authentication across all projects?
# > Show me all API patterns from project history
# > What database migrations were done?
```

### One-Shot Queries
```bash
# Simple query
python hybridrag.py query --text "Find appointment tables" --mode hybrid

# Agentic multi-hop reasoning
python hybridrag.py query --text "Compare authentication patterns" --agentic
```

### Query Modes
- `local` - Specific entities/relationships
- `global` - High-level overviews
- `hybrid` - **Recommended** - Best of both
- `agentic` - Multi-hop reasoning

---

## 📊 Check Status

### Database Info
```bash
python hybridrag.py check-db      # Quick database check
python hybridrag.py db-info       # Detailed info with source folders
python hybridrag.py list-dbs      # List all databases in directory
```

### System Status
```bash
python hybridrag.py status
```

---

## 🗂️ Common Workflows

### Add New Project Path
```bash
# Add another directory to existing database
./scripts/ingest_specstory_folders.sh /mnt/other-projects add
```

### Re-Ingest Everything (Fresh Start)
```bash
# WARNING: This deletes existing database
./scripts/ingest_specstory_folders.sh /home/gyasisutton/dev fresh
```

### Update Existing Data (Incremental)
```bash
# Only processes new/changed files
./scripts/ingest_specstory_folders.sh /home/gyasisutton/dev add
```

---

## 📁 File Structure

```
hybridrag/
├── hybridrag.py              # Main entry point
├── scripts/
│   ├── ingest_specstory_folders.sh    # ⭐ Use this for ingestion
│   └── watch_specstory_folders.sh     # ⭐ Use this for auto-watch
├── lightrag_db/              # Database location
└── logs/                     # Log files
```

---

## ⚙️ Configuration

### Environment Variables (.env)
```bash
OPENAI_API_KEY=your_key_here
# Optional:
ANTHROPIC_API_KEY=your_key_here
```

### Database Location
- Default: `./lightrag_db/`
- Change with: `--working-dir` flag

---

## 🐛 Troubleshooting

### No .specstory folders found
```bash
# Verify folders exist
find /home/gyasisutton/dev -type d -name ".specstory"
```

### API Key errors
```bash
# Check .env file
cat .env | grep OPENAI_API_KEY
```

### Check logs
```bash
# Ingestion logs
tail -f logs/ingestion_*.log

# Watcher logs
tail -f logs/watcher_*.log
```

---

## 📝 Quick Command Reference

| Task | Command |
|------|---------|
| **Ingest all specstory** | `./scripts/ingest_specstory_folders.sh /path/to/projects fresh` |
| **Add to existing** | `./scripts/ingest_specstory_folders.sh /path/to/projects add` |
| **Watch for changes** | `./scripts/watch_specstory_folders.sh /path/to/projects 300` |
| **Interactive query** | `python hybridrag.py interactive` |
| **One-shot query** | `python hybridrag.py query --text "question" --mode hybrid` |
| **Check database** | `python hybridrag.py check-db` |
| **Detailed db info** | `python hybridrag.py db-info` |
| **List all databases** | `python hybridrag.py list-dbs` |
| **System status** | `python hybridrag.py status` |

### Advanced Ingestion Flags

| Flag | Description |
|------|-------------|
| `--metadata KEY=VALUE` | Add metadata tags (can use multiple times) |
| `--yes`, `-y` | Skip confirmation prompts (for scripting) |
| `--quiet`, `-q` | Suppress verbose output, show only progress bar |

Example with all flags:
```bash
python hybridrag.py ingest --folder ./data --db-action add --metadata "project=myapp" --yes --quiet
```

---

## 🎯 Typical Workflow

1. **First Time Setup:**
   ```bash
   cd /home/gyasisutton/dev/tools/RAG/hybridrag
   source .venv/bin/activate
   ./scripts/ingest_specstory_folders.sh /home/gyasisutton/dev fresh
   ```

2. **Start Querying:**
   ```bash
   python hybridrag.py interactive
   ```

3. **Auto-Update (Optional):**
   ```bash
   nohup ./scripts/watch_specstory_folders.sh /home/gyasisutton/dev 300 > watcher.log 2>&1 &
   ```

---

## 📂 Not Just SpecStory - Regular Folder Ingestion

HybridRAG works with **any folder**, not just `.specstory`:

```bash
# Ingest any folder directly
python hybridrag.py ingest --folder /path/to/documents

# Multiple folders at once
python hybridrag.py ingest --folder ./docs --folder ./notes --db-action add

# With custom metadata
python hybridrag.py ingest --folder ./research \
    --metadata "project=research" \
    --metadata "year=2025"
```

| Use Case | Approach |
|----------|----------|
| `.specstory` folders (Claude Code history) | Use `./scripts/ingest_specstory_folders.sh` |
| Any other documents (PDFs, markdown, code) | Use `python hybridrag.py ingest --folder` |

---

## 💡 Pro Tips

- Use `fresh` only for first-time setup
- Use `add` for incremental updates
- Watcher checks every 5 minutes by default (300 seconds)
- All queries use the unified database by default
- Logs are in `logs/` directory with timestamps
- **HybridRAG is not limited to `.specstory`** - ingest any documents!

---

**Need more details?** See `QUICK_START_SPECSTORY.md` or `README.md`

