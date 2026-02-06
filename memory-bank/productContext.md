# HybridRAG Product Context

## Why This Project Exists

### The Problem
Software development generates vast amounts of conversation history in tools like JIRA/SpecStory. This knowledge is trapped in individual markdown files scattered across project folders, making it difficult to:
- Find previous solutions to similar problems
- Recall architectural decisions and their rationale
- Access cross-project knowledge and patterns
- Leverage past work to accelerate current development

### The Solution
HybridRAG transforms scattered conversation histories into a queryable knowledge graph:
1. **Ingests** SpecStory conversation files from multiple projects
2. **Builds** a LightRAG knowledge graph with entities and relationships
3. **Enables** semantic search via CLI and Claude Desktop (MCP)
4. **Monitors** source folders for automatic delta ingestion

## Value Propositions

### For AI Assistants (Claude Code)
- **Instant Access**: Query past work via MCP tools without manual file searches
- **Context Enrichment**: Retrieve relevant conversations to inform current decisions
- **Cross-Project Learning**: Find patterns across multiple development efforts
- **Historical Continuity**: Understand what was tried before and why

### For Developers
- **Knowledge Preservation**: Developer conversations persist beyond project completion
- **Faster Ramp-Up**: New team members can search historical context
- **Decision Traceability**: Find why certain approaches were chosen
- **Pattern Recognition**: Discover recurring issues and proven solutions

### For Development Teams
- **Organizational Memory**: Tribal knowledge becomes searchable
- **Best Practices Discovery**: Identify successful patterns across projects
- **Error Prevention**: Learn from past mistakes in previous projects
- **Knowledge Sharing**: Break down knowledge silos between teams

## Problems Solved

### 1. Information Fragmentation
**Before**: 27+ SpecStory folders across dev tree, thousands of markdown files
**After**: Single unified knowledge graph searchable by natural language

### 2. Manual Context Discovery
**Before**: grep/find/IDE search for relevant conversations
**After**: Semantic search finds conceptually related content, not just keyword matches

### 3. Static Documentation
**Before**: Documentation quickly becomes stale and disconnected from actual work
**After**: Live knowledge base automatically updated from ongoing conversations

### 4. Tool Lock-In
**Before**: Knowledge tied to specific LLM provider (OpenAI, Azure, etc.)
**After**: Multi-provider support via LiteLLM (Azure, OpenAI, Anthropic, Gemini, Ollama)

### 5. Single-Database Limitation
**Before**: Would need separate tool instances for different knowledge bases
**After**: Registry system manages multiple databases, switch with `--db name`

### 6. Backend Ambiguity
**Before**: "Which backend is serving this query?" was unclear
**After**: Every MCP response shows backend metadata (postgres, json, etc.)

## Integration Points

### Claude Desktop (Primary)
- MCP server exposes 8 query tools
- Tools appear in Claude's tool palette
- Background task support for long-running queries
- Diagnostic logging for debugging

### Command Line Interface
- Interactive query mode with history
- One-shot queries for scripting
- Database management commands
- Watcher control (start/stop/status)

### Systemd Services (Linux)
- Persistent watchers that survive reboots
- Per-database service instances
- Centralized log management

## Success Metrics

### Technical
- :white_check_mark: 7K+ entities ingested from SpecStory files
- :white_check_mark: 7K+ relationships extracted
- :white_check_mark: 31K+ rows in PostgreSQL backend
- :white_check_mark: All 8 MCP tools verified working
- :white_check_mark: Watcher covering 27 SpecStory folders

### Functional
- :white_check_mark: Query results return relevant conversations
- :white_check_mark: Delta ingestion processes only new files
- :white_check_mark: Backend metadata transparent to users
- :white_check_mark: Registry auto-resolution eliminates env var config

### User Experience
- :white_check_mark: Single command to query any database: `hybridrag --db specstory query --text "..."`
- :white_check_mark: CLI installable: `pip install -e .` makes `hybridrag` command available
- :white_check_mark: Clear error messages with credential masking
- :white_check_mark: No more "I can't find" responses from MCP tools

## Future Opportunities

### Enhanced Analysis
- Conversation threading and timeline visualization
- Entity relationship graph exploration
- Trend analysis across projects over time
- Topic clustering and evolution tracking

### Advanced Ingestion
- Real-time ingestion as conversations happen
- Git commit message correlation
- Pull request and code review integration
- Test result and CI/CD log ingestion

### Collaborative Features
- Shared annotations on retrieved conversations
- Bookmark and tag management
- Team knowledge curation workflows
- Cross-team knowledge sharing

### Intelligence Layer
- Automatic insight extraction
- Proactive pattern detection
- Recommendation engine for similar problems
- Automated documentation generation from conversations
