#!/usr/bin/env python3
"""
Migrate text_chunks from JSON to PostgreSQL lightrag_doc_chunks table.

This script migrates the kv_store_text_chunks.json data to the
lightrag_doc_chunks PostgreSQL table.
"""

import json
import asyncio
from datetime import datetime
from pathlib import Path
import sys

# Add project root for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "dev/tools/RAG/hybridrag"))

async def migrate_text_chunks(
    json_file: str = "/home/gyasisutton/dev/tools/RAG/hybridrag/lightrag_db/kv_store_text_chunks.json",
    workspace: str = "default",
    batch_size: int = 500
):
    """Migrate text_chunks JSON to PostgreSQL."""
    import asyncpg

    # Database connection
    conn = await asyncpg.connect(
        host="localhost",
        port=5433,
        user="hybridrag",
        password="hybridrag_secure_2026",
        database="hybridrag"
    )

    try:
        # Load JSON data
        print(f"Loading JSON from {json_file}...")
        with open(json_file, 'r') as f:
            data = json.load(f)

        total = len(data)
        print(f"Found {total} records to migrate")

        # Check current count
        existing = await conn.fetchval("SELECT count(*) FROM lightrag_doc_chunks WHERE workspace = $1", workspace)
        print(f"Existing records in DB: {existing}")

        if existing >= total:
            print("Migration appears complete. Skipping.")
            return

        # Prepare batch inserts
        migrated = 0
        batch = []

        for key, value in data.items():
            # Extract ID (use key or _id field)
            chunk_id = value.get('_id', key)

            # Convert epoch timestamps to datetime
            create_time = None
            update_time = None
            if value.get('create_time'):
                create_time = datetime.fromtimestamp(value['create_time'])
            if value.get('update_time'):
                update_time = datetime.fromtimestamp(value['update_time'])

            # Prepare record
            record = (
                chunk_id,
                workspace,
                value.get('full_doc_id'),
                value.get('chunk_order_index'),
                value.get('tokens'),
                value.get('content'),
                value.get('file_path'),
                json.dumps(value.get('llm_cache_list', [])),
                create_time,
                update_time
            )
            batch.append(record)

            # Insert batch
            if len(batch) >= batch_size:
                await insert_batch(conn, batch)
                migrated += len(batch)
                print(f"Progress: {migrated}/{total} ({migrated*100//total}%)")
                batch = []

        # Insert remaining
        if batch:
            await insert_batch(conn, batch)
            migrated += len(batch)

        print(f"\nMigration complete: {migrated} records inserted")

        # Verify
        final_count = await conn.fetchval("SELECT count(*) FROM lightrag_doc_chunks WHERE workspace = $1", workspace)
        print(f"Final count in DB: {final_count}")

        if final_count == total:
            print("✅ Migration verified: counts match!")
        else:
            print(f"⚠️ Count mismatch: JSON={total}, DB={final_count}")

    finally:
        await conn.close()


async def insert_batch(conn, batch):
    """Insert a batch of records."""
    await conn.executemany(
        """
        INSERT INTO lightrag_doc_chunks
            (id, workspace, full_doc_id, chunk_order_index, tokens, content, file_path, llm_cache_list, create_time, update_time)
        VALUES
            ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, $10)
        ON CONFLICT (workspace, id) DO UPDATE SET
            full_doc_id = EXCLUDED.full_doc_id,
            chunk_order_index = EXCLUDED.chunk_order_index,
            tokens = EXCLUDED.tokens,
            content = EXCLUDED.content,
            file_path = EXCLUDED.file_path,
            llm_cache_list = EXCLUDED.llm_cache_list,
            create_time = EXCLUDED.create_time,
            update_time = EXCLUDED.update_time
        """,
        batch
    )


if __name__ == "__main__":
    asyncio.run(migrate_text_chunks())
