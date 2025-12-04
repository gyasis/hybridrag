#!/usr/bin/env python3
"""
Full System Test - Automated
============================
Test the complete system automatically.
"""

import os
import sys
import time
import signal
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from config.config import load_config
from src.process_manager import ProcessManager

def test_full_system():
    print("🧪 Full HybridRAG System Test")
    print("=" * 50)
    
    # Use sample data folder
    test_folder = Path("./data").resolve()
    print(f"✅ Using test folder: {test_folder}")
    
    if not test_folder.exists():
        print(f"❌ Test folder doesn't exist")
        return False
    
    # Setup
    config = load_config()
    process_manager = ProcessManager()
    
    def signal_handler(signum, frame):
        print(f"\n🛑 Signal {signum} received")
        process_manager.shutdown()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        print("\n🔧 Starting processes...")
        
        # Start watcher
        process_manager.start_watcher_process([str(test_folder)], recursive=True)
        print("✅ Folder watcher started")
        
        # Start ingestion
        process_manager.start_ingestion_process(config)
        print("✅ Ingestion worker started")
        
        # Wait for startup
        time.sleep(3)
        
        # Check status
        status = process_manager.get_system_status()
        print(f"\n📊 Process Status:")
        for name, proc_info in status['processes'].items():
            print(f"  {name}: {proc_info['status']} (PID: {proc_info['pid']})")
        
        # Monitor for 20 seconds
        print(f"\n📈 Monitoring for 20 seconds...")
        
        for i in range(20):
            status = process_manager.get_system_status()
            shared = status['shared_state']
            queues = status['queue_sizes']
            
            # Check for progress
            progress = process_manager.get_ingestion_progress()
            if progress and progress.total_files > 0:
                print(f"📊 Progress: {progress.processed_files}/{progress.total_files} files | Current: {progress.current_file}")
            
            print(f"⏱️  {20-i}s | Found: {shared.get('total_files_found', 0)} | Processed: {shared.get('total_files_processed', 0)} | Queued: {queues.get('watcher_to_ingestion', 0)}")
            
            time.sleep(1)
        
        # Final results
        print(f"\n📊 Final Results:")
        final_status = process_manager.get_system_status()
        shared = final_status['shared_state']
        queues = final_status['queue_sizes']
        
        print(f"  Files found: {shared.get('total_files_found', 0)}")
        print(f"  Files processed: {shared.get('total_files_processed', 0)}")
        print(f"  LightRAG ready: {shared.get('lightrag_ready', False)}")
        print(f"  Files queued: {queues.get('watcher_to_ingestion', 0)}")
        
        # Test if LightRAG database was created
        lightrag_db = Path("./lightrag_db")
        if lightrag_db.exists():
            db_files = list(lightrag_db.glob("*.json"))
            print(f"  LightRAG files: {len(db_files)}")
            if db_files:
                print("  ✅ LightRAG database created successfully!")
                return True
        
        print("  ⚠️  LightRAG database not found")
        return False
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False
    finally:
        print("\n🔄 Shutting down...")
        process_manager.shutdown()
        print("👋 Test complete!")

if __name__ == "__main__":
    success = test_full_system()
    if success:
        print("\n🎉 SUCCESS: HybridRAG system is working!")
        print("\n💡 Next steps:")
        print("   1. Run: python simple_main.py")
        print("   2. Choose your folder to watch") 
        print("   3. Ask questions about your documents!")
    else:
        print("\n⚠️  Some issues detected - check logs above")
    
    sys.exit(0 if success else 1)