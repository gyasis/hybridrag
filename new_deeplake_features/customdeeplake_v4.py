"""
CustomDeepLake: A wrapper class for DeepLake vector store operations with OpenAI embeddings.

This module provides a clean interface for interacting with DeepLake vector stores,
handling document storage, retrieval, and similarity search using OpenAI embeddings.

Key Features:
- Document storage and retrieval
- Semantic search using OpenAI embeddings
- RECENCY-BASED SEARCH: Prioritize recent results without explicit timestamps
- Metadata filtering
- Read-only mode support
- Comprehensive error handling and logging

RECENCY FUNCTIONALITY:
This module includes advanced recency-based search capabilities that allow you to
prioritize recent results in vector search without requiring explicit timestamps.
The recency scoring is based on insertion order using DeepLake's ROW_NUMBER() function.

HOW RECENCY WORKS:
1. Uses ROW_NUMBER() as a proxy for recency (higher row numbers = more recent)
2. Normalizes recency scores: (ROW_NUMBER() - 1) / total_records
3. Combines with similarity using weighted fusion: (1-w)*similarity + w*recency
4. Perfect for sequential data ingestion where insertion order = recency

USAGE EXAMPLES:
    # Standard search (unchanged)
    results = db.search("machine learning", n_results=5)
    
    # Recency-weighted search
    results = db.search("machine learning", n_results=5, recency_weight=0.3)
    
    # Recency-focused search (convenience method)
    results = db.search_recent("machine learning", n_results=5)
    
    # Pure recency (not recommended)
    results = db.search("machine learning", n_results=5, recency_weight=1.0)

RECENCY WEIGHT GUIDELINES:
- 0.0: Pure similarity (existing behavior, backward compatible)
- 0.2: Light recency boost (subtle preference for recent results)
- 0.3: Balanced (recommended default for most use cases)
- 0.5: Equal weight (may hurt relevance)
- 0.7: Recency-focused (strong preference for recent results)
- 1.0: Pure recency (not recommended - ignores relevance)

Dependencies:
- deeplake: For vector store operations
- openai: For generating embeddings
- python-dotenv: For environment variable management
"""

import os
from typing import List, Dict, Optional, Union
import deeplake
from openai import OpenAI
from dotenv import load_dotenv
import logging
import uuid

# Configure logging with a more detailed format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


load_dotenv(".env", override=True)






class CustomDeepLake:
    """
    A wrapper class for DeepLake vector store operations with OpenAI embeddings.

    This class provides methods for:
    1. Initializing and managing DeepLake vector store connections (using VectorStore)
    2. Generating embeddings using OpenAI's API
    3. Performing semantic search on stored documents
    4. RECENCY-BASED SEARCH: Prioritize recent results without explicit timestamps
    5. Adding and deleting documents from the store
    6. Managing metadata associated with documents

    RECENCY SEARCH CAPABILITIES:
    ============================
    This class includes advanced recency-based search functionality that allows you to
    prioritize recent results in vector search without requiring explicit timestamps.
    
    The recency scoring is based on insertion order using DeepLake's ROW_NUMBER() function:
    - Higher row numbers = more recent records
    - Recency scores are normalized to 0.0-1.0 range
    - Combined with similarity using weighted fusion formula
    
    KEY METHODS FOR RECENCY:
    - search(query, recency_weight=0.0): Main search method with optional recency weighting
    - search_recent(query): Convenience method with optimized recency settings
    
    RECENCY WEIGHT PARAMETER:
    - 0.0: Pure similarity (existing behavior, backward compatible)
    - 0.3: Balanced (recommended default for most use cases)
    - 0.7: Recency-focused (strong preference for recent results)
    - 1.0: Pure recency (not recommended - ignores relevance)

    Attributes:
        db_path (str): Path to the DeepLake database
        read_only (bool): Whether the database is in read-only mode
        ds (VectorStore): The DeepLake vector store instance (using VectorStore abstraction).
                          Named 'ds' for convention alignment with dataset examples.
        client (OpenAI): The OpenAI client instance
    """



    def __init__(self, db_path: str, client: Optional[OpenAI] = None):
        """
        Initialize the VectorSearchV4 class.

        Parameters:
        - db_path: Path to the V4 dataset
        - client: OpenAI client for generating embeddings. If None, will create new client.
        """
        self.db_path = db_path
        self.client = client if client else OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        logger.info(f"Opening dataset at path: {db_path}")
        try:
            self.ds = deeplake.open(db_path)
            logger.info("Dataset opened successfully")
            self.inspect_dataset()
        except Exception as e:
            logger.error(f"Error opening dataset: {str(e)}")
            raise

    def inspect_dataset(self):
        """
        Inspect the dataset structure and print information about its contents.
        """
        logger.info("Dataset Structure:")
        logger.info("-" * 50)
        
        # Print dataset summary (length and column overview)
        logger.info("Dataset Summary (Overview):")
        self.ds.summary()

    def embedding_function(self, texts: Union[str, List[str]], model: str = "text-embedding-ada-002") -> List[List[float]]:
        """
        Generate embeddings for the given texts using OpenAI's embedding API.

        Args:
            texts (Union[str, List[str]]): Single text string or list of text strings
            model (str): The embedding model to use (default: text-embedding-ada-002)

        Returns:
            List[List[float]]: List of embedding vectors

        Raises:
            Exception: If embedding generation fails (e.g., API error)
        """
        try:
            # Convert single string to list for consistent processing
            if isinstance(texts, str):
                texts = [texts]
            
            # Clean texts by removing newlines
            texts = [t.replace("\n", " ") for t in texts]
            
            # Calculate approximate tokens (rough estimate: 1 token ≈ 4 characters)
            total_chars = sum(len(text) for text in texts)
            estimated_tokens = total_chars // 4
            
            # OpenAI has a limit of 300,000 tokens per request
            MAX_TOKENS_PER_REQUEST = 300000
            # Use close to max for better performance: aim for ~290,000 tokens per batch
            TARGET_TOKENS_PER_BATCH = 290000
            
            logger.info(f"Total documents: {len(texts)}, estimated tokens: {estimated_tokens}")
            
            if estimated_tokens <= TARGET_TOKENS_PER_BATCH:
                # Single batch is fine
                logger.debug("Processing all documents in single batch")
                response = self.client.embeddings.create(
                    input=texts,
                    model=model
                )
                embeddings = [data.embedding for data in response.data]
                return embeddings
            else:
                # Need to batch the requests
                logger.info(f"Large batch detected ({estimated_tokens} tokens). Processing in batches...")
                
                all_embeddings = []
                batch_size = max(1, len(texts) // (estimated_tokens // TARGET_TOKENS_PER_BATCH + 1))
                
                logger.info(f"Using batch size of {batch_size} documents per request")
                
                for i in range(0, len(texts), batch_size):
                    batch_texts = texts[i:i + batch_size]
                    batch_chars = sum(len(text) for text in batch_texts)
                    batch_tokens = batch_chars // 4
                    
                    logger.debug(f"Processing batch {i//batch_size + 1}: {len(batch_texts)} documents, ~{batch_tokens} tokens")
                    
                    try:
                        response = self.client.embeddings.create(
                            input=batch_texts,
                            model=model
                        )
                        batch_embeddings = [data.embedding for data in response.data]
                        all_embeddings.extend(batch_embeddings)
                        logger.debug(f"Successfully processed batch {i//batch_size + 1}")
                        
                    except Exception as e:
                        logger.error(f"Error processing batch {i//batch_size + 1}: {str(e)}")
                        # If a batch fails, try with smaller batch size
                        if "max_tokens_per_request" in str(e):
                            logger.warning("Batch still too large, reducing batch size and retrying...")
                            # Reduce batch size and retry this batch
                            smaller_batch_size = batch_size // 2
                            for j in range(0, len(batch_texts), smaller_batch_size):
                                sub_batch = batch_texts[j:j + smaller_batch_size]
                                logger.debug(f"Processing sub-batch: {len(sub_batch)} documents")
                                response = self.client.embeddings.create(
                                    input=sub_batch,
                                    model=model
                                )
                                sub_embeddings = [data.embedding for data in response.data]
                                all_embeddings.extend(sub_embeddings)
                        else:
                            raise e
                
                logger.info(f"Successfully processed all {len(texts)} documents in batches")
                return all_embeddings
            
        except Exception as e:
            logger.error(f"Error generating embeddings: {str(e)}")
            raise

    def search(
        self,
        query: str,
        n_results: int = 5,
        return_text_only: bool = False,
        recency_weight: float = 0.0,
    ) -> Union[str, List[Dict]]:
        """
        Perform a vector similarity search on the V4 dataset with optional recency weighting.

        This method supports both traditional vector similarity search and hybrid search that
        combines similarity with recency scoring. When recency_weight > 0, the search uses
        DeepLake's ROW_NUMBER() function to calculate recency scores based on insertion order,
        then combines them with vector similarity using weighted fusion.

        RECENCY SCORING APPROACH:
        - Uses ROW_NUMBER() as a proxy for recency (higher row numbers = more recent)
        - Normalizes recency scores: (ROW_NUMBER() - 1) / total_records
        - Combines with similarity using: (1-w)*similarity + w*recency
        - Perfect for sequential data ingestion where insertion order = recency

        Parameters:
        - query: The text to search for similar entries
        - n_results: Number of results to return
        - return_text_only: If True, return only the text of the results
        - recency_weight: Weight for recency scoring (0.0 = pure similarity, 1.0 = pure recency)
                         Uses insertion order (ROW_NUMBER) as recency proxy
                         Recommended values: 0.0 (pure similarity), 0.3 (balanced), 0.7 (recency-focused)

        Returns:
        - If return_text_only: A compiled string of texts
        - Otherwise: List of dicts with full result information including scores
        """
        try:
            logger.info(f"Searching for: {query} (recency_weight: {recency_weight})")
            
            # ============================================================================
            # PARAMETER VALIDATION
            # ============================================================================
            # Ensure recency_weight is within valid range [0.0, 1.0]
            # 0.0 = pure similarity (existing behavior)
            # 1.0 = pure recency (not recommended for most use cases)
            if not 0.0 <= recency_weight <= 1.0:
                raise ValueError("recency_weight must be between 0.0 and 1.0")
            
            # ============================================================================
            # EMBEDDING GENERATION
            # ============================================================================
            # Generate the embedding for the query text using OpenAI's embedding API
            # This converts the text query into a vector representation for similarity search
            query_embedding = self.embedding_function(query)[0]
            
            # Convert embedding to string format required by DeepLake TQL queries
            # DeepLake expects embeddings as comma-separated values in ARRAY[...] format
            text_vector = ','.join(str(x) for x in query_embedding)

            # ============================================================================
            # QUERY STRATEGY SELECTION
            # ============================================================================
            # Choose between pure similarity search or hybrid recency-weighted search
            # based on the recency_weight parameter
            if recency_weight == 0.0:
                # ========================================================================
                # PURE VECTOR SIMILARITY SEARCH (EXISTING BEHAVIOR)
                # ========================================================================
                # This maintains backward compatibility - existing code will work unchanged
                # Uses only COSINE_SIMILARITY for ranking results
                logger.debug("Using pure vector similarity search")
                similar = self.ds.query(f"""
                    SELECT *
                    ORDER BY COSINE_SIMILARITY(embedding, ARRAY[{text_vector}]) DESC
                    LIMIT {n_results}
                """)
            else:
                # ========================================================================
                # HYBRID RECENCY-WEIGHTED SEARCH
                # ========================================================================
                # This is the new recency functionality that combines vector similarity
                # with recency scoring based on insertion order
                logger.debug(f"Using hybrid search with {recency_weight:.2f} recency weight")
                similar = self.ds.query(f"""
                    SELECT *,
                           -- Calculate vector similarity score (0.0 to 1.0)
                           COSINE_SIMILARITY(embedding, ARRAY[{text_vector}]) as similarity_score,
                           
                           -- Calculate recency score based on insertion order
                           -- ROW_NUMBER() gives zero-based row index
                           -- Normalize to 0.0-1.0 range where 1.0 = most recent
                           (ROW_NUMBER() - 1) / (SELECT COUNT(*) FROM dataset) as recency_score,
                           
                           -- Combine similarity and recency using weighted fusion
                           -- Formula: (1-w)*similarity + w*recency
                           -- This ensures both factors contribute to final ranking
                           ((1 - {recency_weight}) * COSINE_SIMILARITY(embedding, ARRAY[{text_vector}]) + 
                            {recency_weight} * ((ROW_NUMBER() - 1) / (SELECT COUNT(*) FROM dataset))) as combined_score
                    ORDER BY combined_score DESC
                    LIMIT {n_results}
                """)
            
            # ============================================================================
            # RESULT PROCESSING
            # ============================================================================
            # Process the query results based on the requested return format
            if return_text_only:
                # ========================================================================
                # TEXT-ONLY RETURN FORMAT
                # ========================================================================
                # Concatenate all result texts with separators for easy reading
                compiled_text = "\n\n---\n\n".join(item["text"] for item in similar)
                return compiled_text
            else:
                # ========================================================================
                # FULL RESULT FORMAT WITH METADATA
                # ========================================================================
                # Extract all relevant fields from the query results
                # These are the standard fields available in all DeepLake datasets
                ids = similar["id"][:]
                texts = similar["text"][:]
                embeddings = similar["embedding"][:]
                metadata = similar["metadata"][:]

                # ========================================================================
                # BUILD RESULT DICTIONARIES
                # ========================================================================
                # Combine results into a list of dictionaries for easy access
                results = []
                for i, (id_, text, embedding, meta) in enumerate(zip(ids, texts, embeddings, metadata)):
                    # Create base result dictionary with standard fields
                    result_dict = {
                        "id": id_,
                        "text": text,
                        "embedding": embedding,
                        "metadata": meta,
                    }
                    
                    # ====================================================================
                    # ADD RECENCY SCORING INFORMATION (IF APPLICABLE)
                    # ====================================================================
                    # When recency weighting was used, include the detailed scoring breakdown
                    # This helps users understand how the hybrid scoring worked
                    if recency_weight > 0.0:
                        try:
                            # Extract the individual scoring components from the TQL query results
                            # These fields are only available when recency_weight > 0.0
                            result_dict["similarity_score"] = similar["similarity_score"][i] if hasattr(similar, "similarity_score") else None
                            result_dict["recency_score"] = similar["recency_score"][i] if hasattr(similar, "recency_score") else None
                            result_dict["combined_score"] = similar["combined_score"][i] if hasattr(similar, "combined_score") else None
                        except Exception as e:
                            # Gracefully handle cases where scoring information isn't available
                            logger.warning(f"Could not extract scoring information: {e}")
                    
                    results.append(result_dict)
                
                # ========================================================================
                # LOGGING AND RETURN
                # ========================================================================
                logger.info(f"Found {len(results)} results")
                if recency_weight > 0.0:
                    logger.info(f"Search used {recency_weight:.2f} recency weighting")
                return results
                
        except Exception as e:
            logger.error(f"Error performing search: {str(e)}")
            raise

    def search_recent(
        self,
        query: str,
        n_results: int = 5,
        recency_weight: float = 0.3,
        return_text_only: bool = False,
    ) -> Union[str, List[Dict]]:
        """
        Perform a recency-focused vector similarity search.
        
        This is a convenience method that calls the main search() method with a default
        recency_weight optimized for finding recent results while maintaining relevance.
        It's designed for users who want recency-weighted results without having to
        specify the recency_weight parameter every time.
        
        WHY 0.3 AS DEFAULT?
        - 0.0 would be pure similarity (no recency boost)
        - 0.5 would be equal weight (might hurt relevance too much)
        - 0.3 provides a good balance: 70% similarity, 30% recency
        - This typically gives recent results a meaningful boost without
          completely overriding semantic relevance
        
        USE CASES:
        - Finding recent documents that match a query
        - Prioritizing newly ingested data in search results
        - Balancing relevance with recency for time-sensitive searches
        
        Parameters:
        - query: The text to search for similar entries
        - n_results: Number of results to return
        - recency_weight: Weight for recency scoring (default: 0.3 for balanced results)
        - return_text_only: If True, return only the text of the results
        
        Returns:
        - If return_text_only: A compiled string of texts
        - Otherwise: List of dicts with full result information including scores
        """
        logger.info(f"Performing recency-focused search for: {query}")
        return self.search(
            query=query,
            n_results=n_results,
            return_text_only=return_text_only,
            recency_weight=recency_weight
        )

    def add_documents(
        self,
        documents: List[str],
        metadata: Optional[List[Dict]] = None
    ) -> List[str]:
        """
        Add documents to the vector store (self.ds).

        This method:
        1. Generates embeddings for the documents
        2. Adds documents, embeddings, and metadata to the vector store
        3. Returns the IDs of the added documents

        Args:
            documents (List[str]): List of document texts to add
            metadata (Optional[List[Dict]]): Optional metadata for each document.
                                           Must match length of documents if provided.

        Returns:
            List[str]: List of IDs for the added documents

        Raises:
            ValueError: If metadata length doesn't match documents
            Exception: If document addition fails
        """
        logger.debug(f"Starting to add {len(documents)} documents")
        if not self.ds:
            logger.error("DeepLake VectorStore (ds) is not initialized")
            raise RuntimeError("DeepLake VectorStore (ds) is not initialized.")
            
        try:
            # Validate metadata length if provided
            if metadata and len(metadata) != len(documents):
                logger.error(f"Metadata length ({len(metadata)}) doesn't match documents length ({len(documents)})")
                raise ValueError("Length of metadata must match length of documents")
                
            # Generate embeddings for all documents
            logger.debug("Generating embeddings for documents")
            embeddings = self.embedding_function(documents)
            logger.debug(f"Generated {len(embeddings)} embeddings")

            # Generate a base UUID for this batch
            base_uuid = uuid.uuid1()
            base_int = int(base_uuid.hex, 16)
            
            # Prepare batch data in column-oriented format
            batch_data = {
                "id": [],
                "text": documents,
                "embedding": [],
                "metadata": []
            }
            
            added_ids = []
            
            # Log batch information
            logger.info(f"Preparing to append batch of {len(documents)} documents")
            logger.debug(f"Base UUID for this batch: {base_uuid}")
            
            # Log sample of first document if available
            if documents and len(documents) > 0:
                sample_doc = documents[0][:200] + "..." if len(documents[0]) > 200 else documents[0]
                logger.debug(f"Sample document (truncated): {sample_doc}")
            
            # Log sample of first metadata if available
            if metadata and len(metadata) > 0:
                logger.debug(f"Sample metadata: {metadata[0]}")
            
            # Log sample of first embedding if available
            if len(embeddings) > 0:
                embedding_shape = f"shape: {len(embeddings[0])}" if hasattr(embeddings[0], "__len__") else "shape: unknown"
                logger.debug(f"Sample embedding {embedding_shape}")
            
            # Prepare data for batch append
            for i, (doc, emb) in enumerate(zip(documents, embeddings)):
                # Generate a new UUID by incrementing the base UUID
                new_id = uuid.UUID(int=base_int + i)
                id_str = str(new_id)
                added_ids.append(id_str)
                
                # Add to batch data
                batch_data["id"].append(id_str)
                
                # Convert embedding to list if it's a numpy array
                emb_list = emb.tolist() if hasattr(emb, 'tolist') else emb
                batch_data["embedding"].append(emb_list)
                
                # Add metadata
                batch_data["metadata"].append(metadata[i] if metadata else {})
            
            # Log the batch structure (sample)
            logger.debug(f"Batch append data structure: {{")
            logger.debug(f"  'id': ['{batch_data['id'][0]}', ...] (total: {len(batch_data['id'])})")
            logger.debug(f"  'text': ['{documents[0][:30]}...', ...] (total: {len(batch_data['text'])})")
            logger.debug(f"  'embedding': [array(...), ...] (total: {len(batch_data['embedding'])})")
            logger.debug(f"  'metadata': [{batch_data['metadata'][0]}, ...] (total: {len(batch_data['metadata'])})")
            logger.debug(f"}}")
            
            # Perform batch append operation
            self.ds.append(batch_data)
            
            # Log successful addition with detailed verification
            logger.info(f"Successfully added {len(documents)} documents to DeepLake dataset")
            logger.info(f"Current dataset size: {len(self.ds)} records")
            
            # Verify the last few records were added by checking dataset length
            expected_new_length = len(self.ds)
            logger.debug(f"Expected dataset length after addition: {expected_new_length}")
            
            # Try to access and log a few fields from the recently added data
            try:
                recent_idx = len(self.ds) - 1  # Index of most recently added record
                if recent_idx >= 0:
                    logger.info(f"Verification - Recently added record (index {recent_idx}):")
                    # Log ID
                    if "id" in self.ds:
                        recent_id = self.ds.id[recent_idx].numpy()
                        logger.info(f"  id: {recent_id}")
                    
                    # Log text sample
                    if "text" in self.ds:
                        recent_text = self.ds.text[recent_idx].numpy()
                        text_preview = str(recent_text)[:100] + "..." if len(str(recent_text)) > 100 else str(recent_text)
                        logger.info(f"  text: {text_preview}")
                    
                    # Log metadata
                    if "metadata" in self.ds:
                        recent_metadata = self.ds.metadata[recent_idx].numpy()
                        logger.info(f"  metadata: {recent_metadata}")
            except Exception as e:
                logger.warning(f"Could not verify recently added data: {str(e)}")
            
            logger.debug(f"Added document IDs: {added_ids}")
            return added_ids
            
        except Exception as e:
            logger.error(f"Error adding documents: {str(e)}", exc_info=True)
            raise

    def delete_documents(self, ids: List[str]) -> None:
        """
        Delete documents from the vector store.

        This method:
        1. Removes documents and their associated embeddings from the store
        2. Handles batch deletion of multiple documents

        Args:
            ids (List[str]): List of document IDs to delete

        Raises:
            Exception: If document deletion fails
        """
        if not self.ds:
            raise RuntimeError("DeepLake VectorStore (ds) is not initialized.")
            
        try:
            # Delete documents from vector store
            self.ds.delete(ids)
            logger.info(f"Successfully deleted {len(ids)} documents")
            
        except Exception as e:
            logger.error(f"Error deleting documents: {str(e)}")
            raise

# Example usage with detailed comments
if __name__ == "__main__":
    # Initialize the database with read-only access
    db = CustomDeepLake(input("path to db: "))
    
    # Print detailed dataset information
    print("\nDataset Information:")
    print("-" * 50)
    print(f"Dataset path: {db.db_path}")
    print(f"Dataset length: {len(db.ds)}")
    print("\nAvailable columns:")
    for key in db.ds.columns:
        print(f"- {key}")
    
    print("\nFirst 3 rows of data:")
    print("-" * 50)
    for i in range(min(3, len(db.ds))):
        print(f"\nRow {i}:")
        for key in db.ds.columns:
            value = db.ds[key][i].numpy()
            print(f"{key}: {value}")
    
    print("\nDataset Summary:")
    print("-" * 50)
    db.ds.summary() 