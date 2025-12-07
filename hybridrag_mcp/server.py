#!/usr/bin/env python3
"""
HybridRAG MCP Server
====================
Model Context Protocol server for Claude Desktop integration.

Provides LightRAG query tools with multi-mode support (local, global, hybrid, naive, mix).
Supports multiple instances via HYBRIDRAG_DATABASE environment variable.

Usage:
    # Direct execution
    python -m hybridrag_mcp.server

    # Via uv in Claude Desktop config
    uv --directory /path/to/hybridrag run python -m hybridrag_mcp.server

Environment Variables:
    HYBRIDRAG_DATABASE: Path to the LightRAG database directory (required)
    HYBRIDRAG_MODEL: LLM model override (optional)
    HYBRIDRAG_EMBED_MODEL: Embedding model override (optional)
"""

import os
import sys
import asyncio
import logging
from pathlib import Path
from typing import Literal, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastmcp import FastMCP
from src.lightrag_core import HybridLightRAGCore
from config.config import HybridRAGConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Get database path from environment
DATABASE_PATH = os.environ.get("HYBRIDRAG_DATABASE")
MODEL_OVERRIDE = os.environ.get("HYBRIDRAG_MODEL")
EMBED_MODEL_OVERRIDE = os.environ.get("HYBRIDRAG_EMBED_MODEL")

# Validate database path
if not DATABASE_PATH:
    logger.error("HYBRIDRAG_DATABASE environment variable not set")
    print("Error: HYBRIDRAG_DATABASE environment variable is required", file=sys.stderr)
    print("Set it to the path of your LightRAG database directory", file=sys.stderr)
    sys.exit(1)

DATABASE_PATH = Path(DATABASE_PATH).expanduser().resolve()
if not DATABASE_PATH.exists():
    logger.warning(f"Database path does not exist: {DATABASE_PATH}")
    print(f"Warning: Database path does not exist: {DATABASE_PATH}", file=sys.stderr)
    print("The database will be created on first ingestion", file=sys.stderr)

# Initialize MCP server
mcp = FastMCP(
    name="HybridRAG MCP Server"
)

# Global LightRAG core instance (lazy initialized)
_lightrag_core: Optional[HybridLightRAGCore] = None


async def get_lightrag_core() -> HybridLightRAGCore:
    """Get or initialize the LightRAG core instance."""
    global _lightrag_core

    if _lightrag_core is None:
        logger.info(f"Initializing HybridLightRAGCore with database: {DATABASE_PATH}")

        # Create config
        config = HybridRAGConfig()
        config.lightrag.working_dir = str(DATABASE_PATH)

        # Apply model overrides if set
        if MODEL_OVERRIDE:
            config.lightrag.model_name = MODEL_OVERRIDE
            logger.info(f"Using model override: {MODEL_OVERRIDE}")

        if EMBED_MODEL_OVERRIDE:
            config.lightrag.embedding_model = EMBED_MODEL_OVERRIDE
            logger.info(f"Using embedding model override: {EMBED_MODEL_OVERRIDE}")

        # Initialize core
        _lightrag_core = HybridLightRAGCore(config)
        await _lightrag_core._ensure_initialized()

        logger.info("HybridLightRAGCore initialized successfully")

    return _lightrag_core


@mcp.tool
async def hybridrag_query(
    query: str,
    mode: Literal["local", "global", "hybrid", "naive", "mix"] = "hybrid",
    top_k: int = 10,
    context_only: bool = False,
    max_entity_tokens: int = 6000,
    max_relation_tokens: int = 8000
) -> str:
    """
    Query the HybridRAG knowledge base with configurable retrieval modes.

    Args:
        query: Search query or question about the knowledge base
        mode: Retrieval mode:
            - local: Entity-focused, specific relationships
            - global: Community-based summaries and overviews
            - hybrid: Combined local + global (recommended default)
            - naive: Basic vector similarity
            - mix: All strategies combined
        top_k: Number of top results to retrieve (default: 10)
        context_only: Return raw context without LLM generation
        max_entity_tokens: Max tokens for entity context (local/hybrid modes)
        max_relation_tokens: Max tokens for relation context (global/hybrid modes)

    Returns:
        Query result from LightRAG
    """
    try:
        core = await get_lightrag_core()

        result = await core.aquery(
            query=query,
            mode=mode,
            only_need_context=context_only,
            top_k=top_k,
            max_entity_tokens=max_entity_tokens,
            max_relation_tokens=max_relation_tokens
        )

        if result.error:
            return f"Error: {result.error}"

        # Format response with metadata
        response = result.result
        if not context_only:
            response += f"\n\n---\n_Query mode: {mode} | Execution time: {result.execution_time:.2f}s_"

        return response

    except Exception as e:
        logger.error(f"Query error: {e}")
        return f"Error executing query: {str(e)}"


@mcp.tool
async def hybridrag_local_query(
    query: str,
    top_k: int = 10,
    max_entity_tokens: int = 6000
) -> str:
    """
    Query using LOCAL mode for specific entity relationships.

    Best for:
    - Finding specific functions, classes, or named concepts
    - Looking up entity definitions and properties
    - Tracing direct relationships between entities

    Args:
        query: Search query targeting specific entities
        top_k: Number of entity matches to retrieve
        max_entity_tokens: Maximum tokens for entity context

    Returns:
        Entity-focused query results
    """
    try:
        core = await get_lightrag_core()

        result = await core.local_query(
            query=query,
            top_k=top_k,
            max_entity_tokens=max_entity_tokens
        )

        if result.error:
            return f"Error: {result.error}"

        return result.result + f"\n\n---\n_Mode: local | Time: {result.execution_time:.2f}s_"

    except Exception as e:
        logger.error(f"Local query error: {e}")
        return f"Error executing local query: {str(e)}"


@mcp.tool
async def hybridrag_global_query(
    query: str,
    top_k: int = 10,
    max_relation_tokens: int = 8000
) -> str:
    """
    Query using GLOBAL mode for high-level overviews and summaries.

    Best for:
    - Understanding overall architecture or workflow
    - Getting summaries of large document sets
    - Identifying high-level patterns and themes

    Args:
        query: Search query for overviews or summaries
        top_k: Number of community matches to retrieve
        max_relation_tokens: Maximum tokens for relationship context

    Returns:
        High-level overview and summary results
    """
    try:
        core = await get_lightrag_core()

        result = await core.global_query(
            query=query,
            top_k=top_k,
            max_relation_tokens=max_relation_tokens
        )

        if result.error:
            return f"Error: {result.error}"

        return result.result + f"\n\n---\n_Mode: global | Time: {result.execution_time:.2f}s_"

    except Exception as e:
        logger.error(f"Global query error: {e}")
        return f"Error executing global query: {str(e)}"


@mcp.tool
async def hybridrag_hybrid_query(
    query: str,
    top_k: int = 10,
    max_entity_tokens: int = 6000,
    max_relation_tokens: int = 8000
) -> str:
    """
    Query using HYBRID mode combining local entities and global context.

    This is the recommended default for most queries. Combines:
    - Entity-specific information (local)
    - Community summaries and relationships (global)

    Best for:
    - General questions needing both specifics and context
    - Most everyday queries
    - When unsure which mode to use

    Args:
        query: Search query
        top_k: Number of matches per strategy
        max_entity_tokens: Maximum entity tokens
        max_relation_tokens: Maximum relation tokens

    Returns:
        Comprehensive results combining local and global retrieval
    """
    try:
        core = await get_lightrag_core()

        result = await core.hybrid_query(
            query=query,
            top_k=top_k,
            max_entity_tokens=max_entity_tokens,
            max_relation_tokens=max_relation_tokens
        )

        if result.error:
            return f"Error: {result.error}"

        return result.result + f"\n\n---\n_Mode: hybrid | Time: {result.execution_time:.2f}s_"

    except Exception as e:
        logger.error(f"Hybrid query error: {e}")
        return f"Error executing hybrid query: {str(e)}"


@mcp.tool
async def hybridrag_multihop_query(
    query: str,
    max_steps: int = 8,
    verbose: bool = False
) -> str:
    """
    Execute multi-hop reasoning for complex analytical queries.

    Uses PromptChain's AgenticStepProcessor to perform multi-step analysis:
    1. Analyzes the query and determines information needs
    2. Plans which LightRAG tools to call
    3. Executes multiple tool calls, accumulating context
    4. Synthesizes a final answer from gathered information

    Best for:
    - Complex analytical questions requiring multiple perspectives
    - Comparative analysis ("Compare X and Y")
    - Multi-entity queries ("How do A, B, and C relate?")
    - Questions requiring both specific details and broad context

    Args:
        query: Complex question requiring multi-step reasoning
        max_steps: Maximum reasoning steps (2-10 recommended)
        verbose: Include reasoning trace in output

    Returns:
        Synthesized answer from multi-hop reasoning
    """
    try:
        core = await get_lightrag_core()

        # Import agentic RAG module
        try:
            from src.agentic_rag import create_agentic_rag
        except ImportError as e:
            return f"Error: Multi-hop reasoning requires PromptChain. Install with: pip install git+https://github.com/gyasis/PromptChain.git\n\nImport error: {e}"

        # Create agentic RAG instance
        model_name = MODEL_OVERRIDE or "azure/gpt-4o"
        agentic = create_agentic_rag(
            lightrag_core=core,
            model_name=model_name,
            max_internal_steps=max_steps,
            verbose=verbose
        )

        # Execute multi-hop reasoning
        result = await agentic.execute_multi_hop_reasoning(
            query=query,
            timeout_seconds=300.0
        )

        # Format response
        response = result.get('answer', 'No answer generated')

        if verbose and 'reasoning_trace' in result:
            response += f"\n\n---\n**Reasoning Trace:**\n{result['reasoning_trace']}"

        response += f"\n\n---\n_Mode: multihop | Steps: {result.get('steps_taken', 'unknown')} | Time: {result.get('execution_time', 0):.2f}s_"

        return response

    except Exception as e:
        logger.error(f"Multi-hop query error: {e}")
        return f"Error executing multi-hop query: {str(e)}"


@mcp.tool
async def hybridrag_extract_context(
    query: str,
    mode: Literal["local", "global", "hybrid"] = "hybrid",
    top_k: int = 10
) -> str:
    """
    Extract raw context from the knowledge base without LLM generation.

    Returns the retrieved context chunks that would be used to answer the query,
    without passing them through an LLM for synthesis.

    Useful for:
    - Seeing exactly what was retrieved
    - Building custom prompts with the context
    - Debugging retrieval quality

    Args:
        query: Search query
        mode: Retrieval mode (local, global, hybrid)
        top_k: Number of results to retrieve

    Returns:
        Raw retrieved context
    """
    try:
        core = await get_lightrag_core()

        context = await core.extract_context(
            query=query,
            mode=mode,
            top_k=top_k
        )

        return context if context else "No context retrieved for this query."

    except Exception as e:
        logger.error(f"Context extraction error: {e}")
        return f"Error extracting context: {str(e)}"


@mcp.tool
async def hybridrag_database_status() -> str:
    """
    Get the current status of the HybridRAG database.

    Returns information about:
    - Database location and size
    - Model configuration
    - Graph statistics
    - Initialization status

    Returns:
        Database status information
    """
    try:
        core = await get_lightrag_core()
        stats = core.get_stats()

        # Format status
        lines = [
            "# HybridRAG Database Status",
            "",
            f"**Database Path:** `{stats.get('working_directory', 'unknown')}`",
            f"**Initialized:** {stats.get('initialized', False)}",
            f"**LLM Model:** {stats.get('model_name', 'unknown')}",
            f"**Embedding Model:** {stats.get('embedding_model', 'unknown')}",
            f"**Context Cache Size:** {stats.get('cache_size', 0)}",
            "",
        ]

        # Add graph files info
        if 'graph_files' in stats:
            lines.append(f"**Graph Files:** {stats['graph_files']}")

        if 'storage_info' in stats:
            lines.append("")
            lines.append("**Storage Details:**")
            for name, size in stats['storage_info'].items():
                lines.append(f"  - {name}: {size}")

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"Status error: {e}")
        return f"Error getting database status: {str(e)}"


@mcp.tool
async def hybridrag_health_check() -> str:
    """
    Perform a health check on the HybridRAG system.

    Checks:
    - Database initialization
    - Query functionality
    - Working directory status

    Returns:
        Health check results
    """
    try:
        core = await get_lightrag_core()
        health = await core.health_check()

        status_emoji = {
            "healthy": "✅",
            "degraded": "⚠️",
            "unhealthy": "❌"
        }.get(health.get('status', 'unknown'), "❓")

        lines = [
            f"# Health Check: {status_emoji} {health.get('status', 'unknown').upper()}",
            "",
        ]

        if 'checks' in health:
            lines.append("**Checks:**")
            for check_name, check_result in health['checks'].items():
                emoji = "✅" if check_result == "ok" else "❌"
                lines.append(f"  - {check_name}: {emoji} {check_result}")

        if 'error' in health:
            lines.append("")
            lines.append(f"**Error:** {health['error']}")

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"Health check error: {e}")
        return f"❌ Health check failed: {str(e)}"


def main():
    """Run the MCP server."""
    logger.info(f"Starting HybridRAG MCP Server")
    logger.info(f"Database: {DATABASE_PATH}")
    if MODEL_OVERRIDE:
        logger.info(f"Model override: {MODEL_OVERRIDE}")
    if EMBED_MODEL_OVERRIDE:
        logger.info(f"Embedding model override: {EMBED_MODEL_OVERRIDE}")

    # Run the MCP server (stdio transport)
    mcp.run()


if __name__ == "__main__":
    main()
