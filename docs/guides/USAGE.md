# HybridRAG Usage Guide

Comprehensive guide for the unified `hybridrag.py` interface.

## Quick Start

```bash
# 1. Setup environment
source .venv/bin/activate  # or use: uv run

# 2. Ingest data
python hybridrag.py ingest --folder ./data

# 3. Query the database
python hybridrag.py interactive
```

## Commands Overview

| Command | Purpose | Example |
|---------|---------|---------|
| `query` | One-shot query | `hybridrag.py query --text "Find tables"` |
| `interactive` | Interactive CLI | `hybridrag.py interactive` |
| `ingest` | Data ingestion | `hybridrag.py ingest --folder ./data` |
| `status` | System status | `hybridrag.py status` |
| `check-db` | Database info | `hybridrag.py check-db` |

---

## Query Commands

### One-Shot Query

Execute a single query and exit:

```bash
# Basic query (hybrid mode by default)
python hybridrag.py query --text "What tables are related to appointments?"

# Specific mode
python hybridrag.py query --text "..." --mode local
python hybridrag.py query --text "..." --mode global
python hybridrag.py query --text "..." --mode hybrid
python hybridrag.py query --text "..." --mode naive
python hybridrag.py query --text "..." --mode mix

# With agentic reasoning (multi-hop)
python hybridrag.py query --text "..." --agentic

# Using PromptChain for advanced reasoning
python hybridrag.py query --text "..." --use-promptchain --agentic
```

### Interactive Mode

Start an interactive query session:

```bash
python hybridrag.py interactive
```

**Interactive Commands:**
```
:local      - Switch to local mode (specific details)
:global     - Switch to global mode (broad overviews)
:hybrid     - Switch to hybrid mode (balanced)
:naive      - Switch to naive mode (simple vector search)
:mix        - Switch to mix mode (multi-strategy)
:context    - Toggle context-only mode
:help       - Show help
:quit       - Exit
```

**Query Modes Explained:**

- **local**: Best for specific entity relationships, detailed connections
  - Example: "How do APPOINTMENT and PATIENT tables relate?"

- **global**: Best for high-level overviews, broad patterns
  - Example: "What are all the Collector category tables?"

- **hybrid**: Balanced combination of local detail and global context
  - Example: "Explain the appointment workflow and related tables"

- **naive**: Simple vector retrieval without graph reasoning
  - Example: Quick searches when graph context isn't needed

- **mix**: Advanced multi-strategy retrieval approach
  - Example: Complex queries requiring multiple reasoning paths

---

## Ingestion Commands

### Basic Ingestion

Ingest documents from a folder:

```bash
# Single folder
python hybridrag.py ingest --folder ./data

# Multiple folders
python hybridrag.py ingest --folder ./data --folder ./more_data

# Non-recursive (top-level only)
python hybridrag.py ingest --folder ./data --no-recursive
```

### Database Management

Control what happens to existing database:

```bash
# Use existing database (skip ingestion)
python hybridrag.py ingest --db-action use

# Add to existing database
python hybridrag.py ingest --folder ./new_data --db-action add

# Start fresh (delete existing and create new)
python hybridrag.py ingest --folder ./data --db-action fresh
```

**⚠️ Warning:** `--db-action fresh` will delete all existing data!

### Multiprocess Ingestion

Use multiprocess architecture for large datasets:

```bash
python hybridrag.py ingest --folder ./data --multiprocess
```

Benefits:
- Parallel processing
- Better resource utilization
- Faster ingestion for large datasets

---

## Management Commands

### System Status

Check overall system health:

```bash
python hybridrag.py status
```

Shows:
- Database location and size
- Number of files
- Process status (if running)
- Ingestion progress

### Database Check

Get detailed database statistics:

```bash
python hybridrag.py check-db
```

Shows:
- Database existence
- File breakdown (kv_store, vdb files)
- Storage usage
- File counts

---

## Advanced Usage

### Custom Database Location

Use a different database directory:

```bash
python hybridrag.py --working-dir ./custom_db query --text "..."
python hybridrag.py --working-dir ./custom_db interactive
```

### Custom Configuration

Provide a custom config file:

```bash
python hybridrag.py --config ./my_config.yaml ingest --folder ./data
```

### Programmatic Usage

Use HybridRAG in Python scripts:

```python
import asyncio
from hybridrag import HybridRAGCLI
from argparse import Namespace

# Simulate command-line args
args = Namespace(
    command='query',
    text='Find appointment tables',
    mode='hybrid',
    agentic=False,
    use_promptchain=False,
    working_dir='./athena_lightrag_db'
)

# Run query
cli = HybridRAGCLI(args)
asyncio.run(cli.run())
```

---

## Common Workflows

### First-Time Setup

```bash
# 1. Activate environment
source .venv/bin/activate

# 2. Check database status
python hybridrag.py check-db

# 3. Ingest data (if needed)
python hybridrag.py ingest --folder ./data

# 4. Start querying
python hybridrag.py interactive
```

### Adding New Data

```bash
# Add to existing database without losing current data
python hybridrag.py ingest --folder ./new_documents --db-action add
```

### Switching Databases

```bash
# Create separate database for different projects
python hybridrag.py --working-dir ./project_a_db ingest --folder ./project_a
python hybridrag.py --working-dir ./project_b_db ingest --folder ./project_b

# Query specific database
python hybridrag.py --working-dir ./project_a_db interactive
```

### Batch Queries

```bash
# Process multiple queries non-interactively
for query in "query1" "query2" "query3"; do
    python hybridrag.py query --text "$query" --mode hybrid >> results.txt
done
```

---

## Troubleshooting

### Database Not Found

```bash
# Check if database exists
python hybridrag.py check-db

# If not, create it
python hybridrag.py ingest --folder ./data
```

### No Results for Queries

```bash
# Check database has data
python hybridrag.py check-db

# Try different query modes
python hybridrag.py query --text "..." --mode global  # Broader search
python hybridrag.py query --text "..." --mode naive   # Simpler search
```

### Slow Queries

```bash
# Use simpler modes for faster results
python hybridrag.py query --text "..." --mode naive

# Or use local mode for specific queries
python hybridrag.py query --text "..." --mode local
```

### Ingestion Errors

```bash
# Check logs
tail -f hybridrag.log

# Try with smaller batch
python hybridrag.py ingest --folder ./small_subset
```

---

## Performance Tips

1. **Query Mode Selection**:
   - Use `local` for specific, targeted queries (fastest)
   - Use `global` for broad overviews
   - Use `hybrid` for balanced results
   - Use `naive` when graph reasoning isn't needed

2. **Ingestion Optimization**:
   - Use `--multiprocess` for large datasets
   - Ingest in batches for very large collections
   - Monitor with `status` command during ingestion

3. **Database Management**:
   - Keep separate databases for different projects
   - Use `--db-action add` to update existing database
   - Periodically check database size with `check-db`

4. **Agentic Queries**:
   - Only use `--agentic` for complex multi-hop queries
   - Simple queries are faster without agentic reasoning
   - Use `--use-promptchain` for most advanced reasoning

---

## Help & Support

```bash
# Get help on any command
python hybridrag.py --help
python hybridrag.py query --help
python hybridrag.py ingest --help

# Check examples
ls examples/

# Read documentation
cat README.md
cat memory-bank/projectbrief.md
```

For detailed documentation, see:
- `README.md` - Project overview
- `memory-bank/` - Comprehensive project documentation
- `examples/` - Example scripts and usage patterns
- `legacy/README.md` - Migration guide from old scripts
