#!/usr/bin/env python3
"""
Test the fixed synchronous query interface
"""
import asyncio
from query_with_promptchain import create_promptchain_with_rag

async def test_query():
    """Test single query"""
    print("Creating PromptChain with LightRAG tools...")
    chain = create_promptchain_with_rag()

    test_question = "What are the main components of PromptChain?"

    print(f"\n🔍 Question: {test_question}")
    print("="*70)
    print("🤖 Processing with ReACT method...\n")

    result = await chain.process_prompt_async(test_question)

    print("\n" + "="*70)
    print("📖 Answer:")
    print("="*70)
    print(result)
    print("="*70)

if __name__ == "__main__":
    asyncio.run(test_query())
