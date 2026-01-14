# HybridRAG Quick Start Guide

> **5-minute setup** for knowledge graph-powered RAG

---

## Prerequisites

- Python 3.10+
- Virtual environment with HybridRAG installed

```bash
cd /path/to/hybridrag
source .venv/bin/activate  # or: uv sync && source .venv/bin/activate
```

---

## 1. Ingest Your Documents

### Option A: Quick Ingest (One-Time)

```bash
python hybridrag.py ingest --folder ./my-docs
```

### Option B: Register & Watch (Continuous)

```bash
# Register a database
python hybridrag.py db register mydb \
    --path ./mydb_data \
    --source ./my-docs \
    --auto-watch \
    --interval 300

# Start auto-watcher
python hybridrag.py db watch start mydb
```

---

## 2. Query Your Knowledge Base

### Single Query

```bash
python hybridrag.py query "What is the main architecture pattern?"

# With registered database
python hybridrag.py --db mydb query "How does authentication work?"
```

### Interactive Mode

```bash
python hybridrag.py interactive

# Or with specific database
python hybridrag.py --db mydb interactive
```

### Query Modes

```bash
# Local: Specific entities (functions, classes, concepts)
python hybridrag.py query "getUserById function" --mode local

# Global: High-level overviews and patterns
python hybridrag.py query "system architecture" --mode global

# Hybrid: Balanced (default, recommended)
python hybridrag.py query "database design patterns" --mode hybrid

# Multi-hop: Complex analysis requiring multiple steps
python hybridrag.py query "Compare auth v1 vs v2" --multihop --verbose
```

---

## 3. Choose Your Backend

### JSON (Default) - Simple & Fast

```bash
python hybridrag.py db register mydb \
    --path ./mydb \
    --source ./docs
```

### PostgreSQL - Enterprise Scale

```bash
# Setup PostgreSQL (Docker)
python hybridrag.py backend setup-docker --password mypass

# Register with PostgreSQL backend
python hybridrag.py db register mydb \
    --path ./mydb \
    --source ./docs \
    --backend postgres \
    --connection-string "postgresql://hybridrag:mypass@localhost:5432/hybridrag"
```

---

## 4. Monitor & Manage

### TUI Dashboard

```bash
python hybridrag.py monitor
```

### Quick Status

```bash
python hybridrag.py status
python hybridrag.py db list
python hybridrag.py db show mydb
```

---

## Quick Reference

| Task | Command |
|------|---------|
| Ingest folder | `python hybridrag.py ingest --folder ./docs` |
| Register DB | `python hybridrag.py db register name --path ./db --source ./docs` |
| List DBs | `python hybridrag.py db list` |
| Start watcher | `python hybridrag.py db watch start name` |
| Query | `python hybridrag.py query "..."` |
| Query with DB | `python hybridrag.py --db name query "..."` |
| Interactive | `python hybridrag.py interactive` |
| Monitor | `python hybridrag.py monitor` |

---

## Query Mode Decision Tree

```
Is it about a SPECIFIC thing (function, table, concept)?
  ├─ YES → --mode local
  │
  └─ NO → Need an OVERVIEW or SUMMARY?
           ├─ YES → --mode global
           │
           └─ NO → Complex analysis or comparison?
                    ├─ YES → --multihop
                    └─ NO → --mode hybrid (default)
```

---

## Supported File Types

| Category | Extensions |
|----------|------------|
| Documents | `.txt`, `.md`, `.pdf`, `.html` |
| Code | `.py`, `.js`, `.ts`, `.java`, `.go`, `.rs` |
| Data | `.json`, `.csv`, `.yaml`, `.yml` |

---

## Environment Variables

```bash
export HYBRIDRAG_DATABASE=./lightrag_db      # Default database path
export LIGHTRAG_MODEL=azure/gpt-4o           # LLM model
export LIGHTRAG_EMBED_MODEL=azure/text-embedding-3-small
```

---

## Next Steps

- **SpecStory users**: See `SPECSTORY_QUICKSTART.md`
- **Query modes**: See `QUERY_MODES.md`
- **PostgreSQL migration**: See `MIGRATION.md`
- **Full reference**: See `CHEATSHEET.md`
