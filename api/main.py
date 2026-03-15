"""
api/main.py
-----------
FastAPI WebSocket server that proxies audio between the browser and Gemini
Live API.  nginx routes /ws/ here; Streamlit stays on port 8501.

Browser  →  Int16 PCM 16 kHz (binary frames)  →  FastAPI  →  Gemini Live
Browser  ←  Int16 PCM 24 kHz (binary frames)  ←  FastAPI  ←  Gemini Live
Browser  ←  {"type":"turn_complete","text":"..."}  ←  FastAPI (text frame)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.context_builder import VOICE_SYSTEM_PROMPT  # noqa: E402

LIVE_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-native-audio-latest")

app = FastAPI()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _recv_from_browser(
    websocket: WebSocket,
    session,
    stop: asyncio.Event,
) -> None:
    """Forward binary PCM frames from browser → Gemini Live."""
    try:
        while not stop.is_set():
            data = await websocket.receive_bytes()
            await session.send_realtime_input(
                audio=types.Blob(data=data, mime_type="audio/pcm;rate=16000")
            )
    except (WebSocketDisconnect, RuntimeError):
        pass
    except Exception as exc:
        print(f"[recv_from_browser] {exc}")
    finally:
        stop.set()


async def _send_to_browser(
    websocket: WebSocket,
    session,
    stop: asyncio.Event,
) -> None:
    """Forward audio chunks + transcripts from Gemini Live → browser.

    session.receive() is a finite async iterator — it yields messages for
    one turn and then stops.  The outer while loop re-enters it for every
    subsequent turn so that Penny can respond to multiple questions without
    the user having to reconnect.
    """
    accumulated_transcript = ""
    try:
        while not stop.is_set():
            async for response in session.receive():
                if stop.is_set():
                    break

                sc = response.server_content

                # ── Audio chunks → binary frame ──────────────────────────
                if sc and sc.model_turn:
                    for part in sc.model_turn.parts:
                        if part.inline_data and part.inline_data.data:
                            await websocket.send_bytes(part.inline_data.data)

                # Older SDK versions surface audio at top-level response.data
                if response.data:
                    await websocket.send_bytes(response.data)

                # ── Output transcription (what Gemini said) ───────────────
                if sc and sc.output_transcription:
                    chunk = (sc.output_transcription.text or "").strip()
                    if chunk:
                        accumulated_transcript += " " + chunk

                # ── Interrupted ───────────────────────────────────────────
                if sc and getattr(sc, "interrupted", False):
                    accumulated_transcript = ""
                    await websocket.send_text(
                        json.dumps({"type": "interrupted"})
                    )

                # ── Turn complete → send transcript ───────────────────────
                if sc and sc.turn_complete:
                    transcript = accumulated_transcript.strip()
                    accumulated_transcript = ""
                    await websocket.send_text(
                        json.dumps({"type": "turn_complete", "text": transcript})
                    )

    except (WebSocketDisconnect, RuntimeError):
        pass
    except Exception as exc:
        print(f"[send_to_browser] {exc}")
    finally:
        stop.set()


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@app.websocket("/ws/audio")
async def audio_proxy(websocket: WebSocket) -> None:
    await websocket.accept()

    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        output_audio_transcription=types.AudioTranscriptionConfig(),
        system_instruction=types.Content(
            role="system",
            parts=[types.Part(text=VOICE_SYSTEM_PROMPT)],
        ),
    )

    stop = asyncio.Event()
    try:
        async with client.aio.live.connect(model=LIVE_MODEL, config=config) as session:
            t1 = asyncio.create_task(_recv_from_browser(websocket, session, stop))
            t2 = asyncio.create_task(_send_to_browser(websocket, session, stop))
            _done, pending = await asyncio.wait(
                [t1, t2], return_when=asyncio.FIRST_COMPLETED
            )
            stop.set()
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

    except Exception as exc:
        print(f"[audio_proxy] {exc}")
        try:
            await websocket.send_text(
                json.dumps({"type": "error", "message": str(exc)})
            )
        except Exception:
            pass
