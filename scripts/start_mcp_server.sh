#!/bin/bash
# Start HybridRAG MCP Server with SSE transport
# Run this in the background for Claude Code integration

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="/tmp/hybridrag_mcp_server.log"
PID_FILE="/tmp/hybridrag_mcp_server.pid"

# Environment variables
export HYBRIDRAG_DATABASE="${PROJECT_DIR}/lightrag_db"
export HYBRIDRAG_DATABASE_NAME="specstory"
export HYBRIDRAG_MODEL="openai/gpt-4o-mini"
export HYBRIDRAG_EMBED_MODEL="azure/text-embedding-3-small"
export EMBEDDING_DIM="1536"
export MCP_TRANSPORT="sse"
export MCP_PORT="${MCP_PORT:-8766}"

# API keys from environment or defaults
export OPENAI_API_KEY="${OPENAI_API_KEY}"
export AZURE_API_KEY="${AZURE_API_KEY}"
export AZURE_API_BASE="${AZURE_API_BASE:-https://admin-m9ihapvr-eastus2.cognitiveservices.azure.com}"

cd "$PROJECT_DIR"

# Check if server is already running
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo "Server already running with PID $OLD_PID"
        echo "Use: kill $OLD_PID to stop it first"
        exit 1
    fi
fi

echo "Starting HybridRAG MCP Server (SSE transport on port $MCP_PORT)..."
echo "Log file: $LOG_FILE"
echo "PID file: $PID_FILE"

# Start server in background
nohup uv run python -m hybridrag_mcp > "$LOG_FILE" 2>&1 &
SERVER_PID=$!
echo "$SERVER_PID" > "$PID_FILE"

echo "Server started with PID $SERVER_PID"
echo ""
echo "Check status: curl http://localhost:$MCP_PORT/sse"
echo "View logs: tail -f $LOG_FILE"
echo "Stop server: kill \$(cat $PID_FILE)"
