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
import base64
import zlib
import struct
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Callable

if TYPE_CHECKING:
    from ..config.config import BackendConfig

logger = logging.getLogger(__name__)


def _decode_embedding(encoded_vector: Optional[str]) -> Optional[List[float]]:
    """
    Decode a base64+zlib encoded embedding vector.

    The HybridRAG/LightRAG format stores embeddings as:
    - Base64 encoded string
    - Zlib compressed
    - Float32 packed binary

    Args:
        encoded_vector: Base64 encoded string or None

    Returns:
        List of floats or None if decoding fails
    """
    if not encoded_vector or not isinstance(encoded_vector, str):
        return None

    try:
        # Decode base64
        decoded = base64.b64decode(encoded_vector)

        # Decompress zlib
        decompressed = zlib.decompress(decoded)

        # Unpack as float32 array
        num_floats = len(decompressed) // 4
        embedding = list(struct.unpack(f'{num_floats}f', decompressed[:num_floats * 4]))

        return embedding

    except Exception as e:
        logger.debug(f"Could not decode embedding: {e}")
        return None


def _decode_matrix(matrix_str: str, embedding_dim: int) -> Optional[List[List[float]]]:
    """
    Decode the matrix field from nano-vectordb JSON format.

    The nano-vectordb stores ALL embeddings in a single 'matrix' field as:
    - Base64 encoded numpy float32 array
    - Reshaped to (num_entities, embedding_dim)

    Args:
        matrix_str: Base64 encoded matrix string
        embedding_dim: Expected embedding dimension

    Returns:
        List of embedding lists, or None if decoding fails
    """
    if not matrix_str or not isinstance(matrix_str, str):
        return None

    try:
        import numpy as np

        # Decode base64 to bytes
        decoded = base64.b64decode(matrix_str)

        # Convert to numpy float32 array
        arr = np.frombuffer(decoded, dtype=np.float32)

        # Reshape to embeddings matrix
        num_embeddings = len(arr) // embedding_dim
        matrix = arr.reshape(num_embeddings, embedding_dim)

        # Convert to list of lists
        return [row.tolist() for row in matrix]

    except Exception as e:
        logger.error(f"Could not decode matrix: {e}")
        return None


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
    text_chunks_migrated: int = 0
    text_chunks_total: int = 0
    graph_nodes_migrated: int = 0
    graph_nodes_total: int = 0
    graph_edges_migrated: int = 0
    graph_edges_total: int = 0
    llm_cache_migrated: int = 0
    llm_cache_total: int = 0

    # Error tracking
    errors: List[Dict[str, Any]] = field(default_factory=list)
    last_error: Optional[str] = None

    # Batch tracking for resume
    last_entity_id: Optional[str] = None
    last_relation_id: Optional[str] = None
    last_chunk_id: Optional[str] = None
    last_doc_id: Optional[str] = None
    last_text_chunk_id: Optional[str] = None
    last_llm_cache_id: Optional[str] = None
    graph_migration_complete: bool = False

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

                await self._migrate_text_chunks()
                if self._cancelled:
                    return self._create_result(start_time, "Migration cancelled by user")

                await self._migrate_llm_cache()
                if self._cancelled:
                    return self._create_result(start_time, "Migration cancelled by user")

                await self._migrate_age_graph()
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

        # Count text chunks
        text_chunks_file = self.source_path / 'kv_store_text_chunks.json'
        if text_chunks_file.exists():
            with open(text_chunks_file) as f:
                data = json.load(f)
                self.checkpoint.text_chunks_total = len(data)

        # Count graph nodes and edges
        graph_file = self.source_path / 'graph_chunk_entity_relation.graphml'
        if graph_file.exists():
            try:
                import networkx as nx
                G = nx.read_graphml(graph_file)
                self.checkpoint.graph_nodes_total = G.number_of_nodes()
                self.checkpoint.graph_edges_total = G.number_of_edges()
            except ImportError:
                logger.warning("networkx not installed, cannot count graph nodes/edges")

        # Count LLM response cache
        llm_cache_file = self.source_path / 'kv_store_llm_response_cache.json'
        if llm_cache_file.exists():
            with open(llm_cache_file) as f:
                data = json.load(f)
                self.checkpoint.llm_cache_total = len(data)

        logger.info(f"Source counts - Entities: {self.checkpoint.entities_total}, "
                   f"Relations: {self.checkpoint.relations_total}, "
                   f"Chunks: {self.checkpoint.chunks_total}, "
                   f"Docs: {self.checkpoint.docs_total}, "
                   f"TextChunks: {self.checkpoint.text_chunks_total}, "
                   f"GraphNodes: {self.checkpoint.graph_nodes_total}, "
                   f"GraphEdges: {self.checkpoint.graph_edges_total}, "
                   f"LLMCache: {self.checkpoint.llm_cache_total}")

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
        embedding_dim = data.get('embedding_dim', 1536)

        # CRITICAL: Decode embeddings from matrix field (not individual vector fields)
        # nano-vectordb stores all embeddings in a single base64-encoded matrix
        matrix_str = data.get('matrix', '')
        embeddings_matrix = _decode_matrix(matrix_str, embedding_dim)

        if embeddings_matrix:
            logger.info(f"Decoded {len(embeddings_matrix)} embeddings from matrix field")
        else:
            logger.warning("Could not decode matrix field, falling back to individual vectors")
            embeddings_matrix = None

        batch = []

        for idx, chunk in enumerate(chunks):
            if self._cancelled:
                break

            chunk_id = chunk.get('__id__', str(idx))

            # Skip if already migrated
            if (self.checkpoint.last_chunk_id and
                chunk_id <= self.checkpoint.last_chunk_id):
                continue

            # Get embedding from matrix (by index) or fall back to individual field
            if embeddings_matrix and idx < len(embeddings_matrix):
                embedding = embeddings_matrix[idx]
            else:
                # Fallback: try individual vector field
                encoded_vector = chunk.get('vector', '')
                embedding = _decode_embedding(encoded_vector)
                if embedding is None:
                    embedding = chunk.get('__vector__', [])

            content = chunk.get('content', '')
            metadata = {k: v for k, v in chunk.items()
                       if k not in ('__id__', '__vector__', 'vector', 'content')}

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

    async def _migrate_text_chunks(self) -> None:
        """Migrate text chunks (kv_store_text_chunks.json) to lightrag_doc_chunks table."""
        text_chunks_file = self.source_path / 'kv_store_text_chunks.json'
        if not text_chunks_file.exists():
            logger.info("No text chunks file found, skipping")
            return

        logger.info("Migrating text chunks...")
        with open(text_chunks_file) as f:
            data = json.load(f)

        workspace = self.checkpoint.target_workspace
        batch = []

        for chunk_id, chunk_data in data.items():
            if self._cancelled:
                break

            # Skip if already migrated (resume support)
            if (self.checkpoint.last_text_chunk_id and
                chunk_id <= self.checkpoint.last_text_chunk_id):
                continue

            # Extract fields from chunk data
            if isinstance(chunk_data, dict):
                tokens = chunk_data.get('tokens', 0)
                content = chunk_data.get('content', '')
                full_doc_id = chunk_data.get('full_doc_id', '')
                chunk_order_index = chunk_data.get('chunk_order_index', 0)
                file_path = chunk_data.get('file_path')
                llm_cache_list = json.dumps(chunk_data.get('llm_cache_list', []))
            else:
                # Simple string content
                tokens = 0
                content = str(chunk_data)
                full_doc_id = ''
                chunk_order_index = 0
                file_path = None
                llm_cache_list = '[]'

            batch.append((
                chunk_id, workspace, full_doc_id, chunk_order_index,
                tokens, content, file_path, llm_cache_list
            ))

            if len(batch) >= self.batch_size:
                await self._insert_text_chunk_batch(batch)
                self.checkpoint.text_chunks_migrated += len(batch)
                self.checkpoint.last_text_chunk_id = batch[-1][0]
                self.checkpoint.save(self.checkpoint_file)
                self._notify_progress()
                batch = []

        # Insert remaining
        if batch and not self._cancelled:
            await self._insert_text_chunk_batch(batch)
            self.checkpoint.text_chunks_migrated += len(batch)
            self.checkpoint.last_text_chunk_id = batch[-1][0]
            self.checkpoint.save(self.checkpoint_file)
            self._notify_progress()

        logger.info(f"Migrated {self.checkpoint.text_chunks_migrated} text chunks")

    async def _insert_text_chunk_batch(self, batch: List[tuple]) -> None:
        """Insert a batch of text chunks into lightrag_doc_chunks table."""
        await self._pg_conn.executemany(
            """
            INSERT INTO lightrag_doc_chunks (id, workspace, full_doc_id, chunk_order_index,
                                            tokens, content, file_path, llm_cache_list)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
            ON CONFLICT (id, workspace) DO UPDATE SET
                full_doc_id = EXCLUDED.full_doc_id,
                chunk_order_index = EXCLUDED.chunk_order_index,
                tokens = EXCLUDED.tokens,
                content = EXCLUDED.content,
                file_path = EXCLUDED.file_path,
                llm_cache_list = EXCLUDED.llm_cache_list
            """,
            batch
        )

    async def _migrate_llm_cache(self) -> None:
        """Migrate LLM response cache (kv_store_llm_response_cache.json) to lightrag_llm_cache table."""
        llm_cache_file = self.source_path / 'kv_store_llm_response_cache.json'
        if not llm_cache_file.exists():
            logger.info("No LLM response cache file found, skipping")
            return

        logger.info("Migrating LLM response cache...")
        with open(llm_cache_file) as f:
            data = json.load(f)

        workspace = self.checkpoint.target_workspace
        batch = []

        for cache_id, cache_data in data.items():
            if self._cancelled:
                break

            # Skip if already migrated (resume support)
            if (self.checkpoint.last_llm_cache_id and
                cache_id <= self.checkpoint.last_llm_cache_id):
                continue

            # Extract fields from cache data
            if isinstance(cache_data, dict):
                original_prompt = cache_data.get('original_prompt', '')
                return_value = cache_data.get('return', '')
                chunk_id = cache_data.get('chunk_id')
                cache_type = cache_data.get('cache_type', '')
                queryparam = json.dumps(cache_data.get('queryparam')) if cache_data.get('queryparam') else None

                # Convert timestamps
                create_time = cache_data.get('create_time')
                update_time = cache_data.get('update_time')
                if isinstance(create_time, (int, float)):
                    from datetime import datetime as dt
                    create_time = dt.fromtimestamp(create_time)
                else:
                    create_time = None
                if isinstance(update_time, (int, float)):
                    from datetime import datetime as dt
                    update_time = dt.fromtimestamp(update_time)
                else:
                    update_time = None
            else:
                # Simple string value
                original_prompt = ''
                return_value = str(cache_data)
                chunk_id = None
                cache_type = ''
                queryparam = None
                create_time = None
                update_time = None

            batch.append((
                workspace, cache_id, original_prompt, return_value,
                chunk_id, cache_type, queryparam, create_time, update_time
            ))

            if len(batch) >= self.batch_size:
                await self._insert_llm_cache_batch(batch)
                self.checkpoint.llm_cache_migrated += len(batch)
                self.checkpoint.last_llm_cache_id = batch[-1][1]
                self.checkpoint.save(self.checkpoint_file)
                self._notify_progress()
                batch = []

        # Insert remaining
        if batch and not self._cancelled:
            await self._insert_llm_cache_batch(batch)
            self.checkpoint.llm_cache_migrated += len(batch)
            self.checkpoint.last_llm_cache_id = batch[-1][1]
            self.checkpoint.save(self.checkpoint_file)
            self._notify_progress()

        logger.info(f"Migrated {self.checkpoint.llm_cache_migrated} LLM cache entries")

    async def _insert_llm_cache_batch(self, batch: List[tuple]) -> None:
        """Insert a batch of LLM cache entries into lightrag_llm_cache table."""
        await self._pg_conn.executemany(
            """
            INSERT INTO lightrag_llm_cache (workspace, id, original_prompt, return_value,
                                           chunk_id, cache_type, queryparam, create_time, update_time)
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9)
            ON CONFLICT (workspace, id) DO UPDATE SET
                original_prompt = EXCLUDED.original_prompt,
                return_value = EXCLUDED.return_value,
                chunk_id = EXCLUDED.chunk_id,
                cache_type = EXCLUDED.cache_type,
                queryparam = EXCLUDED.queryparam,
                update_time = EXCLUDED.update_time
            """,
            batch
        )

    async def _migrate_age_graph(self) -> None:
        """
        Migrate GraphML to Apache AGE knowledge graph.

        This is CRITICAL for LightRAG queries - the graph must be in AGE
        for Cypher queries to work. Uses direct table inserts for performance.
        """
        if self.checkpoint.graph_migration_complete:
            logger.info("Graph migration already complete, skipping")
            return

        graph_file = self.source_path / 'graph_chunk_entity_relation.graphml'
        if not graph_file.exists():
            logger.info("No GraphML file found, skipping AGE graph migration")
            return

        try:
            import networkx as nx
        except ImportError:
            logger.error("networkx not installed, cannot migrate graph. Install with: pip install networkx")
            return

        logger.info("Migrating GraphML to Apache AGE...")
        G = nx.read_graphml(graph_file)
        total_nodes = G.number_of_nodes()
        total_edges = G.number_of_edges()
        logger.info(f"Graph has {total_nodes:,} nodes and {total_edges:,} edges")

        # Graph name matches the workspace/source
        graph_name = "chunk_entity_relation"

        try:
            # Setup AGE extension
            await self._pg_conn.execute("LOAD 'age';")
            await self._pg_conn.execute('SET search_path = ag_catalog, "$user", public;')

            # Get graph ID
            graph_row = await self._pg_conn.fetchrow(
                "SELECT graphid FROM ag_catalog.ag_graph WHERE name = $1", graph_name
            )

            if not graph_row:
                logger.info(f"Creating AGE graph '{graph_name}'...")
                await self._pg_conn.execute(
                    f"SELECT create_graph('{graph_name}');"
                )
                graph_row = await self._pg_conn.fetchrow(
                    "SELECT graphid FROM ag_catalog.ag_graph WHERE name = $1", graph_name
                )

            graphid = graph_row['graphid']
            logger.info(f"Using graph ID: {graphid}")

            # Get or create labels
            base_label = await self._pg_conn.fetchrow(
                "SELECT id FROM ag_catalog.ag_label WHERE graph = $1 AND name = 'base'", graphid
            )
            if not base_label:
                # Create vertex label via Cypher
                await self._pg_conn.execute(
                    f"SELECT * FROM cypher('{graph_name}', $$ CREATE (:base {{id: 'init'}}) $$) as (v agtype);"
                )
                await self._pg_conn.execute(
                    f"SELECT * FROM cypher('{graph_name}', $$ MATCH (n:base {{id: 'init'}}) DELETE n $$) as (v agtype);"
                )
                base_label = await self._pg_conn.fetchrow(
                    "SELECT id FROM ag_catalog.ag_label WHERE graph = $1 AND name = 'base'", graphid
                )

            directed_label = await self._pg_conn.fetchrow(
                "SELECT id FROM ag_catalog.ag_label WHERE graph = $1 AND name = 'DIRECTED'", graphid
            )
            if not directed_label:
                # Create edge label via Cypher
                await self._pg_conn.execute(
                    f"SELECT * FROM cypher('{graph_name}', $$ CREATE (:base {{id: 'src'}}), (:base {{id: 'tgt'}}) $$) as (v agtype);"
                )
                await self._pg_conn.execute(
                    f"SELECT * FROM cypher('{graph_name}', $$ MATCH (a:base {{id: 'src'}}), (b:base {{id: 'tgt'}}) CREATE (a)-[:DIRECTED]->(b) $$) as (v agtype);"
                )
                await self._pg_conn.execute(
                    f"SELECT * FROM cypher('{graph_name}', $$ MATCH (n:base) WHERE n.id IN ['src', 'tgt'] DETACH DELETE n $$) as (v agtype);"
                )
                directed_label = await self._pg_conn.fetchrow(
                    "SELECT id FROM ag_catalog.ag_label WHERE graph = $1 AND name = 'DIRECTED'", graphid
                )

            base_label_id = base_label['id']
            directed_label_id = directed_label['id']
            logger.info(f"Label IDs - base: {base_label_id}, DIRECTED: {directed_label_id}")

            # Check existing counts
            v_count = await self._pg_conn.fetchval(f"SELECT count(*) FROM {graph_name}.base")
            if v_count > 0:
                logger.info(f"Clearing existing graph data ({v_count} vertices)...")
                await self._pg_conn.execute(f'DELETE FROM {graph_name}."DIRECTED"')
                await self._pg_conn.execute(f"DELETE FROM {graph_name}.base")

            # === MIGRATE VERTICES ===
            logger.info("Migrating vertices to AGE...")
            nodes = list(G.nodes(data=True))
            node_to_seq = {}  # Map node ID to sequence number for edge creation

            for i in range(0, total_nodes, self.batch_size):
                if self._cancelled:
                    break

                batch = nodes[i:i+self.batch_size]

                for j, (node_id, attrs) in enumerate(batch):
                    seq = i + j + 1
                    node_to_seq[node_id] = seq

                    # Build properties
                    props = dict(attrs)
                    props["id"] = node_id
                    props_json = json.dumps(props)

                    # Insert using _graphid function
                    await self._pg_conn.execute(
                        f"""
                        INSERT INTO {graph_name}.base (id, properties)
                        VALUES (
                            ag_catalog._graphid({base_label_id}::integer, {seq}::bigint),
                            $1::agtype
                        )
                        """,
                        props_json
                    )

                self.checkpoint.graph_nodes_migrated = min(i + self.batch_size, total_nodes)
                if (i + self.batch_size) % 10000 == 0 or (i + self.batch_size) >= total_nodes:
                    logger.info(f"  Vertices: {self.checkpoint.graph_nodes_migrated:,}/{total_nodes:,}")
                    self.checkpoint.save(self.checkpoint_file)
                    self._notify_progress()

            logger.info(f"Migrated {total_nodes:,} vertices")

            # === MIGRATE EDGES ===
            logger.info("Migrating edges to AGE...")
            edges = list(G.edges(data=True))
            migrated_edges = 0
            skipped = 0

            for i in range(0, total_edges, self.batch_size):
                if self._cancelled:
                    break

                batch = edges[i:i+self.batch_size]

                for j, (src, tgt, attrs) in enumerate(batch):
                    if src not in node_to_seq or tgt not in node_to_seq:
                        skipped += 1
                        continue

                    seq = migrated_edges + 1
                    src_seq = node_to_seq[src]
                    tgt_seq = node_to_seq[tgt]

                    props = dict(attrs) if attrs else {}
                    props_json = json.dumps(props)

                    await self._pg_conn.execute(
                        f"""
                        INSERT INTO {graph_name}."DIRECTED" (id, start_id, end_id, properties)
                        VALUES (
                            ag_catalog._graphid({directed_label_id}::integer, {seq}::bigint),
                            ag_catalog._graphid({base_label_id}::integer, {src_seq}::bigint),
                            ag_catalog._graphid({base_label_id}::integer, {tgt_seq}::bigint),
                            $1::agtype
                        )
                        """,
                        props_json
                    )
                    migrated_edges += 1

                self.checkpoint.graph_edges_migrated = migrated_edges
                if (i + self.batch_size) % 20000 == 0 or (i + self.batch_size) >= total_edges:
                    logger.info(f"  Edges: {min(i + self.batch_size, total_edges):,}/{total_edges:,}")
                    self.checkpoint.save(self.checkpoint_file)
                    self._notify_progress()

            logger.info(f"Migrated {migrated_edges:,} edges ({skipped} skipped)")

            # Verify
            final_v = await self._pg_conn.fetchval(f"SELECT count(*) FROM {graph_name}.base")
            final_e = await self._pg_conn.fetchval(f'SELECT count(*) FROM {graph_name}."DIRECTED"')
            logger.info(f"Final counts - Vertices: {final_v:,}, Edges: {final_e:,}")

            if final_v >= total_nodes * 0.95:
                self.checkpoint.graph_migration_complete = True
                logger.info("Graph migration complete!")
            else:
                logger.warning("Graph migration may be incomplete")

            self.checkpoint.save(self.checkpoint_file)

        except Exception as e:
            logger.error(f"Error during AGE graph migration: {e}")
            self.checkpoint.errors.append({
                'timestamp': datetime.now().isoformat(),
                'error': str(e),
                'type': 'age_graph_migration'
            })
            self.checkpoint.save(self.checkpoint_file)
            raise
