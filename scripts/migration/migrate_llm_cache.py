#!/usr/bin/env python3
"""
Migrate LLM response cache from JSON to PostgreSQL.
Standalone script for migrating kv_store_llm_response_cache.json.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path


async def migrate_llm_cache(
    json_file: str = "/home/gyasisutton/dev/tools/RAG/hybridrag/lightrag_db/kv_store_llm_response_cache.json",
    workspace: str = "default",
    batch_size: int = 500
):
    """Migrate LLM response cache to PostgreSQL."""
    import asyncpg

    print(f"Loading {json_file}...")
    with open(json_file) as f:
        data = json.load(f)

    total = len(data)
    print(f"Found {total:,} cache entries")

    conn = await asyncpg.connect(
        host="localhost",
        port=5433,
        user="hybridrag",
        password="hybridrag_secure_2026",
        database="hybridrag"
    )

    try:
        # Check current count
        current = await conn.fetchval("SELECT count(*) FROM lightrag_llm_cache WHERE workspace = $1", workspace)
        print(f"Current entries in PostgreSQL: {current:,}")

        migrated = 0
        batch = []

        for cache_id, cache_data in data.items():
            # Extract fields
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
                    create_time = datetime.fromtimestamp(create_time)
                else:
                    create_time = None
                if isinstance(update_time, (int, float)):
                    update_time = datetime.fromtimestamp(update_time)
                else:
                    update_time = None
            else:
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

            if len(batch) >= batch_size:
                await conn.executemany(
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
                migrated += len(batch)
                batch = []
                if migrated % 10000 == 0:
                    print(f"  Progress: {migrated:,}/{total:,}")

        # Insert remaining
        if batch:
            await conn.executemany(
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
            migrated += len(batch)

        # Verify
        final = await conn.fetchval("SELECT count(*) FROM lightrag_llm_cache WHERE workspace = $1", workspace)
        print(f"\n=== VERIFICATION ===")
        print(f"Final count: {final:,} (expected: {total:,})")

        if final >= total * 0.95:
            print("✅ LLM cache migration complete!")
        else:
            print("⚠️ Migration may be incomplete")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(migrate_llm_cache())
