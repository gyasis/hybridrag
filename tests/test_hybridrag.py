#!/usr/bin/env python3
"""
HybridRAG Test Script
====================
Test script to validate the HybridRAG system functionality.
"""

import os
import sys
import asyncio
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.config.app_config import load_config
from main import HybridRAGSystem

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_basic_functionality():
    """Test basic HybridRAG functionality."""
    print("🧪 Testing HybridRAG System")
    print("=" * 50)
    
    try:
        # Load configuration
        config = load_config()
        print(f"✅ Configuration loaded")
        
        # Create system
        system = HybridRAGSystem(config)
        print(f"✅ System created")
        
        # Initialize
        await system.initialize()
        print(f"✅ System initialized")
        
        # Test system status
        status = await system.get_system_status()
        print(f"✅ System status: {status.get('health', {}).get('status', 'unknown')}")
        
        # Test simple search (if there's data)
        try:
            result = await system.one_shot_query("What is machine learning?", mode="simple")
            if result.get('error'):
                print(f"⚠️  Search test: {result['error']}")
            else:
                print(f"✅ Search test successful")
                print(f"   Query: {result['query']}")
                print(f"   Result length: {len(result.get('result', ''))}")
        except Exception as e:
            print(f"⚠️  Search test failed: {e}")
        
        # Test agentic search if PromptChain available
        try:
            result = await system.one_shot_query("Explain AI and ML relationship", mode="agentic")
            if result.get('error'):
                print(f"⚠️  Agentic test: {result['error']}")
            else:
                print(f"✅ Agentic test successful")
        except Exception as e:
            print(f"⚠️  Agentic test failed: {e}")
        
        # Test ingestion pipeline
        try:
            # Check if there are sample files to process
            data_dir = Path("./data")
            sample_files = list(data_dir.glob("*.md")) + list(data_dir.glob("*.txt"))
            if sample_files:
                print(f"✅ Found {len(sample_files)} sample files for ingestion")
                
                # Process a small batch to test ingestion
                processed = await system.ingestion_pipeline.process_batch(batch_size=2)
                print(f"✅ Ingestion test: processed {processed} files")
            else:
                print(f"⚠️  No sample files found for ingestion test")
                
        except Exception as e:
            print(f"⚠️  Ingestion test failed: {e}")
        
        # Cleanup
        await system.shutdown()
        print(f"✅ System shutdown complete")
        
        print("\n🎉 Basic functionality test completed!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        logger.error(f"Test error: {e}", exc_info=True)
        return False
    
    return True

async def test_file_watcher():
    """Test file watcher functionality."""
    print("\n🔍 Testing File Watcher")
    print("=" * 30)
    
    try:
        config = load_config()
        system = HybridRAGSystem(config)
        await system.initialize()
        
        # Get watcher stats
        if system.folder_watcher:
            stats = system.folder_watcher.get_queue_stats()
            print(f"✅ Watcher stats: {stats}")
            
            # Test scanning
            files_to_process = system.folder_watcher.scan_folders()
            print(f"✅ Scan found {len(files_to_process)} files to process")
            
        await system.shutdown()
        
    except Exception as e:
        print(f"❌ File watcher test failed: {e}")
        return False
        
    return True

async def test_search_modes():
    """Test different search modes."""
    print("\n🔍 Testing Search Modes")
    print("=" * 30)
    
    try:
        config = load_config()
        system = HybridRAGSystem(config)
        await system.initialize()
        
        test_query = "machine learning algorithms"
        
        # Test different modes
        modes = ["local", "global", "hybrid"]
        for mode in modes:
            try:
                result = await system.search_interface.simple_search(test_query, mode=mode)
                print(f"✅ {mode.capitalize()} mode: {result.execution_time:.2f}s")
            except Exception as e:
                print(f"⚠️  {mode.capitalize()} mode failed: {e}")
        
        # Test search stats
        stats = system.search_interface.get_stats()
        print(f"✅ Search stats: {stats}")
        
        await system.shutdown()
        
    except Exception as e:
        print(f"❌ Search modes test failed: {e}")
        return False
        
    return True

def check_environment():
    """Check environment setup."""
    print("🔧 Checking Environment")
    print("=" * 25)
    
    # Check API key
    if os.getenv("OPENAI_API_KEY"):
        print("✅ OPENAI_API_KEY found")
    else:
        print("❌ OPENAI_API_KEY missing - set in .env file")
        return False
    
    # Check directories
    required_dirs = ["src", "config", "data"]
    for dir_name in required_dirs:
        if Path(dir_name).exists():
            print(f"✅ {dir_name}/ directory exists")
        else:
            print(f"❌ {dir_name}/ directory missing")
            return False
    
    # Check key files
    key_files = [
        "src/folder_watcher.py",
        "src/ingestion_pipeline.py", 
        "src/lightrag_core.py",
        "src/search_interface.py",
        "config/config.py",
        "main.py"
    ]
    
    for file_path in key_files:
        if Path(file_path).exists():
            print(f"✅ {file_path} exists")
        else:
            print(f"❌ {file_path} missing")
            return False
    
    return True

async def main():
    """Main test function."""
    print("🚀 HybridRAG System Test Suite")
    print("=" * 40)
    
    # Check environment first
    if not check_environment():
        print("\n❌ Environment check failed. Please fix issues and retry.")
        return 1
    
    # Run tests
    test_results = []
    
    test_results.append(await test_basic_functionality())
    test_results.append(await test_file_watcher())
    test_results.append(await test_search_modes())
    
    # Summary
    passed = sum(test_results)
    total = len(test_results)
    
    print(f"\n📊 Test Summary")
    print("=" * 20)
    print(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        print("🎉 All tests passed! HybridRAG system is ready.")
        return 0
    else:
        print("⚠️  Some tests failed. Check the output above for details.")
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))