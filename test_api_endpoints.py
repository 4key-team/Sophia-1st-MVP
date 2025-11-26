#!/usr/bin/env python3
"""
Test script for Sophia API endpoints with correct Bearer authentication
"""

import requests

# Configuration
BASE_URL = "http://localhost:8000"
API_KEY = "dev-key"  # Use your dev-key


def test_api_endpoints():
    """Test all API endpoints with proper Bearer authentication"""
    headers = {"Authorization": f"Bearer {API_KEY}"}

    print("Testing Sophia API Endpoints")
    print(f"Base URL: {BASE_URL}")
    print(f"API Key: {API_KEY}")
    print("-" * 50)

    # Test 1: Health check (no auth required)
    print("\n1. Testing /health (no auth)")
    try:
        response = requests.get(f"{BASE_URL}/health")
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            print(f"Response: {response.json()}")
            print("PASS")
        else:
            print("FAIL")
    except Exception as e:
        print(f"Error: {e}")

    # Test 2: Root endpoint (no auth required)
    print("\n2. Testing / (no auth)")
    try:
        response = requests.get(f"{BASE_URL}/")
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            print(f"Response: {response.json()}")
            print("PASS")
        else:
            print("FAIL")
    except Exception as e:
        print(f"Error: {e}")

    # Test 3: Generate response (requires auth)
    print("\n3. Testing /generate-response (with auth)")
    try:
        payload = {"text": "What is DeFi and how does it work?"}
        response = requests.post(
            f"{BASE_URL}/generate-response", json=payload, headers=headers
        )
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Reply: {data.get('reply', 'N/A')}")
            print("PASS")
        else:
            print(f"Error: {response.text}")
            print("FAIL")
    except Exception as e:
        print(f"Error: {e}")

    # Test 4: Text chat with DeFi question (requires auth)
    print("\n4. Testing /text-chat with DeFi question")
    try:
        payload = {"message": "What is yield farming in DeFi?"}
        response = requests.post(f"{BASE_URL}/text-chat", json=payload, headers=headers)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Session ID: {data.get('session_id', 'N/A')}")
            print(f"Transcript: {data.get('transcript', 'N/A')}")
            print(f"Reply: {data.get('reply', 'N/A')[:100]}...")
            print(f"Intent: {data.get('intent', 'N/A')}")
            print("PASS")
            return data.get("session_id")
        else:
            print(f"Error: {response.text}")
            print("FAIL")
    except Exception as e:
        print(f"Error: {e}")

    return None


def test_defi_scenarios(session_id=None):
    """Test various DeFi conversation scenarios"""
    headers = {"Authorization": f"Bearer {API_KEY}"}

    print("\n" + "=" * 50)
    print("DEFI CONVERSATION SCENARIOS")
    print("=" * 50)

    scenarios = [
        {"message": "What are liquidity pools?", "expected_intent": "defi_question"},
        {
            "message": "I'm worried about impermanent loss",
            "expected_intent": "emotional_support",
        },
        {"message": "How's the weather today?", "expected_intent": "small_talk"},
        {
            "message": "Can you explain staking rewards?",
            "expected_intent": "defi_question",
        },
    ]

    for i, scenario in enumerate(scenarios, 1):
        print(f"\n{i}. Testing: '{scenario['message']}'")
        try:
            payload = {"message": scenario["message"], "session_id": session_id}
            response = requests.post(
                f"{BASE_URL}/text-chat", json=payload, headers=headers
            )

            if response.status_code == 200:
                data = response.json()
                intent = data.get("intent", "unknown")
                print(f"   Intent detected: {intent}")
                print(f"   Expected: {scenario['expected_intent']}")

                if intent == scenario["expected_intent"]:
                    print("   Intent classification: PASS")
                else:
                    print("   Intent classification: FAIL")

                print(f"   Reply: {data.get('reply', 'N/A')[:80]}...")
                session_id = data.get("session_id")  # Update session for continuity
            else:
                print(f"   API Error: {response.text}")

        except Exception as e:
            print(f"   Error: {e}")


def check_server():
    """Check if server is running"""
    try:
        response = requests.get(f"{BASE_URL}/", timeout=3)
        return response.status_code == 200
    except Exception:
        return False


if __name__ == "__main__":
    print("Sophia API Test Script")
    print("=" * 30)

    # Check if server is running
    if not check_server():
        print("ERROR: Server is not running!")
        print("Start the server first with: python main.py")
        exit(1)

    print("Server is running, proceeding with tests...")

    # Run API endpoint tests
    session_id = test_api_endpoints()

    # Run DeFi scenario tests
    test_defi_scenarios(session_id)

    print("\n" + "=" * 50)
    print("TESTING COMPLETED")
    print("=" * 50)
    print("Check the output above for any FAIL results")
