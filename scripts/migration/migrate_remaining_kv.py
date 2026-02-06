#!/usr/bin/env python3
"""
Migrate remaining KV stores from JSON to PostgreSQL.
- doc_status -> lightrag_doc_status
- full_docs -> lightrag_doc_full
"""

import json
import asyncio
from datetime import datetime
from pathlib import Path


async def migrate_doc_status(conn, workspace: str = "default"):
    """Migrate doc_status from JSON to PostgreSQL."""
    json_file = "/home/gyasisutton/dev/tools/RAG/hybridrag/lightrag_db/kv_store_doc_status.json"

    print("\n=== Migrating doc_status ===")
    with open(json_file, 'r') as f:
        data = json.load(f)

    total = len(data)
    print(f"Found {total} records to migrate")

    existing = await conn.fetchval("SELECT count(*) FROM lightrag_doc_status WHERE workspace = $1", workspace)
    print(f"Existing records in DB: {existing}")

    if existing >= total:
        print("Migration appears complete. Skipping.")
        return

    batch = []
    for key, value in data.items():
        doc_id = key

        # Map fields from JSON to table columns
        record = (
            workspace,
            doc_id,
            value.get('content_summary'),
            value.get('content_length'),
            value.get('chunks_count'),
            value.get('status'),
            value.get('file_path'),
            json.dumps(value.get('chunks_list', [])),
            value.get('track_id'),
            json.dumps(value.get('metadata', {})),
            value.get('error_msg'),
        )
        batch.append(record)

    await conn.executemany(
        """
        INSERT INTO lightrag_doc_status
            (workspace, id, content_summary, content_length, chunks_count, status,
             file_path, chunks_list, track_id, metadata, error_msg)
        VALUES
            ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, $10::jsonb, $11)
        ON CONFLICT (workspace, id) DO UPDATE SET
            content_summary = EXCLUDED.content_summary,
            content_length = EXCLUDED.content_length,
            chunks_count = EXCLUDED.chunks_count,
            status = EXCLUDED.status,
            file_path = EXCLUDED.file_path,
            chunks_list = EXCLUDED.chunks_list,
            track_id = EXCLUDED.track_id,
            metadata = EXCLUDED.metadata,
            error_msg = EXCLUDED.error_msg
        """,
        batch
    )

    final_count = await conn.fetchval("SELECT count(*) FROM lightrag_doc_status WHERE workspace = $1", workspace)
    print(f"Final count in DB: {final_count}")
    if final_count >= total:
        print("✅ doc_status migration verified!")


async def migrate_full_docs(conn, workspace: str = "default"):
    """Migrate full_docs from JSON to PostgreSQL."""
    json_file = "/home/gyasisutton/dev/tools/RAG/hybridrag/lightrag_db/kv_store_full_docs.json"

    print("\n=== Migrating full_docs ===")
    with open(json_file, 'r') as f:
        data = json.load(f)

    total = len(data)
    print(f"Found {total} records to migrate")

    existing = await conn.fetchval("SELECT count(*) FROM lightrag_doc_full WHERE workspace = $1", workspace)
    print(f"Existing records in DB: {existing}")

    if existing >= total:
        print("Migration appears complete. Skipping.")
        return

    batch = []
    for key, value in data.items():
        doc_id = key

        # Extract metadata fields
        content = value.get('content', '')
        doc_name = value.get('doc_name') or value.get('file_path', '')

        # Build meta from any extra fields
        meta = {k: v for k, v in value.items() if k not in ('content', 'doc_name', 'file_path')}

        record = (
            doc_id,
            workspace,
            doc_name[:1024] if doc_name else None,  # Truncate to fit varchar(1024)
            content,
            json.dumps(meta) if meta else '{}',
        )
        batch.append(record)

    await conn.executemany(
        """
        INSERT INTO lightrag_doc_full
            (id, workspace, doc_name, content, meta)
        VALUES
            ($1, $2, $3, $4, $5::jsonb)
        ON CONFLICT (workspace, id) DO UPDATE SET
            doc_name = EXCLUDED.doc_name,
            content = EXCLUDED.content,
            meta = EXCLUDED.meta
        """,
        batch
    )

    final_count = await conn.fetchval("SELECT count(*) FROM lightrag_doc_full WHERE workspace = $1", workspace)
    print(f"Final count in DB: {final_count}")
    if final_count >= total:
        print("✅ full_docs migration verified!")


async def main():
    import asyncpg

    conn = await asyncpg.connect(
        host="localhost",
        port=5433,
        user="hybridrag",
        password="hybridrag_secure_2026",
        database="hybridrag"
    )

    try:
        await migrate_doc_status(conn)
        await migrate_full_docs(conn)
        print("\n=== All migrations complete! ===")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
