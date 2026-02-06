#!/usr/bin/env python3
"""
Restore Embeddings from Matrix
==============================
Restores embeddings from nano-vectordb's matrix field to PostgreSQL.

The nano-vectordb format stores embeddings in a base64-encoded matrix field,
NOT in individual entity 'vector' fields. This script:
1. Reads matrix from vdb_*.json files
2. Decodes base64 -> numpy array
3. Maps embeddings to entities by index
4. Updates PostgreSQL with correct embeddings

Usage:
    python scripts/restore_embeddings_from_matrix.py [--batch-size 100] [--entities-only]
"""

import asyncio
import argparse
import logging
import sys
import base64
from pathlib import Path
from typing import List, Tuple
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_matrix_embeddings(json_path: Path, file_name: str) -> Tuple[np.ndarray, List[dict], int]:
    """
    Load embeddings from nano-vectordb matrix field.

    Returns:
        Tuple of (matrix, entities_data, embedding_dim)
    """
    import json

    file_path = json_path / file_name
    if not file_path.exists():
        logger.warning(f"File not found: {file_path}")
        return None, [], 0

    logger.info(f"Loading {file_path}...")
    with open(file_path) as f:
        data = json.load(f)

    embedding_dim = data.get('embedding_dim', 1536)
    entities = data.get('data', [])
    matrix_str = data.get('matrix', '')

    if not matrix_str:
        logger.warning(f"No matrix field in {file_name}")
        return None, entities, embedding_dim

    # Decode matrix
    logger.info(f"Decoding matrix ({len(matrix_str)} chars)...")
    decoded = base64.b64decode(matrix_str)
    arr = np.frombuffer(decoded, dtype=np.float32)

    num_embeddings = len(arr) // embedding_dim
    matrix = arr.reshape(num_embeddings, embedding_dim)

    logger.info(f"Loaded {num_embeddings} embeddings @ {embedding_dim} dims")

    # Verify
    norms = np.linalg.norm(matrix, axis=1)
    valid = np.sum(norms > 0.1)
    logger.info(f"Valid embeddings: {valid}/{num_embeddings}")

    return matrix, entities, embedding_dim


async def restore_entity_embeddings(conn, json_path: Path, batch_size: int = 100):
    """Restore entity embeddings from vdb_entities.json matrix."""
    matrix, entities, embedding_dim = load_matrix_embeddings(json_path, 'vdb_entities.json')

    if matrix is None:
        return 0

    if len(entities) != len(matrix):
        logger.error(f"Mismatch: {len(entities)} entities vs {len(matrix)} embeddings")
        return 0

    logger.info(f"Restoring {len(entities)} entity embeddings...")

    updated = 0
    errors = 0

    for i in range(0, len(entities), batch_size):
        batch_entities = entities[i:i+batch_size]
        batch_embeddings = matrix[i:i+batch_size]

        for entity, embedding in zip(batch_entities, batch_embeddings):
            entity_name = entity.get('entity_name', '')
            if not entity_name:
                errors += 1
                continue

            # Format for pgvector
            vec_str = '[' + ','.join(map(str, embedding.tolist())) + ']'

            try:
                result = await conn.execute(
                    """UPDATE lightrag_vdb_entity
                       SET content_vector = $1::vector
                       WHERE entity_name = $2""",
                    vec_str, entity_name
                )
                updated += 1
            except Exception as e:
                logger.debug(f"Error updating {entity_name}: {e}")
                errors += 1

        logger.info(f"Entities: {updated}/{len(entities)} ({100*updated/len(entities):.1f}%)")

    logger.info(f"Entity embeddings: {updated} updated, {errors} errors")
    return updated


async def restore_chunk_embeddings(conn, json_path: Path, batch_size: int = 100):
    """Restore chunk embeddings from vdb_chunks.json matrix."""
    matrix, chunks, embedding_dim = load_matrix_embeddings(json_path, 'vdb_chunks.json')

    if matrix is None:
        return 0

    if len(chunks) != len(matrix):
        logger.error(f"Mismatch: {len(chunks)} chunks vs {len(matrix)} embeddings")
        return 0

    logger.info(f"Restoring {len(chunks)} chunk embeddings...")

    updated = 0
    errors = 0

    for i in range(0, len(chunks), batch_size):
        batch_chunks = chunks[i:i+batch_size]
        batch_embeddings = matrix[i:i+batch_size]

        for chunk, embedding in zip(batch_chunks, batch_embeddings):
            chunk_id = chunk.get('__id__', '')
            if not chunk_id:
                errors += 1
                continue

            vec_str = '[' + ','.join(map(str, embedding.tolist())) + ']'

            try:
                await conn.execute(
                    """UPDATE lightrag_vdb_chunks
                       SET content_vector = $1::vector
                       WHERE id = $2""",
                    vec_str, chunk_id
                )
                updated += 1
            except Exception as e:
                logger.debug(f"Error updating chunk {chunk_id}: {e}")
                errors += 1

        if len(chunks) > 0:
            logger.info(f"Chunks: {updated}/{len(chunks)} ({100*updated/len(chunks):.1f}%)")

    logger.info(f"Chunk embeddings: {updated} updated, {errors} errors")
    return updated


async def restore_relation_embeddings(conn, json_path: Path, batch_size: int = 100):
    """Restore relation embeddings from vdb_relationships.json matrix."""
    matrix, relations, embedding_dim = load_matrix_embeddings(json_path, 'vdb_relationships.json')

    if matrix is None:
        return 0

    if len(relations) != len(matrix):
        logger.error(f"Mismatch: {len(relations)} relations vs {len(matrix)} embeddings")
        return 0

    logger.info(f"Restoring {len(relations)} relation embeddings...")

    updated = 0
    errors = 0

    for i in range(0, len(relations), batch_size):
        batch_rels = relations[i:i+batch_size]
        batch_embeddings = matrix[i:i+batch_size]

        for rel, embedding in zip(batch_rels, batch_embeddings):
            rel_id = rel.get('__id__', '')
            if not rel_id:
                errors += 1
                continue

            vec_str = '[' + ','.join(map(str, embedding.tolist())) + ']'

            try:
                await conn.execute(
                    """UPDATE lightrag_vdb_relation
                       SET content_vector = $1::vector
                       WHERE id = $2""",
                    vec_str, rel_id
                )
                updated += 1
            except Exception as e:
                logger.debug(f"Error updating relation {rel_id}: {e}")
                errors += 1

        if len(relations) > 0:
            logger.info(f"Relations: {updated}/{len(relations)} ({100*updated/len(relations):.1f}%)")

    logger.info(f"Relation embeddings: {updated} updated, {errors} errors")
    return updated


async def main():
    parser = argparse.ArgumentParser(description='Restore embeddings from nano-vectordb matrix')
    parser.add_argument('--batch-size', type=int, default=100, help='Batch size')
    parser.add_argument('--entities-only', action='store_true', help='Only restore entity embeddings')
    parser.add_argument('--chunks-only', action='store_true', help='Only restore chunk embeddings')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be restored')
    args = parser.parse_args()

    import asyncpg
    from src.database_registry import DatabaseRegistry

    json_path = Path('lightrag_db')

    if args.dry_run:
        logger.info("DRY RUN - Checking source data...")
        for fname in ['vdb_entities.json', 'vdb_chunks.json', 'vdb_relationships.json']:
            matrix, data, dim = load_matrix_embeddings(json_path, fname)
            if matrix is not None:
                logger.info(f"  {fname}: {len(data)} items, {dim} dims, matrix valid")
        return

    # Connect to PostgreSQL
    registry = DatabaseRegistry()
    entry = registry.get('specstory')
    backend_config = entry.get_backend_config()
    env_vars = backend_config.get_env_vars()

    logger.info("Connecting to PostgreSQL...")
    conn = await asyncpg.connect(
        host=env_vars['POSTGRES_HOST'],
        port=int(env_vars['POSTGRES_PORT']),
        user=env_vars['POSTGRES_USER'],
        password=env_vars['POSTGRES_PASSWORD'],
        database=env_vars['POSTGRES_DATABASE']
    )

    try:
        results = {}

        if args.entities_only:
            results['entities'] = await restore_entity_embeddings(conn, json_path, args.batch_size)
        elif args.chunks_only:
            results['chunks'] = await restore_chunk_embeddings(conn, json_path, args.batch_size)
        else:
            results['entities'] = await restore_entity_embeddings(conn, json_path, args.batch_size)
            results['chunks'] = await restore_chunk_embeddings(conn, json_path, args.batch_size)
            results['relations'] = await restore_relation_embeddings(conn, json_path, args.batch_size)

        # Summary
        logger.info("=" * 50)
        logger.info("EMBEDDING RESTORATION COMPLETE")
        for name, count in results.items():
            logger.info(f"  {name.capitalize()}: {count}")
        logger.info("=" * 50)

        # Verify
        logger.info("Verifying...")
        result = await conn.fetchrow("""
            SELECT
                COUNT(*) FILTER (WHERE vector_norm(content_vector) > 0.1) as valid,
                COUNT(*) as total
            FROM lightrag_vdb_entity
        """)
        logger.info(f"Valid entity vectors: {result['valid']}/{result['total']}")

    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())
