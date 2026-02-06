# Implementation Plan: Pluggable Database Backend System

**Branch**: `001-pluggable-db-backend` | **Date**: 2025-12-19 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-pluggable-db-backend/spec.md`

## Summary

Enable HybridRAG to use PostgreSQL (and other databases) as storage backends instead of JSON files by leveraging LightRAG's built-in pluggable storage architecture. The implementation exposes LightRAG's existing `PGKVStorage`, `PGVectorStorage`, `PGGraphStorage`, and `PGDocStatusStorage` classes through HybridRAG's configuration system, adds migration tooling, and provides Docker auto-provisioning.

**Key Discovery**: LightRAG v1.4.9.8 already provides complete PostgreSQL support. No custom storage abstraction needed.

## Technical Context

**Language/Version**: Python 3.8+ (targeting 3.11+ for production)
**Primary Dependencies**:
- `lightrag-hku>=1.4.9.8` (provides all storage backends)
- `asyncpg>=0.28.0` (PostgreSQL async driver, auto-installed)
- `docker>=6.0.0` (optional, for auto-provisioning)

**Storage**:
- Default: JSON files via `JsonKVStorage`, `NanoVectorDBStorage`, `NetworkXStorage`, `JsonDocStatusStorage`
- Target: PostgreSQL via `PGKVStorage`, `PGVectorStorage`, `PGGraphStorage`, `PGDocStatusStorage`
- Future: MongoDB, Neo4j (already supported by LightRAG)

**Testing**: pytest with pytest-asyncio for async tests
**Target Platform**: Linux server (WSL2 compatible)
**Project Type**: Single project (CLI + library)

**Performance Goals**:
- Watcher memory < 500MB regardless of graph size (vs current 5-7GB)
- Backend status command < 5 seconds
- Migration throughput > 1GB/30min

**Constraints**:
- Backward compatibility with existing JSON databases
- No data loss during migration
- Watcher must pause during migration

**Scale/Scope**:
- Support graphs up to 100GB
- Support 10+ registered databases with mixed backends

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Modular Architecture | ✅ PASS | Leverages LightRAG's pluggable storage system |
| II. Backward Compatibility | ✅ PASS | JSON remains default, existing workflows unchanged |
| III. Memory Efficiency | ✅ PASS | PostgreSQL eliminates in-memory graph loading |
| IV. CLI-First Interface | ✅ PASS | All commands support `--json` flag |
| V. Observable Operations | ✅ PASS | Migration progress, health status queryable |
| VI. Test-Informed Development | ✅ PASS | Contract tests for storage interface |
| VII. Wave-Based Parallel Execution | ✅ PASS | Tasks organized into parallel waves |

## Project Structure

### Documentation (this feature)

```text
specs/001-pluggable-db-backend/
├── plan.md              # This file
├── research.md          # Phase 0 output - LightRAG backend analysis
├── data-model.md        # Phase 1 output - Configuration schemas
├── contracts/           # Phase 1 output - API contracts
│   ├── backend-config.yaml
│   └── cli-commands.yaml
├── quickstart.md        # Phase 1 output - Developer guide
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
src/
├── config/
│   └── config.py           # MODIFY: Add BackendConfig dataclass
├── lightrag_core.py        # MODIFY: Pass storage params to LightRAG
├── database_registry.py    # MODIFY: Add backend_type, backend_config
└── migration/              # NEW: Migration tooling
    ├── __init__.py
    ├── json_to_postgres.py
    └── verify.py

cli/
├── backend.py              # NEW: backend status, setup-docker commands
└── migrate.py              # NEW: migrate command

docker/
└── docker-compose.postgres.yaml  # NEW: PostgreSQL auto-provisioning

tests/
├── unit/
│   └── test_backend_config.py
├── integration/
│   └── test_postgres_backend.py
└── contract/
    └── test_storage_interface.py
```

**Structure Decision**: Single project layout. New code added to existing `src/` and `cli/` directories. New `docker/` directory for compose files.

## Complexity Tracking

No constitution violations. Implementation leverages existing LightRAG capabilities.

## Implementation Phases

### Phase 1: Configuration & Core (Wave 1-2)

**Wave 1 - Config Layer** (PARALLEL_SWARM):
- Task 1.1: Add `BackendConfig` to `config/config.py`
- Task 1.2: Add `backend_type`, `backend_config` to `DatabaseEntry`
- Task 1.3: Create `docker/docker-compose.postgres.yaml`

**Wave 2 - Core Integration** (SEQUENTIAL_MERGE):
- Task 2.1: Modify `HybridLightRAGCore._init_lightrag()` to accept storage params
- Task 2.2: Add backend factory function
- Task 2.3: Update watcher to use backend config
- Task 2.4: Add proactive size monitoring to watcher (check file sizes after each ingest, emit warnings when thresholds exceeded)

### Phase 2: CLI Commands (Wave 3)

**Wave 3 - CLI** (PARALLEL_SWARM):
- Task 3.1: Create `cli/backend.py` with `status` command
- Task 3.2: Add `setup-docker` command
- Task 3.3: Create `cli/migrate.py` with migration command

### Phase 3: Migration Tool (Wave 4-5)

**Wave 4 - Migration Core** (SEQUENTIAL_MERGE):
- Task 4.1: Create `src/migration/json_to_postgres.py`
- Task 4.2: Add incremental/resumable migration support
- Task 4.3: Create verification module

**Wave 5 - Testing** (PARALLEL_SWARM):
- Task 5.1: Unit tests for config
- Task 5.2: Integration tests for PostgreSQL backend
- Task 5.3: Contract tests for storage interface
- Task 5.4: Integration tests for proactive size monitoring

## Execution Plan Schema

```json
{
  "execution_plan": {
    "phase_id": "001-pluggable-db-backend",
    "waves": [
      {
        "wave_id": 1,
        "strategy": "PARALLEL_SWARM",
        "rationale": "Config changes are independent, no file conflicts",
        "tasks": [
          {
            "task_id": "1.1",
            "agent_role": "Backend_Dev",
            "instruction": "Add BackendConfig dataclass to config/config.py with backend_type enum and connection parameters",
            "file_locks": ["src/config/config.py"],
            "dependencies": []
          },
          {
            "task_id": "1.2",
            "agent_role": "Backend_Dev",
            "instruction": "Add backend_type and backend_config fields to DatabaseEntry in database_registry.py",
            "file_locks": ["src/database_registry.py"],
            "dependencies": []
          },
          {
            "task_id": "1.3",
            "agent_role": "DevOps_Engineer",
            "instruction": "Create docker-compose.postgres.yaml with pgvector image and persistent volumes",
            "file_locks": ["docker/docker-compose.postgres.yaml"],
            "dependencies": []
          }
        ],
        "checkpoint_after": {
          "enabled": true,
          "git_agent": "git-version-manager",
          "memory_bank_agent": "memory-bank-keeper"
        }
      },
      {
        "wave_id": 2,
        "strategy": "SEQUENTIAL_MERGE",
        "rationale": "Core changes depend on config being complete",
        "tasks": [
          {
            "task_id": "2.1",
            "agent_role": "Backend_Dev",
            "instruction": "Modify HybridLightRAGCore._init_lightrag() to pass kv_storage, vector_storage, graph_storage, doc_status_storage params based on config",
            "file_locks": ["src/lightrag_core.py"],
            "dependencies": ["1.1", "1.2"]
          },
          {
            "task_id": "2.2",
            "agent_role": "Backend_Dev",
            "instruction": "Add get_storage_classes() factory function that maps backend_type to LightRAG storage class names",
            "file_locks": ["src/lightrag_core.py"],
            "dependencies": ["2.1"]
          },
          {
            "task_id": "2.3",
            "agent_role": "Backend_Dev",
            "instruction": "Update WatcherDaemon to read backend config from registry and pass to core",
            "file_locks": ["scripts/hybridrag-watcher.py"],
            "dependencies": ["2.1"]
          },
          {
            "task_id": "2.4",
            "agent_role": "Backend_Dev",
            "instruction": "Add proactive size monitoring to watcher: after each ingest cycle, check JSON file sizes against thresholds (500MB/file, 2GB total), emit WARNING logs with migration command suggestion when exceeded",
            "file_locks": ["scripts/hybridrag-watcher.py"],
            "dependencies": ["2.3"]
          }
        ],
        "checkpoint_after": {
          "enabled": true,
          "git_agent": "git-version-manager",
          "memory_bank_agent": "memory-bank-keeper"
        }
      },
      {
        "wave_id": 3,
        "strategy": "PARALLEL_SWARM",
        "rationale": "CLI commands are independent modules",
        "tasks": [
          {
            "task_id": "3.1",
            "agent_role": "CLI_Dev",
            "instruction": "Create cli/backend.py with 'backend status' command showing file sizes, backend type, health",
            "file_locks": ["cli/backend.py"],
            "dependencies": ["2.1"]
          },
          {
            "task_id": "3.2",
            "agent_role": "CLI_Dev",
            "instruction": "Add 'backend setup-docker' command that runs docker-compose and stores connection in registry",
            "file_locks": ["cli/backend.py"],
            "dependencies": ["1.3"]
          },
          {
            "task_id": "3.3",
            "agent_role": "CLI_Dev",
            "instruction": "Create cli/migrate.py with 'migrate' command supporting --from json --to postgres",
            "file_locks": ["cli/migrate.py"],
            "dependencies": ["2.1"]
          }
        ],
        "checkpoint_after": {
          "enabled": true,
          "git_agent": "git-version-manager",
          "memory_bank_agent": "memory-bank-keeper"
        }
      },
      {
        "wave_id": 4,
        "strategy": "SEQUENTIAL_MERGE",
        "rationale": "Migration modules have internal dependencies",
        "tasks": [
          {
            "task_id": "4.1",
            "agent_role": "Data_Engineer",
            "instruction": "Create src/migration/json_to_postgres.py with MigrationJob class that reads JSON files and inserts into PostgreSQL via LightRAG storage classes",
            "file_locks": ["src/migration/__init__.py", "src/migration/json_to_postgres.py"],
            "dependencies": ["3.3"]
          },
          {
            "task_id": "4.2",
            "agent_role": "Data_Engineer",
            "instruction": "Add checkpoint/resume support to MigrationJob using a progress file",
            "file_locks": ["src/migration/json_to_postgres.py"],
            "dependencies": ["4.1"]
          },
          {
            "task_id": "4.3",
            "agent_role": "Data_Engineer",
            "instruction": "Create src/migration/verify.py to compare record counts and sample data between JSON and PostgreSQL",
            "file_locks": ["src/migration/verify.py"],
            "dependencies": ["4.1"]
          }
        ],
        "checkpoint_after": {
          "enabled": true,
          "git_agent": "git-version-manager",
          "memory_bank_agent": "memory-bank-keeper"
        }
      },
      {
        "wave_id": 5,
        "strategy": "PARALLEL_SWARM",
        "rationale": "Tests are independent and can run in parallel",
        "tasks": [
          {
            "task_id": "5.1",
            "agent_role": "QA_Engineer",
            "instruction": "Create tests/unit/test_backend_config.py with tests for BackendConfig, BackendType enum",
            "file_locks": ["tests/unit/test_backend_config.py"],
            "dependencies": ["1.1"]
          },
          {
            "task_id": "5.2",
            "agent_role": "QA_Engineer",
            "instruction": "Create tests/integration/test_postgres_backend.py with tests for PostgreSQL storage operations",
            "file_locks": ["tests/integration/test_postgres_backend.py"],
            "dependencies": ["2.1"]
          },
          {
            "task_id": "5.3",
            "agent_role": "QA_Engineer",
            "instruction": "Create tests/contract/test_storage_interface.py verifying JSON and PostgreSQL backends produce identical query results",
            "file_locks": ["tests/contract/test_storage_interface.py"],
            "dependencies": ["4.3"]
          },
          {
            "task_id": "5.4",
            "agent_role": "QA_Engineer",
            "instruction": "Create tests/integration/test_proactive_monitoring.py verifying watcher emits warnings when JSON file sizes exceed thresholds",
            "file_locks": ["tests/integration/test_proactive_monitoring.py"],
            "dependencies": ["2.4"]
          }
        ],
        "checkpoint_after": {
          "enabled": true,
          "git_agent": "git-version-manager",
          "memory_bank_agent": "memory-bank-keeper"
        }
      }
    ]
  }
}
```

## Dependencies

### Required (already installed)
- `lightrag-hku>=1.4.9.8` - Provides all storage backends
- `asyncpg>=0.28.0` - PostgreSQL driver (auto-installed by LightRAG)

### Optional
- `docker>=6.0.0` - For auto-provisioning (pip install docker)

### External
- PostgreSQL 14+ with pgvector extension
- Docker Engine (for auto-provisioning)

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| LightRAG API changes | Pin version, add compatibility tests |
| Data loss during migration | Backup JSON first, verify counts post-migration |
| Docker not available | Provide manual connection string option |
| pgvector not installed | Check extension on connection, provide install instructions |
