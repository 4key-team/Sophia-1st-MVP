#!/usr/bin/env python3
"""
Simple test runner for Sophia API
Run with: python run_tests.py
"""

import subprocess
import sys
import time
import requests


def check_server_running():
    """Check if the server is already running"""
    try:
        response = requests.get("http://localhost:8000/", timeout=2)
        return response.status_code == 200
    except Exception:
        return False


def start_server():
    """Start the server in background"""
    print("🚀 Starting Sophia server...")
    process = subprocess.Popen(
        [sys.executable, "main.py"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )

    # Wait for server to start
    for _ in range(30):  # Wait up to 30 seconds
        if check_server_running():
            print("✅ Server started successfully")
            return process
        time.sleep(1)

    print("❌ Server failed to start")
    return None


def run_tests():
    """Run the test suite"""
    print("🧪 Running test suite...")
    result = subprocess.run(
        [sys.executable, "test_sophia_api.py"], capture_output=False, text=True
    )
    return result.returncode == 0


def main():
    print("🤖 Sophia API Test Runner")
    print("=" * 40)

    # Check if server is running
    server_process = None
    if check_server_running():
        print("✅ Server is already running")
    else:
        server_process = start_server()
        if not server_process:
            print("❌ Cannot start server, exiting")
            return

    try:
        # Run tests
        success = run_tests()

        if success:
            print("\n🎉 All tests completed!")
        else:
            print("\n⚠️  Some tests failed")

    finally:
        # Clean up
        if server_process:
            print("\n🛑 Stopping server...")
            server_process.terminate()
            server_process.wait()


if __name__ == "__main__":
    main()
