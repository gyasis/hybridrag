# Batch Ingestion Flow

## Complete Lifecycle

```
┌─────────────────────────────────────────────────────────────┐
│ PHASE 1: DISCOVERY (5 minutes)                              │
│ Find all .specstory files, save paths to pending list       │
└─────────────────────────────────────────────────────────────┘
                            ↓
                    [pending.txt]
                    5000 file paths
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ PHASE 2: BATCH FEEDING (days/weeks)                         │
│ Process 10 files at a time, with throttling                 │
└─────────────────────────────────────────────────────────────┘
                            ↓
        ┌───────────────────┴───────────────────┐
        │                                       │
        ▼                                       ▼
┌──────────────┐                        ┌──────────────┐
│ File Changed?│                        │ File Deleted?│
│              │                        │              │
│ ✓ Reads NEW  │                        │ ✓ Skips     │
│   content    │                        │   gracefully │
│   from disk  │                        │              │
└──────────────┘                        └──────────────┘
        │                                       │
        └───────────────────┬───────────────────┘
                            ↓
                    [Watcher Logic]
                - Check if duplicate (hash)
                - Ingest if new
                - Skip if duplicate
                            ↓
                    [Update pending.txt]
                    Remove processed files
                            ↓
                    [Resource Check]
                CPU > 80% or Memory > 85%?
                    → Pause & wait
                            ↓
                    [Next Batch]
                    Repeat until empty
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ PHASE 3: ONGOING MONITORING (forever)                       │
│ Regular watcher (every 24 hours)                            │
│ Handles 1-2 files at a time                                 │
└─────────────────────────────────────────────────────────────┘
```

## Key Scenarios

### 1. File Changes While On List

**What Happens:**
- Pending list only stores file PATHS (not content)
- When batch controller processes the file:
  - Reads CURRENT content from disk
  - Calculates hash of CURRENT content
  - Ingests latest version

**Example:**
```
10:00 AM - Discovery: file.md added to pending (old content)
2:00 PM  - User edits file.md (new content)
9:00 AM  - Batch processes file.md
           → Reads NEW content
           → Ingests NEW version ✓
```

### 2. File Deleted While On List

**What Happens:**
```python
if not file_path.exists():
    logger.warning(f"File not found: {file_path.name}")
    errors += 1
    continue  # Skip to next file
```

**Result:** Skipped gracefully, no crash

### 3. List is Empty

**First Time (After Completion):**
```
🎉 BATCH INGESTION COMPLETE!
   Total ingested: 4837
   Duplicates skipped: 163
   Errors: 0

📌 NEXT STEPS:
   python hybridrag.py db watch start azure-specstory
```

**Run Again (List Already Empty):**
```
✅ No pending files - bulk ingestion already complete!

💡 For ongoing file monitoring, start the watcher:
   python hybridrag.py db watch start azure-specstory
```

### 4. Pause & Resume

**Pause:**
- Press Ctrl+C
- Progress saved in pending.txt

**Resume:**
```bash
python scripts/batch-ingestion-controller.py azure-specstory
# Picks up where it left off!
```

## Usage

### Initial Bulk Ingestion

```bash
# Step 1: Discovery (fast)
python scripts/batch-ingestion-controller.py azure-specstory --discover
# Output: Found 5000 files, saved to pending list

# Step 2: Start batch feeding (slow, can take days)
python scripts/batch-ingestion-controller.py azure-specstory
# Processes with throttling, pause/resume anytime
```

### Ongoing Monitoring (After Bulk Complete)

```bash
# Start regular watcher
python hybridrag.py db watch start azure-specstory

# Now handles:
# - New files (1-2 at a time)
# - File modifications
# - Same duplicate detection
```

## Resource Throttling

**Automatic Pausing:**
- CPU > 80% → Pause, wait 30 seconds, check again
- Memory > 85% → Pause, wait 30 seconds, check again

**Configurable:**
```bash
python scripts/batch-ingestion-controller.py azure-specstory \
  --batch-size 5 \
  --max-cpu 70 \
  --max-memory 80
```

## Backend Compatibility

✅ **Works with ALL backends:**
- JSON (default)
- PostgreSQL
- MongoDB (future)

**How?** Uses existing watcher logic, which already handles all backends!
