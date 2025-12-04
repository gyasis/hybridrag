#!/bin/bash
#
# HybridRAG Separate Database Ingestion Script
# ============================================
# Creates SEPARATE databases for each project's .specstory folder
# Use this when you need strict isolation between projects
#
# Usage:
#   ./scripts/ingest_separate_databases.sh <parent_path>
#
# Arguments:
#   parent_path  - Parent directory to search for .specstory folders
#
# Examples:
#   ./scripts/ingest_separate_databases.sh /home/gyasis/Documents/code
#
# Output:
#   Creates separate database directories:
#     - lightrag_db_project1/
#     - lightrag_db_project2/
#     - lightrag_db_project3/
#
# Querying specific database:
#   LIGHTRAG_WORKING_DIR="./lightrag_db_project1" python hybridrag.py interactive
#

set -e
set -o pipefail

# =============================================================================
# Configuration
# =============================================================================

PARENT_PATH="${1:-}"
HYBRIDRAG_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TEMP_FILE="/tmp/specstory_separate_$$.txt"
LOG_FILE="${HYBRIDRAG_DIR}/logs/separate_ingestion_$(date +%Y%m%d_%H%M%S).log"

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
    echo -e "${BOLD}${BLUE}  HybridRAG Separate Database Ingestion${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

print_usage() {
    echo -e "${YELLOW}Usage:${NC}"
    echo -e "  $0 <parent_path>"
    echo ""
    echo -e "${YELLOW}Example:${NC}"
    echo -e "  $0 /home/gyasis/Documents/code"
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

if [ -z "$PARENT_PATH" ]; then
    echo -e "${RED}Error: Parent path not provided${NC}"
    echo ""
    print_usage
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

mkdir -p "${HYBRIDRAG_DIR}/logs"

# =============================================================================
# Main Script
# =============================================================================

print_header

log "Starting separate database ingestion"
log "Parent path: $PARENT_PATH"

echo -e "${GREEN}Searching for .specstory folders in:${NC}"
echo -e "  ${CYAN}$PARENT_PATH${NC}"
echo ""

echo -e "${YELLOW}Scanning directory tree...${NC}"

if ! find "$PARENT_PATH" -type d -name ".specstory" > "$TEMP_FILE" 2>/dev/null; then
    echo -e "${RED}Error: Failed to search directory${NC}"
    exit 1
fi

FOLDER_COUNT=$(wc -l < "$TEMP_FILE")
log "Found $FOLDER_COUNT .specstory folder(s)"

if [ "$FOLDER_COUNT" -eq 0 ]; then
    echo -e "${YELLOW}No .specstory folders found in $PARENT_PATH${NC}"
    exit 0
fi

echo -e "${GREEN}Found ${BOLD}${FOLDER_COUNT}${NC}${GREEN} .specstory folder(s)${NC}"
echo -e "${YELLOW}Will create SEPARATE database for each project${NC}"
echo ""

# List projects
cat "$TEMP_FILE" | while IFS= read -r folder; do
    PROJECT_NAME=$(dirname "$folder" | xargs basename)
    DB_PATH="${HYBRIDRAG_DIR}/lightrag_db_${PROJECT_NAME}"
    echo -e "  ${BLUE}→${NC} ${BOLD}$PROJECT_NAME${NC}"
    echo -e "    ${CYAN}Source: $folder${NC}"
    echo -e "    ${YELLOW}Database: $DB_PATH${NC}"
    echo ""
done

if [ -t 0 ]; then
    read -p "Proceed with separate database creation? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}Operation cancelled.${NC}"
        exit 0
    fi
else
    echo -e "${BLUE}Running in non-interactive mode${NC}"
fi

echo ""
echo -e "${GREEN}Creating separate databases...${NC}"
echo ""

# =============================================================================
# Process Each Folder
# =============================================================================

COUNTER=0
SUCCESS_COUNT=0
FAILED_COUNT=0

while IFS= read -r folder; do
    COUNTER=$((COUNTER + 1))
    PROJECT_NAME=$(dirname "$folder" | xargs basename)
    DB_PATH="${HYBRIDRAG_DIR}/lightrag_db_${PROJECT_NAME}"

    echo -e "${BLUE}[$COUNTER/$FOLDER_COUNT]${NC} Processing: ${BOLD}${YELLOW}$PROJECT_NAME${NC}"
    echo -e "  Source: ${CYAN}$folder${NC}"
    echo -e "  Database: ${YELLOW}$DB_PATH${NC}"

    log "[$COUNTER/$FOLDER_COUNT] Creating database for $PROJECT_NAME"

    # Create database directory
    mkdir -p "$DB_PATH"

    # Ingest with custom database path
    # Note: --yes skips confirmation prompts, --quiet suppresses verbose output, </dev/null prevents stdin consumption
    # Use tee to show progress bar on screen while also logging, stderr goes to log only
    if LIGHTRAG_WORKING_DIR="$DB_PATH" \
       python "$HYBRIDRAG_DIR/hybridrag.py" ingest \
       --folder "$folder" \
       --db-action fresh \
       --metadata "project=$PROJECT_NAME" \
       --metadata "source_path=$folder" \
       --yes \
       --quiet \
       </dev/null 2>> "$LOG_FILE" | tee -a "$LOG_FILE"; then

        echo -e "  ${GREEN}✓ Success${NC}"
        log "  SUCCESS: Database created for $PROJECT_NAME"
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    else
        echo -e "  ${RED}✗ Failed${NC}"
        log "  FAILED: Database creation failed for $PROJECT_NAME"
        FAILED_COUNT=$((FAILED_COUNT + 1))
    fi

    echo ""

done < "$TEMP_FILE"

# =============================================================================
# Summary
# =============================================================================

echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}Separate Database Creation Complete!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo -e "${BOLD}Summary:${NC}"
echo -e "  Total projects: ${CYAN}$FOLDER_COUNT${NC}"
echo -e "  Successful: ${GREEN}$SUCCESS_COUNT${NC}"
echo -e "  Failed: ${RED}$FAILED_COUNT${NC}"
echo ""

log "Operation complete. Success: $SUCCESS_COUNT, Failed: $FAILED_COUNT"

echo -e "${BOLD}Created databases:${NC}"
ls -d "${HYBRIDRAG_DIR}"/lightrag_db_* 2>/dev/null | while read -r db; do
    DB_NAME=$(basename "$db")
    PROJECT_NAME="${DB_NAME#lightrag_db_}"
    echo -e "  ${BLUE}→${NC} ${YELLOW}$PROJECT_NAME${NC}: ${CYAN}$db${NC}"
done
echo ""

echo -e "${BOLD}Query specific database:${NC}"
echo -e "  ${YELLOW}# Project 1${NC}"
FIRST_DB=$(ls -d "${HYBRIDRAG_DIR}"/lightrag_db_* 2>/dev/null | head -n1)
if [ -n "$FIRST_DB" ]; then
    PROJECT_NAME=$(basename "$FIRST_DB" | sed 's/lightrag_db_//')
    echo -e "  ${CYAN}LIGHTRAG_WORKING_DIR=\"./lightrag_db_${PROJECT_NAME}\" python hybridrag.py interactive${NC}"
fi
echo ""

echo -e "${BOLD}Query all databases (loop):${NC}"
echo -e "  ${CYAN}for db in lightrag_db_*; do${NC}"
echo -e "    ${CYAN}LIGHTRAG_WORKING_DIR=\"\$db\" python hybridrag.py query --text \"your query\"${NC}"
echo -e "  ${CYAN}done${NC}"
echo ""

if [ $FAILED_COUNT -gt 0 ]; then
    echo -e "${YELLOW}⚠️  Some databases failed. Check: $LOG_FILE${NC}"
    exit 1
fi

log "Script completed successfully"
exit 0
