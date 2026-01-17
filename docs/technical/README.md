# Technical Documentation

Implementation notes, bug fixes, and technical clarifications.

## Documents

### AGENTIC_STEP_CLARIFICATION.md
**Purpose:** Clarifies agentic step processing implementation

**Topics Covered:**
- AgenticStepProcessor architecture
- Tool calling mechanisms
- Multi-step reasoning flow
- History management strategies

**Use When:** Understanding or debugging agentic workflows

---

### INCREMENTAL_UPDATE_FIX.md
**Purpose:** Documents incremental update bug fix

**Topics Covered:**
- Issue: Duplicate entries on incremental updates
- Root cause analysis
- Solution implementation
- Testing verification

**Use When:** Working on incremental ingestion features

---

### LightRAG_Cliff_Notes.md
**Purpose:** Quick reference for LightRAG usage

**Topics Covered:**
- Core concepts and architecture
- Query modes explained
- Storage structure
- Common patterns and gotchas

**Use When:** Quick lookup of LightRAG functionality

---

### QUICK_COMPARISON.md
**Purpose:** Feature comparison matrices

**Topics Covered:**
- Query mode comparisons
- Performance benchmarks
- Storage backend differences
- API feature matrix

**Use When:** Choosing between different approaches

---

### RATE_LIMITING_IMPROVEMENTS.md
**Purpose:** Rate limiting strategies and implementation

**Topics Covered:**
- API rate limit handling
- Backoff strategies
- Batch processing optimization
- Cost management techniques

**Use When:** Optimizing API usage or handling rate limits

---

## Adding Technical Documentation

When documenting technical details:

1. **Problem Statement** - What issue/challenge
2. **Analysis** - Root cause or investigation
3. **Solution** - How it was solved
4. **Implementation** - Code changes or approach
5. **Testing** - How to verify it works
6. **References** - Related code, issues, or docs

## Document Categories

| Category | Examples | When to Use |
|----------|----------|-------------|
| **Bug Fixes** | INCREMENTAL_UPDATE_FIX.md | Document significant fixes |
| **Clarifications** | AGENTIC_STEP_CLARIFICATION.md | Explain complex features |
| **Quick References** | LightRAG_Cliff_Notes.md | Provide quick lookups |
| **Comparisons** | QUICK_COMPARISON.md | Help with decision-making |
| **Optimization** | RATE_LIMITING_IMPROVEMENTS.md | Performance improvements |

## Related Documentation

- **PRDs** (../prd/) - Feature specifications
- **Guides** (../guides/) - User documentation
- **Source Code** (../../src/) - Implementation details
