"""
audio_utils.py
--------------
PCM audio helpers for capturing microphone input and playing back
Gemini's spoken responses within the Streamlit app.
"""

from __future__ import annotations

import io
import wave


# Gemini Live API expects 16-bit signed PCM, mono, 16 kHz
SAMPLE_RATE = 16_000
CHANNELS = 1
SAMPLE_WIDTH = 2  # bytes (16-bit)


def pcm_to_wav_bytes(pcm_data: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Wrap raw PCM bytes in a WAV container so browsers can play it."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)
    return buf.getvalue()


def wav_bytes_to_pcm(wav_data: bytes) -> bytes:
    """Strip WAV header and return raw PCM payload."""
    buf = io.BytesIO(wav_data)
    with wave.open(buf, "rb") as wf:
        return wf.readframes(wf.getnframes())


def chunk_pcm(pcm_data: bytes, chunk_ms: int = 100) -> list[bytes]:
    """
    Split PCM into fixed-length chunks.
    chunk_ms: duration of each chunk in milliseconds.
    """
    bytes_per_chunk = int(SAMPLE_RATE * SAMPLE_WIDTH * CHANNELS * chunk_ms / 1000)
    return [
        pcm_data[i : i + bytes_per_chunk]
        for i in range(0, len(pcm_data), bytes_per_chunk)
    ]
