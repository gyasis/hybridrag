# Migration System User Stories & Implementation Flows

This document maps user stories to their implementation in the HybridRAG migration system, showing how code flows through each scenario.

---

## Table of Contents

1. [US-001: Preview Migration (Dry Run)](#us-001-preview-migration-dry-run)
2. [US-002: Direct Migration](#us-002-direct-migration)
3. [US-003: Staged Migration (Safe Migration)](#us-003-staged-migration-safe-migration)
4. [US-004: Resume Interrupted Migration](#us-004-resume-interrupted-migration)
5. [US-005: Create Backup Only](#us-005-create-backup-only)
6. [US-006: List Available Backups](#us-006-list-available-backups)
7. [US-007: Rollback to Previous State](#us-007-rollback-to-previous-state)
8. [US-008: Verify Migration Integrity](#us-008-verify-migration-integrity)
9. [US-009: Query Migrated Database](#us-009-query-migrated-database)

---

## US-001: Preview Migration (Dry Run)

### User Story
> As a database administrator, I want to preview what a migration will do before executing it, so I can verify the scope and avoid unexpected changes.

### Command
```bash
python hybridrag.py backend migrate mydb --dry-run \
    --connection-string postgresql://user:pass@localhost:5432/hybridrag
```

### Code Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. CLI Entry Point                                                          │
│    hybridrag.py:cmd_backend_migrate()                                       │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. Parse Arguments                                                          │
│    - name: "mydb"                                                           │
│    - dry_run: True                                                          │
│    - connection_string: "postgresql://..."                                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. Resolve Source Path                                                      │
│    source_path = Path(f"lightrag_db/{db_name}")  # or lightrag_db if exists │
│    File: hybridrag.py:~line 890                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4. Dry Run Branch (dry_run=True)                                            │
│    File: hybridrag.py:~line 920-960                                         │
│                                                                             │
│    # Count records in source files                                          │
│    entities = load_json("kv_store_full_docs.json") → count                  │
│    relations = parse_graphml("graph_chunk_entity_relation.graphml") → count │
│    chunks = load_json("vdb_chunks.json")['data'] → count                    │
│    docs = load_json("kv_store_doc_status.json") → count                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 5. Output Preview                                                           │
│                                                                             │
│    🔍 DRY RUN - Migration Preview                                           │
│    ==================================================                       │
│    Database:   mydb                                                         │
│    Source:     /path/to/lightrag_db                                         │
│    Target:     PostgreSQL                                                   │
│    Batch Size: 1000                                                         │
│                                                                             │
│    📊 Records to Migrate:                                                   │
│       Entities           72                                                 │
│       Relations           0                                                 │
│       Chunks              0                                                 │
│       Documents           0                                                 │
│       Total              72                                                 │
│                                                                             │
│    ✓ No changes made (dry run)                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key Files
- `hybridrag.py` - CLI handling and dry-run logic
- Source JSON files in `lightrag_db/`

---

## US-002: Direct Migration

### User Story
> As a database administrator, I want to migrate my JSON-based database to PostgreSQL directly, so I can benefit from better query performance and scalability.

### Command
```bash
python hybridrag.py backend migrate mydb \
    --connection-string postgresql://user:pass@localhost:5432/hybridrag
```

### Code Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. CLI Entry Point                                                          │
│    hybridrag.py:cmd_backend_migrate()                                       │
│    - dry_run: False                                                         │
│    - staged: False                                                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. Create BackendConfig                                                     │
│    File: src/config/config.py:BackendConfig.from_connection_string()        │
│                                                                             │
│    target_config = BackendConfig.from_connection_string(connection_string)  │
│    target_config.postgres_workspace = db_name                               │
│                                                                             │
│    # Parses: postgresql://user:pass@host:port/database                      │
│    # Sets: backend_type = BackendType.POSTGRESQL                            │
│    #       postgres_host, postgres_port, postgres_database, etc.            │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. Setup Checkpoint                                                         │
│    checkpoint_file = source_path / '.migration_checkpoint.json'             │
│                                                                             │
│    # Check for existing checkpoint (for resume)                             │
│    existing_checkpoint = MigrationCheckpoint.load(checkpoint_file)          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4. Create MigrationJob                                                      │
│    File: src/migration/json_to_postgres.py:MigrationJob.__init__()          │
│                                                                             │
│    job = MigrationJob(                                                      │
│        source_path=str(source_path),                                        │
│        target_config=target_config,                                         │
│        checkpoint_file=str(checkpoint_file),                                │
│        batch_size=1000,                                                     │
│        continue_on_error=True,                                              │
│    )                                                                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 5. Run Migration                                                            │
│    File: src/migration/json_to_postgres.py:MigrationJob.run()               │
│                                                                             │
│    result = await job.run(verify=True)                                      │
│                                                                             │
│    Internal steps:                                                          │
│    ├── _ensure_tables()      # Create PostgreSQL tables                     │
│    ├── _migrate_entities()   # kv_store_full_docs.json → lightrag_entities  │
│    ├── _migrate_relations()  # .graphml → lightrag_relations                │
│    ├── _migrate_chunks()     # vdb_chunks.json → lightrag_chunks            │
│    ├── _migrate_docs()       # kv_store_doc_status.json → lightrag_doc_status│
│    └── _verify() if verify   # Run MigrationVerifier                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 6. Entity Migration Detail                                                  │
│    File: src/migration/json_to_postgres.py:_migrate_entities()              │
│                                                                             │
│    Source: kv_store_full_docs.json                                          │
│    Target: lightrag_entities table                                          │
│                                                                             │
│    for batch in batches(entities, batch_size=1000):                         │
│        INSERT INTO lightrag_entities (workspace, entity_id, content)        │
│        VALUES ($1, $2, $3)                                                  │
│        ON CONFLICT (workspace, entity_id) DO UPDATE                         │
│                                                                             │
│        checkpoint.entities_migrated += len(batch)                           │
│        checkpoint.save()  # Checkpoint after each batch                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 7. Relation Migration Detail                                                │
│    File: src/migration/json_to_postgres.py:_migrate_relations()             │
│                                                                             │
│    Source: graph_chunk_entity_relation.graphml (NetworkX GraphML)           │
│    Target: lightrag_relations table                                         │
│                                                                             │
│    graph = nx.read_graphml(source_path / "graph_chunk_entity_relation.graphml")│
│    for edge in graph.edges(data=True):                                      │
│        INSERT INTO lightrag_relations (workspace, source_id, target_id, ...)│
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 8. Chunk Migration Detail (with Vectors)                                    │
│    File: src/migration/json_to_postgres.py:_migrate_chunks()                │
│                                                                             │
│    Source: vdb_chunks.json (contains 'data' array with embeddings)          │
│    Target: lightrag_chunks table (with pgvector embedding column)           │
│                                                                             │
│    chunks_data = json.load("vdb_chunks.json")['data']                       │
│    for chunk in chunks_data:                                                │
│        INSERT INTO lightrag_chunks                                          │
│            (workspace, chunk_id, content, embedding, metadata)              │
│        VALUES ($1, $2, $3, $4::vector, $5)                                  │
│                                                                             │
│    # Vector dimension detected dynamically (e.g., 3852)                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 9. Update Registry (BUG-004 Fix)                                            │
│    File: hybridrag.py + src/database_registry.py                            │
│                                                                             │
│    if result.success:                                                       │
│        registry.update(                                                     │
│            db_name,                                                         │
│            backend_type='postgres',                                         │
│            backend_config={                                                 │
│                'connection_string': connection_string,                      │
│                'workspace': db_name,                                        │
│            }                                                                │
│        )                                                                    │
│                                                                             │
│    # Registry file: ~/.hybridrag/database_registry.json                     │
│    # Now future queries use PostgreSQL backend automatically                │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 10. Output Results                                                          │
│                                                                             │
│    Job ID: abc123-def456                                                    │
│    Status: completed                                                        │
│    Duration: 45.2s                                                          │
│                                                                             │
│    📊 Migration Results:                                                    │
│       Entities migrated: 72/72                                              │
│       Relations migrated: 150/150                                           │
│       Chunks migrated: 500/500                                              │
│       Documents migrated: 10/10                                             │
│                                                                             │
│    ✅ Migration completed successfully                                       │
│    📝 Registry updated: 'mydb' now uses PostgreSQL backend                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key Files
- `hybridrag.py` - CLI orchestration
- `src/migration/json_to_postgres.py` - MigrationJob, MigrationCheckpoint, MigrationResult
- `src/config/config.py` - BackendConfig
- `src/database_registry.py` - Registry updates

### PostgreSQL Tables Created
```sql
-- Entities (key-value store)
lightrag_entities (
    workspace VARCHAR(255),
    entity_id VARCHAR(512),
    content JSONB,
    created_at TIMESTAMP
)

-- Relations (graph edges)
lightrag_relations (
    workspace VARCHAR(255),
    source_id VARCHAR(512),
    target_id VARCHAR(512),
    weight FLOAT,
    properties JSONB
)

-- Chunks (text with vectors)
lightrag_chunks (
    workspace VARCHAR(255),
    chunk_id VARCHAR(512),
    content TEXT,
    embedding vector(3852),  -- Dynamic dimension
    metadata JSONB
)

-- Document status
lightrag_doc_status (
    workspace VARCHAR(255),
    doc_id VARCHAR(512),
    status_data JSONB
)
```

---

## US-003: Staged Migration (Safe Migration)

### User Story
> As a database administrator, I want to migrate using a staged workflow with automatic backup, so I can safely rollback if something goes wrong.

### Command
```bash
python hybridrag.py backend migrate mydb --staged \
    --connection-string postgresql://user:pass@localhost:5432/hybridrag
```

### Code Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 1: PREPARE (Backup)                                                   │
│ File: src/migration/backup.py:StagedMigration.prepare()                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1.1 Create StagedMigration Instance                                         │
│                                                                             │
│    staged = StagedMigration(                                                │
│        database_name=db_name,                                               │
│        source_path=source_path,                                             │
│        target_connection=connection_string,                                 │
│        staging_prefix="_staging",                                           │
│    )                                                                        │
│                                                                             │
│    # Loads state from: source_path/.migration_state.json                    │
│    # State tracks: phase, backup_id, staging_complete, verification_passed  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1.2 Create Backup                                                           │
│    File: src/migration/backup.py:DatabaseBackup.create_backup()             │
│                                                                             │
│    backup = DatabaseBackup(database_name, source_path)                      │
│    metadata = backup.create_backup()                                        │
│                                                                             │
│    # Creates: lightrag_db/.backups/mydb_20251219_213814.tar.gz              │
│    # Metadata: lightrag_db/.backups/mydb_20251219_213814.meta.json          │
│                                                                             │
│    Files backed up:                                                         │
│    ├── kv_store_full_docs.json                                              │
│    ├── kv_store_doc_status.json                                             │
│    ├── graph_chunk_entity_relation.graphml                                  │
│    ├── vdb_chunks.json                                                      │
│    ├── vdb_entities.json                                                    │
│    └── ... (13 total files)                                                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1.3 Update State                                                            │
│                                                                             │
│    state = {                                                                │
│        "phase": "prepared",                                                 │
│        "backup_id": "20251219_213814",                                      │
│        "staging_complete": false,                                           │
│        "verification_passed": false,                                        │
│        "promoted": false,                                                   │
│        "errors": [],                                                        │
│        "updated_at": "2025-12-19T21:38:14"                                  │
│    }                                                                        │
│    # Saved to: source_path/.migration_state.json                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 2: STAGING (Migrate to Staging Tables)                                │
│ File: src/migration/backup.py:StagedMigration.migrate_to_staging()          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2.1 Detect Embedding Dimension (BUG-007 Fix)                                │
│    File: src/migration/backup.py:_detect_embedding_dimension()              │
│                                                                             │
│    def _detect_embedding_dimension(self) -> int:                            │
│        chunks_file = self.source_path / 'vdb_chunks.json'                   │
│        data = json.load(chunks_file)                                        │
│        for chunk in data['data'][:10]:                                      │
│            for key in ['vector', 'embedding', '__vector__']:                │
│                if key in chunk and chunk[key]:                              │
│                    return len(chunk[key])  # e.g., 3852                     │
│        return 1536  # fallback                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2.2 Create Staging Tables                                                   │
│    File: src/migration/backup.py:_create_staging_tables()                   │
│                                                                             │
│    # Tables created with _staging suffix:                                   │
│    CREATE TABLE hybridrag_kv_store_staging (...)                            │
│    CREATE TABLE hybridrag_graph_edges_staging (...)                         │
│    CREATE TABLE hybridrag_chunks_staging (...)                              │
│    CREATE TABLE hybridrag_doc_status_staging (...)                          │
│                                                                             │
│    # Vector column with detected dimension:                                 │
│    ALTER TABLE hybridrag_chunks_staging                                     │
│    ADD COLUMN embedding vector(3852)  -- Dynamic!                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2.3 Migrate Data to Staging                                                 │
│                                                                             │
│    await _migrate_entities_to_staging(conn)                                 │
│    await _migrate_relations_to_staging(conn)                                │
│    await _migrate_chunks_to_staging(conn)                                   │
│    await _migrate_docs_to_staging(conn)                                     │
│                                                                             │
│    # State updated:                                                         │
│    state['staging_complete'] = True                                         │
│    state['phase'] = 'staged'                                                │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 3: VERIFY                                                             │
│ File: src/migration/backup.py:StagedMigration.verify_staging()              │
│       src/migration/verify.py:MigrationVerifier                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3.1 Run Verification Checks                                                 │
│    File: src/migration/verify.py:MigrationVerifier.verify_all()             │
│                                                                             │
│    verifier = MigrationVerifier(                                            │
│        database_name=db_name,                                               │
│        source_path=source_path,                                             │
│        target_connection=connection_string,                                 │
│        sample_size=100,                                                     │
│    )                                                                        │
│    report = await verifier.verify_all()                                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3.2 Verification Checks (BUG-005 Fixes Applied)                             │
│                                                                             │
│    ┌──────────────────────────────────────────────────────────────────────┐ │
│    │ verify_entity_counts()                                               │ │
│    │   Source: kv_store_full_docs.json → count keys                       │ │
│    │   Target: SELECT COUNT(*) FROM lightrag_entities WHERE workspace=$1  │ │
│    │   Result: ✓ PASSED if counts match                                   │ │
│    └──────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│    ┌──────────────────────────────────────────────────────────────────────┐ │
│    │ verify_relation_counts()                                             │ │
│    │   Source: graph_chunk_entity_relation.graphml → count edges          │ │
│    │   Target: SELECT COUNT(*) FROM lightrag_relations WHERE workspace=$1 │ │
│    │   Result: ✓ PASSED if counts match                                   │ │
│    └──────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│    ┌──────────────────────────────────────────────────────────────────────┐ │
│    │ verify_chunk_counts()                                                │ │
│    │   Source: vdb_chunks.json['data'] → count items                      │ │
│    │   Target: SELECT COUNT(*) FROM lightrag_chunks WHERE workspace=$1    │ │
│    │   Result: ✓ PASSED if counts match                                   │ │
│    └──────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│    ┌──────────────────────────────────────────────────────────────────────┐ │
│    │ verify_doc_status_counts()                                           │ │
│    │   Source: kv_store_doc_status.json → count keys                      │ │
│    │   Target: SELECT COUNT(*) FROM lightrag_doc_status WHERE workspace=$1│ │
│    │   Result: ✓ PASSED if counts match                                   │ │
│    └──────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│    ┌──────────────────────────────────────────────────────────────────────┐ │
│    │ verify_entity_samples()                                              │ │
│    │   Sample 100 random entities from source                             │ │
│    │   Query: SELECT content FROM lightrag_entities                       │ │
│    │          WHERE workspace=$1 AND entity_id=$2                         │ │
│    │   Compare: source_value == json.loads(target_value)                  │ │
│    │   Result: ✓ PASSED if all samples match                              │ │
│    └──────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│    ┌──────────────────────────────────────────────────────────────────────┐ │
│    │ verify_chunk_vectors()                                               │ │
│    │   Query: SELECT COUNT(*), MIN(vector_dims(embedding)),               │ │
│    │          MAX(vector_dims(embedding))                                 │ │
│    │          FROM lightrag_chunks WHERE workspace=$1                     │ │
│    │   Check: All vectors have consistent dimensions                      │ │
│    │   Result: ✓ PASSED if dimensions consistent                          │ │
│    └──────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3.3 Generate Verification Report                                            │
│                                                                             │
│    ============================================================             │
│    MIGRATION VERIFICATION REPORT                                            │
│    ============================================================             │
│    Database: mydb                                                           │
│    Migration: json → postgresql                                             │
│    ------------------------------------------------------------             │
│    ✓ PASSED: Entity Count Verification                                      │
│    ✓ PASSED: Relation Count Verification                                    │
│    ✓ PASSED: Chunk Count Verification                                       │
│    ✓ PASSED: Document Status Count Verification                             │
│    ✓ PASSED: Entity Sample Verification                                     │
│    ✓ PASSED: Vector Embedding Verification                                  │
│    ------------------------------------------------------------             │
│    ✓ ALL CHECKS PASSED (6/6 passed)                                         │
│    ============================================================             │
│                                                                             │
│    state['verification_passed'] = True                                      │
│    state['phase'] = 'verified'                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 4: PROMOTE                                                            │
│ File: src/migration/backup.py:StagedMigration.promote()                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4.1 Rename Staging Tables to Production                                     │
│                                                                             │
│    # Drop existing production tables (if any)                               │
│    DROP TABLE IF EXISTS hybridrag_kv_store                                  │
│    DROP TABLE IF EXISTS hybridrag_graph_edges                               │
│    DROP TABLE IF EXISTS hybridrag_chunks                                    │
│    DROP TABLE IF EXISTS hybridrag_doc_status                                │
│                                                                             │
│    # Rename staging to production                                           │
│    ALTER TABLE hybridrag_kv_store_staging RENAME TO hybridrag_kv_store      │
│    ALTER TABLE hybridrag_graph_edges_staging RENAME TO hybridrag_graph_edges│
│    ALTER TABLE hybridrag_chunks_staging RENAME TO hybridrag_chunks          │
│    ALTER TABLE hybridrag_doc_status_staging RENAME TO hybridrag_doc_status  │
│                                                                             │
│    state['promoted'] = True                                                 │
│    state['phase'] = 'promoted'                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4.2 Update Registry (BUG-004 Fix)                                           │
│    File: hybridrag.py + src/database_registry.py                            │
│                                                                             │
│    registry.update(                                                         │
│        db_name,                                                             │
│        backend_type='postgres',                                             │
│        backend_config={                                                     │
│            'connection_string': connection_string,                          │
│            'workspace': db_name,                                            │
│        }                                                                    │
│    )                                                                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4.3 Final Output                                                            │
│                                                                             │
│    ============================================================             │
│    ✅ STAGED MIGRATION COMPLETED SUCCESSFULLY                                │
│    ============================================================             │
│                                                                             │
│    📝 Registry updated: 'mydb' now uses PostgreSQL backend                  │
│    Backup retained: 20251219_213814                                         │
│    To rollback if needed:                                                   │
│      python hybridrag.py backend migrate mydb --rollback 20251219_213814    │
└─────────────────────────────────────────────────────────────────────────────┘
```

### State Machine

```
                    ┌─────────┐
                    │ initial │
                    └────┬────┘
                         │ prepare()
                         ▼
                    ┌─────────┐
                    │prepared │
                    └────┬────┘
                         │ migrate_to_staging()
                         ▼
                    ┌─────────┐
                    │ staged  │
                    └────┬────┘
                         │ verify_staging()
                    ┌────┴────┐
                    │         │
        verify fails│         │verify passes
                    ▼         ▼
    ┌───────────────────┐ ┌─────────┐
    │verification_failed│ │verified │
    └─────────┬─────────┘ └────┬────┘
              │                │ promote()
              │ rollback()     ▼
              │           ┌─────────┐
              └──────────►│promoted │
                          └─────────┘
                               │
                               │ rollback()
                               ▼
                          ┌───────────┐
                          │rolled_back│
                          └───────────┘
```

---

## US-004: Resume Interrupted Migration

### User Story
> As a database administrator, if my migration is interrupted (network issue, crash), I want to resume from where it left off instead of starting over.

### Command
```bash
# Migration was interrupted...
# Resume with the same command (auto-detects checkpoint)
python hybridrag.py backend migrate mydb \
    --connection-string postgresql://user:pass@localhost:5432/hybridrag

# Or explicitly specify job ID
python hybridrag.py backend migrate mydb \
    --resume abc123-def456 \
    --connection-string postgresql://user:pass@localhost:5432/hybridrag
```

### Code Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. Check for Existing Checkpoint                                            │
│    File: hybridrag.py                                                       │
│                                                                             │
│    checkpoint_file = source_path / '.migration_checkpoint.json'             │
│    existing_checkpoint = MigrationCheckpoint.load(checkpoint_file)          │
│                                                                             │
│    if existing_checkpoint:                                                  │
│        print("⚠️  Previous migration detected, resuming...")                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. Checkpoint Structure                                                     │
│    File: src/migration/json_to_postgres.py:MigrationCheckpoint              │
│                                                                             │
│    .migration_checkpoint.json:                                              │
│    {                                                                        │
│        "job_id": "abc123-def456",                                           │
│        "status": "in_progress",                                             │
│        "started_at": "2025-12-19T21:00:00",                                 │
│        "entities_total": 72,                                                │
│        "entities_migrated": 50,      # <-- Resume from here                 │
│        "relations_total": 150,                                              │
│        "relations_migrated": 150,    # <-- Already done                     │
│        "chunks_total": 500,                                                 │
│        "chunks_migrated": 0,         # <-- Not started                      │
│        "docs_total": 10,                                                    │
│        "docs_migrated": 0,                                                  │
│        "last_entity_id": "entity_050",                                      │
│        "errors": []                                                         │
│    }                                                                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. MigrationJob Loads Checkpoint                                            │
│    File: src/migration/json_to_postgres.py:MigrationJob.__init__()          │
│                                                                             │
│    job = MigrationJob(                                                      │
│        source_path=str(source_path),                                        │
│        target_config=target_config,                                         │
│        checkpoint_file=str(checkpoint_file),  # <-- Loads existing          │
│        ...                                                                  │
│    )                                                                        │
│                                                                             │
│    # In __init__:                                                           │
│    self.checkpoint = MigrationCheckpoint.load(checkpoint_file)              │
│    if self.checkpoint is None:                                              │
│        self.checkpoint = MigrationCheckpoint(job_id=uuid4())                │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4. Resume Migration (Skip Completed)                                        │
│    File: src/migration/json_to_postgres.py:MigrationJob.run()               │
│                                                                             │
│    # In _migrate_entities():                                                │
│    if checkpoint.entities_migrated >= checkpoint.entities_total:            │
│        logger.info("Entities already migrated, skipping...")                │
│        return  # Skip!                                                      │
│                                                                             │
│    # Resume from last position:                                             │
│    entities_to_migrate = all_entities[checkpoint.entities_migrated:]        │
│    for batch in batches(entities_to_migrate, batch_size):                   │
│        # Migrate batch                                                      │
│        checkpoint.entities_migrated += len(batch)                           │
│        checkpoint.save()                                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 5. Continue with Remaining Data                                             │
│                                                                             │
│    📊 Resuming Migration:                                                   │
│       Entities:  50/72 done → migrating 22 remaining                        │
│       Relations: 150/150 done → skipping                                    │
│       Chunks:    0/500 done → migrating 500                                 │
│       Documents: 0/10 done → migrating 10                                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Checkpoint Saves
Checkpoints are saved after each batch to minimize data loss:

```
Entity batch 1 (1000 records) → checkpoint.save()
Entity batch 2 (1000 records) → checkpoint.save()
[CRASH HERE]
Resume → Skip batch 1 and 2, continue from batch 3
```

---

## US-005: Create Backup Only

### User Story
> As a database administrator, I want to create a backup of my database without migrating, so I have a restore point before making manual changes.

### Command
```bash
python hybridrag.py backend migrate mydb --backup-only
```

### Code Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. CLI Detects --backup-only Flag                                           │
│    File: hybridrag.py                                                       │
│                                                                             │
│    if backup_only:                                                          │
│        backup = DatabaseBackup(db_name, source_path)                        │
│        metadata = backup.create_backup()                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. DatabaseBackup.create_backup()                                           │
│    File: src/migration/backup.py                                            │
│                                                                             │
│    def create_backup(self) -> BackupMetadata:                               │
│        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")                 │
│        backup_name = f"{self.database_name}_{timestamp}"                    │
│                                                                             │
│        # Collect all files to backup                                        │
│        files_to_backup = []                                                 │
│        for pattern in ['*.json', '*.graphml', '*.pkl']:                     │
│            files_to_backup.extend(self.source_path.glob(pattern))           │
│                                                                             │
│        # Create tarball                                                     │
│        tarball_path = self.backup_dir / f"{backup_name}.tar.gz"             │
│        with tarfile.open(tarball_path, 'w:gz') as tar:                      │
│            for file in files_to_backup:                                     │
│                tar.add(file, arcname=file.name)                             │
│                                                                             │
│        # Save metadata                                                      │
│        metadata = BackupMetadata(                                           │
│            backup_id=timestamp,                                             │
│            database_name=self.database_name,                                │
│            file_count=len(files_to_backup),                                 │
│            total_size_kb=tarball_path.stat().st_size / 1024,                │
│            created_at=datetime.now(),                                       │
│        )                                                                    │
│        metadata.save(self.backup_dir / f"{backup_name}.meta.json")          │
│                                                                             │
│        return metadata                                                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. Output                                                                   │
│                                                                             │
│    💾 Creating backup for 'mydb'...                                         │
│                                                                             │
│    ✅ Backup created successfully                                            │
│       Backup ID:  20251219_213814                                           │
│       Files:      13                                                        │
│       Size:       3,522,656.6 KB                                            │
│       Location:   lightrag_db/.backups/mydb_20251219_213814.tar.gz          │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Backup Directory Structure
```
lightrag_db/
├── .backups/
│   ├── mydb_20251219_213814.tar.gz       # Compressed backup
│   ├── mydb_20251219_213814.meta.json    # Metadata
│   ├── mydb_20251218_142030.tar.gz       # Older backup
│   └── mydb_20251218_142030.meta.json
├── kv_store_full_docs.json
├── vdb_chunks.json
└── ...
```

---

## US-006: List Available Backups

### User Story
> As a database administrator, I want to see all available backups for a database, so I can choose which one to restore.

### Command
```bash
python hybridrag.py backend migrate mydb --list-backups
```

### Code Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. CLI Detects --list-backups Flag                                          │
│    File: hybridrag.py                                                       │
│                                                                             │
│    if list_backups:                                                         │
│        backup = DatabaseBackup(db_name, source_path)                        │
│        backups = backup.list_backups()                                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. DatabaseBackup.list_backups()                                            │
│    File: src/migration/backup.py                                            │
│                                                                             │
│    def list_backups(self) -> List[BackupMetadata]:                          │
│        backups = []                                                         │
│        for meta_file in self.backup_dir.glob(f"{self.database_name}_*.meta.json"):│
│            metadata = BackupMetadata.load(meta_file)                        │
│            backups.append(metadata)                                         │
│                                                                             │
│        # Sort by created_at descending (newest first)                       │
│        return sorted(backups, key=lambda b: b.created_at, reverse=True)     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. Output                                                                   │
│                                                                             │
│    📋 Backups for 'mydb'                                                    │
│    ============================================================             │
│       20251219_213814      |  13 files | 3,522,656.6 KB | 2025-12-19T21:41  │
│       20251218_142030      |  13 files | 3,450,234.5 KB | 2025-12-18T14:20  │
│       20251217_091500      |  12 files | 3,400,100.0 KB | 2025-12-17T09:15  │
│    ============================================================             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## US-007: Rollback to Previous State

### User Story
> As a database administrator, if something goes wrong after migration, I want to rollback to a previous backup state.

### Command
```bash
python hybridrag.py backend migrate mydb --rollback 20251219_213814
```

### Code Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. CLI Detects --rollback Flag                                              │
│    File: hybridrag.py                                                       │
│                                                                             │
│    if rollback_backup_id:                                                   │
│        backup = DatabaseBackup(db_name, source_path)                        │
│        success = backup.restore_backup(rollback_backup_id)                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. Confirmation Prompt (unless -y flag)                                     │
│                                                                             │
│    ⚠️  WARNING: This will restore 'mydb' to backup 20251219_213814           │
│    Current data will be OVERWRITTEN.                                        │
│                                                                             │
│    Backup details:                                                          │
│      Created: 2025-12-19T21:41:23                                           │
│      Files:   13                                                            │
│      Size:    3,522,656.6 KB                                                │
│                                                                             │
│    Proceed with rollback? [y/N]:                                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. DatabaseBackup.restore_backup()                                          │
│    File: src/migration/backup.py                                            │
│                                                                             │
│    def restore_backup(self, backup_id: str) -> bool:                        │
│        tarball_path = self.backup_dir / f"{self.database_name}_{backup_id}.tar.gz"│
│                                                                             │
│        # Clear existing files                                               │
│        for pattern in ['*.json', '*.graphml', '*.pkl']:                     │
│            for file in self.source_path.glob(pattern):                      │
│                file.unlink()                                                │
│                                                                             │
│        # Extract backup                                                     │
│        with tarfile.open(tarball_path, 'r:gz') as tar:                      │
│            tar.extractall(self.source_path)                                 │
│                                                                             │
│        return True                                                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4. Update Registry (Revert to JSON backend)                                 │
│                                                                             │
│    registry.update(                                                         │
│        db_name,                                                             │
│        backend_type='json',                                                 │
│        backend_config={'path': str(source_path)}                            │
│    )                                                                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 5. Output                                                                   │
│                                                                             │
│    ✅ Rollback successful                                                    │
│       Restored from: 20251219_213814                                        │
│       Files restored: 13                                                    │
│       Registry updated: 'mydb' now uses JSON backend                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## US-008: Verify Migration Integrity

### User Story
> As a database administrator, I want to verify that migrated data matches the source exactly, so I can trust the migration was successful.

### Automatic Verification (Part of Migration)
Verification runs automatically after migration unless `--skip-verify` is passed.

### Code Flow (Detailed)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ MigrationVerifier.verify_all()                                              │
│ File: src/migration/verify.py                                               │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
        ▼                           ▼                           ▼
┌───────────────┐         ┌─────────────────┐         ┌─────────────────┐
│ Entity Check  │         │ Relation Check  │         │  Chunk Check    │
└───────┬───────┘         └────────┬────────┘         └────────┬────────┘
        │                          │                           │
        ▼                          ▼                           ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                                                                           │
│  SOURCE                          COMPARISON                    TARGET     │
│  ------                          ----------                    ------     │
│                                                                           │
│  kv_store_full_docs.json    ─────────►  lightrag_entities                 │
│  Count: 72 entities              ==     Count: 72 rows                    │
│                                                                           │
│  graph_chunk_entity_              ─────────►  lightrag_relations          │
│  relation.graphml                                                         │
│  Count: 150 edges                ==     Count: 150 rows                   │
│                                                                           │
│  vdb_chunks.json['data']    ─────────►  lightrag_chunks                   │
│  Count: 500 chunks               ==     Count: 500 rows                   │
│                                                                           │
│  kv_store_doc_status.json   ─────────►  lightrag_doc_status               │
│  Count: 10 docs                  ==     Count: 10 rows                    │
│                                                                           │
└───────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ Sample Verification (100 random entities)                                 │
│                                                                           │
│ for entity_id in random.sample(all_entity_ids, 100):                      │
│     source_value = source_data[entity_id]                                 │
│     target_row = SELECT content FROM lightrag_entities                    │
│                  WHERE workspace=$1 AND entity_id=$2                      │
│     target_value = json.loads(target_row['content'])                      │
│                                                                           │
│     if source_value != target_value:                                      │
│         discrepancies.append({                                            │
│             "key": entity_id,                                             │
│             "issue": "Content mismatch"                                   │
│         })                                                                │
└───────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ Vector Verification                                                       │
│                                                                           │
│ SELECT COUNT(*),                                                          │
│        MIN(vector_dims(embedding)) as min_dim,                            │
│        MAX(vector_dims(embedding)) as max_dim                             │
│ FROM lightrag_chunks                                                      │
│ WHERE workspace=$1 AND embedding IS NOT NULL                              │
│                                                                           │
│ Check: min_dim == max_dim (all vectors same dimension)                    │
│ Expected: 3852 (detected from source)                                     │
└───────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ Generate VerificationResult for Each Check                                │
│                                                                           │
│ result = VerificationResult(                                              │
│     check_name="Entity Count Verification",                               │
│     passed=True,                                                          │
│     source_count=72,                                                      │
│     target_count=72,                                                      │
│     discrepancies=[],                                                     │
│ )                                                                         │
│                                                                           │
│ # Adds to report:                                                         │
│ report.add_check(result)                                                  │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## US-009: Query Migrated Database

### User Story
> As a user, after migration I want my queries to automatically use the new PostgreSQL backend without changing my code.

### Code Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. User Runs Query                                                          │
│                                                                             │
│    python hybridrag.py query mydb "What is the main topic?"                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. Get Backend from Registry                                                │
│    File: src/database_registry.py                                           │
│                                                                             │
│    registry = get_registry()                                                │
│    db_config = registry.get(db_name)                                        │
│                                                                             │
│    # Registry returns:                                                      │
│    {                                                                        │
│        "backend_type": "postgres",                                          │
│        "backend_config": {                                                  │
│            "connection_string": "postgresql://...",                         │
│            "workspace": "mydb"                                              │
│        }                                                                    │
│    }                                                                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. Create Backend-Specific Storage                                          │
│    File: src/storage/factory.py (conceptual)                                │
│                                                                             │
│    if backend_type == 'postgres':                                           │
│        storage = PostgreSQLStorage(                                         │
│            connection_string=config['connection_string'],                   │
│            workspace=config['workspace'],                                   │
│        )                                                                    │
│    else:                                                                    │
│        storage = JSONStorage(path=config['path'])                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4. Execute Query Against PostgreSQL                                         │
│                                                                             │
│    # Vector similarity search using pgvector                                │
│    SELECT chunk_id, content,                                                │
│           embedding <=> $1::vector AS distance                              │
│    FROM lightrag_chunks                                                     │
│    WHERE workspace = $2                                                     │
│    ORDER BY distance                                                        │
│    LIMIT 10                                                                 │
│                                                                             │
│    # Entity lookup                                                          │
│    SELECT content FROM lightrag_entities                                    │
│    WHERE workspace = $1 AND entity_id = $2                                  │
│                                                                             │
│    # Relationship traversal                                                 │
│    SELECT target_id, properties FROM lightrag_relations                     │
│    WHERE workspace = $1 AND source_id = $2                                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 5. Return Results (Same Format as JSON Backend)                             │
│                                                                             │
│    The user sees identical results regardless of backend:                   │
│                                                                             │
│    Query: "What is the main topic?"                                         │
│    Answer: Based on the knowledge graph, the main topic is...               │
│                                                                             │
│    # User code unchanged - backend is abstracted                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Registry File Structure
```json
// ~/.hybridrag/database_registry.json
{
  "databases": {
    "mydb": {
      "backend_type": "postgres",
      "backend_config": {
        "connection_string": "postgresql://user:pass@localhost:5432/hybridrag",
        "workspace": "mydb"
      },
      "migrated_at": "2025-12-19T21:45:00",
      "original_path": "/path/to/lightrag_db"
    },
    "other_db": {
      "backend_type": "json",
      "backend_config": {
        "path": "/path/to/other_db"
      }
    }
  }
}
```

---

## Data Type Mappings

| JSON Source File | PostgreSQL Table | Key Columns |
|-----------------|------------------|-------------|
| `kv_store_full_docs.json` | `lightrag_entities` | workspace, entity_id, content |
| `graph_chunk_entity_relation.graphml` | `lightrag_relations` | workspace, source_id, target_id, properties |
| `vdb_chunks.json` | `lightrag_chunks` | workspace, chunk_id, content, embedding, metadata |
| `kv_store_doc_status.json` | `lightrag_doc_status` | workspace, doc_id, status_data |

---

## Error Handling Summary

| Error Type | Handling | User Action |
|------------|----------|-------------|
| Connection failure | Checkpoint saved, can resume | Check connection string, retry |
| Batch failure | Continue to next batch if `continue_on_error=True` | Review errors in checkpoint |
| Verification failure | Migration paused at 'verified' phase | Review discrepancies, rollback or investigate |
| Disk full | Checkpoint saved, migration stops | Free disk space, resume |
| Interrupted | Checkpoint saved at last batch | Rerun same command to resume |

---

## File Reference

| File | Purpose |
|------|---------|
| `hybridrag.py` | CLI entry point, command handling |
| `src/migration/__init__.py` | Module exports |
| `src/migration/json_to_postgres.py` | MigrationJob, MigrationCheckpoint, MigrationResult |
| `src/migration/backup.py` | DatabaseBackup, StagedMigration, BackupMetadata |
| `src/migration/verify.py` | MigrationVerifier, VerificationResult, MigrationVerificationReport |
| `src/config/config.py` | BackendConfig |
| `src/database_registry.py` | DatabaseRegistry |
