-- HybridRAG PostgreSQL Initialization Script
-- ==========================================
-- This script runs automatically when the container starts for the first time.
-- It sets up the pgvector extension required for vector similarity search.

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Verify pgvector is installed
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        RAISE NOTICE 'pgvector extension installed successfully';
    ELSE
        RAISE EXCEPTION 'pgvector extension failed to install';
    END IF;
END $$;

-- Grant necessary permissions to hybridrag user
GRANT ALL PRIVILEGES ON DATABASE hybridrag TO hybridrag;
GRANT ALL ON SCHEMA public TO hybridrag;

-- Create schema for HybridRAG migration tracking (optional)
CREATE TABLE IF NOT EXISTS hybridrag_migration_jobs (
    job_id VARCHAR(64) PRIMARY KEY,
    database_name VARCHAR(255) NOT NULL,
    source_backend VARCHAR(32) NOT NULL,
    target_backend VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    total_records INTEGER DEFAULT 0,
    migrated_records INTEGER DEFAULT 0,
    failed_records INTEGER DEFAULT 0,
    last_error TEXT,
    checkpoints JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for status queries
CREATE INDEX IF NOT EXISTS idx_migration_status ON hybridrag_migration_jobs(status);

-- Log initialization complete
DO $$
BEGIN
    RAISE NOTICE 'HybridRAG PostgreSQL initialization complete';
END $$;
