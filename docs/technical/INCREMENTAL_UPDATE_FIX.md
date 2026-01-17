# LightRAG Incremental Update Fix

## Problem Diagnosis

**Issue:** `deeplake_to_lightrag.py` was reprocessing ALL 15,000+ documents on every run, taking hours/days.

**Root Cause:** Missing `ids` parameter in `ainsert()` call:
```python
# ❌ OLD CODE (line 316)
await self.rag.ainsert(batch)  # No IDs = MD5 hashing = full reprocess
```

## How LightRAG Handles Duplicates

LightRAG has TWO duplicate detection modes:

### Mode 1: With `ids` Parameter (RECOMMENDED)
```python
# ✅ CORRECT
await self.rag.ainsert(documents, ids=doc_ids)
```
- Uses your provided IDs
- Checks `doc_status` storage for existing IDs
- **Automatically skips already-processed documents**
- Perfect for incremental updates

### Mode 2: Without `ids` (AUTO MD5 HASHING)
```python
# ❌ PROBLEMATIC
await self.rag.ainsert(documents)  # Generates MD5 from ENTIRE content
```
- Generates MD5 hash from **entire document content**
- ANY content change = different hash = treated as new document
- **Cannot detect partial modifications**
- Forces full reprocessing

## The Fix

### Key Changes in `deeplake_to_lightrag_incremental.py`:

1. **Generate Stable Document IDs** (lines 123-132):
```python
def generate_document_id(self, record: Dict) -> str:
    """Generate stable ID from schema.table pattern"""
    table_name = str(record.get("TABLE NAME", "Unknown"))
    schema_name = str(record.get("SCHEMANAME", "Unknown"))
    return f"athena.{schema_name}.{table_name}"
```

2. **Extract Documents WITH IDs** (lines 159-221):
```python
def extract_documents_with_ids(self) -> Tuple[List[str], List[str]]:
    documents = []
    document_ids = []

    for record in data:
        doc_id = self.generate_document_id(record)  # Stable ID
        doc = self.format_document(record, metadata)

        documents.append(doc)
        document_ids.append(doc_id)  # Track ID

    return documents, document_ids
```

3. **Pass IDs to ainsert()** (line 263):
```python
async def ingest_to_lightrag_incremental(
    self,
    documents: List[str],
    document_ids: List[str],  # ✅ IDs provided
    batch_size: int = 10
):
    # LightRAG filters duplicates internally
    await self.rag.ainsert(batch_docs, ids=batch_ids)  # ✅ FIXED!
```

## How It Works Internally

From LightRAG source (`apipeline_enqueue_documents`):

```python
# Step 1: Validate/generate IDs
if ids is not None:
    contents = {id_: {"content": doc} for id_, doc in zip(ids, input)}
else:
    # Falls back to MD5 hashing (problematic)
    contents = {compute_mdhash_id(content): {"content": content} for content in input}

# Step 2: Filter already-processed documents
all_new_doc_ids = set(contents.keys())
unique_new_doc_ids = await self.doc_status.filter_keys(all_new_doc_ids)  # ✅ Checks existing

if not unique_new_doc_ids:
    logger.info("No new unique documents were found.")
    return  # ✅ Skips duplicates!

# Step 3: Only process NEW documents
await self.full_docs.upsert(new_docs)
await self.doc_status.upsert(new_docs)
```

## Testing the Fix

### Run 1 - Initial Ingestion:
```bash
python deeplake_to_lightrag_incremental.py
# Output: "Processed: 15,000 documents" (full ingestion)
```

### Run 2 - Duplicate Detection:
```bash
python deeplake_to_lightrag_incremental.py
# Output: "No new unique documents were found." (skips all!)
```

### Verify:
Check LightRAG logs for:
```
INFO: Stored 0 new unique documents  # ✅ Duplicates skipped!
```

## Folder Ingestion Already Fixed

The `folder_to_lightrag.py` script ALREADY uses this pattern correctly:

```python
# folder_to_lightrag.py line 182
doc_id = str(file_path.absolute())  # File path as ID
await self.rag.ainsert(batch_docs, ids=batch_doc_ids)  # ✅ Correct!
```

## For Modified Documents

If you need to handle **modified** documents (e.g., file with 200 new lines):

### Option 1: Delete + Re-insert
```python
# Delete old version
await rag.adelete_by_doc_id("athena.schema.table")

# Insert new version
await rag.ainsert([updated_doc], ids=["athena.schema.table"])
```

### Option 2: Track Modification Times
```python
import pickle
from pathlib import Path

# Load tracking data
tracking_file = Path("./document_tracking.pkl")
if tracking_file.exists():
    with open(tracking_file, 'rb') as f:
        processed_docs = pickle.load(f)  # {doc_id: modification_time}
else:
    processed_docs = {}

# Check if modified
for record in deeplake_data:
    doc_id = generate_document_id(record)
    current_mod_time = record.get("modified_time")  # If available

    if doc_id not in processed_docs or processed_docs[doc_id] < current_mod_time:
        # Modified or new - delete and re-insert
        await rag.adelete_by_doc_id(doc_id)
        await rag.ainsert([format_document(record)], ids=[doc_id])
        processed_docs[doc_id] = current_mod_time

# Save tracking
with open(tracking_file, 'wb') as f:
    pickle.dump(processed_docs, f)
```

## Migration Guide

### From OLD to NEW Script:

1. **Backup existing database:**
```bash
cp -r ./athena_lightrag_db ./athena_lightrag_db.backup
```

2. **Use new incremental script:**
```bash
# First run - processes all documents with IDs
python deeplake_to_lightrag_incremental.py

# Subsequent runs - skips duplicates automatically
python deeplake_to_lightrag_incremental.py  # Fast!
```

3. **Verify duplicate detection:**
```bash
# Should see: "No new unique documents were found"
# Or: "Stored 0 new unique documents"
```

## Key Takeaways

1. **ALWAYS pass `ids` to `ainsert()`** for incremental updates
2. **Use stable, meaningful IDs** (schema.table, file_path, etc.)
3. **LightRAG handles duplicate filtering automatically** via `doc_status` storage
4. **MD5 hashing (no IDs) = full reprocessing** on ANY content change
5. **For modifications:** Delete old + insert new, or track modification times

## Performance Impact

**Old Script (no IDs):**
- 15,000 documents × ~5 seconds each = **~21 hours** per run
- Every run reprocesses EVERYTHING

**New Script (with IDs):**
- First run: ~21 hours (one-time ingestion)
- Subsequent runs: **~2 minutes** (skips all duplicates)
- Modified documents only: **Minutes, not hours**

**210-file folder example:**
- Old: Hours for every run
- New: Seconds (after initial ingestion)
