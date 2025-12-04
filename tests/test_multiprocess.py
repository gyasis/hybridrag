#!/usr/bin/env python3
"""
Multiprocess HybridRAG Test Script
=================================
Test the multiprocess version of HybridRAG.
"""

import os
import sys
import time
import asyncio
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from config.config import load_config
from src.process_manager import ProcessManager
from src.lightrag_core import create_lightrag_core

def test_environment_setup():
    """Test environment setup."""
    print("🔧 Testing Environment Setup")
    print("=" * 40)
    
    success = True
    
    # Check API key
    if os.getenv("OPENAI_API_KEY"):
        print("✅ OPENAI_API_KEY found")
    else:
        print("❌ OPENAI_API_KEY missing")
        success = False
    
    # Check sample data
    data_dir = Path("./data")
    sample_files = list(data_dir.glob("*.md")) + list(data_dir.glob("*.txt"))
    if sample_files:
        print(f"✅ Found {len(sample_files)} sample files")
        for file_path in sample_files:
            print(f"    📄 {file_path.name}")
    else:
        print("⚠️  No sample files found - creating test file")
        # Create a simple test file
        data_dir.mkdir(exist_ok=True)
        test_file = data_dir / "test_document.txt"
        test_file.write_text("""
Test Document for HybridRAG

This is a test document to verify that the HybridRAG system can properly ingest and search documents.

Key topics covered:
- Document ingestion
- Text processing  
- Search functionality
- Multi-process architecture

The system should be able to find this content when searching for terms like "test", "document", or "HybridRAG".
        """.strip())
        print(f"✅ Created test file: {test_file}")
    
    return success

def test_process_manager():
    """Test process manager functionality."""
    print("\n🔄 Testing Process Manager")
    print("=" * 40)
    
    try:
        # Load config
        config = load_config()
        print("✅ Configuration loaded")
        
        # Create process manager
        manager = ProcessManager()
        print("✅ Process manager created")
        
        # Test starting processes
        watch_folders = ["./data"]
        print(f"✅ Watch folders: {watch_folders}")
        
        # Start watcher process
        manager.start_watcher_process(watch_folders, recursive=True)
        print("✅ Watcher process started")
        
        # Start ingestion process  
        manager.start_ingestion_process(config)
        print("✅ Ingestion process started")
        
        # Wait a moment for processes to initialize
        print("⏳ Waiting for processes to initialize...")
        time.sleep(5)
        
        # Check status
        status = manager.get_system_status()
        print("\n📊 Process Status:")
        for name, proc_info in status['processes'].items():
            print(f"  {name}: {proc_info['status']} (PID: {proc_info['pid']})")
        
        # Let it run for a bit to test file detection and ingestion
        print("\n⏳ Running for 15 seconds to test ingestion...")
        
        for i in range(15):
            time.sleep(1)
            
            # Check for progress updates
            progress = manager.get_ingestion_progress()
            if progress:
                print(f"\r📊 Progress: {progress.processed_files}/{progress.total_files} files", end="", flush=True)
            else:
                print(f"\r⏳ Waiting... {15-i}s", end="", flush=True)
        
        print("\n")
        
        # Final status check
        final_status = manager.get_system_status()
        shared_state = final_status['shared_state']
        
        print("📈 Final Results:")
        print(f"  Files found: {shared_state.get('total_files_found', 0)}")
        print(f"  Files processed: {shared_state.get('total_files_processed', 0)}")
        print(f"  Ingestion active: {shared_state.get('ingestion_active', False)}")
        
        # Shutdown
        print("\n🛑 Shutting down processes...")
        manager.shutdown()
        print("✅ Process manager test completed")
        
        return True
        
    except Exception as e:
        print(f"❌ Process manager test failed: {e}")
        return False

def test_search_functionality():
    """Test search functionality."""
    print("\n🔍 Testing Search Functionality")
    print("=" * 40)
    
    try:
        # Load config and create LightRAG core
        config = load_config()
        lightrag_core = create_lightrag_core(config)
        
        print("✅ LightRAG core created")
        
        # Test health check
        health = asyncio.run(lightrag_core.health_check())
        print(f"✅ Health check: {health['status']}")
        
        # Test simple query
        test_queries = [
            "What is this document about?",
            "test document",
            "HybridRAG system"
        ]
        
        print("\n🧪 Testing queries:")
        for query in test_queries:
            try:
                result = asyncio.run(lightrag_core.aquery(query, mode="hybrid"))
                if result.error:
                    print(f"⚠️  Query '{query}': {result.error}")
                else:
                    print(f"✅ Query '{query}': {len(result.result)} chars response")
            except Exception as e:
                print(f"❌ Query '{query}' failed: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ Search functionality test failed: {e}")
        return False

def main():
    """Main test function."""
    print("🧪 HybridRAG Multiprocess Test Suite")
    print("=" * 50)
    
    tests = [
        ("Environment Setup", test_environment_setup),
        ("Process Manager", test_process_manager), 
        ("Search Functionality", test_search_functionality)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n🎯 Running: {test_name}")
        try:
            result = test_func()
            results.append((test_name, result))
            if result:
                print(f"✅ {test_name}: PASSED")
            else:
                print(f"❌ {test_name}: FAILED")
        except Exception as e:
            print(f"❌ {test_name}: ERROR - {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n📊 Test Summary")
    print("=" * 30)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name:20} {status}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Multiprocess HybridRAG is ready.")
        print("\n💡 Next steps:")
        print("   1. Copy .env.example to .env and add your OpenAI API key")
        print("   2. Run: python main_multiprocess.py")
        print("   3. Choose folders to watch when prompted")
        print("   4. Start asking questions!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} tests failed. Please check the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())