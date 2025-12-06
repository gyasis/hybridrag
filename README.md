# HybridRAG System

A comprehensive knowledge graph-based retrieval system that combines folder watching, document ingestion, and intelligent search capabilities using LightRAG and PromptChain.

## 🚀 Features

### 📁 Intelligent Folder Monitoring
- **Recursive watching** of multiple directories
- **Real-time detection** of new and modified files
- **Smart filtering** by file extensions and size limits
- **Deduplication** using SHA256 hashing
- **SQLite tracking** of processed files

### ⚡ Advanced Document Processing
- **Multi-format support**: TXT, MD, PDF, HTML, JSON, YAML, CSV, code files
- **Intelligent chunking** with token-aware splitting
- **PDF OCR capabilities** (optional)
- **Metadata preservation** throughout pipeline
- **Batch processing** with configurable concurrency

### 🧠 Sophisticated Search Interface
- **Multi-mode queries**: Local, Global, Hybrid, Agentic
- **Simple search**: Direct LightRAG queries
- **Agentic search**: Multi-hop reasoning using PromptChain
- **Multi-query synthesis**: Combine multiple searches
- **Interactive CLI** with command history

### 🔄 Production-Ready Architecture
- **Async/await** throughout for performance
- **Graceful error handling** and recovery
- **Comprehensive logging** with rotation
- **Health monitoring** and statistics
- **Signal handling** for clean shutdown

## 📋 Prerequisites

- Python 3.8+
- Azure API key (preferred) or OpenAI API key
- Optional: Other LLM provider keys (Anthropic, Gemini) for alternative models

## 🛠️ Installation

1. **Clone or create the project directory**:
```bash
mkdir hybridrag && cd hybridrag
```

2. **Install dependencies**:
```bash
pip install -r requirements.txt
```

3. **Install PromptChain** (for agentic features):
```bash
pip install git+https://github.com/gyasis/PromptChain.git
```

4. **Setup environment**:
```bash
cp .env.example .env
# Edit .env and add your API keys
```

## 🎯 Quick Start

### 1. First-Time Setup
```bash
# Activate environment
source .venv/bin/activate  # or: uv run

# Check database status
python hybridrag.py check-db

# Ingest data
python hybridrag.py ingest --folder ./data
```

### 2. Query Your Data
```bash
# Interactive mode (recommended)
python hybridrag.py interactive

# One-shot query
python hybridrag.py query --text "Find appointment tables" --mode hybrid

# Advanced query with multi-hop reasoning
python hybridrag.py query --text "..." --agentic --use-promptchain
```

### 3. Manage Your System
```bash
# Check status
python hybridrag.py status

# Database info
python hybridrag.py check-db
```

## 📖 Comprehensive Usage

See [USAGE.md](docs/guides/USAGE.md) for complete documentation including:
- All available commands and flags
- Query mode explanations (local/global/hybrid/naive/mix)
- Database management
- Advanced features
- Troubleshooting guide

### Common Commands

```bash
# Ingestion
python hybridrag.py ingest --folder ./data
python hybridrag.py ingest --folder ./data --db-action fresh  # Start fresh
python hybridrag.py ingest --folder ./data --db-action add    # Add to existing

# Ingestion with metadata and scripting flags
python hybridrag.py ingest --folder ./data --metadata "project=myproject" --yes --quiet

# Queries
python hybridrag.py interactive                               # Interactive CLI
python hybridrag.py query --text "..." --mode hybrid         # One-shot query
python hybridrag.py query --text "..." --agentic             # Multi-hop reasoning

# Management
python hybridrag.py status                                    # System status
python hybridrag.py check-db                                  # Database info
python hybridrag.py db-info                                   # Detailed database info with sources
python hybridrag.py list-dbs                                  # List all databases
python hybridrag.py --help                                    # Show help
```

### Ingestion Flags

| Flag | Description |
|------|-------------|
| `--folder PATH` | Folder(s) to ingest (can specify multiple) |
| `--db-action {use,add,fresh}` | Database action: use existing, add to existing, or start fresh |
| `--metadata KEY=VALUE` | Add metadata (can specify multiple, e.g., `--metadata project=foo --metadata version=1`) |
| `--yes`, `-y` | Skip confirmation prompts (for scripted use) |
| `--quiet`, `-q` | Suppress verbose output, show only progress bar |
| `--recursive` | Watch folders recursively (default: true) |
| `--multiprocess` | Use multiprocess architecture |

### Multi-Project Ingestion Scripts

For ingesting multiple `.specstory` folders at once:

```bash
# Ingest all .specstory folders into a SINGLE database (recommended)
./scripts/ingest_specstory_folders.sh /path/to/jira-issues fresh

# Ingest each project into SEPARATE databases
./scripts/ingest_separate_databases.sh /path/to/projects

# Watch for changes and auto-ingest
./scripts/watch_specstory_folders.sh /path/to/jira-issues

# Use specific model (e.g., Gemini)
./scripts/ingest_specstory_folders.sh /path/to/projects fresh gemini/gemini-pro
./scripts/watch_specstory_folders.sh /path/to/projects 300 anthropic/claude-opus
```

Features:
- **Progress bar**: tqdm-based progress during ingestion
- **Restartable**: Queue-based architecture - files stay queued until processed
- **Metadata tagging**: Each project tagged with `project=NAME` and `source_path`
- **Error tracking**: Failed files moved to `ingestion_queue/errors/`

## ⚙️ Configuration

The system uses a hierarchical configuration in `config/config.py`:

### LightRAG Configuration
```python
@dataclass
class LightRAGConfig:
    working_dir: str = "./lightrag_db"
    model_name: str = "azure/gpt-5.1"           # Default: Azure GPT-5.1
    embedding_model: str = "azure/text-embedding-3-small"
    chunk_size: int = 1200
    chunk_overlap: int = 100
```

**Model Override**: You can override models at runtime:
```bash
# Use Gemini instead of Azure
python hybridrag.py --model gemini/gemini-pro ingest --folder ./data

# Use Anthropic Claude
python hybridrag.py --model anthropic/claude-opus query --text "your query"

# Set via environment variable
export LIGHTRAG_MODEL="openai/gpt-4o"
python hybridrag.py interactive
```

### Ingestion Configuration
```python
@dataclass
class IngestionConfig:
    watch_folders: List[str] = ["./data"]
    file_extensions: List[str] = [".txt", ".md", ".pdf", ".json", ...]
    recursive: bool = True
    batch_size: int = 10
    max_file_size_mb: float = 50.0
```

### Search Configuration
```python
@dataclass
class SearchConfig:
    default_mode: str = "hybrid"
    default_top_k: int = 10
    enable_reranking: bool = True
    enable_context_accumulation: bool = True
```

## 📊 Query Modes

### Local Mode
Focus on specific entities and relationships:
```python
result = await search_interface.simple_search(
    "machine learning algorithms", 
    mode="local"
)
```

### Global Mode  
High-level overviews and summaries:
```python
result = await search_interface.simple_search(
    "overview of AI technologies",
    mode="global" 
)
```

### Hybrid Mode (Recommended)
Combines local and global approaches:
```python
result = await search_interface.simple_search(
    "deep learning applications",
    mode="hybrid"
)
```

### Agentic Mode
Multi-hop reasoning with tool access:
```python
result = await search_interface.agentic_search(
    "Compare machine learning and deep learning approaches",
    max_steps=5
)
```

## 🔧 Advanced Features

### Custom Document Processing
Extend the `DocumentProcessor` class to handle additional file types:

```python
class CustomDocumentProcessor(DocumentProcessor):
    def read_file(self, file_path: str, extension: str) -> str:
        if extension == '.custom':
            return self._read_custom_format(file_path)
        return super().read_file(file_path, extension)
```

### Custom Search Tools
Add domain-specific tools for agentic search:

```python
def custom_search_tool(query: str) -> str:
    # Your custom search logic
    return results

# Register with search interface
search_interface.register_tool(custom_search_tool)
```

### Monitoring and Metrics
The system provides comprehensive monitoring:

```python
# Get detailed statistics
stats = await system.get_system_status()

# Monitor ingestion progress
watcher_stats = folder_watcher.get_queue_stats()
ingestion_stats = ingestion_pipeline.get_stats()

# Track search performance
search_stats = search_interface.get_stats()
```

## 📁 Project Structure

```
hybridrag/
├── src/                      # Core system components
│   ├── folder_watcher.py      # File monitoring system
│   ├── ingestion_pipeline.py  # Document processing
│   ├── lightrag_core.py       # LightRAG interface
│   ├── search_interface.py    # Search functionality
│   ├── process_manager.py     # Multiprocess orchestration
│   └── status_display.py      # Status reporting
├── config/
│   └── config.py              # Configuration classes
├── tests/                    # Test suite
│   ├── test_hybridrag.py      # Integration tests
│   ├── test_multiprocess.py   # Multiprocess tests
│   └── ...                    # Additional tests
├── scripts/                  # Utility scripts
│   ├── deeplake_to_lightrag.py      # DeepLake ingestion
│   ├── folder_to_lightrag.py        # Folder ingestion
│   └── ...                          # Other utilities
├── examples/                 # Example usage patterns
│   ├── lightrag_query_demo.py       # Interactive demo
│   ├── query_with_promptchain.py    # PromptChain examples
│   └── ...                          # Quick tests
├── legacy/                   # Deprecated entry points
│   ├── main.py                # Old main script
│   ├── simple_main.py         # Old simple version
│   └── ...                    # Other old scripts
├── memory-bank/             # Project documentation
│   ├── projectbrief.md        # Project overview
│   ├── progress.md            # Progress tracking
│   └── ...                    # Additional docs
├── data/                    # Default watch folder
├── lightrag_db/            # LightRAG knowledge graph
├── ingestion_queue/        # Processing queue
├── hybridrag.py            # ⭐ Unified entry point
├── USAGE.md                # Complete usage guide
├── requirements.txt        # Dependencies
├── .env.example            # Environment template
└── README.md               # This file
```

**Note:** Use `hybridrag.py` as the main entry point. Scripts in `legacy/` are deprecated.

## 🚨 Error Handling

The system implements comprehensive error handling:

- **File Processing Errors**: Files with errors are moved to `ingestion_queue/errors/`
- **API Rate Limits**: Built-in retry logic with exponential backoff
- **Network Issues**: Graceful degradation and fallback mechanisms
- **Resource Exhaustion**: Memory and disk usage monitoring
- **Graceful Shutdown**: Signal handling for clean termination

## 📈 Performance Tuning

### Ingestion Performance
- Adjust `batch_size` for throughput vs. memory usage
- Configure `max_concurrent_ingestions` based on system resources
- Set appropriate `poll_interval` for responsiveness vs. CPU usage

### Search Performance
- Use `local` mode for specific entity queries
- Use `global` mode for broad overviews
- Use `hybrid` mode for balanced results
- Enable `reranking` for improved relevance

### Memory Management
- Configure `chunk_size` and `chunk_overlap` for optimal indexing
- Set `max_file_size_mb` to prevent memory issues
- Monitor LightRAG database size and consider periodic cleanup

## 🔍 Troubleshooting

### Common Issues

1. **Import Errors**: Ensure PromptChain is installed for agentic features
2. **API Rate Limits**: Reduce batch sizes and increase delays
3. **Memory Issues**: Lower chunk sizes and concurrent processing
4. **File Processing**: Check file permissions and encoding
5. **LightRAG Errors**: Verify API key for your model provider (AZURE_API_KEY, OPENAI_API_KEY, etc.)

### Debug Mode
Enable verbose logging:
```bash
export HYBRIDRAG_LOG_LEVEL=DEBUG
python main.py search
```

### Health Checks
Regular system health monitoring:
```bash
python main.py status | jq '.health'
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- **LightRAG**: Knowledge graph construction and querying
- **PromptChain**: Multi-hop reasoning and agent orchestration
- **LiteLLM**: Unified interface for multiple LLM providers (Azure, OpenAI, Anthropic, Gemini)
- **Community**: Various document processing libraries

---

**Happy Searching! 🔍✨**