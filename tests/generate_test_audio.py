"""Generate test audio files for prosody testing."""

import numpy as np
import wave
import io


def generate_test_wav(
    duration_seconds: float = 2.0,
    sample_rate: int = 16000,
    frequency: int = 200,
    amplitude: float = 0.5,
    pitch_trend: str = "flat"
) -> bytes:
    """
    Generate a test WAV file with specific characteristics.

    Args:
        duration_seconds: Length of audio in seconds
        sample_rate: Sample rate in Hz
        frequency: Base frequency in Hz
        amplitude: Amplitude (0.0-1.0)
        pitch_trend: "flat", "rising", or "falling"

    Returns:
        WAV file as bytes
    """
    num_samples = int(duration_seconds * sample_rate)
    t = np.linspace(0, duration_seconds, num_samples)

    # Generate frequency trajectory based on pitch trend
    if pitch_trend == "rising":
        freq = frequency + (t / duration_seconds) * 100  # Rise 100Hz
    elif pitch_trend == "falling":
        freq = frequency - (t / duration_seconds) * 100  # Fall 100Hz
    else:  # flat
        freq = frequency

    # Generate sine wave
    audio = amplitude * np.sin(2 * np.pi * freq * t)

    # Convert to 16-bit PCM
    audio_int16 = (audio * 32767).astype(np.int16)

    # Write to WAV bytes
    wav_io = io.BytesIO()
    with wave.open(wav_io, 'wb') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_int16.tobytes())

    return wav_io.getvalue()


if __name__ == "__main__":
    # Generate test files
    print("Generating test audio files...")

    # Low intensity, slow pace, flat pitch
    low_slow_flat = generate_test_wav(
        duration_seconds=3.0,
        amplitude=0.2,
        pitch_trend="flat"
    )
    print(f"✓ Low/slow/flat: {len(low_slow_flat)} bytes")

    # High intensity, fast pace, rising pitch
    high_fast_rising = generate_test_wav(
        duration_seconds=1.0,
        amplitude=0.8,
        pitch_trend="rising"
    )
    print(f"✓ High/fast/rising: {len(high_fast_rising)} bytes")

    # Medium intensity, normal pace, falling pitch
    medium_normal_falling = generate_test_wav(
        duration_seconds=2.0,
        amplitude=0.5,
        pitch_trend="falling"
    )
    print(f"✓ Medium/normal/falling: {len(medium_normal_falling)} bytes")

    print("\nTest audio generation complete!")
