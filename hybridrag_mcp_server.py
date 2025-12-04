#!/usr/bin/env python3
"""
HybridRAG MCP Server
====================
FastMCP 2.0 compliant server exposing LightRAG knowledge bases as MCP tools.

This generic MCP server allows any LightRAG database to be exposed to Claude Desktop
and other MCP-compatible clients for natural language querying.

🎯 CORE CAPABILITIES:
• Local Query: Focused entity/relationship discovery
• Global Query: High-level overviews and comprehensive summaries
• Hybrid Query: Balanced search combining specific details with broader context
• Database Info: Metadata about the current knowledge base

🔧 MCP TOOLS PROVIDED:
1. lightrag_local_query - Specific entity relationships and detailed information
2. lightrag_global_query - Comprehensive overviews and patterns
3. lightrag_hybrid_query - Balanced entity and relationship search (RECOMMENDED)
4. get_database_info - Database metadata and status

🚀 USAGE:
    python hybridrag_mcp_server.py --working-dir /path/to/database --name my-project

📝 CONFIGURATION:
    Environment Variables:
    - OPENAI_API_KEY: Required for LLM and embeddings
    - OPENAI_API_BASE: Optional custom endpoint
    - LIGHTRAG_LOG_LEVEL: Logging level (default: INFO)

Author: HybridRAG Team
Version: 1.0.0
Date: 2025-11-23
"""

# CRITICAL: Load environment variables BEFORE any other imports
from dotenv import load_dotenv
import os

load_dotenv(override=True)  # Force project .env to override system vars

# Ensure API key is loaded
if not os.getenv('OPENAI_API_KEY'):
    import sys
    print("ERROR: OPENAI_API_KEY not found in environment", file=sys.stderr)
    print("Set it in .env file or export OPENAI_API_KEY=your-key", file=sys.stderr)
    sys.exit(1)

import asyncio
import argparse
import sys
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass

# FastMCP 2.0 imports
from fastmcp import FastMCP
from pydantic import BaseModel, Field

# LightRAG imports
from lightrag import LightRAG, QueryParam
from lightrag.llm.openai import gpt_4o_mini_complete, openai_embed

# =============================================================================
# Configuration
# =============================================================================

@dataclass
class ServerConfig:
    """MCP Server configuration"""
    working_dir: str
    project_name: str = "default"
    log_level: str = "INFO"

    def __post_init__(self):
        # Validate working directory exists
        if not Path(self.working_dir).exists():
            raise ValueError(f"Working directory does not exist: {self.working_dir}")


# =============================================================================
# Initialize FastMCP
# =============================================================================

mcp = FastMCP("HybridRAG Knowledge Base")

# Global state
rag_instance: Optional[LightRAG] = None
server_config: Optional[ServerConfig] = None


# =============================================================================
# Initialization
# =============================================================================

def initialize_lightrag(config: ServerConfig) -> LightRAG:
    """
    Initialize LightRAG instance with given configuration

    Args:
        config: Server configuration

    Returns:
        Initialized LightRAG instance
    """
    global rag_instance, server_config

    server_config = config

    # Set up logging
    log_level = getattr(logging, config.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format='[%(asctime)s] %(levelname)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    logger = logging.getLogger(__name__)
    logger.info(f"Initializing LightRAG for project: {config.project_name}")
    logger.info(f"Working directory: {config.working_dir}")

    # Create LightRAG instance
    rag_instance = LightRAG(
        working_dir=config.working_dir,
        llm_model_func=gpt_4o_mini_complete,
        embedding_func=openai_embed
    )

    logger.info("✓ LightRAG initialized successfully")

    return rag_instance


# =============================================================================
# MCP Tool Definitions
# =============================================================================

@mcp.tool()
async def lightrag_local_query(
    query: str,
    top_k: int = 60,
    max_entity_tokens: int = 6000
) -> Dict[str, Any]:
    """
    Query knowledge base for specific entity relationships and detailed information.

    **Best for:**
    - Finding specific connections between entities
    - Detailed entity information
    - Targeted searches for particular topics
    - "What is X?" or "How does Y relate to Z?" type questions

    **Example queries:**
    - "What are the authentication patterns in this project?"
    - "How does the API endpoint connect to the database?"
    - "Show me the error handling approach for API calls"

    Args:
        query: Search query for specific entities or relationships
        top_k: Number of top entities to retrieve (default: 60, range: 10-200)
        max_entity_tokens: Maximum tokens for entity context (default: 6000, range: 1000-15000)

    Returns:
        Dictionary containing:
        - success: Whether query succeeded
        - mode: Query mode used ("local")
        - query: Original query text
        - result: Query results with entity details
        - project: Project name
        - error: Error message if failed
    """
    if not rag_instance:
        return {
            "success": False,
            "error": "LightRAG not initialized. Server may be starting up."
        }

    logger = logging.getLogger(__name__)
    logger.info(f"Local query: {query[:100]}...")

    try:
        result = await rag_instance.aquery(
            query,
            param=QueryParam(
                mode="local",
                top_k=top_k,
                max_token_for_text_unit=max_entity_tokens
            )
        )

        logger.info(f"✓ Local query completed ({len(result)} chars)")

        return {
            "success": True,
            "mode": "local",
            "query": query,
            "result": result,
            "project": server_config.project_name if server_config else "unknown",
            "metadata": {
                "top_k": top_k,
                "max_entity_tokens": max_entity_tokens
            }
        }
    except Exception as e:
        logger.error(f"✗ Local query failed: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "query": query,
            "mode": "local"
        }


@mcp.tool()
async def lightrag_global_query(
    query: str,
    top_k: int = 60,
    max_relation_tokens: int = 8000
) -> Dict[str, Any]:
    """
    Get high-level overviews and comprehensive summaries from knowledge base.

    **Best for:**
    - Broad questions requiring comprehensive answers
    - Discovering patterns across the codebase
    - Understanding overall architecture or structure
    - "What are all..." or "Give me an overview of..." type questions

    **Example queries:**
    - "What are all the API endpoints in this project?"
    - "Give me an overview of the testing strategy"
    - "What patterns appear throughout the authentication system?"

    Args:
        query: Search query for high-level overviews
        top_k: Number of top relationships to retrieve (default: 60, range: 10-200)
        max_relation_tokens: Maximum tokens for relationship context (default: 8000, range: 2000-20000)

    Returns:
        Dictionary containing:
        - success: Whether query succeeded
        - mode: Query mode used ("global")
        - query: Original query text
        - result: Query results with broad patterns
        - project: Project name
        - error: Error message if failed
    """
    if not rag_instance:
        return {
            "success": False,
            "error": "LightRAG not initialized. Server may be starting up."
        }

    logger = logging.getLogger(__name__)
    logger.info(f"Global query: {query[:100]}...")

    try:
        result = await rag_instance.aquery(
            query,
            param=QueryParam(
                mode="global",
                top_k=top_k,
                max_token_for_global_context=max_relation_tokens
            )
        )

        logger.info(f"✓ Global query completed ({len(result)} chars)")

        return {
            "success": True,
            "mode": "global",
            "query": query,
            "result": result,
            "project": server_config.project_name if server_config else "unknown",
            "metadata": {
                "top_k": top_k,
                "max_relation_tokens": max_relation_tokens
            }
        }
    except Exception as e:
        logger.error(f"✗ Global query failed: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "query": query,
            "mode": "global"
        }


@mcp.tool()
async def lightrag_hybrid_query(
    query: str,
    top_k: int = 60,
    max_entity_tokens: int = 6000,
    max_relation_tokens: int = 8000
) -> Dict[str, Any]:
    """
    Balanced search combining specific details with broader context.

    **🌟 RECOMMENDED MODE for most queries**

    **Best for:**
    - General questions requiring both detail and context
    - Exploratory queries
    - Complex questions needing multiple perspectives
    - Most day-to-day use cases
    - When you're unsure which mode to use

    **Example queries:**
    - "How is user authentication implemented and what are the security patterns?"
    - "Explain the database migration process and related tooling"
    - "What's the relationship between the API layer and business logic?"

    **Why hybrid?**
    This mode combines:
    - LOCAL mode: Specific entity details and relationships
    - GLOBAL mode: Broader patterns and contextual information

    Result: Best of both worlds - detailed AND comprehensive answers.

    Args:
        query: Search query combining specific and broad context
        top_k: Number of top items to retrieve (default: 60, range: 10-200)
        max_entity_tokens: Maximum tokens for entity details (default: 6000, range: 1000-15000)
        max_relation_tokens: Maximum tokens for relationships (default: 8000, range: 2000-20000)

    Returns:
        Dictionary containing:
        - success: Whether query succeeded
        - mode: Query mode used ("hybrid")
        - query: Original query text
        - result: Query results with balanced information
        - project: Project name
        - error: Error message if failed
    """
    if not rag_instance:
        return {
            "success": False,
            "error": "LightRAG not initialized. Server may be starting up."
        }

    logger = logging.getLogger(__name__)
    logger.info(f"Hybrid query: {query[:100]}...")

    try:
        result = await rag_instance.aquery(
            query,
            param=QueryParam(
                mode="hybrid",
                top_k=top_k,
                max_token_for_text_unit=max_entity_tokens,
                max_token_for_global_context=max_relation_tokens
            )
        )

        logger.info(f"✓ Hybrid query completed ({len(result)} chars)")

        return {
            "success": True,
            "mode": "hybrid",
            "query": query,
            "result": result,
            "project": server_config.project_name if server_config else "unknown",
            "metadata": {
                "top_k": top_k,
                "max_entity_tokens": max_entity_tokens,
                "max_relation_tokens": max_relation_tokens
            }
        }
    except Exception as e:
        logger.error(f"✗ Hybrid query failed: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "query": query,
            "mode": "hybrid"
        }


@mcp.tool()
async def get_database_info() -> Dict[str, Any]:
    """
    Get information about the current LightRAG knowledge base.

    **Provides:**
    - Working directory location
    - Project name
    - Database initialization status
    - Metadata (if available)
    - File counts and storage info

    **Use this to:**
    - Verify which database you're querying
    - Check if database is properly initialized
    - Get project metadata
    - Debug connection issues

    Returns:
        Dictionary containing:
        - success: Whether info retrieval succeeded
        - working_dir: Path to database directory
        - project_name: Name of this knowledge base
        - initialized: Whether LightRAG is initialized
        - metadata: Additional database metadata (if available)
        - error: Error message if failed
    """
    if not rag_instance:
        return {
            "success": False,
            "error": "LightRAG not initialized. Server may be starting up.",
            "initialized": False
        }

    logger = logging.getLogger(__name__)
    logger.info("Retrieving database info...")

    try:
        working_dir = Path(rag_instance.working_dir)
        metadata_file = working_dir / "metadata.json"

        info = {
            "success": True,
            "initialized": True,
            "working_dir": str(working_dir),
            "project_name": server_config.project_name if server_config else "unknown",
            "metadata_exists": metadata_file.exists()
        }

        # Count files in database
        if working_dir.exists():
            try:
                file_count = sum(1 for _ in working_dir.rglob('*') if _.is_file())
                info["file_count"] = file_count
            except Exception as e:
                logger.warning(f"Could not count files: {e}")

        # Load metadata if available
        if metadata_file.exists():
            try:
                import json
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                    info["metadata"] = metadata
            except Exception as e:
                logger.warning(f"Could not read metadata: {e}")
                info["metadata_error"] = str(e)

        logger.info(f"✓ Database info retrieved for {info['project_name']}")

        return info

    except Exception as e:
        logger.error(f"✗ Failed to get database info: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "initialized": True  # RAG is initialized even if metadata retrieval failed
        }


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """Main entry point for HybridRAG MCP Server"""

    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="HybridRAG MCP Server - Expose LightRAG knowledge bases via MCP protocol",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start server for a project
  python hybridrag_mcp_server.py --working-dir ./databases/my_project --name my-project

  # Use with custom log level
  python hybridrag_mcp_server.py --working-dir ./db --name proj --log-level DEBUG

  # Multiple servers (in separate terminals or systemd services)
  python hybridrag_mcp_server.py --working-dir ./db1 --name project1
  python hybridrag_mcp_server.py --working-dir ./db2 --name project2

Configuration:
  Set OPENAI_API_KEY in environment or .env file
  Optional: OPENAI_API_BASE for custom endpoint
        """
    )

    parser.add_argument(
        "--working-dir",
        type=str,
        required=True,
        help="Path to LightRAG working directory (database location)"
    )

    parser.add_argument(
        "--name",
        type=str,
        default="default",
        help="Project name for this knowledge base (default: 'default')"
    )

    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)"
    )

    args = parser.parse_args()

    # Validate working directory
    working_dir = Path(args.working_dir)
    if not working_dir.exists():
        print(f"✗ Error: Working directory does not exist: {working_dir}", file=sys.stderr)
        print(f"", file=sys.stderr)
        print(f"Did you mean to create it first?", file=sys.stderr)
        print(f"  mkdir -p {working_dir}", file=sys.stderr)
        print(f"", file=sys.stderr)
        print(f"Or ingest data:", file=sys.stderr)
        print(f"  python hybridrag.py ingest --folder /path/to/data", file=sys.stderr)
        sys.exit(1)

    # Create configuration
    try:
        config = ServerConfig(
            working_dir=str(working_dir),
            project_name=args.name,
            log_level=args.log_level
        )
    except ValueError as e:
        print(f"✗ Configuration error: {e}", file=sys.stderr)
        sys.exit(1)

    # Print startup banner
    print(f"", file=sys.stderr)
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", file=sys.stderr)
    print(f"  HybridRAG MCP Server v1.0.0", file=sys.stderr)
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", file=sys.stderr)
    print(f"", file=sys.stderr)
    print(f"  Project:    {config.project_name}", file=sys.stderr)
    print(f"  Database:   {config.working_dir}", file=sys.stderr)
    print(f"  Log Level:  {config.log_level}", file=sys.stderr)
    print(f"", file=sys.stderr)

    # Initialize LightRAG
    try:
        print(f"Initializing LightRAG...", file=sys.stderr)
        initialize_lightrag(config)
        print(f"✓ LightRAG initialized successfully", file=sys.stderr)
        print(f"", file=sys.stderr)
    except Exception as e:
        print(f"✗ Failed to initialize LightRAG: {e}", file=sys.stderr)
        print(f"", file=sys.stderr)
        print(f"Troubleshooting:", file=sys.stderr)
        print(f"  1. Check OPENAI_API_KEY is set", file=sys.stderr)
        print(f"  2. Verify working directory exists and has data", file=sys.stderr)
        print(f"  3. Check permissions on working directory", file=sys.stderr)
        sys.exit(1)

    # Print available tools
    print(f"Available MCP Tools:", file=sys.stderr)
    print(f"  • lightrag_local_query   - Specific entity relationships", file=sys.stderr)
    print(f"  • lightrag_global_query  - High-level overviews", file=sys.stderr)
    print(f"  • lightrag_hybrid_query  - Balanced search (RECOMMENDED)", file=sys.stderr)
    print(f"  • get_database_info      - Database metadata", file=sys.stderr)
    print(f"", file=sys.stderr)
    print(f"✓ MCP server ready", file=sys.stderr)
    print(f"", file=sys.stderr)

    # Run MCP server (this blocks until server terminates)
    try:
        mcp.run()
    except KeyboardInterrupt:
        print(f"\n\n✓ Server stopped by user", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(f"\n\n✗ Server error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
