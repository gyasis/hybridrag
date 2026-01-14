# HybridRAG Database Manager Cheatsheet

> CLI commands and TUI dashboard reference for database management

---

## CLI: Database Registry Commands

### Register Database

```bash
# Basic registration
python hybridrag.py db register mydb --path ./db_data --source ./docs

# Full options
python hybridrag.py db register mydb \
    --path ./db_data \                    # Database storage path
    --source ./docs \                     # Source folder to watch
    --type filesystem \                   # filesystem|specstory|api|schema
    --auto-watch \                        # Enable auto-watching
    --interval 300 \                      # Watch interval (seconds)
    --model azure/gpt-4o \                # LLM model
    --embed-model azure/text-embedding-3-small \
    --description "My docs" \             # Description
    --extensions ".md,.txt,.py" \         # File extensions to include
    --backend json \                      # json|postgres
    --connection-string "postgresql://..." # For postgres backend
```

### List & Show

```bash
python hybridrag.py db list              # List all registered databases
python hybridrag.py db show mydb         # Show database details
python hybridrag.py db show mydb --stats # Include KG stats + last 5 processed files
python hybridrag.py db show mydb --json  # Output as JSON
```

### Update Settings

```bash
python hybridrag.py db update mydb --interval 600        # Change interval
python hybridrag.py db update mydb --model azure/gpt-4o  # Change model
python hybridrag.py db update mydb --auto-watch false    # Disable auto-watch
python hybridrag.py db update mydb --description "New description"
```

### Sync & Unregister

```bash
python hybridrag.py db sync mydb         # Incremental sync (new files only)
python hybridrag.py db sync mydb --fresh # Full re-ingest from source

python hybridrag.py db unregister mydb   # Remove from registry (keeps files)
```

---

## CLI: Watcher Commands

### Control

```bash
python hybridrag.py db watch start mydb   # Start watcher daemon
python hybridrag.py db watch stop mydb    # Stop watcher
python hybridrag.py db watch status       # Status of all watchers
python hybridrag.py db watch status mydb  # Status of specific watcher

# Using global --db flag (same effect)
python hybridrag.py --db mydb db watch start
python hybridrag.py --db mydb db watch stop
python hybridrag.py --db mydb db watch status
```

### Systemd Integration (Persistent)

```bash
# Start with systemd (survives reboots)
python hybridrag.py db watch start mydb --systemd

# Install all auto-watch DBs as systemd units
python hybridrag.py db watch install-systemd
python hybridrag.py db watch uninstall-systemd

# Manage with systemctl
systemctl --user status hybridrag-watcher@mydb.service
systemctl --user restart hybridrag-watcher@mydb.service
journalctl --user -u hybridrag-watcher@mydb.service -f
```

---

## CLI: Backend Commands

### Status

```bash
python hybridrag.py backend status           # Show all backends status
python hybridrag.py backend status mydb      # Specific database backend

# Using global --db flag (same effect)
python hybridrag.py --db mydb backend status
```

### PostgreSQL Setup

```bash
# Auto-provision Docker PostgreSQL with pgvector
python hybridrag.py backend setup-docker \
    --port 5432 \
    --password mypass \
    --data-dir ~/.hybridrag/pg-data

# Register with PostgreSQL backend
python hybridrag.py db register mydb \
    --path ./db \
    --source ./docs \
    --backend postgres \
    --connection-string "postgresql://hybridrag:mypass@localhost:5432/hybridrag"

# Or with individual params
python hybridrag.py db register mydb \
    --backend postgres \
    --postgres-host localhost \
    --postgres-port 5432 \
    --postgres-user hybridrag \
    --postgres-password mypass \
    --postgres-database hybridrag
```

### Migration (JSON to PostgreSQL)

```bash
# Preview migration (dry run)
python hybridrag.py backend migrate mydb \
    --connection-string "postgresql://..." \
    --dry-run

# Safe staged migration (4-phase)
python hybridrag.py backend migrate mydb \
    --connection-string "postgresql://..." \
    --staged \
    --batch-size 1000

# Backup management
python hybridrag.py backend migrate mydb --backup-only
python hybridrag.py backend migrate mydb --list-backups
python hybridrag.py backend migrate mydb --rollback BACKUP_ID
```

---

## CLI: Quick Status Commands

```bash
python hybridrag.py status              # Overall system status
python hybridrag.py check-db            # Check database health
python hybridrag.py snapshot            # Database snapshot info
python hybridrag.py db list             # List all registered databases
python hybridrag.py db show mydb --stats # Show KG stats + last 5 processed files
```

---

## TUI: Monitor Dashboard

### Launch

```bash
python hybridrag.py monitor              # Start TUI dashboard
python hybridrag.py monitor --refresh 5  # Custom refresh rate (seconds)
python hybridrag.py monitor --new        # Start with new database wizard
python hybridrag.py monitor --mouse      # Enable mouse support
```

### Keyboard Shortcuts

| Key | Action | Description |
|-----|--------|-------------|
| `q` | Quit | Exit the dashboard |
| `r` | Refresh | Force refresh all panels |
| `n` | New | Open new database wizard |
| `s` | Start | Start watcher for selected DB |
| `x` | Stop | Stop watcher for selected DB |
| `a` | Auto-watch | Toggle auto-watch setting |
| `y` | Sync | Force sync/re-ingest |
| `l` | Logs | View watcher logs |
| `t` | Toggle Logs | Switch log scope (global/DB) |
| `h` | History | Toggle ingestion history panel |
| `i` | Info | Show detailed database info |
| `m` | Maximize | Toggle maximize current panel |

### Dashboard Panels

| Panel | Description |
|-------|-------------|
| **Timeline** | Visual activity timeline |
| **Databases** | List of registered databases with status |
| **Watcher** | Current watcher status and info |
| **Actions** | Context-sensitive action buttons |
| **Source Files** | Recently processed files |
| **Activity Log** | Real-time log messages |

### Panel Navigation

- Use **arrow keys** or **Tab** to navigate between panels
- **Enter** to select/activate item
- **m** to maximize focused panel (press again to restore)

---

## Quick Reference Tables

### Database Types

| Type | Use Case | Key Options |
|------|----------|-------------|
| `filesystem` | Documents, code, notes | `--extensions` |
| `specstory` | Claude Code conversations | `--jira-project` |
| `api` | REST API sources | `--api-config` |
| `schema` | Database schemas | `--schema-config` |

### Backend Types

| Backend | Best For | Setup |
|---------|----------|-------|
| `json` | Small DBs (<1GB), simple setup | Default, no config |
| `postgres` | Large DBs, production, concurrent | Docker or existing PG |

### Watcher Modes

| Mode | When to Use | Persistence |
|------|-------------|-------------|
| Standalone | Development, testing | Until terminal closes |
| Systemd | Production, always-on | Survives reboots |

---

## File Locations

| Item | Path |
|------|------|
| Registry | `~/.hybridrag/registry.yaml` |
| Config pointer | `~/.hybridrag/config_pointer` |
| PID files | `~/.hybridrag/watchers/<name>.pid` |
| Watcher logs | `./logs/watcher_<name>.log` |
| JSON DB files | `<path>/kv_store_*.json`, `vdb_*.json`, `*.graphml` |
| Systemd units | `~/.config/systemd/user/hybridrag-watcher@.service` |

---

## Common Workflows

### New Database Setup

```bash
# 1. Register
python hybridrag.py db register mydb --path ./mydb --source ./docs --auto-watch

# 2. Initial ingest
python hybridrag.py ingest --folder ./docs --working-dir ./mydb

# 3. Start watcher
python hybridrag.py db watch start mydb

# 4. Verify
python hybridrag.py db show mydb
```

### Migrate to PostgreSQL

```bash
# 1. Setup PostgreSQL
python hybridrag.py backend setup-docker --password mypass

# 2. Preview migration
python hybridrag.py backend migrate mydb --connection-string "postgresql://..." --dry-run

# 3. Run staged migration
python hybridrag.py backend migrate mydb --connection-string "postgresql://..." --staged

# 4. Verify
python hybridrag.py backend status mydb
```

### Troubleshooting

```bash
# Stale PID file
rm ~/.hybridrag/watchers/mydb.pid

# Force re-registration
python hybridrag.py db unregister mydb
python hybridrag.py db register mydb --path ./db --source ./docs

# View watcher logs
tail -f logs/watcher_mydb.log

# Check database health
python hybridrag.py --db mydb check-db
```
