#!/usr/bin/env python3
"""
Alter Vector Dimension from 768 to 1536
=======================================
Changes PostgreSQL vector columns from 768 to 1536 dimensions.

Steps:
1. Drop HNSW indexes (can't alter with index present)
2. Alter vector columns to 1536
3. Clear existing (zero) vectors
4. Recreate HNSW indexes

Usage:
    python scripts/alter_vector_dimension.py [--dry-run]
"""

import asyncio
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Tables and their vector columns/indexes
VECTOR_TABLES = [
    {
        'table': 'lightrag_vdb_entity',
        'column': 'content_vector',
        'index': 'idx_lightrag_vdb_entity_hnsw_cosine'
    },
    {
        'table': 'lightrag_vdb_chunks',
        'column': 'content_vector',
        'index': 'idx_lightrag_vdb_chunks_hnsw_cosine'
    },
    {
        'table': 'lightrag_vdb_relation',
        'column': 'content_vector',
        'index': 'idx_lightrag_vdb_relation_hnsw_cosine'
    },
]

OLD_DIM = 768
NEW_DIM = 1536


async def alter_to_1536(conn, dry_run: bool = False):
    """Alter all vector columns from 768 to 1536."""

    for table_info in VECTOR_TABLES:
        table = table_info['table']
        column = table_info['column']
        index = table_info['index']

        logger.info(f"\n{'='*50}")
        logger.info(f"Processing {table}")
        logger.info(f"{'='*50}")

        # Step 1: Drop index
        logger.info(f"Step 1: Dropping index {index}...")
        if not dry_run:
            try:
                await conn.execute(f"DROP INDEX IF EXISTS {index}")
                logger.info(f"  ✓ Index dropped")
            except Exception as e:
                logger.warning(f"  Index drop failed (may not exist): {e}")
        else:
            logger.info(f"  [DRY RUN] Would drop index {index}")

        # Step 2: Alter column - need to drop and recreate since pgvector doesn't support ALTER TYPE
        logger.info(f"Step 2: Altering {column} from vector({OLD_DIM}) to vector({NEW_DIM})...")
        if not dry_run:
            try:
                # Drop and recreate column (pgvector limitation)
                await conn.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {column}")
                await conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} vector({NEW_DIM})")
                logger.info(f"  ✓ Column altered to vector({NEW_DIM})")
            except Exception as e:
                logger.error(f"  Column alter failed: {e}")
                raise
        else:
            logger.info(f"  [DRY RUN] Would alter column to vector({NEW_DIM})")

        # Step 3: Recreate HNSW index
        logger.info(f"Step 3: Recreating HNSW index {index}...")
        if not dry_run:
            try:
                await conn.execute(f"""
                    CREATE INDEX {index}
                    ON {table}
                    USING hnsw ({column} vector_cosine_ops)
                """)
                logger.info(f"  ✓ Index recreated")
            except Exception as e:
                logger.error(f"  Index creation failed: {e}")
                raise
        else:
            logger.info(f"  [DRY RUN] Would recreate HNSW index")

        # Step 4: Verify
        if not dry_run:
            result = await conn.fetchrow(f"""
                SELECT format_type(a.atttypid, a.atttypmod) as type
                FROM pg_attribute a
                JOIN pg_class c ON a.attrelid = c.oid
                WHERE c.relname = '{table}' AND a.attname = '{column}'
            """)
            logger.info(f"Step 4: Verified - {table}.{column} is now {result['type']}")


async def main():
    parser = argparse.ArgumentParser(description='Alter vector dimension from 768 to 1536')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done')
    args = parser.parse_args()

    import asyncpg
    from src.database_registry import DatabaseRegistry

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
            logger.info("\n" + "="*50)
            logger.info("DRY RUN MODE - No changes will be made")
            logger.info("="*50)

        await alter_to_1536(conn, dry_run=args.dry_run)

        if not args.dry_run:
            logger.info("\n" + "="*50)
            logger.info("VECTOR DIMENSION CHANGE COMPLETE")
            logger.info("All tables now use vector(1536)")
            logger.info("="*50)
            logger.info("\nNext steps:")
            logger.info("1. Update config/config.py: embedding_dim = 1536")
            logger.info("2. Run: python scripts/restore_embeddings_from_matrix.py")

    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())
