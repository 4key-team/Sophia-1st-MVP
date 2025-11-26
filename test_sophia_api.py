#!/usr/bin/env python3
"""
Test script for Sophia AI Backend API with DeFi Agent
Tests all endpoints including the new LangGraph-powered DeFi chat functionality
"""

import requests
import time
import os
import wave
import numpy as np
from io import BytesIO

# Configuration
BASE_URL = "http://localhost:8000"
ACCESS_TOKEN_ENV = "SUPABASE_ACCESS_TOKEN"


class SophiaAPITester:
    def __init__(self, base_url: str = BASE_URL, auth_token: str | None = None):
        self.base_url = base_url
        token = auth_token or os.getenv(ACCESS_TOKEN_ENV)
        if not token:
            raise ValueError(
                f"Missing Supabase access token. Provide a JWT via the '{ACCESS_TOKEN_ENV}' environment variable "
                "or pass an explicit auth_token to SophiaAPITester."
            )
        self.headers = {"Authorization": f"Bearer {token}"}
        self.session_id = None

    def create_test_audio(
        self, text: str = "Hello Sophia, what is DeFi?", duration: float = 2.0
    ) -> bytes:
        """Create a simple test WAV file"""
        sample_rate = 16000
        t = np.linspace(0, duration, int(sample_rate * duration), False)
        # Create a simple sine wave tone
        tone = np.sin(2 * np.pi * 440 * t) * 0.3
        # Convert to 16-bit PCM
        audio_data = (tone * 32767).astype(np.int16)

        # Create WAV file in memory
        buffer = BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)  # mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio_data.tobytes())

        return buffer.getvalue()

    def test_health_check(self):
        """Test health check endpoint"""
        print("\n🔍 Testing /health endpoint...")
        try:
            response = requests.get(f"{self.base_url}/health")
            print(f"Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"Response: {data}")
                print("PASS Health check passed")
                return True
            else:
                print("FAIL Health check failed")
                return False
        except Exception as e:
            print(f"FAIL Health check error: {e}")
            return False

    def test_root_endpoint(self):
        """Test root endpoint"""
        print("\n🔍 Testing / endpoint...")
        try:
            response = requests.get(f"{self.base_url}/")
            print(f"Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"Response: {data}")
                print("✅ Root endpoint passed")
                return True
            else:
                print("❌ Root endpoint failed")
                return False
        except Exception as e:
            print(f"❌ Root endpoint error: {e}")
            return False

    def test_transcribe_endpoint(self):
        """Test transcription endpoint"""
        print("\n🔍 Testing /transcribe endpoint...")
        try:
            audio_data = self.create_test_audio("Test transcription")
            files = {"file": ("test.wav", audio_data, "audio/wav")}

            response = requests.post(
                f"{self.base_url}/transcribe", files=files, headers=self.headers
            )

            print(f"Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"Transcript: {data.get('text', 'N/A')}")
                print(f"Emotion: {data.get('emotion', {})}")
                print("✅ Transcribe endpoint passed")
                return True
            else:
                print(f"❌ Transcribe endpoint failed: {response.text}")
                return False
        except Exception as e:
            print(f"❌ Transcribe endpoint error: {e}")
            return False

    def test_generate_response_endpoint(self):
        """Test response generation endpoint"""
        print("\n🔍 Testing /generate-response endpoint...")
        try:
            payload = {"text": "What is yield farming in DeFi?"}

            response = requests.post(
                f"{self.base_url}/generate-response", json=payload, headers=self.headers
            )

            print(f"Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"Reply: {data.get('reply', 'N/A')}")
                print(f"Tone: {data.get('tone', 'N/A')}")
                print("✅ Generate response endpoint passed")
                return True
            else:
                print(f"❌ Generate response endpoint failed: {response.text}")
                return False
        except Exception as e:
            print(f"❌ Generate response endpoint error: {e}")
            return False

    def test_synthesize_endpoint(self):
        """Test synthesis endpoint"""
        print("\n🔍 Testing /synthesize endpoint...")
        try:
            payload = {"text": "Hello! Welcome to DeFi learning with Sophia."}

            response = requests.post(
                f"{self.base_url}/synthesize", json=payload, headers=self.headers
            )

            print(f"Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"Audio URL: {data.get('audio_url', 'N/A')}")
                print(f"Emotion: {data.get('emotion', {})}")
                print("✅ Synthesize endpoint passed")
                return True
            else:
                print(f"❌ Synthesize endpoint failed: {response.text}")
                return False
        except Exception as e:
            print(f"❌ Synthesize endpoint error: {e}")
            return False

    def test_chat_endpoint(self):
        """Test basic chat endpoint"""
        print("\n🔍 Testing /chat endpoint...")
        try:
            audio_data = self.create_test_audio("Hi Sophia, how are you?")
            files = {"file": ("test_chat.wav", audio_data, "audio/wav")}

            response = requests.post(
                f"{self.base_url}/chat", files=files, headers=self.headers
            )

            print(f"Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"Transcript: {data.get('transcript', 'N/A')}")
                print(f"Reply: {data.get('reply', 'N/A')}")
                print(f"User Emotion: {data.get('user_emotion', {})}")
                print(f"Sophia Emotion: {data.get('sophia_emotion', {})}")
                print(f"Audio URL: {data.get('audio_url', 'N/A')}")
                print("✅ Chat endpoint passed")
                return True
            else:
                print(f"❌ Chat endpoint failed: {response.text}")
                return False
        except Exception as e:
            print(f"❌ Chat endpoint error: {e}")
            return False

    def test_defi_chat_endpoint(self):
        """Test DeFi chat endpoint with LangGraph"""
        print("\n🔍 Testing /defi-chat endpoint...")
        try:
            # Test with DeFi-related question
            audio_data = self.create_test_audio(
                "What is liquidity farming and how does it work?"
            )
            files = {"file": ("defi_test.wav", audio_data, "audio/wav")}

            response = requests.post(
                f"{self.base_url}/defi-chat", files=files, headers=self.headers
            )

            print(f"Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                self.session_id = data.get("session_id")  # Store for session test
                print(f"Session ID: {data.get('session_id', 'N/A')}")
                print(f"Transcript: {data.get('transcript', 'N/A')}")
                print(f"Reply: {data.get('reply', 'N/A')}")
                print(f"Intent: {data.get('intent', 'N/A')}")
                print(f"User Emotion: {data.get('user_emotion', {})}")
                print(f"Sophia Emotion: {data.get('sophia_emotion', {})}")
                print(f"Audio URL: {data.get('audio_url', 'N/A')}")
                print(f"Context Memory: {data.get('context_memory', {})}")
                print(f"Fallbacks Used: {data.get('fallbacks_used', {})}")
                print(
                    f"Evaluation Logs: {len(data.get('evaluation_logs', []))} entries"
                )
                print("✅ DeFi chat endpoint passed")
                return True
            else:
                print(f"❌ DeFi chat endpoint failed: {response.text}")
                return False
        except Exception as e:
            print(f"❌ DeFi chat endpoint error: {e}")
            return False

    def test_text_chat_endpoint(self):
        """Test text-only chat endpoint"""
        print("\n🔍 Testing /text-chat endpoint...")
        try:
            payload = {
                "message": "Can you explain what an automated market maker is?",
                "session_id": self.session_id,  # Use same session if available
            }

            response = requests.post(
                f"{self.base_url}/text-chat", json=payload, headers=self.headers
            )

            print(f"Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"Session ID: {data.get('session_id', 'N/A')}")
                print(f"Transcript: {data.get('transcript', 'N/A')}")
                print(f"Reply: {data.get('reply', 'N/A')}")
                print(f"Intent: {data.get('intent', 'N/A')}")
                print(f"User Emotion: {data.get('user_emotion', {})}")
                print(f"Sophia Emotion: {data.get('sophia_emotion', {})}")
                print(f"Audio URL: {data.get('audio_url', 'N/A')}")
                print("✅ Text chat endpoint passed")
                return True
            else:
                print(f"❌ Text chat endpoint failed: {response.text}")
                return False
        except Exception as e:
            print(f"❌ Text chat endpoint error: {e}")
            return False

    def test_session_memory_endpoint(self):
        """Test session memory retrieval"""
        print("\n🔍 Testing /sessions/{session_id} endpoint...")
        if not self.session_id:
            print("⚠️  No session ID available, skipping test")
            return True

        try:
            response = requests.get(
                f"{self.base_url}/sessions/{self.session_id}", headers=self.headers
            )

            print(f"Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"Session ID: {data.get('session_id', 'N/A')}")
                print(f"Context: {data.get('context', {})}")
                print("✅ Session memory endpoint passed")
                return True
            else:
                print(f"❌ Session memory endpoint failed: {response.text}")
                return False
        except Exception as e:
            print(f"❌ Session memory endpoint error: {e}")
            return False

    def test_server_availability(self):
        """Test if server is running"""
        print("\n🔍 Testing server availability...")
        try:
            response = requests.get(f"{self.base_url}/", timeout=5)
            if response.status_code == 200:
                print("✅ Server is running")
                return True
            else:
                print(f"❌ Server responded with status {response.status_code}")
                return False
        except requests.exceptions.ConnectionError:
            print("❌ Server is not running or not accessible")
            return False
        except Exception as e:
            print(f"❌ Server availability error: {e}")
            return False

    def run_all_tests(self):
        """Run all test cases"""
        print("Starting Sophia API Test Suite")
        print(f"Testing server at: {self.base_url}")
        print(
            f"Using API Key: {'***' + self.headers['Authorization'].split(' ')[1][-4:] if self.headers.get('Authorization') else 'None'}"
        )

        tests = [
            ("Server Availability", self.test_server_availability),
            ("Root Endpoint", self.test_root_endpoint),
            ("Health Check", self.test_health_check),
            ("Transcribe", self.test_transcribe_endpoint),
            ("Generate Response", self.test_generate_response_endpoint),
            ("Synthesize", self.test_synthesize_endpoint),
            ("Basic Chat", self.test_chat_endpoint),
            ("DeFi Chat (LangGraph)", self.test_defi_chat_endpoint),
            ("Text Chat", self.test_text_chat_endpoint),
            ("Session Memory", self.test_session_memory_endpoint),
        ]

        results = {}
        passed = 0
        total = len(tests)

        for test_name, test_func in tests:
            print(f"\n{'=' * 60}")
            print(f"Running: {test_name}")
            print("=" * 60)

            start_time = time.time()
            try:
                success = test_func()
                duration = time.time() - start_time
                results[test_name] = {"passed": success, "duration": duration}
                if success:
                    passed += 1
                    print(f"⏱️  Duration: {duration:.2f}s")
            except Exception as e:
                print(f"❌ Test '{test_name}' crashed: {e}")
                results[test_name] = {
                    "passed": False,
                    "duration": time.time() - start_time,
                    "error": str(e),
                }

        # Summary
        print(f"\n{'=' * 60}")
        print("📊 TEST SUMMARY")
        print("=" * 60)
        print(f"Passed: {passed}/{total}")
        print(f"Success Rate: {(passed / total) * 100:.1f}%")

        for test_name, result in results.items():
            status = "✅ PASS" if result["passed"] else "❌ FAIL"
            duration = result["duration"]
            error_info = (
                f" - {result.get('error', '')}"
                if not result["passed"] and "error" in result
                else ""
            )
            print(f"{status} {test_name} ({duration:.2f}s){error_info}")

        return results


class DeFiTestScenarios:
    """Test specific DeFi conversation scenarios"""

    def __init__(self, tester: SophiaAPITester):
        self.tester = tester

    def test_defi_questions(self):
        """Test various DeFi-related questions"""
        defi_questions = [
            "What is yield farming?",
            "How do liquidity pools work?",
            "What's the difference between APY and APR?",
            "Can you explain impermanent loss?",
            "What are the risks of DeFi protocols?",
        ]

        print("\n🏦 Testing DeFi Question Scenarios")
        print("=" * 50)

        for i, question in enumerate(defi_questions, 1):
            print(f"\n{i}. Testing: '{question}'")

            try:
                payload = {"message": question, "session_id": self.tester.session_id}
                response = requests.post(
                    f"{self.tester.base_url}/text-chat",
                    json=payload,
                    headers=self.tester.headers,
                )

                if response.status_code == 200:
                    data = response.json()
                    print(f"   Intent: {data.get('intent', 'N/A')}")
                    print(f"   Reply: {data.get('reply', 'N/A')[:100]}...")
                    print("   ✅ Success")
                else:
                    print(f"   ❌ Failed: {response.status_code}")

            except Exception as e:
                print(f"   ❌ Error: {e}")

    def test_emotional_scenarios(self):
        """Test emotional support scenarios"""
        emotional_questions = [
            "I'm worried about losing money in DeFi",
            "I'm confused about all these protocols",
            "I'm excited to start investing",
            "Help me understand this better",
        ]

        print("\n💝 Testing Emotional Support Scenarios")
        print("=" * 50)

        for i, question in enumerate(emotional_questions, 1):
            print(f"\n{i}. Testing: '{question}'")

            try:
                payload = {"message": question, "session_id": self.tester.session_id}
                response = requests.post(
                    f"{self.tester.base_url}/text-chat",
                    json=payload,
                    headers=self.tester.headers,
                )

                if response.status_code == 200:
                    data = response.json()
                    print(f"   Intent: {data.get('intent', 'N/A')}")
                    print(f"   Reply: {data.get('reply', 'N/A')[:100]}...")
                    print("   ✅ Success")
                else:
                    print(f"   ❌ Failed: {response.status_code}")

            except Exception as e:
                print(f"   ❌ Error: {e}")


def main():
    """Run the complete test suite"""
    print("Sophia AI Backend Test Suite")
    print("=" * 60)

    # Initialize tester
    tester = SophiaAPITester()

    # Run core API tests
    results = tester.run_all_tests()

    # Run DeFi-specific scenario tests
    if any(r["passed"] for r in results.values()):
        defi_tester = DeFiTestScenarios(tester)
        defi_tester.test_defi_questions()
        defi_tester.test_emotional_scenarios()
    else:
        print("\n⚠️  Skipping DeFi scenarios due to core test failures")

    print("\n🎉 Testing completed!")

    # Check if server needs to be started
    if not results.get("Server Availability", {}).get("passed", False):
        print("\n💡 Tip: Start the server with:")
        print("   python main.py")
        print("   or")
        print("   uvicorn main:app --host 0.0.0.0 --port 8000 --reload")


if __name__ == "__main__":
    main()
