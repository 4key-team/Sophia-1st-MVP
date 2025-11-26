"""Prosody snapshot and context formatting utilities for voice analysis."""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ProsodySnapshot:
    """Voice prosody characteristics captured during speech analysis.

    Attributes:
        intensity: Voice intensity level - "low", "medium", or "high"
        pitch_movement: Pitch pattern - "rising", "falling", or "flat"
        pace: Speaking rate - "slow", "normal", or "fast"
    """
    intensity: Optional[str] = None  # "low" / "medium" / "high"
    pitch_movement: Optional[str] = None  # "rising" / "falling" / "flat"
    pace: Optional[str] = None  # "slow" / "normal" / "fast"


def format_prosody_context(prosody: Optional[ProsodySnapshot]) -> str:
    """Format prosody snapshot into a human-readable context string.

    Args:
        prosody: ProsodySnapshot instance or None

    Returns:
        Empty string if prosody is None, otherwise formatted string like:
        "User prosody: intensity=high, pitch=rising, pace=fast"

    Examples:
        >>> prosody = ProsodySnapshot(intensity="high", pitch_movement="rising", pace="fast")
        >>> format_prosody_context(prosody)
        'User prosody: intensity=high, pitch=rising, pace=fast'

        >>> format_prosody_context(None)
        ''
    """
    if prosody is None:
        return ""

    parts = []
    if prosody.intensity is not None:
        parts.append(f"intensity={prosody.intensity}")
    if prosody.pitch_movement is not None:
        parts.append(f"pitch={prosody.pitch_movement}")
    if prosody.pace is not None:
        parts.append(f"pace={prosody.pace}")

    if not parts:
        return ""

    return f"User prosody: {', '.join(parts)}"


def extract_prosody_from_audio(audio_bytes: bytes) -> Optional[ProsodySnapshot]:
    """
    Extract prosody characteristics from audio data using real audio analysis.

    Uses librosa for acoustic feature extraction:
    - Intensity: RMS (Root Mean Square) energy analysis
    - Pitch movement: Fundamental frequency (F0) trajectory analysis
    - Pace: Speech rate estimation from onset detection

    Args:
        audio_bytes: Raw audio data in bytes (WAV format preferred)

    Returns:
        ProsodySnapshot with real prosody characteristics, or None if audio is invalid

    Example:
        >>> with open("speech.wav", "rb") as f:
        ...     audio = f.read()
        >>> prosody = extract_prosody_from_audio(audio)
        >>> prosody.intensity
        'high'
    """
    try:
        import io
        import numpy as np
        import librosa
        import soundfile as sf

        # Guard against empty or invalid audio
        if not audio_bytes or len(audio_bytes) < 1024:
            logger.debug("Audio too short for prosody extraction")
            return None

        # Load audio from bytes
        audio_io = io.BytesIO(audio_bytes)
        try:
            # Try to load as audio file (WAV, MP3, etc.)
            y, sr = librosa.load(audio_io, sr=None, mono=True)
        except Exception:
            # Fallback: try as raw PCM data
            try:
                audio_io.seek(0)
                y, sr = sf.read(audio_io)
                if len(y.shape) > 1:
                    y = y[:, 0]  # Take first channel if stereo
            except Exception as e:
                logger.warning(f"Failed to load audio: {e}")
                return None

        # Validate audio
        if len(y) < sr * 0.1:  # Less than 0.1 seconds
            logger.debug("Audio too short for analysis")
            return None

        # 1. INTENSITY ANALYSIS (RMS energy)
        rms = librosa.feature.rms(y=y)[0]
        mean_rms = np.mean(rms)
        max_rms = np.max(rms)

        # Normalize and classify intensity
        # Thresholds empirically determined for speech
        if mean_rms < 0.02:
            intensity = "low"
        elif mean_rms < 0.08:
            intensity = "medium"
        else:
            intensity = "high"

        # 2. PITCH MOVEMENT ANALYSIS (F0 trajectory)
        # Use piptrack for pitch detection
        pitches, magnitudes = librosa.piptrack(y=y, sr=sr, fmin=75, fmax=600)

        # Extract pitch contour
        pitch_values = []
        for t in range(pitches.shape[1]):
            index = magnitudes[:, t].argmax()
            pitch = pitches[index, t]
            if pitch > 0:  # Valid pitch
                pitch_values.append(pitch)

        if len(pitch_values) > 10:
            # Analyze pitch trend
            first_third = np.median(pitch_values[:len(pitch_values)//3])
            last_third = np.median(pitch_values[-len(pitch_values)//3:])
            pitch_diff = last_third - first_third

            # Classify pitch movement (>5% change is significant)
            if abs(pitch_diff) < first_third * 0.05:
                pitch_movement = "flat"
            elif pitch_diff > 0:
                pitch_movement = "rising"
            else:
                pitch_movement = "falling"
        else:
            pitch_movement = "flat"  # Not enough pitch data

        # 3. PACE ANALYSIS (speech rate from onset detection)
        # Detect onset events (syllable/word boundaries)
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        onsets = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr)

        # Calculate speech rate (onsets per second)
        duration = len(y) / sr
        speech_rate = len(onsets) / duration if duration > 0 else 0

        # Classify pace based on onset rate
        # Normal speech: ~4-6 syllables/sec
        if speech_rate < 4.0:
            pace = "slow"
        elif speech_rate < 7.0:
            pace = "normal"
        else:
            pace = "fast"

        logger.info(
            f"Extracted prosody: intensity={intensity} (RMS={mean_rms:.4f}), "
            f"pitch={pitch_movement} (Δ={pitch_diff if len(pitch_values) > 10 else 0:.1f}Hz), "
            f"pace={pace} (rate={speech_rate:.2f} onsets/s)"
        )

        return ProsodySnapshot(
            intensity=intensity,
            pitch_movement=pitch_movement,
            pace=pace
        )

    except ImportError as e:
        logger.error(f"Required library not installed: {e}")
        logger.error("Install with: pip install librosa numpy soundfile")
        return None
    except Exception as e:
        logger.warning(f"Prosody extraction failed: {e}", exc_info=True)
        return None
