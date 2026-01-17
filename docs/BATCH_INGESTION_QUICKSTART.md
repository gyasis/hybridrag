# Batch Ingestion - Quick Start Guide

> **⚠️ PostgreSQL Backend Requirement:** If using PostgreSQL backend, you MUST use `apache/age:latest` Docker image instead of `pgvector/pgvector:pg16`. LightRAG's PostgreSQL graph storage requires Apache AGE extension. See [PostgreSQL Deployment Guide](user-stories/isolated-postgres-deployment.md).

## Problem Solved ✅

**Before:** Watcher tried to ingest ALL 3076 files at once, blocking your system for hours/days

**After:** Batch controller processes 10 files at a time with resource monitoring, runs over days/weeks in the background

---

## How It Works

```
Phase 1: Discovery (Fast - 2 minutes)
├─ Scans /home/gyasis/Documents/code
├─ Finds all .specstory/history/*.md files
└─ Saves 3076 file paths to pending list

Phase 2: Batch Feeding (Slow - Days/Weeks)
├─ Processes 10 files per batch
├─ Checks CPU/Memory before each batch
├─ Pauses if system too busy
├─ Can pause/resume anytime
└─ Uses existing duplicate detection!

Phase 3: Ongoing Monitoring (Forever)
└─ Regular watcher handles 1-2 files at a time
```

---

## Usage

### For Initial Bulk Ingestion (Now)

```bash
# 1. Discovery already done! (3076 files found)
# Skip this step - already completed

# 2. Start batch ingestion
python scripts/batch-ingestion-controller.py azure-specstory

# This will:
# - Process 10 files at a time
# - Check CPU < 80%, Memory < 85%
# - Pause if system busy
# - Take ~3-10 minutes per file (depending on content)
# - Run for several days total
```

### Monitoring Progress

```bash
# Check how many files remain
wc -l ~/.hybridrag/batch_ingestion/azure-specstory.pending.txt

# Initially: 3076 files
# After 1 hour: ~3070 files (processing ~6-10 files/hour)
```

### Pause & Resume

**To Pause:**
- Just press Ctrl+C or kill the process
- Progress is auto-saved!

**To Resume:**
```bash
python scripts/batch-ingestion-controller.py azure-specstory
# Picks up exactly where it left off
```

### For Ongoing Monitoring (After Bulk Complete)

```bash
# Start regular watcher (lightweight)
python hybridrag.py db watch start azure-specstory

# Now handles:
# - New files (1-2 at a time)
# - File modifications
# - Every 24 hours check
```

---

## Configuration Options

```bash
# Smaller batches (slower, gentler on system)
python scripts/batch-ingestion-controller.py azure-specstory --batch-size 5

# More aggressive CPU usage
python scripts/batch-ingestion-controller.py azure-specstory --max-cpu 90

# Lower memory threshold
python scripts/batch-ingestion-controller.py azure-specstory --max-memory 75
```

---

## Key Features

### ✅ Backend Agnostic
Works with ALL backends (JSON, PostgreSQL, MongoDB)

### ✅ Uses Existing Duplicate Detection
Reuses watcher's hash-based duplicate checking

### ✅ Resource Aware
- Pauses if CPU > 80%
- Pauses if Memory > 85%
- Configurable thresholds

### ✅ Handles File Changes
- Reads current content from disk (not cached)
- Skips deleted files gracefully
- Always ingests latest version

### ✅ Pause/Resume
- Progress saved after each batch
- Kill and restart anytime
- No data loss

---

## Expected Timeline

**With Default Settings (batch_size=10, no throttling):**

```
Hour 1:   ~10 files    (3066 remaining)
Hour 8:   ~80 files    (2996 remaining)
Day 1:    ~240 files   (2836 remaining)
Week 1:   ~1680 files  (1396 remaining)
Week 2:   ~3360 files  (COMPLETE! 🎉)
```

**With Resource Throttling (CPU/Memory pauses):**
- Could take 3-4 weeks depending on system usage
- System remains responsive for your work

---

## What Happens When List is Empty?

```bash
# Run batch controller again
python scripts/batch-ingestion-controller.py azure-specstory

# Output:
✅ No pending files - bulk ingestion already complete!

💡 For ongoing file monitoring, start the watcher:
   python hybridrag.py db watch start azure-specstory
```

---

## Files Created

| File | Purpose |
|------|---------|
| `~/.hybridrag/batch_ingestion/azure-specstory.pending.txt` | List of files to process |
| `scripts/batch-ingestion-controller.py` | The batch controller |
| `docs/BATCH_INGESTION_FLOW.md` | Detailed architecture |
| `docs/BATCH_INGESTION_QUICKSTART.md` | This guide |

---

## Troubleshooting

**"No files found during discovery"**
- Fixed! Was looking for `.history` instead of `history`
- Re-run discovery: `python scripts/batch-ingestion-controller.py azure-specstory --discover`

**"Process seems stuck"**
- LightRAG processing is slow (embeddings + entity extraction)
- Expected: 3-10 minutes per file
- Check: `wc -l ~/.hybridrag/batch_ingestion/azure-specstory.pending.txt`

**"Want to speed it up"**
```bash
# Increase batch size
python scripts/batch-ingestion-controller.py azure-specstory --batch-size 20

# Allow higher CPU usage
python scripts/batch-ingestion-controller.py azure-specstory --max-cpu 95
```

**"Need to stop and resume later"**
- Just Ctrl+C - progress is saved automatically
- Resume anytime with same command

---

## Next Steps

1. **Run the batch ingestion** (let it run for days/weeks)
2. **Monitor progress occasionally** (check pending file count)
3. **When complete, start regular watcher** for ongoing monitoring
4. **Query your SpecStory history!**
   ```bash
   python hybridrag.py --db azure-specstory interactive
   ```

---

**Status:** ✅ System tested and working! (1 file successfully processed)

**Discovered:** 3076 files
**Remaining:** 3075 files
**Progress:** 0.03% complete
