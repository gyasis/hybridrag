#!/usr/bin/env python3
"""
Ingestion Pipeline Module
=========================
Processes queued files and ingests them into LightRAG.
"""

import os
import json
import logging
import asyncio
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime
import traceback
from concurrent.futures import ThreadPoolExecutor

# Progress bar
from tqdm import tqdm
import re
import sys

# Document processing imports
import tiktoken
import pypdf
from bs4 import BeautifulSoup
import csv
import yaml

logger = logging.getLogger(__name__)


class TqdmLoggingHandler(logging.Handler):
    """
    Custom logging handler that intercepts LightRAG chunk progress messages
    and updates a tqdm progress bar instead of printing to console.
    """

    # Pattern to match: "Chunk 284 of 1477 extracted 7 Ent + 6 Rel chunk-xxx"
    CHUNK_PATTERN = re.compile(r'Chunk (\d+) of (\d+) extracted (\d+) Ent \+ (\d+) Rel')

    def __init__(self, chunk_pbar: tqdm = None):
        super().__init__()
        self.chunk_pbar = chunk_pbar
        self.total_chunks = 0
        self.current_chunk = 0
        self.total_entities = 0
        self.total_relations = 0

    def set_pbar(self, pbar: tqdm):
        """Set or update the progress bar reference."""
        self.chunk_pbar = pbar

    def reset_stats(self):
        """Reset statistics for a new file."""
        self.total_chunks = 0
        self.current_chunk = 0
        self.total_entities = 0
        self.total_relations = 0

    def emit(self, record):
        try:
            msg = self.format(record)

            # Check if this is a chunk progress message
            match = self.CHUNK_PATTERN.search(msg)
            if match:
                current = int(match.group(1))
                total = int(match.group(2))
                entities = int(match.group(3))
                relations = int(match.group(4))

                # Update totals
                self.total_entities += entities
                self.total_relations += relations

                # Update progress bar if available
                if self.chunk_pbar is not None:
                    # Set total on first chunk
                    if self.chunk_pbar.total != total:
                        self.chunk_pbar.total = total
                        self.chunk_pbar.refresh()

                    # Update progress
                    delta = current - self.current_chunk
                    if delta > 0:
                        self.chunk_pbar.update(delta)

                    # Update postfix with entity/relation counts
                    self.chunk_pbar.set_postfix_str(
                        f"Ent:{self.total_entities} Rel:{self.total_relations}"
                    )

                self.current_chunk = current
                self.total_chunks = total

            # Also check for cache/LLM messages to show activity
            elif 'LLM cache' in msg or 'extracted' in msg.lower():
                if self.chunk_pbar is not None:
                    # Just update the display to show activity
                    self.chunk_pbar.refresh()

        except Exception:
            self.handleError(record)


class DocumentProcessor:
    """Process various document types into text chunks."""
    
    def __init__(self, config):
        """Initialize document processor."""
        self.config = config
        self.chunk_size = config.lightrag.chunk_size
        self.chunk_overlap = config.lightrag.chunk_overlap
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
        
    def read_file(self, file_path: str, extension: str) -> str:
        """Read file content based on extension."""
        file_path = Path(file_path)
        
        try:
            if extension in ['.txt', '.md']:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read()
                    
            elif extension == '.pdf':
                return self._read_pdf(file_path)
                
            elif extension == '.html':
                with open(file_path, 'r', encoding='utf-8') as f:
                    soup = BeautifulSoup(f.read(), 'html.parser')
                    return soup.get_text(separator='\n')
                    
            elif extension == '.json':
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return json.dumps(data, indent=2)
                    
            elif extension in ['.yaml', '.yml']:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    return yaml.dump(data, default_flow_style=False)
                    
            elif extension == '.csv':
                return self._read_csv(file_path)
                
            elif extension in ['.py', '.js', '.java', '.cpp', '.c', '.go', '.rs']:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # Add file path as context for code files
                    return f"# File: {file_path}\n\n{content}"
                    
            else:
                # Try to read as text
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()
                    
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            raise
    
    def _read_pdf(self, file_path: Path) -> str:
        """Extract text from PDF file."""
        text_parts = []
        try:
            with open(file_path, 'rb') as f:
                pdf_reader = pypdf.PdfReader(f)
                for page_num, page in enumerate(pdf_reader.pages):
                    text = page.extract_text()
                    if text:
                        text_parts.append(f"[Page {page_num + 1}]\n{text}")
        except Exception as e:
            logger.error(f"Error reading PDF {file_path}: {e}")
            raise
        return '\n\n'.join(text_parts)
    
    def _read_csv(self, file_path: Path) -> str:
        """Convert CSV to readable text format."""
        text_parts = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                csv_reader = csv.DictReader(f)
                for row_num, row in enumerate(csv_reader):
                    if row_num == 0:
                        text_parts.append(f"Columns: {', '.join(row.keys())}\n")
                    row_text = ' | '.join(f"{k}: {v}" for k, v in row.items())
                    text_parts.append(f"Row {row_num + 1}: {row_text}")
        except Exception as e:
            logger.error(f"Error reading CSV {file_path}: {e}")
            raise
        return '\n'.join(text_parts)
    
    def chunk_text(self, text: str, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Chunk text into smaller pieces with metadata.
        
        Args:
            text: Text to chunk
            metadata: Metadata to attach to each chunk
            
        Returns:
            List of chunks with metadata
        """
        if not text:
            return []
            
        # Calculate token count
        tokens = self.tokenizer.encode(text)
        
        # If text is small enough, return as single chunk
        if len(tokens) <= self.chunk_size:
            return [{
                "content": text,
                "metadata": {
                    **metadata,
                    "chunk_index": 0,
                    "total_chunks": 1,
                    "token_count": len(tokens)
                }
            }]
        
        # Split into sentences for better chunking
        sentences = text.split('. ')
        
        chunks = []
        current_chunk = []
        current_tokens = 0
        chunk_index = 0
        
        for sentence in sentences:
            sentence_tokens = len(self.tokenizer.encode(sentence))
            
            # If adding this sentence would exceed chunk size
            if current_tokens + sentence_tokens > self.chunk_size and current_chunk:
                # Save current chunk
                chunk_text = '. '.join(current_chunk) + '.'
                chunks.append({
                    "content": chunk_text,
                    "metadata": {
                        **metadata,
                        "chunk_index": chunk_index,
                        "token_count": current_tokens
                    }
                })
                
                # Start new chunk with overlap
                if self.chunk_overlap > 0 and len(current_chunk) > 1:
                    # Keep last few sentences for overlap
                    overlap_sentences = current_chunk[-(self.chunk_overlap // 50):]
                    current_chunk = overlap_sentences + [sentence]
                    current_tokens = sum(len(self.tokenizer.encode(s)) for s in current_chunk)
                else:
                    current_chunk = [sentence]
                    current_tokens = sentence_tokens
                    
                chunk_index += 1
            else:
                current_chunk.append(sentence)
                current_tokens += sentence_tokens
        
        # Add final chunk
        if current_chunk:
            chunk_text = '. '.join(current_chunk)
            if not chunk_text.endswith('.'):
                chunk_text += '.'
            chunks.append({
                "content": chunk_text,
                "metadata": {
                    **metadata,
                    "chunk_index": chunk_index,
                    "token_count": current_tokens
                }
            })
        
        # Update total chunks count
        for chunk in chunks:
            chunk["metadata"]["total_chunks"] = len(chunks)
            
        return chunks

class IngestionPipeline:
    """Manages the ingestion of documents into LightRAG."""
    
    def __init__(self, config, lightrag_instance):
        """
        Initialize ingestion pipeline.
        
        Args:
            config: HybridRAGConfig instance
            lightrag_instance: Initialized LightRAG instance
        """
        self.config = config
        self.lightrag = lightrag_instance
        self.processor = DocumentProcessor(config)
        self.queue_dir = Path(config.ingestion.ingestion_queue_dir)
        self.executor = ThreadPoolExecutor(max_workers=config.system.max_concurrent_ingestions)
        self._stop_event = asyncio.Event()
        
        logger.info("IngestionPipeline initialized")
    
    def get_queued_files(self) -> List[Dict[str, Any]]:
        """Get list of files queued for ingestion."""
        queue_files = []
        
        for queue_file in self.queue_dir.glob("*.json"):
            try:
                with open(queue_file, 'r') as f:
                    metadata = json.load(f)
                    metadata['queue_file'] = str(queue_file)
                    queue_files.append(metadata)
            except Exception as e:
                logger.error(f"Error reading queue file {queue_file}: {e}")
                
        # Sort by queue time
        queue_files.sort(key=lambda x: x.get('queued_at', ''))
        return queue_files
    
    async def process_queued_file(self, queue_metadata: Dict[str, Any]) -> bool:
        """
        Process a single queued file.
        
        Args:
            queue_metadata: Metadata about the queued file
            
        Returns:
            True if successful, False otherwise
        """
        queue_file = Path(queue_metadata['queue_file'])
        queued_file = Path(queue_metadata['queued_file'])
        original_path = queue_metadata['original_path']
        
        try:
            logger.info(f"Processing file: {original_path}")
            
            # Read and process the file
            content = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                self.processor.read_file,
                str(queued_file),
                queue_metadata['extension']
            )
            
            if not content:
                logger.warning(f"Empty content from file: {original_path}")
                return False
            
            # Create metadata for the document
            doc_metadata = {
                "source": original_path,
                "file_type": queue_metadata['extension'],
                "ingested_at": datetime.now().isoformat(),
                "file_size": queue_metadata['size'],
                "file_hash": queue_metadata['hash']
            }
            
            # Chunk the content
            chunks = self.processor.chunk_text(content, doc_metadata)
            
            if not chunks:
                logger.warning(f"No chunks generated from file: {original_path}")
                return False
            
            logger.info(f"Generated {len(chunks)} chunks from {original_path}")
            
            # Combine chunks for ingestion (LightRAG will handle its own chunking)
            # But we provide structured content with metadata
            full_content = f"# Document: {original_path}\n"
            full_content += f"# Type: {queue_metadata['extension']}\n"
            full_content += f"# Ingested: {doc_metadata['ingested_at']}\n\n"
            
            for i, chunk in enumerate(chunks):
                if i > 0:
                    full_content += "\n\n---\n\n"
                full_content += chunk['content']
            
            # Ingest into LightRAG with source file path for tracking
            await self.lightrag.ainsert(full_content, file_path=original_path)
            
            logger.info(f"Successfully ingested: {original_path}")
            
            # Clean up queue files
            try:
                queue_file.unlink()
                queued_file.unlink()
            except Exception as e:
                logger.error(f"Error cleaning up queue files: {e}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error processing file {original_path}: {e}")
            logger.error(traceback.format_exc())
            
            # Move to error queue
            error_dir = self.queue_dir / "errors"
            error_dir.mkdir(exist_ok=True)
            
            try:
                error_metadata = {
                    **queue_metadata,
                    "error": str(e),
                    "error_time": datetime.now().isoformat()
                }
                error_file = error_dir / f"error_{queue_file.name}"
                with open(error_file, 'w') as f:
                    json.dump(error_metadata, f, indent=2)
                    
                # Clean up original queue file
                queue_file.unlink()
                
            except Exception as cleanup_error:
                logger.error(f"Error moving file to error queue: {cleanup_error}")
            
            return False
    
    async def process_batch(self, batch_size: int = None) -> int:
        """
        Process a batch of queued files.
        
        Args:
            batch_size: Number of files to process (default from config)
            
        Returns:
            Number of successfully processed files
        """
        batch_size = batch_size or self.config.ingestion.batch_size
        queued_files = self.get_queued_files()[:batch_size]
        
        if not queued_files:
            return 0
        
        logger.info(f"Processing batch of {len(queued_files)} files")
        
        # Process files concurrently
        tasks = [
            self.process_queued_file(queue_metadata)
            for queue_metadata in queued_files
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count successes
        success_count = sum(1 for r in results if r is True)
        
        logger.info(f"Batch processing complete: {success_count}/{len(queued_files)} successful")
        
        return success_count
    
    async def ingestion_loop(self):
        """Main ingestion loop that processes queued files."""
        logger.info("Starting ingestion loop")
        
        while not self._stop_event.is_set():
            try:
                # Process a batch of files
                processed = await self.process_batch()
                
                # If no files were processed, wait longer
                if processed == 0:
                    wait_time = self.config.ingestion.poll_interval * 2
                else:
                    wait_time = 1  # Process quickly if there are more files
                
            except Exception as e:
                logger.error(f"Error in ingestion loop: {e}")
                wait_time = self.config.ingestion.poll_interval
            
            # Wait before next batch
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=wait_time
                )
            except asyncio.TimeoutError:
                pass
    
    async def start(self):
        """Start the ingestion pipeline."""
        logger.info("Starting IngestionPipeline")
        self._stop_event.clear()
        await self.ingestion_loop()

    async def stop(self):
        """Stop the ingestion pipeline."""
        logger.info("Stopping IngestionPipeline")
        self._stop_event.set()
        self.executor.shutdown(wait=True)

    async def run_batch(self) -> Dict:
        """
        Run one-shot batch ingestion: process all queued files once and exit.

        Returns:
            Dict with ingestion results: files_found, files_processed, files_failed, errors
        """
        logger.info("Starting batch ingestion (one-shot mode)")

        results = {
            "files_found": 0,
            "files_processed": 0,
            "files_failed": 0,
            "errors": []
        }

        # Process all queued files
        queued_files = self.get_queued_files()
        results["files_found"] = len(queued_files)

        if not queued_files:
            logger.info("No files queued for ingestion")
            return results

        logger.info(f"Found {len(queued_files)} files to process")

        # Set up nested progress bars with LightRAG log interception
        # Get LightRAG logger and set up our custom handler
        lightrag_logger = logging.getLogger("lightrag")

        # Create our custom handler for chunk progress
        tqdm_handler = TqdmLoggingHandler()
        tqdm_handler.setLevel(logging.INFO)

        # Remove existing handlers temporarily and add ours
        original_handlers = lightrag_logger.handlers.copy()
        lightrag_logger.handlers.clear()
        lightrag_logger.addHandler(tqdm_handler)

        try:
            # Outer progress bar for files (position=0 is bottom in nested mode)
            with tqdm(total=len(queued_files), desc="📁 Files", unit="file",
                      position=0, leave=True, file=sys.stderr,
                      bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]') as file_pbar:

                for queue_metadata in queued_files:
                    original_path = queue_metadata.get('original_path', 'unknown')
                    file_name = Path(original_path).name
                    file_pbar.set_postfix_str(file_name[:40])

                    # Inner progress bar for chunks (position=1 is above files bar)
                    with tqdm(total=100, desc="   📦 Chunks", unit="chunk",
                              position=1, leave=False, file=sys.stderr,
                              bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{rate_fmt}] {postfix}') as chunk_pbar:

                        # Connect chunk progress bar to our handler
                        tqdm_handler.set_pbar(chunk_pbar)
                        tqdm_handler.reset_stats()

                        try:
                            success = await self.process_queued_file(queue_metadata)
                            if success:
                                results["files_processed"] += 1
                                file_pbar.set_postfix_str(f"✓ {file_name[:35]}")
                                logger.info(f"✓ Processed: {original_path}")
                            else:
                                results["files_failed"] += 1
                                results["errors"].append(f"Failed to process: {original_path}")
                                file_pbar.set_postfix_str(f"✗ {file_name[:35]}")
                                logger.warning(f"✗ Failed: {original_path}")
                        except Exception as e:
                            results["files_failed"] += 1
                            error_msg = f"Error processing {original_path}: {str(e)}"
                            results["errors"].append(error_msg)
                            file_pbar.set_postfix_str(f"⚠ {file_name[:35]}")
                            logger.error(error_msg)

                        # Disconnect chunk progress bar
                        tqdm_handler.set_pbar(None)

                    file_pbar.update(1)

        finally:
            # Restore original LightRAG handlers
            lightrag_logger.handlers.clear()
            for handler in original_handlers:
                lightrag_logger.addHandler(handler)

        logger.info(f"Batch complete: {results['files_processed']}/{results['files_found']} processed, {results['files_failed']} failed")
        return results

    def get_stats(self) -> Dict:
        """Get ingestion statistics."""
        queue_files = list(self.queue_dir.glob("*.json"))
        error_files = list((self.queue_dir / "errors").glob("*.json"))

        return {
            "queued_files": len(queue_files),
            "error_files": len(error_files),
            "queue_directory": str(self.queue_dir)
        }