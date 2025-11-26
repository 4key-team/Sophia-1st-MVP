#!/usr/bin/env python3
"""
Test the RAG integration in the running API
"""

import requests
import json
import base64
import time

API_URL = "http://localhost:8000"

def test_health():
    """Test if the API is running"""
    try:
        response = requests.get(f"{API_URL}/health")
        if response.status_code == 200:
            print("✅ API is running and healthy")
            print(f"   Response: {response.json()}")
            return True
    except Exception as e:
        print(f"❌ API health check failed: {e}")
    return False

def test_rag_context():
    """Test if RAG context is being added to responses"""
    
    # Create test questions that should trigger RAG
    test_questions = [
        "What is DeFi?",
        "How does yield farming work?", 
        "What are the risks of DeFi?",
        "What is impermanent loss?"
    ]
    
    print("\n" + "="*60)
    print("🔍 TESTING RAG CONTEXT IN API RESPONSES")
    print("="*60)
    
    for question in test_questions:
        print(f"\n📝 Testing: '{question}'")
        print("-" * 40)
        
        # Create a simple text query (simulating voice transcription)
        payload = {
            "session_id": f"test_{int(time.time())}",
            "transcript": question,
            "user_emotion": {"label": "neutral", "confidence": 0.9}
        }
        
        try:
            # Call the text processing endpoint
            response = requests.post(
                f"{API_URL}/api/process_text",
                json=payload,
                headers={"Authorization": "Bearer dev-key"}
            )
            
            if response.status_code == 200:
                result = response.json()
                llm_response = result.get("llm_response", "")
                
                # Check if the response contains DeFi-specific information
                if any(keyword in llm_response.lower() for keyword in ["defi", "decentralized", "finance", "protocol", "liquidity", "yield", "impermanent"]):
                    print("✅ Response contains DeFi-specific information")
                    print(f"   Response preview: {llm_response[:200]}...")
                else:
                    print("⚠️ Response might not be using RAG context")
                    print(f"   Response preview: {llm_response[:200]}...")
            else:
                print(f"❌ API call failed with status {response.status_code}")
                print(f"   Error: {response.text}")
                
        except Exception as e:
            print(f"❌ API call error: {e}")

def check_rag_status():
    """Check RAG status through a debug endpoint if available"""
    try:
        # Try to get system info
        response = requests.get(
            f"{API_URL}/api/system_info",
            headers={"Authorization": "Bearer dev-key"}
        )
        
        if response.status_code == 200:
            info = response.json()
            print("\n" + "="*60)
            print("📊 SYSTEM INFORMATION")
            print("="*60)
            print(json.dumps(info, indent=2))
            
            # Check for RAG status in the response
            if "rag_enabled" in info:
                if info["rag_enabled"]:
                    print("\n✅ RAG is ENABLED in the system")
                else:
                    print("\n❌ RAG is DISABLED in the system")
    except:
        pass  # This endpoint might not exist

def main():
    print("\n" + "="*60)
    print("🧪 SOPHIA RAG INTEGRATION TEST")
    print("="*60)
    
    # Test if API is running
    if not test_health():
        print("\n❌ API is not running. Please start the server first.")
        return
    
    # Check RAG status
    check_rag_status()
    
    # Test RAG context in responses
    test_rag_context()
    
    print("\n" + "="*60)
    print("✅ RAG INTEGRATION TEST COMPLETE")
    print("="*60)
    print("\n🎯 Next Steps:")
    print("1. If RAG responses look generic, check server logs")
    print("2. Ensure ENABLE_LOCAL_RAG=1 is set when starting the server")
    print("3. Monitor the quality of responses for DeFi questions")

if __name__ == "__main__":
    main()