"""
Migration Backup Module (Phase 7)
==================================

Provides backup and restore functionality for safe migrations.
Ensures original data is preserved until migration is verified successful.

Features:
- Creates timestamped backups before migration
- Supports incremental backups
- Automatic cleanup of old backups
- Restore from backup on migration failure
"""

import json
import logging
import tarfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class BackupMetadata:
    """Metadata for a backup."""
    backup_id: str
    database_name: str
    source_path: str
    backup_path: str
    created_at: str
    file_count: int = 0
    total_size_bytes: int = 0
    files: List[str] = field(default_factory=list)
    checksum: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'backup_id': self.backup_id,
            'database_name': self.database_name,
            'source_path': self.source_path,
            'backup_path': self.backup_path,
            'created_at': self.created_at,
            'file_count': self.file_count,
            'total_size_bytes': self.total_size_bytes,
            'files': self.files,
            'checksum': self.checksum,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BackupMetadata':
        return cls(**data)

    def save(self, filepath: Path) -> None:
        """Save metadata to JSON file."""
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, filepath: Path) -> Optional['BackupMetadata']:
        """Load metadata from JSON file."""
        if not filepath.exists():
            return None
        with open(filepath, 'r') as f:
            return cls.from_dict(json.load(f))


class DatabaseBackup:
    """
    Manages database backups for safe migration.

    Creates compressed backups of JSON database files before migration,
    allowing rollback if migration fails.
    """

    # Files to backup (JSON database files)
    BACKUP_FILES = [
        'kv_store_full_docs.json',
        'kv_store_text_chunks.json',
        'kv_store_llm_response_cache.json',
        'kv_store_doc_status.json',
        'graph_chunk_entity_relation.graphml',
        'vdb_chunks.json',
        'vdb_entities.json',
        'vdb_relationships.json',
    ]

    def __init__(
        self,
        database_name: str,
        source_path: Path,
        backup_dir: Optional[Path] = None,
        max_backups: int = 3,
    ):
        """
        Initialize backup manager.

        Args:
            database_name: Name of the database
            source_path: Path to the database directory
            backup_dir: Directory to store backups (default: source_path/.backups)
            max_backups: Maximum number of backups to retain
        """
        self.database_name = database_name
        self.source_path = Path(source_path)
        self.backup_dir = backup_dir or (self.source_path / '.backups')
        self.max_backups = max_backups

        # Ensure backup directory exists
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self, backup_id: Optional[str] = None) -> BackupMetadata:
        """
        Create a backup of the database.

        Args:
            backup_id: Optional custom backup ID (default: timestamp)

        Returns:
            BackupMetadata with backup details
        """
        # Generate backup ID
        if not backup_id:
            backup_id = datetime.now().strftime('%Y%m%d_%H%M%S')

        backup_name = f"{self.database_name}_{backup_id}"
        backup_path = self.backup_dir / f"{backup_name}.tar.gz"

        logger.info(f"Creating backup: {backup_name}")

        # Collect files to backup
        files_to_backup = []
        total_size = 0

        for filename in self.BACKUP_FILES:
            filepath = self.source_path / filename
            if filepath.exists():
                files_to_backup.append(filepath)
                total_size += filepath.stat().st_size

        # Also backup any .json files we might have missed
        for filepath in self.source_path.glob('*.json'):
            if filepath not in files_to_backup:
                files_to_backup.append(filepath)
                total_size += filepath.stat().st_size

        # Create compressed tarball
        with tarfile.open(backup_path, 'w:gz') as tar:
            for filepath in files_to_backup:
                arcname = filepath.name  # Store just filename, not full path
                tar.add(filepath, arcname=arcname)
                logger.debug(f"  Added: {arcname}")

        # Create metadata
        metadata = BackupMetadata(
            backup_id=backup_id,
            database_name=self.database_name,
            source_path=str(self.source_path),
            backup_path=str(backup_path),
            created_at=datetime.now().isoformat(),
            file_count=len(files_to_backup),
            total_size_bytes=total_size,
            files=[f.name for f in files_to_backup],
        )

        # Save metadata
        metadata_path = self.backup_dir / f"{backup_name}.meta.json"
        metadata.save(metadata_path)

        logger.info(f"Backup created: {backup_path}")
        logger.info(f"  Files: {metadata.file_count}, Size: {total_size / 1024:.1f} KB")

        # Cleanup old backups
        self._cleanup_old_backups()

        return metadata

    def restore_backup(self, backup_id: str) -> bool:
        """
        Restore database from a backup.

        Args:
            backup_id: ID of the backup to restore

        Returns:
            True if restore successful, False otherwise
        """
        backup_name = f"{self.database_name}_{backup_id}"
        backup_path = self.backup_dir / f"{backup_name}.tar.gz"
        metadata_path = self.backup_dir / f"{backup_name}.meta.json"

        if not backup_path.exists():
            logger.error(f"Backup not found: {backup_path}")
            return False

        logger.info(f"Restoring from backup: {backup_name}")

        # Load metadata
        metadata = BackupMetadata.load(metadata_path)

        # Extract files
        with tarfile.open(backup_path, 'r:gz') as tar:
            tar.extractall(path=self.source_path)

        if metadata:
            logger.info(f"Restored {metadata.file_count} files")
        else:
            logger.info("Restore complete")

        return True

    def list_backups(self) -> List[BackupMetadata]:
        """
        List all available backups.

        Returns:
            List of BackupMetadata for available backups
        """
        backups = []

        for meta_file in sorted(self.backup_dir.glob('*.meta.json'), reverse=True):
            metadata = BackupMetadata.load(meta_file)
            if metadata:
                # Verify backup file exists
                backup_path = Path(metadata.backup_path)
                if backup_path.exists():
                    backups.append(metadata)

        return backups

    def get_latest_backup(self) -> Optional[BackupMetadata]:
        """Get the most recent backup."""
        backups = self.list_backups()
        return backups[0] if backups else None

    def delete_backup(self, backup_id: str) -> bool:
        """
        Delete a specific backup.

        Args:
            backup_id: ID of the backup to delete

        Returns:
            True if deleted, False if not found
        """
        backup_name = f"{self.database_name}_{backup_id}"
        backup_path = self.backup_dir / f"{backup_name}.tar.gz"
        metadata_path = self.backup_dir / f"{backup_name}.meta.json"

        deleted = False

        if backup_path.exists():
            backup_path.unlink()
            deleted = True

        if metadata_path.exists():
            metadata_path.unlink()
            deleted = True

        if deleted:
            logger.info(f"Deleted backup: {backup_name}")

        return deleted

    def _cleanup_old_backups(self) -> None:
        """Remove old backups exceeding max_backups limit."""
        backups = self.list_backups()

        while len(backups) > self.max_backups:
            oldest = backups.pop()
            self.delete_backup(oldest.backup_id)
            logger.info(f"Cleaned up old backup: {oldest.backup_id}")


class StagedMigration:
    """
    Implements staged migration workflow for safe data transfer.

    Workflow:
    1. Create backup of original data
    2. Migrate data to staging area (new PostgreSQL schema/tables)
    3. Verify migration in staging
    4. If verified, promote staging to production
    5. Only delete original after successful promotion
    """

    def __init__(
        self,
        database_name: str,
        source_path: Path,
        target_connection: str,
        staging_prefix: str = "_staging",
    ):
        """
        Initialize staged migration.

        Args:
            database_name: Name of the database
            source_path: Path to JSON source files
            target_connection: PostgreSQL connection string
            staging_prefix: Prefix for staging tables
        """
        self.database_name = database_name
        self.source_path = Path(source_path)
        self.target_connection = target_connection
        self.staging_prefix = staging_prefix

        # State tracking
        self.state_file = self.source_path / '.migration_state.json'
        self.state = self._load_state()

        # Backup manager
        self.backup = DatabaseBackup(database_name, source_path)

    def _load_state(self) -> Dict[str, Any]:
        """Load migration state from file."""
        if self.state_file.exists():
            with open(self.state_file, 'r') as f:
                return json.load(f)
        return {
            'phase': 'initial',
            'backup_id': None,
            'staging_complete': False,
            'verification_passed': False,
            'promoted': False,
            'errors': [],
        }

    def _save_state(self) -> None:
        """Save migration state to file."""
        self.state['updated_at'] = datetime.now().isoformat()
        with open(self.state_file, 'w') as f:
            json.dump(self.state, f, indent=2)

    def _detect_embedding_dimension(self) -> int:
        """
        Detect embedding dimension from source vdb_chunks.json file.

        Returns:
            Detected dimension (default: 1536 if cannot be determined)
        """
        chunks_file = self.source_path / 'vdb_chunks.json'
        if not chunks_file.exists():
            logger.debug("No vdb_chunks.json found, using default dimension 1536")
            return 1536

        try:
            with open(chunks_file, 'r') as f:
                data = json.load(f)

            # vdb_chunks.json has 'data' key with list of chunks
            chunks = []
            if isinstance(data, dict) and 'data' in data:
                chunks = data['data']
            elif isinstance(data, list):
                chunks = data

            if chunks:
                # Find first chunk with an embedding
                for chunk in chunks[:10]:  # Check first 10 chunks
                    # Try different possible embedding key names
                    for key in ['vector', 'embedding', '__vector__']:
                        if key in chunk and chunk[key]:
                            dim = len(chunk[key])
                            logger.info(f"Detected embedding dimension: {dim}")
                            return dim

            logger.debug("No embeddings found, using default dimension 1536")
            return 1536

        except Exception as e:
            logger.warning(f"Could not detect embedding dimension: {e}")
            return 1536

    async def prepare(self) -> bool:
        """
        Prepare for migration - create backup.

        Returns:
            True if preparation successful
        """
        logger.info("Phase 1: Preparing for migration...")

        try:
            # Create backup
            metadata = self.backup.create_backup()
            self.state['backup_id'] = metadata.backup_id
            self.state['phase'] = 'prepared'
            self._save_state()

            logger.info(f"Backup created: {metadata.backup_id}")
            return True

        except Exception as e:
            self.state['errors'].append({
                'phase': 'prepare',
                'error': str(e),
                'timestamp': datetime.now().isoformat(),
            })
            self._save_state()
            logger.error(f"Preparation failed: {e}")
            return False

    async def migrate_to_staging(self) -> bool:
        """
        Migrate data to staging tables.

        Returns:
            True if staging migration successful
        """
        logger.info("Phase 2: Migrating to staging...")

        if self.state['phase'] != 'prepared':
            logger.error("Must prepare before migrating")
            return False

        try:
            import asyncpg

            conn = await asyncpg.connect(self.target_connection)

            try:
                # Create staging tables
                await self._create_staging_tables(conn)

                # Migrate data to staging tables
                await self._migrate_entities_to_staging(conn)
                await self._migrate_relations_to_staging(conn)
                await self._migrate_chunks_to_staging(conn)
                await self._migrate_docs_to_staging(conn)

                self.state['staging_complete'] = True
                self.state['phase'] = 'staged'
                self._save_state()

                logger.info("Staging migration complete")
                return True

            finally:
                await conn.close()

        except Exception as e:
            self.state['errors'].append({
                'phase': 'staging',
                'error': str(e),
                'timestamp': datetime.now().isoformat(),
            })
            self._save_state()
            logger.error(f"Staging migration failed: {e}")
            return False

    async def verify_staging(self) -> bool:
        """
        Verify data in staging tables.

        Returns:
            True if verification passed
        """
        logger.info("Phase 3: Verifying staging...")

        if self.state['phase'] != 'staged':
            logger.error("Must complete staging before verifying")
            return False

        try:
            from .verify import MigrationVerifier

            # Create verifier for staging tables
            verifier = MigrationVerifier(
                database_name=self.database_name,
                source_path=self.source_path,
                target_connection=self.target_connection,
            )

            # Run verification
            report = await verifier.verify_all()

            self.state['verification_passed'] = report.passed
            self.state['verification_report'] = report.to_dict()
            self.state['phase'] = 'verified' if report.passed else 'verification_failed'
            self._save_state()

            if report.passed:
                logger.info("Verification PASSED")
            else:
                logger.warning("Verification FAILED")
                report.print_report()

            return report.passed

        except Exception as e:
            self.state['errors'].append({
                'phase': 'verify',
                'error': str(e),
                'timestamp': datetime.now().isoformat(),
            })
            self._save_state()
            logger.error(f"Verification failed: {e}")
            return False

    async def promote(self) -> bool:
        """
        Promote staging tables to production.

        Only proceeds if verification passed.

        Returns:
            True if promotion successful
        """
        logger.info("Phase 4: Promoting staging to production...")

        if not self.state['verification_passed']:
            logger.error("Cannot promote - verification did not pass")
            return False

        try:
            import asyncpg

            conn = await asyncpg.connect(self.target_connection)

            try:
                # Rename staging tables to production
                await self._promote_staging_tables(conn)

                self.state['promoted'] = True
                self.state['phase'] = 'promoted'
                self.state['promoted_at'] = datetime.now().isoformat()
                self._save_state()

                logger.info("Promotion complete - data is now in production tables")
                return True

            finally:
                await conn.close()

        except Exception as e:
            self.state['errors'].append({
                'phase': 'promote',
                'error': str(e),
                'timestamp': datetime.now().isoformat(),
            })
            self._save_state()
            logger.error(f"Promotion failed: {e}")
            return False

    async def rollback(self) -> bool:
        """
        Rollback migration - restore from backup.

        Returns:
            True if rollback successful
        """
        logger.info("Rolling back migration...")

        backup_id = self.state.get('backup_id')
        if not backup_id:
            logger.error("No backup found to restore from")
            return False

        try:
            # Drop staging tables
            await self._cleanup_staging()

            # Restore from backup
            success = self.backup.restore_backup(backup_id)

            if success:
                self.state['phase'] = 'rolled_back'
                self._save_state()
                logger.info("Rollback complete")

            return success

        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            return False

    async def _create_staging_tables(self, conn) -> None:
        """Create staging tables in PostgreSQL."""
        prefix = self.staging_prefix

        # Detect embedding dimension from source data
        embedding_dim = self._detect_embedding_dimension()

        # Create staging tables with prefix
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS hybridrag_kv_store{prefix} (
                id SERIAL PRIMARY KEY,
                workspace VARCHAR(255) NOT NULL,
                key VARCHAR(512) NOT NULL,
                value JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(workspace, key)
            )
        """)

        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS hybridrag_graph_edges{prefix} (
                id SERIAL PRIMARY KEY,
                workspace VARCHAR(255) NOT NULL,
                source_id VARCHAR(512) NOT NULL,
                target_id VARCHAR(512) NOT NULL,
                properties JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(workspace, source_id, target_id)
            )
        """)

        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS hybridrag_chunks{prefix} (
                id SERIAL PRIMARY KEY,
                workspace VARCHAR(255) NOT NULL,
                chunk_id VARCHAR(512) NOT NULL,
                content TEXT,
                metadata JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(workspace, chunk_id)
            )
        """)

        # Check if vector extension exists and add embedding column
        try:
            await conn.execute(f"""
                ALTER TABLE hybridrag_chunks{prefix}
                ADD COLUMN IF NOT EXISTS embedding vector({embedding_dim})
            """)
            logger.info(f"Added vector column with dimension {embedding_dim}")
        except Exception:
            logger.warning("Could not add vector column - pgvector may not be installed")

        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS hybridrag_doc_status{prefix} (
                id SERIAL PRIMARY KEY,
                workspace VARCHAR(255) NOT NULL,
                doc_id VARCHAR(512) NOT NULL,
                status_data JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(workspace, doc_id)
            )
        """)

        logger.debug("Staging tables created")

    async def _migrate_entities_to_staging(self, conn) -> None:
        """Migrate entities to staging table."""
        entities_file = self.source_path / 'kv_store_full_docs.json'
        if not entities_file.exists():
            return

        with open(entities_file, 'r') as f:
            data = json.load(f)

        prefix = self.staging_prefix
        workspace = self.database_name

        for key, value in data.items():
            await conn.execute(f"""
                INSERT INTO hybridrag_kv_store{prefix} (workspace, key, value)
                VALUES ($1, $2, $3)
                ON CONFLICT (workspace, key) DO UPDATE SET value = EXCLUDED.value
            """, workspace, key, json.dumps(value) if isinstance(value, dict) else value)

        logger.debug(f"Migrated {len(data)} entities to staging")

    async def _migrate_relations_to_staging(self, conn) -> None:
        """Migrate relations to staging table."""
        graph_file = self.source_path / 'graph_chunk_entity_relation.graphml'
        if not graph_file.exists():
            return

        try:
            import networkx as nx
            graph = nx.read_graphml(graph_file)
        except ImportError:
            logger.warning("networkx not installed, skipping relations")
            return

        prefix = self.staging_prefix
        workspace = self.database_name

        for source, target, data in graph.edges(data=True):
            await conn.execute(f"""
                INSERT INTO hybridrag_graph_edges{prefix} (workspace, source_id, target_id, properties)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (workspace, source_id, target_id) DO UPDATE SET properties = EXCLUDED.properties
            """, workspace, source, target, json.dumps(data))

        logger.debug(f"Migrated {graph.number_of_edges()} relations to staging")

    async def _migrate_chunks_to_staging(self, conn) -> None:
        """Migrate chunks to staging table."""
        chunks_file = self.source_path / 'vdb_chunks.json'
        if not chunks_file.exists():
            return

        with open(chunks_file, 'r') as f:
            data = json.load(f)

        prefix = self.staging_prefix
        workspace = self.database_name
        chunks = data.get('data', [])

        for chunk in chunks:
            chunk_id = chunk.get('__id__', '')
            content = chunk.get('content', '')
            embedding = chunk.get('__vector__')
            metadata = {k: v for k, v in chunk.items() if k not in ('__id__', '__vector__', 'content')}

            if embedding:
                await conn.execute(f"""
                    INSERT INTO hybridrag_chunks{prefix} (workspace, chunk_id, content, embedding, metadata)
                    VALUES ($1, $2, $3, $4::vector, $5)
                    ON CONFLICT (workspace, chunk_id) DO UPDATE SET
                        content = EXCLUDED.content, embedding = EXCLUDED.embedding, metadata = EXCLUDED.metadata
                """, workspace, chunk_id, content, embedding, json.dumps(metadata))
            else:
                await conn.execute(f"""
                    INSERT INTO hybridrag_chunks{prefix} (workspace, chunk_id, content, metadata)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (workspace, chunk_id) DO UPDATE SET
                        content = EXCLUDED.content, metadata = EXCLUDED.metadata
                """, workspace, chunk_id, content, json.dumps(metadata))

        logger.debug(f"Migrated {len(chunks)} chunks to staging")

    async def _migrate_docs_to_staging(self, conn) -> None:
        """Migrate doc status to staging table."""
        docs_file = self.source_path / 'kv_store_doc_status.json'
        if not docs_file.exists():
            return

        with open(docs_file, 'r') as f:
            data = json.load(f)

        prefix = self.staging_prefix
        workspace = self.database_name

        for doc_id, status_data in data.items():
            await conn.execute(f"""
                INSERT INTO hybridrag_doc_status{prefix} (workspace, doc_id, status_data)
                VALUES ($1, $2, $3)
                ON CONFLICT (workspace, doc_id) DO UPDATE SET status_data = EXCLUDED.status_data
            """, workspace, doc_id, json.dumps(status_data))

        logger.debug(f"Migrated {len(data)} doc statuses to staging")

    async def _promote_staging_tables(self, conn) -> None:
        """Rename staging tables to production names."""
        prefix = self.staging_prefix
        tables = ['hybridrag_kv_store', 'hybridrag_graph_edges', 'hybridrag_chunks', 'hybridrag_doc_status']

        async with conn.transaction():
            for table in tables:
                # Drop old production table if exists
                await conn.execute(f"DROP TABLE IF EXISTS {table}_old")

                # Rename current production to old (if exists)
                try:
                    await conn.execute(f"ALTER TABLE IF EXISTS {table} RENAME TO {table}_old")
                except Exception:
                    pass  # Table might not exist

                # Rename staging to production
                await conn.execute(f"ALTER TABLE {table}{prefix} RENAME TO {table}")

        logger.info("Staging tables promoted to production")

    async def _cleanup_staging(self) -> None:
        """Drop staging tables."""
        try:
            import asyncpg
            conn = await asyncpg.connect(self.target_connection)

            try:
                prefix = self.staging_prefix
                tables = ['hybridrag_kv_store', 'hybridrag_graph_edges', 'hybridrag_chunks', 'hybridrag_doc_status']

                for table in tables:
                    await conn.execute(f"DROP TABLE IF EXISTS {table}{prefix}")

                logger.debug("Staging tables cleaned up")

            finally:
                await conn.close()

        except Exception as e:
            logger.warning(f"Could not cleanup staging: {e}")
