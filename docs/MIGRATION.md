# HybridRAG Database Migration Guide

This guide covers migrating HybridRAG databases from JSON (file-based) storage to PostgreSQL with pgvector.

## Overview

The migration system provides:
- **Safe migration** with automatic backup before any changes
- **Staged workflow** - migrate to staging, verify, then promote
- **Checkpoint/resume** for large databases
- **Rollback** to previous state if needed
- **Verification** of migrated data integrity

## Quick Start

### Basic Migration (Direct)
```bash
# Dry run first to preview
python hybridrag.py backend migrate mydb --dry-run \
    --connection-string postgresql://user:pass@localhost:5432/hybridrag

# Run migration
python hybridrag.py backend migrate mydb \
    --connection-string postgresql://user:pass@localhost:5432/hybridrag
```

### Safe Migration (Recommended)
```bash
# Use staged migration with automatic backup
python hybridrag.py backend migrate mydb --staged \
    --connection-string postgresql://user:pass@localhost:5432/hybridrag
```

## Commands

### Migration Commands

| Command | Description |
|---------|-------------|
| `backend migrate <name> --dry-run` | Preview migration without changes |
| `backend migrate <name>` | Run direct migration |
| `backend migrate <name> --staged` | Run staged migration (backup + verify) |
| `backend migrate <name> --resume JOB_ID` | Resume interrupted migration |

### Backup Commands

| Command | Description |
|---------|-------------|
| `backend migrate <name> --list-backups` | List available backups |
| `backend migrate <name> --backup-only` | Create backup without migrating |
| `backend migrate <name> --rollback BACKUP_ID` | Restore from backup |

## Migration Options

```
Options:
  --connection-string   PostgreSQL connection string
  --batch-size N        Records per batch (default: 1000)
  --dry-run             Preview only, no changes
  --skip-verify         Skip post-migration verification
  --resume JOB_ID       Resume previous migration
  --pause-watcher       Pause watcher during migration (default: True)
  --yes, -y             Skip confirmation prompts

Staged Migration (Phase 7):
  --staged              Use 4-phase staged migration workflow
  --backup-only         Create backup without migrating
  --rollback BACKUP_ID  Rollback to previous backup
  --list-backups        List available backups
```

## Staged Migration Workflow

When using `--staged`, the migration follows this 4-phase workflow:

```
Phase 1: BACKUP
    Create compressed backup of JSON files
    ↓
Phase 2: STAGING
    Migrate data to PostgreSQL staging tables (_staging suffix)
    ↓
Phase 3: VERIFY
    Compare record counts and sample data
    ↓
Phase 4: PROMOTE
    Rename staging tables to production
```

### Benefits of Staged Migration

1. **Data Safety**: Backup created before any changes
2. **Verification**: Data compared before committing
3. **Rollback**: Easy restore if issues found
4. **Resumable**: Can resume from any phase if interrupted

### Example: Full Staged Migration

```bash
# Start staged migration
python hybridrag.py backend migrate specstory --staged \
    --connection-string postgresql://hybridrag:password@localhost:5432/hybridrag

# Output:
# STAGED MIGRATION for 'specstory'
# ============================================================
# Workflow: Backup → Staging → Verify → Promote
# ============================================================
#
# Phase 1/4: Creating backup...
#    ✓ Backup created: 20251219_213814
#
# Phase 2/4: Migrating to staging...
#    ✓ Data migrated to staging tables
#
# Phase 3/4: Verifying staged data...
#    ✓ Verification passed
#
# Phase 4/4: Promoting staging to production...
#    ✓ Staging tables promoted to production
#
# ============================================================
# ✅ STAGED MIGRATION COMPLETED SUCCESSFULLY
# ============================================================
#
# Backup retained: 20251219_213814
# To rollback if needed: python hybridrag.py backend migrate specstory --rollback 20251219_213814
```

## Backup Management

### Creating Backups

```bash
# Create backup before manual operations
python hybridrag.py backend migrate mydb --backup-only
```

Backups are stored as compressed tarballs in `<database_path>/.backups/`:
- Format: `{database}_{timestamp}.tar.gz`
- Metadata: `{database}_{timestamp}.meta.json`
- Default retention: 3 backups (configurable)

### Listing Backups

```bash
python hybridrag.py backend migrate mydb --list-backups

# Output:
# Backups for 'mydb'
# ============================================================
#    20251219_213814      |  13 files | 3,522,656.6 KB | 2025-12-19T21:41:23
#    20251218_142030      |  13 files | 3,450,234.5 KB | 2025-12-18T14:20:30
# ============================================================
```

### Restoring from Backup

```bash
# Rollback to specific backup
python hybridrag.py backend migrate mydb --rollback 20251219_213814

# With confirmation skip
python hybridrag.py backend migrate mydb --rollback 20251219_213814 -y
```

## Migration State

The staged migration tracks state in `.migration_state.json`:

```json
{
  "phase": "verified",
  "backup_id": "20251219_213814",
  "staging_complete": true,
  "verification_passed": true,
  "promoted": false,
  "errors": [],
  "updated_at": "2025-12-19T21:45:00"
}
```

### Phases

| Phase | Description |
|-------|-------------|
| `initial` | No migration started |
| `prepared` | Backup created |
| `staged` | Data in staging tables |
| `verified` | Verification passed |
| `promoted` | Migration complete |
| `rolled_back` | Restored from backup |
| `verification_failed` | Verification failed |

### Resuming Interrupted Migration

If migration is interrupted, run the same command again. It will automatically resume from the last checkpoint:

```bash
# If interrupted during staging, rerun:
python hybridrag.py backend migrate mydb --staged \
    --connection-string postgresql://...

# Output:
# ⚠️  Previous staged migration detected at phase: prepared
#    Resuming from last checkpoint...
```

## Embedding Dimension Detection (Automatic)

**The migration system automatically detects embedding dimensions from your JSON files.**

The migration reads the `embedding_dim` field from nano-vectordb JSON files (vdb_entities.json, vdb_chunks.json, vdb_relationships.json). This is the authoritative source for dimension information.

### Detection Priority

1. **`embedding_dim` key in JSON metadata** (most reliable - nano-vectordb stores this)
2. **Matrix field analysis** (base64-encoded numpy array in nano-vectordb format)
3. **Individual vector fields** (legacy format fallback)
4. **Default: 1536** (text-embedding-3-small standard dimension)

### Common Embedding Dimensions

| Model | Dimension |
|-------|-----------|
| OpenAI text-embedding-3-small | 1536 (default, configurable: 256-1536) |
| Azure text-embedding-3-small | 1536 (configurable: 256-1536) |
| OpenAI text-embedding-3-large | 3072 |
| text-embedding-ada-002 | 1536 |
| sentence-transformers (mpnet) | 768 |

### Manual Override (Optional)

If you need to override the detected dimension:

**Environment Variable:**
```bash
export LIGHTRAG_EMBEDDING_DIM=1536
python hybridrag.py backend migrate mydb --staged ...
```

**In MCP Server Configuration (`.claude.json`):**
```json
{
  "hybridrag-specstory": {
    "env": {
      "HYBRIDRAG_DATABASE_NAME": "specstory",
      "LIGHTRAG_EMBEDDING_DIM": "1536"
    }
  }
}
```

### Verifying Your Embedding Dimension

Check your existing JSON data:
```bash
# Method 1: Read embedding_dim from JSON metadata (recommended)
python -c "
import json
with open('lightrag_db/vdb_entities.json') as f:
    data = json.load(f)
    print(f'embedding_dim: {data.get(\"embedding_dim\", \"not set\")}')
"

# Method 2: Detect from matrix field
python -c "
import json, base64
import numpy as np
with open('lightrag_db/vdb_entities.json') as f:
    data = json.load(f)
    matrix_str = data.get('matrix', '')
    if matrix_str:
        arr = np.frombuffer(base64.b64decode(matrix_str), dtype=np.float32)
        # Test common dimensions
        for dim in [1536, 768, 1024]:
            if len(arr) % dim == 0:
                print(f'Detected dimension: {dim} ({len(arr)//dim} embeddings)')
                break
"

# Method 3: From PostgreSQL (if already migrated)
docker exec hybridrag-postgres psql -U hybridrag -d hybridrag -c \
  "SELECT vector_dims(content_vector) FROM lightrag_vdb_entity LIMIT 1;"
```

### Dimension Mismatch Errors

If you see errors like `different vector dimensions 1536 and 768`:
1. **Root cause**: PostgreSQL table created with wrong dimension
2. **Solution**: The migration now auto-detects from JSON `embedding_dim` field
3. **Manual fix** (if needed): Run `scripts/alter_vector_dimension.py` then `scripts/restore_embeddings_from_matrix.py`

**The migration system prevents this by reading the dimension directly from your source data.**

---

## PostgreSQL Schema

The migration creates these tables:

```sql
-- Key-value store for entities
hybridrag_kv_store (
    workspace VARCHAR(255),
    key VARCHAR(512),
    value JSONB
)

-- Graph edges for relationships
hybridrag_graph_edges (
    workspace VARCHAR(255),
    source_id VARCHAR(512),
    target_id VARCHAR(512),
    properties JSONB
)

-- Text chunks with vectors
hybridrag_chunks (
    workspace VARCHAR(255),
    chunk_id VARCHAR(512),
    content TEXT,
    embedding vector(1536),
    metadata JSONB
)

-- Document processing status
hybridrag_doc_status (
    workspace VARCHAR(255),
    doc_id VARCHAR(512),
    status_data JSONB
)
```

## Verification Checks

Post-migration verification includes:

1. **Entity Count** - Source vs target record counts
2. **Relation Count** - Graph edge counts
3. **Chunk Count** - Text chunk counts
4. **Document Status Count** - Processing status counts
5. **Entity Samples** - Random sample content comparison
6. **Vector Embeddings** - Dimension consistency check

## Troubleshooting

### Connection Issues

```bash
# Test PostgreSQL connection
python hybridrag.py backend setup-docker  # Uses Docker for local testing

# Verify connection
psql postgresql://user:pass@localhost:5432/hybridrag -c "SELECT 1"
```

### Large Database Migration

For databases > 1GB, use batched migration:

```bash
python hybridrag.py backend migrate mydb --staged \
    --batch-size 500 \
    --connection-string postgresql://...
```

### Verification Failures

If verification fails:

1. Check the detailed report for specific discrepancies
2. Review staging tables directly in PostgreSQL
3. Rollback if needed: `--rollback BACKUP_ID`
4. Fix issues and retry

### Clearing Stale State

To reset migration state and start fresh:

```bash
# Remove state file
rm /path/to/database/.migration_state.json

# Then run migration again
python hybridrag.py backend migrate mydb --staged ...
```

## API Reference

### Python API

```python
from src.migration import (
    MigrationJob,          # Direct migration orchestrator
    MigrationVerifier,     # Post-migration verification
    DatabaseBackup,        # Backup management
    StagedMigration,       # Staged migration workflow
)

# Staged migration
staged = StagedMigration(
    database_name="mydb",
    source_path=Path("/path/to/json/db"),
    target_connection="postgresql://...",
)

await staged.prepare()           # Phase 1: Create backup
await staged.migrate_to_staging() # Phase 2: Migrate to staging
await staged.verify_staging()     # Phase 3: Verify
await staged.promote()            # Phase 4: Promote to production
await staged.rollback()           # Optional: Rollback if needed

# Backup management
backup = DatabaseBackup("mydb", Path("/path/to/db"))
metadata = backup.create_backup()
backup.list_backups()
backup.restore_backup("20251219_213814")
```

## See Also

- [Backend Status Command](./BACKEND_STATUS.md)
- [PostgreSQL Setup Guide](./POSTGRES_SETUP.md)
- [Query Modes](./QUERY_MODES.md)
