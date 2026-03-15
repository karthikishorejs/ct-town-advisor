"""
Unit tests for src/audio_utils.py

Tests:
  1. pcm_to_wav_bytes produces valid WAV
  2. wav_bytes_to_pcm round-trips correctly
  3. pcm_to_wav_bytes with custom sample rate
  4. chunk_pcm splits into correct sizes
  5. chunk_pcm with small data
  6. chunk_pcm with exact multiple
  7. WAV header is correct
"""

import io
import struct
import sys
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.audio_utils import (
    CHANNELS,
    SAMPLE_RATE,
    SAMPLE_WIDTH,
    chunk_pcm,
    pcm_to_wav_bytes,
    wav_bytes_to_pcm,
)


# ---------------------------------------------------------------------------
# pcm_to_wav_bytes
# ---------------------------------------------------------------------------

class TestPcmToWavBytes:

    def test_returns_bytes(self):
        """Should return bytes."""
        pcm = b"\x00" * 3200  # 100ms of silence at 16kHz
        result = pcm_to_wav_bytes(pcm)
        assert isinstance(result, bytes)

    def test_starts_with_riff_header(self):
        """WAV file must start with RIFF header."""
        pcm = b"\x00" * 3200
        result = pcm_to_wav_bytes(pcm)
        assert result[:4] == b"RIFF"

    def test_contains_wave_format(self):
        """WAV file must contain WAVE format marker."""
        pcm = b"\x00" * 3200
        result = pcm_to_wav_bytes(pcm)
        assert b"WAVE" in result[:12]

    def test_valid_wav_structure(self):
        """Output should be parseable by the wave module."""
        pcm = b"\x00" * 6400  # 200ms of silence
        wav_data = pcm_to_wav_bytes(pcm)
        buf = io.BytesIO(wav_data)
        with wave.open(buf, "rb") as wf:
            assert wf.getnchannels() == CHANNELS
            assert wf.getsampwidth() == SAMPLE_WIDTH
            assert wf.getframerate() == SAMPLE_RATE
            assert wf.getnframes() == 6400 // SAMPLE_WIDTH

    def test_custom_sample_rate(self):
        """Should respect custom sample rate (e.g., 24kHz for Gemini output)."""
        pcm = b"\x00" * 4800  # 100ms at 24kHz
        wav_data = pcm_to_wav_bytes(pcm, sample_rate=24000)
        buf = io.BytesIO(wav_data)
        with wave.open(buf, "rb") as wf:
            assert wf.getframerate() == 24000

    def test_empty_pcm(self):
        """Empty PCM should produce a valid (empty) WAV file."""
        wav_data = pcm_to_wav_bytes(b"")
        buf = io.BytesIO(wav_data)
        with wave.open(buf, "rb") as wf:
            assert wf.getnframes() == 0

    def test_known_audio_data(self):
        """PCM data should be preserved exactly in the WAV payload."""
        # Create a simple sine-like pattern
        samples = [1000, 2000, 3000, -1000, -2000, -3000]
        pcm = struct.pack(f"<{len(samples)}h", *samples)
        wav_data = pcm_to_wav_bytes(pcm)
        recovered = wav_bytes_to_pcm(wav_data)
        assert recovered == pcm


# ---------------------------------------------------------------------------
# wav_bytes_to_pcm
# ---------------------------------------------------------------------------

class TestWavBytesToPcm:

    def test_round_trip(self):
        """pcm → wav → pcm should be identity."""
        original_pcm = b"\x01\x02" * 1600  # 1600 samples
        wav_data = pcm_to_wav_bytes(original_pcm)
        recovered = wav_bytes_to_pcm(wav_data)
        assert recovered == original_pcm

    def test_silence_round_trip(self):
        """Silence should survive round-trip."""
        silence = b"\x00" * 3200
        wav_data = pcm_to_wav_bytes(silence)
        recovered = wav_bytes_to_pcm(wav_data)
        assert recovered == silence

    def test_returns_bytes(self):
        """Should return bytes type."""
        pcm = b"\x00" * 100
        wav_data = pcm_to_wav_bytes(pcm)
        result = wav_bytes_to_pcm(wav_data)
        assert isinstance(result, bytes)


# ---------------------------------------------------------------------------
# chunk_pcm
# ---------------------------------------------------------------------------

class TestChunkPcm:

    def test_default_chunk_size(self):
        """Default 100ms chunks at 16kHz mono 16-bit = 3200 bytes each."""
        # 500ms of audio = 5 chunks of 100ms
        pcm = b"\x00" * 16000  # 500ms at 16kHz * 2 bytes/sample
        chunks = chunk_pcm(pcm)
        assert len(chunks) == 5
        for c in chunks:
            assert len(c) == 3200

    def test_custom_chunk_ms(self):
        """200ms chunks should be 6400 bytes each."""
        pcm = b"\x00" * 12800  # 400ms of audio
        chunks = chunk_pcm(pcm, chunk_ms=200)
        assert len(chunks) == 2
        for c in chunks:
            assert len(c) == 6400

    def test_partial_last_chunk(self):
        """When data doesn't divide evenly, last chunk is smaller."""
        pcm = b"\x00" * 5000  # Not a multiple of 3200
        chunks = chunk_pcm(pcm, chunk_ms=100)
        assert len(chunks) == 2
        assert len(chunks[0]) == 3200
        assert len(chunks[1]) == 1800

    def test_empty_pcm(self):
        """Empty PCM should return empty list."""
        chunks = chunk_pcm(b"")
        assert chunks == []

    def test_small_pcm(self):
        """PCM smaller than one chunk returns single small chunk."""
        pcm = b"\x00" * 100
        chunks = chunk_pcm(pcm, chunk_ms=100)
        assert len(chunks) == 1
        assert len(chunks[0]) == 100

    def test_exact_multiple(self):
        """When data is exact multiple of chunk size, no partial chunks."""
        pcm = b"\x00" * 6400  # exactly 2 chunks of 100ms
        chunks = chunk_pcm(pcm, chunk_ms=100)
        assert len(chunks) == 2
        assert all(len(c) == 3200 for c in chunks)

    def test_all_data_preserved(self):
        """Concatenating all chunks should equal original data."""
        pcm = b"\xAB\xCD" * 2500  # 5000 bytes
        chunks = chunk_pcm(pcm, chunk_ms=100)
        reassembled = b"".join(chunks)
        assert reassembled == pcm
