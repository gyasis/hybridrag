#!/usr/bin/env python3
"""
HybridRAG Configuration
======================
Central configuration for the hybrid RAG system.
"""

import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

@dataclass
class LightRAGConfig:
    """LightRAG specific configuration."""
    working_dir: str = "./lightrag_db"
    api_key: Optional[str] = None
    model_name: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    max_async: int = 4
    enable_cache: bool = True
    chunk_size: int = 1200
    chunk_overlap: int = 100
    max_tokens_per_chunk: int = 500
    
@dataclass
class IngestionConfig:
    """Configuration for document ingestion."""
    watch_folders: List[str] = field(default_factory=lambda: ["./data"])
    file_extensions: List[str] = field(default_factory=lambda: [
        ".txt", ".md", ".pdf", ".json", ".py", ".js", ".html", ".csv", ".yaml", ".yml"
    ])
    recursive: bool = True
    batch_size: int = 10
    poll_interval: float = 5.0  # seconds
    ingestion_queue_dir: str = "./ingestion_queue"
    processed_files_db: str = "./processed_files.db"
    enable_ocr: bool = False
    max_file_size_mb: float = 50.0
    
@dataclass
class SearchConfig:
    """Configuration for search functionality."""
    default_mode: str = "hybrid"  # local, global, hybrid, naive
    default_top_k: int = 10
    max_entity_tokens: int = 6000
    max_relation_tokens: int = 8000
    response_type: str = "Multiple Paragraphs"
    enable_reranking: bool = True
    enable_context_accumulation: bool = True
    
@dataclass
class SystemConfig:
    """Overall system configuration."""
    project_root: Path = Path(__file__).parent.parent
    log_dir: str = "./logs"
    log_level: str = "INFO"
    enable_monitoring: bool = True
    enable_auto_backup: bool = True
    backup_interval_hours: int = 24
    max_concurrent_ingestions: int = 3
    enable_deduplication: bool = True
    
@dataclass
class HybridRAGConfig:
    """Complete configuration for HybridRAG system."""
    lightrag: LightRAGConfig = field(default_factory=LightRAGConfig)
    ingestion: IngestionConfig = field(default_factory=IngestionConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    system: SystemConfig = field(default_factory=SystemConfig)
    
    def __post_init__(self):
        """Post-initialization setup."""
        # Set API key from environment if not provided
        if not self.lightrag.api_key:
            self.lightrag.api_key = os.getenv("OPENAI_API_KEY")
            
        # Convert relative paths to absolute
        self.lightrag.working_dir = str(self.system.project_root / self.lightrag.working_dir)
        self.ingestion.ingestion_queue_dir = str(self.system.project_root / self.ingestion.ingestion_queue_dir)
        self.ingestion.processed_files_db = str(self.system.project_root / self.ingestion.processed_files_db)
        self.system.log_dir = str(self.system.project_root / self.system.log_dir)
        
        # Ensure directories exist
        for dir_path in [
            self.lightrag.working_dir,
            self.ingestion.ingestion_queue_dir,
            self.system.log_dir
        ]:
            Path(dir_path).mkdir(parents=True, exist_ok=True)
            
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "lightrag": self.lightrag.__dict__,
            "ingestion": self.ingestion.__dict__,
            "search": self.search.__dict__,
            "system": {k: str(v) if isinstance(v, Path) else v 
                      for k, v in self.system.__dict__.items()}
        }

def load_config(config_path: Optional[str] = None) -> HybridRAGConfig:
    """
    Load configuration from file or use defaults.
    
    Args:
        config_path: Optional path to configuration file
        
    Returns:
        HybridRAGConfig instance
    """
    if config_path and Path(config_path).exists():
        import json
        with open(config_path, 'r') as f:
            config_dict = json.load(f)
        # TODO: Implement config loading from dict
        return HybridRAGConfig()
    return HybridRAGConfig()