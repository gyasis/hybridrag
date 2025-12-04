#!/usr/bin/env python3
"""
Test script to demonstrate LightRAG query functionality
"""
import asyncio
from lightrag_query_demo import LightRAGQueryInterface

async def test_query():
    """Test the LightRAG query system with a simple query."""
    print("🔍 Testing LightRAG Query System")
    print("=" * 50)
    
    try:
        # Initialize the query interface
        interface = LightRAGQueryInterface(working_dir="./athena_lightrag_db")
        
        # Test query
        test_query = "What medical tables are available in the database?"
        print(f"Query: {test_query}")
        print("-" * 50)
        
        # Execute the query
        result = await interface.query(test_query, mode="hybrid")
        
        if result:
            print("✅ Query successful!")
            print("Result:")
            print(result)
        else:
            print("❌ Query failed - no results returned")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_query())