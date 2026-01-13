#!/bin/bash
#
# HybridRAG Generic Recursive Ingestion Script
# =============================================
# Recursively finds and ingests folders or files matching patterns
# Supports: folder names, file types, file names, wildcards
#
# Usage:
#   ./scripts/ingest_recursive.sh <parent_path> <db_action> [options]
#
# Options:
#   --folders "pattern1,pattern2"    Find folders matching these names
#   --files "*.md,*.txt"             Find files matching these extensions
#   --names "README.md,CHANGELOG"    Find specific file names
#   --exclude "node_modules,.git"    Exclude these directories
#   --model "azure/gpt-4o"           Override LLM model
#   --tag "mytag"                    Add custom metadata tag
#
# Examples:
#   # Find all .specstory and docs folders
#   ./scripts/ingest_recursive.sh /home/user/dev fresh --folders ".specstory,docs"
#
#   # Find all markdown files
#   ./scripts/ingest_recursive.sh /home/user/dev fresh --files "*.md"
#
#   # Find specific files
#   ./scripts/ingest_recursive.sh /home/user/dev add --names "README.md,CHANGELOG.md"
#
#   # Combined: folders + file types
#   ./scripts/ingest_recursive.sh /home/user/dev fresh \
#       --folders ".specstory,.memory" \
#       --files "*.md" \
#       --exclude "node_modules,.git,vendor"
#

set -e
set -o pipefail

# =============================================================================
# Colors (define first for use everywhere)
# =============================================================================
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# =============================================================================
# Helper Functions (define before use)
# =============================================================================

print_header() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}${BLUE}  HybridRAG Generic Recursive Ingestion${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

print_usage() {
    echo -e "${YELLOW}Usage:${NC}"
    echo -e "  $0 <parent_path> <db_action> [options]"
    echo ""
    echo -e "${YELLOW}Arguments:${NC}"
    echo -e "  parent_path  - Root directory to search recursively"
    echo -e "  db_action    - 'fresh' (new DB) or 'add' (append)"
    echo ""
    echo -e "${YELLOW}Options:${NC}"
    echo -e "  --folders \"p1,p2\"    Folder names to find (e.g., \".specstory,docs\")"
    echo -e "  --files \"*.ext\"      File patterns (e.g., \"*.md,*.txt\")"
    echo -e "  --names \"file.md\"    Specific file names (e.g., \"README.md\")"
    echo -e "  --exclude \"dir1\"     Directories to skip (default: node_modules,.git,...)"
    echo -e "  --model \"model\"      LLM model override"
    echo -e "  --tag \"tag\"          Custom metadata tag"
    echo ""
    echo -e "${YELLOW}Examples:${NC}"
    echo -e "  # Find .specstory and docs folders"
    echo -e "  $0 /home/user/dev fresh --folders \".specstory,docs\""
    echo ""
    echo -e "  # Find all markdown files"
    echo -e "  $0 /home/user/dev fresh --files \"*.md\""
    echo ""
    echo -e "  # Combined search"
    echo -e "  $0 /home/user/dev add --folders \".memory\" --files \"*.md\" --tag \"notes\""
    echo ""
    echo -e "${YELLOW}User Stories:${NC}"
    echo -e "  # Add two folders from different locations:"
    echo -e "  $0 /home/user/dev fresh --folders \".specstory\""
    echo -e "  $0 /home/user/work add --folders \".specstory\"   # 'add' preserves existing"
    echo ""
    echo -e "  # Add another folder later:"
    echo -e "  $0 /mnt/external/project add --folders \"docs\" --tag \"external\""
    echo ""
}

# =============================================================================
# Handle --help before anything else
# =============================================================================

if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    print_header
    print_usage
    exit 0
fi

# =============================================================================
# Configuration
# =============================================================================

PARENT_PATH="${1:-}"
DB_ACTION="${2:-add}"
shift 2 2>/dev/null || true

# Defaults
FOLDER_PATTERNS=""
FILE_PATTERNS=""
NAME_PATTERNS=""
EXCLUDE_DIRS="node_modules,.git,.venv,__pycache__,.cache,vendor,dist,build"
MODEL_OVERRIDE=""
CUSTOM_TAG=""

HYBRIDRAG_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TEMP_FILE="/tmp/recursive_ingest_$$.txt"
LOG_FILE="${HYBRIDRAG_DIR}/logs/recursive_$(date +%Y%m%d_%H%M%S).log"

# =============================================================================
# Parse Arguments
# =============================================================================

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            print_header
            print_usage
            exit 0
            ;;
        --folders)
            FOLDER_PATTERNS="$2"
            shift 2
            ;;
        --files)
            FILE_PATTERNS="$2"
            shift 2
            ;;
        --names)
            NAME_PATTERNS="$2"
            shift 2
            ;;
        --exclude)
            EXCLUDE_DIRS="$2"
            shift 2
            ;;
        --model)
            MODEL_OVERRIDE="$2"
            shift 2
            ;;
        --tag)
            CUSTOM_TAG="$2"
            shift 2
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            print_usage
            exit 1
            ;;
    esac
done

# =============================================================================
# More Helper Functions
# =============================================================================

log() {
    local message="$1"
    mkdir -p "$(dirname "$LOG_FILE")"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $message" | tee -a "$LOG_FILE"
}

cleanup() {
    rm -f "$TEMP_FILE"
}

trap cleanup EXIT

# Build exclude arguments for find command
build_exclude_args() {
    local excludes=""
    IFS=',' read -ra EXCL <<< "$EXCLUDE_DIRS"
    for dir in "${EXCL[@]}"; do
        dir=$(echo "$dir" | xargs)  # trim whitespace
        if [ -n "$dir" ]; then
            excludes="$excludes -path '*/$dir' -prune -o -path '*/$dir/*' -prune -o"
        fi
    done
    echo "$excludes"
}

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

if [[ ! "$DB_ACTION" =~ ^(fresh|add)$ ]]; then
    echo -e "${RED}Error: db_action must be 'fresh' or 'add'${NC}"
    print_usage
    exit 1
fi

# Must have at least one search pattern
if [ -z "$FOLDER_PATTERNS" ] && [ -z "$FILE_PATTERNS" ] && [ -z "$NAME_PATTERNS" ]; then
    echo -e "${RED}Error: Must specify at least one of --folders, --files, or --names${NC}"
    echo ""
    print_usage
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

log "Starting recursive ingestion"
log "Parent path: $PARENT_PATH"
log "Database action: $DB_ACTION"
[ -n "$FOLDER_PATTERNS" ] && log "Folder patterns: $FOLDER_PATTERNS"
[ -n "$FILE_PATTERNS" ] && log "File patterns: $FILE_PATTERNS"
[ -n "$NAME_PATTERNS" ] && log "Name patterns: $NAME_PATTERNS"
[ -n "$EXCLUDE_DIRS" ] && log "Excluding: $EXCLUDE_DIRS"
[ -n "$MODEL_OVERRIDE" ] && log "Model override: $MODEL_OVERRIDE"
[ -n "$CUSTOM_TAG" ] && log "Custom tag: $CUSTOM_TAG"

echo -e "${GREEN}Search Configuration:${NC}"
echo -e "  Root path: ${CYAN}$PARENT_PATH${NC}"
[ -n "$FOLDER_PATTERNS" ] && echo -e "  Folders:   ${CYAN}$FOLDER_PATTERNS${NC}"
[ -n "$FILE_PATTERNS" ] && echo -e "  Files:     ${CYAN}$FILE_PATTERNS${NC}"
[ -n "$NAME_PATTERNS" ] && echo -e "  Names:     ${CYAN}$NAME_PATTERNS${NC}"
echo -e "  Excluding: ${YELLOW}$EXCLUDE_DIRS${NC}"
echo ""

# Build exclusion args
EXCLUDE_ARGS=$(build_exclude_args)

# Clear temp file
> "$TEMP_FILE"

echo -e "${YELLOW}Scanning directory tree...${NC}"

# =============================================================================
# Find Folders
# =============================================================================

if [ -n "$FOLDER_PATTERNS" ]; then
    echo -e "${BLUE}Searching for folders...${NC}"
    IFS=',' read -ra PATTERNS <<< "$FOLDER_PATTERNS"
    for pattern in "${PATTERNS[@]}"; do
        pattern=$(echo "$pattern" | xargs)  # trim whitespace
        if [ -n "$pattern" ]; then
            log "Searching for folders: $pattern"
            # Find directories matching pattern, excluding specified dirs
            eval "find '$PARENT_PATH' $EXCLUDE_ARGS -type d -name '$pattern' -print" 2>/dev/null | while read -r folder; do
                echo "FOLDER:$folder" >> "$TEMP_FILE"
            done
        fi
    done
fi

# =============================================================================
# Find Files by Extension
# =============================================================================

if [ -n "$FILE_PATTERNS" ]; then
    echo -e "${BLUE}Searching for file types...${NC}"
    IFS=',' read -ra PATTERNS <<< "$FILE_PATTERNS"
    for pattern in "${PATTERNS[@]}"; do
        pattern=$(echo "$pattern" | xargs)
        if [ -n "$pattern" ]; then
            log "Searching for files: $pattern"
            eval "find '$PARENT_PATH' $EXCLUDE_ARGS -type f -name '$pattern' -print" 2>/dev/null | while read -r file; do
                echo "FILE:$file" >> "$TEMP_FILE"
            done
        fi
    done
fi

# =============================================================================
# Find Specific File Names
# =============================================================================

if [ -n "$NAME_PATTERNS" ]; then
    echo -e "${BLUE}Searching for specific files...${NC}"
    IFS=',' read -ra PATTERNS <<< "$NAME_PATTERNS"
    for pattern in "${PATTERNS[@]}"; do
        pattern=$(echo "$pattern" | xargs)
        if [ -n "$pattern" ]; then
            log "Searching for file name: $pattern"
            eval "find '$PARENT_PATH' $EXCLUDE_ARGS -type f -name '$pattern' -print" 2>/dev/null | while read -r file; do
                echo "FILE:$file" >> "$TEMP_FILE"
            done
        fi
    done
fi

# =============================================================================
# Count Results
# =============================================================================

TOTAL_COUNT=$(wc -l < "$TEMP_FILE" | xargs)
FOLDER_COUNT=$(grep -c "^FOLDER:" "$TEMP_FILE" 2>/dev/null || echo 0)
FILE_COUNT=$(grep -c "^FILE:" "$TEMP_FILE" 2>/dev/null || echo 0)

log "Found: $FOLDER_COUNT folders, $FILE_COUNT files"

if [ "$TOTAL_COUNT" -eq 0 ]; then
    echo -e "${YELLOW}No matches found!${NC}"
    echo ""
    echo -e "${YELLOW}Tips:${NC}"
    echo -e "  - Check your patterns (use quotes for wildcards)"
    echo -e "  - Verify the parent path contains the expected content"
    echo -e "  - Review excluded directories"
    exit 0
fi

echo ""
echo -e "${GREEN}Found ${BOLD}$TOTAL_COUNT${NC}${GREEN} matches:${NC}"
echo -e "  Folders: ${CYAN}$FOLDER_COUNT${NC}"
echo -e "  Files:   ${CYAN}$FILE_COUNT${NC}"
echo ""

# Display found items (first 20)
echo -e "${YELLOW}Preview (first 20 items):${NC}"
head -20 "$TEMP_FILE" | while IFS= read -r line; do
    TYPE="${line%%:*}"
    PATH_VAL="${line#*:}"
    if [ "$TYPE" = "FOLDER" ]; then
        # Extract meaningful project name (handle .specstory/history pattern)
        FOLDER_NAME=$(basename "$PATH_VAL")
        PARENT=$(dirname "$PATH_VAL")
        PARENT_NAME=$(basename "$PARENT")
        if [ "$PARENT_NAME" = ".specstory" ]; then
            # Go up one more level for project name
            PROJECT=$(basename "$(dirname "$PARENT")")
        else
            PROJECT="$PARENT_NAME"
        fi
        echo -e "  ${BLUE}[DIR]${NC}  ${BOLD}$PROJECT${NC}/${YELLOW}$FOLDER_NAME${NC}"
    else
        FILENAME=$(basename "$PATH_VAL")
        PARENT_DIR=$(basename "$(dirname "$PATH_VAL")")
        echo -e "  ${GREEN}[FILE]${NC} ${CYAN}$PARENT_DIR/${NC}${BOLD}$FILENAME${NC}"
    fi
done

if [ "$TOTAL_COUNT" -gt 20 ]; then
    echo -e "  ${YELLOW}... and $((TOTAL_COUNT - 20)) more${NC}"
fi

echo ""
echo -e "${YELLOW}Database action: ${BOLD}${DB_ACTION}${NC}"

if [ "$DB_ACTION" == "fresh" ]; then
    echo -e "${YELLOW}⚠️  Warning: This will create a NEW database${NC}"
else
    echo -e "${GREEN}✓ Will ADD to existing database${NC}"
fi

echo ""

# Confirm
if [ -t 0 ]; then
    read -p "Proceed with ingestion? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}Cancelled.${NC}"
        exit 0
    fi
else
    echo -e "${BLUE}Non-interactive mode, proceeding...${NC}"
fi

echo ""
echo -e "${GREEN}Starting ingestion...${NC}"
echo ""

# =============================================================================
# Process Items
# =============================================================================

COUNTER=0
SUCCESS_COUNT=0
FAILED_COUNT=0
CURRENT_DB_ACTION="$DB_ACTION"

# Process folders first (if any)
if [ "$FOLDER_COUNT" -gt 0 ]; then
    grep "^FOLDER:" "$TEMP_FILE" | while IFS= read -r line; do
        FOLDER="${line#FOLDER:}"
        COUNTER=$((COUNTER + 1))
        FOLDER_NAME=$(basename "$FOLDER")
        PARENT=$(dirname "$FOLDER")
        PARENT_NAME=$(basename "$PARENT")
        # Handle .specstory/history pattern - get actual project name
        if [ "$PARENT_NAME" = ".specstory" ]; then
            PROJECT_NAME=$(basename "$(dirname "$PARENT")")
        else
            PROJECT_NAME="$PARENT_NAME"
        fi

        echo -e "${BLUE}[$COUNTER]${NC} ${BOLD}$PROJECT_NAME${NC}/${YELLOW}$FOLDER_NAME${NC}"
        log "Processing folder: $FOLDER"

        # Build metadata
        METADATA_ARGS="--metadata project=$PROJECT_NAME --metadata source_path=$FOLDER --metadata type=folder --metadata folder_name=$FOLDER_NAME"
        [ -n "$CUSTOM_TAG" ] && METADATA_ARGS="$METADATA_ARGS --metadata tag=$CUSTOM_TAG"

        MODEL_FLAG=""
        [ -n "$MODEL_OVERRIDE" ] && MODEL_FLAG="--model $MODEL_OVERRIDE"

        if python "$HYBRIDRAG_DIR/hybridrag.py" $MODEL_FLAG ingest \
            --folder "$FOLDER" \
            --db-action "$CURRENT_DB_ACTION" \
            $METADATA_ARGS \
            --yes \
            </dev/null 2>&1 | tee -a "$LOG_FILE"; then
            echo -e "  ${GREEN}✓ Success${NC}"
            SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
        else
            echo -e "  ${RED}✗ Failed${NC}"
            FAILED_COUNT=$((FAILED_COUNT + 1))
        fi

        # Switch to 'add' after first item
        if [ "$CURRENT_DB_ACTION" == "fresh" ]; then
            CURRENT_DB_ACTION="add"
        fi
    done
fi

# Process individual files (if any)
if [ "$FILE_COUNT" -gt 0 ]; then
    echo ""
    echo -e "${BLUE}Processing individual files...${NC}"

    grep "^FILE:" "$TEMP_FILE" | while IFS= read -r line; do
        FILE="${line#FILE:}"
        PARENT_DIR=$(dirname "$FILE")
        FILENAME=$(basename "$FILE")
        PROJECT_NAME=$(basename "$PARENT_DIR")

        echo -e "${BLUE}→${NC} ${CYAN}$PROJECT_NAME/${NC}${BOLD}$FILENAME${NC}"
        log "Processing file: $FILE"

        # Build metadata
        METADATA_ARGS="--metadata project=$PROJECT_NAME --metadata source_path=$FILE --metadata type=file --metadata filename=$FILENAME"
        [ -n "$CUSTOM_TAG" ] && METADATA_ARGS="$METADATA_ARGS --metadata tag=$CUSTOM_TAG"

        MODEL_FLAG=""
        [ -n "$MODEL_OVERRIDE" ] && MODEL_FLAG="--model $MODEL_OVERRIDE"

        # Ingest single file (--folder works for files too)
        if python "$HYBRIDRAG_DIR/hybridrag.py" $MODEL_FLAG ingest \
            --folder "$FILE" \
            --db-action "$CURRENT_DB_ACTION" \
            $METADATA_ARGS \
            --yes \
            </dev/null 2>&1 | tee -a "$LOG_FILE"; then
            echo -e "  ${GREEN}✓${NC}"
        else
            echo -e "  ${RED}✗${NC}"
        fi

        if [ "$CURRENT_DB_ACTION" == "fresh" ]; then
            CURRENT_DB_ACTION="add"
        fi
    done
fi

# =============================================================================
# Summary
# =============================================================================

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}Ingestion Complete!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${BOLD}Summary:${NC}"
echo -e "  Total items:  ${CYAN}$TOTAL_COUNT${NC}"
echo -e "  Folders:      ${CYAN}$FOLDER_COUNT${NC}"
echo -e "  Files:        ${CYAN}$FILE_COUNT${NC}"
echo ""
echo -e "${BOLD}Log file:${NC} ${CYAN}$LOG_FILE${NC}"
echo ""
echo -e "${BOLD}Next steps:${NC}"
echo -e "  ${BLUE}1.${NC} Check database: ${YELLOW}python hybridrag.py check-db${NC}"
echo -e "  ${BLUE}2.${NC} Start querying: ${YELLOW}python hybridrag.py interactive${NC}"
echo ""

log "Ingestion complete"
exit 0
