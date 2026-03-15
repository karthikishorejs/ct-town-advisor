"""
live_agent.py
-------------
Penny's real-time voice layer — full-duplex mic → Gemini Live → speaker.

Architecture
------------
  _mic_task        : pyaudio → 16 kHz PCM chunks → Gemini Live stream
  _receive_task    : Gemini Live stream → audio chunks → speaker playback
                     + text accumulation → JSON parse → callbacks
  _text_sender_task: asyncio queue → Gemini Live text turns (fallback input)

Interrupt model
---------------
  Gemini Live API handles VAD server-side.  When the user speaks while
  Penny is talking the server sets server_content.interrupted = True.
  _receive_task detects this, flushes the speaker buffer, and fires
  on_interrupted() + on_state_change("interrupted").

Penny's response format
-----------------------
  Penny returns a JSON object (see context_builder.SYSTEM_PROMPT):
    {
      "voice_response": "...",   <- spoken aloud (audio)
      "ui_update": { ... }       <- chart / listings / calculator flags
    }
  In audio-only mode the full JSON arrives in text parts alongside the
  audio; on turn_complete we parse it and fire on_ui_update().

Usage
-----
  agent = PennyAgent(
      on_voice_response=lambda t: print("Penny:", t),
      on_ui_update=lambda u: update_ui(u),
      on_state_change=lambda s: set_badge(s),
      on_interrupted=lambda: stop_animation(),
  )
  agent.start_session()   # blocks until stop_session()
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from google import genai
from google.genai import types

from src.audio_utils import CHANNELS, SAMPLE_RATE
from src.context_builder import SYSTEM_PROMPT

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# gemini-2.0-flash-exp supports Live API with AUDIO output.
# Override with GEMINI_MODEL env var; falls back to the verified working model.
LIVE_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-native-audio-latest")

MIC_CHUNK_FRAMES = 1024      # ~64 ms at 16 kHz
OUTPUT_SAMPLE_RATE = 24_000  # Gemini Live outputs 24 kHz PCM


# ---------------------------------------------------------------------------
# Live session config
# ---------------------------------------------------------------------------

def _build_live_config() -> types.LiveConnectConfig:
    return types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=types.Content(
            role="system",
            parts=[types.Part(text=SYSTEM_PROMPT)],
        ),
        output_audio_transcription=types.AudioTranscriptionConfig(),
    )


# ---------------------------------------------------------------------------
# JSON response parser
# ---------------------------------------------------------------------------

def _parse_penny_response(text: str) -> tuple[str, dict | None]:
    """
    Parse Penny's structured JSON response.

    Returns:
        (voice_response_text, ui_update_dict)
        Falls back to (raw_text, None) if the text isn't valid JSON.
    """
    text = text.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        data = json.loads(text)
        voice = data.get("voice_response", text)
        ui = data.get("ui_update")
        return voice, ui
    except (json.JSONDecodeError, AttributeError):
        return text, None


# ---------------------------------------------------------------------------
# PennyAgent
# ---------------------------------------------------------------------------

class PennyAgent:
    """
    Full-duplex voice agent for Penny.

    Callbacks are invoked from the asyncio event-loop thread.  If you need
    to update a non-thread-safe UI (Tkinter, Qt, etc.) marshal to main thread.

    Args:
        on_voice_response : Called with Penny's spoken text when a turn ends.
        on_ui_update      : Called with the ui_update dict from Penny's JSON.
        on_state_change   : Called with one of: "listening" | "thinking" |
                            "speaking" | "interrupted" | "stopped".
        on_interrupted    : Called immediately when the user interrupts Penny.
    """

    def __init__(
        self,
        on_voice_response: Callable[[str], Any] | None = None,
        on_ui_update: Callable[[dict], Any] | None = None,
        on_state_change: Callable[[str], Any] | None = None,
        on_interrupted: Callable[[], Any] | None = None,
    ) -> None:
        self._on_voice_response = on_voice_response
        self._on_ui_update = on_ui_update
        self._on_state_change = on_state_change
        self._on_interrupted = on_interrupted

        self._client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
        self._session: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event = asyncio.Event()
        self._text_queue: asyncio.Queue[str] = asyncio.Queue()
        self._is_speaking = False

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def start_session(self) -> None:
        """
        Start the Penny voice session.  Blocks until stop_session() is called.
        Opens the mic, connects to Gemini Live, and begins listening.
        """
        asyncio.run(self._run())

    def send_text(self, query: str) -> None:
        """
        Send a text query to Penny (non-blocking, safe from any thread).
        Useful as a fallback when the mic is unavailable.
        """
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._text_queue.put_nowait, query)

    def stop_session(self) -> None:
        """Signal the agent to shut down gracefully."""
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._stop_event.set)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _emit_state(self, state: str) -> None:
        if self._on_state_change:
            self._on_state_change(state)

    # ------------------------------------------------------------------
    # Core async loop
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._stop_event.clear()

        print(f"Connecting to Gemini Live ({LIVE_MODEL})…")
        config = _build_live_config()

        async with self._client.aio.live.connect(
            model=LIVE_MODEL, config=config
        ) as session:
            self._session = session
            print("Connected. Penny is ready — speak to her!\n")
            self._emit_state("listening")

            await asyncio.gather(
                self._mic_task(),
                self._receive_task(),
                self._text_sender_task(),
            )

        self._emit_state("stopped")

    # ------------------------------------------------------------------
    # Mic task — captures mic and streams to Gemini Live
    # ------------------------------------------------------------------

    async def _mic_task(self) -> None:
        try:
            import pyaudio
        except ImportError:
            print(
                "pyaudio not installed — microphone disabled.\n"
                "Install: pip install pyaudio\n"
                "Use send_text() for text input instead."
            )
            await self._stop_event.wait()
            return

        pa = pyaudio.PyAudio()
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=CHANNELS,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=MIC_CHUNK_FRAMES,
        )
        print("Microphone open.")

        # Brief silence after Penny finishes speaking before mic resumes,
        # to let the last audio tail clear the speakers.
        _post_speak_cooldown = 0.4   # seconds
        _silence_until: float = 0.0

        try:
            while not self._stop_event.is_set():
                # Non-blocking read via executor to keep the event loop free
                pcm_chunk: bytes = await self._loop.run_in_executor(
                    None, stream.read, MIC_CHUNK_FRAMES, False
                )

                now = self._loop.time()

                # Mute mic while Penny is speaking to prevent echo feedback.
                # When Penny finishes, apply a brief cooldown so the trailing
                # speaker audio doesn't re-trigger Gemini's VAD.
                if self._is_speaking:
                    _silence_until = now + _post_speak_cooldown
                    continue
                if now < _silence_until:
                    continue

                if self._session:
                    await self._session.send(
                        input=types.LiveClientRealtimeInput(
                            media_chunks=[
                                types.Blob(
                                    data=pcm_chunk,
                                    mime_type=f"audio/pcm;rate={SAMPLE_RATE}",
                                )
                            ]
                        )
                    )
        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()

    # ------------------------------------------------------------------
    # Receive task — plays audio + parses text → callbacks
    # ------------------------------------------------------------------

    async def _receive_task(self) -> None:
        try:
            import pyaudio
            pa = pyaudio.PyAudio()
            out_stream = pa.open(
                format=pyaudio.paInt16,
                channels=CHANNELS,
                rate=OUTPUT_SAMPLE_RATE,
                output=True,
            )
            audio_available = True
        except ImportError:
            pa = out_stream = None
            audio_available = False

        # accumulated_text  : non-thought text parts (may contain JSON for ui_update)
        # accumulated_transcript: audio transcription — what Penny actually said aloud
        accumulated_text = ""
        accumulated_transcript = ""

        try:
            while not self._stop_event.is_set():
                async for response in self._session.receive():
                    if self._stop_event.is_set():
                        break

                    sc = response.server_content

                    # ---- Audio output → speaker ----
                    # Always extract from model_turn.parts to avoid the SDK
                    # "non-data parts" warning triggered by response.data
                    # when audio and text/thought parts coexist in one response.
                    audio_data: bytes | None = None
                    if sc and sc.model_turn:
                        for part in sc.model_turn.parts:
                            if part.inline_data and part.inline_data.data:
                                audio_data = part.inline_data.data
                                break

                    if audio_data and audio_available:
                        if not self._is_speaking:
                            self._is_speaking = True
                            self._emit_state("speaking")
                        await self._loop.run_in_executor(
                            None, out_stream.write, audio_data
                        )

                    # ---- Text parts → accumulate, skipping thought/reasoning parts ----
                    if sc and sc.model_turn:
                        for part in sc.model_turn.parts:
                            if part.text and not getattr(part, "thought", False):
                                accumulated_text += part.text
                                if not self._is_speaking:
                                    self._emit_state("thinking")

                    # ---- Audio transcription — what Penny said aloud ----
                    # For native-audio models this is the primary voice text source.
                    if sc and sc.output_transcription:
                        chunk = (sc.output_transcription.text or "").strip()
                        if chunk:
                            accumulated_transcript += " " + chunk

                    # ---- Interrupted — user spoke over Penny ----
                    interrupted = sc and getattr(sc, "interrupted", False)
                    if interrupted:
                        self._is_speaking = False
                        accumulated_text = ""
                        accumulated_transcript = ""
                        if audio_available:
                            out_stream.stop_stream()
                            out_stream.start_stream()
                        if self._on_interrupted:
                            self._on_interrupted()
                        self._emit_state("interrupted")
                        print("[Penny interrupted]")

                    # ---- Turn complete — fire callbacks ----
                    if sc and sc.turn_complete:
                        self._is_speaking = False

                        # Transcription = what Penny said (native-audio models)
                        # Text parts   = JSON payload (text/multimodal models)
                        # Use transcription as voice_response when available;
                        # fall back to text parts (e.g. send_text() in text mode).
                        voice_source = accumulated_transcript.strip() or accumulated_text
                        if voice_source:
                            voice_text, ui_update = _parse_penny_response(voice_source)
                            if self._on_voice_response and voice_text:
                                self._on_voice_response(voice_text)
                        else:
                            ui_update = None

                        # ui_update always comes from text parts (JSON), not audio
                        if not ui_update and accumulated_text:
                            _, ui_update = _parse_penny_response(accumulated_text)
                        if self._on_ui_update and ui_update:
                            self._on_ui_update(ui_update)

                        accumulated_text = ""
                        accumulated_transcript = ""
                        self._emit_state("listening")

        finally:
            if audio_available:
                out_stream.stop_stream()
                out_stream.close()
                pa.terminate()

    # ------------------------------------------------------------------
    # Text sender task — drains send_text() queue
    # ------------------------------------------------------------------

    async def _text_sender_task(self) -> None:
        while not self._stop_event.is_set():
            try:
                query = await asyncio.wait_for(self._text_queue.get(), timeout=0.2)
            except asyncio.TimeoutError:
                continue

            if self._session:
                print(f"\n[Text → Penny] {query}")
                self._emit_state("thinking")
                await self._session.send_client_content(
                    turns=types.Content(
                        role="user",
                        parts=[types.Part(text=query)],
                    ),
                    turn_complete=True,
                )
