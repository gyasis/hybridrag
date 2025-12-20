#!/usr/bin/env python3
"""
LightRAG Core Module
===================
Core LightRAG functionality for the hybrid RAG system.
Based on athena-lightrag patterns.
Uses LiteLLM for provider-agnostic model access (Azure, OpenAI, Anthropic, etc.)
"""

import os
import asyncio
import logging
import random
import re
from collections import OrderedDict
from pathlib import Path
from typing import Dict, List, Optional, Literal, Union, Any, Set, Type
from dataclasses import dataclass
from lightrag import LightRAG, QueryParam
from lightrag.utils import EmbeddingFunc
import litellm
from dotenv import load_dotenv

# Import backend configuration
from src.config.config import BackendType, BackendConfig

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# =============================================================================
# LiteLLM Retry Configuration
# =============================================================================

# Default timeout for LiteLLM API calls (seconds)
LITELLM_DEFAULT_TIMEOUT = 60

# Retry configuration
LITELLM_MAX_RETRIES = 4  # Increased for Azure rate limits
LITELLM_INITIAL_BACKOFF = 2.0  # seconds (increased from 1.0)
LITELLM_MAX_BACKOFF = 60.0  # seconds (increased from 30.0)
LITELLM_BACKOFF_MULTIPLIER = 2.0
LITELLM_JITTER_FACTOR = 0.25  # 25% jitter


def extract_retry_after(exception: Exception) -> Optional[float]:
    """
    Extract 'retry after X seconds' from Azure/OpenAI rate limit errors.

    Azure errors contain: "Please retry after 13 seconds"
    OpenAI errors contain: "Retry-After: 20" header info

    Returns:
        Retry delay in seconds, or None if not found
    """
    error_str = str(exception)

    # Pattern: "retry after X seconds" (Azure style)
    match = re.search(r'retry after (\d+(?:\.\d+)?)\s*(?:second|sec|s)', error_str, re.IGNORECASE)
    if match:
        return float(match.group(1))

    # Pattern: "Retry-After: X" (header style)
    match = re.search(r'Retry-After[:\s]+(\d+(?:\.\d+)?)', error_str, re.IGNORECASE)
    if match:
        return float(match.group(1))

    # Pattern: just "X seconds" after rate limit mention
    if 'rate' in error_str.lower() and 'limit' in error_str.lower():
        match = re.search(r'(\d+(?:\.\d+)?)\s*(?:second|sec|s)', error_str, re.IGNORECASE)
        if match:
            return float(match.group(1))

    return None

# HTTP status codes that are considered transient and should be retried
TRANSIENT_HTTP_STATUS_CODES: Set[int] = {429, 500, 502, 503, 504}

# Non-retryable HTTP status codes (auth errors, bad requests)
NON_RETRYABLE_HTTP_STATUS_CODES: Set[int] = {400, 401, 403, 404, 422}


def is_transient_error(exception: Exception) -> bool:
    """
    Determine if an exception is transient and should be retried.

    Args:
        exception: The exception to check

    Returns:
        True if the error is transient and retryable, False otherwise
    """
    error_str = str(exception).lower()
    error_type = type(exception).__name__

    # Check for specific LiteLLM exception types
    # RateLimitError, ServiceUnavailableError, Timeout, APIConnectionError are retryable
    transient_exception_patterns = [
        'ratelimit', 'rate_limit', 'rate limit',
        'timeout', 'timed out',
        'connection', 'connectionerror',
        'serviceunavailable', 'service_unavailable', 'service unavailable',
        '429', '500', '502', '503', '504',
        'temporarily unavailable',
        'too many requests',
        'server error',
        'internal server error',
        'bad gateway',
        'gateway timeout',
        'overloaded',
    ]

    # Non-retryable patterns (auth errors, bad requests)
    non_retryable_patterns = [
        'authentication', 'unauthorized', '401',
        'forbidden', '403',
        'invalid_api_key', 'invalid api key',
        'bad request', '400',
        'not found', '404',
        'invalid_request', 'invalid request',
        'malformed',
        'validation error', '422',
    ]

    # Check non-retryable patterns first
    for pattern in non_retryable_patterns:
        if pattern in error_str or pattern in error_type.lower():
            return False

    # Check for transient patterns
    for pattern in transient_exception_patterns:
        if pattern in error_str or pattern in error_type.lower():
            return True

    # Default: don't retry unknown errors
    return False


def calculate_backoff_with_jitter(
    attempt: int,
    initial_backoff: float = LITELLM_INITIAL_BACKOFF,
    max_backoff: float = LITELLM_MAX_BACKOFF,
    multiplier: float = LITELLM_BACKOFF_MULTIPLIER,
    jitter_factor: float = LITELLM_JITTER_FACTOR
) -> float:
    """
    Calculate exponential backoff with jitter.

    Args:
        attempt: Current retry attempt (0-indexed)
        initial_backoff: Initial backoff in seconds
        max_backoff: Maximum backoff in seconds
        multiplier: Backoff multiplier
        jitter_factor: Random jitter factor (0.0 to 1.0)

    Returns:
        Backoff duration in seconds
    """
    # Exponential backoff
    backoff = initial_backoff * (multiplier ** attempt)

    # Cap at max backoff
    backoff = min(backoff, max_backoff)

    # Add jitter: backoff * (1 +/- jitter_factor * random)
    jitter = backoff * jitter_factor * (2 * random.random() - 1)
    backoff = max(0.1, backoff + jitter)  # Ensure minimum 100ms

    return backoff


async def retry_with_backoff(
    func,
    *args,
    max_retries: int = LITELLM_MAX_RETRIES,
    operation_name: str = "LiteLLM call",
    **kwargs
):
    """
    Execute an async function with exponential backoff retry for transient errors.

    Args:
        func: Async function to execute
        *args: Positional arguments for func
        max_retries: Maximum number of retry attempts
        operation_name: Name for logging
        **kwargs: Keyword arguments for func

    Returns:
        Result from successful function call

    Raises:
        Exception: If all retries fail or error is non-retryable
    """
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exception = e

            # Check if error is retryable
            if not is_transient_error(e):
                logger.error(f"{operation_name} failed with non-retryable error: {e}")
                raise

            # Check if we have retries left
            if attempt >= max_retries:
                logger.error(
                    f"{operation_name} failed after {max_retries + 1} attempts. "
                    f"Last error: {e}"
                )
                raise

            # Calculate backoff - respect server's retry-after AND compound on repeated failures
            calculated_backoff = calculate_backoff_with_jitter(attempt)
            retry_after = extract_retry_after(e)

            if retry_after is not None:
                # Compound backoff: server's retry-after * (1 + 0.5 * attempt)
                # Attempt 0: retry-after * 1.0 + buffer
                # Attempt 1: retry-after * 1.5 + buffer
                # Attempt 2: retry-after * 2.0 + buffer
                # Attempt 3: retry-after * 2.5 + buffer
                compound_multiplier = 1.0 + (0.5 * attempt)
                base_wait = retry_after * compound_multiplier
                # Use max of server wait or our exponential backoff
                backoff = max(base_wait, calculated_backoff) + 1.0
                # Cap at max backoff
                backoff = min(backoff, LITELLM_MAX_BACKOFF)
                logger.warning(
                    f"{operation_name} rate limited (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                    f"Server requested {retry_after}s. Compounding to {backoff:.1f}s..."
                )
            else:
                backoff = calculated_backoff
                logger.warning(
                    f"{operation_name} transient error (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                    f"Retrying in {backoff:.2f}s..."
                )

            await asyncio.sleep(backoff)

    # Should not reach here, but raise last exception if we do
    raise last_exception

# Type definitions
QueryMode = Literal["local", "global", "hybrid", "naive", "mix"]
ResponseType = Literal["Multiple Paragraphs", "Single Paragraph", "Bullet Points"]

@dataclass
class QueryResult:
    """Structured result from LightRAG query."""
    result: str
    mode: QueryMode
    context_only: bool
    tokens_used: Dict[str, int]
    execution_time: float
    error: Optional[str] = None

class LRUCache:
    """
    Simple LRU (Least Recently Used) cache with max size limit.

    Uses OrderedDict to maintain insertion order and evict oldest items
    when capacity is exceeded.
    """

    def __init__(self, max_size: int = 1000):
        """
        Initialize LRU cache.

        Args:
            max_size: Maximum number of items to store (default 1000)
        """
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._max_size = max_size

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get item from cache, moving it to end (most recently used)."""
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return default

    def set(self, key: str, value: str) -> None:
        """Set item in cache, evicting oldest if at capacity."""
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            if len(self._cache) >= self._max_size:
                # Evict oldest item (first item in OrderedDict)
                self._cache.popitem(last=False)
        self._cache[key] = value

    def __contains__(self, key: str) -> bool:
        return key in self._cache

    def __len__(self) -> int:
        return len(self._cache)

    def clear(self) -> None:
        """Clear all items from cache."""
        self._cache.clear()


class HybridLightRAGCore:
    """
    Core LightRAG interface for hybrid RAG system.
    Implements validated QueryParam patterns.
    """

    # Default max cache size for context cache
    DEFAULT_CACHE_MAX_SIZE = 1000

    def __init__(
        self,
        config,
        cache_max_size: int = DEFAULT_CACHE_MAX_SIZE,
        backend_config: Optional[BackendConfig] = None
    ):
        """
        Initialize Hybrid LightRAG Core.

        Args:
            config: HybridRAGConfig instance
            cache_max_size: Maximum size for context cache (default 1000)
            backend_config: Optional storage backend configuration. If None,
                           uses default JSON backend (NanoVectorDB + NetworkX).
                           Pass BackendConfig(backend_type=BackendType.POSTGRESQL, ...)
                           to use PostgreSQL with pgvector.
        """
        self.config = config.lightrag
        # Store backend configuration (default to JSON backend if not provided)
        self.backend_config = backend_config or BackendConfig()
        self._setup_api_key()
        self._ensure_working_dir()
        self._init_lightrag()
        self.rag_initialized = False
        # Use LRU cache with bounded size to prevent memory leaks
        self.context_cache = LRUCache(max_size=cache_max_size)

        backend_info = f", backend: {self.backend_config.backend_type.value}"
        logger.info(f"HybridLightRAGCore initialized with working dir: {self.config.working_dir}{backend_info}")
    
    def _setup_api_key(self):
        """Setup API key and configure LiteLLM for Azure/OpenAI."""
        # Get API key from config or environment
        self.api_key = self.config.api_key or os.getenv("AZURE_API_KEY") or os.getenv("AZURE_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "API key not found. Set AZURE_API_KEY, AZURE_OPENAI_API_KEY, or OPENAI_API_KEY "
                "environment variable or provide it in configuration."
            )

        # Detect if using Azure based on model name or environment
        self.is_azure = (
            self.config.model_name.startswith("azure/") or
            self.config.embedding_model.startswith("azure/") or
            os.getenv("AZURE_API_BASE") is not None or
            os.getenv("AZURE_OPENAI_ENDPOINT") is not None
        )

        # Store Azure-specific configuration for LiteLLM calls
        # Priority: AZURE_API_BASE > AZURE_OPENAI_ENDPOINT
        self.azure_api_base = os.getenv("AZURE_API_BASE") or os.getenv("AZURE_OPENAI_ENDPOINT")
        self.azure_api_version = os.getenv("AZURE_API_VERSION", "2024-02-01")

        # Configure LiteLLM for Azure if needed
        if self.is_azure:
            if self.azure_api_base:
                # Set LiteLLM Azure configuration via environment
                os.environ['AZURE_API_KEY'] = self.api_key
                os.environ['AZURE_API_BASE'] = self.azure_api_base
                os.environ['AZURE_API_VERSION'] = self.azure_api_version
                logger.info(f"Configured LiteLLM for Azure OpenAI: {self.azure_api_base} (version: {self.azure_api_version})")
            else:
                logger.warning("Azure model detected but no AZURE_API_BASE or AZURE_OPENAI_ENDPOINT set")
        else:
            # Only set OPENAI_API_KEY for non-Azure configurations
            os.environ['OPENAI_API_KEY'] = self.api_key
    
    def _ensure_working_dir(self):
        """Ensure working directory exists."""
        working_dir = Path(self.config.working_dir)
        working_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Working directory ready: {working_dir}")
    
    def _init_lightrag(self):
        """Initialize LightRAG instance with LiteLLM for provider-agnostic access.

        Uses backend_config to determine storage classes:
        - JSON backend (default): JsonKVStorage, NanoVectorDBStorage, NetworkXStorage
        - PostgreSQL backend: PGKVStorage, PGVectorStorage, PGGraphStorage
        """
        backend_type = self.backend_config.backend_type.value
        logger.info(f"Initializing LightRAG instance with LiteLLM (backend: {backend_type})")

        # Known LiteLLM-compatible kwargs (filter out LightRAG internal objects)
        LITELLM_ALLOWED_KWARGS = {
            'temperature', 'top_p', 'max_tokens', 'n', 'stream', 'stop',
            'presence_penalty', 'frequency_penalty', 'logit_bias', 'user',
            'response_format', 'seed', 'tools', 'tool_choice', 'timeout'
        }

        # LLM model function using LiteLLM for provider-agnostic access
        async def llm_model_func(
            prompt: str,
            system_prompt: Optional[str] = None,
            history_messages: Optional[List[Dict[str, str]]] = None,
            **kwargs
        ) -> str:
            """
            LiteLLM-based completion function for Azure/OpenAI/Anthropic/etc.

            Features:
                - Explicit timeout to prevent indefinite hangs
                - Exponential backoff with jitter for transient errors
                - Smart retry logic (only retries 429, 5xx; not 401, 400)
            """
            messages = []

            # Add system prompt if provided
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})

            # Add history messages if provided
            if history_messages:
                messages.extend(history_messages)

            # Add the user prompt
            messages.append({"role": "user", "content": prompt})

            # Filter kwargs to only include LiteLLM-compatible parameters
            # This excludes LightRAG internal objects like JsonKVStorage
            filtered_kwargs = {
                k: v for k, v in kwargs.items()
                if k in LITELLM_ALLOWED_KWARGS and v is not None
            }

            # Build LiteLLM call kwargs
            litellm_kwargs = {
                "model": self.config.model_name,
                "messages": messages,
                "api_key": self.api_key,
                # Set explicit timeout to prevent indefinite hangs
                "timeout": filtered_kwargs.pop("timeout", LITELLM_DEFAULT_TIMEOUT),
                **filtered_kwargs
            }

            # Add Azure-specific parameters if using Azure
            if self.is_azure and self.azure_api_base:
                litellm_kwargs["api_base"] = self.azure_api_base
                litellm_kwargs["api_version"] = self.azure_api_version

            # Inner function for retry wrapper
            async def _do_completion():
                response = await litellm.acompletion(**litellm_kwargs)
                return response.choices[0].message.content

            # Execute with retry logic for transient errors
            return await retry_with_backoff(
                _do_completion,
                max_retries=LITELLM_MAX_RETRIES,
                operation_name="LiteLLM completion"
            )

        # Embedding function using LiteLLM for provider-agnostic embeddings
        async def embedding_func(texts: List[str]) -> List[List[float]]:
            """
            LiteLLM-based embedding function for Azure/OpenAI/etc.

            Features:
                - Explicit timeout to prevent indefinite hangs
                - Exponential backoff with jitter for transient errors
                - Smart retry logic (only retries 429, 5xx; not 401, 400)
            """
            # Build LiteLLM embedding call kwargs
            litellm_kwargs = {
                "model": self.config.embedding_model,
                "input": texts,
                "api_key": self.api_key,
                # Set explicit timeout to prevent indefinite hangs
                "timeout": LITELLM_DEFAULT_TIMEOUT
            }

            # Add Azure-specific parameters if embedding model uses Azure
            if self.config.embedding_model.startswith("azure/") and self.azure_api_base:
                litellm_kwargs["api_base"] = self.azure_api_base
                litellm_kwargs["api_version"] = self.azure_api_version

            # Inner function for retry wrapper
            async def _do_embedding():
                response = await litellm.aembedding(**litellm_kwargs)
                return [item["embedding"] for item in response.data]

            # Execute with retry logic for transient errors
            return await retry_with_backoff(
                _do_embedding,
                max_retries=LITELLM_MAX_RETRIES,
                operation_name="LiteLLM embedding"
            )

        # Build LightRAG initialization kwargs
        lightrag_kwargs = {
            "working_dir": self.config.working_dir,
            "llm_model_func": llm_model_func,
            "llm_model_max_async": self.config.max_async,
            "embedding_func": EmbeddingFunc(
                embedding_dim=self.config.embedding_dim,
                func=embedding_func
            )
        }

        # Configure storage backends based on backend_config
        if self.backend_config.backend_type == BackendType.POSTGRESQL:
            # PostgreSQL backend with pgvector
            storage_classes = self.backend_config.get_storage_classes()
            lightrag_kwargs.update({
                "kv_storage": storage_classes["kv_storage"],
                "vector_storage": storage_classes["vector_storage"],
                "graph_storage": storage_classes["graph_storage"],
                "doc_status_storage": storage_classes["doc_status_storage"],
            })

            # Set PostgreSQL environment variables for LightRAG's storage classes
            env_vars = self.backend_config.get_env_vars()
            for key, value in env_vars.items():
                os.environ[key] = value

            logger.info(
                f"Configured PostgreSQL backend: "
                f"{self.backend_config.postgres_host}:{self.backend_config.postgres_port}/"
                f"{self.backend_config.postgres_database}"
            )
        elif self.backend_config.backend_type == BackendType.JSON:
            # JSON backend (default) - uses LightRAG defaults
            logger.info("Using default JSON backend (NanoVectorDB + NetworkX)")
        else:
            # Future backends (MongoDB, etc.)
            logger.warning(
                f"Backend type '{self.backend_config.backend_type.value}' not yet implemented. "
                f"Falling back to JSON backend."
            )

        # Initialize LightRAG with configured backends
        self.rag = LightRAG(**lightrag_kwargs)
        logger.info(f"LightRAG initialized with LiteLLM (model: {self.config.model_name})")
    
    async def _ensure_initialized(self):
        """Ensure LightRAG storages are initialized."""
        if not self.rag_initialized:
            logger.info("Initializing LightRAG storages for first query...")
            await self.rag.initialize_storages()
            
            # Import and call initialize_pipeline_status for fresh database
            try:
                from lightrag.kg.shared_storage import initialize_pipeline_status
                await initialize_pipeline_status()
                logger.info("LightRAG pipeline status initialized successfully")
            except ImportError:
                # Try alternative import path
                try:
                    from lightrag.utils.pipeline_utils import initialize_pipeline_status
                    await initialize_pipeline_status()
                    logger.info("LightRAG pipeline status initialized successfully")
                except ImportError as e:
                    logger.warning(f"Could not import initialize_pipeline_status: {e}")
            
            self.rag_initialized = True
            logger.info("LightRAG storages and pipeline initialized successfully")
    
    async def ainsert(self, content: str, file_path: str = None) -> bool:
        """
        Insert content into LightRAG knowledge graph.

        Args:
            content: Text content to insert
            file_path: Source file path for citation/tracking (optional)

        Returns:
            True if successful, False otherwise
        """
        try:
            await self._ensure_initialized()
            # Pass file_paths to LightRAG for proper source tracking
            await self.rag.ainsert(content, file_paths=file_path)
            source_info = f" from {file_path}" if file_path else ""
            logger.info(f"Successfully inserted content ({len(content)} chars){source_info}")
            return True
        except Exception as e:
            logger.error(f"Error inserting content: {e}")
            return False
    
    async def aquery(
        self,
        query: str,
        mode: QueryMode = "hybrid",
        only_need_context: bool = False,
        response_type: ResponseType = "Multiple Paragraphs",
        top_k: int = 10,
        max_entity_tokens: int = 6000,
        max_relation_tokens: int = 8000,
        **kwargs
    ) -> QueryResult:
        """
        Query LightRAG with structured parameters.
        
        Args:
            query: Search query
            mode: Query mode (local, global, hybrid, naive, mix)
            only_need_context: Return only context without generation
            response_type: Type of response format
            top_k: Number of top results
            max_entity_tokens: Maximum tokens for entity context
            max_relation_tokens: Maximum tokens for relation context
            **kwargs: Additional parameters
            
        Returns:
            QueryResult with response and metadata
        """
        import time
        start_time = time.time()
        
        try:
            await self._ensure_initialized()
            
            # Create QueryParam with validated configuration
            query_param = QueryParam(
                mode=mode,
                only_need_context=only_need_context,
                response_type=response_type,
                top_k=top_k,
                max_entity_tokens=max_entity_tokens,
                max_relation_tokens=max_relation_tokens,
                **kwargs
            )
            
            # Execute query
            result = await self.rag.aquery(query, param=query_param)
            
            execution_time = time.time() - start_time
            
            # TODO: Implement token counting
            tokens_used = {"total": 0, "prompt": 0, "completion": 0}
            
            logger.info(f"Query completed in {execution_time:.2f}s, mode: {mode}")
            
            return QueryResult(
                result=result,
                mode=mode,
                context_only=only_need_context,
                tokens_used=tokens_used,
                execution_time=execution_time
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"Query failed: {str(e)}"
            logger.error(error_msg)
            
            return QueryResult(
                result="",
                mode=mode,
                context_only=only_need_context,
                tokens_used={"total": 0, "prompt": 0, "completion": 0},
                execution_time=execution_time,
                error=error_msg
            )
    
    async def local_query(
        self,
        query: str,
        top_k: int = 10,
        max_entity_tokens: int = 6000,
        **kwargs
    ) -> QueryResult:
        """Query LightRAG in local mode for specific entity relationships."""
        return await self.aquery(
            query=query,
            mode="local",
            top_k=top_k,
            max_entity_tokens=max_entity_tokens,
            **kwargs
        )
    
    async def global_query(
        self,
        query: str,
        top_k: int = 10,
        max_relation_tokens: int = 8000,
        **kwargs
    ) -> QueryResult:
        """Query LightRAG in global mode for high-level overviews."""
        return await self.aquery(
            query=query,
            mode="global",
            top_k=top_k,
            max_relation_tokens=max_relation_tokens,
            **kwargs
        )
    
    async def hybrid_query(
        self,
        query: str,
        top_k: int = 10,
        max_entity_tokens: int = 6000,
        max_relation_tokens: int = 8000,
        **kwargs
    ) -> QueryResult:
        """Query LightRAG in hybrid mode combining local and global."""
        return await self.aquery(
            query=query,
            mode="hybrid",
            top_k=top_k,
            max_entity_tokens=max_entity_tokens,
            max_relation_tokens=max_relation_tokens,
            **kwargs
        )
    
    async def extract_context(
        self,
        query: str,
        mode: QueryMode = "hybrid",
        top_k: int = 10,
        **kwargs
    ) -> str:
        """Extract raw context without generating response."""
        result = await self.aquery(
            query=query,
            mode=mode,
            only_need_context=True,
            top_k=top_k,
            **kwargs
        )
        return result.result
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the LightRAG instance."""
        working_dir = Path(self.config.working_dir)
        
        stats = {
            "working_directory": str(working_dir),
            "initialized": self.rag_initialized,
            "model_name": self.config.model_name,
            "embedding_model": self.config.embedding_model,
            "cache_size": len(self.context_cache)
        }
        
        # Check for graph files
        if working_dir.exists():
            graph_files = list(working_dir.glob("*.json"))
            stats["graph_files"] = len(graph_files)
            
            # Get storage sizes
            from src.utils import format_file_size
            storage_info = {}
            for file_path in graph_files:
                try:
                    size = file_path.stat().st_size
                    storage_info[file_path.name] = format_file_size(size)
                except Exception:
                    storage_info[file_path.name] = "unknown"
            stats["storage_info"] = storage_info
        
        return stats
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on the LightRAG system."""
        health = {
            "status": "unknown",
            "checks": {}
        }
        
        try:
            # Check initialization
            await self._ensure_initialized()
            health["checks"]["initialization"] = "ok"
            
            # Test simple query
            test_query = "test health check query"
            result = await self.aquery(test_query, mode="local", top_k=1)
            if result.error:
                health["checks"]["query"] = f"failed: {result.error}"
            else:
                health["checks"]["query"] = "ok"
            
            # Check working directory
            working_dir = Path(self.config.working_dir)
            if working_dir.exists() and working_dir.is_dir():
                health["checks"]["working_directory"] = "ok"
            else:
                health["checks"]["working_directory"] = "missing"
            
            # Overall status
            if all(check == "ok" for check in health["checks"].values()):
                health["status"] = "healthy"
            else:
                health["status"] = "degraded"
                
        except Exception as e:
            health["status"] = "unhealthy"
            health["error"] = str(e)
        
        return health

def get_storage_classes(backend_type: Union[BackendType, str]) -> Dict[str, str]:
    """
    Factory function to get LightRAG storage class names for a backend type.

    Maps backend types to LightRAG's pluggable storage class names:
    - JSON: JsonKVStorage, NanoVectorDBStorage, NetworkXStorage, JsonDocStatusStorage
    - PostgreSQL: PGKVStorage, PGVectorStorage, PGGraphStorage, PGDocStatusStorage
    - MongoDB: MongoKVStorage, MongoVectorDBStorage, MongoGraphStorage, MongoDocStatusStorage

    Args:
        backend_type: BackendType enum or string ('json', 'postgres', 'mongodb')

    Returns:
        Dict mapping storage type to LightRAG class name:
        {
            "kv_storage": "JsonKVStorage",
            "vector_storage": "NanoVectorDBStorage",
            "graph_storage": "NetworkXStorage",
            "doc_status_storage": "JsonDocStatusStorage"
        }

    Example:
        >>> get_storage_classes("json")
        {'kv_storage': 'JsonKVStorage', ...}

        >>> get_storage_classes(BackendType.POSTGRESQL)
        {'kv_storage': 'PGKVStorage', ...}
    """
    # Convert string to BackendType if needed
    if isinstance(backend_type, str):
        backend_type = BackendType.from_string(backend_type)

    # Use BackendConfig's get_storage_classes for consistency
    config = BackendConfig(backend_type=backend_type)
    return config.get_storage_classes()


def create_lightrag_core(
    config,
    backend_config: Optional[BackendConfig] = None
) -> HybridLightRAGCore:
    """
    Factory function to create HybridLightRAGCore instance.

    Args:
        config: HybridRAGConfig instance
        backend_config: Optional storage backend configuration.
                       If None, uses default JSON backend.

    Returns:
        HybridLightRAGCore instance

    Example:
        # Default JSON backend
        core = create_lightrag_core(config)

        # PostgreSQL backend
        pg_config = BackendConfig(
            backend_type=BackendType.POSTGRESQL,
            postgres_host="localhost",
            postgres_port=5432,
            postgres_database="hybridrag",
            postgres_password="secret"
        )
        core = create_lightrag_core(config, backend_config=pg_config)
    """
    return HybridLightRAGCore(config, backend_config=backend_config)