#!/usr/bin/env python3
"""
Database Metadata Management
=============================
Tracks source folders, ingestion history, and configuration for each database.
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime


class DatabaseMetadata:
    """Manages metadata for a LightRAG database."""

    def __init__(self, database_dir: str):
        """
        Initialize metadata manager.

        Args:
            database_dir: Path to LightRAG database directory
        """
        self.database_dir = Path(database_dir)
        self.metadata_file = self.database_dir / "database_metadata.json"
        self.metadata = self._load_metadata()

    def _load_metadata(self) -> Dict[str, Any]:
        """Load metadata from file or create default."""
        if self.metadata_file.exists():
            with open(self.metadata_file, 'r') as f:
                return json.load(f)
        else:
            return {
                "version": "1.0",
                "created_at": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat(),
                "source_folders": [],
                "ingestion_history": [],
                "total_files_ingested": 0,
                "database_type": "lightrag",
                "description": ""
            }

    def _save_metadata(self):
        """Save metadata to file."""
        self.database_dir.mkdir(parents=True, exist_ok=True)
        self.metadata["last_updated"] = datetime.now().isoformat()

        with open(self.metadata_file, 'w') as f:
            json.dump(self.metadata, f, indent=2)

    def add_source_folder(self, folder_path: str, recursive: bool = True):
        """
        Add a source folder to tracked sources.

        Args:
            folder_path: Path to source folder
            recursive: Whether folder was watched recursively
        """
        folder_path = str(Path(folder_path).resolve())

        # Check if already exists
        for source in self.metadata["source_folders"]:
            if source["path"] == folder_path:
                # Update existing entry
                source["last_ingested"] = datetime.now().isoformat()
                source["recursive"] = recursive
                self._save_metadata()
                return

        # Add new source
        self.metadata["source_folders"].append({
            "path": folder_path,
            "added_at": datetime.now().isoformat(),
            "last_ingested": datetime.now().isoformat(),
            "recursive": recursive
        })
        self._save_metadata()

    def record_ingestion(self,
                        folder_path: str,
                        files_processed: int,
                        success: bool = True,
                        notes: str = ""):
        """
        Record an ingestion event.

        Args:
            folder_path: Source folder path
            files_processed: Number of files processed
            success: Whether ingestion succeeded
            notes: Additional notes
        """
        self.metadata["ingestion_history"].append({
            "timestamp": datetime.now().isoformat(),
            "source_folder": str(Path(folder_path).resolve()),
            "files_processed": files_processed,
            "success": success,
            "notes": notes
        })

        if success:
            self.metadata["total_files_ingested"] += files_processed

        self._save_metadata()

    def get_source_folders(self) -> List[Dict[str, Any]]:
        """Get list of tracked source folders."""
        return self.metadata.get("source_folders", [])

    def get_ingestion_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent ingestion history.

        Args:
            limit: Maximum number of entries to return
        """
        history = self.metadata.get("ingestion_history", [])
        return history[-limit:]

    def set_description(self, description: str):
        """Set database description."""
        self.metadata["description"] = description
        self._save_metadata()

    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        return {
            "created_at": self.metadata.get("created_at"),
            "last_updated": self.metadata.get("last_updated"),
            "total_files_ingested": self.metadata.get("total_files_ingested", 0),
            "source_folders_count": len(self.metadata.get("source_folders", [])),
            "ingestion_events": len(self.metadata.get("ingestion_history", [])),
            "description": self.metadata.get("description", "")
        }

    def exists(self) -> bool:
        """Check if metadata file exists."""
        return self.metadata_file.exists()

    def clear_history(self):
        """Clear ingestion history (keep source folders)."""
        self.metadata["ingestion_history"] = []
        self._save_metadata()

    def remove_source_folder(self, folder_path: str):
        """
        Remove a source folder from tracking.

        Args:
            folder_path: Path to folder to remove
        """
        folder_path = str(Path(folder_path).resolve())
        self.metadata["source_folders"] = [
            s for s in self.metadata["source_folders"]
            if s["path"] != folder_path
        ]
        self._save_metadata()

    def get_all_metadata(self) -> Dict[str, Any]:
        """Get complete metadata."""
        return self.metadata.copy()


def list_all_databases(base_dir: str = ".") -> List[Dict[str, Any]]:
    """
    Find all LightRAG databases in a directory.

    Args:
        base_dir: Base directory to search

    Returns:
        List of database info dictionaries
    """
    databases = []
    base_path = Path(base_dir)

    # Look for directories containing LightRAG files
    for item in base_path.iterdir():
        if item.is_dir():
            # Check for LightRAG signature files
            if (item / "kv_store_full_docs.json").exists() or \
               (item / "vdb_entities.json").exists():

                metadata = DatabaseMetadata(str(item))
                databases.append({
                    "path": str(item),
                    "name": item.name,
                    "has_metadata": metadata.exists(),
                    "stats": metadata.get_stats() if metadata.exists() else None
                })

    return databases


# Example usage
if __name__ == "__main__":
    # Create metadata for a database
    db_meta = DatabaseMetadata("./lightrag_db")

    # Add source folder
    db_meta.add_source_folder("./data", recursive=True)
    db_meta.set_description("Medical database schema from Athena")

    # Record ingestion
    db_meta.record_ingestion("./data", files_processed=150, success=True)

    # Get info
    print("Source folders:", db_meta.get_source_folders())
    print("Stats:", db_meta.get_stats())

    # List all databases
    print("\nAll databases:")
    for db in list_all_databases():
        print(f"  {db['name']}: {db['path']}")
