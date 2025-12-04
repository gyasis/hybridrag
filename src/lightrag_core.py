#!/usr/bin/env python3
"""
LightRAG Core Module
===================
Core LightRAG functionality for the hybrid RAG system.
Based on athena-lightrag patterns.
"""

import os
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Optional, Literal, Union, Any
from dataclasses import dataclass
from lightrag import LightRAG, QueryParam
from lightrag.llm.openai import openai_complete_if_cache, openai_embed
from lightrag.utils import EmbeddingFunc
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
        """Setup OpenAI API key from config or environment."""
        self.api_key = self.config.api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenAI API key not found. Set OPENAI_API_KEY environment variable "
                "or provide it in configuration."
            )
        # Ensure the API key is set in environment
        os.environ['OPENAI_API_KEY'] = self.api_key
    
    def _ensure_working_dir(self):
        """Ensure working directory exists."""
        working_dir = Path(self.config.working_dir)
        working_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Working directory ready: {working_dir}")
    
    def _init_lightrag(self):
        """Initialize LightRAG instance with validated patterns."""
        logger.info("Initializing LightRAG instance")
        
        # LLM model function using validated openai_complete_if_cache pattern
        def llm_model_func(
            prompt: str, 
            system_prompt: Optional[str] = None, 
            history_messages: Optional[List[Dict[str, str]]] = None,
            **kwargs
        ) -> str:
            # Filter out None values and unsupported parameters
            call_kwargs = {
                "model": self.config.model_name,
                "prompt": prompt,
                "api_key": self.api_key
            }
            
            if system_prompt:
                call_kwargs["system_prompt"] = system_prompt
                
            # Only pass history_messages if it's not None and not empty
            if history_messages:
                call_kwargs["history_messages"] = history_messages
                
            # Add any other supported kwargs
            for key, value in kwargs.items():
                if key not in ['history_messages'] and value is not None:
                    call_kwargs[key] = value
            
            return openai_complete_if_cache(**call_kwargs)
        
        # Embedding function using validated openai_embed pattern
        def embedding_func(texts: List[str]) -> List[List[float]]:
            return openai_embed(
                texts=texts,
                model=self.config.embedding_model,
                api_key=self.api_key
            )
        
        # Initialize LightRAG with validated configuration
        self.rag = LightRAG(
            working_dir=self.config.working_dir,
            llm_model_func=llm_model_func,
            llm_model_max_async=self.config.max_async,
            embedding_func=EmbeddingFunc(
                embedding_dim=self.config.embedding_dim,
                func=embedding_func
            )
        )
        logger.info("LightRAG initialized successfully")
    
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
    
    async def ainsert(self, content: str) -> bool:
        """
        Insert content into LightRAG knowledge graph.
        
        Args:
            content: Text content to insert
            
        Returns:
            True if successful, False otherwise
        """
        try:
            await self._ensure_initialized()
            await self.rag.ainsert(content)
            logger.info(f"Successfully inserted content ({len(content)} chars)")
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
            storage_info = {}
            for file_path in graph_files:
                try:
                    size = file_path.stat().st_size
                    storage_info[file_path.name] = f"{size / 1024:.1f} KB"
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