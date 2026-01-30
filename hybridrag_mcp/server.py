#!/usr/bin/env python3
"""
HybridRAG MCP Server - Optimized with Tiered Query Architecture
================================================================
Model Context Protocol server for Claude Desktop integration.

Provides LightRAG query tools with multi-mode support and tiered escalation strategy.
Tools are organized by speed tier (T1-T4) to guide LLM agents toward optimal queries.

TIERED FRAMEWORK (10-60-600 Rule):
- T1 Recon (instant): database_status, health_check, get_logs
- T2 Tactical (fast): local_query, extract_context
- T3 Strategic (medium): global_query, hybrid_query - run as background tasks
- T4 Deep Intel (slow): multihop_query - complex reasoning, background task

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
import tempfile
import atexit
import shutil
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional, List, Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv(override=True)  # Force project .env to override system vars

from fastmcp import FastMCP, Context
from src.lightrag_core import HybridLightRAGCore
from config.config import HybridRAGConfig
from src.database_registry import DatabaseRegistry
from src.config.config import BackendConfig, BackendType

# Import diagnostic logging module
from hybridrag_mcp.diagnostic_logging import (
    get_diagnostic_store,
    install_diagnostic_handler,
    format_logs_as_markdown,
    set_trace_id,
    clear_trace_id,
)

# Suppress LiteLLM cost calculation warnings for unmapped models
import litellm
litellm.suppress_debug_info = True
litellm.drop_params = True  # Don't fail on unknown params

# =============================================================================
# CONFIGURATION CONSTANTS
# =============================================================================

# Timeout settings (user requested 15 minutes)
DEFAULT_TIMEOUT_SECONDS = 900.0  # 15 minutes for multihop
STRATEGIC_TIMEOUT_SECONDS = 180.0  # 3 minutes for hybrid/global

# Server-side top_k caps by tier (prevents LLMs from requesting excessive values)
MAX_TOP_K_BY_TOOL = {
    "local_query": 10,       # Tier 2
    "extract_context": 15,   # Tier 2
    "global_query": 15,      # Tier 3
    "hybrid_query": 15,      # Tier 3
    "query": 20,             # Tier 3 (flexible mode)
}

# =============================================================================
# LOGGING SETUP
# =============================================================================

# Create temp log directory (cleaned up on restart/exit)
TEMP_LOG_DIR = Path(tempfile.gettempdir()) / "hybridrag_mcp_logs"
if TEMP_LOG_DIR.exists():
    shutil.rmtree(TEMP_LOG_DIR)  # Clean up from previous runs
TEMP_LOG_DIR.mkdir(parents=True, exist_ok=True)

# =============================================================================
# DIAGNOSTIC LOGGING CONFIGURATION
# =============================================================================

# Initialize diagnostic log store (100 entries rotating buffer)
DIAGNOSTIC_LOG_STORE = get_diagnostic_store(maxlen=100)

# Cleanup on exit
def cleanup_temp_logs():
    if TEMP_LOG_DIR.exists():
        shutil.rmtree(TEMP_LOG_DIR, ignore_errors=True)

def cleanup_lightrag_connections():
    """Cleanup LightRAG connections on exit to prevent connection pool leaks."""
    global _lightrag_core
    if _lightrag_core is not None:
        try:
            # Try to finalize LightRAG (closes connection pools)
            if hasattr(_lightrag_core, 'rag') and hasattr(_lightrag_core.rag, 'finalize'):
                # Create event loop if needed for async cleanup
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Schedule cleanup for later
                        loop.create_task(_lightrag_core.rag.finalize())
                    else:
                        loop.run_until_complete(_lightrag_core.rag.finalize())
                except RuntimeError:
                    # No event loop, create one
                    asyncio.run(_lightrag_core.rag.finalize())
            logger.info("LightRAG connections cleaned up successfully")
        except Exception as e:
            logger.warning(f"Error during LightRAG cleanup: {e}")
        finally:
            _lightrag_core = None

atexit.register(cleanup_temp_logs)
atexit.register(cleanup_lightrag_connections)

# Configure logging with both console and temp file output
LOG_FILE = TEMP_LOG_DIR / f"hybridrag_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Console output
        logging.FileHandler(LOG_FILE)  # Temp file output
    ]
)
logger = logging.getLogger(__name__)

# Install diagnostic buffer handler to capture logs for MCP tool
DIAGNOSTIC_HANDLER = install_diagnostic_handler(
    level=logging.DEBUG,  # Capture DEBUG and above
    store=DIAGNOSTIC_LOG_STORE
)

# Enable LiteLLM logging to temp directory for PromptChain debugging
LITELLM_LOG_FILE = TEMP_LOG_DIR / f"litellm_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
try:
    import litellm
    litellm.set_verbose = False  # MUST be False - stdout corrupts MCP stdio protocol
    # Set up LiteLLM file logging
    litellm_logger = logging.getLogger("LiteLLM")
    litellm_logger.setLevel(logging.DEBUG)
    litellm_handler = logging.FileHandler(LITELLM_LOG_FILE)
    litellm_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    litellm_logger.addHandler(litellm_handler)
    logger.info(f"LiteLLM log file: {LITELLM_LOG_FILE}")
except ImportError:
    logger.warning("LiteLLM not available for logging")

logger.info(f"Temp log directory: {TEMP_LOG_DIR}")
logger.info(f"Log file: {LOG_FILE}")

# =============================================================================
# DATABASE CONFIGURATION
# =============================================================================

# Get database path from environment
DATABASE_PATH = os.environ.get("HYBRIDRAG_DATABASE")
DATABASE_NAME = os.environ.get("HYBRIDRAG_DATABASE_NAME")  # Optional: specify database by name
# Model overrides - check HYBRIDRAG_MODEL first, fall back to AGENTIC_MODEL or LIGHTRAG_MODEL
MODEL_OVERRIDE = os.environ.get("HYBRIDRAG_MODEL") or os.environ.get("AGENTIC_MODEL") or os.environ.get("LIGHTRAG_MODEL")
EMBED_MODEL_OVERRIDE = os.environ.get("HYBRIDRAG_EMBED_MODEL") or os.environ.get("LIGHTRAG_EMBED_MODEL")

# Backend configuration (loaded from registry or environment)
BACKEND_CONFIG: Optional[BackendConfig] = None
# Model configuration (loaded from registry, per-database)
MODEL_CONFIG: Optional[Dict[str, Any]] = None

# Try to load from registry first
try:
    registry = DatabaseRegistry()

    # If database name specified, use it; otherwise derive from path
    if DATABASE_NAME:
        db_entry = registry.get(DATABASE_NAME)
        if db_entry:
            BACKEND_CONFIG = db_entry.get_backend_config()
            MODEL_CONFIG = db_entry.get_model_config()
            DATABASE_PATH = DATABASE_PATH or db_entry.path
            logger.info(f"Loaded config from registry for '{DATABASE_NAME}': backend={BACKEND_CONFIG.backend_type.value}")
            if MODEL_CONFIG:
                logger.info(f"Registry model_config: llm={MODEL_CONFIG.get('llm_model')}, embed={MODEL_CONFIG.get('embedding_model')}")
    elif DATABASE_PATH:
        # Try to find database by path
        for entry in registry.list_all():
            if entry.path and Path(entry.path).resolve() == Path(DATABASE_PATH).expanduser().resolve():
                BACKEND_CONFIG = entry.get_backend_config()
                MODEL_CONFIG = entry.get_model_config()
                DATABASE_NAME = entry.name
                logger.info(f"Found registry entry '{entry.name}' for path: backend={BACKEND_CONFIG.backend_type.value}")
                if MODEL_CONFIG:
                    logger.info(f"Registry model_config: llm={MODEL_CONFIG.get('llm_model')}, embed={MODEL_CONFIG.get('embedding_model')}")
                break
except Exception as e:
    logger.error(f"CRITICAL: Could not load from registry: {e}")
    # If a specific database was requested, this is a fatal error
    if DATABASE_NAME:
        print(f"FATAL: Registry lookup failed for database '{DATABASE_NAME}': {e}", file=sys.stderr)
        print("Check ~/.hybridrag/registry.yaml exists and is valid YAML", file=sys.stderr)
        sys.exit(1)

# Apply model config from registry (priority: env override > registry > defaults)
if MODEL_CONFIG:
    # Registry provides per-database model config
    if not MODEL_OVERRIDE and MODEL_CONFIG.get('llm_model'):
        MODEL_OVERRIDE = MODEL_CONFIG['llm_model']
        logger.info(f"Using LLM model from registry: {MODEL_OVERRIDE}")
    if not EMBED_MODEL_OVERRIDE and MODEL_CONFIG.get('embedding_model'):
        EMBED_MODEL_OVERRIDE = MODEL_CONFIG['embedding_model']
        logger.info(f"Using embedding model from registry: {EMBED_MODEL_OVERRIDE}")
    # Set API keys from registry config
    if MODEL_CONFIG.get('api_keys'):
        for key_name, key_value in MODEL_CONFIG['api_keys'].items():
            env_key = f"{key_name.upper()}_API_KEY"
            if key_value and not os.environ.get(env_key):
                os.environ[env_key] = key_value
                logger.info(f"Set {env_key} from registry model_config")

# SAFEGUARD: Warn loudly if DATABASE_NAME was specified but not found in registry
if DATABASE_NAME and BACKEND_CONFIG is None:
    logger.error(f"CRITICAL: Database '{DATABASE_NAME}' not found in registry!")
    print(f"FATAL: Database '{DATABASE_NAME}' not found in ~/.hybridrag/registry.yaml", file=sys.stderr)
    print("Available databases:", file=sys.stderr)
    try:
        for entry in DatabaseRegistry().list_all():
            print(f"  - {entry.name}", file=sys.stderr)
    except Exception:
        print("  (could not list databases)", file=sys.stderr)
    sys.exit(1)

# Validate database path
if not DATABASE_PATH:
    logger.error("HYBRIDRAG_DATABASE environment variable not set")
    print("Error: HYBRIDRAG_DATABASE environment variable is required", file=sys.stderr)
    print("Set it to the path of your LightRAG database directory", file=sys.stderr)
    sys.exit(1)

DATABASE_PATH = Path(DATABASE_PATH).expanduser().resolve()
if not DATABASE_PATH.exists() and (not BACKEND_CONFIG or BACKEND_CONFIG.backend_type == BackendType.JSON):
    logger.warning(f"Database path does not exist: {DATABASE_PATH}")
    print(f"Warning: Database path does not exist: {DATABASE_PATH}", file=sys.stderr)
    print("The database will be created on first ingestion", file=sys.stderr)

# Log backend configuration - BE EXPLICIT about what backend is being used
if BACKEND_CONFIG:
    if BACKEND_CONFIG.backend_type == BackendType.POSTGRESQL:
        logger.info(f"✓ Using PostgreSQL backend: {BACKEND_CONFIG.postgres_host}:{BACKEND_CONFIG.postgres_port}/{BACKEND_CONFIG.postgres_database}")
        print(f"Backend: PostgreSQL ({BACKEND_CONFIG.postgres_host}:{BACKEND_CONFIG.postgres_port}/{BACKEND_CONFIG.postgres_database})", file=sys.stderr)
    else:
        logger.info(f"Using {BACKEND_CONFIG.backend_type.value} backend")
        print(f"Backend: {BACKEND_CONFIG.backend_type.value}", file=sys.stderr)
else:
    # SAFEGUARD: Loud warning when defaulting to JSON
    logger.warning("⚠️ No backend configuration loaded - DEFAULTING TO JSON BACKEND")
    logger.warning("⚠️ Data will be stored in JSON files, NOT PostgreSQL!")
    print("WARNING: No backend configuration - using JSON file storage (not PostgreSQL)", file=sys.stderr)

# =============================================================================
# MCP SERVER INITIALIZATION
# =============================================================================

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
        logger.info(
            f"Initializing HybridLightRAGCore with database: {DATABASE_PATH}",
            extra={"category": "init"}
        )

        # Create config
        config = HybridRAGConfig()
        config.lightrag.working_dir = str(DATABASE_PATH)

        # Apply model overrides if set
        if MODEL_OVERRIDE:
            config.lightrag.model_name = MODEL_OVERRIDE
            logger.info(f"Using model override: {MODEL_OVERRIDE}", extra={"category": "init"})

        if EMBED_MODEL_OVERRIDE:
            config.lightrag.embedding_model = EMBED_MODEL_OVERRIDE
            logger.info(f"Using embedding model override: {EMBED_MODEL_OVERRIDE}", extra={"category": "init"})

        # Initialize core with backend config if available
        if BACKEND_CONFIG:
            logger.info(
                f"Initializing with {BACKEND_CONFIG.backend_type.value} backend",
                extra={"category": "init"}
            )
            _lightrag_core = HybridLightRAGCore(config, backend_config=BACKEND_CONFIG)
        else:
            logger.warning(
                "No BACKEND_CONFIG - initializing with JSON backend",
                extra={"category": "init"}
            )
            _lightrag_core = HybridLightRAGCore(config)

        await _lightrag_core._ensure_initialized()

        # SAFEGUARD: Verify PostgreSQL connection if that's what we expected
        if BACKEND_CONFIG and BACKEND_CONFIG.backend_type == BackendType.POSTGRESQL:
            try:
                # Verify we can actually connect to PostgreSQL
                import asyncpg
                logger.info(
                    f"Verifying PostgreSQL connection to {BACKEND_CONFIG.postgres_host}:{BACKEND_CONFIG.postgres_port}",
                    extra={"category": "db"}
                )
                conn = await asyncpg.connect(
                    host=BACKEND_CONFIG.postgres_host,
                    port=BACKEND_CONFIG.postgres_port,
                    user=BACKEND_CONFIG.postgres_user,
                    password=BACKEND_CONFIG.postgres_password,
                    database=BACKEND_CONFIG.postgres_database
                )
                # Quick verification query
                version = await conn.fetchval("SELECT version()")
                await conn.close()
                logger.info(
                    f"PostgreSQL connection verified: {version[:50]}...",
                    extra={"category": "db", "metadata": {"status": "connected"}}
                )
            except Exception as e:
                logger.error(
                    f"CRITICAL: PostgreSQL connection verification FAILED: {e}",
                    extra={"category": "db", "metadata": {"error_type": type(e).__name__}}
                )
                logger.error(
                    "Data may be going to JSON files instead of PostgreSQL!",
                    extra={"category": "error"}
                )
                raise RuntimeError(f"PostgreSQL backend configured but connection failed: {e}")

        logger.info("HybridLightRAGCore initialized successfully", extra={"category": "init"})

    return _lightrag_core


def cap_top_k(tool_name: str, requested_top_k: int) -> tuple[int, bool]:
    """Cap top_k to maximum allowed for tool tier. Returns (capped_value, was_capped)."""
    max_allowed = MAX_TOP_K_BY_TOOL.get(tool_name, 20)
    if requested_top_k > max_allowed:
        return max_allowed, True
    return requested_top_k, False


def extract_entity_seeds(result_text: str, max_seeds: int = 5) -> List[str]:
    """Extract potential entity names from result text for seeding multihop queries."""
    # Simple extraction - look for capitalized phrases and quoted terms
    import re
    seeds = []

    # Find quoted terms
    quoted = re.findall(r'["\']([^"\']+)["\']', result_text)
    seeds.extend(quoted[:max_seeds])

    # Find capitalized multi-word terms (likely entity names)
    capitalized = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b', result_text)
    for term in capitalized:
        if term not in seeds and len(seeds) < max_seeds:
            seeds.append(term)

    return seeds[:max_seeds]


# =============================================================================
# TIER 1: RECON TOOLS (Instant - <5s)
# =============================================================================

@mcp.tool
async def hybridrag_database_status() -> str:
    """
    [SPEED: INSTANT] [TIER: 1] [MAX_TIMEOUT: 5s]

    Get status and statistics about the HybridRAG knowledge graph database.

    USE FOR: Checking if database exists and is configured before querying.
    STRATEGY: Call this FIRST if unsure whether HybridRAG has relevant data.

    Checks:
    - Database path and initialization status
    - LLM and embedding model configuration
    - Graph size and storage statistics
    - Cache status

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
    [SPEED: INSTANT] [TIER: 1] [MAX_TIMEOUT: 10s]

    Perform a health check to verify the HybridRAG system is working.

    USE FOR: Diagnosing connection or initialization failures.
    STRATEGY: Call when queries return errors or empty results.

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


@mcp.tool
async def hybridrag_get_logs(
    limit: int = 50,
    category: Optional[Literal["db", "embedding", "llm", "query", "system", "init", "error"]] = None,
    min_level: Optional[Literal["DEBUG", "INFO", "WARNING", "ERROR"]] = None,
    errors_only: bool = False,
    trace_id: Optional[str] = None,
    search_text: Optional[str] = None,
    format: Literal["markdown", "raw"] = "markdown"
) -> str:
    """
    [SPEED: INSTANT] [TIER: 1] [MAX_TIMEOUT: 5s]

    Get diagnostic logs from the HybridRAG MCP server with filtering.

    USE FOR: Debugging query issues, monitoring progress, checking for errors.
    STRATEGY: Call after a failed query to understand what went wrong.

    FILTERING OPTIONS:
    - errors_only: Quick filter to see only ERROR/CRITICAL logs
    - category: Filter by log category (db, embedding, llm, query, system)
    - min_level: Minimum log level (DEBUG < INFO < WARNING < ERROR)
    - trace_id: Filter logs from a specific query execution
    - search_text: Search for text in log messages

    CATEGORIES:
    - db: PostgreSQL connections, queries, pool status
    - embedding: Vector embedding calls
    - llm: LLM synthesis/completion calls
    - query: RAG query execution
    - system: Server initialization, general events
    - init: Initialization and startup logs
    - error: Error-specific logs

    Args:
        limit: Number of recent log entries (default: 50)
        category: Filter by category (db|embedding|llm|query|system|init|error)
        min_level: Minimum log level (DEBUG|INFO|WARNING|ERROR)
        errors_only: If True, only show ERROR and CRITICAL logs
        trace_id: Filter by trace ID (from a specific query)
        search_text: Search for text in log messages
        format: Output format - "markdown" (table) or "raw" (file contents)

    Returns:
        Filtered log entries with diagnostic information
    """
    try:
        # If raw format requested, return file contents (legacy behavior)
        if format == "raw":
            if not LOG_FILE.exists():
                return f"Log file not found: {LOG_FILE}"
            with open(LOG_FILE, 'r') as f:
                all_lines = f.readlines()
                recent = all_lines[-limit:] if len(all_lines) > limit else all_lines
            return f"**Log file:** `{LOG_FILE}`\n**Temp dir:** `{TEMP_LOG_DIR}`\n\n---\n```\n{''.join(recent)}```"

        # Use diagnostic store for structured logs
        store = DIAGNOSTIC_LOG_STORE

        # Handle errors_only shortcut
        effective_min_level = "ERROR" if errors_only else min_level

        # Get filtered entries
        entries = store.get_filtered(
            category=category,
            min_level=effective_min_level,
            trace_id=trace_id,
            search_text=search_text,
            limit=limit
        )

        # Build title with filter info
        title_parts = ["Diagnostic Logs"]
        if errors_only:
            title_parts.append("(Errors Only)")
        elif category:
            title_parts.append(f"(Category: {category})")
        elif min_level:
            title_parts.append(f"(Level >= {min_level})")
        if trace_id:
            title_parts.append(f"[Trace: {trace_id}]")
        if search_text:
            title_parts.append(f"[Search: '{search_text}']")

        title = " ".join(title_parts)

        # Format output
        result = format_logs_as_markdown(entries, title=title, include_stats=True)

        # Add store stats
        stats = store.get_stats()
        result += f"\n\n---\n_Buffer: {stats['total_entries']}/{stats['max_entries']} entries_"
        result += f"\n_Log file: `{LOG_FILE}`_"

        return result

    except Exception as e:
        logger.error(f"Error reading logs: {e}", extra={"category": "error"})
        return f"Error reading diagnostic logs: {str(e)}"


# =============================================================================
# TIER 2: TACTICAL TOOLS (Fast - <30s)
# =============================================================================

@mcp.tool
async def hybridrag_local_query(
    query: str,
    top_k: int = 5,
    max_entity_tokens: int = 6000
) -> str:
    """
    [SPEED: FAST] [TIER: 2] [MAX_TIMEOUT: 30s]

    Query for SPECIFIC entities and their direct relationships in the knowledge graph.

    USE FOR: Specific entities, names, definitions, direct relationships.
    STRATEGY: START HERE for most queries. Use top_k=2-5 for speed.
    DO NOT USE: For overviews, summaries, or pattern discovery (use global_query).

    Examples:
        - "What is the HybridRAGConfig class?"
        - "Find the patient_demographics table schema"
        - "What does the get_lineage function do?"
        - "Find the RAF_ASSESSMENT view definition"

    Args:
        query: Specific entity or thing to find
        top_k: Number of entity matches (2-5 recommended, max capped at 10)
        max_entity_tokens: Max tokens for entity context (default: 6000)

    Returns:
        Entity-focused results with direct relationships.
        Includes suggested_seeds for escalation to multihop_query.
        Includes trace_id for debugging with hybridrag_get_logs.
    """
    # Generate trace ID for this query execution
    trace_id = set_trace_id()

    try:
        logger.info(
            f"Local query started: '{query[:80]}...' (top_k={top_k})",
            extra={"category": "query", "trace_id": trace_id, "metadata": {"mode": "local", "top_k": top_k}}
        )

        # Apply server-side top_k cap
        top_k, was_capped = cap_top_k("local_query", top_k)
        if was_capped:
            logger.info(
                f"top_k capped from requested value to {top_k}",
                extra={"category": "query", "trace_id": trace_id}
            )

        logger.info("Initializing LightRAG core", extra={"category": "query", "trace_id": trace_id})
        core = await get_lightrag_core()

        logger.info("Executing local query", extra={"category": "query", "trace_id": trace_id})
        result = await core.local_query(
            query=query,
            top_k=top_k,
            max_entity_tokens=max_entity_tokens
        )

        if result.error:
            logger.error(
                f"Local query returned error: {result.error}",
                extra={"category": "error", "trace_id": trace_id}
            )
            return f"Error: {result.error}\n\n_Trace ID: {trace_id} (use hybridrag_get_logs with trace_id for details)_"

        # Handle None result
        if result.result is None:
            logger.warning(
                "Local query returned no results",
                extra={"category": "query", "trace_id": trace_id}
            )
            return f"No results found for this query.\n\n_Trace ID: {trace_id}_"

        # Extract seeds for potential multihop escalation
        seeds = extract_entity_seeds(result.result)

        logger.info(
            f"Local query completed successfully in {result.execution_time:.2f}s",
            extra={
                "category": "query",
                "trace_id": trace_id,
                "metadata": {"duration_sec": result.execution_time, "result_length": len(result.result)}
            }
        )

        response = result.result
        response += f"\n\n---\n_Mode: local | Tier: 2 | Time: {result.execution_time:.2f}s | Trace: {trace_id}_"
        if was_capped:
            response += "\n_Note: top_k capped at 10 for performance. Use hybrid_query for more depth._"
        if seeds:
            response += f"\n_Suggested multihop seeds: {seeds}_"

        return response

    except Exception as e:
        logger.error(
            f"Local query exception: {type(e).__name__}: {e}",
            extra={"category": "error", "trace_id": trace_id, "metadata": {"error_type": type(e).__name__}},
            exc_info=True
        )
        return f"Error executing local query: {str(e)}\n\n_Trace ID: {trace_id} (use hybridrag_get_logs with trace_id for details)_"
    finally:
        clear_trace_id()


@mcp.tool
async def hybridrag_extract_context(
    query: str,
    mode: Literal["local", "global", "hybrid"] = "local",
    top_k: int = 5
) -> str:
    """
    [SPEED: FAST] [TIER: 2] [MAX_TIMEOUT: 20s]

    Extract RAW context chunks WITHOUT LLM synthesis - for inspection or seeding.

    USE FOR: Getting raw retrieval chunks without LLM processing.
    STRATEGY: Use to inspect what would be retrieved before full query.
              Also use to get entity seeds for multihop_query escalation.

    Unlike other query tools, this returns the raw retrieved text chunks
    WITHOUT passing them through an LLM for answer generation.

    Args:
        query: Search query to retrieve context for
        mode: Retrieval strategy - local (fastest), global, or hybrid (default: local)
        top_k: Number of context chunks (3-5 recommended for seeding, max 15)

    Returns:
        Raw text chunks from the knowledge graph (no LLM processing)
    """
    trace_id = set_trace_id()

    try:
        logger.info(
            f"Extract context started: '{query[:80]}...' (mode={mode}, top_k={top_k})",
            extra={"category": "query", "trace_id": trace_id, "metadata": {"mode": mode, "top_k": top_k}}
        )

        # Apply server-side top_k cap
        top_k, was_capped = cap_top_k("extract_context", top_k)

        core = await get_lightrag_core()

        logger.info("Extracting context (no LLM synthesis)", extra={"category": "query", "trace_id": trace_id})
        context = await core.extract_context(
            query=query,
            mode=mode,
            top_k=top_k
        )

        if not context:
            logger.warning("No context retrieved", extra={"category": "query", "trace_id": trace_id})
            return f"No context retrieved for this query.\n\n_Trace ID: {trace_id}_"

        logger.info(
            f"Context extraction completed, {len(context)} chars",
            extra={"category": "query", "trace_id": trace_id, "metadata": {"result_length": len(context)}}
        )

        response = context
        response += f"\n\n---\n_Mode: {mode} (context only) | Trace: {trace_id}_"
        if was_capped:
            response += "\n_Note: top_k capped at 15 for performance._"

        return response

    except Exception as e:
        logger.error(
            f"Context extraction error: {type(e).__name__}: {e}",
            extra={"category": "error", "trace_id": trace_id},
            exc_info=True
        )
        return f"Error extracting context: {str(e)}\n\n_Trace ID: {trace_id}_"
    finally:
        clear_trace_id()


# =============================================================================
# TIER 3: STRATEGIC TOOLS (Medium - 30-180s, Background Tasks)
# =============================================================================

@mcp.tool()
async def hybridrag_global_query(
    query: str,
    top_k: int = 10,
    max_relation_tokens: int = 8000,
    ctx: Context = None
) -> str:
    """
    [SPEED: MEDIUM] [TIER: 3] [MAX_TIMEOUT: 120s]

    Query for HIGH-LEVEL overviews, summaries, and patterns across the knowledge graph.

    **RUNS AS BACKGROUND TASK** - Returns task ID immediately, poll for results.

    USE FOR: Overviews, summaries, themes, patterns across documents.
    STRATEGY: Use when local_query returns incomplete or "I don't know".
              RUNS AS BACKGROUND TASK - may take 30-60s.
    DO NOT USE: For specific entity lookups (use local_query instead).

    Examples:
        - "What are the main Snowflake tables in this project?"
        - "Summarize the RAF calculation pipeline"
        - "What patterns exist in error handling?"
        - "What are the main data flows in the system?"

    Args:
        query: Question asking for overview, summary, or patterns
        top_k: Number of community/cluster matches (5-10 recommended, max 15)
        max_relation_tokens: Max tokens for relationship context (default: 8000)

    Returns:
        High-level summaries and patterns from community-based retrieval
    """
    trace_id = set_trace_id()

    try:
        logger.info(
            f"Global query started: '{query[:80]}...' (top_k={top_k})",
            extra={"category": "query", "trace_id": trace_id, "metadata": {"mode": "global", "top_k": top_k}}
        )

        # Apply server-side top_k cap
        top_k, was_capped = cap_top_k("global_query", top_k)

        # Report progress if context available
        if ctx:
            await ctx.report_progress(0, 100, "Starting global query...")

        core = await get_lightrag_core()

        if ctx:
            await ctx.report_progress(20, 100, "Retrieving community summaries...")

        logger.info("Executing global query (community summaries)", extra={"category": "query", "trace_id": trace_id})
        result = await core.global_query(
            query=query,
            top_k=top_k,
            max_relation_tokens=max_relation_tokens
        )

        if ctx:
            await ctx.report_progress(90, 100, "Synthesizing response...")

        if result.error:
            logger.error(
                f"Global query returned error: {result.error}",
                extra={"category": "error", "trace_id": trace_id}
            )
            return f"Error: {result.error}\n\n_Trace ID: {trace_id}_"

        # Handle None result
        if result.result is None:
            logger.warning("Global query returned no results", extra={"category": "query", "trace_id": trace_id})
            return f"No results found for this query.\n\n_Trace ID: {trace_id}_"

        # Extract seeds for potential multihop escalation
        seeds = extract_entity_seeds(result.result)

        logger.info(
            f"Global query completed in {result.execution_time:.2f}s",
            extra={"category": "query", "trace_id": trace_id, "metadata": {"duration_sec": result.execution_time}}
        )

        response = result.result
        response += f"\n\n---\n_Mode: global | Tier: 3 | Time: {result.execution_time:.2f}s | Trace: {trace_id}_"
        if was_capped:
            response += "\n_Note: top_k capped at 15 for performance._"
        if seeds:
            response += f"\n_Suggested multihop seeds: {seeds}_"

        if ctx:
            await ctx.report_progress(100, 100, "Complete")

        return response

    except Exception as e:
        logger.error(
            f"Global query exception: {type(e).__name__}: {e}",
            extra={"category": "error", "trace_id": trace_id},
            exc_info=True
        )
        return f"Error executing global query: {str(e)}\n\n_Trace ID: {trace_id}_"
    finally:
        clear_trace_id()


@mcp.tool()
async def hybridrag_hybrid_query(
    query: str,
    top_k: int = 10,
    max_entity_tokens: int = 6000,
    max_relation_tokens: int = 8000,
    ctx: Context = None
) -> str:
    """
    [SPEED: MEDIUM] [TIER: 3] [MAX_TIMEOUT: 180s]

    Query combining BOTH local entity details AND global context. RECOMMENDED for complex questions.

    **RUNS AS BACKGROUND TASK** - Returns task ID immediately, poll for results.

    USE FOR: Questions needing BOTH specific details AND broader context.
    STRATEGY: Use after local_query if answer is incomplete.
              RUNS AS BACKGROUND TASK - may take 60-120s.

    This combines:
    - Local: Specific entity information and direct relationships
    - Global: Community summaries and high-level patterns

    Examples:
        - "How does HybridRAGConfig relate to LightRAG initialization?"
        - "What tables feed into RAF_ASSESSMENT and why?"
        - "Explain the connection between patient data and quality measures"

    Args:
        query: Any natural language question needing comprehensive answer
        top_k: Number of matches per strategy (5-10 recommended, max 15)
        max_entity_tokens: Max tokens for entity details (default: 6000)
        max_relation_tokens: Max tokens for relationships (default: 8000)

    Returns:
        Comprehensive results combining entity details with broader context
    """
    trace_id = set_trace_id()

    try:
        logger.info(
            f"Hybrid query started: '{query[:80]}...' (top_k={top_k})",
            extra={"category": "query", "trace_id": trace_id, "metadata": {"mode": "hybrid", "top_k": top_k}}
        )

        # Apply server-side top_k cap
        top_k, was_capped = cap_top_k("hybrid_query", top_k)

        # Report progress if context available
        if ctx:
            await ctx.report_progress(0, 100, "Starting hybrid query...")

        core = await get_lightrag_core()

        if ctx:
            await ctx.report_progress(20, 100, "Retrieving local entities...")

        logger.info(
            "Executing hybrid query (local + global)",
            extra={"category": "query", "trace_id": trace_id}
        )
        result = await core.hybrid_query(
            query=query,
            top_k=top_k,
            max_entity_tokens=max_entity_tokens,
            max_relation_tokens=max_relation_tokens
        )

        if ctx:
            await ctx.report_progress(90, 100, "Synthesizing response...")

        if result.error:
            logger.error(
                f"Hybrid query returned error: {result.error}",
                extra={"category": "error", "trace_id": trace_id}
            )
            return f"Error: {result.error}\n\n_Trace ID: {trace_id}_"

        # Handle None result
        if result.result is None:
            logger.warning("Hybrid query returned no results", extra={"category": "query", "trace_id": trace_id})
            return f"No results found for this query.\n\n_Trace ID: {trace_id}_"

        # Extract seeds for potential multihop escalation
        seeds = extract_entity_seeds(result.result)

        logger.info(
            f"Hybrid query completed in {result.execution_time:.2f}s",
            extra={"category": "query", "trace_id": trace_id, "metadata": {"duration_sec": result.execution_time}}
        )

        response = result.result
        response += f"\n\n---\n_Mode: hybrid | Tier: 3 | Time: {result.execution_time:.2f}s | Trace: {trace_id}_"
        if was_capped:
            response += "\n_Note: top_k capped at 15 for performance._"
        if seeds:
            response += f"\n_Suggested multihop seeds: {seeds}_"

        if ctx:
            await ctx.report_progress(100, 100, "Complete")

        return response

    except Exception as e:
        logger.error(
            f"Hybrid query exception: {type(e).__name__}: {e}",
            extra={"category": "error", "trace_id": trace_id},
            exc_info=True
        )
        return f"Error executing hybrid query: {str(e)}\n\n_Trace ID: {trace_id}_"
    finally:
        clear_trace_id()


@mcp.tool()
async def hybridrag_query(
    query: str,
    mode: Literal["local", "global", "hybrid", "naive", "mix"] = "hybrid",
    top_k: int = 10,
    context_only: bool = False,
    max_entity_tokens: int = 6000,
    max_relation_tokens: int = 8000,
    ctx: Context = None
) -> str:
    """
    [SPEED: MEDIUM] [TIER: 3] [MAX_TIMEOUT: 180s]

    General query tool with configurable retrieval mode. Use specific tools when possible.

    **RUNS AS BACKGROUND TASK** - Returns task ID immediately, poll for results.

    MODE SELECTION GUIDE:
    - "local": For SPECIFIC entities (Tier 2 speed). Prefer hybridrag_local_query.
    - "global": For OVERVIEWS/summaries (Tier 3). Prefer hybridrag_global_query.
    - "hybrid": RECOMMENDED. Combines local + global (Tier 3).
    - "naive": Simple vector similarity without graph reasoning.
    - "mix": ALL strategies combined. Most comprehensive but slowest.

    DECISION TREE:
    1. Specific named thing? -> "local" or use hybridrag_local_query
    2. Overview/summary? -> "global" or use hybridrag_global_query
    3. Need both? -> "hybrid" or use hybridrag_hybrid_query
    4. Simple keyword search? -> "naive"
    5. Need everything? -> "mix"

    Args:
        query: Natural language question or search terms
        mode: Retrieval strategy (local|global|hybrid|naive|mix). Default: hybrid
        top_k: Number of results per strategy (5-10 recommended, max 20)
        context_only: Return raw chunks without LLM synthesis
        max_entity_tokens: Max tokens for entity context
        max_relation_tokens: Max tokens for relationship context

    Returns:
        Synthesized answer from the knowledge graph with execution metadata
    """
    trace_id = set_trace_id()

    try:
        logger.info(
            f"Query started: '{query[:80]}...' (mode={mode}, top_k={top_k}, context_only={context_only})",
            extra={"category": "query", "trace_id": trace_id, "metadata": {"mode": mode, "top_k": top_k}}
        )

        # Apply server-side top_k cap
        top_k, was_capped = cap_top_k("query", top_k)

        # Report progress if context available
        if ctx:
            await ctx.report_progress(0, 100, f"Starting {mode} query...")

        core = await get_lightrag_core()

        if ctx:
            await ctx.report_progress(30, 100, f"Retrieving with {mode} strategy...")

        logger.info(f"Executing {mode} query", extra={"category": "query", "trace_id": trace_id})
        result = await core.aquery(
            query=query,
            mode=mode,
            only_need_context=context_only,
            top_k=top_k,
            max_entity_tokens=max_entity_tokens,
            max_relation_tokens=max_relation_tokens
        )

        if ctx:
            await ctx.report_progress(90, 100, "Formatting response...")

        if result.error:
            logger.error(
                f"Query returned error: {result.error}",
                extra={"category": "error", "trace_id": trace_id}
            )
            return f"Error: {result.error}\n\n_Trace ID: {trace_id}_"

        # Handle None result
        if result.result is None:
            logger.warning("Query returned no results", extra={"category": "query", "trace_id": trace_id})
            return f"No results found for this query.\n\n_Trace ID: {trace_id}_"

        logger.info(
            f"Query completed in {result.execution_time:.2f}s",
            extra={"category": "query", "trace_id": trace_id, "metadata": {"duration_sec": result.execution_time}}
        )

        # Format response with metadata
        response = result.result
        if not context_only:
            response += f"\n\n---\n_Query mode: {mode} | Tier: 3 | Execution time: {result.execution_time:.2f}s | Trace: {trace_id}_"
            if was_capped:
                response += "\n_Note: top_k capped at 20 for performance._"

        if ctx:
            await ctx.report_progress(100, 100, "Complete")

        return response

    except Exception as e:
        logger.error(
            f"Query exception: {type(e).__name__}: {e}",
            extra={"category": "error", "trace_id": trace_id},
            exc_info=True
        )
        return f"Error executing query: {str(e)}\n\n_Trace ID: {trace_id}_"
    finally:
        clear_trace_id()


# =============================================================================
# TIER 4: DEEP INTEL TOOLS (Slow - 60-900s, Background Tasks)
# =============================================================================

@mcp.tool()
async def hybridrag_multihop_query(
    query: str,
    max_steps: int = 8,
    verbose: bool = False,
    context_seeds: Optional[List[str]] = None,
    ctx: Context = None
) -> str:
    """
    [SPEED: SLOW] [TIER: 4] [MAX_TIMEOUT: 900s (15 min)]

    Execute MULTI-STEP agentic reasoning for COMPLEX analytical queries.

    **RUNS AS BACKGROUND TASK** - Returns task ID immediately, poll for results.

    USE FOR: Complex reasoning that CANNOT be answered in single retrieval.
    STRATEGY: LAST RESORT. Use ONLY when Tier 2-3 tools fail.
              Provide 'context_seeds' from previous queries to speed up.
              RUNS AS BACKGROUND TASK - expect 2-15 minutes.

    Examples:
        - "Compare the old RAF pipeline with the new one"
        - "Trace data flow from Elation to Snowflake final tables"
        - "How do A, B, and C all relate to each other?"
        - "What's the impact of changing table X on downstream reports?"

    HOW IT WORKS (different from other tools):
        1. AI agent analyzes query complexity
        2. Agent plans and executes MULTIPLE sub-queries (local, global, hybrid)
        3. Agent accumulates context across steps
        4. Agent synthesizes comprehensive answer

    PERFORMANCE TIP - CASCADING STRATEGY:
        1. Run local_query first with top_k=3-5
        2. Extract entity names from the result
        3. Pass those as context_seeds to multihop_query
        This skips exploratory phase and focuses on relevant data.

    Args:
        query: Complex analytical question requiring multi-step reasoning
        max_steps: Max reasoning iterations (2-10, default: 8)
        verbose: Include step-by-step reasoning trace in output
        context_seeds: Entity names from previous queries to focus the search.
                      Use results from local_query or extract_context to populate this.

    Returns:
        Synthesized answer from multi-hop reasoning with execution metadata
    """
    trace_id = set_trace_id()

    try:
        logger.info(
            "=== MULTIHOP QUERY START ===",
            extra={"category": "query", "trace_id": trace_id}
        )
        logger.info(
            f"Query: {query[:200]}...",
            extra={"category": "query", "trace_id": trace_id, "metadata": {"mode": "multihop", "max_steps": max_steps}}
        )
        logger.info(
            f"Max steps: {max_steps}, Verbose: {verbose}",
            extra={"category": "query", "trace_id": trace_id}
        )
        logger.info(
            f"Context seeds: {context_seeds}",
            extra={"category": "query", "trace_id": trace_id}
        )
        logger.info(f"Log file: {LOG_FILE}", extra={"category": "system", "trace_id": trace_id})

        # Report progress
        if ctx:
            await ctx.report_progress(0, 100, "Initializing multi-hop reasoning...")

        core = await get_lightrag_core()
        logger.info("LightRAG core initialized", extra={"category": "init", "trace_id": trace_id})

        if ctx:
            await ctx.report_progress(10, 100, "Loading agentic RAG module...")

        # Import agentic RAG module
        try:
            from src.agentic_rag import create_agentic_rag
            logger.info(
                "Agentic RAG module imported successfully",
                extra={"category": "init", "trace_id": trace_id}
            )
        except ImportError as e:
            logger.error(
                f"Failed to import agentic_rag: {e}",
                extra={"category": "error", "trace_id": trace_id}
            )
            return f"Error: Multi-hop reasoning requires PromptChain. Install with: pip install git+https://github.com/gyasis/PromptChain.git\n\nImport error: {e}\n\n_Trace ID: {trace_id}_"

        # Create agentic RAG instance
        model_name = MODEL_OVERRIDE or "azure/gpt-4o"
        logger.info(
            f"Creating agentic RAG with model: {model_name}",
            extra={"category": "llm", "trace_id": trace_id}
        )

        if ctx:
            await ctx.report_progress(20, 100, f"Creating agent with {model_name}...")

        agentic = create_agentic_rag(
            lightrag_core=core,
            model_name=model_name,
            max_internal_steps=max_steps,
            verbose=verbose
        )
        logger.info("Agentic RAG instance created", extra={"category": "init", "trace_id": trace_id})

        # Build enhanced query with context seeds if provided
        enhanced_query = query
        if context_seeds:
            seed_context = f"\n\nFOCUS ON THESE ENTITIES (from previous queries): {', '.join(context_seeds)}"
            enhanced_query = query + seed_context
            logger.info(
                f"Enhanced query with {len(context_seeds)} context seeds",
                extra={"category": "query", "trace_id": trace_id, "metadata": {"seed_count": len(context_seeds)}}
            )

        if ctx:
            await ctx.report_progress(30, 100, "Starting multi-hop reasoning...")

        # Execute multi-hop reasoning with 15-minute timeout
        logger.info(
            "Starting multi-hop reasoning execution...",
            extra={"category": "query", "trace_id": trace_id}
        )
        start_time = datetime.now()

        try:
            result = await agentic.execute_multi_hop_reasoning(
                query=enhanced_query,
                timeout_seconds=DEFAULT_TIMEOUT_SECONDS  # 15 minutes
            )
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info(
                f"Multi-hop reasoning completed in {elapsed:.2f}s",
                extra={"category": "query", "trace_id": trace_id, "metadata": {"duration_sec": elapsed}}
            )
        except asyncio.CancelledError:
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.warning(
                f"Multi-hop query cancelled after {elapsed:.2f}s",
                extra={"category": "error", "trace_id": trace_id}
            )
            return f"Query was cancelled. Multi-hop reasoning takes time (2-15 minutes). Please try again or use a simpler query mode (hybrid, local, global) for faster results.\n\n_Trace ID: {trace_id}_"

        if ctx:
            await ctx.report_progress(90, 100, "Formatting final response...")

        # Format response - agentic_rag returns 'result' key, not 'answer'
        response = result.get('result') or result.get('answer', 'No answer generated')
        logger.info(
            f"Response generated, length: {len(response)} chars",
            extra={"category": "query", "trace_id": trace_id}
        )

        if verbose and 'reasoning_trace' in result:
            response += f"\n\n---\n**Reasoning Trace:**\n{result['reasoning_trace']}"

        response += f"\n\n---\n_Mode: multihop | Tier: 4 | Steps: {result.get('steps_taken', 'unknown')} | Time: {result.get('execution_time', 0):.2f}s | Trace: {trace_id}_"
        if context_seeds:
            response += f"\n_Used context seeds: {context_seeds}_"

        logger.info(
            "=== MULTIHOP QUERY COMPLETE ===",
            extra={"category": "query", "trace_id": trace_id}
        )
        logger.info(
            f"Steps taken: {result.get('steps_taken', 'unknown')}",
            extra={"category": "query", "trace_id": trace_id}
        )
        logger.info(
            f"Execution time: {result.get('execution_time', 0):.2f}s",
            extra={"category": "query", "trace_id": trace_id}
        )

        if ctx:
            await ctx.report_progress(100, 100, "Complete")

        return response

    except asyncio.CancelledError:
        logger.warning(
            "Multi-hop query cancelled during setup",
            extra={"category": "error", "trace_id": trace_id}
        )
        return f"Query was cancelled during initialization. Multi-hop reasoning requires more time. Try using hybrid mode for faster results.\n\n_Trace ID: {trace_id}_"
    except Exception as e:
        logger.error(
            f"Multi-hop query error: {type(e).__name__}: {e}",
            extra={"category": "error", "trace_id": trace_id},
            exc_info=True
        )
        return f"Error executing multi-hop query: {str(e)}\n\n_Trace ID: {trace_id}_"
    finally:
        clear_trace_id()


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def main():
    """Run the MCP server."""
    logger.info("Starting HybridRAG MCP Server (Optimized)")
    logger.info(f"Database: {DATABASE_PATH}")
    logger.info(f"Temp log directory: {TEMP_LOG_DIR}")
    logger.info(f"Log file: {LOG_FILE}")
    logger.info(f"Default timeout: {DEFAULT_TIMEOUT_SECONDS}s (15 minutes)")
    if MODEL_OVERRIDE:
        logger.info(f"Model override: {MODEL_OVERRIDE}")
    if EMBED_MODEL_OVERRIDE:
        logger.info(f"Embedding model override: {EMBED_MODEL_OVERRIDE}")

    logger.info("=== TIERED TOOL ARCHITECTURE ===")
    logger.info("T1 Recon (instant): database_status, health_check, get_logs")
    logger.info("T2 Tactical (fast): local_query, extract_context")
    logger.info("T3 Strategic (medium): global_query, hybrid_query, query")
    logger.info("T4 Deep Intel (slow): multihop_query")
    logger.info("================================")

    # Check transport mode from environment
    transport = os.environ.get("MCP_TRANSPORT", "stdio").lower()
    port = int(os.environ.get("MCP_PORT", "8766"))

    if transport == "sse" or transport == "http":
        # SSE/HTTP transport - more robust for long-running tasks
        # Fixes stdio buffer hang issues with async operations
        logger.info(f"Starting MCP server with SSE transport on port {port}")
        logger.info("SSE transport is more robust for long-running queries")
        mcp.run(transport="sse", port=port)
    else:
        # Default stdio transport (for Claude Code subprocess mode)
        logger.info("Starting MCP server with stdio transport")
        logger.info("Note: If queries hang, try SSE transport: MCP_TRANSPORT=sse")
        mcp.run()


if __name__ == "__main__":
    main()
