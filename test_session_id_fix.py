#!/usr/bin/env python3
"""Quick test for Task #42805: Verify session_id in text-chat/stream SSE events."""

import sys
import os

# Add this at the top to ensure httpx is available
try:
    import httpx
except ImportError:
    print("Installing httpx...")
    os.system("pip install httpx")
    import httpx

import asyncio
import json


API_URL = "http://localhost:8000"
# Use the anon key from .env
API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InRhamt6Ymxxd3d2dXVkcGVzaHp6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjM2NDM4NDAsImV4cCI6MjA3OTIxOTg0MH0.6oSCNyONX8HcCuki_BOiitdgkkNRc_RkTqnKBvz3L2E"


async def test_streaming():
    """Test that session_id is present in SSE events."""
    print("\n" + "="*70)
    print("TESTING: /text-chat/stream session_id in SSE events")
    print("="*70)

    events = {}

    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream(
            "POST",
            f"{API_URL}/text-chat/stream",
            json={"message": "What is staking?"},
            headers={"Authorization": f"Bearer {API_KEY}"},
        ) as response:

            if response.status_code != 200:
                print(f"✗ Request failed: {response.status_code}")
                print(f"  Response: {await response.aread()}")
                return False

            print(f"✓ Connection established (status {response.status_code})")

            buffer = ""
            current_event = None
            current_data = []

            async for chunk in response.aiter_bytes():
                buffer += chunk.decode("utf-8")

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)

                    if line.startswith("event:"):
                        # Flush previous event
                        if current_event and current_data:
                            data = "\n".join(current_data)

                            # Parse and store relevant events
                            if current_event in ["meta", "reply_done", "audio_url"]:
                                try:
                                    payload = json.loads(data)
                                    events[current_event] = payload

                                    session_id = payload.get("session_id")
                                    if session_id:
                                        print(f"✓ Event '{current_event}' has session_id: {session_id}")
                                    else:
                                        print(f"✗ Event '{current_event}' MISSING session_id")
                                        print(f"  Payload keys: {list(payload.keys())}")

                                except json.JSONDecodeError as e:
                                    print(f"✗ Failed to parse '{current_event}': {e}")

                        # Start new event
                        current_event = line.split(":", 1)[1].strip()
                        current_data = []

                    elif line.startswith("data:"):
                        data_content = line.split(":", 1)[1].strip()
                        current_data.append(data_content)

    print("\n" + "-"*70)
    print("VERIFICATION RESULTS:")
    print("-"*70)

    success = True

    # Check meta event
    if "meta" not in events:
        print("✗ FAIL: 'meta' event not received")
        success = False
    elif not events["meta"].get("session_id"):
        print("✗ FAIL: 'meta' event missing session_id")
        success = False
    else:
        print(f"✓ PASS: 'meta' event has session_id")

    # Check reply_done event
    if "reply_done" not in events:
        print("✗ FAIL: 'reply_done' event not received")
        success = False
    elif not events["reply_done"].get("session_id"):
        print("✗ FAIL: 'reply_done' event missing session_id")
        success = False
    else:
        print(f"✓ PASS: 'reply_done' event has session_id")

    # Check audio_url event
    if "audio_url" not in events:
        print("✗ FAIL: 'audio_url' event not received")
        success = False
    elif not events["audio_url"].get("session_id"):
        print("✗ FAIL: 'audio_url' event missing session_id")
        success = False
    else:
        print(f"✓ PASS: 'audio_url' event has session_id")

    # Check all session_ids match
    if all(events.get(e, {}).get("session_id") for e in ["meta", "reply_done", "audio_url"]):
        meta_sid = events["meta"]["session_id"]
        reply_sid = events["reply_done"]["session_id"]
        audio_sid = events["audio_url"]["session_id"]

        if meta_sid == reply_sid == audio_sid:
            print(f"✓ PASS: All session_ids match")
            print(f"  session_id: {meta_sid}")
        else:
            print(f"✗ FAIL: session_ids don't match")
            print(f"  meta:       {meta_sid}")
            print(f"  reply_done: {reply_sid}")
            print(f"  audio_url:  {audio_sid}")
            success = False

    print("="*70)
    return success


async def test_non_streaming():
    """Test that session_id is present in non-streaming response."""
    print("\n" + "="*70)
    print("TESTING: /text-chat session_id in response")
    print("="*70)

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{API_URL}/text-chat",
            json={"message": "What is DeFi?"},
            headers={"Authorization": f"Bearer {API_KEY}"},
        )

        if response.status_code != 200:
            print(f"✗ Request failed: {response.status_code}")
            print(f"  Response: {response.text[:200]}")
            return False

        data = response.json()
        session_id = data.get("session_id")

        if session_id:
            print(f"✓ PASS: Response has session_id: {session_id}")
            return True
        else:
            print(f"✗ FAIL: Response missing session_id")
            print(f"  Response keys: {list(data.keys())}")
            return False


async def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("TASK #42805: Text Chat session_id Validation")
    print("="*70)

    results = {}

    try:
        results["non_streaming"] = await test_non_streaming()
    except Exception as e:
        print(f"✗ Non-streaming test failed: {e}")
        import traceback
        traceback.print_exc()
        results["non_streaming"] = False

    try:
        results["streaming"] = await test_streaming()
    except Exception as e:
        print(f"✗ Streaming test failed: {e}")
        import traceback
        traceback.print_exc()
        results["streaming"] = False

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY:")
    print("="*70)

    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status} - {test_name}")

    all_passed = all(results.values())

    print("="*70)
    if all_passed:
        print("✓✓✓ ALL TESTS PASSED ✓✓✓")
        print("="*70 + "\n")
        sys.exit(0)
    else:
        print("✗✗✗ SOME TESTS FAILED ✗✗✗")
        print("="*70 + "\n")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
