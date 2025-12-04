# DeepLake Database Structure Documentation (v4 API)

## Database Schema

The DeepLake v4 database uses explicit schema definition with proper types:

```python
{
    "id": deeplake.types.Text(),          # Unique identifier for each document
    "text": deeplake.types.Text(),        # Raw document content
    "embedding": deeplake.types.Embedding(1536), # Vector embeddings (1536-dimensional for text-embedding-3-small)
    "metadata": deeplake.types.Dict()     # Document metadata as dictionary
}
```

### Schema Creation

```python
import deeplake
from deeplake import types

# Create dataset with explicit schema
ds = deeplake.create("path/to/dataset")
ds.add_column("id", types.Text())
ds.add_column("text", types.Text())
ds.add_column("embedding", types.Embedding(1536))
ds.add_column("metadata", types.Dict())
ds.commit("Initial schema creation")
```

## Metadata Structure

The metadata field follows this specific structure:

```python
{
    "title": str,        # Document title
    "summary": str,      # Generated summary in structured format
    "web_address": str   # Source URL of the document
}
```

### Summary Field Structure

The `summary` field contains a structured format with the following sections:

```markdown
**TL;DR:**
[Brief summary of the content]

### Main Facts:
1. Technology Overview: [specific technology/framework details]
2. Usefulness: [benefits and applications]
3. Implementation: [implementation approach]
4. Code Examples: [code demonstration]
5. Best Practices: [optimization tips]

### Abstract:
[Detailed overview of the technology/content]

### Implementation Outline:
1. Setup: [environment setup]
2. Configuration: [configuration details]
3. Development: [development steps]
4. Testing: [testing procedures]
5. Deployment: [deployment guidelines]

### Code Excerpts:
[Relevant code snippets]

### Best Practices:
- Optimization: [performance tips]
- Maintainability: [code maintenance]
- Security: [security practices]

### Additional Resources:
- [Resource links]

Main Article URL: [Source URL]
```

## Database Methods (v4 API)

### 1. Opening/Creating Dataset

```python
import deeplake
from deeplake import types

def create_or_open_dataset(dataset_path: str):
    """Create a new DeepLake dataset or open existing one with proper v4 schema"""
    try:
        # Try to open existing dataset first
        ds = deeplake.open(dataset_path)
        return ds
    except Exception:
        # Create new dataset with schema
        ds = deeplake.create(dataset_path)
        
        # Add columns with proper types
        ds.add_column("id", types.Text())
        ds.add_column("text", types.Text())
        ds.add_column("embedding", types.Embedding(1536))  # text-embedding-3-small
        ds.add_column("metadata", types.Dict())
        
        # Commit the schema
        ds.commit("Initial schema creation")
        return ds
```

### 2. Adding Documents (v4 API)

```python
import uuid

def add_document(ds, text: str, title: str, web_address: str):
    """Add a document with metadata to the dataset using v4 API"""
    # Generate summary
    summary = create_summary(text)
    
    # Create metadata
    metadata = {
        "title": title,
        "summary": summary,
        "web_address": web_address
    }
    
    # Generate embedding
    embedding = generate_embedding(text)
    
    # Add to dataset using v4 batch format
    batch_data = {
        "id": [str(uuid.uuid4())],
        "text": [text],
        "embedding": [embedding.tolist()],  # Convert to list for v4
        "metadata": [metadata]
    }
    
    ds.append(batch_data)
    ds.commit("Added document")
```

### 3. Querying Documents (v4 API)

```python
def search_documents(ds, query: str, n_results: int = 5):
    """Search documents with metadata return using v4 TQL"""
    query_embedding = generate_embedding(query)
    embedding_str = ','.join(str(x) for x in query_embedding)
    
    # Use TQL (Tensor Query Language) for v4
    results = ds.query(f"""
        SELECT *
        ORDER BY COSINE_SIMILARITY(embedding, ARRAY[{embedding_str}]) DESC
        LIMIT {n_results}
    """)
    
    return [{
        'id': r['id'],
        'text': r['text'],
        'metadata': r['metadata'],
        'embedding': r['embedding']
    } for r in results]
```

### 4. Metadata-Based Search (v4 API)

```python
def search_by_metadata(ds, metadata_field: str, value: str):
    """Search documents by metadata field using v4 TQL"""
    results = ds.query(f"""
        SELECT *
        WHERE metadata.{metadata_field} LIKE '%{value}%'
    """)
    return results
```

### 5. Summary Extraction (v4 API)

```python
def get_document_summary(ds, doc_id: str):
    """Extract summary from document metadata using v4 TQL"""
    result = ds.query(f"SELECT metadata WHERE id = '{doc_id}'")
    if len(result) > 0:
        return result.metadata[0]['summary']
    return None
```

### 6. Batch Processing (v4 API)

```python
import uuid
from typing import List, Dict

def batch_add_documents(ds, documents: List[Dict]):
    """Add multiple documents with metadata in batch using v4 API"""
    batch_data = {
        'id': [],
        'text': [],
        'embedding': [],
        'metadata': []
    }
    
    for doc in documents:
        summary = create_summary(doc['text'])
        metadata = {
            'title': doc['title'],
            'summary': summary,
            'web_address': doc['web_address']
        }
        
        batch_data['id'].append(str(uuid.uuid4()))
        batch_data['text'].append(doc['text'])
        batch_data['embedding'].append(generate_embedding(doc['text']).tolist())  # Convert to list for v4
        batch_data['metadata'].append(metadata)
    
    # Use v4 batch append
    ds.append(batch_data)
    ds.commit("Added batch of documents")
```

## Usage Example (v4 API)

```python
# Initialize dataset with v4 API
ds = create_or_open_dataset("path/to/dataset")

# Add a document
doc = {
    'text': "Document content...",
    'title': "Document Title",
    'web_address': "https://example.com"
}
add_document(ds, **doc)

# Search documents
results = search_documents(ds, "search query")
for result in results:
    print(f"ID: {result['id']}")
    print(f"Title: {result['metadata']['title']}")
    print(f"Summary: {result['metadata']['summary']}")
    print(f"Source: {result['metadata']['web_address']}")
    print(f"Text: {result['text'][:100]}...")  # First 100 chars
```

## Key Changes in v4 API

1. **Explicit Schema**: Must define schema with `deeplake.types`
2. **Batch Format**: Use dictionary with lists for batch operations
3. **Embedding Format**: Convert embeddings to lists with `.tolist()`
4. **TQL Queries**: Use Tensor Query Language for searching
5. **Commit Operations**: Explicit commits for data persistence
6. **Latest Embeddings**: Upgraded to `text-embedding-3-small` (62.3% MTEB performance vs 61.0% for ada-002)

## Dataset Validation (v4 API)

The ingestor includes comprehensive validation to ensure dataset integrity:

```python
def validate_dataset(dataset_path):
    """Validate dataset structure and retrieve sample data"""
    ds = deeplake.open(dataset_path)
    
    # 1. Dataset summary
    ds.summary()
    
    # 2. Check schema structure
    for column_name in ds.columns:
        print(f"{column_name}: {ds[column_name].dtype}")
    
    # 3. Retrieve first 5 rows
    for i in range(min(5, len(ds))):
        print(f"Record {i+1}: {ds['id'][i].numpy()}")
    
    # 4. Test vector similarity search
    test_embedding = ds['embedding'][0].numpy()
    results = ds.query(f"""
        SELECT *
        ORDER BY COSINE_SIMILARITY(embedding, ARRAY[{embedding_str}]) DESC
        LIMIT 3
    """)
    
    return True
```

## Progress Tracking

The ingestor includes comprehensive progress tracking:

- **File-level progress**: Shows which JSONL file is being processed
- **Record-level progress**: Tracks individual record processing with tqdm
- **Batch progress**: Shows batch completion status
- **Validation progress**: Displays validation steps and results

This documentation provides the specific structure and methods for working with the DeepLake v4 database, with particular attention to the metadata and summary structure that makes this implementation unique. 