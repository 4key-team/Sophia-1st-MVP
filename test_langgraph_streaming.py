#!/usr/bin/env python3
"""
Test script for LangChain agent with Voxtral streaming integration
"""

import os
import sys
import logging
from pathlib import Path

# Add the app directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.langgraph_service import langgraph_service

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_test_wav_audio():
    """Create a simple test WAV audio file for testing"""
    import numpy as np

    # Generate a simple sine wave (440 Hz for 2 seconds)
    sample_rate = 16000
    duration = 2.0
    frequency = 440.0

    t = np.linspace(0, duration, int(sample_rate * duration), False)
    audio_data = np.sin(2 * np.pi * frequency * t) * 0.3

    # Convert to 16-bit PCM
    audio_data = (audio_data * 32767).astype(np.int16)

    # Create WAV header + data
    wav_header = b"RIFF" + (36 + len(audio_data) * 2).to_bytes(4, "little") + b"WAVE"
    wav_header += b"fmt " + (16).to_bytes(4, "little")  # fmt chunk size
    wav_header += (1).to_bytes(2, "little")  # PCM format
    wav_header += (1).to_bytes(2, "little")  # mono
    wav_header += sample_rate.to_bytes(4, "little")  # sample rate
    wav_header += (sample_rate * 2).to_bytes(4, "little")  # byte rate
    wav_header += (2).to_bytes(2, "little")  # block align
    wav_header += (16).to_bytes(2, "little")  # bits per sample
    wav_header += b"data" + (len(audio_data) * 2).to_bytes(4, "little")

    return wav_header + audio_data.tobytes()


def test_langgraph_streaming():
    """Test the LangChain agent streaming functionality"""
    logger.info("Testing LangChain agent with Voxtral streaming...")

    try:
        # Create test audio
        test_audio = create_test_wav_audio()
        logger.info(f"Created test audio: {len(test_audio)} bytes")

        # Test streaming response
        logger.info("Testing streaming response...")
        tokens_received = []

        for token in langgraph_service.stream_conversation_response(
            test_audio, "test_session_123"
        ):
            tokens_received.append(token)
            print(f"Token: '{token}'", end="", flush=True)

            # Limit output for testing
            if len(tokens_received) > 20:
                print("\n[Truncated after 20 tokens for testing]")
                break

        print("\n\nStreaming test completed!")
        print(f"Total tokens received: {len(tokens_received)}")
        print(f"Full response: {''.join(tokens_received)}")

        if tokens_received:
            logger.info("✅ LangChain agent streaming test PASSED")
            return True
        else:
            logger.error(
                "❌ LangChain agent streaming test FAILED - No tokens received"
            )
            return False

    except Exception as e:
        logger.error(f"❌ LangChain agent streaming test FAILED with error: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_langgraph_regular():
    """Test the regular LangChain agent functionality"""
    logger.info("Testing regular LangChain agent...")

    try:
        # Create test audio
        test_audio = create_test_wav_audio()

        # Test regular processing
        result = langgraph_service.process_conversation(test_audio, "test_session_456")

        logger.info(f"Regular processing result keys: {list(result.keys())}")
        logger.info(f"Transcript: {result.get('transcript', 'N/A')}")
        logger.info(f"Reply: {result.get('reply', 'N/A')}")
        logger.info(f"Intent: {result.get('intent', 'N/A')}")

        if result.get("reply"):
            logger.info("✅ Regular LangChain agent test PASSED")
            return True
        else:
            logger.error("❌ Regular LangChain agent test FAILED - No reply generated")
            return False

    except Exception as e:
        logger.error(f"❌ Regular LangChain agent test FAILED with error: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("Testing LangChain Agent with Voxtral Streaming Integration")
    print("=" * 60)

    # Check environment variables
    required_vars = ["MISTRAL_API_KEY", "INWORLD_API_KEY"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        print(f"⚠️  Warning: Missing environment variables: {missing_vars}")
        print("Some tests may fail without proper API keys")

    print("\n1. Testing LangChain agent streaming...")
    streaming_success = test_langgraph_streaming()

    print("\n2. Testing regular LangChain agent...")
    regular_success = test_langgraph_regular()

    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Streaming test: {'✅ PASSED' if streaming_success else '❌ FAILED'}")
    print(f"Regular test: {'✅ PASSED' if regular_success else '❌ FAILED'}")

    if streaming_success and regular_success:
        print(
            "\n🎉 All tests PASSED! LangChain agent integration is working correctly."
        )
        sys.exit(0)
    else:
        print("\n❌ Some tests FAILED. Please check the logs above for details.")
        sys.exit(1)
