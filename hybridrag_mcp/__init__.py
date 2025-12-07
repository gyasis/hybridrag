"""
HybridRAG MCP Server Module
===========================
Model Context Protocol server for Claude Desktop integration.

Provides LightRAG query tools that can be used by Claude Desktop.
Supports multiple instances via HYBRIDRAG_DATABASE environment variable.

Usage:
    python -m hybridrag_mcp.server

Or via uv:
    uv run python -m hybridrag_mcp.server

Environment Variables:
    HYBRIDRAG_DATABASE: Path to the LightRAG database directory (required)
    HYBRIDRAG_MODEL: LLM model override (optional, e.g., "azure/gpt-4o")
    HYBRIDRAG_EMBED_MODEL: Embedding model override (optional)
"""

__version__ = "1.0.0"
__all__ = ["server"]
