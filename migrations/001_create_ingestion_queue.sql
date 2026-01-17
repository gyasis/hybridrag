-- Migration: Create ingestion_queue table for scalable, organic ingestion
-- Handles: in-flight modifications, priority bumping, resume after failures

CREATE TABLE IF NOT EXISTS ingestion_queue (
    -- Primary identification
    file_path TEXT PRIMARY KEY,

    -- Change detection
    content_hash TEXT,
    last_modified TIMESTAMP WITH TIME ZONE,
    file_size_bytes BIGINT,

    -- Processing status
    status TEXT NOT NULL DEFAULT 'DISCOVERED',
    -- DISCOVERED: Found but not processed
    -- VECTORIZING: Currently creating embeddings
    -- VECTORIZED: Vector search ready (basic RAG works)
    -- GRAPHING: Currently extracting entities/relationships
    -- COMPLETED: Fully indexed (hybrid RAG works)
    -- FAILED: Processing error
    -- DIRTY: File modified during processing (needs re-queue)

    -- Priority and scheduling
    priority INTEGER DEFAULT 100,
    -- Lower number = higher priority
    -- 0-50: User-starred folders
    -- 51-100: Recent files (by mtime)
    -- 101-200: Older files

    -- Retry logic
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    last_error TEXT,

    -- Processing timestamps
    discovered_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    vectorized_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,

    -- Worker assignment (for distributed processing)
    locked_by TEXT,  -- Worker PID/hostname
    locked_at TIMESTAMP WITH TIME ZONE,

    -- Metadata
    folder_name TEXT,  -- .specstory parent folder name
    project_path TEXT  -- Top-level project path
);

-- Indexes for efficient queue operations
CREATE INDEX IF NOT EXISTS idx_queue_status_priority
    ON ingestion_queue(status, priority, last_modified DESC);

CREATE INDEX IF NOT EXISTS idx_queue_locked
    ON ingestion_queue(locked_by, locked_at)
    WHERE locked_by IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_queue_project
    ON ingestion_queue(project_path, status);

CREATE INDEX IF NOT EXISTS idx_queue_modified
    ON ingestion_queue(last_modified DESC);

-- Function: Mark file as dirty if modified during processing
CREATE OR REPLACE FUNCTION mark_dirty_if_changed()
RETURNS TRIGGER AS $$
BEGIN
    -- If file is being re-discovered with a different hash
    IF NEW.content_hash IS DISTINCT FROM OLD.content_hash THEN
        IF OLD.status IN ('VECTORIZING', 'GRAPHING') THEN
            -- In-flight process - mark as DIRTY
            NEW.status := 'DIRTY';
            NEW.priority := 50;  -- Boost priority
        ELSIF OLD.status IN ('VECTORIZED', 'COMPLETED') THEN
            -- Already processed - reset to re-ingest
            NEW.status := 'DISCOVERED';
            NEW.priority := 50;  -- Boost priority for updates
            NEW.vectorized_at := NULL;
            NEW.completed_at := NULL;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_mark_dirty
    BEFORE UPDATE ON ingestion_queue
    FOR EACH ROW
    EXECUTE FUNCTION mark_dirty_if_changed();

-- Function: Clean up stale locks (workers that crashed)
CREATE OR REPLACE FUNCTION cleanup_stale_locks(timeout_minutes INTEGER DEFAULT 30)
RETURNS INTEGER AS $$
DECLARE
    affected_rows INTEGER;
BEGIN
    UPDATE ingestion_queue
    SET
        locked_by = NULL,
        locked_at = NULL,
        status = CASE
            WHEN status = 'VECTORIZING' THEN 'DISCOVERED'
            WHEN status = 'GRAPHING' THEN 'VECTORIZED'
            ELSE status
        END
    WHERE
        locked_by IS NOT NULL
        AND locked_at < NOW() - (timeout_minutes || ' minutes')::INTERVAL;

    GET DIAGNOSTICS affected_rows = ROW_COUNT;
    RETURN affected_rows;
END;
$$ LANGUAGE plpgsql;

-- View: Queue statistics
CREATE OR REPLACE VIEW ingestion_stats AS
SELECT
    status,
    COUNT(*) as file_count,
    SUM(file_size_bytes) as total_bytes,
    MIN(priority) as min_priority,
    MAX(last_modified) as newest_file
FROM ingestion_queue
GROUP BY status;

-- View: Projects overview
CREATE OR REPLACE VIEW project_progress AS
SELECT
    project_path,
    folder_name,
    COUNT(*) as total_files,
    COUNT(*) FILTER (WHERE status = 'COMPLETED') as completed,
    COUNT(*) FILTER (WHERE status = 'VECTORIZED') as vectorized_only,
    COUNT(*) FILTER (WHERE status IN ('DISCOVERED', 'DIRTY')) as pending,
    MAX(last_modified) as last_update
FROM ingestion_queue
GROUP BY project_path, folder_name
ORDER BY last_update DESC;

COMMENT ON TABLE ingestion_queue IS 'Queue for organic, scalable ingestion of SpecStory markdown files';
COMMENT ON COLUMN ingestion_queue.status IS 'DISCOVERED → VECTORIZING → VECTORIZED → GRAPHING → COMPLETED (or DIRTY if modified during processing)';
COMMENT ON COLUMN ingestion_queue.priority IS 'Lower = higher priority. 0-50: starred, 51-100: recent, 101+: older files';
