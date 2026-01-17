# Database Management Guide

**Problem Solved:** How to track which folders are associated with which databases.

## The Problem You Identified

Previously, HybridRAG had **NO way to track**:
- Which folders were ingested into which database
- Where the original data came from
- What to re-ingest when updating

### Why This Was Broken:

```bash
# You create database from medical_data
python hybridrag.py ingest --folder ./medical_data --working-dir ./medical_db

# Later... how do you know what folder to use?
python hybridrag.py --working-dir ./medical_db query --text "..."
# The database has NO MEMORY of ./medical_data!
```

---

## The Solution: Database Metadata System

Every database now tracks its **source folders** and **ingestion history**.

### How It Works

When you ingest data, metadata is automatically saved:

```bash
# Ingest data
python hybridrag.py ingest --folder ./medical_data

# Metadata is saved in: ./lightrag_db/database_metadata.json
```

**What's Stored:**
- ✅ All source folders that were ingested
- ✅ When they were ingested
- ✅ Whether recursive mode was used
- ✅ Ingestion history (files processed, timestamps)
- ✅ Database description

---

## New Commands

### 1. List All Databases

```bash
python hybridrag.py list-dbs
```

**Output:**
```
📊 Available Databases
======================================================================

1. lightrag_db
   Path: lightrag_db
   ✅ Has metadata
   Files ingested: 150
   Source folders: 1
   Description: Medical database

2. specstory_lightrag_db
   Path: specstory_lightrag_db
   ⚠️  No metadata (old database)

======================================================================
Total: 2 database(s)
```

### 2. Show Database Info

```bash
python hybridrag.py db-info
# or
python hybridrag.py --working-dir ./medical_db db-info
```

**Output:**
```
🔍 Database Information
======================================================================
Location: /home/user/lightrag_db

📈 Statistics:
   Created: 2025-11-10T10:30:00
   Last updated: 2025-11-10T14:15:00
   Total files ingested: 150
   Ingestion events: 3

📁 Source Folders (1):
   🔄 /home/user/medical_data
      Added: 2025-11-10T10:30:00
      Last ingested: 2025-11-10T14:15:00

📜 Recent Ingestion History:
   1. ✅ 2025-11-10T14:15:00
      Folder: /home/user/medical_data
      Files: 50
======================================================================
```

---

## Complete Workflow Examples

### Example 1: Creating a New Database

```bash
# 1. Ingest data (creates database with metadata)
python hybridrag.py ingest --folder ./medical_data --working-dir ./medical_db

# Output shows:
#   📝 Registered source folder: ./medical_data

# 2. Check what's in the database
python hybridrag.py --working-dir ./medical_db db-info

# 3. Query the database
python hybridrag.py --working-dir ./medical_db interactive
```

**Now the database KNOWS:**
- It came from `./medical_data`
- When it was created
- How many files were processed

### Example 2: Multiple Databases for Different Projects

```bash
# Create medical database
python hybridrag.py ingest \
  --folder ./medical_data \
  --working-dir ./medical_db

# Create legal database
python hybridrag.py ingest \
  --folder ./legal_docs \
  --working-dir ./legal_db

# Create research database
python hybridrag.py ingest \
  --folder ./research_papers \
  --working-dir ./research_db

# List all databases
python hybridrag.py list-dbs

# Query specific database - IT KNOWS ITS SOURCE!
python hybridrag.py --working-dir ./medical_db db-info
python hybridrag.py --working-dir ./legal_db db-info
```

### Example 3: Adding More Data to Existing Database

```bash
# Original ingestion
python hybridrag.py ingest --folder ./data_batch_1

# Add more data later
python hybridrag.py ingest --folder ./data_batch_2 --db-action add

# Check database info - shows BOTH folders!
python hybridrag.py db-info

# Output:
# 📁 Source Folders (2):
#    🔄 ./data_batch_1
#    🔄 ./data_batch_2
```

### Example 4: Migrating Old Databases

```bash
# You have an old database without metadata
python hybridrag.py --working-dir ./old_db db-info

# Output: ⚠️ No metadata found (this is an old database)

# Add metadata by re-ingesting
python hybridrag.py --working-dir ./old_db ingest --folder ./original_data --db-action add

# Now it has metadata!
python hybridrag.py --working-dir ./old_db db-info
```

---

## Understanding Database Defaults

### Default Database Name

The default database is `./lightrag_db`:

```bash
# These are equivalent:
python hybridrag.py ingest --folder ./data
python hybridrag.py --working-dir ./lightrag_db ingest --folder ./data
```

### Using Custom Database Locations

```bash
# Use different database
python hybridrag.py --working-dir ./my_custom_db ingest --folder ./data

# Query that specific database
python hybridrag.py --working-dir ./my_custom_db interactive
```

---

## Metadata File Structure

Each database contains: `database_metadata.json`

```json
{
  "version": "1.0",
  "created_at": "2025-11-10T10:30:00",
  "last_updated": "2025-11-10T14:15:00",
  "source_folders": [
    {
      "path": "/home/user/medical_data",
      "added_at": "2025-11-10T10:30:00",
      "last_ingested": "2025-11-10T14:15:00",
      "recursive": true
    }
  ],
  "ingestion_history": [
    {
      "timestamp": "2025-11-10T10:30:00",
      "source_folder": "/home/user/medical_data",
      "files_processed": 150,
      "success": true,
      "notes": ""
    }
  ],
  "total_files_ingested": 150,
  "database_type": "lightrag",
  "description": "Medical database schema"
}
```

---

## Best Practices

### 1. **Use Descriptive Database Names**

```bash
# Good - clear purpose
python hybridrag.py ingest --folder ./medical --working-dir ./medical_db
python hybridrag.py ingest --folder ./legal --working-dir ./legal_db

# Bad - unclear
python hybridrag.py ingest --folder ./data1 --working-dir ./db1
```

### 2. **Check Database Info Before Querying**

```bash
# Always check what's in a database first
python hybridrag.py list-dbs
python hybridrag.py --working-dir ./my_db db-info

# Then query
python hybridrag.py --working-dir ./my_db interactive
```

### 3. **Document Your Databases**

```bash
# The metadata file is JSON - you can manually edit descriptions:
# Edit: ./lightrag_db/database_metadata.json
# Add: "description": "Q3 2024 medical database - Athena schema"
```

### 4. **Keep Source Folders Organized**

```bash
# Good structure
./projects/
  ├── medical_project/
  │   ├── data/           # Source data
  │   └── medical_db/     # Database
  ├── legal_project/
  │   ├── docs/           # Source data
  │   └── legal_db/       # Database
```

---

## Troubleshooting

### "No metadata found"

**Problem:** Old database created before metadata system

**Solution:**
```bash
# Re-ingest to add metadata
python hybridrag.py --working-dir ./old_db ingest --folder ./original_folder --db-action add
```

### "How do I know what folder to use for an old database?"

**If you forgot:**
```bash
# Check file timestamps in database
ls -lt ./old_db/*.json

# Look at document contents
cat ./old_db/kv_store_full_docs.json | grep -o '"content".*' | head -1

# This might give you clues about the source
```

### "Multiple databases are confusing"

**Solution:** Use `list-dbs` to see all databases:
```bash
python hybridrag.py list-dbs

# Choose one and check its info
python hybridrag.py --working-dir ./database_name db-info
```

---

## Summary: The Complete Answer

### Your Question:
> "How does it know what folder to process with that database?"

### The Answer:
**It NOW knows because:**

1. ✅ **Metadata is automatically saved** during ingestion
2. ✅ **Source folders are tracked** in `database_metadata.json`
3. ✅ **You can see what folders belong to which database** with `db-info`
4. ✅ **List all databases** with `list-dbs`

### Default Database:
- Name: `./lightrag_db` (fixed from athena_lightrag_db)
- Created automatically on first ingestion
- Tracks all source folders

### Commands:
```bash
# List all databases
python hybridrag.py list-dbs

# Show database details (sees source folders!)
python hybridrag.py db-info

# Use specific database
python hybridrag.py --working-dir ./my_db ingest --folder ./data
python hybridrag.py --working-dir ./my_db interactive
```

**Problem solved!** 🎉
