# SpecStory Quick Start Guide

> **5-minute setup** to query your Claude Code conversation history

## Prerequisites

- Python 3.10+, HybridRAG installed
- Projects with `.specstory` folders (from Claude Code)

---

## 1. Initial Ingestion (One-Time)

```bash
cd /path/to/hybridrag

# Ingest all existing .specstory folders
./scripts/ingest_specstory_folders.sh ~/dev/jira-issues fresh
```

Output:
```
Found 6 .specstory folder(s):
  → TIC-4116, DE-2, pseudo-jira-12...
✅ Ingestion complete: 42 files processed
```

---

## 2. Register the Database

```bash
python hybridrag.py db register specstory \
    --path ./lightrag_db \
    --source ~/dev/jira-issues \
    --type specstory \
    --auto-watch \
    --interval 300
```

Verify:
```bash
python hybridrag.py db show specstory
```

---

## 3. Start Auto-Watcher

```bash
python hybridrag.py db watch start specstory
```

Check status:
```bash
python hybridrag.py db watch status
# Output: [✓] specstory 🟢 PID 12345
```

---

## 4. Query Your History

```bash
# Single query
python hybridrag.py --db specstory query "How did we implement the ETL pipeline?"

# Interactive mode
python hybridrag.py --db specstory interactive

# Different search modes
python hybridrag.py --db specstory query "migration patterns" --mode hybrid
python hybridrag.py --db specstory query "specific function" --mode local
python hybridrag.py --db specstory query "architecture overview" --mode global
```

---

## Optional: PostgreSQL Backend

For large conversation archives, use PostgreSQL:

```bash
# Setup Docker PostgreSQL
python hybridrag.py backend setup-docker --password mypass

# Register with PostgreSQL
python hybridrag.py db register specstory-pg \
    --path ./specstory_pg_db \
    --source ~/dev/jira-issues \
    --type specstory \
    --backend postgres \
    --connection-string "postgresql://hybridrag:mypass@localhost:5432/hybridrag"
```

---

## Optional: Systemd (Persistent Watcher)

```bash
# Install systemd service
python hybridrag.py db watch start specstory --systemd

# Manage with systemctl
systemctl --user status hybridrag-watcher@specstory.service
systemctl --user restart hybridrag-watcher@specstory.service

# View logs
journalctl --user -u hybridrag-watcher@specstory.service -f
```

---

## Quick Reference

| Task | Command |
|------|---------|
| Initial ingest | `./scripts/ingest_specstory_folders.sh <path> fresh` |
| Register DB | `python hybridrag.py db register specstory --path ./lightrag_db --source <path> --type specstory` |
| Start watcher | `python hybridrag.py db watch start specstory` |
| Query | `python hybridrag.py --db specstory query "..."` |
| Interactive | `python hybridrag.py --db specstory interactive` |
| Stop watcher | `python hybridrag.py db watch stop specstory` |
| Force re-sync | `python hybridrag.py db sync specstory --fresh` |

---

## Troubleshooting

**Watcher won't start:**
```bash
rm ~/.hybridrag/watchers/specstory.pid
python hybridrag.py db watch start specstory
```

**Database not found:**
```bash
python hybridrag.py db list  # Check registration
```

**View watcher logs:**
```bash
tail -f logs/watcher_specstory.log
```

---

**Setup complete!** New conversations auto-ingest every 5 minutes.
