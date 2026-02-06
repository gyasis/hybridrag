<!--
  SYNC IMPACT REPORT
  ==================
  Version Change: 1.0.0 → 1.1.0

  Modified Principles: None

  Added Sections:
  - Principle VII: Wave-Based Parallel Execution

  Removed Sections: None

  Templates Requiring Updates:
  - ⚠ tasks-template.md - Should reference wave execution pattern
  - ✅ plan-template.md - Compatible with wave-based planning
  - ✅ spec-template.md - No changes needed
  - ✅ checklist-template.md - No changes needed

  Follow-up TODOs:
  - Consider updating tasks-template.md to include wave grouping examples
-->

# HybridRAG Constitution

## Core Principles

### I. Modular Architecture

HybridRAG MUST maintain a modular, pluggable architecture where components can be replaced or extended without affecting the system core.

- Storage backends MUST be interchangeable (JSON, PostgreSQL, Neo4j, MongoDB)
- Query modes MUST be composable and independently selectable
- Document processors MUST be extensible for new file formats
- MCP tools MUST be independently deployable

**Rationale**: The system serves diverse use cases from personal knowledge bases to enterprise deployments. Modularity enables adaptation without forking.

### II. Backward Compatibility

Changes MUST NOT break existing workflows for users who have not opted into new features.

- JSON backend MUST remain the default and fully supported
- CLI command signatures MUST maintain backward compatibility
- Configuration file formats MUST support graceful migration
- Database schemas MUST include migration paths

**Rationale**: Users have accumulated knowledge graphs that represent significant investment. Breaking changes erode trust.

### III. Memory Efficiency

The system MUST be designed to handle large knowledge graphs without excessive memory consumption.

- Watcher processes SHOULD use less than 500MB RAM regardless of graph size
- Large datasets MUST be processable via streaming or pagination
- Caching strategies MUST include eviction policies
- Memory usage MUST be monitorable and reportable

**Rationale**: The primary motivation for database backends is OOM prevention. Memory efficiency is a core value.

### IV. CLI-First Interface

All functionality MUST be accessible via command-line interface with both human-readable and machine-parseable output.

- Commands MUST support `--json` flag for scripted usage
- Error messages MUST be actionable and specific
- Progress indicators MUST be provided for long-running operations
- Commands SHOULD be composable via stdin/stdout where appropriate

**Rationale**: CLI enables automation, scripting, and integration with other tools. It's the foundation of the Unix philosophy.

### V. Observable Operations

System state and operations MUST be transparent and debuggable.

- All operations MUST produce structured logs
- Health status MUST be queryable at any time
- Migration progress MUST be visible and resumable
- Errors MUST include sufficient context for diagnosis

**Rationale**: Production systems require visibility. Silent failures are unacceptable.

### VI. Test-Informed Development

Features SHOULD be developed with testability in mind, though strict TDD is not mandated.

- Public APIs SHOULD have contract tests
- Integration points SHOULD have integration tests
- Bug fixes SHOULD include regression tests
- Performance-critical paths SHOULD have benchmarks

**Rationale**: Testing provides confidence for refactoring and prevents regressions. Pragmatic testing over dogmatic TDD.

### VII. Wave-Based Parallel Execution

Task execution MUST follow a wave-based parallelization pattern to maximize throughput while preventing race conditions.

- Tasks MUST be analyzed for dependencies before execution
- Independent tasks MUST be grouped into parallel execution waves
- Wave N MUST complete entirely before Wave N+1 begins
- File locks MUST be assigned to prevent concurrent edits to the same file
- Checkpoints MUST occur between waves for git commits and memory bank updates

**Execution Wave Protocol**:

1. **Dependency Analysis**: Determine which tasks are sequential (dependent) vs parallel (isolated)
2. **Wave Grouping**: Group independent tasks into execution waves
3. **Concurrency Control**: Assign file locks; tasks editing same file go to different waves
4. **Checkpoint Protocol**: After each wave completes:
   - Spawn `git-version-manager` agent for commits/staging
   - Spawn `memory-bank-keeper` agent for progress.md/activeContext.md updates
   - Validate wave completion before proceeding

**Wave Strategies**:
- `PARALLEL_SWARM`: Multiple agents execute independent tasks simultaneously
- `SEQUENTIAL_MERGE`: Tasks with dependencies execute in order, results merged

**Rationale**: Parallel execution dramatically improves development velocity. Wave-based checkpointing ensures atomic progress commits and prevents lost work. File locking eliminates race conditions in multi-agent scenarios.

## Technical Standards

### Language & Runtime
- Python 3.8+ required
- Async/await preferred for I/O operations
- Type hints encouraged for public APIs

### Dependencies
- LightRAG for knowledge graph operations
- LiteLLM for unified LLM provider interface
- PromptChain for multi-hop reasoning (optional)

### Storage
- JSON files as default backend
- PostgreSQL with pgvector as primary database option
- SQLite for metadata tracking

### Configuration
- Environment variables for secrets (API keys)
- YAML files for registry and database configuration
- CLI flags for runtime overrides

## Development Workflow

### Feature Development
1. Create feature specification via `/speckit.specify`
2. Validate specification via `/speckit.clarify`
3. Generate implementation plan via `/speckit.plan`
4. Generate tasks via `/speckit.tasks`
5. Execute tasks using wave-based parallelization
6. Checkpoint after each wave with git and memory bank agents

### Task Execution Schema

When generating execution plans, the following structure MUST be used:

```json
{
  "execution_plan": {
    "phase_id": "String",
    "waves": [
      {
        "wave_id": "Integer",
        "strategy": "PARALLEL_SWARM | SEQUENTIAL_MERGE",
        "rationale": "Why these tasks are grouped together",
        "tasks": [
          {
            "task_id": "String",
            "agent_role": "String (e.g., QA_Engineer, Backend_Dev)",
            "instruction": "Actionable goal",
            "file_locks": ["Array of specific file paths"],
            "dependencies": ["Array of Task IDs"]
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

### Code Review
- Changes MUST pass linting (ruff)
- Changes SHOULD include relevant tests
- Breaking changes MUST be documented
- Performance impacts MUST be justified

### Release Process
- Semantic versioning (MAJOR.MINOR.PATCH)
- CHANGELOG entries for all user-facing changes
- Migration guides for breaking changes

## Governance

This constitution establishes the non-negotiable principles for HybridRAG development. All contributions, whether from humans or AI agents, MUST comply with these principles.

### Amendment Process
1. Propose changes via pull request to this file
2. Document rationale for changes
3. Ensure backward compatibility or migration path
4. Update dependent templates if principles change

### Compliance Verification
- Pull requests SHOULD reference relevant principles
- Complexity MUST be justified against simplicity principle
- Memory impacts MUST be analyzed for new features
- Task execution MUST follow wave-based parallelization

### Version Policy
- MAJOR: Backward-incompatible principle changes
- MINOR: New principles or significant expansions
- PATCH: Clarifications and minor wording changes

**Version**: 1.1.0 | **Ratified**: 2025-12-19 | **Last Amended**: 2025-12-19
