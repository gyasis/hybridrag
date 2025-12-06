#!/usr/bin/env python3
"""
Folder to LightRAG Ingestion Script
===================================
Ingest documents from a folder (like .specstory/history) into LightRAG for querying.

Author: HybridRAG System
Date: 2025-10-01
"""

import asyncio
import logging
from pathlib import Path
from typing import List
import os
from dotenv import load_dotenv
from tqdm import tqdm
from datetime import datetime

from lightrag import LightRAG, QueryParam
from lightrag.llm.openai import openai_complete_if_cache, openai_embed
from lightrag.utils import EmbeddingFunc
from lightrag.kg.shared_storage import initialize_pipeline_status

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment
load_dotenv()

class FolderToLightRAG:
    """Ingest documents from a folder into LightRAG."""

    def __init__(
        self,
        source_folder: str,
        lightrag_working_dir: str = "./specstory_lightrag_db",
        file_extensions: List[str] = None
    ):
        """
        Initialize the folder ingestion system.

        Args:
            source_folder: Path to folder containing documents
            lightrag_working_dir: Working directory for LightRAG
            file_extensions: List of file extensions to process (e.g., ['.md', '.txt'])
        """
        self.source_folder = Path(source_folder)
        self.lightrag_working_dir = lightrag_working_dir
        self.file_extensions = file_extensions or ['.md', '.txt', '.py', '.json']

        if not self.source_folder.exists():
            raise FileNotFoundError(f"Source folder not found: {source_folder}")

        # Create working directory
        Path(self.lightrag_working_dir).mkdir(parents=True, exist_ok=True)

        # Initialize LightRAG
        self._init_lightrag()

    def _init_lightrag(self):
        """Initialize LightRAG with Azure models (via LiteLLM)."""
        logger.info(f"Initializing LightRAG in {self.lightrag_working_dir}")

        # Prefer Azure API key, fall back to OpenAI
        api_key = os.getenv("AZURE_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("AZURE_API_KEY or OPENAI_API_KEY not found in environment")

        # Get model names from environment (Azure preferred)
        llm_model = os.getenv("LIGHTRAG_MODEL", "azure/gpt-5.1")
        embed_model = os.getenv("LIGHTRAG_EMBED_MODEL", "azure/text-embedding-3-small")

        self.rag = LightRAG(
            working_dir=self.lightrag_working_dir,
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
                    api_key=api_key
                ),
            ),
            max_parallel_insert=2,  # Process 2 documents at a time
            llm_model_max_async=2,  # Reduced from 4 to minimize rate limiting
        )
        logger.info(f"LightRAG initialized successfully (LLM: {llm_model}, Embed: {embed_model})")

    def collect_files(self) -> List[Path]:
        """Collect all files from source folder with matching extensions."""
        logger.info(f"Collecting files from {self.source_folder}")

        files = []
        for ext in self.file_extensions:
            files.extend(self.source_folder.glob(f"**/*{ext}"))

        logger.info(f"Found {len(files)} files to process")
        return sorted(files)

    def read_file(self, file_path: Path) -> tuple:
        """Read and format a file as a document.

        Returns:
            tuple: (document_content, document_id) or (None, None) on error
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Create unique document ID based on file path
            doc_id = str(file_path.absolute())

            # Format as a document with metadata
            doc = f"""# {file_path.name}

**Source**: {file_path}
**Size**: {len(content)} characters
**Modified**: {datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()}

---

{content}
"""
            return doc, doc_id

        except Exception as e:
            logger.error(f"Failed to read {file_path}: {e}")
            return None, None

    async def ingest_files(self, batch_size: int = 5):
        """Ingest files into LightRAG in batches."""
        files = self.collect_files()

        if not files:
            logger.warning("No files found to ingest")
            return

        print(f"\n📚 INGESTION: Processing {len(files)} files into LightRAG")
        print("=" * 70)

        # Initialize LightRAG storages
        await self.rag.initialize_storages()
        await initialize_pipeline_status()

        ingested = 0
        failed = 0

        total_batches = (len(files) + batch_size - 1) // batch_size

        with tqdm(total=len(files), desc="Ingesting files", unit="file") as pbar:
            for batch_num, i in enumerate(range(0, len(files), batch_size), 1):
                batch_files = files[i:i+batch_size]
                batch_docs = []

                print(f"\n{'='*70}")
                print(f"📦 BATCH {batch_num}/{total_batches}: Processing files {i+1}-{min(i+batch_size, len(files))} of {len(files)}")
                print(f"{'='*70}")

                # Read batch files with document IDs
                batch_doc_ids = []
                for file_path in batch_files:
                    doc, doc_id = self.read_file(file_path)
                    if doc and doc_id:
                        batch_docs.append(doc)
                        batch_doc_ids.append(doc_id)
                    else:
                        failed += 1

                # Ingest batch with document IDs for incremental updates
                if batch_docs:
                    try:
                        print(f"🔄 Ingesting {len(batch_docs)} documents into LightRAG...")
                        # LightRAG will skip already-processed documents using 'ids' parameter
                        await self.rag.ainsert(batch_docs, ids=batch_doc_ids)
                        ingested += len(batch_docs)
                        print(f"✅ Batch {batch_num} complete: {ingested} total ingested")
                    except Exception as e:
                        logger.error(f"Batch ingestion failed: {e}")
                        print(f"❌ Batch {batch_num} failed: {e}")
                        failed += len(batch_docs)

                pbar.update(len(batch_files))
                pbar.set_postfix({
                    'Ingested': ingested,
                    'Failed': failed,
                    'Batch': f'{batch_num}/{total_batches}'
                })

                # Rate limiting - increased to reduce API rate limit errors
                if batch_num < total_batches:
                    print(f"⏸️  Rate limiting: waiting 5 seconds before next batch...")
                    await asyncio.sleep(5)

        print(f"\n✅ INGESTION COMPLETE:")
        print(f"   • Successfully ingested: {ingested} files")
        print(f"   • Failed: {failed} files")
        print(f"   • Database: {self.lightrag_working_dir}")

    async def test_query(self, query: str, mode: str = "hybrid"):
        """Test query on ingested data."""
        logger.info(f"Testing query: {query}")

        await self.rag.initialize_storages()
        await initialize_pipeline_status()

        query_param = QueryParam(mode=mode)
        result = await self.rag.aquery(query, param=query_param)

        return result


async def main():
    """Main ingestion function."""

    # Configure source folder
    source_folder = "/home/gyasis/Documents/code/PromptChain/.specstory/history"
    working_dir = "./specstory_lightrag_db"

    print(f"🔍 Folder to LightRAG Ingestion")
    print(f"Source: {source_folder}")
    print(f"Target: {working_dir}")
    print("=" * 70)

    # Create ingestion system
    ingester = FolderToLightRAG(
        source_folder=source_folder,
        lightrag_working_dir=working_dir,
        file_extensions=['.md', '.txt']  # Focus on markdown and text files
    )

    # Run ingestion
    await ingester.ingest_files(batch_size=5)

    # Test with sample queries
    print("\n🧪 Testing with sample queries...")

    test_queries = [
        "What are the main topics discussed in the PromptChain development?",
        "How was tool calling implemented?",
        "What MCP integrations were created?"
    ]

    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"Query: {query}")
        print(f"{'='*60}")

        result = await ingester.test_query(query, mode="hybrid")
        if result:
            print(result[:500] + "..." if len(result) > 500 else result)
        else:
            print("No results")


if __name__ == "__main__":
    asyncio.run(main())
