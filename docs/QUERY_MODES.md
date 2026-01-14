# HybridRAG Query Modes Reference

This document provides comprehensive documentation for all query modes available in HybridRAG, including native LightRAG modes and the advanced multi-hop reasoning capability.

## Table of Contents

- [Overview](#overview)
- [Native LightRAG Modes](#native-lightrag-modes)
  - [Local Mode](#local-mode)
  - [Global Mode](#global-mode)
  - [Hybrid Mode](#hybrid-mode)
  - [Naive Mode](#naive-mode)
  - [Mix Mode](#mix-mode)
- [Multi-Hop Reasoning Mode](#multi-hop-reasoning-mode)
- [Mode Selection Guide](#mode-selection-guide)
- [CLI Usage Examples](#cli-usage-examples)
- [Interactive Mode Commands](#interactive-mode-commands)
- [Python API](#python-api)

---

## Overview

HybridRAG provides six distinct query modes for different retrieval needs:

| Mode | Type | Description | Best For |
|------|------|-------------|----------|
| `local` | Native LightRAG | Entity-focused retrieval | Specific entities, relationships |
| `global` | Native LightRAG | Community-based summaries | Overviews, patterns, architecture |
| `hybrid` | Native LightRAG | Combined local + global | Balanced queries (default) |
| `naive` | Native LightRAG | Basic vector similarity | Simple similarity search |
| `mix` | Native LightRAG | All strategies combined | Complex multi-faceted queries |
| `multihop` | PromptChain | Multi-step agentic reasoning | Complex analysis, comparisons |

---

## Native LightRAG Modes

These modes are built into LightRAG and use the knowledge graph constructed during ingestion.

### Local Mode

**Purpose**: Focus on specific entities and their direct relationships.

**How it works**:
1. Identifies relevant entities from the query
2. Retrieves entity-specific nodes from the knowledge graph
3. Returns direct relationships and attributes

**Best for**:
- Finding specific functions, classes, or named concepts
- Looking up entity definitions and properties
- Tracing direct relationships between entities

**Example queries**:
```
:local
What is the APPOINTMENT table structure?
Find the PatientID column relationships
How does the billing module connect to orders?
```

**CLI**:
```bash
python hybridrag.py query --text "APPOINTMENT table" --mode local
```

**Parameters**:
- `top_k`: Number of entity matches (default: 10)
- `max_entity_tokens`: Maximum tokens for entity context (default: 6000)

---

### Global Mode

**Purpose**: High-level overviews using community-level summaries.

**How it works**:
1. Leverages pre-computed community summaries from the knowledge graph
2. Identifies relevant communities based on the query
3. Returns synthesized overviews and patterns

**Best for**:
- Understanding overall architecture or workflow
- Getting summaries of large document sets
- Identifying high-level patterns and themes

**Example queries**:
```
:global
Overview of the billing workflow
What are the main data domains in this system?
Summarize the patient journey architecture
```

**CLI**:
```bash
python hybridrag.py query --text "billing workflow overview" --mode global
```

**Parameters**:
- `top_k`: Number of community matches (default: 10)
- `max_relation_tokens`: Maximum tokens for relationship context (default: 8000)

---

### Hybrid Mode

**Purpose**: Balanced combination of local entity details and global context.

**How it works**:
1. Performs both local and global retrieval in parallel
2. Combines entity-specific information with community summaries
3. Synthesizes a comprehensive response

**Best for**:
- General questions needing both specifics and context
- Most everyday queries (recommended default)
- When unsure which mode to use

**Example queries**:
```
:hybrid
How do appointments connect to billing?
Explain the patient registration process
What data flows through the charge processing system?
```

**CLI**:
```bash
python hybridrag.py query --text "appointment billing connection" --mode hybrid
```

**Parameters**:
- `top_k`: Number of matches per strategy (default: 10)
- `max_entity_tokens`: Maximum entity tokens (default: 6000)
- `max_relation_tokens`: Maximum relation tokens (default: 8000)

---

### Naive Mode

**Purpose**: Basic vector similarity search without graph reasoning.

**How it works**:
1. Converts query to embedding vector
2. Performs direct similarity search against document chunks
3. Returns top matching chunks without graph enhancement

**Best for**:
- Simple keyword-like searches
- When graph relationships aren't needed
- Debugging or comparing with graph-enhanced modes

**Example queries**:
```
:naive
SELECT * FROM patients
error handling code
configuration settings
```

**CLI**:
```bash
python hybridrag.py query --text "SELECT * FROM patients" --mode naive
```

---

### Mix Mode

**Purpose**: Advanced multi-strategy retrieval using all available methods.

**How it works**:
1. Executes local, global, and naive retrieval simultaneously
2. Combines and deduplicates results from all strategies
3. Applies reranking if enabled
4. Synthesizes comprehensive response

**Best for**:
- Complex queries requiring all retrieval strategies
- Research tasks needing comprehensive coverage
- When other modes return incomplete results

**Example queries**:
```
:mix
Complete analysis of the patient billing lifecycle
All references to authentication across the codebase
Comprehensive documentation of the API endpoints
```

**CLI**:
```bash
python hybridrag.py query --text "patient billing lifecycle" --mode mix
```

---

## Multi-Hop Reasoning Mode

**Purpose**: Complex multi-step analysis using agentic reasoning with LightRAG tools.

### Overview

Multi-hop mode differs fundamentally from native LightRAG modes. Instead of a single retrieval pass, it uses PromptChain's `AgenticStepProcessor` to:

1. **Analyze** the query and determine what information is needed
2. **Plan** which LightRAG tools to call and in what order
3. **Execute** multiple tool calls, accumulating context
4. **Synthesize** a final answer from all gathered information

### How it Works

```
User Query
    │
    ▼
┌─────────────────────────────────────────┐
│     AgenticStepProcessor (LLM)          │
│                                         │
│  ┌─────────────────────────────────┐   │
│  │ Step 1: Analyze query           │   │
│  │ "I need to understand X and Y"  │   │
│  └─────────────────────────────────┘   │
│              │                          │
│              ▼                          │
│  ┌─────────────────────────────────┐   │
│  │ Step 2: Call lightrag_local     │──►│── LightRAG Query
│  │ Tool call with mode=local       │   │
│  └─────────────────────────────────┘   │
│              │                          │
│              ▼                          │
│  ┌─────────────────────────────────┐   │
│  │ Step 3: Call lightrag_global    │──►│── LightRAG Query
│  │ Tool call with mode=global      │   │
│  └─────────────────────────────────┘   │
│              │                          │
│              ▼                          │
│  ┌─────────────────────────────────┐   │
│  │ Step N: Synthesize answer       │   │
│  │ Combine all gathered context    │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
    │
    ▼
Final Answer (with reasoning trace)
```

### Available Tools

Multi-hop mode exposes these tools to the LLM:

| Tool | Description | Parameters |
|------|-------------|------------|
| `lightrag_query` | General query with mode selection | `query`, `mode`, `top_k`, `only_need_context` |
| `lightrag_local_query` | Entity-focused retrieval | `query`, `top_k`, `max_entity_tokens` |
| `lightrag_global_query` | Community-based summaries | `query`, `top_k`, `max_relation_tokens` |
| `lightrag_hybrid_query` | Combined local + global | `query`, `top_k` |
| `lightrag_extract_context` | Raw context without generation | `query`, `mode`, `top_k` |

### Best For

- Complex analytical questions requiring multiple perspectives
- Comparative analysis ("Compare X and Y")
- Multi-entity queries ("How do A, B, and C relate?")
- Questions requiring both specific details and broad context
- Research tasks where the LLM needs to explore the knowledge base

### Example Queries

```
:multihop
Compare the appointment scheduling workflow with the billing workflow

How do patient demographics flow from registration through billing to reporting?

What are all the ways the CHARGE table connects to other clinical data?

Trace the data lineage from raw clinical notes to aggregated reports
```

### CLI Usage

```bash
# One-shot multi-hop query
python hybridrag.py query --text "Compare appointment and billing workflows" --multihop

# With verbose output showing reasoning steps
python hybridrag.py query --text "..." --multihop --verbose
```

### Interactive Mode

```
> :multihop              # Enable multi-hop mode
[MULTIHOP] Multi-hop reasoning enabled

> :verbose               # Enable step-by-step output
[VERBOSE] Verbose mode enabled

> Compare registration and billing

🔄 Multi-hop reasoning in progress...
   Step 1: Calling lightrag_local_query for registration...
   Step 2: Calling lightrag_local_query for billing...
   Step 3: Calling lightrag_global_query for workflow overview...
   Step 4: Synthesizing comparison...

[Result in 45.2s, 4 reasoning steps]
...
```

### Configuration

Multi-hop mode is configured through these parameters:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_internal_steps` | 8 | Maximum reasoning steps before timeout |
| `timeout_seconds` | 300.0 | Maximum total execution time |
| `verbose` | False | Show step-by-step reasoning output |

---

## Mode Selection Guide

### Decision Tree

```
Is your query about a specific entity or relationship?
├─ YES → Use LOCAL mode
│
└─ NO → Is it asking for an overview or summary?
         ├─ YES → Use GLOBAL mode
         │
         └─ NO → Does it require multiple perspectives?
                  ├─ YES → Is it a comparison or complex analysis?
                  │        ├─ YES → Use MULTIHOP mode
                  │        └─ NO → Use MIX mode
                  │
                  └─ NO → Use HYBRID mode (default)
```

### Quick Reference

| Query Type | Recommended Mode |
|------------|------------------|
| "What is the X table?" | `local` |
| "Find the Y function" | `local` |
| "Overview of system" | `global` |
| "Summarize the workflow" | `global` |
| "How does X connect to Y?" | `hybrid` |
| "General question" | `hybrid` |
| "Compare X with Y" | `multihop` |
| "Trace data from A to Z" | `multihop` |
| "All references to X" | `mix` |
| "Comprehensive analysis" | `mix` |

---

## CLI Usage Examples

### Basic Queries

```bash
# Default (hybrid) mode
python hybridrag.py query --text "patient appointments"

# Specific mode
python hybridrag.py query --text "APPOINTMENT table" --mode local
python hybridrag.py query --text "billing overview" --mode global
python hybridrag.py query --text "charge processing" --mode hybrid
python hybridrag.py query --text "SELECT statements" --mode naive
python hybridrag.py query --text "complete analysis" --mode mix
```

### Multi-Hop Queries

```bash
# Basic multi-hop
python hybridrag.py query --text "Compare registration and billing" --multihop

# Verbose multi-hop (shows reasoning steps)
python hybridrag.py query --text "Trace patient data flow" --multihop --verbose
```

### Context-Only Mode

```bash
# Get raw context without LLM generation
python hybridrag.py query --text "appointments" --mode local --context-only
```

---

## Interactive Mode Commands

Enter interactive mode:
```bash
python hybridrag.py interactive
```

### Available Commands

| Command | Description |
|---------|-------------|
| `:local` | Switch to local mode |
| `:global` | Switch to global mode |
| `:hybrid` | Switch to hybrid mode |
| `:naive` | Switch to naive mode |
| `:mix` | Switch to mix mode |
| `:multihop` | Toggle multi-hop reasoning |
| `:context` | Toggle context-only mode |
| `:verbose` | Toggle verbose output |
| `:stats` | Show database statistics |
| `:help` | Show help message |
| `:quit` | Exit interactive mode |

---

## Python API

### Using HybridLightRAGCore Directly

```python
from src.lightrag_core import HybridLightRAGCore
from config.config import HybridRAGConfig

# Initialize
config = HybridRAGConfig()
core = HybridLightRAGCore(config)

# Query with specific mode
result = await core.aquery(
    query="Find appointment tables",
    mode="local",
    top_k=10,
    max_entity_tokens=6000
)

# Convenience methods
result = await core.local_query("appointments", top_k=10)
result = await core.global_query("workflow overview", top_k=10)
result = await core.hybrid_query("appointment billing", top_k=10)

# Extract context only
context = await core.extract_context("appointments", mode="hybrid")
```

### Using Multi-Hop Reasoning

```python
from src.lightrag_core import HybridLightRAGCore
from src.agentic_rag import create_agentic_rag
from config.config import HybridRAGConfig

# Initialize
config = HybridRAGConfig()
core = HybridLightRAGCore(config)
await core._ensure_initialized()

# Create agentic RAG
agentic = create_agentic_rag(
    lightrag_core=core,
    model_name="azure/gpt-4o",
    max_internal_steps=8,
    verbose=True
)

# Execute multi-hop query
result = await agentic.execute_multi_hop_reasoning(
    query="Compare registration and billing workflows",
    timeout_seconds=300.0
)

print(f"Answer: {result['answer']}")
print(f"Steps: {result['steps_taken']}")
print(f"Time: {result['execution_time']:.1f}s")
```

---

## Performance Considerations

### Mode Performance Comparison

| Mode | Speed | Token Usage | Best For |
|------|-------|-------------|----------|
| `naive` | Fastest | Low | Simple searches |
| `local` | Fast | Medium | Entity lookup |
| `global` | Fast | Medium | Summaries |
| `hybrid` | Medium | Medium-High | General queries |
| `mix` | Slower | High | Comprehensive |
| `multihop` | Slowest | Highest | Complex analysis |

### Optimization Tips

1. **Start with `hybrid`** for unknown queries
2. **Use `local`** when you know the entity name
3. **Use `global`** for "overview" or "summary" queries
4. **Reserve `multihop`** for genuinely complex analytical questions
5. **Adjust `top_k`** based on needed coverage (lower = faster)
6. **Use `--context-only`** when you want to process results yourself

---

## Troubleshooting

### Multi-Hop Not Working

If multi-hop mode fails:

1. **Check PromptChain installation**:
   ```bash
   pip show promptchain
   # If missing:
   pip install git+https://github.com/gyasis/PromptChain.git
   ```

2. **Check API key** for the model being used

3. **Try with verbose mode** to see where it fails:
   ```bash
   python hybridrag.py query --text "test" --multihop --verbose
   ```

### Mode Returns Empty Results

1. **Verify data was ingested**:
   ```bash
   python hybridrag.py check-db
   ```

2. **Try different mode** - some queries work better with specific modes

3. **Check query specificity** - too vague queries may not match entities

---

## Further Reading

- [LightRAG Documentation](https://github.com/HKUDS/LightRAG)
- [PromptChain Documentation](https://github.com/gyasis/PromptChain)
- [HybridRAG README](../README.md)
- [Quick Start Guide](../QUICK_START_SPECSTORY.md)
