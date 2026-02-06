# HybridRAG MCP Server Optimization Strategy

## Problem Statement

Based on 5-day SpecStory analysis:
- **37% timeout rate** (600s) on complex queries
- **23% empty result rate** indicating retrieval issues
- Database has grown significantly, impacting performance
- LLM agents often choose wrong tool for query complexity

## Solution: Tiered Escalation Framework

### The 10-60-600 Rule

Guide LLM agents to **"Fail-Fast, Escalate-Slow"**:

1. **10 seconds** - Try Tier 1-2 (instant/fast tools) first
2. **60 seconds** - If incomplete, escalate to Tier 3 (strategic)
3. **600 seconds** - Only use Tier 4 (deep intel) for high-value complex reasoning

---

## Tool Tier Classification

| Tier | Name | Speed | Tool | `task=True` | Max Timeout | Recommended `top_k` |
|:-----|:-----|:------|:-----|:------------|:------------|:--------------------|
| **T1** | Recon | <2s | `database_status`, `health_check`, `get_logs` | No | 10s | N/A |
| **T2** | Tactical | <15s | `local_query`, `extract_context` | No | 30s | 2-5 |
| **T3** | Strategic | <60s | `global_query`, `hybrid_query`, `query` | **Yes** | 180s | 5-10 |
| **T4** | Deep Intel | >60s | `multihop_query` | **Yes** | 600s | N/A (uses seeds) |

---

## Recommended Docstring Schema

Use structured metadata tags that LLMs parse reliably:

```python
"""
[SPEED: FAST] [TIER: 2] [MAX_TIMEOUT: 30s]
USE FOR: Specific facts, entity definitions, or pinpointing known information.
STRATEGY: Always try this tool first for simple questions. Use low top_k (2-5).

Args:
    query: The specific search term.
    top_k: Recommended 3 for speed, 10 for depth.
"""
```

### Key Docstring Elements

1. **[SPEED]**: INSTANT | FAST | MEDIUM | SLOW
2. **[TIER]**: 1-4 (matches escalation framework)
3. **[MAX_TIMEOUT]**: Expected maximum execution time
4. **USE FOR**: Explicit use cases
5. **STRATEGY**: When to choose this over alternatives
6. **DO NOT USE**: Anti-patterns

---

## Cascading Query Strategy

### The "Breadcrumb Seeding" Pattern

User's insight: Start with `top_k=2-5`, then use results to seed multihop.

```
Step 1: Quick Tactical Retrieval
    local_query(query, top_k=3) → 3 high-confidence anchor entities

Step 2: If incomplete, Strategic Expansion
    hybrid_query(query, top_k=5) → broader context + relationships
    Extract: suggested_multihop_seeds from response metadata

Step 3: Deep Intel with Seeds (only if needed)
    multihop_query(
        query=original_query,
        context_seeds=["entity_a", "entity_b", "entity_c"]  # From Step 1-2
    )
```

### Benefits of Seeding

- Multihop skips exploratory phase → faster execution
- Reasoning stays grounded in relevant data
- Prevents "cascading errors" from irrelevant initial retrieval
- Reduces 600s timeout risk significantly

---

## Implementation Changes Required

### 1. Add `task=True` to Strategic Tools

```python
# Current (synchronous, causes timeouts)
@mcp.tool
async def hybridrag_hybrid_query(...):

# Recommended (background task)
@mcp.tool(task=True)
async def hybridrag_hybrid_query(...):
```

**Tools to update:**
- `hybridrag_hybrid_query` → `task=True`
- `hybridrag_global_query` → `task=True`
- `hybridrag_query` (mode=hybrid/global/mix) → `task=True`

### 2. Add Progress Reporting

FastMCP supports `ctx.report_progress()`. Use inside long operations:

```python
@mcp.tool(task=True)
async def hybridrag_hybrid_query(query: str, top_k: int = 10, ctx=None):
    """..."""
    if ctx:
        await ctx.report_progress(0, 100, "Starting hybrid search...")

    # Local retrieval
    local_result = await core.local_query(query, top_k)
    if ctx:
        await ctx.report_progress(40, 100, f"Found {len(local_result)} entities")

    # Global retrieval
    global_result = await core.global_query(query, top_k)
    if ctx:
        await ctx.report_progress(80, 100, "Merging results...")

    # Synthesis
    result = merge_and_synthesize(local_result, global_result)
    if ctx:
        await ctx.report_progress(100, 100, "Complete")

    return result
```

### 3. Add Server-Side `top_k` Capping

Prevent LLMs from requesting excessive `top_k` values:

```python
MAX_TOP_K_BY_TIER = {
    "local_query": 10,      # Tier 2
    "global_query": 15,     # Tier 3
    "hybrid_query": 15,     # Tier 3
    "query": 20,            # Tier 3 (flexible)
}

async def hybridrag_local_query(query: str, top_k: int = 5):
    top_k = min(top_k, MAX_TOP_K_BY_TIER["local_query"])
    # ... rest of implementation
```

### 4. Return Execution Metadata

Help LLMs learn from history by including tier and timing:

```python
return {
    "result": answer,
    "metadata": {
        "tier": 2,
        "tool": "local_query",
        "execution_time": 2.3,
        "top_k_requested": 10,
        "top_k_used": 5,  # If capped
        "suggested_escalation": "hybrid_query" if incomplete else None,
        "suggested_multihop_seeds": extract_top_entities(result)
    }
}
```

---

## Updated Tool Docstrings

### Tier 1: Recon (Instant)

```python
@mcp.tool
async def hybridrag_database_status() -> str:
    """
    [SPEED: INSTANT] [TIER: 1] [MAX_TIMEOUT: 5s]
    USE FOR: Checking if database exists and is configured before querying.
    STRATEGY: Call this FIRST if unsure whether HybridRAG has relevant data.

    Returns: Database path, models, graph statistics
    """
```

```python
@mcp.tool
async def hybridrag_health_check() -> str:
    """
    [SPEED: INSTANT] [TIER: 1] [MAX_TIMEOUT: 10s]
    USE FOR: Diagnosing connection or initialization failures.
    STRATEGY: Call when queries return errors or empty results.

    Returns: Health status with diagnostic details
    """
```

### Tier 2: Tactical (Fast)

```python
@mcp.tool
async def hybridrag_local_query(
    query: str,
    top_k: int = 5,  # Lowered default from 10
    max_entity_tokens: int = 6000
) -> str:
    """
    [SPEED: FAST] [TIER: 2] [MAX_TIMEOUT: 30s]
    USE FOR: Specific entities, names, definitions, direct relationships.
    STRATEGY: START HERE for most queries. Use top_k=2-5 for speed.
    DO NOT USE: For overviews, summaries, or pattern discovery.

    Examples:
        - "What is the HybridRAGConfig class?"
        - "Find the patient_demographics table schema"
        - "What does get_lineage function do?"

    Args:
        query: Specific entity or thing to find
        top_k: 2-5 recommended (max capped at 10)
    """
```

```python
@mcp.tool
async def hybridrag_extract_context(
    query: str,
    mode: Literal["local", "global", "hybrid"] = "local",  # Changed default
    top_k: int = 5
) -> str:
    """
    [SPEED: FAST] [TIER: 2] [MAX_TIMEOUT: 20s]
    USE FOR: Raw retrieval chunks without LLM synthesis.
    STRATEGY: Use to inspect what would be retrieved before full query.
              Also use to get seeds for multihop_query.

    Args:
        query: Search terms
        mode: local (fastest), global, or hybrid
        top_k: 3-5 recommended for seeding

    Returns: Raw text chunks (no LLM processing)
    """
```

### Tier 3: Strategic (Medium)

```python
@mcp.tool(task=True)  # ADDED task=True
async def hybridrag_global_query(
    query: str,
    top_k: int = 10,
    max_relation_tokens: int = 8000
) -> str:
    """
    [SPEED: MEDIUM] [TIER: 3] [MAX_TIMEOUT: 120s]
    USE FOR: Overviews, summaries, themes, patterns across documents.
    STRATEGY: Use when local_query returns "I don't know" or needs context.
              RUNS AS BACKGROUND TASK - may take 30-60s.
    DO NOT USE: For specific entity lookups (use local_query).

    Examples:
        - "What are the main Snowflake tables in this project?"
        - "Summarize the RAF calculation pipeline"
        - "What patterns exist in error handling?"

    Args:
        query: Question asking for overview/summary/patterns
        top_k: 5-10 recommended (max capped at 15)
    """
```

```python
@mcp.tool(task=True)  # ADDED task=True
async def hybridrag_hybrid_query(
    query: str,
    top_k: int = 10,
    max_entity_tokens: int = 6000,
    max_relation_tokens: int = 8000
) -> str:
    """
    [SPEED: MEDIUM] [TIER: 3] [MAX_TIMEOUT: 180s]
    USE FOR: Questions needing BOTH specific details AND broader context.
    STRATEGY: Use after local_query if answer is incomplete.
              RUNS AS BACKGROUND TASK - may take 60-120s.

    Examples:
        - "How does HybridRAGConfig relate to LightRAG initialization?"
        - "What tables feed into the RAF_ASSESSMENT view and why?"

    Args:
        query: Any natural language question
        top_k: 5-10 recommended (max capped at 15)
    """
```

### Tier 4: Deep Intel (Slow)

```python
@mcp.tool(task=True)
async def hybridrag_multihop_query(
    query: str,
    max_steps: int = 8,
    verbose: bool = False,
    context_seeds: list[str] = None  # NEW PARAMETER
) -> str:
    """
    [SPEED: SLOW] [TIER: 4] [MAX_TIMEOUT: 600s]
    USE FOR: Complex reasoning that CANNOT be answered in single retrieval.
    STRATEGY: LAST RESORT. Use ONLY when Tier 2-3 tools fail.
              Provide 'context_seeds' from previous queries to speed up.
              RUNS AS BACKGROUND TASK - expect 2-10 minutes.

    Examples:
        - "Compare the old RAF pipeline with the new one"
        - "Trace data flow from Elation to Snowflake final tables"
        - "How do A, B, and C all relate to each other?"

    HOW IT WORKS:
        1. AI agent analyzes query complexity
        2. Agent executes MULTIPLE sub-queries (local, global, hybrid)
        3. Agent accumulates context across steps
        4. Agent synthesizes comprehensive answer

    PERFORMANCE TIP:
        Run extract_context first with top_k=3, then pass
        resulting entities as context_seeds to focus the search.

    Args:
        query: Complex analytical question
        max_steps: Reasoning iterations (2-10, default: 8)
        verbose: Include step-by-step reasoning trace
        context_seeds: Entity names from previous queries to focus search
    """
```

---

## LLM System Prompt Addition

Add this to the system prompt for agents using HybridRAG:

```
## HybridRAG Query Protocol

You have a TIERED HybridRAG system. Follow the **10-60-600 Rule**:

1. **10 seconds** - Start with Tier 2 (local_query, top_k=3-5)
2. **60 seconds** - If incomplete, escalate to Tier 3 (hybrid_query)
3. **600 seconds** - Only use Tier 4 (multihop_query) for complex reasoning

**Cascading Strategy:**
- Use results from fast queries to seed slower queries
- Pass entity names from local_query as context_seeds to multihop_query
- This prevents timeouts and improves accuracy

**Tool Tiers:**
- [TIER 1] database_status, health_check - Instant diagnostics
- [TIER 2] local_query, extract_context - Fast entity lookup (2-5 top_k)
- [TIER 3] global_query, hybrid_query - Medium, runs background task
- [TIER 4] multihop_query - Slow, complex reasoning only
```

---

## Implementation Priority

### Phase 1: Quick Wins (No Code Changes)
1. Update system prompt with tier guidance
2. Lower default `top_k` values in tool calls
3. Train on cascading pattern: fast first, escalate with seeds

### Phase 2: Docstring Updates
1. Add `[SPEED]`, `[TIER]`, `[MAX_TIMEOUT]` tags to all tools
2. Add explicit "USE FOR" and "DO NOT USE" guidance
3. Update examples to show cascading pattern

### Phase 3: Background Task Expansion
1. Add `task=True` to `hybrid_query` and `global_query`
2. Implement progress reporting with `ctx.report_progress()`
3. Add `context_seeds` parameter to `multihop_query`

### Phase 4: Smart Defaults
1. Add server-side `top_k` capping by tier
2. Return execution metadata for LLM learning
3. Consider "Query Pre-Flight" tool that recommends tier

---

## Expected Outcomes

| Metric | Current | Target |
|--------|---------|--------|
| Timeout Rate | 37% | <10% |
| Empty Results | 23% | <10% |
| Avg Query Time | ~180s | <30s |
| Tier 4 Usage | ~40% | <15% |

By steering LLMs toward faster tools first and providing seeds for complex queries, we expect dramatic improvements in reliability and response time.
