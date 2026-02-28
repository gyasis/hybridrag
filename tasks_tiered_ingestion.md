# Tasks: Tiered Ingestion for HybridRAG Watcher

- [x] T001 Add `ainsert_fast()` to `LightRAGCore` (lightrag_core.py)
- [x] T002 Add `bulk_cutoff_days: int = 30` field to `BatchConfig` (watcher line ~66)
- [x] T003 Add file-age routing in `_process_batch()` (watcher line ~694)
- [x] T004 Write enrichment-pending file tracking
- [ ] T005 Restart watcher and verify fast mode logs appear
- [ ] T006 Smoke-test vector search on a fast-inserted doc
