#!/usr/bin/env python3
"""
Direct test of HybridRAG JSON database (NO MCP).
Tests if the core functionality works against the existing JSON files.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

# Set environment variables
os.environ.setdefault("HYBRIDRAG_DATABASE", str(Path(__file__).parent / "lightrag_db"))

from config.config import HybridRAGConfig
from src.lightrag_core import HybridLightRAGCore
from src.config.config import BackendConfig, BackendType

async def test_json_database():
    """Test direct query against JSON database."""
    print("=" * 60)
    print("DIRECT JSON DATABASE TEST (No MCP)")
    print("=" * 60)

    # Check JSON files exist
    db_path = Path(__file__).parent / "lightrag_db"
    print(f"\n1. Checking database path: {db_path}")

    json_files = list(db_path.glob("*.json"))
    print(f"   Found {len(json_files)} JSON files")

    for f in json_files[:5]:
        size_mb = f.stat().st_size / (1024 * 1024)
        print(f"   - {f.name}: {size_mb:.1f} MB")

    # Initialize with JSON backend (explicitly)
    print("\n2. Initializing HybridLightRAGCore with JSON backend...")

    config = HybridRAGConfig()
    config.lightrag.working_dir = str(db_path)

    # Force JSON backend
    backend_config = BackendConfig(backend_type=BackendType.JSON)

    try:
        core = HybridLightRAGCore(config, backend_config=backend_config)
        print("   ✅ Core initialized successfully")
    except Exception as e:
        print(f"   ❌ Failed to initialize: {e}")
        return False

    # Test queries
    test_queries = [
        "RAF mapping tables temp 2026",
        "SpecStory conversation history",
        "database migration"
    ]

    print("\n3. Testing queries...")

    for query in test_queries:
        print(f"\n   Query: '{query}'")
        print("   " + "-" * 50)

        try:
            # Test local query
            print("   [LOCAL] ", end="", flush=True)
            result = await core.local_query(query, top_k=3)
            if result.error:
                print(f"❌ Error: {result.error}")
            elif result.result and len(result.result) > 10:
                print(f"✅ Got {len(result.result)} chars in {result.execution_time:.2f}s")
                print(f"   Preview: {result.result[:200]}...")
            else:
                print(f"⚠️ Empty result in {result.execution_time:.2f}s")
        except Exception as e:
            print(f"❌ Exception: {e}")

        try:
            # Test hybrid query
            print("   [HYBRID] ", end="", flush=True)
            result = await core.hybrid_query(query, top_k=3)
            if result.error:
                print(f"❌ Error: {result.error}")
            elif result.result and len(result.result) > 10:
                print(f"✅ Got {len(result.result)} chars in {result.execution_time:.2f}s")
                print(f"   Preview: {result.result[:200]}...")
            else:
                print(f"⚠️ Empty result in {result.execution_time:.2f}s")
        except Exception as e:
            print(f"❌ Exception: {e}")

    # Check database stats
    print("\n4. Database stats:")
    try:
        stats = core.get_stats()
        print(f"   Working dir: {stats.get('working_directory')}")
        print(f"   Initialized: {stats.get('initialized')}")
        print(f"   Graph files: {stats.get('graph_files', 'N/A')}")
    except Exception as e:
        print(f"   ❌ Failed to get stats: {e}")

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)

    return True

if __name__ == "__main__":
    asyncio.run(test_json_database())
