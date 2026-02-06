# Feature Specification: Pluggable Database Backend System

**Feature Branch**: `001-pluggable-db-backend`
**Created**: 2025-12-19
**Status**: Draft
**Input**: User description: "Design a modular storage abstraction layer for HybridRAG that supports multiple database backends (JSON, PostgreSQL, Neo4j, MongoDB), monitors JSON file sizes for migration triggers, and provides flexible database provisioning via connection strings or auto-provisioned Docker containers."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Check Backend Status and File Sizes (Priority: P1)

As a HybridRAG administrator, I want to see the current storage backend status and JSON file sizes so I can understand when migration to a database backend might be beneficial.

**Why this priority**: This is foundational - users must be able to assess their current situation before making migration decisions. It provides visibility into the problem (large JSON files) and enables informed decisions.

**Independent Test**: Can be fully tested by running a status command against an existing HybridRAG database and observing file size reports with migration recommendations.

**Acceptance Scenarios**:

1. **Given** a HybridRAG database using JSON storage, **When** the user runs the backend status command, **Then** the system displays each JSON file's size in human-readable format (KB/MB/GB) along with the total storage used.

2. **Given** JSON files exceeding the warning threshold (500MB), **When** the user runs the backend status command, **Then** the system highlights files exceeding the threshold and recommends considering migration to a database backend.

3. **Given** a HybridRAG database using PostgreSQL storage, **When** the user runs the backend status command, **Then** the system displays connection status, database size, and confirms the active backend type.

---

### User Story 2 - Configure Database Backend via Connection String (Priority: P2)

As a HybridRAG administrator with an existing PostgreSQL server, I want to configure HybridRAG to use my database via a connection string so I can leverage my existing infrastructure and avoid OOM issues from large JSON files.

**Why this priority**: Most production users will have existing database infrastructure. This enables the core value proposition of switching from JSON to a scalable database backend.

**Independent Test**: Can be tested by providing a valid PostgreSQL connection string and verifying that HybridRAG successfully connects and can perform basic operations.

**Acceptance Scenarios**:

1. **Given** a valid PostgreSQL connection string, **When** the user configures a database to use this backend, **Then** the system validates the connection and stores the configuration in the registry.

2. **Given** an invalid or unreachable connection string, **When** the user attempts to configure the backend, **Then** the system provides a clear error message explaining the connection failure.

3. **Given** a configured PostgreSQL backend, **When** the watcher process starts, **Then** it uses the database backend instead of JSON files and does not load large JSON files into memory.

---

### User Story 3 - Auto-Provision Database via Docker (Priority: P2)

As a developer without existing database infrastructure, I want HybridRAG to automatically set up a local PostgreSQL container so I can benefit from database-backed storage without manual database administration.

**Why this priority**: Equal to P2 above as it serves a different user segment (developers/local setups). Enables easy onboarding and testing without infrastructure prerequisites.

**Independent Test**: Can be tested on a system with Docker installed by running the auto-setup command and verifying a working PostgreSQL container is created and connected.

**Acceptance Scenarios**:

1. **Given** Docker is installed and running, **When** the user runs the Docker auto-setup command, **Then** the system creates a PostgreSQL container with pgvector extension, configures persistent storage, and stores the connection details in the registry.

2. **Given** a Docker container already exists for HybridRAG, **When** the user runs the auto-setup command again, **Then** the system reuses the existing container (idempotent behavior) and confirms it is running.

3. **Given** Docker is not installed or not running, **When** the user runs the Docker auto-setup command, **Then** the system provides a helpful error message explaining the Docker requirement.

4. **Given** an auto-provisioned Docker container, **When** the system reboots or Docker restarts, **Then** the container automatically restarts and data persists via volume mounts.

---

### User Story 4 - Migrate Data from JSON to PostgreSQL (Priority: P3)

As a HybridRAG administrator with existing data in JSON files, I want to migrate my data to PostgreSQL so I can continue using my accumulated knowledge graph without starting over.

**Why this priority**: Migration is necessary for existing users but comes after basic setup. Users need working backend configuration (P2) before they can migrate.

**Independent Test**: Can be tested by running migration against a test database with known JSON content and verifying all data is accessible via the new backend.

**Acceptance Scenarios**:

1. **Given** an existing JSON-based database and a configured PostgreSQL backend, **When** the user runs the migration command, **Then** all entities, relationships, chunks, and embeddings are transferred to PostgreSQL with progress indication.

2. **Given** a migration in progress, **When** the user checks status, **Then** the system shows migration progress (items migrated, estimated time remaining).

3. **Given** a completed migration, **When** the user queries the database, **Then** results are identical to pre-migration queries (data integrity preserved).

4. **Given** a migration failure mid-process, **When** the user re-runs migration, **Then** the system resumes from where it left off (incremental/resumable migration).

---

### User Story 5 - Proactive Performance Monitoring (Priority: P1)

As a HybridRAG user running the watcher with JSON backend, I want the system to automatically monitor database size and warn me when performance may degrade so I can proactively migrate to PostgreSQL before experiencing OOM crashes.

**Why this priority**: Critical for preventing OOM crashes which are the primary motivation for this feature. Users shouldn't have to manually check status - the system should proactively warn them.

**Independent Test**: Can be tested by running watcher against a database that exceeds thresholds and verifying warning logs are emitted with migration suggestions.

**Acceptance Scenarios**:

1. **Given** a watcher running with JSON backend, **When** any JSON file exceeds the warning threshold (default 500MB), **Then** the watcher logs a WARNING with file name, size, and migration command suggestion.

2. **Given** a watcher running with JSON backend, **When** total database size exceeds 2GB, **Then** the watcher logs a WARNING about degraded performance and strongly recommends PostgreSQL migration.

3. **Given** a watcher running with JSON backend, **When** ingestion rate drops below baseline by more than 50%, **Then** the watcher logs a performance degradation warning with current vs baseline metrics.

4. **Given** a watcher running with PostgreSQL backend, **When** file size checks run, **Then** no warnings are emitted (PostgreSQL doesn't have this limitation).

5. **Given** warning thresholds configured in registry, **When** watcher starts, **Then** it uses the configured thresholds instead of defaults.

---

### User Story 6 - Switch Between Backends (Priority: P3)

As a HybridRAG administrator, I want to switch between different backend configurations so I can test different storage options or move between development and production environments.

**Why this priority**: Advanced use case for users managing multiple environments. Lower priority than core functionality.

**Independent Test**: Can be tested by configuring multiple backends in the registry and switching between them via CLI commands.

**Acceptance Scenarios**:

1. **Given** multiple backend configurations in the registry, **When** the user specifies a different backend for a database, **Then** the system uses the specified backend for subsequent operations.

2. **Given** a running watcher using JSON backend, **When** the user switches to PostgreSQL backend, **Then** the watcher restarts and uses the new backend configuration.

---

### Edge Cases

- What happens when PostgreSQL connection is lost during watcher operation? (System should reconnect with exponential backoff and log warnings)
- How does system handle migration when JSON files are corrupted or malformed? (System should skip corrupted records, log errors, and continue with valid data)
- What happens when Docker container runs out of disk space? (System should detect and warn before operations fail)
- How does system handle concurrent access during migration? (Migration should be exclusive - watcher paused during migration)
- What happens when user tries to migrate to a non-empty PostgreSQL database? (System should warn and require explicit confirmation or use --force flag)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST support JSON file storage as the default backend (backward compatible)
- **FR-002**: System MUST support PostgreSQL with pgvector extension as an alternative backend
- **FR-003**: System MUST allow backend configuration via registry.yaml or CLI flags
- **FR-004**: System MUST validate database connections before accepting configuration
- **FR-005**: System MUST display current backend status including storage sizes and health
- **FR-006**: System MUST warn users when JSON files exceed configurable size thresholds (default: 500MB per file, 2GB total)
- **FR-006a**: Watcher MUST proactively monitor database size during operation and emit warnings when approaching thresholds
- **FR-006b**: Watcher MUST log performance degradation warnings when ingestion slows due to large file sizes
- **FR-006c**: Warnings MUST include actionable migration command suggestion (e.g., "Run: hybridrag migrate <db> --to postgres")
- **FR-007**: System MUST provide a migration command to transfer data from JSON to PostgreSQL
- **FR-008**: System MUST preserve data integrity during migration (verifiable via checksums or counts)
- **FR-009**: System MUST support incremental/resumable migrations for large datasets
- **FR-010**: System MUST automatically provision PostgreSQL via Docker when requested
- **FR-011**: Docker provisioning MUST be idempotent (safe to run multiple times)
- **FR-012**: Docker containers MUST use persistent volumes for data durability
- **FR-013**: System MUST gracefully handle backend connection failures with appropriate error messages
- **FR-014**: System MUST stop/pause watcher during migration to prevent data conflicts
- **FR-015**: System MUST support backend configuration per database in the registry (different databases can use different backends)

### Key Entities

- **BackendConfiguration**: Represents storage backend settings including type (json/postgresql/neo4j/mongodb), connection parameters, and health status
- **MigrationJob**: Represents a data migration operation with source, destination, progress tracking, and status
- **StorageMetrics**: Represents current storage statistics including file sizes, record counts, and threshold alerts
- **DockerInstance**: Represents an auto-provisioned database container with lifecycle management

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can check backend status and see file sizes within 5 seconds
- **SC-002**: Users can configure a PostgreSQL backend via connection string in under 1 minute
- **SC-003**: Docker auto-setup completes and provides working database in under 3 minutes
- **SC-004**: Watcher process with PostgreSQL backend uses less than 500MB RAM regardless of graph size (vs current 5-7GB for large graphs)
- **SC-005**: Migration of 1GB JSON dataset completes within 30 minutes with progress visibility
- **SC-006**: 100% data integrity maintained during migration (verified by record counts and sample queries)
- **SC-007**: System provides clear, actionable error messages for all failure scenarios
- **SC-008**: Existing JSON-based workflows continue to work unchanged (backward compatibility)

## Assumptions

- Users have basic familiarity with database concepts (connection strings, Docker)
- PostgreSQL 14+ with pgvector extension is the primary supported database backend
- Docker is available for users who want auto-provisioning (not required for connection string approach)
- LightRAG's existing PGKVStorage, PGVectorStorage, PGGraphStorage, and PGDocStatusStorage classes will be leveraged
- Initial release focuses on PostgreSQL; Neo4j and MongoDB support are future enhancements
- JSON backend remains the default for backward compatibility and simple setups

## Out of Scope

- Real-time replication between backends
- Multi-master database configurations
- Automatic backend selection based on data size (manual configuration required)
- Neo4j and MongoDB backends (future enhancement)
- Cloud-managed database provisioning (AWS RDS, Azure Database, etc.)
