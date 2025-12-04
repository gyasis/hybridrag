#!/usr/bin/env python3
"""
Simple test to verify the LightRAG + DeepLake integration is working
"""
import asyncio
import os
from lightrag import LightRAG, QueryParam
from lightrag.llm.openai import openai_complete_if_cache, openai_embed
from lightrag.utils import EmbeddingFunc
from dotenv import load_dotenv

load_dotenv()

async def test_lightrag():
    """Test LightRAG directly with a simple query."""
    print("🔍 Testing LightRAG Direct Query")
    print("=" * 40)
    
    # Initialize LightRAG
    api_key = os.getenv("OPENAI_API_KEY")
    
    rag = LightRAG(
        working_dir="./athena_lightrag_db",
        llm_model_func=lambda prompt, system_prompt=None, history_messages=[], **kwargs: 
            openai_complete_if_cache(
                "gpt-4o-mini",
                prompt,
                system_prompt=system_prompt,
                history_messages=history_messages,
                api_key=api_key,
                **kwargs
            ),
        embedding_func=EmbeddingFunc(
            embedding_dim=1536,
            func=lambda texts: openai_embed(
                texts,
                model="text-embedding-ada-002",
                api_key=api_key
            ),
        ),
    )
    
    # Initialize storages
    await rag.initialize_storages()
    
    # Test query - focused on available data
    query_text = "What are the key relationships between appointment tables, payment tables, and provider tables in the ATHENAONE system? How are they connected through foreign keys or IDs? Show me the table structure and relationships."
    print(f"Query: {query_text}")
    print("-" * 40)
    
    try:
        # Simple query with basic parameters
        query_param = QueryParam(mode="hybrid")
        result = await rag.aquery(query_text, param=query_param)
        
        if result:
            print("✅ Query successful!")
            print("Result:")
            print(result)
        else:
            print("❌ No result returned")
            
    except Exception as e:
        print(f"❌ Query error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_lightrag())