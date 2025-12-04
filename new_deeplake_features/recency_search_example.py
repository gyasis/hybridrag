#!/usr/bin/env python3
"""
Example script demonstrating recency-based vector search in DeepLake v4.

This script shows how to use the enhanced CustomDeepLake class with recency weighting
to prioritize recent results in vector search without explicit timestamps.
"""

import sys
import os
sys.path.append('docs')  # Add docs directory to path to import customdeeplake_v4

from customdeeplake_v4 import CustomDeepLake

def demonstrate_recency_search():
    """Demonstrate different recency weighting approaches."""
    
    # Initialize the database
    db_path = input("Enter path to your DeepLake dataset: ").strip()
    if not db_path:
        print("No path provided. Exiting.")
        return
    
    try:
        db = CustomDeepLake(db_path)
        print(f"\n✅ Successfully loaded dataset with {len(db.ds)} records")
        
        # Get a search query from user
        query = input("\nEnter your search query: ").strip()
        if not query:
            print("No query provided. Exiting.")
            return
        
        print(f"\n🔍 Searching for: '{query}'")
        print("=" * 60)
        
        # Test different recency weights
        weights = [0.0, 0.2, 0.5, 0.8]
        weight_names = ["Pure Similarity", "Light Recency", "Balanced", "Recency-Focused"]
        
        for weight, name in zip(weights, weight_names):
            print(f"\n📊 {name} (weight={weight}):")
            print("-" * 40)
            
            try:
                results = db.search(
                    query=query,
                    n_results=3,
                    recency_weight=weight
                )
                
                for i, result in enumerate(results, 1):
                    print(f"{i}. ID: {result['id'][:8]}...")
                    print(f"   Text: {result['text'][:100]}...")
                    
                    # Show scores if available
                    if weight > 0.0 and 'combined_score' in result:
                        print(f"   Combined Score: {result['combined_score']:.4f}")
                        if 'similarity_score' in result:
                            print(f"   Similarity: {result['similarity_score']:.4f}")
                        if 'recency_score' in result:
                            print(f"   Recency: {result['recency_score']:.4f}")
                    print()
                    
            except Exception as e:
                print(f"❌ Error with weight {weight}: {e}")
        
        # Demonstrate convenience method
        print(f"\n🚀 Using convenience method (search_recent):")
        print("-" * 40)
        try:
            recent_results = db.search_recent(query, n_results=3)
            for i, result in enumerate(recent_results, 1):
                print(f"{i}. ID: {result['id'][:8]}...")
                print(f"   Text: {result['text'][:100]}...")
                if 'combined_score' in result:
                    print(f"   Combined Score: {result['combined_score']:.4f}")
                print()
        except Exception as e:
            print(f"❌ Error with search_recent: {e}")
        
        print("\n✅ Recency search demonstration complete!")
        print("\n💡 Tips:")
        print("- recency_weight=0.0: Pure similarity (existing behavior)")
        print("- recency_weight=0.3: Balanced (recommended default)")
        print("- recency_weight=0.7: Recency-focused")
        print("- Higher row numbers = more recent records")
        
    except Exception as e:
        print(f"❌ Error initializing database: {e}")

if __name__ == "__main__":
    demonstrate_recency_search()
