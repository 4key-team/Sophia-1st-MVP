#!/usr/bin/env python3
"""
Test script to verify TTS configuration changes.
This script checks that the TTS configuration uses the correct voice and model settings.
"""


def test_tts_configuration():
    """Test that TTS configuration has been updated correctly."""

    with open("app/services/tts.py", "r") as f:
        content = f.read()

    # Test 1: Check that Deborah voice is used
    assert '"voiceId": "Deborah"' in content, (
        "Deborah voice not found in TTS configuration"
    )
    print("✅ Deborah voice configured correctly")

    # Test 2: Check that latest model is used
    assert '"modelId": "inworld-tts-1-max"' in content, (
        "Latest model inworld-tts-1-max not found"
    )
    print("✅ Latest model inworld-tts-1-max configured correctly")

    # Test 3: Check that temperature is set
    assert '"temperature": 1.1' in content, "Temperature 1.1 not found in configuration"
    print("✅ Temperature parameter configured correctly")

    # Test 4: Check that talking_speed is set
    assert '"talking_speed": 1.0' in content, (
        "Talking speed 1.0 not found in configuration"
    )
    print("✅ Talking speed parameter configured correctly")

    # Test 5: Check that old Ashley voice is not present
    assert '"voiceId": "Ashley"' not in content, (
        "Old Ashley voice still present in code"
    )
    print("✅ Old Ashley voice removed correctly")

    # Test 6: Check that old model is not present
    assert '"modelId": "inworld-tts-1",' not in content, (
        "Old model inworld-tts-1 still present"
    )
    print("✅ Old model removed correctly")

    # Test 7: Check logging messages updated
    assert "Deborah voice and inworld-tts-1-max model" in content, (
        "Log messages not updated"
    )
    print("✅ Log messages updated correctly")

    print("\n🎉 All TTS configuration tests passed!")
    print("📝 Changes summary:")
    print("  - Voice changed from Ashley → Deborah")
    print("  - Model updated from inworld-tts-1 → inworld-tts-1-max")
    print("  - Added temperature: 1.1 for enhanced voice quality")
    print("  - Added talking_speed: 1.0 for normal speaking pace")
    print("  - Updated log messages to reflect new configuration")


if __name__ == "__main__":
    test_tts_configuration()
