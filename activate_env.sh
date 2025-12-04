#!/bin/bash
# Environment activation script for HybridRAG
# This script ensures you're using the correct UV environment

set -e

echo "🔧 HybridRAG Environment Setup"
echo "=============================="

# Check if we're in the right directory
if [ ! -f "pyproject.toml" ]; then
    echo "❌ Error: Please run this script from the hybridrag project directory"
    exit 1
fi

# Check if UV is available
if ! command -v uv &> /dev/null; then
    echo "❌ Error: UV is not installed. Please install UV first:"
    echo "   curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "🏗️  Virtual environment not found. Creating one..."
    uv sync --no-install-project
fi

echo "✅ Environment ready!"
echo ""
echo "To use the environment, run commands with:"
echo "   uv run python script_name.py"
echo ""
echo "Or activate the shell with:"
echo "   source .venv/bin/activate"
echo ""
echo "Available scripts:"
echo "   📄 deeplake_to_lightrag.py - Convert DeepLake data to LightRAG"
echo "   🔍 lightrag_query_demo.py - Interactive LightRAG query interface"
echo ""
echo "Environment validation:"

# Validate environment
echo "🔍 Validating environment..."
uv run python -c "
import sys
print(f'Python: {sys.version}')
print(f'Python executable: {sys.executable}')

# Test key imports
try:
    import lightrag, deeplake, openai
    print('✅ Core dependencies: OK')
except ImportError as e:
    print(f'❌ Import error: {e}')

# Check for .env file
import os
if os.path.exists('.env'):
    print('✅ .env file: Found')
else:
    print('⚠️  .env file: Not found (copy .env.example to .env)')
"

echo ""
echo "🎉 Environment setup complete!"