# Tasks: Pluggable Database Backend System

**Input**: Design documents from `/specs/001-pluggable-db-backend/`
**Prerequisites**: plan.md, spec.md, data-model.md, contracts/backend-config.yaml, contracts/cli-commands.yaml, quickstart.md
**Branch**: `001-pluggable-db-backend`
**Date**: 2025-12-19

## Summary

**Total Tasks**: 24 tasks across 6 phases
**User Stories**: 6 stories (2 P1, 2 P2, 2 P3)
**Parallel Opportunities**: Waves 1, 3, 5 support parallel execution (PARALLEL_SWARM)
**Suggested MVP Scope**: US1 (Backend Status) + US5 (Proactive Monitoring) - enables users to see current state and receive warnings

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1-US6)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Wave 1 - Config Layer)

**Purpose**: Add configuration dataclasses and Docker compose file
**Strategy**: PARALLEL_SWARM - all tasks can run concurrently

- [ ] T001 [P] [US2] Add `BackendType` enum and `BackendConfig` dataclass to `src/config/config.py` with backend_type, postgres connection params, vector index config, and monitoring thresholds (file_size_warning_mb=500, total_size_warning_mb=2048, performance_degradation_pct=50)
- [ ] T002 [P] [US2] Add `backend_type` and `backend_config` fields to `DatabaseEntry` in `src/database_registry.py` with `get_backend_config()` method
- [ ] T003 [P] [US3] Create `docker/docker-compose.postgres.yaml` with pgvector/pgvector:pg16 image, persistent volume, healthcheck, and environment variables

**Checkpoint**: Configuration layer complete - git commit with version tag

---

## Phase 2: Foundational (Wave 2 - Core Integration)

**Purpose**: Core LightRAG integration that MUST be complete before CLI commands
**Strategy**: SEQUENTIAL_MERGE - tasks have dependencies

**CRITICAL**: No CLI commands (Phase 3) can begin until this phase is complete

- [ ] T004 [US2] Modify `HybridLightRAGCore._init_lightrag()` in `src/lightrag_core.py` to accept optional `backend_config` parameter and pass kv_storage, vector_storage, graph_storage, doc_status_storage params to LightRAG based on config
- [ ] T005 [US2] Add `get_storage_classes()` factory function to `src/lightrag_core.py` that maps BackendType to LightRAG storage class names (JsonKVStorage vs PGKVStorage, etc.)
- [ ] T006 [US2] Update `WatcherDaemon` in `scripts/hybridrag-watcher.py` to read backend config from registry and pass to HybridLightRAGCore initialization
- [ ] T007 [US5] Add proactive size monitoring to watcher in `scripts/hybridrag-watcher.py`: after each ingest cycle, check JSON file sizes against thresholds (500MB/file, 2GB total), emit WARNING logs with migration command suggestion when exceeded

**Checkpoint**: Core integration complete - PostgreSQL backend should work when configured

---

## Phase 3: User Story 1 - Check Backend Status (Priority: P1)

**Goal**: Users can see current storage backend status and JSON file sizes
**Independent Test**: Run `hybridrag backend status <db>` and observe file size reports with migration recommendations

### Implementation for User Story 1

- [ ] T008 [US1] Create `cli/backend.py` with Click command group and `status` subcommand that displays backend type, connection status, entity/relation/chunk/doc counts
- [ ] T009 [US1] Add `StorageMetrics` collection logic to `cli/backend.py` - gather file sizes for JSON backend, connection latency for PostgreSQL backend
- [ ] T010 [US1] Implement file size threshold warnings in status output - highlight files > 500MB, suggest migration command when total > 2GB
- [ ] T011 [US1] Add `--json` and `--verbose` flags to status command per contracts/cli-commands.yaml

**Checkpoint**: Users can check backend status and see file size warnings

---

## Phase 4: User Story 5 - Proactive Performance Monitoring (Priority: P1)

**Goal**: Watcher automatically monitors and warns before OOM crashes
**Independent Test**: Run watcher against database exceeding thresholds, verify WARNING logs with migration suggestions

### Implementation for User Story 5

- [ ] T012 [US5] Add baseline ingestion rate tracking to watcher in `scripts/hybridrag-watcher.py` - store rolling average of docs/minute
- [ ] T013 [US5] Implement performance degradation detection - compare current ingestion rate to baseline, warn when > 50% slower
- [ ] T014 [US5] Add configurable threshold loading from registry `backend_config` - allow users to customize warning thresholds
- [ ] T015 [US5] Skip file size warnings when using PostgreSQL backend (not applicable)

**Checkpoint**: Watcher proactively warns users before performance degrades

---

## Phase 5: User Story 2 & 3 - Backend Configuration (Priority: P2)

**Goal**: Users can configure PostgreSQL via connection string OR auto-provision via Docker
**Independent Test**: Configure backend via connection string, verify watcher connects to PostgreSQL

### Implementation for User Story 2 (Connection String)

- [ ] T016 [P] [US2] Add `--backend` and `--connection-string` flags to `hybridrag db create` command in existing CLI
- [ ] T017 [US2] Add connection validation logic - test PostgreSQL connectivity before storing config in registry

### Implementation for User Story 3 (Docker Auto-Provision)

- [ ] T018 [P] [US3] Add `setup-docker` subcommand to `cli/backend.py` that runs docker-compose and stores connection in registry
- [ ] T019 [US3] Implement idempotent container management - detect existing container, reuse if running, provide helpful errors if Docker unavailable

**Checkpoint**: Users can configure PostgreSQL via either connection string or Docker

---

## Phase 6: User Story 4 - Data Migration (Priority: P3)

**Goal**: Migrate existing JSON data to PostgreSQL without data loss
**Independent Test**: Run migration on test database, verify all data accessible via new backend

### Implementation for User Story 4

- [ ] T020 [US4] Create `cli/migrate.py` with `migrate` command supporting `--from json --to postgres --verify` per contracts/cli-commands.yaml
- [ ] T021 [US4] Create `src/migration/__init__.py` and `src/migration/json_to_postgres.py` with `MigrationJob` class that reads JSON files and inserts via LightRAG storage classes
- [ ] T022 [US4] Add checkpoint/resume support to `MigrationJob` using `MigrationCheckpoint` dataclass - save progress to file, resume from last checkpoint
- [ ] T023 [US4] Create `src/migration/verify.py` to compare record counts and sample queries between JSON and PostgreSQL
- [ ] T024 [US4] Add watcher pause/resume logic during migration - stop watcher before migration, restart with new backend after

**Checkpoint**: Users can migrate existing data to PostgreSQL

---

## Phase 7: Testing (Wave 5)

**Purpose**: Verify all functionality works correctly
**Strategy**: PARALLEL_SWARM - tests are independent

- [ ] T025 [P] [US2] Create `tests/unit/test_backend_config.py` with tests for BackendType enum, BackendConfig dataclass, get_storage_classes()
- [ ] T026 [P] [US2] Create `tests/integration/test_postgres_backend.py` with tests for PostgreSQL storage operations (requires running PostgreSQL)
- [ ] T027 [P] [US4] Create `tests/contract/test_storage_interface.py` verifying JSON and PostgreSQL backends produce identical query results
- [ ] T028 [P] [US5] Create `tests/integration/test_proactive_monitoring.py` verifying watcher emits warnings when JSON file sizes exceed thresholds

**Checkpoint**: All tests pass, feature ready for merge

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Setup) ──────────────────────────────────┐
                                                   │
Phase 2 (Foundational) ←──────────────────────────┘
     │
     ├──→ Phase 3 (US1: Status) ─────→ Phase 7 (Tests)
     │
     ├──→ Phase 4 (US5: Monitoring) ─→ Phase 7 (Tests)
     │
     ├──→ Phase 5 (US2/3: Config) ───→ Phase 7 (Tests)
     │
     └──→ Phase 6 (US4: Migration) ──→ Phase 7 (Tests)
```

### User Story Dependencies

| Story | Priority | Can Start After | Dependencies |
|-------|----------|-----------------|--------------|
| US1 | P1 | Phase 2 complete | None |
| US5 | P1 | T007 in Phase 2 | Watcher core integration |
| US2 | P2 | Phase 2 complete | BackendConfig (T001) |
| US3 | P2 | Phase 1 (T003) | Docker compose file |
| US4 | P3 | Phase 3-5 complete | All backends working |
| US6 | P3 | Phase 5 complete | Multiple backend configs |

### Parallel Opportunities

**Wave 1 (Phase 1)**: T001, T002, T003 can all run in parallel
**Wave 3 (Phase 3-5)**: T008, T016, T018 can start in parallel after Phase 2
**Wave 5 (Phase 7)**: T025, T026, T027, T028 can all run in parallel

---

## Implementation Strategy

### MVP First (P1 Stories Only)

1. Complete Phase 1: Setup (Wave 1)
2. Complete Phase 2: Foundational (Wave 2)
3. Complete Phase 3: US1 - Backend Status
4. Complete Phase 4: US5 - Proactive Monitoring
5. **STOP and VALIDATE**: Users can check status and receive warnings
6. Deploy/demo MVP

### Full Implementation

1. MVP (above)
2. Add Phase 5: US2/US3 - Backend Configuration
3. Add Phase 6: US4 - Data Migration
4. Complete Phase 7: Testing
5. Feature complete for merge

---

## File Locks by Task

| Task | Files Modified |
|------|----------------|
| T001 | `src/config/config.py` |
| T002 | `src/database_registry.py` |
| T003 | `docker/docker-compose.postgres.yaml` |
| T004-T005 | `src/lightrag_core.py` |
| T006-T007, T012-T015 | `scripts/hybridrag-watcher.py` |
| T008-T011, T018-T019 | `cli/backend.py` |
| T016-T017 | `cli/` (existing db command) |
| T020 | `cli/migrate.py` |
| T021-T022 | `src/migration/json_to_postgres.py` |
| T023 | `src/migration/verify.py` |

---

## Notes

- [P] tasks = different files, no dependencies - can run in parallel
- [Story] label maps task to specific user story for traceability
- Tests (Phase 7) are included as specified in plan.md Wave 5
- US6 (Switch Between Backends) is implicit once US2/US3/US4 complete
- Commit after each checkpoint with `git-version-manager` agent
- Update `memory-bank-keeper` after each wave completion
