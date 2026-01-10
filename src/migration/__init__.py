"""
HybridRAG Data Migration Module
===============================

Provides migration utilities for moving data between storage backends.
Primary use case: JSON (file-based) to PostgreSQL (pgvector) migration.

Components:
    - MigrationJob: Orchestrates the migration process with checkpoint/resume
    - MigrationCheckpoint: Tracks progress for resumable migrations
    - MigrationVerifier: Validates data integrity after migration
    - DatabaseBackup: Creates and restores database backups
    - StagedMigration: Safe staged migration workflow with backup/verify/promote
"""

from .json_to_postgres import (
    MigrationJob,
    MigrationCheckpoint,
    MigrationStatus,
    MigrationResult,
)
from .verify import MigrationVerifier, MigrationVerificationReport
from .backup import (
    BackupMetadata,
    DatabaseBackup,
    StagedMigration,
)

__all__ = [
    'MigrationJob',
    'MigrationCheckpoint',
    'MigrationStatus',
    'MigrationResult',
    'MigrationVerifier',
    'MigrationVerificationReport',
    'BackupMetadata',
    'DatabaseBackup',
    'StagedMigration',
]
