#!/usr/bin/env python3
"""
HybridRAG - Unified Entry Point
================================
Consolidated interface for all HybridRAG functionality with comprehensive CLI.

Usage Examples:
    # Interactive query mode
    python hybridrag.py interactive

    # One-shot queries
    python hybridrag.py query --text "Find appointment tables" --mode hybrid
    python hybridrag.py query --text "..." --mode local --agentic

    # Ingestion
    python hybridrag.py ingest --folder ./data
    python hybridrag.py ingest --folder ./data --db-action fresh

    # Management
    python hybridrag.py status
    python hybridrag.py check-db

Author: HybridRAG System
Date: 2025-11-10
"""

import asyncio
import argparse
import logging
import sys
import os
import json
import shutil
from pathlib import Path
from typing import Optional, List
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Load environment
load_dotenv()

# Import metadata manager
from src.database_metadata import DatabaseMetadata, list_all_databases

# Import database registry
from src.database_registry import (
    DatabaseRegistry, DatabaseEntry, SourceType,
    get_registry, resolve_database, get_config_for_script,
    register_specstory_database, register_schema_database,
    get_watcher_pid_file, is_watcher_running
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_api_key_for_model(model_name: str) -> Optional[str]:
    """
    Get the appropriate API key based on model provider prefix.

    Supports: azure/, openai/, anthropic/, gemini/, ollama/
    Falls back gracefully if specific key not found.
    """
    model_lower = model_name.lower()

    # Determine provider from model prefix
    if model_lower.startswith('azure/'):
        key = os.getenv("AZURE_API_KEY")
        if key:
            return key
        # Fall back to OpenAI key (LiteLLM uses it for Azure too)
        return os.getenv("OPENAI_API_KEY")

    elif model_lower.startswith('anthropic/') or model_lower.startswith('claude'):
        return os.getenv("ANTHROPIC_API_KEY")

    elif model_lower.startswith('gemini/') or model_lower.startswith('google/'):
        return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

    elif model_lower.startswith('ollama/'):
        # Ollama doesn't need an API key for local models
        return "ollama-local"

    elif model_lower.startswith('openai/') or not '/' in model_lower:
        # OpenAI or bare model name defaults to OpenAI
        return os.getenv("OPENAI_API_KEY")

    # Generic fallback: try Azure first, then OpenAI
    return os.getenv("AZURE_API_KEY") or os.getenv("OPENAI_API_KEY")


class HybridRAGCLI:
    """Unified CLI for HybridRAG operations."""

    def __init__(self, args):
        """Initialize CLI with parsed arguments."""
        self.args = args
        self.config_path = args.config if hasattr(args, 'config') else None

        # Handle --db flag for named database references
        self._db_entry = None
        db_name = getattr(args, 'db', None)

        if db_name:
            # Look up database by name in registry
            working_dir, db_entry = resolve_database(db_name)
            if db_entry:
                self._db_entry = db_entry
                self.working_dir = db_entry.path
                # Use database's model if set and no CLI override
                cli_model = getattr(args, 'model', None)
                if not cli_model and db_entry.model:
                    self.llm_model = db_entry.model
                else:
                    self.llm_model = cli_model if cli_model else os.getenv("LIGHTRAG_MODEL", "azure/gpt-5.1")
            else:
                # Treat as path fallback
                self.working_dir = working_dir
                self.llm_model = args.model if hasattr(args, 'model') and args.model else os.getenv("LIGHTRAG_MODEL", "azure/gpt-5.1")
        else:
            self.working_dir = args.working_dir if hasattr(args, 'working_dir') else "./lightrag_db"
            # Model override support: CLI > env var > default
            self.llm_model = args.model if hasattr(args, 'model') and args.model else os.getenv("LIGHTRAG_MODEL", "azure/gpt-5.1")

        self.embed_model = args.embed_model if hasattr(args, 'embed_model') and args.embed_model else os.getenv("LIGHTRAG_EMBED_MODEL", "azure/text-embedding-3-small")

    async def run(self):
        """Execute the requested command."""
        command = self.args.command

        if command == 'query':
            await self.run_query()
        elif command == 'interactive':
            await self.run_interactive()
        elif command == 'ingest':
            await self.run_ingest()
        elif command == 'status':
            await self.show_status()
        elif command == 'check-db':
            await self.check_database()
        elif command == 'list-dbs':
            await self.list_databases()
        elif command == 'db-info':
            await self.show_database_info()
        elif command == 'db':
            await self.run_db_command()
        elif command == 'monitor':
            self.run_monitor()
        else:
            print(f"❌ Unknown command: {command}")
            return 1

        return 0

    # ========================================
    # Query Commands
    # ========================================

    async def run_query(self):
        """Execute one-shot query."""
        if not self.args.text:
            print("❌ Query mode requires --text parameter")
            return

        mode = self.args.mode
        use_agentic = self.args.agentic
        use_multihop = self.args.multihop if hasattr(self.args, 'multihop') else False
        use_promptchain = self.args.use_promptchain
        verbose = self.args.verbose if hasattr(self.args, 'verbose') else False

        print(f"🔍 Query: {self.args.text}")
        print(f"   Mode: {mode}, Multihop: {use_multihop}, Agentic: {use_agentic}, PromptChain: {use_promptchain}")

        if use_multihop:
            await self._query_with_multihop(self.args.text, verbose)
        elif use_promptchain:
            await self._query_with_promptchain(self.args.text, mode, use_agentic)
        else:
            await self._query_with_lightrag(self.args.text, mode, use_agentic)

    async def run_interactive(self):
        """Run interactive query interface with retrieval."""
        from src.lightrag_core import HybridLightRAGCore
        from config.config import HybridRAGConfig

        print("\n" + "="*70)
        print("🔍 HybridRAG Interactive Query Interface")
        print("="*70)

        # Initialize core with working directory
        config = HybridRAGConfig()
        config.lightrag.working_dir = self.working_dir
        config.lightrag.model_name = self.llm_model
        config.lightrag.embedding_model = self.embed_model

        print(f"\n   Database: {self.working_dir}")
        print(f"   LLM: {self.llm_model}")
        print(f"   Embed: {self.embed_model}")
        print("\n   Initializing...")

        core = HybridLightRAGCore(config)
        await core._ensure_initialized()

        # Initialize agentic RAG for multi-hop (lazy loaded)
        agentic_rag = None

        print("   Ready!")

        print("\nCommands:")
        print("  :local, :global, :hybrid, :naive, :mix  - Switch query mode")
        print("  :multihop                               - Multi-hop reasoning mode")
        print("  :context                                - Toggle context-only mode")
        print("  :verbose                                - Toggle verbose mode")
        print("  :stats                                  - Show database stats")
        print("  :help                                   - Show help")
        print("  :quit                                   - Exit")
        print("\nOr just type your query directly!")
        print("="*70)

        current_mode = "hybrid"
        context_only = False
        verbose_mode = False
        multihop_mode = False

        while True:
            try:
                if multihop_mode:
                    mode_indicator = "multihop"
                else:
                    mode_indicator = f"{current_mode}" + (" ctx" if context_only else "")
                user_input = input(f"\n[{mode_indicator}]> ").strip()

                if not user_input:
                    continue

                # Handle commands
                if user_input.startswith(':'):
                    cmd = user_input[1:].lower()

                    if cmd in ['quit', 'exit', 'q']:
                        print("👋 Goodbye!")
                        break
                    elif cmd in ['local', 'global', 'hybrid', 'naive', 'mix']:
                        current_mode = cmd
                        multihop_mode = False
                        print(f"✅ Switched to {current_mode} mode")
                        continue
                    elif cmd == 'multihop':
                        multihop_mode = not multihop_mode
                        if multihop_mode:
                            print("✅ Multi-hop reasoning enabled (uses LightRAG tools with AgenticStepProcessor)")
                            print("   The system will perform multi-step reasoning to answer complex queries.")
                        else:
                            print(f"❌ Multi-hop disabled, back to {current_mode} mode")
                        continue
                    elif cmd == 'context':
                        context_only = not context_only
                        print(f"{'✅ Context-only' if context_only else '❌ Full response'} mode")
                        continue
                    elif cmd == 'verbose':
                        verbose_mode = not verbose_mode
                        print(f"{'✅ Verbose' if verbose_mode else '❌ Quiet'} mode")
                        continue
                    elif cmd == 'stats':
                        stats = core.get_stats()
                        print("\n📊 Database Stats:")
                        print(f"   Working Dir: {stats.get('working_directory', 'N/A')}")
                        print(f"   Initialized: {stats.get('initialized', 'N/A')}")
                        print(f"   Model: {stats.get('model_name', 'N/A')}")
                        print(f"   Graph Files: {stats.get('graph_files', 'N/A')}")
                        if stats.get('storage_info'):
                            print("   Storage:")
                            for name, size in stats['storage_info'].items():
                                print(f"     {name}: {size}")
                        continue
                    elif cmd == 'help':
                        self._print_help()
                        continue
                    else:
                        print(f"❌ Unknown command: {cmd}")
                        continue

                # Execute query based on mode
                if multihop_mode:
                    # Multi-hop reasoning using AgenticHybridRAG
                    print("🧠 Multi-hop reasoning...")

                    # Lazy initialize agentic RAG
                    if agentic_rag is None:
                        try:
                            from src.agentic_rag import create_agentic_rag
                            agentic_rag = create_agentic_rag(
                                lightrag_core=core,
                                model_name=self.llm_model,
                                max_internal_steps=8,
                                verbose=verbose_mode
                            )
                            print("   Initialized AgenticHybridRAG")
                        except ImportError as e:
                            print(f"❌ Multi-hop requires PromptChain: {e}")
                            print("   Install with: pip install git+https://github.com/gyasis/PromptChain.git")
                            continue
                        except Exception as e:
                            print(f"❌ Failed to initialize multi-hop: {e}")
                            continue

                    # Update verbose mode if changed
                    if agentic_rag:
                        agentic_rag.verbose = verbose_mode
                        agentic_rag.tools_provider.verbose = verbose_mode

                    # Execute multi-hop reasoning
                    result = await agentic_rag.execute_multi_hop_reasoning(
                        query=user_input,
                        timeout_seconds=300.0
                    )

                    # Display results
                    if result.get('success'):
                        print(f"\n💡 Response:")
                        print("-" * 70)
                        print(result.get('result', 'No result'))
                        print("-" * 70)

                        # Show reasoning steps if verbose
                        if verbose_mode and result.get('reasoning_steps'):
                            print("\n🔍 Reasoning Steps:")
                            for i, step in enumerate(result['reasoning_steps'], 1):
                                print(f"   {i}. {step}")

                        print(f"\n⏱️  {result.get('execution_time', 0):.2f}s | Steps: {len(result.get('reasoning_steps', []))} | Contexts: {len(result.get('accumulated_contexts', []))}")
                    else:
                        print(f"\n❌ Multi-hop failed: {result.get('error', 'Unknown error')}")
                        if result.get('reasoning_steps'):
                            print("\n🔍 Partial reasoning steps:")
                            for i, step in enumerate(result['reasoning_steps'], 1):
                                print(f"   {i}. {step}")

                else:
                    # Standard LightRAG query
                    print("🔍 Searching...")
                    result = await core.aquery(
                        user_input,
                        mode=current_mode,
                        only_need_context=context_only
                    )

                    print(f"\n{'📚 Context:' if context_only else '💡 Response:'}")
                    print("-" * 70)
                    # Result is a QueryResult dataclass, access .result for the text
                    print(result.result if hasattr(result, 'result') else result)
                    print("-" * 70)
                    if hasattr(result, 'execution_time'):
                        print(f"⏱️  {result.execution_time:.2f}s | Mode: {result.mode}")

            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
            except EOFError:
                break
            except Exception as e:
                print(f"❌ Error: {e}")
                import traceback
                traceback.print_exc()

    async def _query_with_lightrag(self, query_text: str, mode: str, agentic: bool):
        """Execute query using LightRAG with LiteLLM integration."""
        from src.lightrag_core import HybridLightRAGCore
        from config.config import HybridRAGConfig

        # Initialize config with CLI overrides
        config = HybridRAGConfig()
        config.lightrag.working_dir = self.working_dir
        config.lightrag.model_name = self.llm_model
        config.lightrag.embedding_model = self.embed_model

        print(f"   Using LLM: {self.llm_model}, Embed: {self.embed_model}")

        # Initialize HybridLightRAGCore (uses LiteLLM for Azure/OpenAI/etc.)
        core = HybridLightRAGCore(config)

        # Execute query
        result = await core.aquery(query_text, mode=mode)

        print("\n💡 Response:")
        print("-" * 70)
        # Result is a QueryResult dataclass, access .result for the text
        print(result.result if hasattr(result, 'result') else result)
        print("-" * 70)
        if hasattr(result, 'execution_time'):
            print(f"   Execution time: {result.execution_time:.2f}s")

    async def _query_with_multihop(self, query_text: str, verbose: bool = False):
        """Execute query using multi-hop reasoning with LightRAG tools."""
        from src.lightrag_core import HybridLightRAGCore
        from config.config import HybridRAGConfig

        print("🧠 Using multi-hop reasoning with LightRAG tools...")

        # Initialize config with CLI overrides
        config = HybridRAGConfig()
        config.lightrag.working_dir = self.working_dir
        config.lightrag.model_name = self.llm_model
        config.lightrag.embedding_model = self.embed_model

        print(f"   Using LLM: {self.llm_model}")
        print(f"   Database: {self.working_dir}")

        # Initialize HybridLightRAGCore
        core = HybridLightRAGCore(config)
        await core._ensure_initialized()

        # Initialize AgenticHybridRAG
        try:
            from src.agentic_rag import create_agentic_rag
            agentic_rag = create_agentic_rag(
                lightrag_core=core,
                model_name=self.llm_model,
                max_internal_steps=8,
                verbose=verbose
            )
        except ImportError as e:
            print(f"❌ Multi-hop requires PromptChain: {e}")
            print("   Install with: pip install git+https://github.com/gyasis/PromptChain.git")
            return
        except Exception as e:
            print(f"❌ Failed to initialize multi-hop: {e}")
            return

        # Execute multi-hop reasoning
        print("   Executing multi-hop reasoning...")
        result = await agentic_rag.execute_multi_hop_reasoning(
            query=query_text,
            timeout_seconds=300.0
        )

        # Display results
        if result.get('success'):
            print("\n💡 Response:")
            print("-" * 70)
            print(result.get('result', 'No result'))
            print("-" * 70)

            # Show reasoning steps if verbose
            if verbose and result.get('reasoning_steps'):
                print("\n🔍 Reasoning Steps:")
                for i, step in enumerate(result['reasoning_steps'], 1):
                    print(f"   {i}. {step}")

            print(f"\n⏱️  {result.get('execution_time', 0):.2f}s | Steps: {len(result.get('reasoning_steps', []))} | Contexts: {len(result.get('accumulated_contexts', []))}")
        else:
            print(f"\n❌ Multi-hop failed: {result.get('error', 'Unknown error')}")
            if result.get('reasoning_steps'):
                print("\n🔍 Partial reasoning steps:")
                for i, step in enumerate(result['reasoning_steps'], 1):
                    print(f"   {i}. {step}")

    async def _query_with_promptchain(self, query_text: str, mode: str, agentic: bool):
        """Execute query using PromptChain for advanced reasoning."""
        print("🧠 Using PromptChain for advanced multi-hop reasoning...")

        # Import PromptChain components
        from query_with_promptchain import SpecStoryRAG
        from promptchain.utils.promptchaining import PromptChain
        from promptchain.utils.agentic_step_processor import AgenticStepProcessor

        # Initialize RAG
        spec_rag = SpecStoryRAG(working_dir=self.working_dir)
        await spec_rag.initialize()

        # Get agentic model: CLI override > AGENTIC_MODEL env > LLM model > default
        agentic_model = self.llm_model  # Use the already resolved LLM model (respects --model flag)
        if os.getenv("AGENTIC_MODEL"):
            agentic_model = os.getenv("AGENTIC_MODEL")

        print(f"   Using agentic model: {agentic_model}")

        # Create PromptChain with agentic reasoning
        if agentic:
            agentic_step = AgenticStepProcessor(
                objective=f"Answer the query using LightRAG retrieval tools: {query_text}",
                max_internal_steps=8,
                model_name=agentic_model,
                history_mode="progressive"
            )

            chain = PromptChain(
                models=[agentic_model],
                instructions=[agentic_step],
                verbose=True
            )

            # Register LightRAG tools
            if mode == 'local':
                chain.register_tool_function(spec_rag.query_local)
            elif mode == 'global':
                chain.register_tool_function(spec_rag.query_global)
            elif mode == 'hybrid':
                chain.register_tool_function(spec_rag.query_hybrid)

            result = await chain.process_prompt_async(query_text)
        else:
            # Simple query without agentic reasoning
            if mode == 'local':
                result = await spec_rag.query_local(query_text)
            elif mode == 'global':
                result = await spec_rag.query_global(query_text)
            elif mode == 'hybrid':
                result = await spec_rag.query_hybrid(query_text)
            else:
                result = await spec_rag.query_hybrid(query_text)

        print("\n💡 Response:")
        print("-" * 70)
        print(result)
        print("-" * 70)

    def _print_help(self):
        """Print help message."""
        print("\n" + "="*70)
        print("📖 HybridRAG Interactive Help")
        print("="*70)
        print("\n🔍 Query Modes (native LightRAG):")
        print("  :local    - Specific entity relationships and details")
        print("              Best for: finding specific functions, classes, named concepts")
        print("  :global   - High-level overviews and broad patterns")
        print("              Best for: understanding workflows, architecture, summaries")
        print("  :hybrid   - Balanced combination of local and global")
        print("              Best for: general questions needing both specifics and context")
        print("  :naive    - Simple vector retrieval without graph")
        print("              Best for: basic similarity search, no graph reasoning")
        print("  :mix      - Advanced multi-strategy retrieval")
        print("              Best for: complex queries requiring all retrieval strategies")
        print("\n🧠 Multi-Hop Reasoning:")
        print("  :multihop - Toggle multi-hop reasoning mode")
        print("              Uses AgenticStepProcessor to perform multi-step reasoning")
        print("              LLM dynamically chooses which LightRAG tools to call")
        print("              Great for complex questions requiring multiple queries")
        print("\n⚙️  Settings:")
        print("  :context  - Toggle context-only mode (show raw retrieval context)")
        print("  :verbose  - Toggle verbose mode (show reasoning steps)")
        print("  :stats    - Show database statistics")
        print("\n📌 Other:")
        print("  :help     - Show this help")
        print("  :quit     - Exit interactive mode")
        print("\nJust type your query to search!")
        print("="*70)

    # ========================================
    # Ingestion Commands
    # ========================================

    async def run_ingest(self):
        """Run ingestion pipeline."""
        # Check database action
        db_action = self.args.db_action if hasattr(self.args, 'db_action') else None

        if db_action:
            await self._handle_database_action(db_action)

        # Get folders to ingest
        folders = []
        if self.args.folder:
            folders = [self.args.folder] if isinstance(self.args.folder, str) else self.args.folder
        else:
            folders = self._choose_folders()

        if not folders:
            print("❌ No folders selected for ingestion")
            return

        recursive = self.args.recursive if hasattr(self.args, 'recursive') else True

        # Parse metadata key=value pairs if provided
        extra_metadata = {}
        if hasattr(self.args, 'metadata') and self.args.metadata:
            for item in self.args.metadata:
                if '=' in item:
                    key, value = item.split('=', 1)
                    extra_metadata[key] = value

        print(f"\n🚀 Starting ingestion:")
        print(f"   Folders: {', '.join(folders)}")
        print(f"   Recursive: {recursive}")
        print(f"   Database: {self.working_dir}")
        if extra_metadata:
            print(f"   Metadata: {extra_metadata}")

        # Initialize metadata
        metadata = DatabaseMetadata(self.working_dir)

        # Add source folders to metadata with extra metadata
        for folder in folders:
            metadata.add_source_folder(folder, recursive=recursive, extra_metadata=extra_metadata)
            print(f"   📝 Registered source folder: {folder}")

        # Check for quiet mode
        quiet_mode = hasattr(self.args, 'quiet') and self.args.quiet

        # Run ingestion (using existing pipeline)
        if self.args.multiprocess:
            await self._ingest_multiprocess(folders, recursive)
        else:
            await self._ingest_single_process(folders, recursive, quiet_mode=quiet_mode)

    async def _handle_database_action(self, action: str):
        """Handle database management actions."""
        skip_confirm = hasattr(self.args, 'yes') and self.args.yes

        if action == 'fresh':
            if skip_confirm:
                self._clear_database()
                print("✅ Database cleared - starting fresh (auto-confirmed)")
            else:
                confirm = input("⚠️  This will DELETE existing database. Continue? [y/N]: ").strip().lower()
                if confirm == 'y':
                    self._clear_database()
                    print("✅ Database cleared - starting fresh")
                else:
                    print("❌ Cancelled")
                    sys.exit(0)
        elif action == 'use':
            print("✅ Using existing database")
        elif action == 'add':
            print("✅ Adding to existing database")

    def _clear_database(self):
        """Clear existing database and file tracking."""
        # Clear LightRAG database
        db_path = Path(self.working_dir)
        if db_path.exists():
            shutil.rmtree(db_path)
            print(f"🗑️  Cleared LightRAG DB: {db_path}")

        # Clear file tracking database (processed_files.db)
        # This ensures 'fresh' truly starts fresh by re-processing all files
        tracker_db = Path("./processed_files.db")
        if tracker_db.exists():
            tracker_db.unlink()
            print(f"🗑️  Cleared file tracker: {tracker_db}")

        # Also clear the ingestion queue
        queue_dir = Path("./ingestion_queue")
        if queue_dir.exists():
            shutil.rmtree(queue_dir)
            print(f"🗑️  Cleared ingestion queue: {queue_dir}")

    def _choose_folders(self) -> List[str]:
        """Interactive folder selection."""
        print("\n📁 Folder Selection")
        print("1. Use ./data folder")
        print("2. Enter custom path(s)")

        choice = input("\nChoice [1-2]: ").strip()

        if choice == "1":
            return ["./data"]
        elif choice == "2":
            folders = []
            while True:
                path = input(f"Folder {len(folders)+1} (or Enter to finish): ").strip()
                if not path:
                    break

                folder = Path(path).expanduser().resolve()
                if folder.exists():
                    folders.append(str(folder))
                    print(f"✅ Added: {folder}")
                else:
                    print(f"❌ Not found: {folder}")

            return folders
        else:
            print("❌ Invalid choice")
            return []

    async def _ingest_single_process(self, folders: List[str], recursive: bool, quiet_mode: bool = False):
        """Run ingestion in single process (batch mode - process once and exit)."""
        from config.config import load_config
        from src.ingestion_pipeline import IngestionPipeline
        from src.lightrag_core import create_lightrag_core
        from src.folder_watcher import FolderWatcher

        config = load_config(self.config_path)
        config.ingestion.watch_folders = folders
        config.ingestion.recursive = recursive

        # Suppress verbose logging in quiet mode (keeps progress bar clean)
        if quiet_mode:
            # Suppress LightRAG and other verbose loggers
            for logger_name in ['lightrag', 'lightrag.kg', 'lightrag.llm', 'nano_graphrag',
                               'httpx', 'httpcore', 'openai']:
                logging.getLogger(logger_name).setLevel(logging.WARNING)

        # Initialize components
        lightrag_core = create_lightrag_core(config)

        # Step 1: Discover and queue files using FolderWatcher
        watcher = FolderWatcher(config)
        discovered_files = watcher.scan_folders()

        print(f"   📂 Discovered {len(discovered_files)} file(s)")

        # Queue discovered files
        queued_count = 0
        for file_info in discovered_files:
            if watcher.queue_file(file_info):
                queued_count += 1

        print(f"   📝 Queued {queued_count} file(s) for ingestion")

        # Step 2: Process queued files in batch mode
        pipeline = IngestionPipeline(config, lightrag_core)
        results = await pipeline.run_batch()

        # Step 3: Record ingestion in metadata
        metadata = DatabaseMetadata(self.working_dir)
        for folder in folders:
            metadata.record_ingestion(
                folder_path=folder,
                files_processed=results["files_processed"],
                success=(results["files_failed"] == 0),
                notes=f"Found: {results['files_found']}, Processed: {results['files_processed']}, Failed: {results['files_failed']}"
            )

        # Step 4: Print summary
        print(f"\n✅ Ingestion complete:")
        print(f"   Files found:     {results['files_found']}")
        print(f"   Files processed: {results['files_processed']}")
        print(f"   Files failed:    {results['files_failed']}")

        if results["errors"]:
            print(f"\n⚠️  Errors:")
            for error in results["errors"][:10]:  # Show first 10 errors
                print(f"   - {error}")
            if len(results["errors"]) > 10:
                print(f"   ... and {len(results['errors']) - 10} more errors")

    async def _ingest_multiprocess(self, folders: List[str], recursive: bool):
        """Run ingestion with multiprocess architecture."""
        from config.config import load_config
        from src.process_manager import ProcessManager

        config = load_config(self.config_path)
        process_manager = ProcessManager()

        # Start processes
        process_manager.start_watcher_process(folders, recursive)
        process_manager.start_ingestion_process(config)

        print("✅ Multiprocess ingestion started")
        print("   Press Ctrl+C to stop")

        try:
            while True:
                await asyncio.sleep(5)
                progress = process_manager.get_ingestion_progress()
                if progress:
                    print(f"📊 Progress: {progress.processed_files}/{progress.total_files} files")
        except KeyboardInterrupt:
            print("\n🛑 Stopping...")
            process_manager.shutdown()

    # ========================================
    # Management Commands
    # ========================================

    async def list_databases(self):
        """List all LightRAG databases in current directory."""
        print("\n📊 Available Databases")
        print("="*70)

        databases = list_all_databases()

        if not databases:
            print("❌ No databases found in current directory")
            print("\nCreate a database with:")
            print("   python hybridrag.py ingest --folder ./data")
            return

        for i, db in enumerate(databases, 1):
            print(f"\n{i}. {db['name']}")
            print(f"   Path: {db['path']}")

            if db['has_metadata']:
                stats = db['stats']
                print(f"   ✅ Has metadata")
                print(f"   Files ingested: {stats.get('total_files_ingested', 'Unknown')}")
                print(f"   Source folders: {stats.get('source_folders_count', 0)}")
                if stats.get('description'):
                    print(f"   Description: {stats.get('description')}")
            else:
                print(f"   ⚠️  No metadata (old database)")
                print(f"   Run: python hybridrag.py --working-dir {db['path']} db-info")

        print("\n" + "="*70)
        print(f"Total: {len(databases)} database(s)")

    async def show_database_info(self):
        """Show detailed information about current database."""
        db_path = Path(self.working_dir)

        print(f"\n🔍 Database Information")
        print("="*70)
        print(f"Location: {db_path.resolve()}")

        if not db_path.exists():
            print("❌ Database does not exist")
            return

        # Load metadata
        metadata = DatabaseMetadata(self.working_dir)

        if not metadata.exists():
            print("\n⚠️  No metadata found (this is an old database)")
            print("\nTo add metadata, re-ingest a folder:")
            print(f"   python hybridrag.py --working-dir {self.working_dir} ingest --folder ./data --db-action add")
            return

        # Get stats
        stats = metadata.get_stats()

        print(f"\n📈 Statistics:")
        print(f"   Created: {stats.get('created_at', 'Unknown')}")
        print(f"   Last updated: {stats.get('last_updated', 'Unknown')}")
        print(f"   Total files ingested: {stats.get('total_files_ingested', 0)}")
        print(f"   Ingestion events: {stats.get('ingestion_events', 0)}")

        if stats.get('description'):
            print(f"   Description: {stats.get('description')}")

        # Show source folders
        sources = metadata.get_source_folders()
        if sources:
            print(f"\n📁 Source Folders ({len(sources)}):")
            for source in sources:
                recursive_icon = "🔄" if source.get('recursive') else "📄"
                print(f"   {recursive_icon} {source['path']}")
                print(f"      Added: {source.get('added_at', 'Unknown')}")
                print(f"      Last ingested: {source.get('last_ingested', 'Unknown')}")
        else:
            print("\n📁 No source folders registered")

        # Show recent ingestion history
        history = metadata.get_ingestion_history(limit=5)
        if history:
            print(f"\n📜 Recent Ingestion History:")
            for i, event in enumerate(reversed(history), 1):
                status = "✅" if event.get('success') else "❌"
                print(f"   {i}. {status} {event.get('timestamp', 'Unknown')}")
                print(f"      Folder: {event.get('source_folder', 'Unknown')}")
                print(f"      Files: {event.get('files_processed', 0)}")
                if event.get('notes'):
                    print(f"      Notes: {event.get('notes')}")

        print("="*70)

    async def show_status(self):
        """Show system status."""
        print("\n📊 HybridRAG System Status")
        print("="*70)

        # Database info
        from src.utils import format_file_size
        db_path = Path(self.working_dir)
        if db_path.exists():
            db_files = list(db_path.glob("*.json"))
            db_size = sum(f.stat().st_size for f in db_files)
            print(f"✅ Database: {db_path}")
            print(f"   Files: {len(db_files)}")
            print(f"   Size: {format_file_size(db_size)}")
        else:
            print(f"❌ No database found at: {db_path}")

        # Check for running processes
        try:
            from src.process_manager import ProcessManager
            pm = ProcessManager()
            status = pm.get_system_status()

            print("\n📈 Processes:")
            for proc_name, proc_info in status.get('processes', {}).items():
                status_emoji = "✅" if proc_info.get('status') == 'running' else "❌"
                print(f"   {status_emoji} {proc_name}: {proc_info.get('status', 'unknown')}")
        except Exception as e:
            print(f"\n⚠️  Process status unavailable: {e}")

        print("="*70)

    async def check_database(self):
        """Check database and show statistics."""
        db_path = Path(self.working_dir)

        print("\n🔍 Database Check")
        print("="*70)
        print(f"Location: {db_path}")

        if not db_path.exists():
            print("❌ Database does not exist")
            print("\nRun ingestion to create database:")
            print("   python hybridrag.py ingest --folder ./data")
            return

        # Count files
        json_files = list(db_path.glob("*.json"))
        other_files = list(db_path.glob("*"))

        # Calculate sizes
        from src.utils import format_file_size
        total_size = sum(f.stat().st_size for f in other_files if f.is_file())

        print(f"\n✅ Database exists")
        print(f"   JSON files: {len(json_files)}")
        print(f"   Total files: {len(other_files)}")
        print(f"   Total size: {format_file_size(total_size)}")

        # Show file breakdown
        print("\n📁 File breakdown:")
        for pattern in ["kv_store_*.json", "vdb_*.json"]:
            files = list(db_path.glob(pattern))
            if files:
                print(f"   {pattern}: {len(files)} file(s)")

        print("="*70)

    # ========================================
    # Database Registry Commands
    # ========================================

    async def run_db_command(self):
        """Route database registry subcommands."""
        db_cmd = getattr(self.args, 'db_command', None)

        if not db_cmd:
            print("❌ No db subcommand specified")
            print("\nUsage: python hybridrag.py db <command>")
            print("\nCommands:")
            print("  register   - Register a new database")
            print("  list       - List all registered databases")
            print("  show       - Show database details")
            print("  update     - Update database settings")
            print("  unregister - Remove database from registry")
            print("  sync       - Force re-ingest from source folder")
            print("  watch      - Manage database watchers")
            return

        if db_cmd == 'register':
            await self.run_db_register()
        elif db_cmd == 'list':
            await self.run_db_list()
        elif db_cmd == 'show':
            await self.run_db_show()
        elif db_cmd == 'update':
            await self.run_db_update()
        elif db_cmd == 'unregister':
            await self.run_db_unregister()
        elif db_cmd == 'sync':
            await self.run_db_sync()
        elif db_cmd == 'watch':
            await self.run_db_watch()
        else:
            print(f"❌ Unknown db command: {db_cmd}")

    async def run_db_register(self):
        """Register a new database in the registry."""
        try:
            registry = get_registry()
        except Exception as e:
            print(f"❌ Failed to load registry: {e}")
            return

        name = self.args.name
        path = os.path.abspath(self.args.path)
        source_folder = os.path.abspath(self.args.source_folder) if self.args.source_folder else None
        source_type = self.args.type
        auto_watch = self.args.auto_watch
        interval = self.args.interval
        model = getattr(self.args, 'db_model', None)
        description = self.args.description
        jira_project = getattr(self.args, 'jira_project', None)
        extensions = self.args.extensions

        # Parse extensions if provided
        file_extensions = None
        if extensions:
            file_extensions = [ext.strip() for ext in extensions.split(',')]

        # Build kwargs
        kwargs = {
            'source_type': source_type,
            'auto_watch': auto_watch,
            'watch_interval': interval,
        }
        if model:
            kwargs['model'] = model
        if description:
            kwargs['description'] = description
        if file_extensions:
            kwargs['file_extensions'] = file_extensions

        # Handle specstory-specific config
        if source_type == 'specstory' and jira_project:
            kwargs['specstory_config'] = {
                'jira_project_key': jira_project
            }

        try:
            entry = registry.register(
                name=name,
                path=path,
                source_folder=source_folder,
                **kwargs
            )
            print(f"✅ Registered database: {entry.name}")
            print(f"   Path: {entry.path}")
            if entry.source_folder:
                print(f"   Source: {entry.source_folder}")
            print(f"   Type: {entry.source_type}")
            print(f"   Auto-watch: {entry.auto_watch}")
            if entry.model:
                print(f"   Model: {entry.model}")

        except ValueError as e:
            print(f"❌ Registration failed: {e}")
        except Exception as e:
            print(f"❌ Unexpected error: {e}")

    async def run_db_list(self):
        """List all registered databases."""
        try:
            registry = get_registry()
        except Exception as e:
            print(f"❌ Failed to load registry: {e}")
            return

        databases = registry.list_all()

        if getattr(self.args, 'json', False):
            # JSON output
            import json
            output = [entry.to_dict() for entry in databases]
            print(json.dumps(output, indent=2, default=str))
            return

        if not databases:
            print("\n📊 No databases registered")
            print("\nRegister a database with:")
            print("   python hybridrag.py db register mydb --path ./db --source ./data")
            return

        print("\n📊 Registered Databases")
        print("="*70)

        for entry in databases:
            # Check watcher status
            running, pid = is_watcher_running(entry.name)
            watcher_status = f"🟢 PID {pid}" if running else "⚪ stopped"

            print(f"\n{entry.name}")
            print(f"   Path: {entry.path}")
            if entry.source_folder:
                print(f"   Source: {entry.source_folder}")
            print(f"   Type: {entry.source_type}")
            print(f"   Auto-watch: {entry.auto_watch} ({watcher_status})")
            if entry.model:
                print(f"   Model: {entry.model}")
            if entry.description:
                print(f"   Description: {entry.description}")

        print("\n" + "="*70)
        print(f"Total: {len(databases)} database(s)")

    async def run_db_show(self):
        """Show details for a specific database."""
        try:
            registry = get_registry()
        except Exception as e:
            print(f"❌ Failed to load registry: {e}")
            return

        name = self.args.name
        entry = registry.get(name)

        if not entry:
            print(f"❌ Database not found: {name}")
            print("\nAvailable databases:")
            for db in registry.list_all():
                print(f"   - {db.name}")
            return

        if getattr(self.args, 'json', False):
            import json
            print(json.dumps(entry.to_dict(), indent=2, default=str))
            return

        # Check watcher status
        running, pid = is_watcher_running(entry.name)

        print(f"\n📊 Database: {entry.name}")
        print("="*70)
        print(f"   Path:         {entry.path}")
        print(f"   Source:       {entry.source_folder or 'Not set'}")
        print(f"   Type:         {entry.source_type}")
        print(f"   Auto-watch:   {entry.auto_watch}")
        print(f"   Interval:     {entry.watch_interval}s")
        print(f"   Model:        {entry.model or 'Default'}")
        print(f"   Recursive:    {entry.recursive}")
        print(f"   Description:  {entry.description or 'None'}")
        print(f"   Created:      {entry.created_at}")
        print(f"   Last sync:    {entry.last_sync or 'Never'}")

        # Watcher status
        if running:
            print(f"\n🟢 Watcher running (PID: {pid})")
        else:
            print(f"\n⚪ Watcher stopped")

        # Type-specific config
        if entry.specstory_config:
            print(f"\n   SpecStory Config:")
            for key, val in entry.specstory_config.items():
                print(f"      {key}: {val}")

        if entry.file_extensions:
            print(f"   Extensions: {', '.join(entry.file_extensions)}")

        if entry.preprocessing_pipeline:
            print(f"   Pipeline: {' → '.join(entry.preprocessing_pipeline)}")

        print("="*70)

    async def run_db_update(self):
        """Update database settings."""
        try:
            registry = get_registry()
        except Exception as e:
            print(f"❌ Failed to load registry: {e}")
            return

        name = self.args.name
        entry = registry.get(name)

        if not entry:
            print(f"❌ Database not found: {name}")
            return

        # Collect updates
        updates = {}
        if self.args.auto_watch is not None:
            updates['auto_watch'] = self.args.auto_watch
        if self.args.interval is not None:
            updates['watch_interval'] = self.args.interval
        if getattr(self.args, 'db_model', None):
            updates['model'] = self.args.db_model
        if self.args.description is not None:
            updates['description'] = self.args.description

        if not updates:
            print("❌ No updates specified")
            print("\nAvailable options:")
            print("   --auto-watch true/false")
            print("   --interval <seconds>")
            print("   --model <model-name>")
            print("   --description <text>")
            return

        try:
            updated = registry.update(name, **updates)
            print(f"✅ Updated database: {name}")
            for key, val in updates.items():
                print(f"   {key}: {val}")
        except Exception as e:
            print(f"❌ Update failed: {e}")

    async def run_db_unregister(self):
        """Remove database from registry."""
        try:
            registry = get_registry()
        except Exception as e:
            print(f"❌ Failed to load registry: {e}")
            return

        name = self.args.name
        entry = registry.get(name)

        if not entry:
            print(f"❌ Database not found: {name}")
            return

        # Confirm unless --yes
        if not getattr(self.args, 'yes', False):
            print(f"\n⚠️  About to unregister: {name}")
            print(f"   Path: {entry.path}")
            print(f"\n   This removes the database from the registry.")
            print(f"   The database files will NOT be deleted.")
            response = input("\nProceed? [y/N]: ").strip().lower()
            if response != 'y':
                print("Cancelled.")
                return

        try:
            registry.unregister(name)
            print(f"✅ Unregistered database: {name}")
        except Exception as e:
            print(f"❌ Unregister failed: {e}")

    async def run_db_sync(self):
        """Force re-ingest from source folder."""
        try:
            registry = get_registry()
        except Exception as e:
            print(f"❌ Failed to load registry: {e}")
            return

        name = self.args.name
        entry = registry.get(name)

        if not entry:
            print(f"❌ Database not found: {name}")
            return

        if not entry.source_folder:
            print(f"❌ Database {name} has no source folder configured")
            return

        if not os.path.exists(entry.source_folder):
            print(f"❌ Source folder does not exist: {entry.source_folder}")
            return

        fresh = getattr(self.args, 'fresh', False)
        db_action = 'fresh' if fresh else 'add'

        print(f"\n🔄 Syncing database: {name}")
        print(f"   Source: {entry.source_folder}")
        print(f"   Target: {entry.path}")
        print(f"   Mode: {db_action}")

        # Build ingest command args
        original_working_dir = self.working_dir
        self.working_dir = entry.path

        # Temporarily modify args for ingest
        original_folder = getattr(self.args, 'folder', None)
        original_db_action = getattr(self.args, 'db_action', None)
        original_recursive = getattr(self.args, 'recursive', True)

        self.args.folder = entry.source_folder
        self.args.db_action = db_action
        self.args.recursive = entry.recursive

        try:
            await self.run_ingest()
            # Update last_sync
            registry.update_last_sync(name)
            print(f"\n✅ Sync complete for: {name}")
        except Exception as e:
            print(f"❌ Sync failed: {e}")
        finally:
            # Restore original args
            self.working_dir = original_working_dir
            self.args.folder = original_folder
            self.args.db_action = original_db_action
            self.args.recursive = original_recursive

    async def run_db_watch(self):
        """Handle watch subcommands."""
        watch_cmd = getattr(self.args, 'watch_command', None)

        if not watch_cmd:
            print("❌ No watch subcommand specified")
            print("\nUsage: python hybridrag.py db watch <command>")
            print("\nCommands:")
            print("  start  - Start watcher for a database")
            print("  stop   - Stop watcher for a database")
            print("  status - Show watcher status")
            return

        if watch_cmd == 'start':
            await self.run_db_watch_start()
        elif watch_cmd == 'stop':
            await self.run_db_watch_stop()
        elif watch_cmd == 'status':
            await self.run_db_watch_status()
        else:
            print(f"❌ Unknown watch command: {watch_cmd}")

    async def run_db_watch_start(self):
        """Start watcher for a database."""
        try:
            registry = get_registry()
        except Exception as e:
            print(f"❌ Failed to load registry: {e}")
            return

        start_all = getattr(self.args, 'all', False)
        use_systemd = getattr(self.args, 'systemd', False)

        if start_all:
            # Start all auto-watch databases
            auto_watch_dbs = registry.get_auto_watch_databases()
            if not auto_watch_dbs:
                print("❌ No databases with auto-watch enabled")
                return

            print(f"\n🚀 Starting watchers for {len(auto_watch_dbs)} database(s)...")
            for entry in auto_watch_dbs:
                await self._start_watcher_for_db(entry, use_systemd)
        else:
            name = getattr(self.args, 'name', None)
            if not name:
                print("❌ Database name required (or use --all)")
                return

            entry = registry.get(name)
            if not entry:
                print(f"❌ Database not found: {name}")
                return

            await self._start_watcher_for_db(entry, use_systemd)

    async def _start_watcher_for_db(self, entry: DatabaseEntry, use_systemd: bool = False):
        """Start watcher for a specific database entry."""
        from src.database_registry import get_watcher_pid_file

        # Check if already running
        running, pid = is_watcher_running(entry.name)
        if running:
            print(f"⚠️  Watcher already running for {entry.name} (PID: {pid})")
            return

        if not entry.source_folder:
            print(f"❌ No source folder for {entry.name}")
            return

        pid_file = get_watcher_pid_file(entry.name)

        if use_systemd:
            # Systemd mode - placeholder for now
            print(f"⚠️  Systemd mode not yet implemented for {entry.name}")
            print(f"   Use standalone mode: python hybridrag.py db watch start {entry.name}")
            return

        # Standalone mode - start background process
        import subprocess

        script_path = Path(__file__).parent / "scripts" / "hybridrag-watcher.py"
        if not script_path.exists():
            # Fall back to existing bash script
            bash_script = Path(__file__).parent / "scripts" / "watch_specstory_folders.sh"
            if bash_script.exists() and entry.source_type == 'specstory':
                print(f"🔄 Starting legacy watcher for {entry.name}...")
                cmd = [
                    str(bash_script),
                    entry.source_folder,
                    str(entry.watch_interval),
                ]
                if entry.model:
                    cmd.append(entry.model)

                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )
                # The script handles its own PID file
                print(f"✅ Started watcher for {entry.name} (legacy mode)")
                return

            print(f"⚠️  Watcher script not found. Please create scripts/hybridrag-watcher.py")
            print(f"   or use: python hybridrag.py db watch start-all --systemd")
            return

        # Run the Python watcher script
        cmd = [
            sys.executable,
            str(script_path),
            entry.name,
        ]

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )

        # Write PID file
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(str(proc.pid))

        print(f"✅ Started watcher for {entry.name} (PID: {proc.pid})")

    async def run_db_watch_stop(self):
        """Stop watcher for a database."""
        try:
            registry = get_registry()
        except Exception as e:
            print(f"❌ Failed to load registry: {e}")
            return

        from src.database_registry import get_watcher_pid_file
        import signal

        stop_all = getattr(self.args, 'all', False)

        if stop_all:
            # Stop all watchers
            databases = registry.list_all()
            stopped = 0
            for entry in databases:
                running, pid = is_watcher_running(entry.name)
                if running and pid:
                    try:
                        os.kill(pid, signal.SIGTERM)
                        pid_file = get_watcher_pid_file(entry.name)
                        if pid_file.exists():
                            pid_file.unlink()
                        print(f"✅ Stopped watcher for {entry.name}")
                        stopped += 1
                    except ProcessLookupError:
                        pass
                    except Exception as e:
                        print(f"⚠️  Error stopping {entry.name}: {e}")

            print(f"\nStopped {stopped} watcher(s)")
        else:
            name = getattr(self.args, 'name', None)
            if not name:
                print("❌ Database name required (or use --all)")
                return

            running, pid = is_watcher_running(name)
            if not running:
                print(f"⚠️  No watcher running for {name}")
                return

            try:
                os.kill(pid, signal.SIGTERM)
                pid_file = get_watcher_pid_file(name)
                if pid_file.exists():
                    pid_file.unlink()
                print(f"✅ Stopped watcher for {name} (was PID: {pid})")
            except ProcessLookupError:
                print(f"⚠️  Process {pid} not found (already stopped?)")
                pid_file = get_watcher_pid_file(name)
                if pid_file.exists():
                    pid_file.unlink()
            except Exception as e:
                print(f"❌ Error stopping watcher: {e}")

    async def run_db_watch_status(self):
        """Show watcher status."""
        try:
            registry = get_registry()
        except Exception as e:
            print(f"❌ Failed to load registry: {e}")
            return

        name = getattr(self.args, 'name', None)

        if name:
            # Show status for specific database
            entry = registry.get(name)
            if not entry:
                print(f"❌ Database not found: {name}")
                return

            running, pid = is_watcher_running(name)
            print(f"\n🔍 Watcher Status: {name}")
            print("="*50)
            if running:
                print(f"   Status: 🟢 Running (PID: {pid})")
            else:
                print(f"   Status: ⚪ Stopped")
            print(f"   Auto-watch: {entry.auto_watch}")
            print(f"   Interval: {entry.watch_interval}s")
            print(f"   Source: {entry.source_folder or 'Not set'}")
        else:
            # Show status for all databases
            databases = registry.list_all()

            print("\n🔍 Watcher Status")
            print("="*60)

            if not databases:
                print("No databases registered")
                return

            running_count = 0
            for entry in databases:
                running, pid = is_watcher_running(entry.name)
                if running:
                    running_count += 1
                    status = f"🟢 PID {pid}"
                else:
                    status = "⚪ stopped"

                auto = "✓" if entry.auto_watch else " "
                print(f"   [{auto}] {entry.name:20} {status}")

            print("="*60)
            print(f"Running: {running_count}/{len(databases)}")
            print("\n   [✓] = auto-watch enabled")


def create_parser():
    """Create argument parser."""
    parser = argparse.ArgumentParser(
        description="HybridRAG - Unified interface for RAG operations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive query mode
  python hybridrag.py interactive

  # One-shot queries (default: Azure models from env)
  python hybridrag.py query --text "Find appointment tables" --mode hybrid
  python hybridrag.py query --text "..." --agentic

  # Override model (supports azure/, openai/, anthropic/, gemini/, ollama/)
  python hybridrag.py --model gemini/gemini-pro query --text "..."
  python hybridrag.py --model anthropic/claude-opus query --text "..."
  python hybridrag.py --model openai/gpt-4o query --text "..."

  # Ingestion
  python hybridrag.py ingest --folder ./data
  python hybridrag.py ingest --folder ./data --db-action fresh

  # Management
  python hybridrag.py status
  python hybridrag.py check-db
  python hybridrag.py list-dbs              # List all databases
  python hybridrag.py db-info               # Show database details

  # Interactive Monitor
  python hybridrag.py monitor               # Launch TUI dashboard
  python hybridrag.py monitor --new         # Start with database wizard
  python hybridrag.py monitor --refresh 5   # Custom refresh rate
        """
    )

    # Global options
    parser.add_argument('--config', help='Config file path')
    parser.add_argument('--working-dir', default='./lightrag_db', help='LightRAG database directory')
    parser.add_argument('--db', metavar='NAME', help='Use registered database by name (e.g., --db specstory)')
    parser.add_argument('--model', help='Override LLM model (e.g., azure/gpt-5.1, gemini/gemini-pro, anthropic/claude-opus)')
    parser.add_argument('--embed-model', help='Override embedding model (e.g., azure/text-embedding-3-small)')

    # Subcommands
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # Query command
    query_parser = subparsers.add_parser('query', help='Execute one-shot query')
    query_parser.add_argument('--text', required=True, help='Query text')
    query_parser.add_argument('--mode', choices=['local', 'global', 'hybrid', 'naive', 'mix'],
                             default='hybrid', help='Query mode')
    query_parser.add_argument('--agentic', action='store_true', help='Use agentic multi-hop reasoning')
    query_parser.add_argument('--multihop', action='store_true', help='Use multi-hop reasoning with LightRAG tools')
    query_parser.add_argument('--use-promptchain', action='store_true', help='Use PromptChain for queries')
    query_parser.add_argument('--verbose', '-v', action='store_true', help='Show reasoning steps')

    # Interactive command
    interactive_parser = subparsers.add_parser('interactive', help='Start interactive query interface')

    # Ingest command
    ingest_parser = subparsers.add_parser('ingest', help='Run ingestion pipeline')
    ingest_parser.add_argument('--folder', action='append', help='Folder(s) to ingest (can specify multiple)')
    ingest_parser.add_argument('--recursive', action='store_true', default=True, help='Watch folders recursively')
    ingest_parser.add_argument('--db-action', choices=['use', 'add', 'fresh'],
                              help='Database action: use existing, add to existing, or start fresh')
    ingest_parser.add_argument('--multiprocess', action='store_true', help='Use multiprocess architecture')
    ingest_parser.add_argument('--metadata', action='append', metavar='KEY=VALUE',
                              help='Add metadata key=value pairs (can specify multiple)')
    ingest_parser.add_argument('--yes', '-y', action='store_true',
                              help='Skip confirmation prompts (for scripted use)')
    ingest_parser.add_argument('--quiet', '-q', action='store_true',
                              help='Suppress verbose LightRAG output (show only progress bar)')

    # Status command
    status_parser = subparsers.add_parser('status', help='Show system status')

    # Check-db command
    checkdb_parser = subparsers.add_parser('check-db', help='Check database and show statistics')

    # List-dbs command
    listdbs_parser = subparsers.add_parser('list-dbs', help='List all databases in current directory')

    # Db-info command
    dbinfo_parser = subparsers.add_parser('db-info', help='Show detailed database information with source folders')

    # Monitor command (TUI dashboard)
    monitor_parser = subparsers.add_parser('monitor', help='Launch interactive TUI dashboard')
    monitor_parser.add_argument('--refresh', '-r', type=int, default=2,
                               help='Refresh interval in seconds (default: 2)')
    monitor_parser.add_argument('--new', '-n', action='store_true',
                               help='Start with new database wizard')

    # ========================================
    # Database Registry Commands
    # ========================================
    db_parser = subparsers.add_parser('db', help='Database registry management')
    db_subparsers = db_parser.add_subparsers(dest='db_command', help='Database command')

    # db register
    db_register = db_subparsers.add_parser('register', help='Register a new database')
    db_register.add_argument('name', help='Database name (lowercase alphanumeric + hyphens)')
    db_register.add_argument('--path', required=True, help='Path to database directory')
    db_register.add_argument('--source', '--source-folder', dest='source_folder',
                            help='Path to source data folder')
    db_register.add_argument('--type', choices=['filesystem', 'specstory', 'api', 'schema'],
                            default='filesystem', help='Source type (default: filesystem)')
    db_register.add_argument('--auto-watch', action='store_true', help='Enable auto-watching')
    db_register.add_argument('--interval', type=int, default=300,
                            help='Watch interval in seconds (default: 300)')
    db_register.add_argument('--model', dest='db_model', help='Model to use for this database')
    db_register.add_argument('--description', help='Database description')
    db_register.add_argument('--jira-project', help='JIRA project key (for specstory type)')
    db_register.add_argument('--extensions', help='File extensions to watch (comma-separated)')

    # db list
    db_list = db_subparsers.add_parser('list', help='List all registered databases')
    db_list.add_argument('--json', action='store_true', help='Output as JSON')

    # db show
    db_show = db_subparsers.add_parser('show', help='Show database details')
    db_show.add_argument('name', help='Database name')
    db_show.add_argument('--json', action='store_true', help='Output as JSON')

    # db update
    db_update = db_subparsers.add_parser('update', help='Update database settings')
    db_update.add_argument('name', help='Database name')
    db_update.add_argument('--auto-watch', type=lambda x: x.lower() == 'true',
                          help='Enable/disable auto-watching (true/false)')
    db_update.add_argument('--interval', type=int, help='Watch interval in seconds')
    db_update.add_argument('--model', dest='db_model', help='Model to use')
    db_update.add_argument('--description', help='Database description')

    # db unregister
    db_unregister = db_subparsers.add_parser('unregister', help='Remove database from registry')
    db_unregister.add_argument('name', help='Database name')
    db_unregister.add_argument('--yes', '-y', action='store_true', help='Skip confirmation')

    # db sync
    db_sync = db_subparsers.add_parser('sync', help='Force re-ingest from source folder')
    db_sync.add_argument('name', help='Database name')
    db_sync.add_argument('--fresh', action='store_true', help='Start fresh (clear database first)')

    # db watch
    db_watch_parser = db_subparsers.add_parser('watch', help='Manage database watchers')
    db_watch_subparsers = db_watch_parser.add_subparsers(dest='watch_command', help='Watch command')

    # db watch start
    db_watch_start = db_watch_subparsers.add_parser('start', help='Start watcher for a database')
    db_watch_start.add_argument('name', nargs='?', help='Database name (or all if --all)')
    db_watch_start.add_argument('--all', action='store_true', help='Start all auto-watch databases')
    db_watch_start.add_argument('--systemd', action='store_true', help='Use systemd mode')

    # db watch stop
    db_watch_stop = db_watch_subparsers.add_parser('stop', help='Stop watcher for a database')
    db_watch_stop.add_argument('name', nargs='?', help='Database name (or all if --all)')
    db_watch_stop.add_argument('--all', action='store_true', help='Stop all watchers')

    # db watch status
    db_watch_status = db_watch_subparsers.add_parser('status', help='Show watcher status')
    db_watch_status.add_argument('name', nargs='?', help='Database name (optional)')

    return parser


async def async_main(args):
    """Async entry point for non-monitor commands."""
    cli = HybridRAGCLI(args)
    return await cli.run()


def run_monitor_command(args):
    """Run the monitor command with its own event loop."""
    try:
        from src.monitor import run_monitor
    except ImportError as e:
        print(f"❌ Monitor dependencies not installed: {e}")
        print("\nInstall with:")
        print("   pip install textual psutil")
        return 1

    refresh_interval = getattr(args, 'refresh', 2)
    start_wizard = getattr(args, 'new', False)

    run_monitor(refresh_interval=refresh_interval, start_wizard=start_wizard)
    return 0


def main():
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Special handling for monitor command (needs its own event loop)
    if args.command == 'monitor':
        return run_monitor_command(args)

    # All other commands run in async context
    return asyncio.run(async_main(args))


if __name__ == "__main__":
    sys.exit(main())
