# LightRAG Ingestion Commands

## Manual Ingestion Command

To run the DeepLake to LightRAG conversion/ingestion process manually:

```bash
uv run python deeplake_to_lightrag.py
```

## Prerequisites

1. **Environment Setup** (if not already done):
```bash
# Install UV dependencies
uv sync

# Verify environment variables in .env file
cat .env
# Should contain:
# OPENAI_API_KEY=your_openai_api_key_here
```

2. **Database Access**:
   - DeepLake source: `/media/gyasis/Drive 2/Deeplake_Storage/athena_descriptions_v4`
   - Target directory: `./athena_lightrag_db` (created automatically)

## What the Ingestion Process Does

### Phase 1: Initialization ⚙️
- Sets up LightRAG storages and pipeline
- Validates OpenAI API key
- Initializes knowledge graph database

### Phase 2: Extraction 🔍
- Processes 15,149+ medical table descriptions from DeepLake
- Shows real-time progress with success/error counts
- Formats JSONL records into structured documents
- Validates essential fields (TABLE NAME, SCHEMANAME)

### Phase 3: Ingestion 📚
- Loads documents into LightRAG knowledge graph
- Batch processing with rate limiting
- Progress tracking with ETA calculation
- Individual retry for failed batches

### Phase 4: Validation 🔍
- Tests database responsiveness
- Saves pipeline artifacts and metadata
- Provides next steps for querying

## Expected Output

```
🚀 DEEPLAKE TO LIGHTRAG INGESTION PIPELINE
======================================================================
📅 Started at: 2024-12-XX XX:XX:XX
📂 Source: /media/gyasis/Drive 2/Deeplake_Storage/athena_descriptions_v4
📁 Target: ./athena_lightrag_db
🤖 Model: gpt-4o-mini (text-embedding-ada-002)
======================================================================

⚙️ INITIALIZATION PHASE: Setting up LightRAG storages
✅ Initialization completed in X.XX seconds

🔍 EXTRACTION PHASE: Processing X,XXX records from DeepLake
======================================================================
Extracting documents: 100%|██████████| 15149/15149 [XX:XX<00:00, XX.X docs/s, Success=15,XXX, Errors=X, Rate=XX.X%]

✅ EXTRACTION COMPLETE:
   • Successfully processed: XX,XXX documents
   • Errors encountered: XXX records
   • Success rate: XX.X%
   • Total extracted: XX,XXX documents ready for ingestion

📚 INGESTION PHASE: Loading XX,XXX documents into LightRAG
======================================================================
📊 Configuration:
   • Batch size: 8 documents
   • Expected batches: X,XXX
   • Rate limiting: 1 second between batches

Ingesting to LightRAG: 100%|██████████| 15149/15149 [XX:XX<00:00, XX.X docs/s, Ingested=XX,XXX, Failed=XX, Rate=X.X/s, ETA=XX:XX:XX]

✅ INGESTION COMPLETE:
   • Successfully ingested: XX,XXX documents
   • Failed documents: XXX
   • Success rate: XX.X%
   • Total time: X:XX:XX
   • Average rate: XX.X docs/second

🔍 VALIDATION PHASE: Verifying LightRAG database
✅ Database validation successful - LightRAG is responsive
📁 Artifacts saved to: ./athena_lightrag_db/pipeline_artifacts

🎉 PIPELINE COMPLETED SUCCESSFULLY!
======================================================================
📊 SUMMARY STATISTICS:
   • Total documents processed: XX,XXX
   • Total pipeline time: X:XX:XX
   • Average processing rate: XX.X docs/second

⏱️ PHASE BREAKDOWN:
   • Initialization: X.XXs (X.X%)
   • Extraction: X:XX:XX (XX.X%)
   • Ingestion: X:XX:XX (XX.X%)

🎯 NEXT STEPS:
   1. Run queries using: uv run python lightrag_query_demo.py
   2. Test simple queries using: uv run python test_simple.py
   3. Database ready for complex medical table relationship queries
======================================================================
```

## After Ingestion is Complete

Once you see "🎉 PIPELINE COMPLETED SUCCESSFULLY!", the database is ready for complex queries about:

- Table relationships and foreign keys
- Appointment scheduling workflows  
- Clinical encounter connections
- CPT codes and billing relationships
- Medical data flow between tables

## Troubleshooting

- **Rate Limiting**: The script includes automatic delays and retry logic
- **Memory Issues**: Uses batch processing to handle large dataset efficiently
- **API Errors**: Individual document retry for failed batches
- **Progress Tracking**: Real-time updates with ETA calculations

Run the command above to start the full ingestion process.