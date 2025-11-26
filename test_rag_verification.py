#!/usr/bin/env python3
"""
RAG System Verification Test Script
This script verifies that the RAG system is properly enabled and working.
"""

import sys
import os

# Add the project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load environment variables from .env file BEFORE importing rag_system
from dotenv import load_dotenv
load_dotenv()

# Verify the environment variable is set
print(f"DEBUG: ENABLE_LOCAL_RAG from env = {os.getenv('ENABLE_LOCAL_RAG')}")

from app.services.rag import rag_system

def print_separator():
    print("\n" + "="*70 + "\n")

def test_rag_enabled():
    """Test if RAG system is enabled"""
    print("🔍 TEST 1: RAG System Enabled Status")
    print("-" * 70)
    print(f"RAG Enabled: {rag_system.enabled}")
    print(f"Model Loaded: {rag_system.model is not None}")
    print(f"Total FAQs: {len(rag_system.faqs)}")
    print(f"Similarity Threshold: {rag_system.similarity_threshold}")
    
    if rag_system.enabled and rag_system.model is not None:
        print("\n✅ RAG IS ENABLED AND WORKING!")
        return True
    else:
        print("\n❌ RAG IS NOT WORKING")
        if not rag_system.enabled:
            print("   Reason: RAG is disabled")
        if rag_system.model is None:
            print("   Reason: Model failed to load")
        return False

def test_rag_query_defi():
    """Test RAG query for 'What is DeFi?'"""
    print_separator()
    print("🔍 TEST 2: Query 'What is DeFi?'")
    print("-" * 70)
    
    query = "What is DeFi?"
    result = rag_system.get_context_for_llm(query)
    
    if result:
        print(f"✅ RAG RETURNED CONTEXT ({len(result)} characters)")
        print("\nContext Preview:")
        print(result[:300] + "..." if len(result) > 300 else result)
        return True
    else:
        print("❌ RAG RETURNED EMPTY CONTEXT")
        return False

def test_rag_query_staking():
    """Test RAG query for 'What is staking?'"""
    print_separator()
    print("🔍 TEST 3: Query 'What is staking?'")
    print("-" * 70)
    
    query = "What is staking?"
    results = rag_system.query_faqs(query, top_k=2)
    
    if results:
        print(f"✅ FOUND {len(results)} MATCHING FAQ(s)")
        for i, result in enumerate(results, 1):
            print(f"\n   Match {i}:")
            print(f"   Question: {result.question}")
            print(f"   Similarity: {result.similarity_score:.4f}")
            print(f"   Category: {result.category}")
            print(f"   Answer: {result.answer[:100]}...")
        return True
    else:
        print("❌ NO MATCHING FAQs FOUND")
        return False

def test_rag_query_risks():
    """Test RAG query for DeFi risks"""
    print_separator()
    print("🔍 TEST 4: Query 'What are the risks of DeFi?'")
    print("-" * 70)
    
    query = "What are the risks of DeFi?"
    context = rag_system.get_context_for_llm(query)
    
    if context:
        print(f"✅ RAG CONTEXT RETRIEVED ({len(context)} characters)")
        print("\nContext:")
        print(context)
        return True
    else:
        print("❌ NO CONTEXT RETRIEVED")
        return False

def test_embeddings():
    """Test if embeddings are created for FAQs"""
    print_separator()
    print("🔍 TEST 5: FAQ Embeddings Check")
    print("-" * 70)
    
    embedded_count = sum(1 for faq in rag_system.faqs if faq.embedding is not None)
    print(f"Total FAQs: {len(rag_system.faqs)}")
    print(f"FAQs with embeddings: {embedded_count}")
    
    if embedded_count > 0:
        print(f"\n✅ {embedded_count} FAQs HAVE EMBEDDINGS")
        # Show sample FAQ
        sample_faq = next((faq for faq in rag_system.faqs if faq.embedding), None)
        if sample_faq:
            print(f"\nSample FAQ:")
            print(f"  ID: {sample_faq.id}")
            print(f"  Question: {sample_faq.question}")
            print(f"  Embedding dimensions: {len(sample_faq.embedding)}")
        return True
    else:
        print("\n❌ NO EMBEDDINGS CREATED")
        return False

def main():
    print("="*70)
    print("RAG SYSTEM VERIFICATION TEST")
    print("="*70)
    
    results = {
        "RAG Enabled": test_rag_enabled(),
        "Query 'What is DeFi?'": test_rag_query_defi(),
        "Query 'What is staking?'": test_rag_query_staking(),
        "Query 'DeFi risks'": test_rag_query_risks(),
        "FAQ Embeddings": test_embeddings()
    }
    
    print_separator()
    print("📊 TEST SUMMARY")
    print("-" * 70)
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    all_passed = all(results.values())
    print_separator()
    
    if all_passed:
        print("🎉 ALL TESTS PASSED! RAG SYSTEM IS FULLY OPERATIONAL!")
        print("\n📝 Next Steps:")
        print("   1. Restart your Sophia server: python main.py")
        print("   2. Test with real queries about DeFi")
        print("   3. Check logs for: 'RAG context retrieved: X characters'")
        return 0
    else:
        print("⚠️  SOME TESTS FAILED. PLEASE CHECK THE ERRORS ABOVE.")
        return 1

if __name__ == "__main__":
    exit(main())
