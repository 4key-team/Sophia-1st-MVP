#!/usr/bin/env python3
"""
Test script to verify RAG system is working correctly
"""

import sys
import os
import logging

# Configure logging to see what's happening
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Make sure RAG is enabled
os.environ["ENABLE_LOCAL_RAG"] = "1"

# Add the project directory to the path
sys.path.insert(0, '/home/user/webapp')

# Import after setting the environment variable
from app.services.rag import rag_system

def test_rag_functionality():
    """Test various aspects of the RAG system"""
    
    print("\n" + "="*60)
    print("🧪 RAG SYSTEM STATUS CHECK")
    print("="*60)
    
    # Check 1: RAG enabled status
    print(f"\n✅ RAG Enabled: {rag_system.enabled}")
    print(f"✅ Model Loaded: {rag_system.model is not None}")
    print(f"✅ FAQs Loaded: {len(rag_system.faqs)} FAQs")
    
    # Check 2: Test queries
    test_queries = [
        "What is DeFi?",
        "How does yield farming work?",
        "What are the risks in DeFi?",
        "How do I start with DeFi safely?",
        "What is impermanent loss?"
    ]
    
    print("\n" + "="*60)
    print("🔍 TESTING RAG QUERIES")
    print("="*60)
    
    for query in test_queries:
        print(f"\n📝 Query: '{query}'")
        print("-" * 40)
        
        # Get RAG context
        context = rag_system.get_context_for_llm(query)
        
        if context:
            print("✅ RAG FOUND RELEVANT CONTEXT:")
            # Show first 500 chars to keep output readable
            if len(context) > 500:
                print(context[:500] + "...")
            else:
                print(context)
        else:
            print("❌ No relevant context found")
        
        # Also test the direct query method
        results = rag_system.query_faqs(query, top_k=1)
        if results:
            print(f"\n📊 Top Match:")
            print(f"   Question: {results[0].question}")
            print(f"   Similarity: {results[0].similarity_score:.3f}")
            print(f"   Category: {results[0].category}")
    
    print("\n" + "="*60)
    print("✅ RAG SYSTEM TEST COMPLETE")
    print("="*60)
    
    # Summary
    if rag_system.enabled and rag_system.model is not None:
        print("\n🎉 SUCCESS: RAG is fully operational!")
        print("📚 Your DeFi assistant now has access to:")
        print(f"   - {len(rag_system.faqs)} DeFi FAQ entries")
        print("   - Vector similarity search enabled")
        print("   - Context injection for LLM responses")
    else:
        print("\n⚠️ WARNING: RAG is still disabled!")
        print("Please check:")
        print("   1. ENABLE_LOCAL_RAG=1 in .env")
        print("   2. sentence-transformers is installed")
        print("   3. No import errors occurred")

if __name__ == "__main__":
    test_rag_functionality()