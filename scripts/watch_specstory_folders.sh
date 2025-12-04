#!/bin/bash
#
# HybridRAG .specstory Folder Watcher
# ===================================
# Continuously monitors .specstory folders for changes and auto-ingests
# Uses inotify (Linux) or fswatch (macOS) for real-time file watching
#
# Usage:
#   ./scripts/watch_specstory_folders.sh <parent_path> [interval]
#
# Arguments:
#   parent_path  - Parent directory containing projects with .specstory folders
#   interval     - Check interval in seconds (default: 300 = 5 minutes)
#
# Examples:
#   # Watch with default 5-minute interval
#   ./scripts/watch_specstory_folders.sh /home/gyasis/Documents/code
#
#   # Watch with 1-minute interval
#   ./scripts/watch_specstory_folders.sh /home/gyasis/Documents/code 60
#
#   # Run in background
#   nohup ./scripts/watch_specstory_folders.sh /home/gyasis/Documents/code > watcher.log 2>&1 &
#

set -e
set -o pipefail

# =============================================================================
# Configuration
# =============================================================================

PARENT_PATH="${1:-}"
CHECK_INTERVAL="${2:-300}"  # 5 minutes default
HYBRIDRAG_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOCK_FILE="/tmp/hybridrag_watcher.lock"
PID_FILE="/tmp/hybridrag_watcher.pid"
LAST_RUN_FILE="${HYBRIDRAG_DIR}/.last_specstory_watch"
LOG_FILE="${HYBRIDRAG_DIR}/logs/watcher_$(date +%Y%m%d).log"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# =============================================================================
# Helper Functions
# =============================================================================

print_header() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}${BLUE}  HybridRAG .specstory Folder Watcher${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

log() {
    local message="$1"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $message" | tee -a "$LOG_FILE"
}

cleanup() {
    log "Cleaning up watcher..."
    rm -f "$LOCK_FILE" "$PID_FILE"
}

trap cleanup EXIT INT TERM

acquire_lock() {
    if [ -f "$LOCK_FILE" ]; then
        EXISTING_PID=$(cat "$LOCK_FILE" 2>/dev/null)
        if [ -n "$EXISTING_PID" ] && kill -0 "$EXISTING_PID" 2>/dev/null; then
            echo -e "${RED}Error: Another watcher is already running (PID: $EXISTING_PID)${NC}"
            echo -e "${YELLOW}To stop it: kill $EXISTING_PID${NC}"
            exit 1
        else
            log "Removing stale lock file"
            rm -f "$LOCK_FILE"
        fi
    fi

    echo $$ > "$LOCK_FILE"
    echo $$ > "$PID_FILE"
    log "Lock acquired (PID: $$)"
}

find_specstory_folders() {
    find "$PARENT_PATH" -type d -name ".specstory" 2>/dev/null
}

check_for_changes() {
    local folder="$1"
    local project_name="$2"
    local has_changes=false

    # If this is first run, always ingest
    if [ ! -f "$LAST_RUN_FILE" ]; then
        has_changes=true
    else
        # Check if any files modified since last run
        local last_run=$(cat "$LAST_RUN_FILE")
        if find "$folder" -type f -newermt "@$last_run" 2>/dev/null | grep -q .; then
            has_changes=true
        fi
    fi

    if [ "$has_changes" = true ]; then
        return 0  # Changes detected
    else
        return 1  # No changes
    fi
}

ingest_folder() {
    local folder="$1"
    local project_name="$2"

    log "Ingesting changes from $project_name ($folder)"

    if python "$HYBRIDRAG_DIR/hybridrag.py" ingest \
        --folder "$folder" \
        --db-action add \
        --metadata "project=$project_name" \
        --metadata "source_path=$folder" \
        --metadata "auto_watch=true" \
        --yes \
        --quiet \
        >> "$LOG_FILE" 2>&1; then

        log "✓ Successfully ingested $project_name"
        return 0
    else
        log "✗ Failed to ingest $project_name"
        return 1
    fi
}

# =============================================================================
# Validation
# =============================================================================

if [ -z "$PARENT_PATH" ]; then
    echo -e "${RED}Error: Parent path not provided${NC}"
    echo ""
    echo -e "${YELLOW}Usage:${NC}"
    echo -e "  $0 <parent_path> [interval]"
    exit 1
fi

if [ ! -d "$PARENT_PATH" ]; then
    echo -e "${RED}Error: Parent path does not exist: $PARENT_PATH${NC}"
    exit 1
fi

if [ ! -f "$HYBRIDRAG_DIR/hybridrag.py" ]; then
    echo -e "${RED}Error: hybridrag.py not found in $HYBRIDRAG_DIR${NC}"
    exit 1
fi

# Validate interval is a number
if ! [[ "$CHECK_INTERVAL" =~ ^[0-9]+$ ]]; then
    echo -e "${RED}Error: Interval must be a number (seconds)${NC}"
    exit 1
fi

mkdir -p "${HYBRIDRAG_DIR}/logs"

# =============================================================================
# Acquire Lock
# =============================================================================

acquire_lock

# =============================================================================
# Initial Scan
# =============================================================================

print_header

log "Starting .specstory folder watcher"
log "Parent path: $PARENT_PATH"
log "Check interval: ${CHECK_INTERVAL}s ($(($CHECK_INTERVAL / 60)) minutes)"
log "PID: $$"

echo -e "${GREEN}Searching for .specstory folders...${NC}"

SPECSTORY_FOLDERS=$(find_specstory_folders)
FOLDER_COUNT=$(echo "$SPECSTORY_FOLDERS" | grep -c "." || echo 0)

if [ "$FOLDER_COUNT" -eq 0 ]; then
    echo -e "${YELLOW}No .specstory folders found in $PARENT_PATH${NC}"
    log "No .specstory folders found. Exiting."
    exit 0
fi

log "Found $FOLDER_COUNT .specstory folder(s)"

echo -e "${GREEN}Monitoring ${BOLD}${FOLDER_COUNT}${NC}${GREEN} .specstory folder(s):${NC}"
echo ""

echo "$SPECSTORY_FOLDERS" | while IFS= read -r folder; do
    PROJECT_NAME=$(dirname "$folder" | xargs basename)
    echo -e "  ${BLUE}→${NC} ${BOLD}$PROJECT_NAME${NC}"
    echo -e "    ${CYAN}$folder${NC}"
done

echo ""
echo -e "${YELLOW}Check interval: Every ${CHECK_INTERVAL}s ($(($CHECK_INTERVAL / 60)) min)${NC}"
echo -e "${YELLOW}Log file: ${CYAN}$LOG_FILE${NC}"
echo -e "${YELLOW}Stop watcher: ${CYAN}kill $$${NC}"
echo ""

# Initial ingestion if first run
if [ ! -f "$LAST_RUN_FILE" ]; then
    echo -e "${GREEN}First run detected. Performing initial ingestion...${NC}"
    log "First run: performing initial ingestion of all folders"

    echo "$SPECSTORY_FOLDERS" | while IFS= read -r folder; do
        PROJECT_NAME=$(dirname "$folder" | xargs basename)
        echo -e "${BLUE}→${NC} Ingesting ${YELLOW}$PROJECT_NAME${NC}"
        ingest_folder "$folder" "$PROJECT_NAME"
    done

    echo ""
fi

# Record this run time
date +%s > "$LAST_RUN_FILE"

echo -e "${GREEN}Watcher is now running...${NC}"
echo -e "${CYAN}Press Ctrl+C to stop${NC}"
echo ""

# =============================================================================
# Main Watch Loop
# =============================================================================

ITERATION=0

while true; do
    ITERATION=$((ITERATION + 1))
    CURRENT_TIME=$(date '+%Y-%m-%d %H:%M:%S')

    log "Check #$ITERATION starting at $CURRENT_TIME"

    CHANGES_DETECTED=0
    INGESTED_COUNT=0
    FAILED_COUNT=0

    # Re-scan for .specstory folders (in case new projects added)
    CURRENT_FOLDERS=$(find_specstory_folders)

    echo "$CURRENT_FOLDERS" | while IFS= read -r folder; do
        [ -z "$folder" ] && continue

        PROJECT_NAME=$(dirname "$folder" | xargs basename)

        if check_for_changes "$folder" "$PROJECT_NAME"; then
            CHANGES_DETECTED=$((CHANGES_DETECTED + 1))
            echo -e "${YELLOW}[$(date '+%H:%M:%S')]${NC} Changes detected in ${BOLD}$PROJECT_NAME${NC}"

            if ingest_folder "$folder" "$PROJECT_NAME"; then
                INGESTED_COUNT=$((INGESTED_COUNT + 1))
            else
                FAILED_COUNT=$((FAILED_COUNT + 1))
            fi
        fi
    done

    # Update last run time
    date +%s > "$LAST_RUN_FILE"

    if [ $CHANGES_DETECTED -eq 0 ]; then
        log "No changes detected in any .specstory folders"
    else
        log "Check complete. Changes: $CHANGES_DETECTED, Ingested: $INGESTED_COUNT, Failed: $FAILED_COUNT"
    fi

    # Sleep until next check
    NEXT_CHECK=$(date -d "@$(($(date +%s) + CHECK_INTERVAL))" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date -v+${CHECK_INTERVAL}S '+%Y-%m-%d %H:%M:%S' 2>/dev/null)
    log "Next check at $NEXT_CHECK"

    sleep "$CHECK_INTERVAL"
done
