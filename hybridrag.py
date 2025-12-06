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
        use_promptchain = self.args.use_promptchain

        print(f"🔍 Query: {self.args.text}")
        print(f"   Mode: {mode}, Agentic: {use_agentic}, PromptChain: {use_promptchain}")

        if use_promptchain:
            await self._query_with_promptchain(self.args.text, mode, use_agentic)
        else:
            await self._query_with_lightrag(self.args.text, mode, use_agentic)

    async def run_interactive(self):
        """Run interactive query interface."""
        print("\n" + "="*70)
        print("🔍 HybridRAG Interactive Query Interface")
        print("="*70)

        # Import the interactive demo
        from lightrag_query_demo import LightRAGQueryInterface

        interface = LightRAGQueryInterface(working_dir=self.working_dir)
        await interface._ensure_initialized()

        print("\nCommands:")
        print("  :local, :global, :hybrid, :naive, :mix  - Switch query mode")
        print("  :context                                - Show context only")
        print("  :help                                   - Show help")
        print("  :quit                                   - Exit")
        print("\nOr just type your query directly!")
        print("="*70)

        current_mode = "hybrid"
        context_only = False

        while True:
            try:
                user_input = input(f"\n[{current_mode}]> ").strip()

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
                        print(f"✅ Switched to {current_mode} mode")
                        continue
                    elif cmd == 'context':
                        context_only = not context_only
                        print(f"{'✅ Context-only' if context_only else '❌ Full response'} mode")
                        continue
                    elif cmd == 'help':
                        self._print_help()
                        continue
                    else:
                        print(f"❌ Unknown command: {cmd}")
                        continue

                # Execute query
                result = await interface.query(
                    user_input,
                    mode=current_mode,
                    only_need_context=context_only
                )

                print(f"\n{'📚 Context:' if context_only else '💡 Response:'}")
                print("-" * 70)
                print(result)
                print("-" * 70)

            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
            except EOFError:
                break
            except Exception as e:
                print(f"❌ Error: {e}")

    async def _query_with_lightrag(self, query_text: str, mode: str, agentic: bool):
        """Execute query using LightRAG directly."""
        from lightrag import LightRAG, QueryParam
        from lightrag.llm.openai import openai_complete_if_cache, openai_embed
        from lightrag.utils import EmbeddingFunc

        # Get models from instance (CLI override or env vars)
        llm_model = self.llm_model
        embed_model = self.embed_model

        # Get appropriate API key for the LLM model
        api_key = get_api_key_for_model(llm_model)
        if not api_key:
            print(f"❌ No API key found for model: {llm_model}")
            print("   Set the appropriate env var: AZURE_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.")
            return

        # Get API key for embedding model (may be different provider)
        embed_api_key = get_api_key_for_model(embed_model)
        if not embed_api_key:
            embed_api_key = api_key  # Fall back to LLM API key

        print(f"   Using LLM: {llm_model}, Embed: {embed_model}")

        # Initialize LightRAG
        rag = LightRAG(
            working_dir=self.working_dir,
            llm_model_func=lambda prompt, system_prompt=None, history_messages=[], **kwargs:
                openai_complete_if_cache(
                    llm_model,
                    prompt,
                    system_prompt=system_prompt,
                    history_messages=history_messages,
                    api_key=api_key,
                    **kwargs
                ),
            embedding_func=EmbeddingFunc(
                embedding_dim=1536,
                func=lambda texts: openai_embed(
                    texts,
                    model=embed_model,
                    api_key=embed_api_key
                ),
            ),
        )

        await rag.initialize_storages()

        # Execute query
        result = await rag.aquery(
            query_text,
            param=QueryParam(mode=mode)
        )

        print("\n💡 Response:")
        print("-" * 70)
        print(result)
        print("-" * 70)

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
        print("\nQuery Modes:")
        print("  :local    - Specific entity relationships and details")
        print("  :global   - High-level overviews and broad patterns")
        print("  :hybrid   - Balanced combination of local and global")
        print("  :naive    - Simple vector retrieval without graph")
        print("  :mix      - Advanced multi-strategy retrieval")
        print("\nCommands:")
        print("  :context  - Toggle context-only mode (show retrieval context)")
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
        db_path = Path(self.working_dir)
        if db_path.exists():
            db_files = list(db_path.glob("*.json"))
            db_size = sum(f.stat().st_size for f in db_files) / (1024 * 1024)
            print(f"✅ Database: {db_path}")
            print(f"   Files: {len(db_files)}")
            print(f"   Size: {db_size:.1f} MB")
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
        total_size = sum(f.stat().st_size for f in other_files if f.is_file())

        print(f"\n✅ Database exists")
        print(f"   JSON files: {len(json_files)}")
        print(f"   Total files: {len(other_files)}")
        print(f"   Total size: {total_size / (1024 * 1024):.1f} MB")

        # Show file breakdown
        print("\n📁 File breakdown:")
        for pattern in ["kv_store_*.json", "vdb_*.json"]:
            files = list(db_path.glob(pattern))
            if files:
                print(f"   {pattern}: {len(files)} file(s)")

        print("="*70)


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
        """
    )

    # Global options
    parser.add_argument('--config', help='Config file path')
    parser.add_argument('--working-dir', default='./lightrag_db', help='LightRAG database directory')
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
    query_parser.add_argument('--use-promptchain', action='store_true', help='Use PromptChain for queries')

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

    return parser


async def main():
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    cli = HybridRAGCLI(args)
    return await cli.run()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
