#!/usr/bin/env python3
"""
Search Interface Module
=======================
Query interface for the hybrid RAG system with multi-hop reasoning.
Integrates with PromptChain AgenticStepProcessor for complex queries.
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from datetime import datetime
import json
import sys
import os

# Add promptchain to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

try:
    from promptchain.utils.agentic_step_processor import AgenticStepProcessor
    from promptchain import PromptChain
    PROMPTCHAIN_AVAILABLE = True
except ImportError:
    PROMPTCHAIN_AVAILABLE = False
    logging.warning("PromptChain not available - agentic features disabled")

from lightrag_core import QueryResult, QueryMode, ResponseType

logger = logging.getLogger(__name__)

@dataclass
class SearchResult:
    """Enhanced search result with metadata."""
    query: str
    result: str
    mode: QueryMode
    execution_time: float
    sources: List[str]
    confidence_score: float
    context_used: bool
    agentic_steps: Optional[List[Dict]] = None
    total_tokens: int = 0
    error: Optional[str] = None

@dataclass
class MultiHopContext:
    """Context accumulation for multi-hop reasoning."""
    initial_query: str
    contexts: List[Dict[str, Any]]
    reasoning_steps: List[str]
    final_synthesis: Optional[str] = None
    total_tokens_used: int = 0
    execution_time: float = 0.0

class SearchInterface:
    """
    Main search interface for the hybrid RAG system.
    Provides simple queries and complex multi-hop reasoning.
    """
    
    def __init__(self, config, lightrag_core):
        """
        Initialize search interface.
        
        Args:
            config: HybridRAGConfig instance
            lightrag_core: HybridLightRAGCore instance
        """
        self.config = config
        self.lightrag = lightrag_core
        self.search_config = config.search
        self.query_history: List[SearchResult] = []
        
        # Initialize agentic capabilities if available
        self.agentic_enabled = PROMPTCHAIN_AVAILABLE
        if self.agentic_enabled:
            self._init_agentic_tools()
        
        logger.info(f"SearchInterface initialized (agentic: {self.agentic_enabled})")
    
    def _init_agentic_tools(self):
        """Initialize agentic tools for multi-hop reasoning."""
        if not self.agentic_enabled:
            return
            
        self.lightrag_tools = [
            {
                "type": "function",
                "function": {
                    "name": "lightrag_local_query",
                    "description": "Query LightRAG in local mode for specific entity relationships and detailed information",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query for local context"
                            },
                            "top_k": {
                                "type": "integer",
                                "description": "Number of top entities to retrieve (default: 10)",
                                "default": 10
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function", 
                "function": {
                    "name": "lightrag_global_query",
                    "description": "Query LightRAG in global mode for high-level overviews and broad summaries",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query for global overview"
                            },
                            "max_relation_tokens": {
                                "type": "integer",
                                "description": "Maximum tokens for relationship context (default: 8000)",
                                "default": 8000
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "lightrag_hybrid_query", 
                    "description": "Query LightRAG in hybrid mode combining local entities and global relationships",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query for hybrid analysis"
                            },
                            "top_k": {
                                "type": "integer",
                                "description": "Number of top results (default: 10)",
                                "default": 10
                            },
                            "max_entity_tokens": {
                                "type": "integer", 
                                "description": "Maximum tokens for entity context (default: 6000)",
                                "default": 6000
                            },
                            "max_relation_tokens": {
                                "type": "integer",
                                "description": "Maximum tokens for relation context (default: 8000)", 
                                "default": 8000
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "lightrag_extract_context",
                    "description": "Extract raw context from LightRAG without generating a response",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query for context extraction"
                            },
                            "mode": {
                                "type": "string",
                                "description": "Query mode: local, global, or hybrid (default: hybrid)",
                                "default": "hybrid"
                            }
                        },
                        "required": ["query"]
                    }
                }
            }
        ]
    
    async def simple_search(
        self,
        query: str,
        mode: QueryMode = None,
        top_k: int = None,
        response_type: ResponseType = None,
        **kwargs
    ) -> SearchResult:
        """
        Perform a simple search query.
        
        Args:
            query: Search query
            mode: Query mode (uses config default if None)
            top_k: Number of results (uses config default if None)
            response_type: Response format (uses config default if None)
            **kwargs: Additional query parameters
            
        Returns:
            SearchResult with response and metadata
        """
        start_time = time.time()
        
        # Use config defaults if not specified
        mode = mode or self.search_config.default_mode
        top_k = top_k or self.search_config.default_top_k
        response_type = response_type or self.search_config.response_type
        
        try:
            logger.info(f"Simple search: '{query}' (mode: {mode})")
            
            # Execute query
            result = await self.lightrag.aquery(
                query=query,
                mode=mode,
                top_k=top_k,
                response_type=response_type,
                max_entity_tokens=self.search_config.max_entity_tokens,
                max_relation_tokens=self.search_config.max_relation_tokens,
                **kwargs
            )
            
            execution_time = time.time() - start_time
            
            # Create search result
            search_result = SearchResult(
                query=query,
                result=result.result,
                mode=mode,
                execution_time=execution_time,
                sources=self._extract_sources(result.result),
                confidence_score=self._calculate_confidence(result),
                context_used=result.context_only,
                total_tokens=result.tokens_used.get("total", 0),
                error=result.error
            )
            
            # Add to history
            self.query_history.append(search_result)
            
            return search_result
            
        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"Simple search failed: {str(e)}"
            logger.error(error_msg)
            
            search_result = SearchResult(
                query=query,
                result="",
                mode=mode,
                execution_time=execution_time,
                sources=[],
                confidence_score=0.0,
                context_used=False,
                error=error_msg
            )
            
            self.query_history.append(search_result)
            return search_result
    
    async def agentic_search(
        self,
        query: str,
        objective: str = None,
        max_steps: int = 5,
        model_name: str = "openai/gpt-4o-mini"
    ) -> SearchResult:
        """
        Perform complex multi-hop reasoning search using AgenticStepProcessor.
        
        Args:
            query: Initial search query
            objective: Specific objective for the search (optional)
            max_steps: Maximum reasoning steps
            model_name: Model to use for reasoning
            
        Returns:
            SearchResult with agentic reasoning steps
        """
        if not self.agentic_enabled:
            logger.error("Agentic search requested but PromptChain not available")
            return await self.simple_search(query)
        
        start_time = time.time()
        
        try:
            logger.info(f"Agentic search: '{query}' (max_steps: {max_steps})")
            
            # Set default objective if not provided
            if not objective:
                objective = f"Provide a comprehensive analysis of: {query}"
            
            # Create agentic step processor
            agentic_processor = AgenticStepProcessor(
                objective=objective,
                max_internal_steps=max_steps,
                model_name=model_name
            )
            
            # Create tool functions for LightRAG
            async def lightrag_local_query(query: str, top_k: int = 10) -> str:
                """Local query tool function."""
                result = await self.lightrag.local_query(query, top_k=top_k)
                return result.result
            
            async def lightrag_global_query(query: str, max_relation_tokens: int = 8000) -> str:
                """Global query tool function."""
                result = await self.lightrag.global_query(query, max_relation_tokens=max_relation_tokens)
                return result.result
            
            async def lightrag_hybrid_query(
                query: str, 
                top_k: int = 10, 
                max_entity_tokens: int = 6000,
                max_relation_tokens: int = 8000
            ) -> str:
                """Hybrid query tool function."""
                result = await self.lightrag.hybrid_query(
                    query, 
                    top_k=top_k,
                    max_entity_tokens=max_entity_tokens,
                    max_relation_tokens=max_relation_tokens
                )
                return result.result
            
            async def lightrag_extract_context(query: str, mode: str = "hybrid") -> str:
                """Context extraction tool function."""
                return await self.lightrag.extract_context(query, mode=mode)
            
            # Create PromptChain for agentic processing
            chain = PromptChain(
                models=[model_name],
                instructions=[agentic_processor],
                verbose=True
            )
            
            # Register tool functions
            chain.register_tool_function(lightrag_local_query)
            chain.register_tool_function(lightrag_global_query)
            chain.register_tool_function(lightrag_hybrid_query)
            chain.register_tool_function(lightrag_extract_context)
            
            # Add tools
            chain.add_tools(self.lightrag_tools)
            
            # Execute agentic reasoning
            result = await chain.process_prompt_async(query)
            
            execution_time = time.time() - start_time
            
            # Extract agentic steps if available
            agentic_steps = []
            if hasattr(agentic_processor, 'internal_step_outputs'):
                agentic_steps = agentic_processor.internal_step_outputs
            
            # Create search result
            search_result = SearchResult(
                query=query,
                result=result,
                mode="agentic",
                execution_time=execution_time,
                sources=self._extract_sources(result),
                confidence_score=0.9,  # Higher confidence for agentic results
                context_used=True,
                agentic_steps=agentic_steps,
                total_tokens=0  # TODO: Calculate from chain
            )
            
            # Add to history
            self.query_history.append(search_result)
            
            logger.info(f"Agentic search completed in {execution_time:.2f}s")
            return search_result
            
        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"Agentic search failed: {str(e)}"
            logger.error(error_msg)
            
            # Fallback to simple search
            logger.info("Falling back to simple search")
            fallback_result = await self.simple_search(query)
            fallback_result.error = f"Agentic failed, used fallback: {error_msg}"
            
            return fallback_result
    
    def _extract_sources(self, result_text: str) -> List[str]:
        """Extract source information from result text."""
        sources = []
        # Simple heuristic - look for file paths or document references
        lines = result_text.split('\n')
        for line in lines:
            if 'Document:' in line or 'File:' in line or 'Source:' in line:
                sources.append(line.strip())
        return sources[:5]  # Limit to top 5 sources
    
    def _calculate_confidence(self, query_result: QueryResult) -> float:
        """Calculate confidence score for a query result."""
        if query_result.error:
            return 0.0
        
        # Simple heuristic based on result length and execution time
        result_length = len(query_result.result)
        
        if result_length < 50:
            return 0.3
        elif result_length < 200:
            return 0.6
        elif result_length < 500:
            return 0.8
        else:
            return 0.9
    
    async def multi_query_search(
        self,
        queries: List[str],
        synthesis_prompt: str = None
    ) -> SearchResult:
        """
        Execute multiple queries and synthesize results.
        
        Args:
            queries: List of search queries
            synthesis_prompt: Custom synthesis prompt
            
        Returns:
            SearchResult with synthesized response
        """
        start_time = time.time()
        
        try:
            logger.info(f"Multi-query search with {len(queries)} queries")
            
            # Execute all queries concurrently
            results = await asyncio.gather(*[
                self.simple_search(query) for query in queries
            ])
            
            # Combine results
            combined_results = []
            all_sources = []
            total_tokens = 0
            
            for i, result in enumerate(results):
                if result.result and not result.error:
                    combined_results.append(f"Query {i+1}: {queries[i]}\nResult: {result.result}")
                    all_sources.extend(result.sources)
                    total_tokens += result.total_tokens
            
            if not combined_results:
                raise Exception("No successful results from multi-query search")
            
            # Synthesize if using agentic capabilities
            if self.agentic_enabled and len(combined_results) > 1:
                synthesis_prompt = synthesis_prompt or f"""
                Synthesize the following search results into a comprehensive response:
                
                {chr(10).join(combined_results)}
                
                Provide a unified, coherent answer that incorporates insights from all queries.
                """
                
                synthesis_result = await self.agentic_search(
                    synthesis_prompt,
                    objective="Synthesize multiple search results into a unified response",
                    max_steps=3
                )
                
                final_result = synthesis_result.result
            else:
                # Simple concatenation if agentic not available
                final_result = "\n\n".join(combined_results)
            
            execution_time = time.time() - start_time
            
            search_result = SearchResult(
                query=f"Multi-query: {', '.join(queries[:2])}{'...' if len(queries) > 2 else ''}",
                result=final_result,
                mode="multi-query",
                execution_time=execution_time,
                sources=list(set(all_sources)),  # Remove duplicates
                confidence_score=0.85,
                context_used=True,
                total_tokens=total_tokens
            )
            
            self.query_history.append(search_result)
            return search_result
            
        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"Multi-query search failed: {str(e)}"
            logger.error(error_msg)
            
            return SearchResult(
                query=f"Multi-query: {', '.join(queries)}",
                result="",
                mode="multi-query",
                execution_time=execution_time,
                sources=[],
                confidence_score=0.0,
                context_used=False,
                error=error_msg
            )
    
    def get_search_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent search history."""
        recent_history = self.query_history[-limit:] if limit else self.query_history
        return [
            {
                "query": result.query,
                "mode": result.mode,
                "execution_time": result.execution_time,
                "confidence_score": result.confidence_score,
                "has_error": result.error is not None,
                "timestamp": datetime.now().isoformat(),  # TODO: Store actual timestamp
                "sources_count": len(result.sources),
                "result_length": len(result.result)
            }
            for result in recent_history
        ]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get search interface statistics."""
        if not self.query_history:
            return {
                "total_queries": 0,
                "avg_execution_time": 0,
                "avg_confidence": 0,
                "agentic_enabled": self.agentic_enabled
            }
        
        successful_queries = [q for q in self.query_history if not q.error]
        
        return {
            "total_queries": len(self.query_history),
            "successful_queries": len(successful_queries),
            "avg_execution_time": sum(q.execution_time for q in successful_queries) / len(successful_queries) if successful_queries else 0,
            "avg_confidence": sum(q.confidence_score for q in successful_queries) / len(successful_queries) if successful_queries else 0,
            "mode_distribution": self._get_mode_distribution(),
            "agentic_enabled": self.agentic_enabled,
            "recent_errors": [q.error for q in self.query_history[-5:] if q.error]
        }
    
    def _get_mode_distribution(self) -> Dict[str, int]:
        """Get distribution of query modes used."""
        mode_counts = {}
        for query in self.query_history:
            mode_counts[query.mode] = mode_counts.get(query.mode, 0) + 1
        return mode_counts