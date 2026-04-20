#!/usr/bin/env python3
"""
Bootstrap FileTracker (processed_files.db) from LightRAG's kv_store_doc_status.json.

Idempotent: safe to re-run. Skips files already marked processed in the tracker.

Reads every 'processed' doc in kv_store_doc_status.json, locates its original
file_path on disk, re-hashes the current content, and inserts a row into
processed_files.db with status='processed'.

Rationale: the FileTracker SQLite was blank (1 queued row, 0 processed) while
LightRAG's own doc_status shows 40 processed docs. Without this bootstrap,
the watcher would re-queue every file on next start — the budget guard
would catch it at $5, but that is symptom-suppression, not prevention.

Run from the hybridrag project root:
    uv run python scripts/bootstrap_file_tracker.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC = PROJECT_ROOT / "src"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC))

from src.folder_watcher import FileTracker, FileInfo  # noqa: E402


DOC_STATUS_PATH = PROJECT_ROOT / "lightrag_db" / "kv_store_doc_status.json"
TRACKER_DB_PATH = PROJECT_ROOT / "processed_files.db"


def main() -> int:
    if not DOC_STATUS_PATH.exists():
        print(f"ERROR: {DOC_STATUS_PATH} not found")
        return 2

    with DOC_STATUS_PATH.open() as f:
        doc_status = json.load(f)

    tracker = FileTracker(str(TRACKER_DB_PATH))

    stats = {
        "total_doc_entries": 0,
        "non_processed_skipped": 0,
        "no_file_path": 0,
        "file_missing_on_disk": 0,
        "already_in_tracker": 0,
        "backfilled": 0,
    }

    for doc_id, entry in doc_status.items():
        stats["total_doc_entries"] += 1

        if not isinstance(entry, dict):
            continue

        status = entry.get("status")
        if status != "processed":
            stats["non_processed_skipped"] += 1
            continue

        file_path = entry.get("file_path")
        if not file_path:
            stats["no_file_path"] += 1
            continue

        p = Path(file_path)
        if not p.exists():
            stats["file_missing_on_disk"] += 1
            continue

        # Re-hash current disk content so FileTracker's check matches what the
        # watcher will compute on its next scan.
        current_hash = tracker.get_file_hash(str(p))
        if not current_hash:
            continue

        if tracker.is_file_processed(str(p), current_hash):
            stats["already_in_tracker"] += 1
            continue

        try:
            ingested_at_str = entry.get("updated_at") or entry.get("created_at")
            ingested_at = (
                datetime.fromisoformat(ingested_at_str.replace("Z", "+00:00"))
                if ingested_at_str
                else datetime.now()
            )
        except Exception:
            ingested_at = datetime.now()

        try:
            file_stat = p.stat()
            tracker.mark_file_processed(FileInfo(
                path=str(p),
                size=file_stat.st_size,
                modified_time=file_stat.st_mtime,
                hash=current_hash,
                extension=p.suffix,
                status="processed",
                ingested_at=ingested_at,
            ))
            stats["backfilled"] += 1
        except Exception as e:
            print(f"  error on {p}: {e}")

    print("Bootstrap complete.")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
