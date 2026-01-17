# User Guides

Setup instructions, usage guides, and operational documentation.

## Start Here 🚀

**New to HybridRAG?** Read in this order:

1. **Main README** (../../README.md) - Project overview
2. **USAGE.md** - Complete usage guide ⭐ START HERE
3. **ENVIRONMENT_SETUP.md** - Setup instructions

## Guide Documents

### USAGE.md ⭐
**Purpose:** Comprehensive usage guide for hybridrag.py

**Covers:**
- All commands (query, interactive, ingest, status)
- Query modes explained (local/global/hybrid/naive/mix)
- Database management
- Advanced features
- Troubleshooting

**Target Audience:** All users (required reading!)

---

### ENVIRONMENT_SETUP.md
**Purpose:** Environment configuration and setup

**Covers:**
- Python environment setup with UV
- Dependencies installation
- API key configuration
- Directory structure
- Validation scripts

**Target Audience:** First-time users, deployment

---

### RUN_INGESTION.md
**Purpose:** Detailed ingestion pipeline guide

**Covers:**
- Data ingestion workflows
- Folder watching setup
- Batch processing configuration
- Error handling
- Performance tuning

**Target Audience:** Users setting up data ingestion

---

### DATABASE_MANAGEMENT.md
**Purpose:** Database and metadata management guide

**Covers:**
- Database → folder linkage system
- Tracking source folders
- Managing multiple databases
- New `list-dbs` and `db-info` commands
- Metadata system explained

**Target Audience:** All users managing multiple databases

---

## Quick Reference

### Common Tasks

**First-Time Setup:**
```bash
# 1. Check database
python hybridrag.py check-db

# 2. Ingest data
python hybridrag.py ingest --folder ./data

# 3. Query
python hybridrag.py interactive
```

**Adding More Data:**
```bash
python hybridrag.py ingest --folder ./new_data --db-action add
```

**Different Query Modes:**
```bash
# Interactive (recommended)
python hybridrag.py interactive

# One-shot
python hybridrag.py query --text "..." --mode hybrid
```

### Getting Help

```bash
# General help
python hybridrag.py --help

# Command-specific help
python hybridrag.py query --help
python hybridrag.py ingest --help
```

## Guide Writing Guidelines

When creating new guides:

1. **Start with goals** - What will the user accomplish?
2. **Prerequisites** - What do they need first?
3. **Step-by-step** - Clear, numbered instructions
4. **Examples** - Show, don't just tell
5. **Troubleshooting** - Common issues and solutions
6. **Next steps** - Where to go from here

## Document Status

| Guide | Status | Last Updated | Audience |
|-------|--------|--------------|----------|
| USAGE.md | ✅ Current | Nov 2025 | All users |
| ENVIRONMENT_SETUP.md | ✅ Current | Sep 2024 | New users |
| RUN_INGESTION.md | ✅ Current | Sep 2024 | Data engineers |
| DATABASE_MANAGEMENT.md | ✅ Current | Nov 2025 | All users |

## Related Documentation

- **Examples** (../../examples/) - Working code examples
- **Technical Docs** (../technical/) - Implementation details
- **Memory Bank** (../../memory-bank/) - Project context
