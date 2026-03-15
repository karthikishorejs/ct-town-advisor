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
import struct
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

from fastapi.responses import HTMLResponse  # noqa: E402


@app.get("/test", response_class=HTMLResponse)
async def test_page():
    """Standalone voice test — no Streamlit, no iframe."""
    return """<!DOCTYPE html><html><head><title>Voice Test</title>
<style>body{font-family:monospace;background:#111;color:#eee;padding:20px}
button{padding:10px 24px;font-size:16px;cursor:pointer;margin:8px}
button:disabled{opacity:0.4;cursor:default}
#log{white-space:pre-wrap;max-height:70vh;overflow-y:auto;margin-top:12px;
font-size:13px;line-height:1.5;border:1px solid #333;padding:10px}
.hint{color:#888;font-size:13px;margin:8px 0}
.status{font-size:15px;color:#00d4ff;margin:8px 0;min-height:22px}</style>
</head><body>
<h2>Penny Voice Test (no Streamlit)</h2>
<p class="hint">Click Start, speak, then click Stop Mic.
Penny will respond with audio after you stop.</p>
<button id="startBtn" onclick="start()">🎙️ Start</button>
<button id="stopBtn" onclick="stopMic()" disabled>⏹ Stop Mic</button>
<div id="statusLine" class="status"></div>
<div id="log"></div>
<script>
const LOG=document.getElementById("log");
const STATUS=document.getElementById("statusLine");
function log(m){LOG.textContent+=new Date().toISOString().slice(11,23)+" "+m+"\\n";
LOG.scrollTop=LOG.scrollHeight;console.log(m)}
function setStatus(m){STATUS.textContent=m}

let ws,audioCtx,micStream,proc,nextPlay=0,waiting=false;

async function start(){
  document.getElementById("startBtn").disabled=true;
  document.getElementById("stopBtn").disabled=false;
  waiting=false;
  log("Starting mic…");
  audioCtx=new AudioContext();
  micStream=await navigator.mediaDevices.getUserMedia({
    audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}
  });
  const src=audioCtx.createMediaStreamSource(micStream);
  proc=audioCtx.createScriptProcessor(4096,1,1);
  const rate=audioCtx.sampleRate;
  let chunks=0;
  proc.onaudioprocess=(e)=>{
    if(!ws||ws.readyState!==1)return;
    const f=e.inputBuffer.getChannelData(0);
    const ratio=rate/16000,len=Math.floor(f.length/ratio);
    const out=new Int16Array(len);
    for(let i=0;i<len;i++){const s=Math.max(-1,Math.min(1,f[Math.floor(i*ratio)]));
      out[i]=s<0?s*0x8000:s*0x7FFF;}
    ws.send(out.buffer);chunks++;
    if(chunks%25===0)log("[mic] "+chunks+" chunks ("+((chunks*4096/rate)|0)+"s)");
  };
  src.connect(proc);proc.connect(audioCtx.destination);
  log("Mic ready ("+rate+"Hz). Opening WebSocket…");
  setStatus("🎙️ Listening…");

  ws=new WebSocket((location.protocol==="https:"?"wss:":"ws:")+"//"+location.host+"/ws/audio");
  ws.binaryType="arraybuffer";
  ws.onopen=()=>log("[ws] OPEN ✓ — speak now");
  ws.onclose=(e)=>{
    log("[ws] CLOSE code="+e.code+" clean="+e.wasClean+" reason="+(e.reason||"none"));
    waiting=false;
    setStatus("");
    resetUI();
  };
  ws.onerror=(e)=>log("[ws] ERROR "+e);

  let audioFrames=0;
  ws.onmessage=(evt)=>{
    if(typeof evt.data==="string"){
      log("[ws] ← "+evt.data);
      try{
        const m=JSON.parse(evt.data);
        if(m.type==="turn_complete"){
          if(m.text)log("\\n🗣️ Penny: "+m.text+"\\n");
          if(waiting){
            // Penny finished responding — close cleanly after audio plays
            waiting=false;
            setStatus("✅ Done");
            setTimeout(()=>{
              if(ws&&ws.readyState<=1)ws.close(1000,"done");
              setTimeout(()=>{if(audioCtx){audioCtx.close();audioCtx=null}},2000);
              ws=null;nextPlay=0;
              resetUI();setStatus("");
            },500);
          }
        }
      }catch(_){}
      return;
    }
    audioFrames++;
    setStatus("🗣️ Penny is speaking…");
    const d=new Int16Array(evt.data);
    const f=new Float32Array(d.length);
    for(let i=0;i<d.length;i++)f[i]=d[i]/(d[i]<0?0x8000:0x7FFF);
    const buf=audioCtx.createBuffer(1,f.length,24000);
    buf.copyToChannel(f,0);const s=audioCtx.createBufferSource();
    s.buffer=buf;s.connect(audioCtx.destination);
    const t=Math.max(audioCtx.currentTime,nextPlay);s.start(t);nextPlay=t+buf.duration;
    if(audioFrames===1)log("[play] receiving audio from Penny…");
    if(audioFrames%20===0)log("[play] "+audioFrames+" audio frames");
  };
}

function stopMic(){
  log("Stopping mic (keeping WS open for response)…");
  if(proc){proc.disconnect();proc=null}
  if(micStream){micStream.getTracks().forEach(t=>t.stop());micStream=null}
  document.getElementById("stopBtn").disabled=true;
  // Tell server we're done talking
  if(ws&&ws.readyState===1){
    ws.send(JSON.stringify({type:"mic_stopped"}));
  }
  waiting=true;
  setStatus("⏳ Waiting for Penny…");
  // Timeout safety: if no response in 20s, clean up
  setTimeout(()=>{
    if(waiting){
      log("[timeout] no response from Penny in 20s");
      waiting=false;
      if(ws&&ws.readyState<=1)ws.close(1000,"timeout");
      setTimeout(()=>{if(audioCtx){audioCtx.close();audioCtx=null}},1000);
      ws=null;nextPlay=0;
      resetUI();setStatus("No response — try again");
    }
  },20000);
}

function resetUI(){
  document.getElementById("startBtn").disabled=false;
  document.getElementById("stopBtn").disabled=true;
}
</script></body></html>"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _recv_from_browser(
    websocket: WebSocket,
    session,
    stop: asyncio.Event,
) -> None:
    """Forward binary PCM frames from browser → Gemini Live.

    Accepts both binary frames (audio) and text frames (control messages).
    When the browser sends {"type":"mic_stopped"}, we stop reading but
    do NOT close the WebSocket — the proxy will send silence to trigger
    Gemini's VAD, and _send_to_browser will stream audio back.
    """
    chunks_sent = 0
    mic_stopped_cleanly = False
    try:
        while not stop.is_set():
            msg = await websocket.receive()

            if msg["type"] == "websocket.disconnect":
                print("[recv] browser disconnected")
                break

            # ── Text control message ──────────────────────────────────
            if "text" in msg and msg["text"]:
                try:
                    ctrl = json.loads(msg["text"])
                    if ctrl.get("type") == "mic_stopped":
                        mic_stopped_cleanly = True
                        print("[recv] mic_stopped signal — browser keeping WS open for response")
                        break
                    else:
                        print(f"[recv] unknown control message: {ctrl}")
                except json.JSONDecodeError:
                    print(f"[recv] non-JSON text frame: {msg['text'][:80]}")
                continue

            # ── Binary audio frame ────────────────────────────────────
            data = msg.get("bytes")
            if not data:
                continue

            # Log audio level for first 5 chunks to verify mic data is real
            if chunks_sent < 5:
                n_samples = len(data) // 2
                samples = struct.unpack(f"<{n_samples}h", data)
                rms = (sum(s * s for s in samples) / n_samples) ** 0.5
                peak = max(abs(s) for s in samples)
                print(f"[recv] chunk#{chunks_sent}: {len(data)}B, "
                      f"{n_samples} samples, rms={rms:.0f}, peak={peak}")

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
    except WebSocketDisconnect as exc:
        print(f"[recv] closed — WebSocketDisconnect code={exc.code}")
    except RuntimeError as exc:
        print(f"[recv] closed — RuntimeError: {exc}")
    except Exception as exc:
        print(f"[recv] ERROR {type(exc).__name__}: {exc}")
    finally:
        how = "mic_stopped signal" if mic_stopped_cleanly else "disconnect"
        print(f"[recv] done — {chunks_sent} chunks sent ({how})")
        # Do NOT call stop.set() here — the proxy function handles
        # sending silence to trigger VAD and draining Gemini's response.
        # Setting stop here would cause _send_to_browser to exit before
        # Gemini has a chance to respond.


async def _send_to_browser(
    websocket: WebSocket,
    session,
    stop: asyncio.Event,
) -> None:
    """Forward audio chunks + transcripts from Gemini Live → browser.

    session.receive() is finite per-turn — it yields messages until
    turn_complete, then the async-for exhausts.  The outer while loop
    re-enters it for every subsequent turn so Penny can answer multiple
    questions without the user having to reconnect.
    """
    accumulated_transcript = ""
    audio_frames_sent = 0
    browser_gone = False       # set True when browser WebSocket drops
    print("[send] starting receive loop")
    try:
        resp_count = 0
        while not stop.is_set():
            async for response in session.receive():
                if stop.is_set():
                    break

                resp_count += 1
                sc = response.server_content

                # Log every response so we can see what Gemini is sending
                if resp_count <= 5 or resp_count % 20 == 0:
                    has_audio = bool(sc and sc.model_turn and any(
                        p.inline_data and p.inline_data.data
                        for p in sc.model_turn.parts
                    )) if sc and sc.model_turn else False
                    has_text = bool(sc and sc.model_turn and any(
                        p.text for p in sc.model_turn.parts
                    )) if sc and sc.model_turn else False
                    has_transcript = bool(sc and sc.output_transcription)
                    turn_complete = bool(sc and sc.turn_complete)
                    print(f"[send] resp#{resp_count}: audio={has_audio} "
                          f"text={has_text} transcript={has_transcript} "
                          f"turn_complete={turn_complete}")

                # ── Audio chunks → binary frame ──────────────────────────
                audio_sent_this_msg = False
                if sc and sc.model_turn:
                    for part in sc.model_turn.parts:
                        if part.inline_data and part.inline_data.data:
                            if not browser_gone:
                                try:
                                    await websocket.send_bytes(
                                        part.inline_data.data
                                    )
                                    audio_frames_sent += 1
                                    audio_sent_this_msg = True
                                except (WebSocketDisconnect, RuntimeError):
                                    browser_gone = True
                                    print("[send] browser gone — "
                                          "continuing to drain Gemini")
                            else:
                                audio_frames_sent += 1

                # Older SDK versions surface audio at top-level response.data
                if not audio_sent_this_msg and response.data:
                    if not browser_gone:
                        try:
                            await websocket.send_bytes(response.data)
                            audio_frames_sent += 1
                        except (WebSocketDisconnect, RuntimeError):
                            browser_gone = True
                    else:
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
                    if not browser_gone:
                        try:
                            await websocket.send_text(
                                json.dumps({"type": "interrupted"})
                            )
                        except (WebSocketDisconnect, RuntimeError):
                            browser_gone = True

                # ── Turn complete → send transcript ───────────────────────
                if sc and sc.turn_complete:
                    transcript = accumulated_transcript.strip()
                    accumulated_transcript = ""
                    print(f"[send] turn_complete — transcript={transcript!r}")
                    if not browser_gone:
                        try:
                            await websocket.send_text(
                                json.dumps({
                                    "type": "turn_complete",
                                    "text": transcript,
                                })
                            )
                        except (WebSocketDisconnect, RuntimeError):
                            browser_gone = True

            # session.receive() exhausted for this turn — yield briefly
            await asyncio.sleep(0.05)

    except WebSocketDisconnect as exc:
        print(f"[send] closed — WebSocketDisconnect code={exc.code}")
    except RuntimeError as exc:
        print(f"[send] closed — RuntimeError: {exc}")
    except Exception as exc:
        print(f"[send] ERROR {type(exc).__name__}: {exc}")
    finally:
        sent_to = "browser" if not browser_gone else "Gemini (browser gone)"
        print(f"[send] done — {audio_frames_sent} audio frames ({sent_to})")
        stop.set()

async def _await_send_drain(send_task: asyncio.Task, timeout_s: float = 6.0) -> None:
    """Allow Gemini -> browser responses to flush after mic input stops."""
    try:
        await asyncio.wait_for(send_task, timeout=timeout_s)
        print("[proxy] send loop finished naturally")
    except asyncio.TimeoutError:
        print(f"[proxy] send loop still running after {timeout_s:.1f}s — cancelling")
        send_task.cancel()
        await asyncio.gather(send_task, return_exceptions=True)

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
            if t1.done() and not t2.done():
                # Browser disconnected — Gemini's VAD may not have triggered
                # because it never saw a silence gap.  Send ~1.5 s of silence
                # so VAD detects end-of-speech and starts generating.
                print("[proxy] mic stream ended; sending silence to trigger VAD…")
                SILENCE_SECS = 1.5
                CHUNK_SAMPLES = 1024  # match live_agent.py chunk size
                n_chunks = int(SILENCE_SECS * 16000 / CHUNK_SAMPLES)
                silence_chunk = b"\x00" * (CHUNK_SAMPLES * 2)  # Int16 = 2B/sample
                for _ in range(n_chunks):
                    await session.send(
                        input=types.LiveClientRealtimeInput(
                            media_chunks=[
                                types.Blob(
                                    data=silence_chunk,
                                    mime_type="audio/pcm;rate=16000",
                                )
                            ]
                        )
                    )
                print(f"[proxy] sent {n_chunks} silence chunks; waiting for response…")
                await _await_send_drain(t2, timeout_s=15.0)
            elif t2.done() and not t1.done():
                print("[proxy] send loop ended first; stopping receive loop")
                stop.set()
                t1.cancel()
                await asyncio.gather(t1, return_exceptions=True)

            for task in pending:
                if not task.done():
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
