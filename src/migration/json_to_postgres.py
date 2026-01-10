"""
JSON to PostgreSQL Migration (T021, T022)
==========================================

Migrates HybridRAG data from JSON file storage to PostgreSQL with pgvector.
Supports checkpoint/resume for large migrations.

Usage:
    job = MigrationJob(
        source_path='/path/to/json/db',
        target_config=BackendConfig(...),
        checkpoint_file='/path/to/checkpoint.json'
    )
    result = await job.run()
"""

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Callable

if TYPE_CHECKING:
    from ..config.config import BackendConfig

logger = logging.getLogger(__name__)


class MigrationStatus(str, Enum):
    """Status of a migration job."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class MigrationCheckpoint:
    """
    Tracks migration progress for resumable migrations (T022).

    Saved to a JSON file after each batch to enable resume.
    """
    job_id: str
    source_path: str
    target_workspace: str
    status: MigrationStatus = MigrationStatus.PENDING
    started_at: Optional[str] = None
    updated_at: Optional[str] = None
    completed_at: Optional[str] = None

    # Progress tracking by storage type
    entities_migrated: int = 0
    entities_total: int = 0
    relations_migrated: int = 0
    relations_total: int = 0
    chunks_migrated: int = 0
    chunks_total: int = 0
    docs_migrated: int = 0
    docs_total: int = 0

    # Error tracking
    errors: List[Dict[str, Any]] = field(default_factory=list)
    last_error: Optional[str] = None

    # Batch tracking for resume
    last_entity_id: Optional[str] = None
    last_relation_id: Optional[str] = None
    last_chunk_id: Optional[str] = None
    last_doc_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = asdict(self)
        result['status'] = self.status.value
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MigrationCheckpoint':
        """Create from dictionary."""
        if 'status' in data:
            data['status'] = MigrationStatus(data['status'])
        return cls(**data)

    def save(self, filepath: Path) -> None:
        """Save checkpoint to file."""
        self.updated_at = datetime.now().isoformat()
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, filepath: Path) -> Optional['MigrationCheckpoint']:
        """Load checkpoint from file if exists."""
        if not filepath.exists():
            return None
        with open(filepath, 'r') as f:
            return cls.from_dict(json.load(f))


@dataclass
class MigrationResult:
    """Result of a migration job."""
    success: bool
    status: MigrationStatus
    checkpoint: MigrationCheckpoint
    duration_seconds: float
    message: str
    verification_passed: Optional[bool] = None


class MigrationJob:
    """
    Orchestrates migration from JSON to PostgreSQL backend (T021).

    Features:
    - Batch processing with configurable batch size
    - Checkpoint/resume support (T022)
    - Progress callbacks for UI updates
    - Error handling with continuation option
    """

    def __init__(
        self,
        source_path: str,
        target_config: 'BackendConfig',
        checkpoint_file: Optional[str] = None,
        batch_size: int = 100,
        continue_on_error: bool = True,
        progress_callback: Optional[Callable[[MigrationCheckpoint], None]] = None
    ):
        """
        Initialize migration job.

        Args:
            source_path: Path to JSON database directory
            target_config: BackendConfig for PostgreSQL target
            checkpoint_file: Path to checkpoint file for resume support
            batch_size: Number of records per batch
            continue_on_error: Whether to continue on individual record errors
            progress_callback: Callback for progress updates
        """
        self.source_path = Path(source_path)
        self.target_config = target_config
        self.batch_size = batch_size
        self.continue_on_error = continue_on_error
        self.progress_callback = progress_callback

        # Set up checkpoint file
        if checkpoint_file:
            self.checkpoint_file = Path(checkpoint_file)
        else:
            self.checkpoint_file = self.source_path / '.migration_checkpoint.json'

        # Initialize or load checkpoint
        self.checkpoint = MigrationCheckpoint.load(self.checkpoint_file)
        if not self.checkpoint:
            import uuid
            self.checkpoint = MigrationCheckpoint(
                job_id=str(uuid.uuid4())[:8],
                source_path=str(self.source_path),
                target_workspace=target_config.postgres_workspace
            )

        # Will be initialized in run()
        self._pg_conn = None
        self._cancelled = False

    def cancel(self) -> None:
        """Request cancellation of the migration."""
        self._cancelled = True
        self.checkpoint.status = MigrationStatus.CANCELLED
        self.checkpoint.save(self.checkpoint_file)

    async def run(self, verify: bool = True) -> MigrationResult:
        """
        Execute the migration.

        Args:
            verify: Whether to verify data after migration

        Returns:
            MigrationResult with status and statistics
        """
        start_time = time.time()

        try:
            # Validate source
            if not self.source_path.exists():
                return MigrationResult(
                    success=False,
                    status=MigrationStatus.FAILED,
                    checkpoint=self.checkpoint,
                    duration_seconds=time.time() - start_time,
                    message=f"Source path not found: {self.source_path}"
                )

            # Initialize checkpoint if new
            if self.checkpoint.status == MigrationStatus.PENDING:
                self.checkpoint.status = MigrationStatus.IN_PROGRESS
                self.checkpoint.started_at = datetime.now().isoformat()
                await self._count_source_records()
                self.checkpoint.save(self.checkpoint_file)

            logger.info(f"Starting migration job {self.checkpoint.job_id}")
            logger.info(f"Source: {self.source_path}")
            logger.info(f"Target workspace: {self.checkpoint.target_workspace}")

            # Connect to PostgreSQL
            await self._connect_postgres()

            try:
                # Migrate each storage type
                await self._migrate_entities()
                if self._cancelled:
                    return self._create_result(start_time, "Migration cancelled by user")

                await self._migrate_relations()
                if self._cancelled:
                    return self._create_result(start_time, "Migration cancelled by user")

                await self._migrate_chunks()
                if self._cancelled:
                    return self._create_result(start_time, "Migration cancelled by user")

                await self._migrate_docs()
                if self._cancelled:
                    return self._create_result(start_time, "Migration cancelled by user")

                # Mark complete
                self.checkpoint.status = MigrationStatus.COMPLETED
                self.checkpoint.completed_at = datetime.now().isoformat()
                self.checkpoint.save(self.checkpoint_file)

                # Verify if requested
                verification_passed = None
                if verify:
                    from .verify import MigrationVerifier
                    verifier = MigrationVerifier(
                        source_path=str(self.source_path),
                        target_config=self.target_config
                    )
                    verification_passed = await verifier.verify_counts()

                result = self._create_result(
                    start_time,
                    "Migration completed successfully",
                    verification_passed
                )
                logger.info(f"Migration completed in {result.duration_seconds:.1f}s")
                return result

            finally:
                await self._disconnect_postgres()

        except Exception as e:
            self.checkpoint.status = MigrationStatus.FAILED
            self.checkpoint.last_error = str(e)
            self.checkpoint.errors.append({
                'timestamp': datetime.now().isoformat(),
                'error': str(e),
                'type': type(e).__name__
            })
            self.checkpoint.save(self.checkpoint_file)
            logger.error(f"Migration failed: {e}")

            return MigrationResult(
                success=False,
                status=MigrationStatus.FAILED,
                checkpoint=self.checkpoint,
                duration_seconds=time.time() - start_time,
                message=f"Migration failed: {e}"
            )

    def _create_result(
        self,
        start_time: float,
        message: str,
        verification_passed: Optional[bool] = None
    ) -> MigrationResult:
        """Create migration result."""
        return MigrationResult(
            success=self.checkpoint.status == MigrationStatus.COMPLETED,
            status=self.checkpoint.status,
            checkpoint=self.checkpoint,
            duration_seconds=time.time() - start_time,
            message=message,
            verification_passed=verification_passed
        )

    async def _count_source_records(self) -> None:
        """Count total records in source for progress tracking."""
        # Count entities
        entities_file = self.source_path / 'kv_store_full_docs.json'
        if entities_file.exists():
            with open(entities_file) as f:
                data = json.load(f)
                self.checkpoint.entities_total = len(data)

        # Count relations (from graph)
        graph_file = self.source_path / 'graph_chunk_entity_relation.graphml'
        if graph_file.exists():
            import re
            with open(graph_file) as f:
                content = f.read()
                edges = re.findall(r'<edge', content)
                self.checkpoint.relations_total = len(edges)

        # Count chunks
        chunks_file = self.source_path / 'vdb_chunks.json'
        if chunks_file.exists():
            with open(chunks_file) as f:
                data = json.load(f)
                self.checkpoint.chunks_total = len(data.get('data', []))

        # Count docs
        docs_file = self.source_path / 'kv_store_doc_status.json'
        if docs_file.exists():
            with open(docs_file) as f:
                data = json.load(f)
                self.checkpoint.docs_total = len(data)

        logger.info(f"Source counts - Entities: {self.checkpoint.entities_total}, "
                   f"Relations: {self.checkpoint.relations_total}, "
                   f"Chunks: {self.checkpoint.chunks_total}, "
                   f"Docs: {self.checkpoint.docs_total}")

    async def _connect_postgres(self) -> None:
        """Connect to PostgreSQL."""
        try:
            import asyncpg
        except ImportError:
            raise RuntimeError("asyncpg not installed. Install with: pip install asyncpg")

        conn_str = self.target_config.get_connection_string()
        self._pg_conn = await asyncpg.connect(conn_str)
        logger.debug("Connected to PostgreSQL")

    async def _disconnect_postgres(self) -> None:
        """Disconnect from PostgreSQL."""
        if self._pg_conn:
            await self._pg_conn.close()
            self._pg_conn = None
            logger.debug("Disconnected from PostgreSQL")

    async def _migrate_entities(self) -> None:
        """Migrate entities from JSON to PostgreSQL."""
        entities_file = self.source_path / 'kv_store_full_docs.json'
        if not entities_file.exists():
            logger.info("No entities file found, skipping")
            return

        logger.info("Migrating entities...")
        with open(entities_file) as f:
            data = json.load(f)

        workspace = self.checkpoint.target_workspace
        batch = []

        for key, value in data.items():
            if self._cancelled:
                break

            # Skip if already migrated (resume support)
            if (self.checkpoint.last_entity_id and
                key <= self.checkpoint.last_entity_id):
                continue

            batch.append((key, json.dumps(value) if isinstance(value, dict) else value))

            if len(batch) >= self.batch_size:
                await self._insert_entity_batch(batch, workspace)
                self.checkpoint.entities_migrated += len(batch)
                self.checkpoint.last_entity_id = batch[-1][0]
                self.checkpoint.save(self.checkpoint_file)
                self._notify_progress()
                batch = []

        # Insert remaining
        if batch and not self._cancelled:
            await self._insert_entity_batch(batch, workspace)
            self.checkpoint.entities_migrated += len(batch)
            self.checkpoint.last_entity_id = batch[-1][0]
            self.checkpoint.save(self.checkpoint_file)
            self._notify_progress()

        logger.info(f"Migrated {self.checkpoint.entities_migrated} entities")

    async def _insert_entity_batch(self, batch: List[tuple], workspace: str) -> None:
        """Insert a batch of entities into PostgreSQL."""
        await self._pg_conn.executemany(
            """
            INSERT INTO lightrag_entities (workspace, entity_id, content)
            VALUES ($1, $2, $3)
            ON CONFLICT (workspace, entity_id) DO UPDATE SET content = EXCLUDED.content
            """,
            [(workspace, key, value) for key, value in batch]
        )

    async def _migrate_relations(self) -> None:
        """Migrate relations from graph file to PostgreSQL."""
        graph_file = self.source_path / 'graph_chunk_entity_relation.graphml'
        if not graph_file.exists():
            logger.info("No graph file found, skipping relations")
            return

        logger.info("Migrating relations...")

        try:
            import networkx as nx
            graph = nx.read_graphml(graph_file)
        except ImportError:
            logger.warning("networkx not installed, skipping relation migration")
            return

        workspace = self.checkpoint.target_workspace
        batch = []

        for idx, (source, target, data) in enumerate(graph.edges(data=True)):
            if self._cancelled:
                break

            edge_id = f"{source}_{target}"

            # Skip if already migrated
            if (self.checkpoint.last_relation_id and
                edge_id <= self.checkpoint.last_relation_id):
                continue

            batch.append((source, target, json.dumps(data)))

            if len(batch) >= self.batch_size:
                await self._insert_relation_batch(batch, workspace)
                self.checkpoint.relations_migrated += len(batch)
                self.checkpoint.last_relation_id = edge_id
                self.checkpoint.save(self.checkpoint_file)
                self._notify_progress()
                batch = []

        if batch and not self._cancelled:
            await self._insert_relation_batch(batch, workspace)
            self.checkpoint.relations_migrated += len(batch)
            self.checkpoint.save(self.checkpoint_file)
            self._notify_progress()

        logger.info(f"Migrated {self.checkpoint.relations_migrated} relations")

    async def _insert_relation_batch(self, batch: List[tuple], workspace: str) -> None:
        """Insert a batch of relations into PostgreSQL."""
        await self._pg_conn.executemany(
            """
            INSERT INTO lightrag_relations (workspace, source_id, target_id, properties)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (workspace, source_id, target_id)
            DO UPDATE SET properties = EXCLUDED.properties
            """,
            [(workspace, src, tgt, props) for src, tgt, props in batch]
        )

    async def _migrate_chunks(self) -> None:
        """Migrate vector chunks from NanoVectorDB to PostgreSQL pgvector."""
        chunks_file = self.source_path / 'vdb_chunks.json'
        if not chunks_file.exists():
            logger.info("No chunks file found, skipping")
            return

        logger.info("Migrating chunks with embeddings...")
        with open(chunks_file) as f:
            data = json.load(f)

        workspace = self.checkpoint.target_workspace
        chunks = data.get('data', [])
        batch = []

        for idx, chunk in enumerate(chunks):
            if self._cancelled:
                break

            chunk_id = chunk.get('__id__', str(idx))

            # Skip if already migrated
            if (self.checkpoint.last_chunk_id and
                chunk_id <= self.checkpoint.last_chunk_id):
                continue

            embedding = chunk.get('__vector__', [])
            content = chunk.get('content', '')
            metadata = {k: v for k, v in chunk.items()
                       if k not in ('__id__', '__vector__', 'content')}

            batch.append((chunk_id, content, embedding, json.dumps(metadata)))

            if len(batch) >= self.batch_size:
                await self._insert_chunk_batch(batch, workspace)
                self.checkpoint.chunks_migrated += len(batch)
                self.checkpoint.last_chunk_id = batch[-1][0]
                self.checkpoint.save(self.checkpoint_file)
                self._notify_progress()
                batch = []

        if batch and not self._cancelled:
            await self._insert_chunk_batch(batch, workspace)
            self.checkpoint.chunks_migrated += len(batch)
            self.checkpoint.save(self.checkpoint_file)
            self._notify_progress()

        logger.info(f"Migrated {self.checkpoint.chunks_migrated} chunks")

    async def _insert_chunk_batch(self, batch: List[tuple], workspace: str) -> None:
        """Insert a batch of chunks with embeddings into PostgreSQL."""
        await self._pg_conn.executemany(
            """
            INSERT INTO lightrag_chunks (workspace, chunk_id, content, embedding, metadata)
            VALUES ($1, $2, $3, $4::vector, $5)
            ON CONFLICT (workspace, chunk_id)
            DO UPDATE SET content = EXCLUDED.content,
                         embedding = EXCLUDED.embedding,
                         metadata = EXCLUDED.metadata
            """,
            [(workspace, cid, content, emb, meta) for cid, content, emb, meta in batch]
        )

    async def _migrate_docs(self) -> None:
        """Migrate document status records to PostgreSQL."""
        docs_file = self.source_path / 'kv_store_doc_status.json'
        if not docs_file.exists():
            logger.info("No docs status file found, skipping")
            return

        logger.info("Migrating document status...")
        with open(docs_file) as f:
            data = json.load(f)

        workspace = self.checkpoint.target_workspace
        batch = []

        for doc_id, doc_data in data.items():
            if self._cancelled:
                break

            # Skip if already migrated
            if (self.checkpoint.last_doc_id and
                doc_id <= self.checkpoint.last_doc_id):
                continue

            batch.append((doc_id, json.dumps(doc_data)))

            if len(batch) >= self.batch_size:
                await self._insert_doc_batch(batch, workspace)
                self.checkpoint.docs_migrated += len(batch)
                self.checkpoint.last_doc_id = batch[-1][0]
                self.checkpoint.save(self.checkpoint_file)
                self._notify_progress()
                batch = []

        if batch and not self._cancelled:
            await self._insert_doc_batch(batch, workspace)
            self.checkpoint.docs_migrated += len(batch)
            self.checkpoint.save(self.checkpoint_file)
            self._notify_progress()

        logger.info(f"Migrated {self.checkpoint.docs_migrated} documents")

    async def _insert_doc_batch(self, batch: List[tuple], workspace: str) -> None:
        """Insert a batch of document status records into PostgreSQL."""
        await self._pg_conn.executemany(
            """
            INSERT INTO lightrag_doc_status (workspace, doc_id, status_data)
            VALUES ($1, $2, $3)
            ON CONFLICT (workspace, doc_id) DO UPDATE SET status_data = EXCLUDED.status_data
            """,
            [(workspace, doc_id, data) for doc_id, data in batch]
        )

    def _notify_progress(self) -> None:
        """Notify progress callback if set."""
        if self.progress_callback:
            self.progress_callback(self.checkpoint)
