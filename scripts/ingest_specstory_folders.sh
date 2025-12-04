#!/bin/bash
#
# HybridRAG Selective .specstory Folder Ingestion Script
# ======================================================
# Finds and ingests ONLY .specstory folders from specified parent path
# Supports both unified database and separate database modes
#
# Usage:
#   ./scripts/ingest_specstory_folders.sh <parent_path> [db_action]
#
# Arguments:
#   parent_path  - Parent directory to search for .specstory folders
#   db_action    - 'fresh' (start new DB) or 'add' (append to existing)
#                  Default: 'add'
#
# Examples:
#   # Fresh ingestion (creates new database)
#   ./scripts/ingest_specstory_folders.sh /home/gyasis/Documents/code fresh
#
#   # Add to existing database
#   ./scripts/ingest_specstory_folders.sh /home/gyasis/Documents/code add
#
#   # Process multiple paths into unified DB
#   ./scripts/ingest_specstory_folders.sh /home/gyasis/Documents/code fresh
#   ./scripts/ingest_specstory_folders.sh /mnt/projects add
#

set -e  # Exit on error
set -o pipefail  # Catch errors in pipes

# =============================================================================
# Configuration
# =============================================================================

PARENT_PATH="${1:-}"
DB_ACTION="${2:-add}"
HYBRIDRAG_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TEMP_FILE="/tmp/specstory_paths_$$.txt"
LOG_FILE="${HYBRIDRAG_DIR}/logs/ingestion_$(date +%Y%m%d_%H%M%S).log"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# =============================================================================
# Helper Functions
# =============================================================================

print_header() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}${BLUE}  HybridRAG Multi-Project Ingestion${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

print_usage() {
    echo -e "${YELLOW}Usage:${NC}"
    echo -e "  $0 <parent_path> [db_action]"
    echo ""
    echo -e "${YELLOW}Arguments:${NC}"
    echo -e "  parent_path  - Directory to search for .specstory folders"
    echo -e "  db_action    - 'fresh' or 'add' (default: add)"
    echo ""
    echo -e "${YELLOW}Examples:${NC}"
    echo -e "  $0 /home/gyasis/Documents/code fresh"
    echo -e "  $0 /home/gyasis/Documents/code add"
    echo ""
}

log() {
    local message="$1"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $message" | tee -a "$LOG_FILE"
}

cleanup() {
    rm -f "$TEMP_FILE"
}

trap cleanup EXIT

# =============================================================================
# Validation
# =============================================================================

# Check if parent path provided
if [ -z "$PARENT_PATH" ]; then
    echo -e "${RED}Error: Parent path not provided${NC}"
    echo ""
    print_usage
    exit 1
fi

# Validate parent path exists
if [ ! -d "$PARENT_PATH" ]; then
    echo -e "${RED}Error: Parent path does not exist: $PARENT_PATH${NC}"
    exit 1
fi

# Validate db_action parameter
if [[ ! "$DB_ACTION" =~ ^(fresh|add)$ ]]; then
    echo -e "${RED}Error: db_action must be 'fresh' or 'add', got: $DB_ACTION${NC}"
    print_usage
    exit 1
fi

# Check if Python and hybridrag.py exist
if [ ! -f "$HYBRIDRAG_DIR/hybridrag.py" ]; then
    echo -e "${RED}Error: hybridrag.py not found in $HYBRIDRAG_DIR${NC}"
    exit 1
fi

# Create logs directory
mkdir -p "${HYBRIDRAG_DIR}/logs"

# =============================================================================
# Main Script
# =============================================================================

print_header

log "Starting .specstory folder search and ingestion"
log "Parent path: $PARENT_PATH"
log "Database action: $DB_ACTION"

echo -e "${GREEN}Searching for .specstory folders in:${NC}"
echo -e "  ${CYAN}$PARENT_PATH${NC}"
echo ""

# Find all .specstory folders
echo -e "${YELLOW}Scanning directory tree...${NC}"
log "Executing find command"

if ! find "$PARENT_PATH" -type d -name ".specstory" > "$TEMP_FILE" 2>/dev/null; then
    echo -e "${RED}Error: Failed to search directory${NC}"
    log "ERROR: find command failed"
    exit 1
fi

# Count folders found
FOLDER_COUNT=$(wc -l < "$TEMP_FILE")
log "Found $FOLDER_COUNT .specstory folder(s)"

if [ "$FOLDER_COUNT" -eq 0 ]; then
    echo -e "${YELLOW}No .specstory folders found in $PARENT_PATH${NC}"
    echo ""
    echo -e "${YELLOW}Tip: Ensure your projects have a .specstory subdirectory${NC}"
    echo -e "Example structure:"
    echo -e "  ${CYAN}$PARENT_PATH/${NC}"
    echo -e "  ${CYAN}├── project1/${NC}"
    echo -e "  ${CYAN}│   └── .specstory/     ${GREEN}← Will be found${NC}"
    echo -e "  ${CYAN}└── project2/${NC}"
    echo -e "  ${CYAN}    └── .specstory/     ${GREEN}← Will be found${NC}"
    exit 0
fi

echo -e "${GREEN}Found ${BOLD}${FOLDER_COUNT}${NC}${GREEN} .specstory folder(s):${NC}"
echo ""

# Display found folders with parent project name
cat "$TEMP_FILE" | while IFS= read -r folder; do
    PROJECT_NAME=$(dirname "$folder" | xargs basename)
    echo -e "  ${BLUE}→${NC} ${BOLD}$PROJECT_NAME${NC} ${YELLOW}(.specstory)${NC}"
    echo -e "    ${CYAN}$folder${NC}"
done

echo ""
echo -e "${YELLOW}Database action: ${BOLD}${DB_ACTION}${NC}"

if [ "$DB_ACTION" == "fresh" ]; then
    echo -e "${YELLOW}⚠️  Warning: This will create a NEW database (existing data will be lost)${NC}"
else
    echo -e "${GREEN}✓ Will ADD to existing database${NC}"
fi

echo ""

# Confirm before proceeding (skip if running in non-interactive mode)
if [ -t 0 ]; then
    read -p "Proceed with ingestion? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}Ingestion cancelled.${NC}"
        log "Ingestion cancelled by user"
        exit 0
    fi
else
    echo -e "${BLUE}Running in non-interactive mode, proceeding automatically...${NC}"
    log "Running in non-interactive mode"
fi

echo ""
echo -e "${GREEN}Starting ingestion...${NC}"
echo ""
log "Beginning ingestion of $FOLDER_COUNT folders"

# =============================================================================
# Process Each Folder
# =============================================================================

COUNTER=0
SUCCESS_COUNT=0
FAILED_COUNT=0
CURRENT_DB_ACTION="$DB_ACTION"

while IFS= read -r folder; do
    COUNTER=$((COUNTER + 1))
    PROJECT_NAME=$(dirname "$folder" | xargs basename)

    echo -e "${BLUE}[$COUNTER/$FOLDER_COUNT]${NC} Processing: ${BOLD}${YELLOW}$PROJECT_NAME${NC}"
    echo -e "  Path: ${CYAN}$folder${NC}"
    echo -e "  DB Action: ${CYAN}$CURRENT_DB_ACTION${NC}"

    log "[$COUNTER/$FOLDER_COUNT] Processing $PROJECT_NAME from $folder (action: $CURRENT_DB_ACTION)"

    # Ingest with metadata tagging
    if python "$HYBRIDRAG_DIR/hybridrag.py" ingest \
        --folder "$folder" \
        --db-action "$CURRENT_DB_ACTION" \
        --metadata "project=$PROJECT_NAME" \
        --metadata "source_path=$folder" \
        >> "$LOG_FILE" 2>&1; then

        echo -e "  ${GREEN}✓ Success${NC}"
        log "  SUCCESS: $PROJECT_NAME ingested"
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    else
        echo -e "  ${RED}✗ Failed${NC}"
        log "  FAILED: $PROJECT_NAME ingestion failed"
        FAILED_COUNT=$((FAILED_COUNT + 1))
    fi

    echo ""

    # After first folder with 'fresh', switch to 'add' for remaining folders
    if [ "$CURRENT_DB_ACTION" == "fresh" ]; then
        CURRENT_DB_ACTION="add"
    fi

done < "$TEMP_FILE"

# =============================================================================
# Summary
# =============================================================================

echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}Ingestion Complete!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo -e "${BOLD}Summary:${NC}"
echo -e "  Total folders: ${CYAN}$FOLDER_COUNT${NC}"
echo -e "  Successful: ${GREEN}$SUCCESS_COUNT${NC}"
echo -e "  Failed: ${RED}$FAILED_COUNT${NC}"
echo ""

log "Ingestion complete. Total: $FOLDER_COUNT, Success: $SUCCESS_COUNT, Failed: $FAILED_COUNT"

if [ $FAILED_COUNT -gt 0 ]; then
    echo -e "${YELLOW}⚠️  Some folders failed to ingest. Check log file:${NC}"
    echo -e "  ${CYAN}$LOG_FILE${NC}"
    echo ""
fi

echo -e "${BOLD}Next steps:${NC}"
echo -e "  ${BLUE}1.${NC} Check database: ${YELLOW}python hybridrag.py check-db${NC}"
echo -e "  ${BLUE}2.${NC} View statistics: ${YELLOW}python hybridrag.py status${NC}"
echo -e "  ${BLUE}3.${NC} Start querying: ${YELLOW}python hybridrag.py interactive${NC}"
echo ""

echo -e "${BOLD}Example queries:${NC}"
echo -e "  ${CYAN}→${NC} How did we implement authentication across all projects?"
echo -e "  ${CYAN}→${NC} Show me all database migrations from project history"
echo -e "  ${CYAN}→${NC} What API patterns appear in our codebase?"
echo ""

log "Script completed successfully"

# Exit with error if any failures occurred
if [ $FAILED_COUNT -gt 0 ]; then
    exit 1
fi

exit 0
