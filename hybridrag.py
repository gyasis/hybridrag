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

import argparse
import asyncio
import json
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Load environment
load_dotenv()

# Import metadata manager
# Import backend configuration for status command
from src.config.backend_config import BackendConfig
from src.database_metadata import DatabaseMetadata, list_all_databases

# Import database registry
from src.database_registry import (
    DatabaseEntry,
    get_registry,
    get_watcher_pid_file,
    is_watcher_running,
    resolve_database,
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

    elif model_lower.startswith('openai/') or '/' not in model_lower:
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
        self._backend_config = None  # Backend config from registry (auto-resolved)
        db_name = getattr(args, 'db', None)

        if db_name:
            # Look up database by name in registry
            working_dir, db_entry = resolve_database(db_name)
            if db_entry:
                self._db_entry = db_entry
                self.working_dir = db_entry.path
                # Auto-load backend config from registry
                self._backend_config = db_entry.get_backend_config()
                logger.info(f"Registry '{db_entry.name}': backend={self._backend_config.backend_type.value}")
                # Model priority: CLI > model_config (registry) > db_entry.model > env > default
                cli_model = getattr(args, 'model', None)
                model_config = db_entry.get_model_config()
                if cli_model:
                    self.llm_model = cli_model
                elif model_config and model_config.get('llm_model'):
                    self.llm_model = model_config['llm_model']
                elif db_entry.model:
                    self.llm_model = db_entry.model
                else:
                    self.llm_model = os.getenv("LIGHTRAG_MODEL", "azure/gpt-5.1")
                # Apply API keys from registry model_config
                if model_config and model_config.get('api_keys'):
                    for key_name, key_value in model_config['api_keys'].items():
                        env_key = f"{key_name.upper()}_API_KEY"
                        if key_value and not os.environ.get(env_key):
                            os.environ[env_key] = key_value
            else:
                # Treat as path fallback
                self.working_dir = working_dir
                self.llm_model = args.model if hasattr(args, 'model') and args.model else os.getenv("LIGHTRAG_MODEL", "azure/gpt-5.1")
        else:
            self.working_dir = args.working_dir if hasattr(args, 'working_dir') else "./lightrag_db"
            # Model override support: CLI > env var > default
            self.llm_model = args.model if hasattr(args, 'model') and args.model else os.getenv("LIGHTRAG_MODEL", "azure/gpt-5.1")

            # Auto-resolve backend config from registry by path matching
            # This ensures even without --db, the correct backend is used
            try:
                registry = get_registry()
                resolved_path = str(Path(self.working_dir).expanduser().resolve())
                for entry in registry.list_all():
                    if entry.path and str(Path(entry.path).resolve()) == resolved_path:
                        self._db_entry = entry
                        self._backend_config = entry.get_backend_config()
                        logger.info(
                            f"Auto-resolved registry entry '{entry.name}' for path {resolved_path}: "
                            f"backend={self._backend_config.backend_type.value}"
                        )
                        break
            except Exception as e:
                logger.debug(f"Registry auto-resolve failed (non-fatal): {e}")

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
        # Note: 'list-dbs' removed - use 'db list' instead
        # Note: 'db-info' removed - use 'db show <name>' instead
        elif command == 'db':
            await self.run_db_command()
        elif command == 'monitor':
            self.run_monitor()
        elif command == 'snapshot':
            await self.show_snapshot()
        elif command == 'backend':
            await self.run_backend_command()
        elif command == 'logs':
            await self.run_logs_command()
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
        from config.app_config import HybridRAGConfig
        from src.lightrag_core import HybridLightRAGCore

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
                        print("\n💡 Response:")
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
        from config.app_config import HybridRAGConfig
        from src.lightrag_core import HybridLightRAGCore

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
        from config.app_config import HybridRAGConfig
        from src.lightrag_core import HybridLightRAGCore

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
        from promptchain.utils.agentic_step_processor import AgenticStepProcessor
        from promptchain.utils.promptchaining import PromptChain
        from query_with_promptchain import SpecStoryRAG

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

        # Display backend info from registry
        backend_label = "json (default)"
        if self._backend_config:
            backend_label = self._backend_config.backend_type.value
            if self._backend_config.backend_type.value == "postgres":
                backend_label += (
                    f" ({self._backend_config.postgres_host}:"
                    f"{self._backend_config.postgres_port}/"
                    f"{self._backend_config.postgres_database})"
                )

        print("\n🚀 Starting ingestion:")
        print(f"   Folders: {', '.join(folders)}")
        print(f"   Recursive: {recursive}")
        print(f"   Database: {self.working_dir}")
        print(f"   Backend: {backend_label}")
        if self._db_entry:
            print(f"   Registry: {self._db_entry.name}")
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
        from config.app_config import load_config
        from src.folder_watcher import FolderWatcher
        from src.ingestion_pipeline import IngestionPipeline
        from src.lightrag_core import create_lightrag_core

        config = load_config(self.config_path)
        config.ingestion.watch_folders = folders
        config.ingestion.recursive = recursive

        # Suppress verbose logging in quiet mode (keeps progress bar clean)
        if quiet_mode:
            # Suppress LightRAG and other verbose loggers
            for logger_name in ['lightrag', 'lightrag.kg', 'lightrag.llm', 'nano_graphrag',
                               'httpx', 'httpcore', 'openai']:
                logging.getLogger(logger_name).setLevel(logging.WARNING)

        # Initialize components with backend config from registry (if available)
        if self._backend_config:
            backend_type = self._backend_config.backend_type.value
            print(f"   🔧 Backend: {backend_type} (from registry)")
            lightrag_core = create_lightrag_core(config, backend_config=self._backend_config)
        else:
            print("   🔧 Backend: json (default - no registry config)")
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
        print("\n✅ Ingestion complete:")
        print(f"   Files found:     {results['files_found']}")
        print(f"   Files processed: {results['files_processed']}")
        print(f"   Files failed:    {results['files_failed']}")

        if results["errors"]:
            print("\n⚠️  Errors:")
            for error in results["errors"][:10]:  # Show first 10 errors
                print(f"   - {error}")
            if len(results["errors"]) > 10:
                print(f"   ... and {len(results['errors']) - 10} more errors")

    async def _ingest_multiprocess(self, folders: List[str], recursive: bool):
        """Run ingestion with multiprocess architecture."""
        from config.app_config import load_config
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
                print("   ✅ Has metadata")
                print(f"   Files ingested: {stats.get('total_files_ingested', 'Unknown')}")
                print(f"   Source folders: {stats.get('source_folders_count', 0)}")
                if stats.get('description'):
                    print(f"   Description: {stats.get('description')}")
            else:
                print("   ⚠️  No metadata (old database)")
                print(f"   Run: python hybridrag.py --working-dir {db['path']} db-info")

        print("\n" + "="*70)
        print(f"Total: {len(databases)} database(s)")

    async def show_database_info(self):
        """Show detailed information about current database."""
        db_path = Path(self.working_dir)

        print("\n🔍 Database Information")
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

        print("\n📈 Statistics:")
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
            print("\n📜 Recent Ingestion History:")
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

        print("\n✅ Database exists")
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

    async def show_snapshot(self):
        """Quick status snapshot for monitoring: watchers, folders, files processed."""
        from datetime import datetime

        from src.utils import format_file_size

        print("\n" + "="*60)
        print("  HYBRIDRAG SNAPSHOT  " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        print("="*60)

        # Get all registered databases
        try:
            registry = get_registry()
            databases = registry.list_all()
        except Exception:
            databases = []

        if not databases:
            # Fall back to working dir only
            db_path = Path(self.working_dir)
            if db_path.exists():
                json_files = list(db_path.glob("*.json"))
                total_size = sum(f.stat().st_size for f in db_path.glob("*") if f.is_file())
                print(f"\n  DB: {db_path.name}")
                print(f"      Size: {format_file_size(total_size)} | Files: {len(json_files)} JSON")
            else:
                print(f"\n  No database at: {self.working_dir}")
            print("\n" + "="*60)
            return

        # Summary counters
        total_watchers = 0
        running_watchers = 0
        total_files_processed = 0
        total_db_size = 0
        all_source_folders = []

        for entry in databases:
            total_watchers += 1
            running, pid = is_watcher_running(entry.name)
            if running:
                running_watchers += 1

            # Get database stats
            db_path = Path(entry.path)
            if db_path.exists():
                db_files = list(db_path.glob("*.json"))
                db_size = sum(f.stat().st_size for f in db_path.glob("*") if f.is_file())
                total_db_size += db_size

            # Get metadata for file count
            try:
                meta = DatabaseMetadata(entry.path)
                files_ingested = meta.metadata.get("total_files_ingested", 0)
                total_files_processed += files_ingested
                # Get source folders from metadata
                for folder in meta.metadata.get("source_folders", []):
                    all_source_folders.append(folder.get("path", ""))
            except Exception:
                files_ingested = 0

            # Display per-database info
            watcher_icon = "🟢" if running else "⚪"
            watcher_text = f"PID {pid}" if running else "stopped"
            print(f"\n  [{entry.name}]")
            print(f"      Watcher: {watcher_icon} {watcher_text}")
            if entry.source_folder:
                print(f"      Source:  {entry.source_folder}")
            print(f"      Files:   {files_ingested} processed")
            print(f"      DB Size: {format_file_size(db_size) if db_path.exists() else 'N/A'}")

        # Summary
        print("\n" + "-"*60)
        print("  SUMMARY")
        print(f"      Watchers: {running_watchers}/{total_watchers} running")
        print(f"      Folders:  {len(all_source_folders)} source folders tracked")
        print(f"      Files:    {total_files_processed} total processed")
        print(f"      Storage:  {format_file_size(total_db_size)}")
        print("="*60 + "\n")

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

        # Handle backend configuration (T016)
        backend = getattr(self.args, 'backend', 'json')
        connection_string = getattr(self.args, 'connection_string', None)

        if backend == 'postgres':
            # Build backend config for PostgreSQL
            backend_config_dict = {
                'backend_type': 'postgres',
            }

            if connection_string:
                # Parse connection string
                try:
                    parsed_config = BackendConfig.from_connection_string(connection_string)
                    backend_config_dict.update({
                        'postgres_host': parsed_config.postgres_host,
                        'postgres_port': parsed_config.postgres_port,
                        'postgres_user': parsed_config.postgres_user,
                        'postgres_password': parsed_config.postgres_password,
                        'postgres_database': parsed_config.postgres_database,
                        'connection_string': connection_string,
                    })
                except Exception as e:
                    print(f"❌ Invalid connection string: {e}")
                    return
            else:
                # Use individual parameters
                password = getattr(self.args, 'postgres_password', None) or os.environ.get('POSTGRES_PASSWORD')
                backend_config_dict.update({
                    'postgres_host': getattr(self.args, 'postgres_host', 'localhost'),
                    'postgres_port': getattr(self.args, 'postgres_port', 5432),
                    'postgres_user': getattr(self.args, 'postgres_user', 'hybridrag'),
                    'postgres_password': password,
                    'postgres_database': getattr(self.args, 'postgres_database', 'hybridrag'),
                })

            # Validate PostgreSQL connection before registering (T017)
            print("🔌 Validating PostgreSQL connection...")
            is_valid, error_msg = await self._validate_postgres_connection(backend_config_dict)
            if not is_valid:
                print(f"❌ PostgreSQL connection failed: {error_msg}")
                print("\nTroubleshooting:")
                print("  1. Ensure PostgreSQL is running")
                print("  2. Check connection parameters")
                print("  3. Verify user has database access")
                print("\nOr auto-provision with: python hybridrag.py backend setup-docker")
                return

            print("✅ PostgreSQL connection validated")
            kwargs['backend_type'] = 'postgres'
            kwargs['backend_config'] = backend_config_dict
        else:
            # Default JSON backend
            kwargs['backend_type'] = 'json'
            kwargs['backend_config'] = {'backend_type': 'json'}

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
            print(f"   Backend: {kwargs.get('backend_type', 'json')}")
            print(f"   Auto-watch: {entry.auto_watch}")
            if entry.model:
                print(f"   Model: {entry.model}")

        except ValueError as e:
            print(f"❌ Registration failed: {e}")
        except Exception as e:
            print(f"❌ Unexpected error: {e}")

    async def _validate_postgres_connection(self, config_dict: dict) -> tuple:
        """
        Validate PostgreSQL connection before registering database (T017).

        Args:
            config_dict: Backend configuration dictionary with postgres_* fields

        Returns:
            Tuple of (is_valid: bool, error_message: str or None)
        """
        try:
            import asyncpg
        except ImportError:
            return False, "asyncpg package not installed. Install with: pip install asyncpg"

        # Build connection string
        host = config_dict.get('postgres_host', 'localhost')
        port = config_dict.get('postgres_port', 5432)
        user = config_dict.get('postgres_user', 'hybridrag')
        password = config_dict.get('postgres_password', '')
        database = config_dict.get('postgres_database', 'hybridrag')

        if config_dict.get('connection_string'):
            conn_str = config_dict['connection_string']
        else:
            password_part = f":{password}" if password else ""
            conn_str = f"postgresql://{user}{password_part}@{host}:{port}/{database}"

        try:
            # Attempt to connect with timeout
            conn = await asyncio.wait_for(
                asyncpg.connect(conn_str),
                timeout=10.0
            )
            try:
                # Verify pgvector extension is available
                result = await conn.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector')"
                )
                if not result:
                    return False, "pgvector extension not installed. Run: CREATE EXTENSION vector;"
                return True, None
            finally:
                await conn.close()

        except asyncio.TimeoutError:
            return False, f"Connection timed out (10s) - host {host}:{port} not reachable"
        except asyncpg.InvalidCatalogNameError:
            return False, f"Database '{database}' does not exist"
        except asyncpg.InvalidAuthorizationSpecificationError:
            return False, f"Authentication failed for user '{user}'"
        except asyncpg.PostgresConnectionError as e:
            return False, f"Connection refused - {str(e)}"
        except Exception as e:
            return False, f"Connection error: {str(e)}"

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

        show_stats = getattr(self.args, 'stats', False)

        if getattr(self.args, 'json', False):
            import json
            data = entry.to_dict()
            if show_stats:
                # Include knowledge graph stats in JSON output
                metrics = await self._collect_backend_metrics(entry, verbose=False)
                data['knowledge_graph'] = {
                    'entities': metrics.get('entity_count', 0),
                    'relations': metrics.get('relation_count', 0),
                    'chunks': metrics.get('chunk_count', 0),
                    'documents': metrics.get('doc_count', 0)
                }
            print(json.dumps(data, indent=2, default=str))
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
            print("\n⚪ Watcher stopped")

        # Knowledge graph stats (when --stats flag is provided)
        if show_stats:
            print("\n📈 Knowledge Graph Stats:")
            try:
                metrics = await self._collect_backend_metrics(entry, verbose=False)
                print(f"   Entities:     {metrics.get('entity_count', 0):,}")
                print(f"   Relations:    {metrics.get('relation_count', 0):,}")
                print(f"   Chunks:       {metrics.get('chunk_count', 0):,}")
                print(f"   Documents:    {metrics.get('doc_count', 0):,}")
                if metrics.get('warnings'):
                    for warning in metrics['warnings']:
                        print(f"   ⚠️  {warning}")
            except Exception as e:
                print(f"   ⚠️  Could not collect stats: {e}")

            # Show doc status details from kv_store_doc_status.json
            try:
                doc_status_path = Path(entry.path) / "kv_store_doc_status.json"
                if doc_status_path.exists():
                    import json
                    with open(doc_status_path, 'r') as f:
                        doc_status = json.load(f)

                    # Collect all file info
                    files_info = []
                    processing_files = []
                    total_content_size = 0

                    for doc_id, doc_data in doc_status.items():
                        if isinstance(doc_data, dict):
                            total_content_size += doc_data.get('content_length', 0)
                            if doc_data.get('file_path'):
                                info = {
                                    'path': doc_data.get('file_path', 'Unknown'),
                                    'updated': doc_data.get('updated_at', doc_data.get('created_at', '')),
                                    'chunks': doc_data.get('chunks_count', 0),
                                    'size': doc_data.get('content_length', 0),
                                    'status': doc_data.get('status', 'unknown')
                                }
                                if info['status'] == 'processing':
                                    processing_files.append(info)
                                else:
                                    files_info.append(info)

                    # Show content size
                    print(f"   Content:      {total_content_size / 1024 / 1024:.1f} MB")

                    # Show files currently processing
                    if processing_files:
                        print(f"\n⏳ Processing ({len(processing_files)} files):")
                        for item in processing_files[:3]:  # Show max 3
                            filename = Path(item.get('path', 'Unknown')).name
                            print(f"   → {filename}")

                    # Show recent processed files
                    if files_info:
                        print("\n📂 Recent Files (last 5):")
                        recent = sorted(files_info, key=lambda x: x.get('updated', ''), reverse=True)[:5]
                        for item in recent:
                            ts = item.get('updated', 'Unknown')[:19].replace('T', ' ')
                            filename = Path(item.get('path', 'Unknown')).name
                            chunks = item.get('chunks', 0)
                            print(f"   ✓ {ts}  {filename} ({chunks} chunks)")
            except Exception:
                pass  # Silently skip if can't read

        # Type-specific config
        if entry.specstory_config:
            print("\n   SpecStory Config:")
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
            print("\n   This removes the database from the registry.")
            print("   The database files will NOT be deleted.")
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
        original_multiprocess = getattr(self.args, 'multiprocess', False)
        original_yes = getattr(self.args, 'yes', False)
        original_quiet = getattr(self.args, 'quiet', False)
        original_metadata = getattr(self.args, 'metadata', None)

        self.args.folder = entry.source_folder
        self.args.db_action = db_action
        self.args.recursive = entry.recursive
        self.args.multiprocess = False  # Use single process for sync
        self.args.yes = True  # Auto-confirm for sync
        self.args.quiet = False  # Show progress
        self.args.metadata = None  # No extra metadata for sync

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
            self.args.multiprocess = original_multiprocess
            self.args.yes = original_yes
            self.args.quiet = original_quiet
            self.args.metadata = original_metadata

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
            # Fall back to --db flag if no positional argument provided
            if not name and self._db_entry:
                name = self._db_entry.name
            if not name:
                print("❌ Database name required (use --db NAME or provide name argument)")
                return

            entry = registry.get(name)
            if not entry:
                print(f"❌ Database not found: {name}")
                return

            await self._start_watcher_for_db(entry, use_systemd)

    async def _start_watcher_for_db(self, entry: DatabaseEntry, use_systemd: bool = False):
        """Start watcher for a specific database entry."""

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

                # Watcher manages its own logs with rotation (200MB max, 5 backups)
                log_dir = Path(__file__).parent / "logs"
                log_file = log_dir / f"watcher_{entry.name}.log"

                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )
                # The watcher script handles its own logging and PID file
                print(f"✅ Started watcher for {entry.name} (legacy mode)")
                print(f"   Log: {log_file}")
                return

            print("⚠️  Watcher script not found. Please create scripts/hybridrag-watcher.py")
            print("   or use: python hybridrag.py db watch start-all --systemd")
            return

        # Run the Python watcher script
        # Use the .venv Python if available, otherwise use current interpreter
        venv_python = Path(__file__).parent / ".venv" / "bin" / "python"
        python_exe = str(venv_python) if venv_python.exists() else sys.executable

        cmd = [
            python_exe,
            str(script_path),
            entry.name,
        ]

        # Watcher manages its own logs with rotation (200MB max, 5 backups)
        log_dir = Path(__file__).parent / "logs"
        log_file = log_dir / f"watcher_{entry.name}.log"

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )

        # Note: DO NOT write PID file here - the watcher script handles
        # its own PID file creation with proper flock locking to prevent
        # race conditions. See BUG-003 fix.

        print(f"✅ Started watcher for {entry.name} (PID: {proc.pid})")
        print(f"   Python: {python_exe}")
        print(f"   Log: {log_file}")

    async def run_db_watch_stop(self):
        """Stop watcher for a database."""
        try:
            registry = get_registry()
        except Exception as e:
            print(f"❌ Failed to load registry: {e}")
            return

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
            # Fall back to --db flag if no positional argument provided
            if not name and self._db_entry:
                name = self._db_entry.name
            if not name:
                print("❌ Database name required (use --db NAME or provide name argument)")
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
        # Fall back to --db flag if no positional argument provided
        if not name and self._db_entry:
            name = self._db_entry.name

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
                print("   Status: ⚪ Stopped")
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

    # ========================================
    # Backend Management Commands
    # ========================================

    async def run_backend_command(self):
        """Route backend management subcommands."""
        backend_cmd = getattr(self.args, 'backend_command', None)

        if not backend_cmd:
            print("❌ No backend subcommand specified")
            print("\nUsage: python hybridrag.py backend <command>")
            print("\nCommands:")
            print("  status       - Show backend status and metrics")
            print("  setup-docker - Auto-provision PostgreSQL with pgvector via Docker")
            print("  migrate      - Migrate database from JSON to PostgreSQL")
            return

        if backend_cmd == 'status':
            await self.show_backend_status()
        elif backend_cmd == 'setup-docker':
            await self.setup_docker()
        elif backend_cmd == 'migrate':
            await self.run_migrate()
        else:
            print(f"❌ Unknown backend command: {backend_cmd}")

    async def setup_docker(self):
        """
        Auto-provision PostgreSQL with pgvector via Docker (T018-T019).

        Implements idempotent container management:
        - Detects if container is already running
        - Reuses existing container if healthy
        - Creates new container if needed
        - Provides helpful errors if Docker is unavailable
        """
        import shutil
        import subprocess

        port = getattr(self.args, 'port', 5432)
        password = getattr(self.args, 'password', 'hybridrag_default')
        data_dir = getattr(self.args, 'data_dir', None)
        force = getattr(self.args, 'force', False)

        # Check if Docker is available
        docker_path = shutil.which('docker')
        if not docker_path:
            print("❌ Docker not found in PATH")
            print("\nTo use auto-provisioning, install Docker:")
            print("  - Desktop: https://www.docker.com/products/docker-desktop")
            print("  - Linux: https://docs.docker.com/engine/install/")
            print("\nAlternatively, connect to existing PostgreSQL:")
            print("  python hybridrag.py db register mydb --backend postgres \\")
            print("    --connection-string postgresql://user:pass@host:5432/db --path ./db")
            return

        # Check if Docker daemon is running
        try:
            result = subprocess.run(
                ['docker', 'info'],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode != 0:
                print("❌ Docker daemon is not running")
                print("\nStart Docker and try again")
                return
        except subprocess.TimeoutExpired:
            print("❌ Docker daemon not responding")
            return
        except Exception as e:
            print(f"❌ Error checking Docker: {e}")
            return

        container_name = 'hybridrag-postgres'

        # Check if container already exists (T019 - idempotent management)
        try:
            result = subprocess.run(
                ['docker', 'inspect', container_name],
                capture_output=True,
                text=True
            )
            container_exists = result.returncode == 0

            if container_exists and not force:
                # Check if it's running
                result = subprocess.run(
                    ['docker', 'inspect', '-f', '{{.State.Running}}', container_name],
                    capture_output=True,
                    text=True
                )
                is_running = result.stdout.strip() == 'true'

                if is_running:
                    # Check if it's healthy
                    result = subprocess.run(
                        ['docker', 'inspect', '-f', '{{.State.Health.Status}}', container_name],
                        capture_output=True,
                        text=True
                    )
                    health = result.stdout.strip()

                    if health == 'healthy':
                        print(f"✅ Container '{container_name}' is already running and healthy")
                        self._print_docker_connection_info(port, password)
                        return
                    else:
                        print(f"⚠️  Container exists but health status: {health}")
                        print("   Waiting for container to become healthy...")
                else:
                    print("⚠️  Container exists but is not running. Starting...")
                    subprocess.run(['docker', 'start', container_name], check=True)

        except Exception as e:
            print(f"⚠️  Error checking container status: {e}")
            container_exists = False

        # If container doesn't exist or force is set, use docker-compose
        if not container_exists or force:
            print("🐳 Provisioning PostgreSQL with pgvector...")

            # Find docker-compose file
            script_dir = Path(__file__).parent
            compose_file = script_dir / 'docker' / 'docker-compose.postgres.yaml'

            if not compose_file.exists():
                print(f"❌ Docker compose file not found: {compose_file}")
                return

            # Build environment
            env = os.environ.copy()
            env['POSTGRES_PASSWORD'] = password
            env['POSTGRES_PORT'] = str(port)
            if data_dir:
                env['POSTGRES_DATA_DIR'] = data_dir

            # Run docker-compose
            compose_cmd = ['docker', 'compose', '-f', str(compose_file)]
            if force:
                compose_cmd.extend(['up', '-d', '--force-recreate'])
            else:
                compose_cmd.extend(['up', '-d'])

            try:
                result = subprocess.run(
                    compose_cmd,
                    env=env,
                    capture_output=True,
                    text=True
                )
                if result.returncode != 0:
                    print(f"❌ Docker compose failed: {result.stderr}")
                    return
            except Exception as e:
                print(f"❌ Failed to run docker-compose: {e}")
                return

        # Wait for container to be healthy
        print("⏳ Waiting for PostgreSQL to be ready...")
        max_attempts = 30
        for attempt in range(max_attempts):
            try:
                result = subprocess.run(
                    ['docker', 'inspect', '-f', '{{.State.Health.Status}}', container_name],
                    capture_output=True,
                    text=True
                )
                health = result.stdout.strip()
                if health == 'healthy':
                    break
                await asyncio.sleep(2)
            except Exception:
                await asyncio.sleep(2)
        else:
            print("⚠️  Container did not become healthy in time")
            print("   Check logs with: docker logs hybridrag-postgres")
            return

        print("✅ PostgreSQL with pgvector is ready!")
        self._print_docker_connection_info(port, password)

    def _print_docker_connection_info(self, port: int, password: str):
        """Print connection information for Docker PostgreSQL."""
        print("\n📌 Connection Details:")
        print(f"   Host:     localhost:{port}")
        print("   Database: hybridrag")
        print("   User:     hybridrag")
        print(f"   Password: {password}")
        print("\n📋 Connection String:")
        print(f"   postgresql://hybridrag:{password}@localhost:{port}/hybridrag")
        print("\n📚 Register a database with this backend:")
        print("   python hybridrag.py db register mydb \\")
        print("     --backend postgres \\")
        print(f"     --connection-string postgresql://hybridrag:{password}@localhost:{port}/hybridrag \\")
        print("     --path ./mydb --source ./data")
        print("\n🔧 Manage container:")
        print("   docker logs hybridrag-postgres    # View logs")
        print("   docker stop hybridrag-postgres    # Stop container")
        print("   docker start hybridrag-postgres   # Start container")

    async def run_migrate(self):
        """
        Run data migration from JSON to PostgreSQL (T020).

        Implements:
        - Watcher pause during migration (T024)
        - MigrationJob orchestration (T021)
        - Checkpoint/resume support (T022)
        - Post-migration verification (T023)
        - Staged migration with backup (Phase 7)
        """
        from pathlib import Path

        from src.config.backend_config import BackendConfig
        from src.database_registry import get_registry
        from src.migration import (
            DatabaseBackup,
            MigrationCheckpoint,
            MigrationJob,
            StagedMigration,
        )

        # Get arguments
        db_name = getattr(self.args, 'name', None)
        # Fall back to --db flag if no positional argument provided
        if not db_name and self._db_entry:
            db_name = self._db_entry.name
        connection_string = getattr(self.args, 'connection_string', None)
        batch_size = getattr(self.args, 'batch_size', 1000)
        dry_run = getattr(self.args, 'dry_run', False)
        skip_verify = getattr(self.args, 'skip_verify', False)
        resume_job_id = getattr(self.args, 'resume', None)
        pause_watcher = getattr(self.args, 'pause_watcher', True)
        skip_confirm = getattr(self.args, 'yes', False)

        # Staged migration options (Phase 7)
        staged_mode = getattr(self.args, 'staged', False)
        backup_only = getattr(self.args, 'backup_only', False)
        rollback_id = getattr(self.args, 'rollback', None)
        list_backups = getattr(self.args, 'list_backups', False)

        # Load registry and find database
        try:
            registry = get_registry()
        except Exception as e:
            print(f"❌ Failed to load registry: {e}")
            return

        entry = registry.get(db_name)
        if not entry:
            print(f"❌ Database not found: {db_name}")
            print("\nRegistered databases:")
            for db in registry.list_all():
                print(f"  - {db.name}")
            return

        # Get source path first (needed for all operations)
        source_path = Path(entry.path)
        if not source_path.exists():
            print(f"❌ Database path not found: {source_path}")
            return

        # ─────────────────────────────────────────────────────────────────
        # Phase 7: Backup Operations (backup-only, list-backups, rollback)
        # These don't require connection string - work with local files only
        # ─────────────────────────────────────────────────────────────────

        # List backups option
        if list_backups:
            backup_mgr = DatabaseBackup(db_name, source_path)
            backups = backup_mgr.list_backups()

            if not backups:
                print(f"\n📋 No backups found for '{db_name}'")
                return

            print(f"\n📋 Backups for '{db_name}'")
            print("="*60)
            for b in backups:
                size_kb = b.total_size_bytes / 1024
                print(f"   {b.backup_id:20} | {b.file_count:3} files | {size_kb:,.1f} KB | {b.created_at[:19]}")
            print("="*60)
            return

        # Backup only option
        if backup_only:
            print(f"\n💾 Creating backup for '{db_name}'...")
            backup_mgr = DatabaseBackup(db_name, source_path)
            metadata = backup_mgr.create_backup()
            print("\n✅ Backup created successfully")
            print(f"   Backup ID:  {metadata.backup_id}")
            print(f"   Files:      {metadata.file_count}")
            print(f"   Size:       {metadata.total_size_bytes / 1024:.1f} KB")
            print(f"   Location:   {metadata.backup_path}")
            return

        # Rollback option
        if rollback_id:
            print(f"\n⏪ Rolling back '{db_name}' to backup: {rollback_id}")
            backup_mgr = DatabaseBackup(db_name, source_path)

            # Verify backup exists
            backups = backup_mgr.list_backups()
            backup_exists = any(b.backup_id == rollback_id for b in backups)

            if not backup_exists:
                print(f"❌ Backup not found: {rollback_id}")
                print("\nAvailable backups:")
                for b in backups:
                    print(f"   - {b.backup_id}")
                return

            if not skip_confirm:
                print("\n⚠️  Warning: This will overwrite current database files")
                response = input("Proceed with rollback? [y/N] ").strip().lower()
                if response != 'y':
                    print("Rollback cancelled")
                    return

            success = backup_mgr.restore_backup(rollback_id)
            if success:
                print(f"\n✅ Rollback complete - database restored from {rollback_id}")
            else:
                print("\n❌ Rollback failed")
            return

        # ─────────────────────────────────────────────────────────────────
        # For migration operations (not backup-only), validate prerequisites
        # ─────────────────────────────────────────────────────────────────

        # Check source backend
        source_backend = getattr(entry, 'backend_type', 'json') or 'json'
        if source_backend != 'json':
            print(f"❌ Database '{db_name}' is already using {source_backend} backend")
            print("   Migration is only supported from JSON to PostgreSQL")
            return

        # Get or validate connection string
        if not connection_string:
            # Try to get from backend config
            backend_cfg = getattr(entry, 'backend_config', None) or {}
            if isinstance(backend_cfg, dict) and backend_cfg.get('connection_string'):
                connection_string = backend_cfg['connection_string']
            else:
                print("❌ No connection string specified")
                print("\nProvide connection string via:")
                print("  --connection-string postgresql://user:pass@host:5432/db")
                print("\nOr register the database with backend config:")
                print(f"  python hybridrag.py db register {db_name} --backend postgres --connection-string ...")
                return

        # Preview mode
        if dry_run:
            print("\n🔍 DRY RUN - Migration Preview")
            print("="*50)
            print(f"Database:   {db_name}")
            print(f"Source:     {source_path}")
            print("Target:     PostgreSQL")
            print(f"Batch Size: {batch_size}")

            # Count records in each category
            import json as json_lib
            counts = {}
            json_files = [
                ('kv_store_full_docs.json', 'entities'),
                ('graph_chunk_entity_relation.json', 'relations'),
                ('text_chunks.json', 'chunks'),
                ('doc_status.json', 'documents'),
            ]
            for filename, label in json_files:
                filepath = source_path / filename
                if filepath.exists():
                    try:
                        with open(filepath, 'r') as f:
                            data = json_lib.load(f)
                            counts[label] = len(data) if isinstance(data, dict) else 0
                    except Exception:
                        counts[label] = 0
                else:
                    counts[label] = 0

            print("\n📊 Records to Migrate:")
            total = sum(counts.values())
            for label, count in counts.items():
                print(f"   {label.capitalize():12} {count:>8,}")
            print(f"   {'Total':12} {total:>8,}")

            print("\n✓ No changes made (dry run)")
            return

        # Confirmation
        if not skip_confirm:
            print("\n⚠️  Migration Warning")
            print("="*50)
            print(f"Database: {db_name}")
            print(f"From:     JSON ({source_path})")
            print("To:       PostgreSQL")
            print("\nThis will copy all data to PostgreSQL.")
            print("The original JSON files will be preserved.")

            response = input("\nProceed with migration? [y/N] ").strip().lower()
            if response != 'y':
                print("Migration cancelled")
                return

        # Pause watcher if requested (T024)
        watcher_was_running = False
        if pause_watcher:
            try:
                from src.watcher_control import pause_watcher as do_pause
                watcher_was_running = await do_pause(db_name)
                if watcher_was_running:
                    print(f"⏸️  Paused watcher for '{db_name}'")
            except ImportError:
                # Watcher control not available - not critical
                pass
            except Exception as e:
                print(f"⚠️  Could not pause watcher: {e}")

        try:
            # ─────────────────────────────────────────────────────────────────
            # Phase 7: Staged Migration Workflow (if --staged is specified)
            # ─────────────────────────────────────────────────────────────────
            if staged_mode:
                print(f"\n🔄 STAGED MIGRATION for '{db_name}'")
                print("="*60)
                print("Workflow: Backup → Staging → Verify → Promote")
                print("="*60)

                staged = StagedMigration(
                    database_name=db_name,
                    source_path=source_path,
                    target_connection=connection_string,
                )

                # Check if resuming a previous staged migration
                if staged.state['phase'] not in ('initial', 'promoted', 'rolled_back'):
                    print(f"\n⚠️  Previous staged migration detected at phase: {staged.state['phase']}")
                    print("   Resuming from last checkpoint...")

                # Phase 1: Prepare (create backup)
                if staged.state['phase'] in ('initial',):
                    print("\n📦 Phase 1/4: Creating backup...")
                    if not await staged.prepare():
                        print("❌ Preparation failed")
                        return
                    print(f"   ✓ Backup created: {staged.state['backup_id']}")

                # Phase 2: Migrate to staging tables
                if staged.state['phase'] in ('prepared',):
                    print("\n🚀 Phase 2/4: Migrating to staging...")
                    if not await staged.migrate_to_staging():
                        print("❌ Staging migration failed")
                        print(f"   Backup available: {staged.state['backup_id']}")
                        print(f"   To rollback: python hybridrag.py backend migrate {db_name} --rollback {staged.state['backup_id']}")
                        return
                    print("   ✓ Data migrated to staging tables")

                # Phase 3: Verify staging
                if staged.state['phase'] in ('staged',):
                    print("\n🔍 Phase 3/4: Verifying staged data...")
                    if not await staged.verify_staging():
                        print("\n❌ Verification failed - NOT promoting to production")
                        print(f"   Backup available: {staged.state['backup_id']}")
                        print(f"   To rollback: python hybridrag.py backend migrate {db_name} --rollback {staged.state['backup_id']}")
                        return
                    print("   ✓ Verification passed")

                # Phase 4: Promote staging to production
                if staged.state['phase'] in ('verified',):
                    print("\n⬆️  Phase 4/4: Promoting staging to production...")
                    if not await staged.promote():
                        print("❌ Promotion failed")
                        print(f"   Backup available: {staged.state['backup_id']}")
                        return
                    print("   ✓ Staging tables promoted to production")

                # Success! Update registry to use PostgreSQL backend (BUG-004 fix)
                try:
                    registry.update(
                        db_name,
                        backend_type='postgres',
                        backend_config={
                            'connection_string': connection_string,
                            'workspace': db_name,
                        }
                    )
                except Exception as e:
                    print(f"\n⚠️  Registry update failed: {e}")
                    print("   You may need to manually update the registry")

                print("\n" + "="*60)
                print("✅ STAGED MIGRATION COMPLETED SUCCESSFULLY")
                print("="*60)
                print(f"\n📝 Registry updated: '{db_name}' now uses PostgreSQL backend")
                print(f"Backup retained: {staged.state['backup_id']}")
                print(f"To rollback if needed: python hybridrag.py backend migrate {db_name} --rollback {staged.state['backup_id']}")

            else:
                # ─────────────────────────────────────────────────────────────────
                # Standard Migration (original flow without staging)
                # ─────────────────────────────────────────────────────────────────
                # Create BackendConfig from connection string
                target_config = BackendConfig.from_connection_string(connection_string)
                target_config.postgres_workspace = db_name  # Use db_name as workspace

                # Set up checkpoint file path
                checkpoint_file = source_path / '.migration_checkpoint.json'

                # Check for existing checkpoint to resume
                existing_checkpoint = None
                if resume_job_id:
                    existing_checkpoint = MigrationCheckpoint.load(checkpoint_file)
                    if existing_checkpoint and existing_checkpoint.job_id != resume_job_id:
                        print(f"⚠️  Checkpoint job ID mismatch: expected {resume_job_id}, found {existing_checkpoint.job_id}")
                        existing_checkpoint = None

                # Create migration job
                print(f"\n🚀 Starting migration for '{db_name}'...")
                job = MigrationJob(
                    source_path=str(source_path),
                    target_config=target_config,
                    checkpoint_file=str(checkpoint_file),
                    batch_size=batch_size,
                    continue_on_error=True,
                )

                # Resume or run
                if resume_job_id and existing_checkpoint:
                    print(f"📥 Resuming job: {resume_job_id}")
                    # MigrationJob auto-loads checkpoint in __init__, so just run()
                result = await job.run(verify=not skip_verify)

                # Show results
                print("\n" + "="*50)
                if result.success:
                    print("✅ MIGRATION COMPLETED SUCCESSFULLY")
                else:
                    print("❌ MIGRATION FAILED")

                # Access checkpoint for detailed stats
                checkpoint = result.checkpoint
                print(f"\nJob ID: {checkpoint.job_id}")
                print(f"Status: {result.status.value}")
                print(f"Duration: {result.duration_seconds:.1f}s")

                total_records = (checkpoint.entities_total + checkpoint.relations_total +
                               checkpoint.chunks_total + checkpoint.docs_total)
                migrated_records = (checkpoint.entities_migrated + checkpoint.relations_migrated +
                                   checkpoint.chunks_migrated + checkpoint.docs_migrated)
                failed_records = total_records - migrated_records

                print("\nRecords:")
                print(f"   Total:    {total_records:,}")
                print(f"   Migrated: {migrated_records:,}")
                print(f"   Failed:   {failed_records:,}")

                if checkpoint.last_error:
                    print(f"\n❌ Error: {checkpoint.last_error}")

                # Show verification result if run internally
                if result.verification_passed is not None:
                    if result.verification_passed:
                        print("\n✅ Post-migration verification passed")
                    else:
                        print("\n⚠️  Post-migration verification found discrepancies")

                # Update registry to use PostgreSQL backend (BUG-004 fix)
                if result.success:
                    try:
                        registry.update(
                            db_name,
                            backend_type='postgres',
                            backend_config={
                                'connection_string': connection_string,
                                'workspace': db_name,
                            }
                        )
                        print(f"\n📝 Registry updated: '{db_name}' now uses PostgreSQL backend")
                    except Exception as e:
                        print(f"\n⚠️  Registry update failed: {e}")
                        print("   Run: python hybridrag.py db update <name> --backend postgres --connection-string <conn>")

        finally:
            # Resume watcher if it was paused (T024)
            if pause_watcher and watcher_was_running:
                try:
                    from src.watcher_control import resume_watcher as do_resume
                    await do_resume(db_name)
                    print(f"▶️  Resumed watcher for '{db_name}'")
                except ImportError:
                    pass
                except Exception as e:
                    print(f"⚠️  Could not resume watcher: {e}")

    async def show_backend_status(self):
        """Show backend status with storage metrics."""
        try:
            registry = get_registry()
        except Exception as e:
            print(f"❌ Failed to load registry: {e}")
            return

        # Determine which database to show status for
        name = getattr(self.args, 'name', None)
        # Fall back to --db flag if no positional argument provided
        if not name and self._db_entry:
            name = self._db_entry.name
        output_json = getattr(self.args, 'json', False)
        verbose = getattr(self.args, 'verbose', False)

        if name:
            entry = registry.get(name)
            if not entry:
                print(f"❌ Database not found: {name}")
                return
            await self._show_single_backend_status(entry, output_json, verbose)
        else:
            # Show status for all databases
            databases = registry.list_all()
            if not databases:
                print("❌ No databases registered")
                return

            if output_json:
                results = []
                for entry in databases:
                    status = await self._collect_backend_metrics(entry, verbose)
                    results.append(status)
                print(json.dumps(results, indent=2, default=str))
            else:
                print("\n📊 Backend Status Overview")
                print("="*70)
                for entry in databases:
                    await self._show_single_backend_status(entry, False, verbose)
                    print("-"*70)

    async def _show_single_backend_status(self, entry: 'DatabaseEntry', output_json: bool, verbose: bool):
        """Show backend status for a single database."""
        metrics = await self._collect_backend_metrics(entry, verbose)

        if output_json:
            print(json.dumps(metrics, indent=2, default=str))
            return

        # Header
        print(f"\n🗄️  Database: {entry.name}")
        print(f"   Backend Type: {metrics['backend_type']}")
        print(f"   Path: {entry.path}")

        # Connection status
        conn_status = "🟢 Connected" if metrics['connected'] else "🔴 Disconnected"
        print(f"   Connection: {conn_status}")

        # Entity/relation counts
        print("\n   📈 Storage Metrics:")
        print(f"      Entities:    {metrics.get('entity_count', 'N/A'):,}")
        print(f"      Relations:   {metrics.get('relation_count', 'N/A'):,}")
        print(f"      Chunks:      {metrics.get('chunk_count', 'N/A'):,}")
        print(f"      Documents:   {metrics.get('doc_count', 'N/A'):,}")

        # File sizes (JSON backend only)
        if metrics['backend_type'] == 'json' and 'storage_size' in metrics:
            storage = metrics['storage_size']
            print("\n   💾 Storage Size:")
            print(f"      Total:       {storage.get('total_mb', 0):.2f} MB")

            if verbose and 'files' in storage:
                for fname, size_mb in storage['files'].items():
                    print(f"        {fname}: {size_mb:.2f} MB")

            # Warnings
            warnings = metrics.get('warnings', [])
            if warnings:
                print("\n   ⚠️  Warnings:")
                for warning in warnings:
                    print(f"      - {warning}")

        # PostgreSQL connection info
        if metrics['backend_type'] == 'postgres' and verbose:
            config = metrics.get('connection_config', {})
            if config:
                print("\n   🔗 Connection Details:")
                print(f"      Host: {config.get('host', 'N/A')}:{config.get('port', 'N/A')}")
                print(f"      Database: {config.get('database', 'N/A')}")
                print(f"      Workspace: {config.get('workspace', 'N/A')}")

    async def _collect_backend_metrics(self, entry: 'DatabaseEntry', verbose: bool) -> dict:
        """Collect backend metrics for a database entry."""
        # Get backend configuration
        backend_config = entry.get_backend_config()
        backend_type = backend_config.backend_type.value

        metrics = {
            'database_name': entry.name,
            'backend_type': backend_type,
            'path': str(entry.path),
            'connected': False,
            'entity_count': 0,
            'relation_count': 0,
            'chunk_count': 0,
            'doc_count': 0,
            'warnings': []
        }

        try:
            if backend_type == 'json':
                metrics.update(await self._collect_json_metrics(entry.path, backend_config, verbose))
            elif backend_type == 'postgres':
                metrics.update(await self._collect_postgres_metrics(entry, backend_config, verbose))
            else:
                metrics['warnings'].append(f"Unknown backend type: {backend_type}")
        except Exception as e:
            metrics['warnings'].append(f"Error collecting metrics: {str(e)}")

        return metrics

    async def _collect_json_metrics(self, db_path: str, config: BackendConfig, verbose: bool) -> dict:
        """Collect metrics for JSON file backend."""
        from pathlib import Path

        db_dir = Path(db_path)
        metrics = {
            'connected': db_dir.exists(),
            'storage_size': {'total_mb': 0, 'files': {}},
            'warnings': []
        }

        if not db_dir.exists():
            metrics['warnings'].append(f"Database directory does not exist: {db_path}")
            return metrics

        # Count entities/relations from graph file
        graph_file = db_dir / "graph_chunk_entity_relation.graphml"
        if graph_file.exists():
            try:
                import networkx as nx
                graph = nx.read_graphml(str(graph_file))
                metrics['entity_count'] = graph.number_of_nodes()
                metrics['relation_count'] = graph.number_of_edges()
            except Exception as e:
                metrics['warnings'].append(f"Could not read graph: {e}")

        # Count chunks from vector storage
        chunks_file = db_dir / "vdb_chunks.json"
        if chunks_file.exists():
            try:
                with open(chunks_file, 'r') as f:
                    chunk_data = json.load(f)
                    if isinstance(chunk_data, dict):
                        metrics['chunk_count'] = len(chunk_data.get('data', []))
                    elif isinstance(chunk_data, list):
                        metrics['chunk_count'] = len(chunk_data)
            except Exception as e:
                metrics['warnings'].append(f"Could not read chunks: {e}")

        # Count documents from doc status
        doc_status_file = db_dir / "kv_store_doc_status.json"
        if doc_status_file.exists():
            try:
                with open(doc_status_file, 'r') as f:
                    doc_data = json.load(f)
                    metrics['doc_count'] = len(doc_data)
            except Exception as e:
                metrics['warnings'].append(f"Could not read doc status: {e}")

        # Calculate file sizes
        total_size = 0
        for f in db_dir.glob("*.json"):
            size_bytes = f.stat().st_size
            size_mb = size_bytes / (1024 * 1024)
            metrics['storage_size']['files'][f.name] = size_mb
            total_size += size_mb

            # Check threshold warnings
            if size_mb > config.file_size_warning_mb:
                metrics['warnings'].append(
                    f"File {f.name} exceeds {config.file_size_warning_mb}MB threshold: {size_mb:.1f}MB"
                )

        # Add graphml file size
        if graph_file.exists():
            size_bytes = graph_file.stat().st_size
            size_mb = size_bytes / (1024 * 1024)
            metrics['storage_size']['files'][graph_file.name] = size_mb
            total_size += size_mb

        metrics['storage_size']['total_mb'] = total_size

        # Total size warning
        if total_size > config.total_size_warning_mb:
            metrics['warnings'].append(
                f"Total storage exceeds {config.total_size_warning_mb}MB threshold: {total_size:.1f}MB. "
                f"Consider migrating to PostgreSQL backend."
            )

        return metrics

    async def _collect_postgres_metrics(self, entry: 'DatabaseEntry', config: BackendConfig, verbose: bool) -> dict:
        """Collect metrics for PostgreSQL backend."""
        metrics = {
            'connected': False,
            'warnings': [],
            'connection_config': {
                'host': config.postgres_host,
                'port': config.postgres_port,
                'database': config.postgres_database,
                'workspace': config.postgres_workspace
            }
        }

        try:
            import asyncpg
        except ImportError:
            metrics['warnings'].append("asyncpg not installed - cannot query PostgreSQL metrics")
            return metrics

        try:
            conn_str = config.get_connection_string()
            if not conn_str:
                metrics['warnings'].append("No PostgreSQL connection string configured")
                return metrics

            conn = await asyncpg.connect(conn_str)
            try:
                metrics['connected'] = True

                workspace = config.postgres_workspace

                # Count entities
                entity_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM lightrag_entities WHERE workspace = $1",
                    workspace
                )
                metrics['entity_count'] = entity_count or 0

                # Count relations
                relation_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM lightrag_relations WHERE workspace = $1",
                    workspace
                )
                metrics['relation_count'] = relation_count or 0

                # Count chunks
                chunk_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM lightrag_chunks WHERE workspace = $1",
                    workspace
                )
                metrics['chunk_count'] = chunk_count or 0

                # Count documents
                doc_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM lightrag_doc_status WHERE workspace = $1",
                    workspace
                )
                metrics['doc_count'] = doc_count or 0

            finally:
                await conn.close()

        except Exception as e:
            metrics['warnings'].append(f"PostgreSQL connection error: {str(e)}")

        return metrics

    # ========================================
    # Logs Management Commands
    # ========================================

    async def run_logs_command(self):
        """Route logs management subcommands."""
        logs_cmd = getattr(self.args, 'logs_command', None)

        if not logs_cmd:
            print("❌ No logs subcommand specified")
            print("\nUsage: python hybridrag.py logs <command>")
            print("\nCommands:")
            print("  clean  - Clean old log files")
            print("  show   - Show log file info")
            return

        if logs_cmd == 'clean':
            await self.run_logs_clean()
        elif logs_cmd == 'show':
            await self.run_logs_show()
        else:
            print(f"❌ Unknown logs command: {logs_cmd}")

    async def run_logs_clean(self):
        """Clean old log files based on age or size."""
        import time as time_module

        log_dir = Path(__file__).parent / "logs"
        if not log_dir.exists():
            print("📁 No logs directory found")
            return

        days = getattr(self.args, 'days', 7)
        max_size_mb = getattr(self.args, 'size', None)
        dry_run = getattr(self.args, 'dry_run', False)
        clean_all = getattr(self.args, 'all', False)

        # Collect log files
        log_files = list(log_dir.glob("*.log*"))
        if not log_files:
            print("📁 No log files found")
            return

        # Calculate current stats
        total_size = sum(f.stat().st_size for f in log_files) / (1024 * 1024)
        print(f"📊 Current logs: {len(log_files)} files, {total_size:.1f} MB")

        # Determine files to delete
        files_to_delete = []
        cutoff = time_module.time() - (days * 24 * 60 * 60)

        for log_file in log_files:
            if clean_all:
                files_to_delete.append(log_file)
            elif log_file.stat().st_mtime < cutoff:
                files_to_delete.append(log_file)

        # If size threshold specified, also check that
        if max_size_mb and total_size > max_size_mb:
            # Sort by age, delete oldest first until under threshold
            sorted_logs = sorted(log_files, key=lambda f: f.stat().st_mtime)
            current_size = total_size
            for log_file in sorted_logs:
                if current_size <= max_size_mb:
                    break
                if log_file not in files_to_delete:
                    files_to_delete.append(log_file)
                    current_size -= log_file.stat().st_size / (1024 * 1024)

        if not files_to_delete:
            print(f"✅ No logs older than {days} days to clean")
            return

        # Show what will be deleted
        delete_size = sum(f.stat().st_size for f in files_to_delete) / (1024 * 1024)
        print(f"\n{'Would delete' if dry_run else 'Deleting'}: {len(files_to_delete)} files ({delete_size:.1f} MB)")

        for f in files_to_delete[:10]:  # Show first 10
            age_days = (time_module.time() - f.stat().st_mtime) / (24 * 60 * 60)
            size_mb = f.stat().st_size / (1024 * 1024)
            print(f"  {'🗑️ ' if not dry_run else '📋 '}{f.name} ({size_mb:.1f} MB, {age_days:.0f} days old)")

        if len(files_to_delete) > 10:
            print(f"  ... and {len(files_to_delete) - 10} more")

        if dry_run:
            print("\n💡 Run without --dry-run to delete these files")
            return

        # Delete files
        deleted = 0
        for f in files_to_delete:
            try:
                f.unlink()
                deleted += 1
            except Exception as e:
                print(f"  ⚠️  Failed to delete {f.name}: {e}")

        print(f"\n✅ Deleted {deleted} files, freed {delete_size:.1f} MB")

    async def run_logs_show(self):
        """Show log file information."""
        log_dir = Path(__file__).parent / "logs"
        if not log_dir.exists():
            print("📁 No logs directory found")
            return

        db_name = getattr(self.args, 'name', None)
        import time as time_module

        # Collect log files
        if db_name:
            log_files = list(log_dir.glob(f"*{db_name}*.log*"))
        else:
            log_files = list(log_dir.glob("*.log*"))

        if not log_files:
            print("📁 No log files found")
            return

        # Sort by modification time (newest first)
        log_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

        total_size = sum(f.stat().st_size for f in log_files) / (1024 * 1024)

        print(f"📁 Log Directory: {log_dir}")
        print(f"📊 Total: {len(log_files)} files, {total_size:.1f} MB")
        print()
        print(f"{'File':<45} {'Size':>10} {'Age':>10}")
        print("-" * 67)

        for f in log_files[:20]:  # Show first 20
            age_days = (time_module.time() - f.stat().st_mtime) / (24 * 60 * 60)
            size_mb = f.stat().st_size / (1024 * 1024)

            if age_days < 1:
                age_str = f"{age_days * 24:.0f}h"
            else:
                age_str = f"{age_days:.0f}d"

            name = f.name[:42] + "..." if len(f.name) > 45 else f.name
            print(f"{name:<45} {size_mb:>8.1f}MB {age_str:>10}")

        if len(log_files) > 20:
            print(f"... and {len(log_files) - 20} more files")

        print()
        print("💡 Clean old logs: python hybridrag.py logs clean --days 7")
        print("💡 Auto-rotation: 200MB max per file, 5 backups, 7-day cleanup")


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

    # Note: 'list-dbs' removed - use 'db list' instead
    # Note: 'db-info' removed - use 'db show <name>' instead

    # Snapshot command - quick status overview
    snapshot_parser = subparsers.add_parser('snapshot', help='Quick status snapshot: watchers, folders, files processed')

    # Monitor command (TUI dashboard)
    monitor_parser = subparsers.add_parser('monitor', help='Launch interactive TUI dashboard')
    monitor_parser.add_argument('--refresh', '-r', type=int, default=2,
                               help='Refresh interval in seconds (default: 2)')
    monitor_parser.add_argument('--new', '-n', action='store_true',
                               help='Start with new database wizard')
    monitor_parser.add_argument('--mouse', '-m', action='store_true',
                               help='Enable mouse support (disabled by default to prevent terminal issues)')

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
    # Backend configuration (T016)
    db_register.add_argument('--backend', choices=['json', 'postgres'],
                            default='json', help='Storage backend type (default: json)')
    db_register.add_argument('--connection-string',
                            help='PostgreSQL connection string (e.g., postgresql://user:pass@host:5432/db)')
    db_register.add_argument('--postgres-host', default='localhost',
                            help='PostgreSQL host (default: localhost)')
    db_register.add_argument('--postgres-port', type=int, default=5432,
                            help='PostgreSQL port (default: 5432)')
    db_register.add_argument('--postgres-user', default='hybridrag',
                            help='PostgreSQL user (default: hybridrag)')
    db_register.add_argument('--postgres-password',
                            help='PostgreSQL password (or set POSTGRES_PASSWORD env var)')
    db_register.add_argument('--postgres-database', default='hybridrag',
                            help='PostgreSQL database name (default: hybridrag)')

    # db list
    db_list = db_subparsers.add_parser('list', help='List all registered databases')
    db_list.add_argument('--json', action='store_true', help='Output as JSON')

    # db show
    db_show = db_subparsers.add_parser('show', help='Show database details')
    db_show.add_argument('name', help='Database name')
    db_show.add_argument('--json', action='store_true', help='Output as JSON')
    db_show.add_argument('--stats', action='store_true',
                        help='Include knowledge graph stats (entities, relations, chunks, documents)')

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

    # ========================================
    # Backend Management Commands
    # ========================================
    backend_parser = subparsers.add_parser('backend', help='Storage backend management')
    backend_subparsers = backend_parser.add_subparsers(dest='backend_command', help='Backend command')

    # backend status
    backend_status = backend_subparsers.add_parser('status', help='Show backend status and metrics')
    backend_status.add_argument('name', nargs='?', help='Database name (optional, uses current db if not specified)')
    backend_status.add_argument('--json', action='store_true', help='Output as JSON')
    backend_status.add_argument('--verbose', '-v', action='store_true', help='Show detailed metrics')

    # backend setup-docker (T018)
    backend_docker = backend_subparsers.add_parser('setup-docker',
                                                   help='Auto-provision PostgreSQL with pgvector via Docker')
    backend_docker.add_argument('--port', type=int, default=5432,
                               help='Host port for PostgreSQL (default: 5432)')
    backend_docker.add_argument('--password', default='hybridrag_default',
                               help='PostgreSQL password (default: hybridrag_default)')
    backend_docker.add_argument('--data-dir',
                               help='Host path for persistent data (default: Docker volume)')
    backend_docker.add_argument('--force', action='store_true',
                               help='Force recreate container even if running')

    # backend migrate (T020)
    backend_migrate = backend_subparsers.add_parser('migrate',
                                                    help='Migrate database from JSON to PostgreSQL')
    backend_migrate.add_argument('name', help='Database name to migrate')
    backend_migrate.add_argument('--connection-string',
                                help='PostgreSQL connection string (or uses registered backend config)')
    backend_migrate.add_argument('--batch-size', type=int, default=1000,
                                help='Batch size for migration (default: 1000)')
    backend_migrate.add_argument('--dry-run', action='store_true',
                                help='Preview migration without making changes')
    backend_migrate.add_argument('--skip-verify', action='store_true',
                                help='Skip post-migration verification')
    backend_migrate.add_argument('--resume', metavar='JOB_ID',
                                help='Resume a previous migration job')
    backend_migrate.add_argument('--pause-watcher', action='store_true', default=True,
                                help='Pause watcher during migration (default: True)')
    backend_migrate.add_argument('--yes', '-y', action='store_true',
                                help='Skip confirmation prompts')

    # Staged migration options (Phase 7 - safe migration with backup)
    backend_migrate.add_argument('--staged', action='store_true',
                                help='Use staged migration: backup → staging → verify → promote')
    backend_migrate.add_argument('--backup-only', action='store_true',
                                help='Create backup without migrating')
    backend_migrate.add_argument('--rollback', metavar='BACKUP_ID',
                                help='Rollback to a previous backup')
    backend_migrate.add_argument('--list-backups', action='store_true',
                                help='List available backups for the database')

    # ===================== LOGS COMMAND =====================
    logs_parser = subparsers.add_parser('logs', help='Manage log files')
    logs_subparsers = logs_parser.add_subparsers(dest='logs_command', help='Logs command')

    # logs clean
    logs_clean = logs_subparsers.add_parser('clean', help='Clean old log files')
    logs_clean.add_argument('--days', type=int, default=7,
                           help='Remove logs older than N days (default: 7)')
    logs_clean.add_argument('--size', type=float, default=None,
                           help='Remove logs if total size exceeds N MB')
    logs_clean.add_argument('--dry-run', action='store_true',
                           help='Show what would be deleted without deleting')
    logs_clean.add_argument('--all', action='store_true',
                           help='Remove ALL log files (use with caution)')

    # logs show
    logs_show = logs_subparsers.add_parser('show', help='Show log file info')
    logs_show.add_argument('name', nargs='?', help='Database name to show logs for')

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
    mouse = getattr(args, 'mouse', False)

    run_monitor(refresh_interval=refresh_interval, start_wizard=start_wizard, mouse=mouse)
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
