#!/bin/bash
#
# HybridRAG Folder Watcher (Generic)
# ==================================
# Watches any folder and ingests into a specified database location
#
# Usage:
#   ./scripts/watch_folder.sh <source_folder> <database_path> [interval]
#
# Examples:
#   # Watch Documents folder, store DB on Desktop
#   ./scripts/watch_folder.sh ~/Documents/my_docs ~/Desktop/my_lightrag_db
#
#   # Watch with 2-minute interval
#   ./scripts/watch_folder.sh ~/Documents/my_docs ~/Desktop/my_lightrag_db 120
#
#   # Run in background
#   nohup ./scripts/watch_folder.sh ~/Documents ~/Desktop/docs_db 300 > watch.log 2>&1 &

set -e

# =============================================================================
# Configuration
# =============================================================================

SOURCE_FOLDER="${1:-}"
DATABASE_PATH="${2:-}"
CHECK_INTERVAL="${3:-300}"  # 5 minutes default
HYBRIDRAG_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# =============================================================================
# Validation
# =============================================================================

if [ -z "$SOURCE_FOLDER" ] || [ -z "$DATABASE_PATH" ]; then
    echo -e "${RED}Error: Missing required arguments${NC}"
    echo ""
    echo -e "${YELLOW}Usage:${NC}"
    echo -e "  $0 <source_folder> <database_path> [interval_seconds]"
    echo ""
    echo -e "${YELLOW}Examples:${NC}"
    echo -e "  $0 ~/Documents/my_docs ~/Desktop/my_lightrag_db"
    echo -e "  $0 ~/Documents ~/Desktop/docs_db 120"
    exit 1
fi

# Expand paths
SOURCE_FOLDER=$(eval echo "$SOURCE_FOLDER")
DATABASE_PATH=$(eval echo "$DATABASE_PATH")

if [ ! -d "$SOURCE_FOLDER" ]; then
    echo -e "${RED}Error: Source folder does not exist: $SOURCE_FOLDER${NC}"
    exit 1
fi

# Create database directory if needed
mkdir -p "$DATABASE_PATH"

# =============================================================================
# Main
# =============================================================================

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}${BLUE}  HybridRAG Folder Watcher${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  ${GREEN}Source:${NC}   $SOURCE_FOLDER"
echo -e "  ${GREEN}Database:${NC} $DATABASE_PATH"
echo -e "  ${GREEN}Interval:${NC} ${CHECK_INTERVAL}s ($(($CHECK_INTERVAL / 60)) min)"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop${NC}"
echo ""

# Track file hashes to detect changes
HASH_FILE="/tmp/hybridrag_watch_$(echo "$SOURCE_FOLDER" | md5sum | cut -d' ' -f1).hashes"

first_run=true

while true; do
    # Calculate current file hashes
    current_hashes=$(find "$SOURCE_FOLDER" -type f \( -name "*.txt" -o -name "*.md" -o -name "*.pdf" -o -name "*.json" -o -name "*.yaml" -o -name "*.yml" -o -name "*.py" -o -name "*.js" -o -name "*.html" -o -name "*.csv" \) -exec md5sum {} \; 2>/dev/null | sort)

    # Check if hashes changed or first run
    if [ "$first_run" = true ] || [ "$current_hashes" != "$(cat "$HASH_FILE" 2>/dev/null)" ]; then
        if [ "$first_run" = true ]; then
            echo -e "[$(date '+%H:%M:%S')] ${GREEN}Initial ingestion...${NC}"
            DB_ACTION="fresh"
        else
            echo -e "[$(date '+%H:%M:%S')] ${YELLOW}Changes detected, ingesting...${NC}"
            DB_ACTION="add"
        fi

        # Run ingestion
        if python "$HYBRIDRAG_DIR/hybridrag.py" \
            --working-dir "$DATABASE_PATH" \
            ingest --folder "$SOURCE_FOLDER" \
            --db-action "$DB_ACTION" \
            --yes; then

            echo -e "[$(date '+%H:%M:%S')] ${GREEN}✓ Ingestion complete${NC}"
            echo "$current_hashes" > "$HASH_FILE"
        else
            echo -e "[$(date '+%H:%M:%S')] ${RED}✗ Ingestion failed${NC}"
        fi

        first_run=false
    else
        echo -e "[$(date '+%H:%M:%S')] No changes detected"
    fi

    echo -e "${CYAN}Next check in ${CHECK_INTERVAL}s...${NC}"
    sleep "$CHECK_INTERVAL"
done
