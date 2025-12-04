FROM python:3.12-slim

# Metadata
LABEL maintainer="HybridRAG Team"
LABEL description="HybridRAG - Multi-project knowledge graph RAG system"
LABEL version="1.0.0"

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first (for Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install PromptChain for agentic features
RUN pip install --no-cache-dir git+https://github.com/gyasis/PromptChain.git

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p lightrag_db ingestion_queue/errors ingestion_queue/processed

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python hybridrag.py status || exit 1

# Default command (can be overridden)
CMD ["python", "hybridrag.py", "--help"]
