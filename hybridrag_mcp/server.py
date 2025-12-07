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
    Query the HybridRAG knowledge graph with configurable retrieval modes.

    This is the main query tool with full control over retrieval strategy.

    MODE SELECTION GUIDE:
    - "local": For SPECIFIC entities, names, or things. Use when query targets a particular item.
    - "global": For OVERVIEWS, summaries, themes, or patterns across the knowledge base.
    - "hybrid": RECOMMENDED DEFAULT. Combines local + global for balanced results.
    - "naive": Simple vector similarity. Use for keyword/text matching without graph reasoning.
    - "mix": ALL strategies combined. Use for comprehensive research requiring full coverage.

    DECISION TREE:
    1. Asking about a specific named thing? -> "local"
    2. Asking for overview/summary/patterns? -> "global"
    3. Need both specifics AND context? -> "hybrid"
    4. Simple keyword search? -> "naive"
    5. Need everything possible? -> "mix"

    Args:
        query: Natural language question or search terms
        mode: Retrieval strategy (local|global|hybrid|naive|mix). Default: hybrid
        top_k: Number of results per strategy (default: 10)
        context_only: Return raw retrieved chunks without LLM synthesis
        max_entity_tokens: Max tokens for entity context in local/hybrid modes
        max_relation_tokens: Max tokens for relationship context in global/hybrid modes

    Returns:
        Synthesized answer from the knowledge graph with execution metadata
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
    Query for SPECIFIC entities and their direct relationships in the knowledge graph.

    USE THIS when the query targets a PARTICULAR named thing:
    - Specific functions, classes, tables, or modules
    - Named concepts, people, or identifiers
    - Direct relationships between known entities
    - "What is X?" or "Find Y" type questions

    DO NOT USE for overviews, summaries, or pattern discovery - use global_query instead.

    Args:
        query: The specific entity or thing to find
        top_k: Number of entity matches to retrieve (default: 10)
        max_entity_tokens: Max tokens for entity context (default: 6000)

    Returns:
        Entity-focused results with direct relationships
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
    Query for HIGH-LEVEL overviews, summaries, and patterns across the knowledge graph.

    USE THIS when the query asks for:
    - Overviews or summaries of topics/domains
    - Patterns, themes, or trends across documents
    - Architecture or workflow understanding
    - "What are the main..." or "Summarize..." type questions
    - Broad categorization or classification

    DO NOT USE for specific entity lookups - use local_query instead.

    Args:
        query: Question asking for overview, summary, or patterns
        top_k: Number of community/cluster matches (default: 10)
        max_relation_tokens: Max tokens for relationship context (default: 8000)

    Returns:
        High-level summaries and patterns from community-based retrieval
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
    Query combining BOTH local entity details AND global context. RECOMMENDED DEFAULT.

    USE THIS when:
    - You need both specific details AND broader context
    - The query is general-purpose or you're unsure which mode fits
    - Questions involve relationships between entities AND their context
    - Most everyday questions about the knowledge base

    This combines:
    - Local: Specific entity information and direct relationships
    - Global: Community summaries and high-level patterns

    Args:
        query: Any natural language question
        top_k: Number of matches per strategy (default: 10)
        max_entity_tokens: Max tokens for entity details (default: 6000)
        max_relation_tokens: Max tokens for relationships (default: 8000)

    Returns:
        Comprehensive results combining entity details with broader context
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
    Execute MULTI-STEP agentic reasoning for COMPLEX analytical queries.

    USE THIS for questions that CANNOT be answered in a single retrieval:
    - Comparative analysis: "Compare X with Y", "What's the difference between A and B?"
    - Multi-entity questions: "How do A, B, and C all relate to each other?"
    - Tracing/lineage: "Trace the flow from X to Z", "What's the chain from A to B?"
    - Complex analysis requiring multiple perspectives and synthesis

    HOW IT WORKS (different from other tools):
    1. An AI agent analyzes what information is needed
    2. Agent plans and executes MULTIPLE queries (local, global, hybrid)
    3. Agent accumulates context across multiple retrieval steps
    4. Agent synthesizes a final comprehensive answer

    SLOWER but MORE THOROUGH than single-mode queries. Use when simpler queries fail
    to provide complete answers.

    Args:
        query: Complex question requiring multi-step reasoning
        max_steps: Max reasoning iterations (default: 8, range: 2-10)
        verbose: Include step-by-step reasoning trace in output

    Returns:
        Synthesized answer from multi-hop reasoning with execution metadata
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

        # Execute multi-hop reasoning with shield to protect from client cancellation
        # This prevents the MCP client timeout from cancelling the long-running operation
        try:
            result = await asyncio.shield(
                agentic.execute_multi_hop_reasoning(
                    query=query,
                    timeout_seconds=600.0
                )
            )
        except asyncio.CancelledError:
            logger.warning("Multi-hop query cancelled by client - this is expected for long queries")
            return "Query was cancelled. Multi-hop reasoning takes time (2-10 minutes). Please try again or use a simpler query mode (hybrid, local, global) for faster results."

        # Format response - agentic_rag returns 'result' key, not 'answer'
        response = result.get('result') or result.get('answer', 'No answer generated')

        if verbose and 'reasoning_trace' in result:
            response += f"\n\n---\n**Reasoning Trace:**\n{result['reasoning_trace']}"

        response += f"\n\n---\n_Mode: multihop | Steps: {result.get('steps_taken', 'unknown')} | Time: {result.get('execution_time', 0):.2f}s_"

        return response

    except asyncio.CancelledError:
        logger.warning("Multi-hop query cancelled during setup")
        return "Query was cancelled during initialization. Multi-hop reasoning requires more time. Try using hybrid mode for faster results."
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
    Extract RAW context chunks WITHOUT LLM synthesis - for inspection or custom processing.

    USE THIS when you want to:
    - See exactly what chunks were retrieved (debugging)
    - Build your own custom prompt with the raw context
    - Inspect retrieval quality before running a full query
    - Pass context to a different LLM or processing pipeline

    Unlike other query tools, this returns the raw retrieved text chunks
    WITHOUT passing them through an LLM for answer generation.

    Args:
        query: Search query to retrieve context for
        mode: Retrieval strategy - local|global|hybrid (default: hybrid)
        top_k: Number of context chunks to retrieve (default: 10)

    Returns:
        Raw text chunks from the knowledge graph (no LLM processing)
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
    Get status and statistics about the HybridRAG knowledge graph database.

    USE THIS to check:
    - Database path and whether it's properly initialized
    - Which LLM and embedding models are configured
    - Graph size and storage statistics
    - Cache status

    Helpful for debugging connection issues or verifying configuration.

    Returns:
        Database status including path, models, and graph statistics
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
    Perform a health check to verify the HybridRAG system is working.

    USE THIS when:
    - Queries are failing or returning errors
    - You want to verify the system is properly initialized
    - Troubleshooting connection or configuration issues

    Checks performed:
    - Database initialization status
    - Working directory accessibility
    - Basic query functionality

    Returns:
        Health status (healthy/degraded/unhealthy) with diagnostic details
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
