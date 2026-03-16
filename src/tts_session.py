"""
tts_session.py
--------------
Persistent Gemini Live API session for text-to-speech.

WHY A SEPARATE MODULE?
Streamlit re-executes app/main.py on every rerun (~0.3 s during polling).
Module-level globals in app/main.py get reset each time, leaking event loops,
threads, and file descriptors.  Python caches imports (sys.modules), so
module-level code HERE runs exactly ONCE per process.

THREAD MODEL:
  _tts_event_loop — asyncio loop running forever in a daemon thread
  _live_session   — Gemini Live API session living on that loop
  generate()      — callable from ANY thread; submits a coroutine and waits
"""

from __future__ import annotations

import asyncio
import io
import os
import queue
import threading
import wave

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

LIVE_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-native-audio-latest")

_TTS_SYSTEM_INSTRUCTION = (
    "You are Penny, a warm Connecticut Town Advisor. "
    "Read the following text aloud in a friendly, natural tone. "
    "Say ONLY what is given — do not add or change anything."
)

# ---------------------------------------------------------------------------
# Persistent event loop (one per process, created at import time)
# ---------------------------------------------------------------------------

_tts_event_loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
_tts_loop_thread = threading.Thread(
    target=_tts_event_loop.run_forever,
    daemon=True,
    name="TTS-EventLoop",
)
_tts_loop_thread.start()
print("[tts] event loop started")


# ---------------------------------------------------------------------------
# Persistent Gemini Live session (lives on the event loop)
# ---------------------------------------------------------------------------

_live_session = None
_live_cm = None  # async context manager returned by connect()


async def _get_or_create_session():
    """Return the live TTS session, connecting if needed."""
    global _live_session, _live_cm

    if _live_session is not None:
        return _live_session

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise EnvironmentError("GOOGLE_API_KEY not set")

    client = genai.Client(api_key=api_key)
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=types.Content(
            role="system",
            parts=[types.Part(text=_TTS_SYSTEM_INSTRUCTION)],
        ),
    )
    print("[tts] connecting to Gemini Live…")
    _live_cm = client.aio.live.connect(model=LIVE_MODEL, config=config)
    _live_session = await _live_cm.__aenter__()
    print("[tts] Gemini Live session ready ✓")
    return _live_session


async def _close_session():
    """Tear down the live session so the next call reconnects."""
    global _live_session, _live_cm
    if _live_cm is not None:
        try:
            await _live_cm.__aexit__(None, None, None)
        except Exception:
            pass
    _live_session = None
    _live_cm = None


def _pack_wav(audio_chunks: list[bytes]) -> bytes:
    """Wrap raw PCM chunks in a WAV container (24 kHz, mono, 16-bit)."""
    pcm = b"".join(audio_chunks)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(pcm)
    return buf.getvalue()


async def _tts_generate(text: str) -> bytes | None:
    """Send text to the persistent Live session and return WAV bytes.

    Retries ONCE with a fresh session if the first attempt fails
    (handles timed-out pre-warmed sessions and transient errors).
    """
    for attempt in range(2):
        try:
            session = await _get_or_create_session()
            await session.send_client_content(
                turns=[types.Content(
                    role="user",
                    parts=[types.Part(text=f"Read this aloud: {text}")],
                )],
                turn_complete=True,
            )
            audio_chunks: list[bytes] = []
            async for response in session.receive():
                sc = response.server_content
                if sc and sc.model_turn:
                    for part in sc.model_turn.parts:
                        if part.inline_data and part.inline_data.data:
                            audio_chunks.append(part.inline_data.data)
                if sc and sc.turn_complete:
                    break

            if audio_chunks:
                return _pack_wav(audio_chunks)
            print(f"[tts] attempt {attempt + 1}: no audio chunks received")
            await _close_session()

        except Exception as exc:
            print(f"[tts] attempt {attempt + 1} failed: "
                  f"{type(exc).__name__}: {exc}")
            await _close_session()

        if attempt == 0:
            print("[tts] retrying with fresh session…")

    return None


# ---------------------------------------------------------------------------
# Public API (callable from any thread)
# ---------------------------------------------------------------------------

def generate(text: str) -> bytes | None:
    """Generate Penny's voice audio.  Reuses persistent Live API session.

    Callable from any thread — submits work to the persistent event loop
    and blocks until the result is ready (or 30 s timeout).
    """
    if not text or len(text) < 5:
        return None
    future = asyncio.run_coroutine_threadsafe(
        _tts_generate(text), _tts_event_loop
    )
    try:
        return future.result(timeout=30)
    except Exception as exc:
        print(f"[tts] generation failed: {exc}")
        return None


def start_background(text: str, tts_q: queue.Queue) -> threading.Thread:
    """Kick off TTS in a daemon thread; result goes on tts_q.

    Returns the thread so the caller can check .is_alive().
    """
    def _worker():
        try:
            wav = generate(text)
            if wav:
                tts_q.put(wav)
                print(f"[tts-bg] audio ready ({len(wav):,} bytes)")
            else:
                print("[tts-bg] no audio returned")
        except Exception as exc:
            print(f"[tts-bg] failed: {exc}")

    t = threading.Thread(target=_worker, daemon=True, name="PennyTTS")
    t.start()
    return t


def prewarm() -> None:
    """Open the Live session in the background so the first TTS call is fast."""
    asyncio.run_coroutine_threadsafe(
        _get_or_create_session(), _tts_event_loop
    )


# Pre-warm at import time — session will be ready by the time user clicks
prewarm()
