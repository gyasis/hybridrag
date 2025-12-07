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
from pathlib import Path
from typing import Dict, List, Optional, Literal, Union, Any
from dataclasses import dataclass
from lightrag import LightRAG, QueryParam
from lightrag.utils import EmbeddingFunc
import litellm
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

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

class HybridLightRAGCore:
    """
    Core LightRAG interface for hybrid RAG system.
    Implements validated QueryParam patterns.
    """
    
    def __init__(self, config):
        """
        Initialize Hybrid LightRAG Core.
        
        Args:
            config: HybridRAGConfig instance
        """
        self.config = config.lightrag
        self._setup_api_key()
        self._ensure_working_dir()
        self._init_lightrag()
        self.rag_initialized = False
        self.context_cache: Dict[str, str] = {}
        
        logger.info(f"HybridLightRAGCore initialized with working dir: {self.config.working_dir}")
    
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
        """Initialize LightRAG instance with LiteLLM for provider-agnostic access."""
        logger.info("Initializing LightRAG instance with LiteLLM")

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
            """LiteLLM-based completion function for Azure/OpenAI/Anthropic/etc."""
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

            try:
                # Build LiteLLM call kwargs
                litellm_kwargs = {
                    "model": self.config.model_name,
                    "messages": messages,
                    "api_key": self.api_key,
                    **filtered_kwargs
                }

                # Add Azure-specific parameters if using Azure
                if self.is_azure and self.azure_api_base:
                    litellm_kwargs["api_base"] = self.azure_api_base
                    litellm_kwargs["api_version"] = self.azure_api_version

                # Use LiteLLM for provider-agnostic completion
                response = await litellm.acompletion(**litellm_kwargs)
                return response.choices[0].message.content
            except Exception as e:
                logger.error(f"LiteLLM completion error: {e}")
                raise

        # Embedding function using LiteLLM for provider-agnostic embeddings
        async def embedding_func(texts: List[str]) -> List[List[float]]:
            """LiteLLM-based embedding function for Azure/OpenAI/etc."""
            try:
                # Build LiteLLM embedding call kwargs
                litellm_kwargs = {
                    "model": self.config.embedding_model,
                    "input": texts,
                    "api_key": self.api_key
                }

                # Add Azure-specific parameters if embedding model uses Azure
                if self.config.embedding_model.startswith("azure/") and self.azure_api_base:
                    litellm_kwargs["api_base"] = self.azure_api_base
                    litellm_kwargs["api_version"] = self.azure_api_version

                response = await litellm.aembedding(**litellm_kwargs)
                return [item["embedding"] for item in response.data]
            except Exception as e:
                logger.error(f"LiteLLM embedding error: {e}")
                raise

        # Initialize LightRAG with LiteLLM functions
        self.rag = LightRAG(
            working_dir=self.config.working_dir,
            llm_model_func=llm_model_func,
            llm_model_max_async=self.config.max_async,
            embedding_func=EmbeddingFunc(
                embedding_dim=self.config.embedding_dim,
                func=embedding_func
            )
        )
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

def create_lightrag_core(config) -> HybridLightRAGCore:
    """
    Factory function to create HybridLightRAGCore instance.
    
    Args:
        config: HybridRAGConfig instance
        
    Returns:
        HybridLightRAGCore instance
    """
    return HybridLightRAGCore(config)