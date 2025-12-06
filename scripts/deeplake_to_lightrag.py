#!/usr/bin/env python3
"""
DeepLake to LightRAG Document Ingestion Pipeline
=================================================
This script reads JSONL-structured data from DeepLake's athena_descriptions_v4 database
and ingests it into LightRAG for knowledge graph-based RAG queries.

Author: HybridRAG System
Date: 2024
"""

import os
import json
import asyncio
import logging
from typing import List, Dict, Optional
from pathlib import Path
import deeplake
from lightrag import LightRAG, QueryParam
from lightrag.llm.openai import openai_complete_if_cache, openai_embed
from lightrag.utils import EmbeddingFunc
from lightrag.kg.shared_storage import initialize_pipeline_status
from dotenv import load_dotenv
import time
from tqdm import tqdm
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

class DeepLakeToLightRAG:
    """
    A class to handle the conversion of DeepLake athena_descriptions_v4 data
    into LightRAG documents for knowledge graph-based querying.
    """
    
    def __init__(
        self,
        deeplake_path: str = "/media/gyasis/Drive 2/Deeplake_Storage/athena_descriptions_v4",
        lightrag_working_dir: str = "./athena_lightrag_db",
        openai_api_key: Optional[str] = None
    ):
        """
        Initialize the DeepLake to LightRAG converter.
        
        Args:
            deeplake_path: Path to the DeepLake database
            lightrag_working_dir: Working directory for LightRAG database
            openai_api_key: OpenAI API key (if not in env)
        """
        self.deeplake_path = deeplake_path
        self.lightrag_working_dir = lightrag_working_dir
        # Prefer Azure API key, fall back to OpenAI
        self.api_key = openai_api_key or os.getenv("AZURE_API_KEY") or os.getenv("OPENAI_API_KEY")

        if not self.api_key:
            raise ValueError("API key not found. Set AZURE_API_KEY or OPENAI_API_KEY environment variable.")
        
        # Create working directory if it doesn't exist
        Path(self.lightrag_working_dir).mkdir(parents=True, exist_ok=True)
        
        # Initialize LightRAG (will be completed asynchronously)
        self._init_lightrag()
        
        # Open DeepLake dataset
        self._open_deeplake()
    
    def _init_lightrag(self):
        """Initialize LightRAG with Azure models (via LiteLLM)."""
        logger.info(f"Initializing LightRAG in {self.lightrag_working_dir}")

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
                    api_key=self.api_key,
                    **kwargs
                ),
            embedding_func=EmbeddingFunc(
                embedding_dim=1536,
                func=lambda texts: openai_embed(
                    texts,
                    model=embed_model,
                    api_key=self.api_key
                ),
            ),
            # Configure for medical/technical content
            max_parallel_insert=2,  # Conservative to avoid rate limits
            llm_model_max_async=4,
        )
        logger.info(f"LightRAG initialized successfully (LLM: {llm_model}, Embed: {embed_model})")
    
    async def _initialize_lightrag_storages(self):
        """Initialize LightRAG storages asynchronously."""
        logger.info("Initializing LightRAG storages...")
        await self.rag.initialize_storages()
        await initialize_pipeline_status()
        logger.info("LightRAG storages initialized successfully")
    
    def _open_deeplake(self):
        """Open the DeepLake dataset."""
        logger.info(f"Opening DeepLake dataset at {self.deeplake_path}")
        try:
            self.ds = deeplake.open(self.deeplake_path)
            logger.info(f"DeepLake dataset opened. Length: {len(self.ds)}")
            self.ds.summary()
        except Exception as e:
            logger.error(f"Failed to open DeepLake dataset: {e}")
            raise
    
    def parse_jsonl_text(self, text: str) -> Dict:
        """
        Parse the JSONL-like text from DeepLake into a structured dictionary.
        
        Args:
            text: JSONL string from DeepLake
            
        Returns:
            Parsed dictionary
        """
        try:
            # The text is already a JSON string
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON: {e}")
            return {}
    
    def format_document(self, record: Dict, metadata) -> str:
        """
        Format a DeepLake record into a readable document for LightRAG.
        
        Args:
            record: Parsed JSONL record
            metadata: Metadata from DeepLake (could be DeepLake Dict or regular dict)
            
        Returns:
            Formatted document string
        """
        doc_parts = []
        
        # Convert DeepLake metadata to regular dict if needed
        meta_dict = {}
        if metadata is not None:
            try:
                # Try to access as dict-like object
                if hasattr(metadata, '__getitem__'):
                    # Try common keys
                    for key in ['TABLE NAME', 'TABLEID', 'source_file']:
                        try:
                            meta_dict[key] = metadata[key]
                        except (KeyError, TypeError):
                            pass
                elif isinstance(metadata, dict):
                    meta_dict = metadata
            except Exception as e:
                logger.debug(f"Could not convert metadata: {e}")
        
        # Title section
        table_name = str(record.get("TABLE NAME", "Unknown Table"))
        schema_name = str(record.get("SCHEMANAME", "Unknown Schema"))
        doc_parts.append(f"# {schema_name}.{table_name}")
        doc_parts.append("")
        
        # Table description
        if "TABLE DESCRIPTION" in record:
            doc_parts.append(f"## Description")
            doc_parts.append(str(record["TABLE DESCRIPTION"]))
            doc_parts.append("")
        
        # Detailed comments
        if "COMMENTS" in record:
            doc_parts.append(f"## Details")
            doc_parts.append(str(record["COMMENTS"]))
            doc_parts.append("")
        
        # Metadata section
        doc_parts.append(f"## Metadata")
        if "TABLEID" in record:
            doc_parts.append(f"- **Table ID**: {str(record['TABLEID'])}")
        if "CATEGORY" in record:
            doc_parts.append(f"- **Category**: {str(record['CATEGORY'])}")
        if "RELEASE VERSION" in record:
            doc_parts.append(f"- **Release Version**: {str(record['RELEASE VERSION'])}")
        if "RELEASE DATE" in record:
            doc_parts.append(f"- **Release Date**: {str(record['RELEASE DATE'])}")
        if "ROW COUNT" in record:
            doc_parts.append(f"- **Row Count**: {str(record['ROW COUNT'])}")
        
        # Add source information
        doc_parts.append("")
        doc_parts.append(f"---")
        source_file = meta_dict.get('source_file', 'Unknown')
        doc_parts.append(f"*Source: {source_file}*")
        
        return "\n".join(doc_parts)
    
    def extract_documents(self, batch_size: int = 100) -> List[str]:
        """
        Extract and format documents from DeepLake in batches with progress tracking.
        
        Args:
            batch_size: Number of records to process at once
            
        Returns:
            List of formatted documents
        """
        documents = []
        total_records = len(self.ds)
        processed_count = 0
        error_count = 0
        
        print(f"\n🔍 EXTRACTION PHASE: Processing {total_records:,} records from DeepLake")
        print("=" * 70)
        
        # Create progress bar for extraction
        with tqdm(total=total_records, desc="Extracting documents", unit="docs") as pbar:
            for i in range(0, total_records, batch_size):
                batch_end = min(i + batch_size, total_records)
                
                # Access data in batches for efficiency
                try:
                    texts = self.ds["text"][i:batch_end]
                    metadatas = self.ds["metadata"][i:batch_end]
                except Exception as e:
                    logger.error(f"Failed to access batch {i}-{batch_end}: {e}")
                    pbar.update(batch_end - i)
                    error_count += batch_end - i
                    continue
                
                batch_docs = []
                for j, (text, metadata) in enumerate(zip(texts, metadatas)):
                    try:
                        # Parse JSONL text
                        record = self.parse_jsonl_text(text)
                        
                        if record:
                            # Validate essential fields
                            if "TABLE NAME" in record and "SCHEMANAME" in record:
                                document = self.format_document(record, metadata)
                                batch_docs.append(document)
                                processed_count += 1
                            else:
                                logger.warning(f"Missing essential fields at index {i+j}")
                                error_count += 1
                        else:
                            logger.warning(f"Empty record at index {i+j}")
                            error_count += 1
                            
                    except Exception as e:
                        logger.error(f"Error processing record {i+j}: {e}")
                        error_count += 1
                        continue
                    
                    # Update progress bar for each record
                    pbar.update(1)
                
                # Add batch to documents
                documents.extend(batch_docs)
                
                # Update progress description
                success_rate = (processed_count / (processed_count + error_count)) * 100 if (processed_count + error_count) > 0 else 0
                pbar.set_postfix({
                    'Success': f"{processed_count:,}",
                    'Errors': f"{error_count:,}", 
                    'Rate': f"{success_rate:.1f}%"
                })
        
        print(f"\n✅ EXTRACTION COMPLETE:")
        print(f"   • Successfully processed: {processed_count:,} documents")
        print(f"   • Errors encountered: {error_count:,} records")
        print(f"   • Success rate: {(processed_count/(processed_count+error_count)*100):.1f}%")
        print(f"   • Total extracted: {len(documents):,} documents ready for ingestion")
        
        return documents
    
    async def ingest_to_lightrag(self, documents: List[str], batch_size: int = 10):
        """
        Ingest documents into LightRAG in batches with comprehensive progress tracking.
        
        Args:
            documents: List of formatted documents
            batch_size: Number of documents to insert at once
        """
        total_docs = len(documents)
        ingested_count = 0
        failed_count = 0
        start_time = time.time()
        
        print(f"\n📚 INGESTION PHASE: Loading {total_docs:,} documents into LightRAG")
        print("=" * 70)
        print(f"📊 Configuration:")
        print(f"   • Batch size: {batch_size} documents")
        print(f"   • Expected batches: {(total_docs + batch_size - 1) // batch_size}")
        print(f"   • Rate limiting: 1 second between batches")
        print()
        
        # Create progress bar for ingestion
        with tqdm(total=total_docs, desc="Ingesting to LightRAG", unit="docs") as pbar:
            for i in range(0, total_docs, batch_size):
                batch = documents[i:i+batch_size]
                batch_end = min(i + batch_size, total_docs)
                batch_start_time = time.time()
                
                try:
                    # Insert batch into LightRAG with validation
                    await self.rag.ainsert(batch)
                    batch_success = len(batch)
                    ingested_count += batch_success
                    
                    batch_time = time.time() - batch_start_time
                    
                    # Update progress
                    pbar.update(len(batch))
                    
                    # Calculate ETA
                    elapsed = time.time() - start_time
                    if ingested_count > 0:
                        rate = ingested_count / elapsed
                        remaining = total_docs - ingested_count
                        eta_seconds = remaining / rate if rate > 0 else 0
                        eta = timedelta(seconds=int(eta_seconds))
                        
                        pbar.set_postfix({
                            'Ingested': f"{ingested_count:,}",
                            'Failed': f"{failed_count:,}",
                            'Rate': f"{rate:.1f}/s",
                            'ETA': str(eta)
                        })
                    
                    # Rate limiting - longer delay for larger batches
                    delay = max(1.0, batch_size * 0.1)
                    await asyncio.sleep(delay)
                    
                except Exception as e:
                    logger.error(f"Batch {i}-{batch_end} failed: {e}")
                    
                    # Try individual insertion for failed batch with detailed tracking
                    batch_failed = 0
                    for j, doc in enumerate(batch):
                        try:
                            await self.rag.ainsert([doc])
                            ingested_count += 1
                            await asyncio.sleep(0.5)  # Smaller delay for individual docs
                        except Exception as e2:
                            logger.error(f"Document {i+j} failed: {str(e2)[:100]}...")
                            batch_failed += 1
                            failed_count += 1
                        
                        # Update progress for each individual document
                        pbar.update(1)
                    
                    if batch_failed > 0:
                        logger.warning(f"Batch {i}-{batch_end}: {batch_failed} documents failed individual insertion")
        
        # Final statistics
        total_time = time.time() - start_time
        success_rate = (ingested_count / total_docs) * 100
        avg_rate = ingested_count / total_time if total_time > 0 else 0
        
        print(f"\n✅ INGESTION COMPLETE:")
        print(f"   • Successfully ingested: {ingested_count:,} documents")
        print(f"   • Failed documents: {failed_count:,}")
        print(f"   • Success rate: {success_rate:.1f}%")
        print(f"   • Total time: {timedelta(seconds=int(total_time))}")
        print(f"   • Average rate: {avg_rate:.1f} docs/second")
        
        # Log final statistics
        logger.info(f"Ingestion completed: {ingested_count}/{total_docs} documents ({success_rate:.1f}% success rate)")
    
    async def run_ingestion(self):
        """Run the complete ingestion pipeline with comprehensive progress tracking."""
        pipeline_start_time = time.time()
        
        print(f"\n🚀 DEEPLAKE TO LIGHTRAG INGESTION PIPELINE")
        print(f"{'='*70}")
        print(f"📅 Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📂 Source: {self.deeplake_path}")
        print(f"📁 Target: {self.lightrag_working_dir}")
        llm_model = os.getenv("LIGHTRAG_MODEL", "azure/gpt-5.1")
        embed_model = os.getenv("LIGHTRAG_EMBED_MODEL", "azure/text-embedding-3-small")
        print(f"🤖 Model: {llm_model} ({embed_model})")
        print(f"{'='*70}")
        
        try:
            # Phase 1: Initialize LightRAG storages
            print(f"\n⚙️  INITIALIZATION PHASE: Setting up LightRAG storages")
            init_start = time.time()
            await self._initialize_lightrag_storages()
            init_time = time.time() - init_start
            print(f"✅ Initialization completed in {init_time:.2f} seconds")
            
            # Phase 2: Extract documents from DeepLake
            extract_start = time.time()
            documents = self.extract_documents(batch_size=100)
            extract_time = time.time() - extract_start
            
            if not documents:
                print(f"\n❌ PIPELINE FAILED: No documents extracted from DeepLake")
                logger.error("No documents extracted from DeepLake")
                return False
            
            print(f"\n⏱️  Extraction completed in {timedelta(seconds=int(extract_time))}")
            
            # Phase 3: Ingest into LightRAG
            ingest_start = time.time()
            await self.ingest_to_lightrag(documents, batch_size=8)  # Slightly smaller batches for stability
            ingest_time = time.time() - ingest_start
            
            print(f"\n⏱️  Ingestion completed in {timedelta(seconds=int(ingest_time))}")
            
            # Phase 4: Validation and cleanup
            print(f"\n🔍 VALIDATION PHASE: Verifying LightRAG database")
            await self._validate_ingestion()
            
            # Save sample documents and metadata
            await self._save_pipeline_artifacts(documents)
            
            # Final pipeline statistics
            total_time = time.time() - pipeline_start_time
            self._print_pipeline_summary(total_time, len(documents), init_time, extract_time, ingest_time)
            
            return True
            
        except Exception as e:
            total_time = time.time() - pipeline_start_time
            print(f"\n❌ PIPELINE FAILED after {timedelta(seconds=int(total_time))}")
            print(f"   Error: {str(e)}")
            logger.error(f"Pipeline failed: {e}")
            return False
    
    async def _validate_ingestion(self):
        """Validate the ingestion by checking LightRAG database state."""
        try:
            # Test a simple query to validate the database
            test_query = "What tables are available?"
            query_param = QueryParam(mode="naive")
            result = await self.rag.aquery(test_query, param=query_param)
            
            if result:
                print(f"✅ Database validation successful - LightRAG is responsive")
                logger.info("Database validation passed")
            else:
                print(f"⚠️  Database validation warning - Empty response to test query")
                logger.warning("Database validation returned empty result")
                
        except Exception as e:
            print(f"❌ Database validation failed: {str(e)}")
            logger.error(f"Database validation failed: {e}")
    
    async def _save_pipeline_artifacts(self, documents: List[str]):
        """Save pipeline artifacts for reference and debugging."""
        try:
            artifacts_dir = Path(self.lightrag_working_dir) / "pipeline_artifacts"
            artifacts_dir.mkdir(exist_ok=True)
            
            # Save sample documents
            sample_path = artifacts_dir / "sample_documents.json"
            with open(sample_path, "w") as f:
                json.dump(documents[:10], f, indent=2)
            
            # Save pipeline metadata
            metadata = {
                "pipeline_completed_at": datetime.now().isoformat(),
                "total_documents_processed": len(documents),
                "deeplake_source": self.deeplake_path,
                "lightrag_target": self.lightrag_working_dir,
                "model_config": {
                    "llm_model": os.getenv("LIGHTRAG_MODEL", "azure/gpt-5.1"),
                    "embedding_model": os.getenv("LIGHTRAG_EMBED_MODEL", "azure/text-embedding-3-small"),
                    "embedding_dim": 1536
                }
            }
            
            metadata_path = artifacts_dir / "pipeline_metadata.json"
            with open(metadata_path, "w") as f:
                json.dump(metadata, f, indent=2)
            
            print(f"📁 Artifacts saved to: {artifacts_dir}")
            logger.info(f"Pipeline artifacts saved to {artifacts_dir}")
            
        except Exception as e:
            print(f"⚠️  Failed to save pipeline artifacts: {e}")
            logger.warning(f"Failed to save pipeline artifacts: {e}")
    
    def _print_pipeline_summary(self, total_time: float, doc_count: int, init_time: float, extract_time: float, ingest_time: float):
        """Print comprehensive pipeline summary."""
        print(f"\n🎉 PIPELINE COMPLETED SUCCESSFULLY!")
        print(f"{'='*70}")
        print(f"📊 SUMMARY STATISTICS:")
        print(f"   • Total documents processed: {doc_count:,}")
        print(f"   • Total pipeline time: {timedelta(seconds=int(total_time))}")
        print(f"   • Average processing rate: {doc_count/total_time:.1f} docs/second")
        print(f"\n⏱️  PHASE BREAKDOWN:")
        print(f"   • Initialization: {init_time:.2f}s ({init_time/total_time*100:.1f}%)")
        print(f"   • Extraction: {timedelta(seconds=int(extract_time))} ({extract_time/total_time*100:.1f}%)")
        print(f"   • Ingestion: {timedelta(seconds=int(ingest_time))} ({ingest_time/total_time*100:.1f}%)")
        print(f"\n🎯 NEXT STEPS:")
        print(f"   1. Run queries using: uv run python lightrag_query_demo.py")
        print(f"   2. Test simple queries using: uv run python test_simple.py")
        print(f"   3. Database ready for complex medical table relationship queries")
        print(f"{'='*70}\n")
    
    async def query(self, query_text: str, mode: str = "hybrid"):
        """
        Query the LightRAG database with proper QueryParam usage.
        
        Args:
            query_text: The query string
            mode: Query mode (local, global, hybrid, naive, mix)
            
        Returns:
            Query results
        """
        logger.info(f"Querying LightRAG: '{query_text}' (mode: {mode})")
        
        try:
            query_param = QueryParam(mode=mode)
            result = await self.rag.aquery(query_text, param=query_param)
            return result
        except Exception as e:
            logger.error(f"Query failed: {e}")
            return None


async def main():
    """Main function to run the ingestion pipeline."""
    
    # Initialize converter
    converter = DeepLakeToLightRAG(
        deeplake_path="/media/gyasis/Drive 2/Deeplake_Storage/athena_descriptions_v4",
        lightrag_working_dir="./athena_lightrag_db"
    )
    
    # Run ingestion
    await converter.run_ingestion()
    
    # Test with sample queries
    test_queries = [
        "What tables are related to appointments?",
        "Tell me about anesthesia case tables",
        "What are the main collector category tables?",
        "Describe the allowable schedule category"
    ]
    
    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"Query: {query}")
        print(f"{'='*60}")
        
        result = await converter.query(query, mode="hybrid")
        if result:
            print(result)
        else:
            print("No results found")


if __name__ == "__main__":
    asyncio.run(main())