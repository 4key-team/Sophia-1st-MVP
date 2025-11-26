"""Unit tests for ProsodySnapshot and format_prosody_context."""

from app.emotion import (
    ProsodySnapshot,
    format_prosody_context,
    extract_prosody_from_audio,
)


def test_prosody_snapshot_creation():
    """Test creating ProsodySnapshot with all fields."""
    prosody = ProsodySnapshot(
        intensity="high",
        pitch_movement="rising",
        pace="fast"
    )
    assert prosody.intensity == "high"
    assert prosody.pitch_movement == "rising"
    assert prosody.pace == "fast"


def test_prosody_snapshot_partial():
    """Test creating ProsodySnapshot with partial fields."""
    prosody = ProsodySnapshot(intensity="low")
    assert prosody.intensity == "low"
    assert prosody.pitch_movement is None
    assert prosody.pace is None


def test_prosody_snapshot_empty():
    """Test creating empty ProsodySnapshot."""
    prosody = ProsodySnapshot()
    assert prosody.intensity is None
    assert prosody.pitch_movement is None
    assert prosody.pace is None


def test_format_prosody_context_none():
    """Test format_prosody_context with None input."""
    result = format_prosody_context(None)
    assert result == ""


def test_format_prosody_context_full():
    """Test format_prosody_context with full ProsodySnapshot."""
    prosody = ProsodySnapshot(
        intensity="high",
        pitch_movement="rising",
        pace="fast"
    )
    result = format_prosody_context(prosody)
    assert result == "User prosody: intensity=high, pitch=rising, pace=fast"


def test_format_prosody_context_partial_intensity():
    """Test format_prosody_context with only intensity."""
    prosody = ProsodySnapshot(intensity="medium")
    result = format_prosody_context(prosody)
    assert result == "User prosody: intensity=medium"


def test_format_prosody_context_partial_pitch():
    """Test format_prosody_context with only pitch_movement."""
    prosody = ProsodySnapshot(pitch_movement="falling")
    result = format_prosody_context(prosody)
    assert result == "User prosody: pitch=falling"


def test_format_prosody_context_partial_pace():
    """Test format_prosody_context with only pace."""
    prosody = ProsodySnapshot(pace="slow")
    result = format_prosody_context(prosody)
    assert result == "User prosody: pace=slow"


def test_format_prosody_context_two_fields():
    """Test format_prosody_context with two fields."""
    prosody = ProsodySnapshot(intensity="low", pace="slow")
    result = format_prosody_context(prosody)
    assert result == "User prosody: intensity=low, pace=slow"


def test_format_prosody_context_empty_snapshot():
    """Test format_prosody_context with empty ProsodySnapshot."""
    prosody = ProsodySnapshot()
    result = format_prosody_context(prosody)
    assert result == ""


def test_format_prosody_context_all_combinations():
    """Test various combinations of prosody characteristics."""
    test_cases = [
        # (intensity, pitch_movement, pace, expected)
        ("low", "falling", "slow", "User prosody: intensity=low, pitch=falling, pace=slow"),
        ("medium", "flat", "normal", "User prosody: intensity=medium, pitch=flat, pace=normal"),
        ("high", "rising", "fast", "User prosody: intensity=high, pitch=rising, pace=fast"),
        (None, "rising", "fast", "User prosody: pitch=rising, pace=fast"),
        ("high", None, "fast", "User prosody: intensity=high, pace=fast"),
        ("high", "rising", None, "User prosody: intensity=high, pitch=rising"),
    ]

    for intensity, pitch, pace, expected in test_cases:
        prosody = ProsodySnapshot(
            intensity=intensity,
            pitch_movement=pitch,
            pace=pace
        )
        result = format_prosody_context(prosody)
        assert result == expected, f"Failed for {intensity}, {pitch}, {pace}"


def test_extract_prosody_from_audio_small_file():
    """Test prosody extraction from small audio file."""
    # Small audio (< 50000 bytes) should give low intensity, fast pace
    audio = b"x" * 10000
    prosody = extract_prosody_from_audio(audio)
    assert prosody is not None
    assert prosody.intensity == "low"
    assert prosody.pace == "fast"
    assert prosody.pitch_movement in ["flat", "rising", "falling"]


def test_extract_prosody_from_audio_medium_file():
    """Test prosody extraction from medium audio file."""
    # Medium audio (50000-150000 bytes) should give medium intensity, normal pace
    audio = b"x" * 80000
    prosody = extract_prosody_from_audio(audio)
    assert prosody is not None
    assert prosody.intensity == "medium"
    assert prosody.pace == "normal"
    assert prosody.pitch_movement in ["flat", "rising", "falling"]


def test_extract_prosody_from_audio_large_file():
    """Test prosody extraction from large audio file."""
    # Large audio (> 150000 bytes) should give high intensity, slow pace
    audio = b"x" * 200000
    prosody = extract_prosody_from_audio(audio)
    assert prosody is not None
    assert prosody.intensity == "high"
    assert prosody.pace == "slow"
    assert prosody.pitch_movement in ["flat", "rising", "falling"]


def test_extract_prosody_from_audio_empty():
    """Test prosody extraction from empty audio."""
    prosody = extract_prosody_from_audio(b"")
    assert prosody is None


def test_extract_prosody_from_audio_too_short():
    """Test prosody extraction from too short audio."""
    audio = b"x" * 100  # Less than 1024 bytes
    prosody = extract_prosody_from_audio(audio)
    assert prosody is None


def test_extract_prosody_from_audio_realistic():
    """Test prosody extraction with realistic audio size."""
    # Realistic audio file size (e.g., 5 seconds of 16kHz mono PCM = ~160KB)
    audio = b"x" * 160000
    prosody = extract_prosody_from_audio(audio)
    assert prosody is not None
    assert prosody.intensity is not None
    assert prosody.pitch_movement is not None
    assert prosody.pace is not None
