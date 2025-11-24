"""Helpers for working with raw PCM16 audio buffers."""

from __future__ import annotations

import array
import struct


def wav_header_pcm16(
    num_samples: int,
    sample_rate: int = 16000,
    num_channels: int = 1,
) -> bytes:
    """Build a minimal WAV header for PCM16 audio."""

    byte_rate = sample_rate * num_channels * 2
    block_align = num_channels * 2
    data_size = num_samples * 2
    riff_chunk_size = 36 + data_size
    return b"".join(
        [
            b"RIFF",
            struct.pack("<I", riff_chunk_size),
            b"WAVE",
            b"fmt ",
            struct.pack(
                "<IHHIIHH",
                16,
                1,
                num_channels,
                sample_rate,
                byte_rate,
                block_align,
                16,
            ),
            b"data",
            struct.pack("<I", data_size),
        ]
    )


def avg_abs_pcm16(buf: bytes) -> float:
    """Return the average absolute amplitude of a PCM16 buffer."""

    if not buf:
        return 0.0

    samples = array.array("h")
    samples.frombytes(buf[: len(buf) - (len(buf) % 2)])
    if not samples:
        return 0.0
    return sum(abs(value) for value in samples) / len(samples)

def pcm16_to_wav(
    pcm_bytes: bytes, *, sample_rate: int = 48000, channels: int = 1
) -> bytes:
    """Wrap raw PCM16 bytes with a minimal WAV header so browsers can play each chunk."""
    import struct

    data_size = len(pcm_bytes)
    byte_rate = sample_rate * channels * 2
    block_align = channels * 2
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        channels,
        sample_rate,
        byte_rate,
        block_align,
        16,
        b"data",
        data_size,
    )
    return header + pcm_bytes