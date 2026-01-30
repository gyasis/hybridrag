#!/usr/bin/env python3
"""
Agentic RAG Module
==================
Multi-hop reasoning using PromptChain's AgenticStepProcessor with LightRAG tools.
Based on athena-lightrag patterns.

The LightRAG queries are exposed as tools with parameters (mode, top_k, etc.)
that AgenticStepProcessor can call dynamically to perform multi-hop reasoning.
"""

import asyncio
import time
import json
import logging
import random
from typing import Dict, List, Optional, Any, Literal
from dataclasses import dataclass, field

from promptchain import PromptChain
from promptchain.utils.agentic_step_processor import AgenticStepProcessor

# Import retry utilities from lightrag_core
from src.lightrag_core import (
    is_transient_error,
    calculate_backoff_with_jitter,
    LITELLM_MAX_RETRIES,
)

logger = logging.getLogger(__name__)

# Query modes supported by LightRAG
QueryMode = Literal["local", "global", "hybrid", "naive", "mix"]


@dataclass
class MultiHopContext:
    """Context accumulation for multi-hop reasoning."""
    initial_query: str
    contexts: List[Dict[str, Any]] = field(default_factory=list)
    reasoning_steps: List[str] = field(default_factory=list)
    final_synthesis: Optional[str] = None
    total_tokens_used: int = 0
    execution_time: float = 0.0


class LightRAGToolsProvider:
    """
    Provides LightRAG query functions as tools for PromptChain.
    Each tool has parameters (mode, top_k, etc.) that the LLM can choose.
    """

    def __init__(self, lightrag_core, verbose: bool = False):
        """
        Initialize tools provider.

        Args:
            lightrag_core: HybridLightRAGCore instance
            verbose: Enable verbose logging
        """
        self.lightrag_core = lightrag_core
        self.verbose = verbose
        self.context_accumulator = MultiHopContext(initial_query="")

    def reset_context_accumulator(self, query: str):
        """Reset context accumulator for a new multi-hop session."""
        self.context_accumulator = MultiHopContext(initial_query=query)

    def get_accumulated_context(self) -> MultiHopContext:
        """Get the current accumulated context."""
        return self.context_accumulator

    # ==================== TOOL FUNCTIONS ====================
    # These are the actual functions that get called by AgenticStepProcessor

    async def lightrag_query(
        self,
        query: str,
        mode: str = "hybrid",
        top_k: int = 10,
        max_entity_tokens: int = 6000,
        max_relation_tokens: int = 8000,
        only_context: bool = False
    ) -> str:
        """
        Query LightRAG knowledge base with specified mode and parameters.

        Args:
            query: The search query
            mode: Query mode - 'local' for entities, 'global' for overviews,
                  'hybrid' for combined, 'naive' for simple vector, 'mix' for all
            top_k: Number of top results to retrieve
            max_entity_tokens: Maximum tokens for entity context
            max_relation_tokens: Maximum tokens for relation context
            only_context: If True, return raw context without LLM generation

        Returns:
            Query result as string (or context if only_context=True)
        """
        try:
            if self.verbose:
                logger.info(f"[LightRAG Tool] Query: '{query[:50]}...' mode={mode} top_k={top_k}")

            result = await self.lightrag_core.aquery(
                query=query,
                mode=mode,
                top_k=top_k,
                max_entity_tokens=max_entity_tokens,
                max_relation_tokens=max_relation_tokens,
                only_need_context=only_context
            )

            # Accumulate context for multi-hop tracking
            context_entry = {
                "type": f"lightrag_{mode}",
                "query": query,
                "mode": mode,
                "top_k": top_k,
                "result_preview": result.result[:500] if result.result else "",
                "execution_time": result.execution_time
            }
            self.context_accumulator.contexts.append(context_entry)
            self.context_accumulator.reasoning_steps.append(
                f"Queried LightRAG ({mode} mode) for: {query[:100]}"
            )

            if result.error:
                return json.dumps({"error": result.error})

            # Defensive: ensure we never return None
            return result.result or ""

        except Exception as e:
            logger.error(f"[LightRAG Tool] Error: {e}")
            return json.dumps({"error": str(e)})

    async def lightrag_local_query(
        self,
        query: str,
        top_k: int = 10,
        max_entity_tokens: int = 6000
    ) -> str:
        """
        Query LightRAG in LOCAL mode for specific entity relationships.

        Use this for finding specific entities, functions, classes, or named concepts.

        Args:
            query: The search query focused on specific entities
            top_k: Number of top results to retrieve
            max_entity_tokens: Maximum tokens for entity context
        """
        return await self.lightrag_query(
            query=query,
            mode="local",
            top_k=top_k,
            max_entity_tokens=max_entity_tokens
        )

    async def lightrag_global_query(
        self,
        query: str,
        top_k: int = 10,
        max_relation_tokens: int = 8000
    ) -> str:
        """
        Query LightRAG in GLOBAL mode for high-level overviews.

        Use this for understanding workflows, architecture, or broad patterns.

        Args:
            query: The search query for overview/summary
            top_k: Number of top results to retrieve
            max_relation_tokens: Maximum tokens for relation context
        """
        return await self.lightrag_query(
            query=query,
            mode="global",
            top_k=top_k,
            max_relation_tokens=max_relation_tokens
        )

    async def lightrag_hybrid_query(
        self,
        query: str,
        top_k: int = 10,
        max_entity_tokens: int = 6000,
        max_relation_tokens: int = 8000
    ) -> str:
        """
        Query LightRAG in HYBRID mode combining local and global.

        Use this for general questions needing both specific details and context.

        Args:
            query: The search query
            top_k: Number of top results to retrieve
            max_entity_tokens: Maximum tokens for entity context
            max_relation_tokens: Maximum tokens for relation context
        """
        return await self.lightrag_query(
            query=query,
            mode="hybrid",
            top_k=top_k,
            max_entity_tokens=max_entity_tokens,
            max_relation_tokens=max_relation_tokens
        )

    async def lightrag_context_extract(
        self,
        query: str,
        mode: str = "hybrid",
        top_k: int = 10
    ) -> str:
        """
        Extract raw context from LightRAG without LLM generation.

        Use this to gather raw data before synthesis.

        Args:
            query: The search query
            mode: Query mode to use
            top_k: Number of top results
        """
        return await self.lightrag_query(
            query=query,
            mode=mode,
            top_k=top_k,
            only_context=True
        )

    async def accumulate_context(
        self,
        context_type: str,
        context_data: str,
        reasoning_step: str
    ) -> str:
        """
        Accumulate context for multi-hop reasoning.

        Args:
            context_type: Type of context being accumulated
            context_data: The context data to store
            reasoning_step: Description of the reasoning step
        """
        context_entry = {
            "type": context_type,
            "data": context_data[:2000],  # Truncate for safety
            "step": reasoning_step,
            "tokens": len(context_data) // 4  # Rough estimate
        }

        self.context_accumulator.contexts.append(context_entry)
        self.context_accumulator.reasoning_steps.append(reasoning_step)
        self.context_accumulator.total_tokens_used += context_entry["tokens"]

        return f"Accumulated {context_type} context ({context_entry['tokens']} est. tokens). Total contexts: {len(self.context_accumulator.contexts)}"

    # ==================== TOOL SCHEMAS ====================

    def create_lightrag_tools(self) -> List[Dict]:
        """
        Create tool schemas in OpenAI function calling format.
        These define what parameters the LLM can pass to each tool.
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": "lightrag_query",
                    "description": "Query the LightRAG knowledge base with full parameter control. Use specific modes for different query types.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query"
                            },
                            "mode": {
                                "type": "string",
                                "enum": ["local", "global", "hybrid", "naive", "mix"],
                                "description": "Query mode: 'local' for specific entities, 'global' for overviews, 'hybrid' for combined, 'naive' for simple vector search, 'mix' for all strategies",
                                "default": "hybrid"
                            },
                            "top_k": {
                                "type": "integer",
                                "description": "Number of top results to retrieve",
                                "default": 10
                            },
                            "max_entity_tokens": {
                                "type": "integer",
                                "description": "Maximum tokens for entity context",
                                "default": 6000
                            },
                            "max_relation_tokens": {
                                "type": "integer",
                                "description": "Maximum tokens for relation context",
                                "default": 8000
                            },
                            "only_context": {
                                "type": "boolean",
                                "description": "If true, return raw context without LLM generation",
                                "default": False
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "lightrag_local_query",
                    "description": "Query in LOCAL mode for specific entity relationships. Best for finding specific functions, classes, or named concepts.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Query focused on specific entities"
                            },
                            "top_k": {
                                "type": "integer",
                                "description": "Number of top results",
                                "default": 10
                            },
                            "max_entity_tokens": {
                                "type": "integer",
                                "description": "Maximum tokens for entity context",
                                "default": 6000
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
                    "description": "Query in GLOBAL mode for high-level overviews. Best for understanding workflows, architecture, or patterns.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Query for overview/summary information"
                            },
                            "top_k": {
                                "type": "integer",
                                "description": "Number of top results",
                                "default": 10
                            },
                            "max_relation_tokens": {
                                "type": "integer",
                                "description": "Maximum tokens for relation context",
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
                    "description": "Query in HYBRID mode combining local and global. Best for general questions needing both specifics and context.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query"
                            },
                            "top_k": {
                                "type": "integer",
                                "description": "Number of top results",
                                "default": 10
                            },
                            "max_entity_tokens": {
                                "type": "integer",
                                "description": "Maximum tokens for entity context",
                                "default": 6000
                            },
                            "max_relation_tokens": {
                                "type": "integer",
                                "description": "Maximum tokens for relation context",
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
                    "name": "lightrag_context_extract",
                    "description": "Extract raw context without LLM generation. Use to gather data before synthesis.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query"
                            },
                            "mode": {
                                "type": "string",
                                "enum": ["local", "global", "hybrid", "naive", "mix"],
                                "description": "Query mode to use",
                                "default": "hybrid"
                            },
                            "top_k": {
                                "type": "integer",
                                "description": "Number of top results",
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
                    "name": "accumulate_context",
                    "description": "Store context for multi-hop reasoning. Use to track findings across queries.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "context_type": {
                                "type": "string",
                                "description": "Type of context (e.g., 'entity', 'relationship', 'summary')"
                            },
                            "context_data": {
                                "type": "string",
                                "description": "The context data to store"
                            },
                            "reasoning_step": {
                                "type": "string",
                                "description": "Description of the reasoning step"
                            }
                        },
                        "required": ["context_type", "context_data", "reasoning_step"]
                    }
                }
            }
        ]

    def register_tool_functions(self, prompt_chain: PromptChain):
        """
        Register LightRAG tool functions with PromptChain.

        Args:
            prompt_chain: The PromptChain instance to register tools with
        """
        prompt_chain.register_tool_function(self.lightrag_query)
        prompt_chain.register_tool_function(self.lightrag_local_query)
        prompt_chain.register_tool_function(self.lightrag_global_query)
        prompt_chain.register_tool_function(self.lightrag_hybrid_query)
        prompt_chain.register_tool_function(self.lightrag_context_extract)
        prompt_chain.register_tool_function(self.accumulate_context)


class AgenticHybridRAG:
    """
    Main class combining AgenticStepProcessor with LightRAG tools for multi-hop reasoning.
    """

    def __init__(
        self,
        lightrag_core,
        model_name: str = "azure/gpt-4.1",
        max_internal_steps: int = 8,
        verbose: bool = False
    ):
        """
        Initialize Agentic HybridRAG.

        Args:
            lightrag_core: HybridLightRAGCore instance
            model_name: LLM model to use for reasoning
            max_internal_steps: Maximum reasoning steps
            verbose: Enable verbose logging
        """
        self.lightrag_core = lightrag_core
        self.model_name = model_name
        self.max_internal_steps = max_internal_steps
        self.verbose = verbose

        # Initialize tools provider
        self.tools_provider = LightRAGToolsProvider(lightrag_core, verbose=verbose)

        logger.info(f"AgenticHybridRAG initialized (model: {model_name}, max_steps: {max_internal_steps})")

    def create_multi_hop_processor(
        self,
        objective: str,
        custom_instructions: Optional[List[str]] = None
    ) -> AgenticStepProcessor:
        """
        Create AgenticStepProcessor configured for multi-hop LightRAG reasoning.

        Args:
            objective: The reasoning objective
            custom_instructions: Optional custom instructions

        Returns:
            Configured AgenticStepProcessor
        """
        return AgenticStepProcessor(
            objective=objective,
            max_internal_steps=self.max_internal_steps,
            model_name=self.model_name,
            history_mode="progressive"  # Accumulate all tool results for better multi-hop reasoning
        )

    def create_reasoning_chain(
        self,
        objective: str,
        pre_processing_steps: Optional[List[str]] = None,
        post_processing_steps: Optional[List[str]] = None
    ) -> PromptChain:
        """
        Create a PromptChain with LightRAG tools for multi-hop reasoning.

        Args:
            objective: The reasoning objective
            pre_processing_steps: Optional pre-processing instructions
            post_processing_steps: Optional post-processing instructions

        Returns:
            Configured PromptChain with LightRAG tools
        """
        # Create agentic step processor
        agentic_step = self.create_multi_hop_processor(objective)

        # Build instruction sequence
        instructions = []

        # Add pre-processing steps
        if pre_processing_steps:
            instructions.extend(pre_processing_steps)

        # Add the main agentic reasoning step
        instructions.append(agentic_step)

        # Add post-processing steps
        if post_processing_steps:
            instructions.extend(post_processing_steps)
        else:
            # Default synthesis step
            instructions.append(
                "Synthesize all accumulated contexts and reasoning into a comprehensive final response: {input}"
            )

        # Create PromptChain
        chain = PromptChain(
            models=[self.model_name],
            instructions=instructions,
            verbose=self.verbose,
            store_steps=True
        )

        # Register LightRAG tools
        self.tools_provider.register_tool_functions(chain)
        chain.add_tools(self.tools_provider.create_lightrag_tools())

        return chain

    async def execute_multi_hop_reasoning(
        self,
        query: str,
        objective: Optional[str] = None,
        reset_context: bool = True,
        timeout_seconds: float = 600.0,
        circuit_breaker_failures: int = 3
    ) -> Dict[str, Any]:
        """
        Execute multi-hop reasoning using LightRAG tools with timeout and circuit breaker.

        Args:
            query: The question to answer
            objective: Optional custom objective (auto-generated if not provided)
            reset_context: Whether to reset context accumulator
            timeout_seconds: Maximum execution time
            circuit_breaker_failures: Max failures before circuit breaker opens

        Returns:
            Dictionary with reasoning results and context
        """
        start_time = time.time()

        if reset_context:
            self.tools_provider.reset_context_accumulator(query)

        # Create objective if not provided
        if not objective:
            objective = f"""Analyze the query '{query}' using multi-hop reasoning.

Strategy:
1. Break down the question into sub-questions if complex
2. Use appropriate query modes strategically:
   - lightrag_local_query for specific entities/functions
   - lightrag_global_query for overviews/architecture
   - lightrag_hybrid_query for balanced analysis
   - lightrag_context_extract for raw data gathering
3. Accumulate findings across multiple queries
4. Synthesize a comprehensive answer"""

        # Create reasoning chain
        chain = self.create_reasoning_chain(objective)

        # Execute reasoning with timeout protection
        try:
            result = await asyncio.wait_for(
                self._execute_with_circuit_breaker(chain, query, circuit_breaker_failures),
                timeout=timeout_seconds
            )

            # Get accumulated context
            context = self.tools_provider.get_accumulated_context()
            context.final_synthesis = result
            context.execution_time = time.time() - start_time

            return {
                "result": result,
                "reasoning_steps": context.reasoning_steps,
                "accumulated_contexts": context.contexts,
                "total_tokens_used": context.total_tokens_used,
                "execution_time": context.execution_time,
                "step_outputs": chain.step_outputs if hasattr(chain, 'step_outputs') else {},
                "success": True
            }

        except asyncio.TimeoutError:
            logger.error(f"Multi-hop reasoning timed out after {timeout_seconds}s")
            context = self.tools_provider.get_accumulated_context()
            return {
                "result": "",
                "reasoning_steps": context.reasoning_steps,
                "accumulated_contexts": context.contexts,
                "execution_time": time.time() - start_time,
                "success": False,
                "error": f"Timeout after {timeout_seconds} seconds"
            }

        except Exception as e:
            logger.error(f"Multi-hop reasoning failed: {e}")
            context = self.tools_provider.get_accumulated_context()
            return {
                "result": "",
                "reasoning_steps": context.reasoning_steps,
                "accumulated_contexts": context.contexts,
                "execution_time": time.time() - start_time,
                "success": False,
                "error": str(e)
            }

    async def _execute_with_circuit_breaker(
        self,
        chain: PromptChain,
        query: str,
        max_failures: int
    ) -> str:
        """
        Execute chain with circuit breaker pattern to prevent infinite loops.

        Only retries transient errors (429, 5xx). Non-retryable errors (401, 400, 403)
        are raised immediately without consuming retry attempts.

        Args:
            chain: The PromptChain to execute
            query: The query input
            max_failures: Maximum allowed transient failures before circuit breaker opens

        Returns:
            Result string from chain execution

        Raises:
            Exception: If a non-retryable error occurs or max_failures exceeded
        """
        transient_failures = 0
        last_error = None

        while transient_failures < max_failures:
            try:
                result = await chain.process_prompt_async(query)
                return result
            except Exception as e:
                last_error = e

                # Check if error is transient (retryable)
                if not is_transient_error(e):
                    # Non-retryable error (401, 400, 403, etc.) - fail immediately
                    logger.error(
                        f"Circuit breaker: Non-retryable error, failing immediately: {e}"
                    )
                    raise

                # Transient error - count it and potentially retry
                transient_failures += 1
                logger.warning(
                    f"Circuit breaker: Transient error "
                    f"(attempt {transient_failures}/{max_failures}): {e}"
                )

                if transient_failures < max_failures:
                    # Exponential backoff with jitter before retry
                    backoff = calculate_backoff_with_jitter(transient_failures - 1)
                    logger.info(f"Circuit breaker: Retrying in {backoff:.2f}s...")
                    await asyncio.sleep(backoff)

        # Circuit breaker opened - all retries exhausted for transient errors
        raise Exception(
            f"Circuit breaker opened after {max_failures} transient failures. "
            f"Last error: {last_error}"
        )


def create_agentic_rag(lightrag_core, model_name: str = "azure/gpt-4.1", **kwargs) -> AgenticHybridRAG:
    """
    Factory function to create AgenticHybridRAG instance.

    Args:
        lightrag_core: HybridLightRAGCore instance
        model_name: LLM model to use
        **kwargs: Additional arguments for AgenticHybridRAG

    Returns:
        AgenticHybridRAG instance
    """
    return AgenticHybridRAG(lightrag_core, model_name=model_name, **kwargs)
