#!/usr/bin/env python3
"""
Regenerate Embeddings Script
============================
Generates new embeddings for all entities, chunks, and relations in PostgreSQL.

The original ingestion failed to generate embeddings.
This script:
1. Reads entity/chunk/relation content from PostgreSQL
2. Generates embeddings using Azure text-embedding-3-small @ 768 dims
3. Updates PostgreSQL with valid embeddings

Usage:
    python scripts/regenerate_embeddings.py [--batch-size 50] [--entities-only]
"""

import asyncio
import argparse
import logging
import sys
import os
from pathlib import Path
from typing import List
import numpy as np

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def get_embedding(texts: List[str], api_key: str, dimensions: int = 768) -> List[List[float]]:
    """Generate embeddings using Azure/OpenAI API."""
    import litellm

    if not texts:
        return []

    try:
        response = await litellm.aembedding(
            model=os.getenv("LIGHTRAG_EMBED_MODEL", "azure/text-embedding-3-small"),
            input=texts,
            dimensions=dimensions,
            api_key=api_key,
            timeout=60,
        )
        return [item['embedding'] for item in response.data]
    except Exception as e:
        logger.error(f"Embedding error: {e}")
        raise


async def regenerate_entity_embeddings(conn, api_key: str, batch_size: int = 50):
    """Regenerate embeddings for all entities."""
    logger.info("Counting entities...")
    total = await conn.fetchval("SELECT COUNT(*) FROM lightrag_vdb_entity")
    logger.info(f"Total entities: {total}")

    updated = 0
    errors = 0
    offset = 0

    while offset < total:
        # Fetch batch
        rows = await conn.fetch("""
            SELECT id, entity_name, content
            FROM lightrag_vdb_entity
            ORDER BY id
            LIMIT $1 OFFSET $2
        """, batch_size, offset)

        if not rows:
            break

        # Prepare texts for embedding (use entity_name + content)
        texts = []
        ids = []
        for row in rows:
            text = f"{row['entity_name']}: {row['content'] or ''}"[:8000]  # Limit length
            texts.append(text)
            ids.append(row['id'])

        try:
            # Generate embeddings
            embeddings = await get_embedding(texts, api_key)

            # Update database
            for entity_id, embedding in zip(ids, embeddings):
                vec_str = '[' + ','.join(map(str, embedding)) + ']'
                await conn.execute(
                    """UPDATE lightrag_vdb_entity
                       SET content_vector = $1::vector
                       WHERE id = $2""",
                    vec_str, entity_id
                )
                updated += 1

            logger.info(f"Entities: {updated}/{total} ({100*updated/total:.1f}%)")

        except Exception as e:
            logger.error(f"Batch error at offset {offset}: {e}")
            errors += len(rows)

        offset += batch_size

        # Rate limit protection
        await asyncio.sleep(0.1)

    logger.info(f"Entity embeddings: {updated} updated, {errors} errors")
    return updated


async def regenerate_chunk_embeddings(conn, api_key: str, batch_size: int = 50):
    """Regenerate embeddings for all chunks."""
    logger.info("Counting chunks...")
    total = await conn.fetchval("SELECT COUNT(*) FROM lightrag_vdb_chunks")
    logger.info(f"Total chunks: {total}")

    updated = 0
    errors = 0
    offset = 0

    while offset < total:
        rows = await conn.fetch("""
            SELECT id, content
            FROM lightrag_vdb_chunks
            ORDER BY id
            LIMIT $1 OFFSET $2
        """, batch_size, offset)

        if not rows:
            break

        texts = [row['content'][:8000] for row in rows]
        ids = [row['id'] for row in rows]

        try:
            embeddings = await get_embedding(texts, api_key)

            for chunk_id, embedding in zip(ids, embeddings):
                vec_str = '[' + ','.join(map(str, embedding)) + ']'
                await conn.execute(
                    """UPDATE lightrag_vdb_chunks
                       SET content_vector = $1::vector
                       WHERE id = $2""",
                    vec_str, chunk_id
                )
                updated += 1

            logger.info(f"Chunks: {updated}/{total} ({100*updated/total:.1f}%)")

        except Exception as e:
            logger.error(f"Batch error at offset {offset}: {e}")
            errors += len(rows)

        offset += batch_size
        await asyncio.sleep(0.1)

    logger.info(f"Chunk embeddings: {updated} updated, {errors} errors")
    return updated


async def regenerate_relation_embeddings(conn, api_key: str, batch_size: int = 50):
    """Regenerate embeddings for all relations."""
    logger.info("Counting relations...")
    total = await conn.fetchval("SELECT COUNT(*) FROM lightrag_vdb_relation")
    logger.info(f"Total relations: {total}")

    updated = 0
    errors = 0
    offset = 0

    while offset < total:
        rows = await conn.fetch("""
            SELECT id, src_id, tgt_id, content
            FROM lightrag_vdb_relation
            ORDER BY id
            LIMIT $1 OFFSET $2
        """, batch_size, offset)

        if not rows:
            break

        texts = []
        ids = []
        for row in rows:
            text = f"{row['src_id']} -> {row['tgt_id']}: {row['content'] or ''}"[:8000]
            texts.append(text)
            ids.append(row['id'])

        try:
            embeddings = await get_embedding(texts, api_key)

            for rel_id, embedding in zip(ids, embeddings):
                vec_str = '[' + ','.join(map(str, embedding)) + ']'
                await conn.execute(
                    """UPDATE lightrag_vdb_relation
                       SET content_vector = $1::vector
                       WHERE id = $2""",
                    vec_str, rel_id
                )
                updated += 1

            logger.info(f"Relations: {updated}/{total} ({100*updated/total:.1f}%)")

        except Exception as e:
            logger.error(f"Batch error at offset {offset}: {e}")
            errors += len(rows)

        offset += batch_size
        await asyncio.sleep(0.1)

    logger.info(f"Relation embeddings: {updated} updated, {errors} errors")
    return updated


async def main():
    parser = argparse.ArgumentParser(description='Regenerate embeddings for HybridRAG')
    parser.add_argument('--batch-size', type=int, default=50, help='Batch size for embedding calls')
    parser.add_argument('--entities-only', action='store_true', help='Only regenerate entity embeddings')
    parser.add_argument('--chunks-only', action='store_true', help='Only regenerate chunk embeddings')
    parser.add_argument('--dry-run', action='store_true', help='Show counts without updating')
    args = parser.parse_args()

    import asyncpg
    from src.database_registry import DatabaseRegistry

    # Get API key
    api_key = os.getenv("AZURE_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("No API key found. Set AZURE_API_KEY or OPENAI_API_KEY")
        return

    # Get database connection
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
        if args.dry_run:
            entities = await conn.fetchval("SELECT COUNT(*) FROM lightrag_vdb_entity")
            chunks = await conn.fetchval("SELECT COUNT(*) FROM lightrag_vdb_chunks")
            relations = await conn.fetchval("SELECT COUNT(*) FROM lightrag_vdb_relation")
            logger.info(f"DRY RUN - Would regenerate:")
            logger.info(f"  Entities: {entities}")
            logger.info(f"  Chunks: {chunks}")
            logger.info(f"  Relations: {relations}")
            logger.info(f"  Estimated API calls: {(entities + chunks + relations) // args.batch_size}")
            return

        # Test embedding API
        logger.info("Testing embedding API...")
        test = await get_embedding(["test"], api_key)
        logger.info(f"API working - embedding dim: {len(test[0])}")

        # Regenerate
        results = {}

        if args.entities_only:
            results['entities'] = await regenerate_entity_embeddings(conn, api_key, args.batch_size)
        elif args.chunks_only:
            results['chunks'] = await regenerate_chunk_embeddings(conn, api_key, args.batch_size)
        else:
            results['entities'] = await regenerate_entity_embeddings(conn, api_key, args.batch_size)
            results['chunks'] = await regenerate_chunk_embeddings(conn, api_key, args.batch_size)
            results['relations'] = await regenerate_relation_embeddings(conn, api_key, args.batch_size)

        # Summary
        logger.info("=" * 50)
        logger.info("EMBEDDING REGENERATION COMPLETE")
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
