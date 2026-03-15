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
    chunks_sent = 0
    try:
        while not stop.is_set():
            data = await websocket.receive_bytes()
            # Use same send pattern as the working live_agent.py
            await session.send(
                input=types.LiveClientRealtimeInput(
                    media_chunks=[
                        types.Blob(data=data, mime_type="audio/pcm;rate=16000")
                    ]
                )
            )
            chunks_sent += 1
            if chunks_sent % 50 == 0:   # log every ~4 s of audio
                print(f"[recv] {chunks_sent} audio chunks sent to Gemini")
    except (WebSocketDisconnect, RuntimeError):
        pass
    except Exception as exc:
        print(f"[recv] ERROR: {exc}")
    finally:
        print(f"[recv] done — {chunks_sent} total chunks sent")
        stop.set()


async def _send_to_browser(
    websocket: WebSocket,
    session,
    stop: asyncio.Event,
) -> None:
    """Forward audio chunks + transcripts from Gemini Live → browser.

    session.receive() is an infinite async generator — it yields messages
    from ALL turns until the session closes.  Do NOT wrap in a while loop;
    that would re-create the generator and lose messages between turns.
    """
    accumulated_transcript = ""
    audio_frames_sent = 0
    print("[send] starting receive loop")
    try:
        # session.receive() is finite per-turn — it yields messages until
        # turn_complete, then the async-for exhausts.  The outer while loop
        # re-enters it for every subsequent turn so Penny can answer multiple
        # questions without the user having to reconnect.
        while not stop.is_set():
            async for response in session.receive():
                if stop.is_set():
                    break

                sc = response.server_content

                # ── Audio chunks → binary frame ──────────────────────────
                audio_sent_this_msg = False
                if sc and sc.model_turn:
                    for part in sc.model_turn.parts:
                        if part.inline_data and part.inline_data.data:
                            await websocket.send_bytes(part.inline_data.data)
                            audio_frames_sent += 1
                            audio_sent_this_msg = True

                # Older SDK versions surface audio at top-level response.data
                if not audio_sent_this_msg and response.data:
                    await websocket.send_bytes(response.data)
                    audio_frames_sent += 1

                if audio_sent_this_msg:
                    print(f"[send] audio frame #{audio_frames_sent} → browser")

                # ── Output transcription ──────────────────────────────────
                if sc and sc.output_transcription:
                    chunk = (sc.output_transcription.text or "").strip()
                    if chunk:
                        print(f"[send] transcript: {chunk!r}")
                        accumulated_transcript += " " + chunk

                # ── Interrupted ───────────────────────────────────────────
                if sc and getattr(sc, "interrupted", False):
                    print("[send] interrupted")
                    accumulated_transcript = ""
                    await websocket.send_text(
                        json.dumps({"type": "interrupted"})
                    )

                # ── Turn complete → send transcript ───────────────────────
                if sc and sc.turn_complete:
                    transcript = accumulated_transcript.strip()
                    accumulated_transcript = ""
                    print(f"[send] turn_complete — transcript={transcript!r}")
                    await websocket.send_text(
                        json.dumps({"type": "turn_complete", "text": transcript})
                    )

            # session.receive() exhausted for this turn — yield briefly
            # so _recv_from_browser can continue streaming audio in
            await asyncio.sleep(0.05)

    except (WebSocketDisconnect, RuntimeError):
        pass
    except Exception as exc:
        print(f"[send] ERROR: {exc}")
    finally:
        print(f"[send] done — {audio_frames_sent} audio frames sent to browser")
        stop.set()


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@app.websocket("/ws/audio")
async def audio_proxy(websocket: WebSocket) -> None:
    print(f"[proxy] new connection from {websocket.client}")
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
        print(f"[proxy] connecting to Gemini Live ({LIVE_MODEL})…")
        async with client.aio.live.connect(model=LIVE_MODEL, config=config) as session:
            print("[proxy] Gemini Live connected ✓")
            t1 = asyncio.create_task(_recv_from_browser(websocket, session, stop))
            t2 = asyncio.create_task(_send_to_browser(websocket, session, stop))
            _done, pending = await asyncio.wait(
                [t1, t2], return_when=asyncio.FIRST_COMPLETED
            )
            print("[proxy] one task done, cancelling the other")
            stop.set()
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            print("[proxy] session closed")

    except Exception as exc:
        print(f"[proxy] ERROR: {exc}")
        try:
            await websocket.send_text(
                json.dumps({"type": "error", "message": str(exc)})
            )
        except Exception:
            pass
