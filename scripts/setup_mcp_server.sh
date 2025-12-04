#!/bin/bash
#
# HybridRAG MCP Server Setup Script
# ==================================
# Complete setup and verification for MCP server deployment
#
# Usage:
#   ./scripts/setup_mcp_server.sh [--test]
#
# Options:
#   --test    Run verification tests after setup
#

set -e
set -o pipefail

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RUN_TESTS=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --test)
            RUN_TESTS=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}${BLUE}  HybridRAG MCP Server Setup${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

cd "$PROJECT_ROOT"

# =============================================================================
# Step 1: Check Prerequisites
# =============================================================================

echo -e "${YELLOW}[1/6] Checking prerequisites...${NC}"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}✗ Python 3 not found${NC}"
    exit 1
fi
echo -e "${GREEN}  ✓ Python 3 found: $(python3 --version)${NC}"

# Check pip
if ! command -v pip3 &> /dev/null && ! command -v pip &> /dev/null; then
    echo -e "${RED}✗ pip not found${NC}"
    exit 1
fi
echo -e "${GREEN}  ✓ pip found${NC}"

# Check if in virtual environment
if [[ -z "$VIRTUAL_ENV" ]]; then
    echo -e "${YELLOW}  ⚠ Not in a virtual environment${NC}"
    echo -e "${YELLOW}    Recommended: source .venv/bin/activate${NC}"
else
    echo -e "${GREEN}  ✓ Virtual environment active: $VIRTUAL_ENV${NC}"
fi

echo ""

# =============================================================================
# Step 2: Install MCP Dependencies
# =============================================================================

echo -e "${YELLOW}[2/6] Installing MCP dependencies...${NC}"

if [ -f "requirements-mcp.txt" ]; then
    pip install -r requirements-mcp.txt -q
    echo -e "${GREEN}  ✓ MCP dependencies installed${NC}"
else
    echo -e "${RED}  ✗ requirements-mcp.txt not found${NC}"
    exit 1
fi

echo ""

# =============================================================================
# Step 3: Verify MCP Server File
# =============================================================================

echo -e "${YELLOW}[3/6] Verifying MCP server file...${NC}"

if [ -f "hybridrag_mcp_server.py" ]; then
    echo -e "${GREEN}  ✓ hybridrag_mcp_server.py found${NC}"

    # Make executable
    chmod +x hybridrag_mcp_server.py
    echo -e "${GREEN}  ✓ Made executable${NC}"
else
    echo -e "${RED}  ✗ hybridrag_mcp_server.py not found${NC}"
    exit 1
fi

echo ""

# =============================================================================
# Step 4: Check Environment Variables
# =============================================================================

echo -e "${YELLOW}[4/6] Checking environment variables...${NC}"

# Check for .env file
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}  ⚠ No .env file found${NC}"

    if [ -f ".env.example" ]; then
        echo -e "${YELLOW}    Creating .env from .env.example...${NC}"
        cp .env.example .env
        echo -e "${GREEN}  ✓ .env created${NC}"
        echo -e "${YELLOW}    Please edit .env and add your OPENAI_API_KEY${NC}"
    else
        echo -e "${RED}  ✗ .env.example not found${NC}"
    fi
else
    echo -e "${GREEN}  ✓ .env file exists${NC}"
fi

# Check for OPENAI_API_KEY
if [ -f ".env" ]; then
    if grep -q "OPENAI_API_KEY=sk-" .env; then
        echo -e "${GREEN}  ✓ OPENAI_API_KEY appears to be set${NC}"
    else
        echo -e "${YELLOW}  ⚠ OPENAI_API_KEY may not be set in .env${NC}"
        echo -e "${YELLOW}    Edit .env and add: OPENAI_API_KEY=sk-your-key-here${NC}"
    fi
fi

echo ""

# =============================================================================
# Step 5: Create Sample Configuration
# =============================================================================

echo -e "${YELLOW}[5/6] Creating sample configurations...${NC}"

# Create config directory
mkdir -p config

# Check if example configs exist
CONFIG_FILES=(
    "config/claude_desktop_config.example.json"
    "config/claude_desktop_config.multi_project.json"
    "config/claude_desktop_config.uv.json"
)

for config_file in "${CONFIG_FILES[@]}"; do
    if [ -f "$config_file" ]; then
        echo -e "${GREEN}  ✓ $config_file exists${NC}"
    else
        echo -e "${YELLOW}  ⚠ $config_file missing${NC}"
    fi
done

echo ""

# =============================================================================
# Step 6: Test MCP Server (Optional)
# =============================================================================

if [ "$RUN_TESTS" = true ]; then
    echo -e "${YELLOW}[6/6] Running verification tests...${NC}"

    # Check if pytest is installed
    if ! python3 -m pytest --version &> /dev/null; then
        echo -e "${YELLOW}  Installing pytest...${NC}"
        pip install pytest -q
    fi

    # Run tests
    echo -e "${BLUE}  Running test suite...${NC}"
    if python3 -m pytest tests/test_mcp_server.py -v; then
        echo -e "${GREEN}  ✓ All tests passed${NC}"
    else
        echo -e "${RED}  ✗ Some tests failed${NC}"
        echo -e "${YELLOW}  Review test output above for details${NC}"
    fi
else
    echo -e "${YELLOW}[6/6] Skipping tests (use --test to run)${NC}"
fi

echo ""

# =============================================================================
# Summary and Next Steps
# =============================================================================

echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}Setup Complete!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo -e "${BOLD}Next Steps:${NC}"
echo ""

echo -e "${BLUE}1. Configure Claude Desktop:${NC}"
echo -e "   ${CYAN}# macOS/Linux${NC}"
echo -e "   nano ~/.config/claude/claude_desktop_config.json"
echo -e ""
echo -e "   ${CYAN}# Copy example config:${NC}"
echo -e "   cat config/claude_desktop_config.example.json"
echo ""

echo -e "${BLUE}2. Create/use a LightRAG database:${NC}"
echo -e "   ${CYAN}# Ingest data${NC}"
echo -e "   python hybridrag.py ingest --folder ./data"
echo ""

echo -e "${BLUE}3. Test MCP server manually:${NC}"
echo -e "   ${CYAN}# Start server${NC}"
echo -e "   python hybridrag_mcp_server.py \\"
echo -e "     --working-dir ./lightrag_db \\"
echo -e "     --name my-project"
echo ""

echo -e "${BLUE}4. Restart Claude Desktop:${NC}"
echo -e "   ${CYAN}# Server will be available in Claude Desktop${NC}"
echo ""

echo -e "${BOLD}Documentation:${NC}"
echo -e "  • ${CYAN}docs/MCP_SERVER_INTEGRATION.md${NC} - Complete guide"
echo -e "  • ${CYAN}QUICK_START_SPECSTORY.md${NC} - Quick deployment"
echo -e "  • ${CYAN}config/${NC} - Example configurations"
echo ""

echo -e "${GREEN}Happy querying! 🚀${NC}"
echo ""
