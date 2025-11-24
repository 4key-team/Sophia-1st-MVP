"""Utility helpers for lightweight audio analysis."""

from __future__ import annotations

import audioop
import json
from typing import Any, Dict

from fastapi import HTTPException, UploadFile

ALLOWED_AUDIO_EXTENSIONS = [
    ".wav",
    ".webm",
    ".mp3",
    ".mp4",
    ".ogg",
    ".flac",
    ".m4a",
    ".aac",
]
ALLOWED_AUDIO_CONTENT_TYPES = {
    'audio/wav',
    'audio/x-wav',
    'audio/webm',
    'audio/ogg',
    'audio/flac',
    'audio/mp4',
    'audio/aac',
}

def prosody_features(pcm_bytes: bytes) -> Dict[str, str]:
    """Return a coarse intensity classification based on PCM16 RMS."""
    try:
        if not pcm_bytes or len(pcm_bytes) < 2:
            raise ValueError("No samples")

        # audioop operates in C and is far faster than Python loops for RMS
        rms = audioop.rms(pcm_bytes, 2)
        normalized = min(rms / 32768.0, 1.0)

        if normalized < 0.1:
            intensity = "low"
        elif normalized < 0.3:
            intensity = "medium"
        else:
            intensity = "high"

        return {"intensity": intensity}
    except Exception:
        return {"intensity": "low"}

async def extract_audio(upload: UploadFile):
    payload = await upload.read()
    """Lightweight magic-byte sniffing to catch obvious non-audio uploads."""
    if not payload or len(payload) < 4:
        raise HTTPException(
            status_code=400, detail="File must contain recognizable audio data"
        )
    head = payload[:4]
    is_valid = False
    if head == b"RIFF":  # WAV/WEBP containers
        is_valid = True
    elif head[:3] == b"ID3":  # MP3 ID3 tag
        is_valid = True
    elif head == b"OggS":
        is_valid = True
    elif head == b"fLaC":
        is_valid = True
    # MPEG frame sync (11 set bits) catches many MP3/MP2 streams
    elif payload[0] == 0xFF and (payload[1] & 0xE0) == 0xE0:
        is_valid = True
    # MP4/M4A files often start with an ftyp atom at offset 4
    elif len(payload) >= 12 and payload[4:8] == b"ftyp":
        is_valid = True
    # As a last resort, treat files with enough non-zero bytes as plausible audio
    elif not is_valid and not any(b for b in payload[:512]):
        raise HTTPException(
            status_code=400, detail="File must contain recognizable audio data"
        )
    return payload

def validate_audio_upload(upload: UploadFile) -> None:
    filename = upload.filename.lower()
    content_type = upload.content_type
    if content_type not in ALLOWED_AUDIO_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                "File must be a supported audio format."
                " Supported formats: wav, webm, mp4, ogg, flac, m4a, aac"
            ),
        )
    for ext in ALLOWED_AUDIO_EXTENSIONS:
        if filename.endswith(ext):
            return
    raise HTTPException(
        status_code=400,
        detail=(
            "File must be a supported audio format."
            " Supported formats: wav, webm, mp4, ogg, flac, m4a, aac"
        ),
    )

def sse_event(event_type: str, payload: Any):
    return f"event: {event_type}\ndata: {payload if isinstance(payload, str) else json.dumps(payload)}\n\n"