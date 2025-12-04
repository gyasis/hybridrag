# DeepLake v4 Dataset Management - Cliff Notes

## 📚 **Overview**
DeepLake v4 is a specialized dataset format for AI applications, optimized for managing large datasets efficiently. This guide covers all essential operations for dataset management.

---

## 🏗️ **Dataset Creation & Opening**

### **Creating New Datasets**
```python
import deeplake
from deeplake import types

# Basic creation
ds = deeplake.create("path/to/dataset")

# Create with immediate schema
ds = deeplake.create("path/to/dataset")
ds.add_column("id", types.Text())
ds.add_column("text", types.Text())
ds.add_column("embedding", types.Embedding(1536))
ds.add_column("metadata", types.Dict())
ds.commit("Initial schema creation")
```

### **Opening Existing Datasets**
```python
# Read-write access
ds = deeplake.open("path/to/dataset")

# Read-only access (prevents modifications)
ds = deeplake.open_read_only("path/to/dataset")

# With cloud credentials
ds = deeplake.open("s3://bucket/dataset", 
    creds={"aws_access_key_id": "key", "aws_secret_access_key": "secret"})
```

### **Cloud Storage Support**
```python
# Activeloop Cloud
ds = deeplake.create("al://organization_id/dataset_name")

# AWS S3
ds = deeplake.create("s3://mybucket/my_dataset")

# Google Cloud Storage
ds = deeplake.create("gcs://my-bucket/dataset")

# Azure Blob Storage
ds = deeplake.create("azure://container/dataset")

# In-memory (temporary)
ds = deeplake.create("mem://in-memory")
```

---

## 📊 **Column Types & Schema Management**

### **Available Column Types**

#### **Text Types**
```python
# Basic text
ds.add_column("name", types.Text())

# Text with BM25 indexing (for search optimization)
ds.add_column("content", types.Text(index_type=types.BM25))
```

#### **Numeric Types**
```python
# Integers
ds.add_column("age", types.Int32())
ds.add_column("count", types.Int64())

# Floating point
ds.add_column("score", "float32")
ds.add_column("confidence", "float64")
```

#### **Embedding Types**
```python
# Vector embeddings (specify dimension)
ds.add_column("embedding", types.Embedding(768))  # 768-dimensional
ds.add_column("embedding", types.Embedding(1536)) # 1536-dimensional (text-embedding-3-small)
```

#### **Image Types**
```python
# Basic image
ds.add_column("images", types.Image())

# Image with specific settings
ds.add_column("photos", types.Image(
    dtype=types.UInt8(), 
    sample_compression="jpeg"
))
```

#### **Complex Types**
```python
# Dictionary/JSON data
ds.add_column("metadata", types.Dict())

# Class labels
ds.add_column("labels", types.ClassLabel("int32"))

# Arrays
ds.add_column("tags", types.Array())
```

#### **Complete Schema Example**
```python
# Create dataset with comprehensive schema
ds = deeplake.create("comprehensive_dataset")

# Add all column types
ds.add_column("id", types.Text())
ds.add_column("name", types.Text())
ds.add_column("age", types.Int32())
ds.add_column("score", "float32")
ds.add_column("embedding", types.Embedding(1536))
ds.add_column("image", types.Image())
ds.add_column("metadata", types.Dict())
ds.add_column("labels", types.ClassLabel("int32"))

# Set metadata for labels
ds["labels"].metadata["class_names"] = ["cat", "dog", "bird"]

ds.commit("Complete schema creation")
```

---

## 📝 **Data Operations**

### **Adding Data (Appending)**
```python
# Single record
ds.append({
    "id": "doc_001",
    "text": "Sample document text",
    "embedding": [0.1, 0.2, 0.3, ...],  # 1536-dimensional vector
    "metadata": {"source": "web", "category": "news"}
})

# Multiple records (dictionary format - RECOMMENDED for performance)
ds.append({
    "id": ["doc_001", "doc_002"],
    "text": ["Text 1", "Text 2"],
    "embedding": [embedding1, embedding2],
    "metadata": [{"source": "web"}, {"source": "book"}]
})

# List of dictionaries (row-by-row format)
ds.append([
    {"id": "doc_001", "text": "Text 1", "embedding": embedding1},
    {"id": "doc_002", "text": "Text 2", "embedding": embedding2}
])

# Append from other sources
ds.append(deeplake.from_parquet("./file.parquet"))
```

### **Updating Existing Data**
```python
# Update single value
ds["labels"][0] = 1

# Update batch of values
ds["labels"][0:32] = new_labels

# Update embeddings
embeddings = model.encode(images)
ds["embeddings"][0:len(embeddings)] = embeddings

# Async update for better performance
future = ds["labels"].set_async(slice(0, 32), new_labels)
future.wait()

# Update column metadata
ds["images"].metadata["mean"] = [0.485, 0.456, 0.406]
ds["images"].metadata["std"] = [0.229, 0.224, 0.225]
```

### **Batch Processing**
```python
# Process data in batches (RECOMMENDED approach)
batch_size = 1000
for i in range(0, len(data), batch_size):
    batch = data[i:i+batch_size]
    ds.append(batch)
    if i % 10000 == 0:
        ds.commit(f"Processed {i} records")

# Batch access for reading (FAST approach)
batch_size = 500
for batch in ds.batches(batch_size):
    print(batch["column1"])

# Single column batch access
column = ds["column1"]
for i in range(0, len(column), batch_size):
    print(column[i:i+batch_size])
```

### **Committing Changes**
```python
# Basic commit
ds.commit()

# Commit with message
ds.commit("Added new documents")

# Async commit
ds.commit_async().wait()

# Async commit with message
ds.commit_async("Added new documents").wait()

# Check if async commit is complete
future = ds.commit_async()
if future.is_completed():
    print("Commit completed!")
```

---

## 🔍 **Querying & Data Access**

### **Basic Queries**
```python
# Simple query
results = ds.query("SELECT * WHERE category == 'active'")

# Query with conditions
results = ds.query("SELECT * WHERE confidence > 0.9")

# Query with text search
results = ds.query("SELECT * WHERE text CONTAINS 'machine learning'")
```

### **Vector Similarity Search**
```python
# Cosine similarity search
search_vector = [0.1, 0.2, 0.3, ...]  # Your query vector
vector_str = ','.join(str(x) for x in search_vector)

results = ds.query(f"""
    SELECT *
    ORDER BY COSINE_SIMILARITY(embedding, ARRAY[{vector_str}]) DESC
    LIMIT 10
""")
```

### **Data Access Patterns**
```python
# Iterate through all records
for row in ds:
    image = row["images"]
    label = row["labels"]

# Access specific columns (with proper data handling)
images = ds["images"][:].numpy() if hasattr(ds["images"][:], 'numpy') else ds["images"][:]
labels = ds["labels"][:].numpy() if hasattr(ds["labels"][:], 'numpy') else ds["labels"][:]

# Access by index (with proper data handling)
first_image = ds["images"][0].numpy() if hasattr(ds["images"][0], 'numpy') else ds["images"][0]
first_label = ds["labels"][0].numpy() if hasattr(ds["labels"][0], 'numpy') else ds["labels"][0]

# Slicing
image_slice = ds["images"][10:20].numpy() if hasattr(ds["images"][10:20], 'numpy') else ds["images"][10:20]

# Access specific indices (non-contiguous)
selected = ds["embeddings"][[1, 5, 10]].numpy() if hasattr(ds["embeddings"][[1, 5, 10]], 'numpy') else ds["embeddings"][[1, 5, 10]]

# Async data access (for better performance)
future = ds["images"].get_async(slice(0, 1000))
images = future.result()

# Direct column access (RECOMMENDED for efficiency)
images = ds["images"][:].numpy() if hasattr(ds["images"][:], 'numpy') else ds["images"][:]
labels = ds["labels"][:].numpy() if hasattr(ds["labels"][:], 'numpy') else ds["labels"][:]

# Schema access (DeepLake v4 - NOT ds.columns!)
schema = ds.schema
print("Column names:", list(schema.keys()))
print("ID column info:", schema['id'])
```

### **Best Practices for Data Access**
```python
# ✅ PREFER: Batch access instead of row-by-row
batch_size = 500
for batch in ds.batches(batch_size):
    process_batch(batch["images"])

# ✅ PREFER: Direct column access
images = ds["images"][0:100]  # Fast

# ❌ AVOID: Row-by-row iteration for large datasets
for i in range(len(ds)):
    image = ds["images"][i]  # Slow for large datasets

# ✅ PREFER: Read-only mode when possible
ds = deeplake.open_read_only("path/to/dataset")

# ✅ PREFER: Use query for complex filtering
results = ds.query("SELECT * WHERE confidence > 0.9")
```

---

## 🗂️ **Dataset Management**

### **Dataset Information**
```python
# Get dataset summary
ds.summary()

# Get dataset length
total_records = len(ds)

# Get column information
for tensor_name in ds.tensors:
    column = ds[column_name]
    print(f"{column_name}: {column.dtype}")

# Get metadata
metadata = ds.metadata
```

### **Copying Datasets**
```python
# Copy entire dataset
deeplake.copy("s3://source/dataset", "s3://dest/dataset")

# Copy with credentials
deeplake.copy(
    src="s3://source-bucket/dataset",
    dst="gcs://dest-bucket/dataset", 
    dst_creds={"credentials": "for-dest-storage"}
)
```

### **Deleting Datasets**
```python
# DeepLake v4 doesn't have a built-in delete method
# You must delete the directory manually
import shutil
shutil.rmtree("path/to/dataset")

# Safe deletion with confirmation
def delete_dataset_safely(dataset_path):
    if os.path.exists(dataset_path):
        try:
            ds = deeplake.open(dataset_path)
            total_records = len(ds)
            print(f"Dataset contains {total_records} records")
            
            confirm = input("Are you sure you want to delete? (yes/no): ")
            if confirm.lower() == 'yes':
                shutil.rmtree(dataset_path)
                print("Dataset deleted successfully")
            else:
                print("Deletion cancelled")
        except Exception as e:
            print(f"Error accessing dataset: {e}")
    else:
        print("Dataset not found")
```

---

## ⚡ **Batch & Columnar Optimizations**

### **Understanding the Performance Problem**

DeepLake v4 is built on a **columnar storage architecture** similar to Apache Parquet. This means data is stored by columns, not by rows, which provides massive performance benefits when you understand how to leverage it.

### **❌ Inefficient Row-by-Row Processing**
```python
# SLOW - Don't do this!
for record in data:
    ds.append({
        "id": record["id"],
        "text": record["text"], 
        "embedding": record["embedding"]
    })
    ds.commit()  # Commit after every single record!
```

**Problems:**
- Each `append()` call has overhead
- Commits after every record are expensive
- Embedding generation one-by-one is slow
- Doesn't leverage columnar storage benefits

### **✅ Efficient Batch Processing**
```python
# FAST - Do this instead!
batch_data = {
    "id": [],
    "text": [],
    "embedding": []
}

# Collect data in lists first
for record in data:
    batch_data["id"].append(record["id"])
    batch_data["text"].append(record["text"])

# Generate embeddings for entire batch at once
batch_embeddings = embedding_function(batch_data["text"])
batch_data["embedding"] = [emb.tolist() for emb in batch_embeddings]

# Append entire batch at once
ds.append(batch_data)
ds.commit()  # Commit once per batch
```

### **Why Columnar Format is Faster**

#### **1. Memory Layout Optimization**
```python
# Row format (inefficient)
data = [
    {"id": "1", "text": "hello", "embedding": [0.1, 0.2]},
    {"id": "2", "text": "world", "embedding": [0.3, 0.4]}
]

# Column format (efficient)
data = {
    "id": ["1", "2"],
    "text": ["hello", "world"], 
    "embedding": [[0.1, 0.2], [0.3, 0.4]]
}
```

**Benefits:**
- **Better memory locality**: All IDs stored together, all texts together
- **Vectorized operations**: Can process entire columns at once
- **Compression efficiency**: Similar data types compress better together
- **Cache efficiency**: CPU cache hits are more likely

#### **2. Batch Size Optimization**
```python
# Optimal batch sizes for different scenarios
batch_sizes = {
    "text_only": 2000,      # Small data, can handle large batches
    "text_embeddings": 1000, # Medium data, balanced approach
    "images": 100,          # Large data, smaller batches
    "mixed_media": 500      # Variable data, conservative approach
}

# Memory-aware batch sizing
import psutil
available_memory = psutil.virtual_memory().available
if available_memory < 2 * 1024**3:  # Less than 2GB
    batch_size = 500
else:
    batch_size = 1000
```

#### **3. Embedding Generation Optimization**
```python
# SLOW - Individual embedding calls
embeddings = []
for text in texts:
    embedding = embedding_function(text)  # API call per text
    embeddings.append(embedding)

# FAST - Batch embedding generation
embeddings = embedding_function(texts)  # Single API call for all texts
```

**Performance Impact:**
- **Individual calls**: 1.22 seconds per record
- **Batch calls**: 0.01-0.1 seconds per record
- **Speedup**: 10-100x faster!

### **Commit Strategy Optimization**

#### **❌ Frequent Commits (Slow)**
```python
for batch in batches:
    ds.append(batch)
    ds.commit()  # Expensive I/O operation every time
```

#### **✅ Periodic Commits (Fast)**
```python
commit_frequency = 10  # Commit every 10 batches
for i, batch in enumerate(batches):
    ds.append(batch)
    if (i + 1) % commit_frequency == 0:
        ds.commit(f"Batch {i+1} completed")
```

**Benefits:**
- **Reduced I/O**: Fewer disk writes
- **Better throughput**: More time spent on data processing
- **Atomic operations**: Larger, more meaningful commits

### **Memory Management for Large Batches**

#### **Memory Monitoring**
```python
import psutil
import os

def monitor_memory():
    process = psutil.Process(os.getpid())
    memory_mb = process.memory_info().rss / 1024 / 1024
    return memory_mb

# Adjust batch size based on memory usage
memory_usage = monitor_memory()
if memory_usage > 1000:  # More than 1GB
    batch_size = 500
else:
    batch_size = 1000
```

#### **Memory-Efficient Data Types**
```python
# Use appropriate data types to save memory
ds.add_column("embedding", types.Embedding(1536))  # Float32 by default
ds.add_column("id", types.Text())                  # Efficient text storage
ds.add_column("metadata", types.Dict())            # Compressed JSON storage

# Avoid unnecessary precision
# Use float32 instead of float64 for embeddings
embeddings = np.array(embeddings, dtype=np.float32)
```

### **Async Operations for Maximum Performance**

#### **Async Batch Processing**
```python
import asyncio

async def process_batch_async(batch_data, ds):
    # Generate embeddings asynchronously
    embeddings = await asyncio.to_thread(embedding_function, batch_data["text"])
    batch_data["embedding"] = [emb.tolist() for emb in embeddings]
    
    # Append to dataset
    ds.append(batch_data)

# Process multiple batches concurrently
async def process_all_batches(batches, ds):
    tasks = [process_batch_async(batch, ds) for batch in batches]
    await asyncio.gather(*tasks)
```

### **Performance Monitoring & Profiling**

#### **Real-Time Performance Metrics**
```python
import time

def track_performance():
    start_time = time.time()
    records_processed = 0
    
    for batch in batches:
        # Process batch
        ds.append(batch)
        records_processed += len(batch["id"])
        
        # Calculate metrics
        elapsed = time.time() - start_time
        records_per_second = records_processed / elapsed
        memory_usage = psutil.Process().memory_info().rss / 1024 / 1024
        
        print(f"Speed: {records_per_second:.1f} records/sec, Memory: {memory_usage:.1f}MB")
```

### **Best Practices Summary**

#### **✅ Do This:**
- Use **dictionary format**: `{"col1": [...], "col2": [...]}`
- **Batch size 1000+** for text and embeddings
- **Generate embeddings in batches**
- **Commit every 10-50 batches**
- **Monitor memory usage**
- **Use appropriate data types**

#### **❌ Don't Do This:**
- Row-by-row processing
- Individual embedding calls
- Commits after every record
- Ignoring memory usage
- Using unnecessarily precise data types

### **Performance Comparison**

| Method | Records/sec | Memory Usage | I/O Operations |
|--------|-------------|--------------|----------------|
| Row-by-row | 0.8 | Low | High |
| Small batches (10) | 1.2 | Low | High |
| **Large batches (1000)** | **50-100** | **Medium** | **Low** |
| **Async + Large batches** | **100-200** | **Medium** | **Low** |

### **Troubleshooting Performance Issues**

#### **Out of Memory Errors**
```python
# Reduce batch size
batch_size = 500  # Instead of 1000

# Use memory-efficient data types
embeddings = np.array(embeddings, dtype=np.float32)

# Process in smaller chunks
for chunk in chunks(data, batch_size):
    process_chunk(chunk)
```

#### **Slow Embedding Generation**
```python
# Use batch embedding generation
embeddings = embedding_function(texts)  # Not individual calls

# Consider async operations
embeddings = await asyncio.to_thread(embedding_function, texts)

# Use faster embedding models
model = "text-embedding-3-small"  # Faster than text-embedding-3-large
```

#### **Slow I/O Operations**
```python
# Reduce commit frequency
commit_frequency = 20  # Instead of 10

# Use compression
ds.add_column("text", types.Text(compression="lz4"))

# Consider cloud storage for large datasets
ds = deeplake.create("s3://bucket/dataset")  # Instead of local storage
```

---

## 🌿 **Version Control & Branching**

### **Branches**
```python
# Create branch
ds.branch("experimental")

# Access branch
branch = ds.branches["experimental"]
branch_ds = branch.open()

# Merge branch
ds.merge("experimental")

# Delete branch
branch.delete()
```

### **Tags**
```python
# Create tag
ds.tag("v1.0", "Initial release")

# Access tagged version
tag = ds.tags["v1.0"]
tagged_ds = tag.open()

# Delete tag
tag.delete()
```

### **History**
```python
# View commit history
for version in ds.history:
    print(version.id, version.message)
```

---

## 🔄 **Synchronization**

### **Push/Pull Operations**
```python
# Push changes to remote
ds.push("s3://remote/dataset")

# Pull changes from remote
ds.pull("s3://remote/dataset")

# Async operations
async def sync_async():
    await ds.push_async("s3://remote/dataset")
    await ds.pull_async("s3://remote/dataset")
```

---

## 🕒 **Recency-Based Vector Search**

### **Problem: Prioritizing Recent Results Without Timestamps**

When ingesting data sequentially over time, you want to prioritize recent results in vector search without explicit timestamps. DeepLake v4 provides several approaches using insertion order as a recency proxy.

### **Solution: Hybrid Scoring with ROW_NUMBER()**

```python
# Basic recency-weighted search
def search_with_recency(ds, query, recency_weight=0.3):
    query_embedding = embedding_function(query)[0]
    text_vector = ','.join(str(x) for x in query_embedding)
    
    results = ds.query(f"""
        SELECT *,
               COSINE_SIMILARITY(embedding, ARRAY[{text_vector}]) as similarity_score,
               (ROW_NUMBER() - 1) / (SELECT COUNT(*) FROM dataset) as recency_score,
               ((1 - {recency_weight}) * COSINE_SIMILARITY(embedding, ARRAY[{text_vector}]) + 
                {recency_weight} * ((ROW_NUMBER() - 1) / (SELECT COUNT(*) FROM dataset))) as combined_score
        ORDER BY combined_score DESC
        LIMIT 10
    """)
    return results
```

### **Recency Scoring Strategies**

#### **1. Normalized Rank (Recommended)**
```python
# Linear recency scoring
recency_score = (ROW_NUMBER() - 1) / (SELECT COUNT(*) FROM dataset)
# Higher row numbers = more recent = higher recency score
```

#### **2. Exponential Decay**
```python
# Exponential decay for stronger recent bias
recency_score = EXP(-0.1 * (1 - normalized_rank))
# Emphasizes very recent results more strongly
```

#### **3. Bucketed Recency**
```python
# Discrete recency buckets
CASE
    WHEN (ROW_NUMBER() > COUNT(*) * 0.9) THEN 1.0  -- Last 10%
    WHEN (ROW_NUMBER() > COUNT(*) * 0.7) THEN 0.7  -- Next 20%
    ELSE 0.3  -- Older 70%
END AS recency_score
```

### **Hybrid Scoring Formula**

```python
# Weighted combination of similarity and recency
combined_score = (1 - recency_weight) * similarity_score + recency_weight * recency_score

# Where:
# - recency_weight = 0.0: Pure similarity (existing behavior)
# - recency_weight = 0.3: Balanced (recommended default)
# - recency_weight = 0.7: Recency-focused
# - recency_weight = 1.0: Pure recency (not recommended)
```

### **Implementation in CustomDeepLake**

```python
# Standard search (unchanged)
results = db.search("machine learning", n_results=5)

# Recency-weighted search
results = db.search("machine learning", n_results=5, recency_weight=0.3)

# Recency-focused search (convenience method)
results = db.search_recent("machine learning", n_results=5)

# Pure recency (not recommended for most use cases)
results = db.search("machine learning", n_results=5, recency_weight=1.0)
```

### **Advanced Recency Patterns**

#### **Windowed Recency**
```python
# Only consider recent N records for recency scoring
SELECT *,
       COSINE_SIMILARITY(embedding, ARRAY[{text_vector}]) as similarity_score,
       CASE 
           WHEN ROW_NUMBER() > (SELECT COUNT(*) FROM dataset) - 1000 
           THEN (ROW_NUMBER() - (SELECT COUNT(*) FROM dataset) + 1000) / 1000.0
           ELSE 0.0
       END as recency_score
FROM dataset
WHERE ROW_NUMBER() > (SELECT COUNT(*) FROM dataset) - 1000
ORDER BY combined_score DESC
```

#### **Multiplicative Combination**
```python
# Multiply scores instead of adding (stronger effect)
combined_score = similarity_score * (1 + recency_score)
```

### **Best Practices**

1. **Start with recency_weight=0.3** for balanced results
2. **Test different weights** based on your use case
3. **Monitor result quality** - too much recency can hurt relevance
4. **Consider your data ingestion pattern** - batch ingestion may need different approaches
5. **Use windowed recency** for very large datasets to focus on truly recent items

### **Performance Considerations**

- **ROW_NUMBER() calculation** adds overhead to queries
- **Large datasets** may benefit from windowed recency approaches
- **Index usage** - ensure your embedding column is properly indexed
- **Query complexity** - hybrid scoring queries are more complex than pure similarity

---

## ⚠️ **Common Errors & Fixes**

### **Error: 'Dataset' object has no attribute 'columns'**
```python
# ❌ WRONG (DeepLake v3 API)
for column_name in ds.columns:
    print(column_name)

# ✅ CORRECT (DeepLake v4 API)
for column_name in ds.schema.keys():
    print(column_name)
```

### **Error: 'str' object has no attribute 'numpy'**
```python
# ❌ WRONG - calling .numpy() on string data
text_value = ds['text'][0].numpy()  # Fails if text is already a string

# ✅ CORRECT - check if .numpy() is available
text_value = ds['text'][0].numpy() if hasattr(ds['text'][0], 'numpy') else ds['text'][0]

# ✅ ALTERNATIVE - handle different data types
if isinstance(ds['text'][0], str):
    text_value = ds['text'][0]  # Already a string
else:
    text_value = ds['text'][0].numpy()  # Convert to numpy
```

### **Error: Dataset validation fails**
```python
# ✅ ROBUST validation approach
def validate_dataset(ds):
    try:
        # Check if dataset has required attributes
        if not hasattr(ds, 'schema'):
            print("❌ Dataset missing schema attribute")
            return False
            
        # Check schema structure
        schema_keys = list(ds.schema.keys())
        print(f"✅ Schema columns: {schema_keys}")
        
        # Test data access with error handling
        if len(ds) > 0:
            for col_name in schema_keys:
                try:
                    sample_data = ds[col_name][0]
                    if hasattr(sample_data, 'numpy'):
                        sample_data = sample_data.numpy()
                    print(f"✅ Column '{col_name}' accessible")
                except Exception as e:
                    print(f"❌ Column '{col_name}' access failed: {e}")
                    return False
        
        return True
    except Exception as e:
        print(f"❌ Validation failed: {e}")
        return False
```

---

## ⚡ **Performance & Best Practices**

### **Batch Processing**
```python
# Process in batches for large datasets
batch_size = 1000
for i in range(0, len(data), batch_size):
    batch = data[i:i+batch_size]
    ds.append(batch)
    if i % 10000 == 0:
        ds.commit(f"Processed {i} records")
```

### **Async Operations**
```python
# Use async for better performance
future = ds.query_async("SELECT * WHERE category == 'active'")
results = future.result()

# Async commit
future = ds.commit_async("Added new data")
future.wait()
```

### **Memory Management**
```python
# Use in-memory datasets for temporary data
memory_ds = deeplake.create("mem://temp_dataset")

# Copy to persistent storage when ready
memory_ds.copy("s3://my-bucket/persistent_dataset")
```

---

## 🚨 **Common Issues & Solutions**

### **Dataset Not Found Error**
```python
# Check if dataset exists before opening
import os
if os.path.exists(dataset_path):
    ds = deeplake.open(dataset_path)
else:
    ds = deeplake.create(dataset_path)
```

### **Schema Mismatch**
```python
# Always commit schema changes
ds.add_column("new_field", types.Text())
ds.commit("Added new column")
```

### **Memory Issues**
```python
# Use batch processing for large datasets
# Process in chunks and commit regularly
```

---

## 📋 **Quick Reference**

### **Essential Commands**
```python
# Create
ds = deeplake.create("path")

# Open
ds = deeplake.open("path")

# Add column
ds.add_column("name", types.Text())

# Append data
ds.append({"name": ["value"]})

# Commit
ds.commit("message")

# Query
results = ds.query("SELECT * WHERE condition")

# Summary
ds.summary()
```

### **Column Type Quick Reference**
- `types.Text()` - Text data
- `types.Int32()` - 32-bit integer
- `types.Float32()` - 32-bit float
- `types.Embedding(1536)` - Vector embeddings
- `types.Image()` - Image data
- `types.Dict()` - Dictionary/JSON data
- `types.ClassLabel("int32")` - Classification labels

---

## 🎯 **Key Takeaways**

1. **Always commit schema changes** after adding columns
2. **Use batch processing** for large datasets - dictionary format is faster than row-by-row
3. **DeepLake v4 uses `types.Dict()`** for metadata (not `types.JSON()`)
4. **No built-in delete method** - delete directories manually with `shutil.rmtree()`
5. **Vector search requires** converting embeddings to comma-separated strings
6. **Use async operations** for better performance (`set_async`, `get_async`, `commit_async`)
7. **Cloud storage** requires proper credentials setup
8. **Version control** with branches and tags for data management
9. **Update existing data** using direct column assignment: `ds["column"][index] = new_value`
10. **Prefer read-only mode** when you don't need to modify data
11. **Use direct column access** instead of row-by-row iteration for better performance
12. **Batch access is significantly faster** than individual record access
13. **Use `ds.schema`** instead of `ds.columns` for schema information (DeepLake v4 API)
14. **Handle data access carefully** - check if `.numpy()` is available before calling it
15. **Robust error handling** needed for data access due to different data types
16. **Recency-based search** using `ROW_NUMBER()` and hybrid scoring for prioritizing recent results
17. **Hybrid scoring formula** combines vector similarity with recency: `(1-w)*similarity + w*recency`
18. **Start with recency_weight=0.3** for balanced similarity and recency results

---

*Based on DeepLake v4.2 documentation from Context7 research*