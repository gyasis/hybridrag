#!/usr/bin/env python3
"""
Fix Embeddings Script
=====================
Restores embeddings from JSON backup to PostgreSQL.

The original migration failed to decode base64+zlib encoded vectors.
This script:
1. Reads vdb_entities.json, vdb_relationships.json, vdb_chunks.json
2. Decodes base64+zlib vectors
3. Updates PostgreSQL tables with valid embeddings
"""

import asyncio
import json
import base64
import zlib
import struct
import logging
import sys
from pathlib import Path
from typing import Optional, List
import numpy as np

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database_registry import DatabaseRegistry

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def decode_embedding(encoded_vector: Optional[str]) -> Optional[List[float]]:
    """Decode base64+zlib encoded embedding vector."""
    if not encoded_vector or not isinstance(encoded_vector, str):
        return None

    try:
        decoded = base64.b64decode(encoded_vector)
        decompressed = zlib.decompress(decoded)
        num_floats = len(decompressed) // 4
        embedding = list(struct.unpack(f'{num_floats}f', decompressed[:num_floats * 4]))
        return embedding
    except Exception as e:
        logger.debug(f"Could not decode embedding: {e}")
        return None


async def fix_entity_embeddings(conn, json_path: Path, batch_size: int = 100):
    """Update entity embeddings from vdb_entities.json."""
    entities_file = json_path / 'vdb_entities.json'
    if not entities_file.exists():
        logger.warning(f"No {entities_file} found")
        return 0

    logger.info(f"Loading {entities_file}...")
    with open(entities_file) as f:
        data = json.load(f)

    entities = data.get('data', [])
    logger.info(f"Found {len(entities)} entities to update")

    updated = 0
    skipped = 0
    batch = []

    for entity in entities:
        entity_name = entity.get('entity_name', '')
        encoded = entity.get('vector', '')
        embedding = decode_embedding(encoded)

        if embedding is None:
            skipped += 1
            continue

        # Validate embedding
        arr = np.array(embedding)
        if np.linalg.norm(arr) < 0.001:
            skipped += 1
            continue

        # Format for pgvector
        vec_str = '[' + ','.join(map(str, embedding)) + ']'
        batch.append((vec_str, entity_name))

        if len(batch) >= batch_size:
            await conn.executemany(
                """UPDATE lightrag_vdb_entity
                   SET content_vector = $1::vector
                   WHERE entity_name = $2""",
                batch
            )
            updated += len(batch)
            logger.info(f"Updated {updated} entities...")
            batch = []

    if batch:
        await conn.executemany(
            """UPDATE lightrag_vdb_entity
               SET content_vector = $1::vector
               WHERE entity_name = $2""",
            batch
        )
        updated += len(batch)

    logger.info(f"Entity embeddings: {updated} updated, {skipped} skipped")
    return updated


async def fix_chunk_embeddings(conn, json_path: Path, batch_size: int = 100):
    """Update chunk embeddings from vdb_chunks.json."""
    chunks_file = json_path / 'vdb_chunks.json'
    if not chunks_file.exists():
        logger.warning(f"No {chunks_file} found")
        return 0

    logger.info(f"Loading {chunks_file}...")
    with open(chunks_file) as f:
        data = json.load(f)

    chunks = data.get('data', [])
    logger.info(f"Found {len(chunks)} chunks to update")

    updated = 0
    skipped = 0
    batch = []

    for chunk in chunks:
        chunk_id = chunk.get('__id__', '')
        encoded = chunk.get('vector', '')
        embedding = decode_embedding(encoded)

        if embedding is None:
            skipped += 1
            continue

        arr = np.array(embedding)
        if np.linalg.norm(arr) < 0.001:
            skipped += 1
            continue

        vec_str = '[' + ','.join(map(str, embedding)) + ']'
        batch.append((vec_str, chunk_id))

        if len(batch) >= batch_size:
            await conn.executemany(
                """UPDATE lightrag_vdb_chunks
                   SET content_vector = $1::vector
                   WHERE id = $2""",
                batch
            )
            updated += len(batch)
            logger.info(f"Updated {updated} chunks...")
            batch = []

    if batch:
        await conn.executemany(
            """UPDATE lightrag_vdb_chunks
               SET content_vector = $1::vector
               WHERE id = $2""",
            batch
        )
        updated += len(batch)

    logger.info(f"Chunk embeddings: {updated} updated, {skipped} skipped")
    return updated


async def fix_relation_embeddings(conn, json_path: Path, batch_size: int = 100):
    """Update relation embeddings from vdb_relationships.json."""
    relations_file = json_path / 'vdb_relationships.json'
    if not relations_file.exists():
        logger.warning(f"No {relations_file} found")
        return 0

    logger.info(f"Loading {relations_file}...")
    with open(relations_file) as f:
        data = json.load(f)

    relations = data.get('data', [])
    logger.info(f"Found {len(relations)} relations to update")

    updated = 0
    skipped = 0
    batch = []

    for rel in relations:
        rel_id = rel.get('__id__', '')
        encoded = rel.get('vector', '')
        embedding = decode_embedding(encoded)

        if embedding is None:
            skipped += 1
            continue

        arr = np.array(embedding)
        if np.linalg.norm(arr) < 0.001:
            skipped += 1
            continue

        vec_str = '[' + ','.join(map(str, embedding)) + ']'
        batch.append((vec_str, rel_id))

        if len(batch) >= batch_size:
            await conn.executemany(
                """UPDATE lightrag_vdb_relation
                   SET content_vector = $1::vector
                   WHERE id = $2""",
                batch
            )
            updated += len(batch)
            logger.info(f"Updated {updated} relations...")
            batch = []

    if batch:
        await conn.executemany(
            """UPDATE lightrag_vdb_relation
               SET content_vector = $1::vector
               WHERE id = $2""",
            batch
        )
        updated += len(batch)

    logger.info(f"Relation embeddings: {updated} updated, {skipped} skipped")
    return updated


async def main():
    """Main function to fix all embeddings."""
    import asyncpg

    # Get database connection info
    registry = DatabaseRegistry()
    entry = registry.get('specstory')
    backend_config = entry.get_backend_config()
    env_vars = backend_config.get_env_vars()

    json_path = Path('lightrag_db')

    logger.info("Connecting to PostgreSQL...")
    conn = await asyncpg.connect(
        host=env_vars['POSTGRES_HOST'],
        port=int(env_vars['POSTGRES_PORT']),
        user=env_vars['POSTGRES_USER'],
        password=env_vars['POSTGRES_PASSWORD'],
        database=env_vars['POSTGRES_DATABASE']
    )

    try:
        # First verify we can decode embeddings from JSON
        logger.info("Verifying JSON embeddings...")
        with open(json_path / 'vdb_entities.json') as f:
            data = json.load(f)
        sample = data['data'][0]
        test_vec = decode_embedding(sample.get('vector', ''))
        if test_vec:
            norm = np.linalg.norm(np.array(test_vec))
            logger.info(f"Sample decoded vector: dim={len(test_vec)}, norm={norm:.4f}")
            if norm < 0.001:
                logger.error("Decoded vectors are still zeros! Check JSON source.")
                return
        else:
            logger.error("Could not decode sample vector!")
            return

        # Fix each type
        entities_updated = await fix_entity_embeddings(conn, json_path)
        chunks_updated = await fix_chunk_embeddings(conn, json_path)
        relations_updated = await fix_relation_embeddings(conn, json_path)

        logger.info("=" * 50)
        logger.info("EMBEDDING FIX COMPLETE")
        logger.info(f"  Entities: {entities_updated}")
        logger.info(f"  Chunks: {chunks_updated}")
        logger.info(f"  Relations: {relations_updated}")
        logger.info("=" * 50)

        # Verify fix
        logger.info("Verifying fix...")
        result = await conn.fetchrow("""
            SELECT
                COUNT(*) FILTER (WHERE vector_norm(content_vector) > 0.1) as valid,
                COUNT(*) as total
            FROM lightrag_vdb_entity
        """)
        logger.info(f"Entity vectors: {result['valid']}/{result['total']} valid")

    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())
