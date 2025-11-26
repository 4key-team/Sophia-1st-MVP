"""Smoke test for API-key authentication responses."""

import requests

# Test authentication
headers = {"Authorization": "Bearer dev-key"}

print("Testing authentication with Bearer dev-key")

# Test generate-response endpoint
try:
    response = requests.post(
        "http://localhost:8000/generate-response",
        json={"text": "Hello, what is DeFi?"},
        headers=headers,
        timeout=30,
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        print("SUCCESS: Authentication working!")
        data = response.json()
        print(f"Reply: {data.get('reply', 'No reply')}")
    else:
        print(f"FAIL: {response.text}")
except Exception as e:
    print(f"Error: {e}")

# Test text-chat endpoint
print("\nTesting text-chat endpoint...")
try:
    response = requests.post(
        "http://localhost:8000/text-chat",
        json={"message": "What is yield farming?"},
        headers=headers,
        timeout=30,
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        print("SUCCESS: Text chat working!")
        data = response.json()
        print(f"Intent: {data.get('intent', 'No intent')}")
        print(f"Reply: {data.get('reply', 'No reply')}")
    else:
        print(f"FAIL: {response.text}")
except Exception as e:
    print(f"Error: {e}")
