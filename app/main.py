"""
app/main.py
-----------
Penny — CT Town Advisor · Streamlit frontend

Text queries : direct generate_content call (synchronous, returns JSON)
Voice queries: PennyAgent background thread + queue polling
Charts / map : driven by Penny's ui_update JSON field
Tax calc     : pure Streamlit slider, no AI

Run with:
    streamlit run app/main.py
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import queue
import sys
import threading
import time
import wave  # noqa: E402 — stdlib, used for WAV packaging
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as st_components
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.context_builder import SYSTEM_PROMPT, build_context, get_all_towns, get_town_data
from src.live_agent import PennyAgent

# Streamlit custom component: browser WebSocket audio (Cloud Run voice path)
_AUDIO_COMPONENT_PATH = ROOT / "app" / "components" / "audio_component"
_audio_ws_component = st_components.declare_component(
    "audio_ws",
    path=str(_AUDIO_COMPONENT_PATH),
)

# ---------------------------------------------------------------------------
# Page config (must be first Streamlit call)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Penny — CT Town Advisor",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BG       = "#0a0e1a"
CARD_BG  = "#0f1525"
BORDER   = "#1a2a4a"
ACCENT   = "#00d4ff"
TEXT     = "#e0e6f0"
MUTED    = "#8899aa"

TOWN_COLORS: dict[str, str] = {
    "Wallingford": "#2196F3",
    "North Haven":  "#4CAF50",
    "Cheshire":     "#9C27B0",
}

TOWN_COORDS: dict[str, tuple[float, float]] = {
    "Wallingford": (41.4571, -72.8231),
    "North Haven": (41.3904, -72.8597),
    "Cheshire":    (41.4987, -72.9012),
}

AVATAR_PATHS: dict[str, Path] = {
    "Wallingford": ROOT / "app" / "assets" / "wallingford_avatar.png",
    "North Haven": ROOT / "app" / "assets" / "north_haven_avatar.png",
    "Cheshire":    ROOT / "app" / "assets" / "cheshire_avatar.png",
}

# (icon, label, hex_color)
STATUS_CONFIG: dict[str, tuple[str, str, str]] = {
    "listening":   ("🎙️", "Listening",   ACCENT),
    "thinking":    ("🤔", "Thinking",    "#FFB300"),
    "speaking":    ("🗣️", "Speaking",    "#00FF88"),
    "interrupted": ("↩️", "Redirecting", "#FF6B35"),
    "stopped":     ("⏹️", "Stopped",     "#666"),
    "ready":       ("✅", "Ready",        ACCENT),
}

STARTERS = [
    "Best town for families?",
    "Compare education spending",
    "Which town has lowest tax?",
    "Show homes in North Haven",
]

GEMINI_MODEL    = os.getenv("GEMINI_TEXT_MODEL", "gemini-2.5-flash")
CT_ASSESS_RATIO = 0.70   # CT assessed value = 70 % of fair market value

# Cloud Run sets K_SERVICE automatically; pyaudio mic doesn't work there
IS_CLOUD_RUN = bool(os.getenv("K_SERVICE"))

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

def _inject_css() -> None:
    st.markdown(f"""
<style>
/* ── Global dark background ─────────────────────────────────────────────── */
[data-testid="stAppViewContainer"],
[data-testid="stHeader"],
section[data-testid="stMain"] > div,
.stApp {{ background-color: {BG} !important; }}

/* ── Typography ─────────────────────────────────────────────────────────── */
html, body, [class*="css"],
h1, h2, h3, h4, p, span, div, label {{ color: {TEXT}; }}

/* ── Inputs ─────────────────────────────────────────────────────────────── */
.stTextInput > div > div > input,
.stSelectbox > div > div > div {{
    background-color: #111827 !important;
    color: {TEXT} !important;
    border: 1px solid {BORDER} !important;
    border-radius: 8px !important;
}}
.stTextInput > div > div > input:focus {{
    border-color: {ACCENT} !important;
    box-shadow: 0 0 0 2px {ACCENT}33 !important;
}}

/* ── Buttons ─────────────────────────────────────────────────────────────── */
.stButton > button {{
    background: linear-gradient(135deg, #111827, #0d1520) !important;
    color: {ACCENT} !important;
    border: 1px solid {ACCENT}55 !important;
    border-radius: 20px !important;
    padding: 6px 18px !important;
    font-size: 0.83rem !important;
    transition: all 0.2s ease !important;
}}
.stButton > button:hover {{
    background: linear-gradient(135deg, #162040, #0e1c30) !important;
    border-color: {ACCENT} !important;
    box-shadow: 0 0 14px {ACCENT}44 !important;
    transform: translateY(-1px) !important;
}}

/* ── Persona card ────────────────────────────────────────────────────────── */
.persona-card {{
    background: {CARD_BG};
    border-radius: 16px;
    padding: 20px 16px;
    border: 1px solid {BORDER};
    text-align: center;
    margin-bottom: 16px;
    transition: box-shadow 0.3s ease;
}}
.persona-card .stat-row {{
    display: flex;
    justify-content: space-around;
    margin-top: 12px;
    gap: 8px;
}}
.persona-card .stat-item {{
    background: #0d1624;
    border-radius: 10px;
    padding: 8px 10px;
    flex: 1;
}}
.persona-card .stat-val {{
    font-size: 1.05rem;
    font-weight: 700;
    color: {ACCENT};
}}
.persona-card .stat-lbl {{
    font-size: 0.68rem;
    color: {MUTED};
    margin-top: 2px;
}}
.persona-empty {{
    background: {CARD_BG};
    border-radius: 16px;
    padding: 28px 16px;
    border: 1px dashed {BORDER};
    text-align: center;
    color: {MUTED};
    font-size: 0.9rem;
    margin-bottom: 16px;
}}

/* ── Status pill ─────────────────────────────────────────────────────────── */
.status-pill {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 14px;
    border-radius: 20px;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.02em;
    border: 1px solid currentColor;
}}

/* ── Mic pulse ───────────────────────────────────────────────────────────── */
@keyframes pulse-ring {{
    0%   {{ box-shadow: 0 0 0 0 {ACCENT}88; }}
    70%  {{ box-shadow: 0 0 0 14px {ACCENT}00; }}
    100% {{ box-shadow: 0 0 0 0  {ACCENT}00; }}
}}
.mic-pulse .stButton > button {{
    animation: pulse-ring 1.4s ease-out infinite !important;
    border-color: {ACCENT} !important;
    background: linear-gradient(135deg, #062038, #040e1e) !important;
}}

/* ── Chat bubbles ────────────────────────────────────────────────────────── */
.chat-wrap {{
    max-height: 340px;
    overflow-y: auto;
    padding-right: 6px;
    margin-bottom: 8px;
}}
.chat-wrap::-webkit-scrollbar {{ width: 4px; }}
.chat-wrap::-webkit-scrollbar-thumb {{ background: {BORDER}; border-radius: 4px; }}
.chat-bubble-user {{
    background: #0d2040;
    border: 1px solid #1a3a6a;
    border-radius: 14px 14px 4px 14px;
    padding: 10px 14px;
    margin: 6px 0 6px 30px;
    font-size: 0.88rem;
}}
.chat-bubble-penny {{
    background: {CARD_BG};
    border: 1px solid {BORDER};
    border-radius: 14px 14px 14px 4px;
    padding: 10px 14px;
    margin: 6px 30px 6px 0;
    font-size: 0.88rem;
}}
.chat-label {{
    font-size: 0.68rem;
    color: {MUTED};
    margin-bottom: 3px;
}}

/* ── Metrics ─────────────────────────────────────────────────────────────── */
[data-testid="stMetric"] {{
    background: {CARD_BG} !important;
    padding: 12px 14px !important;
    border-radius: 12px !important;
    border: 1px solid {BORDER} !important;
}}
[data-testid="stMetricValue"] {{ color: {ACCENT} !important; }}
[data-testid="stMetricLabel"] {{ color: {MUTED}  !important; font-size: 0.75rem !important; }}

/* ── Plotly chart wrapper ────────────────────────────────────────────────── */
[data-testid="stPlotlyChart"] {{
    border-radius: 14px !important;
    overflow: hidden !important;
    border: 1px solid {BORDER} !important;
}}

/* ── Section headers ─────────────────────────────────────────────────────── */
.section-header {{
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: {MUTED};
    margin: 14px 0 8px;
}}

/* ── Calculator panel ───────────────────────────────────────────────────── */
.calc-panel {{
    background: {CARD_BG};
    border-radius: 14px;
    padding: 16px;
    border: 1px solid {BORDER};
    margin-top: 10px;
}}

/* ── Sliders ─────────────────────────────────────────────────────────────── */
[data-testid="stSlider"] [data-baseweb="slider"] [role="slider"] {{
    background-color: {ACCENT} !important;
    border-color: {ACCENT} !important;
}}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

def _init_session_state() -> None:
    defaults: dict = {
        "active_town":         None,
        "current_chart_data":  None,
        "show_calculator":     False,
        "show_listings":       False,
        "highlight_towns":     [],
        "agent_state":         "ready",
        "chat_history":        [],
        "penny_agent":         None,
        "agent_thread":        None,
        "mic_active":          False,
        "pending_query":       None,
        "waiting_response":    False,
        "last_voice_turn_id":  -1,   # dedup WebSocket voice turns
        "pending_audio":       None,  # WAV bytes queued for playback
        "tts_thread":          None,  # background TTS thread (or None)
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
    # Queues must be created separately (new object each script run, but guarded)
    if "update_queue" not in st.session_state:
        st.session_state.update_queue = queue.Queue()
    if "tts_queue" not in st.session_state:
        st.session_state.tts_queue = queue.Queue()


# ---------------------------------------------------------------------------
# PennyAgent — background thread
# ---------------------------------------------------------------------------

def _init_agent() -> None:
    """Create and start PennyAgent once; safe to call on every render."""
    # Already running?
    t = st.session_state.agent_thread
    if t is not None and t.is_alive():
        return

    q: queue.Queue = st.session_state.update_queue

    def _on_voice_response(text: str) -> None:
        q.put({"type": "voice", "text": text})

    def _on_ui_update(ui: dict) -> None:
        q.put({"type": "ui", "data": ui})

    def _on_state_change(state: str) -> None:
        q.put({"type": "state", "state": state})

    def _on_interrupted() -> None:
        q.put({"type": "interrupted"})

    agent = PennyAgent(
        on_voice_response=_on_voice_response,
        on_ui_update=_on_ui_update,
        on_state_change=_on_state_change,
        on_interrupted=_on_interrupted,
    )
    st.session_state.penny_agent = agent

    thread = threading.Thread(
        target=agent.start_session,
        daemon=True,
        name="PennyAgent",
    )
    thread.start()
    st.session_state.agent_thread = thread


def _drain_queue() -> bool:
    """Apply all pending agent updates to session_state. Returns True if changed."""
    q: queue.Queue = st.session_state.update_queue
    changed = False
    while not q.empty():
        try:
            msg = q.get_nowait()
        except queue.Empty:
            break
        t = msg.get("type")
        if t == "voice":
            st.session_state.chat_history.append(
                {"role": "assistant", "content": msg["text"]}
            )
            st.session_state.waiting_response = False
            changed = True
        elif t == "ui":
            _apply_ui_update(msg["data"])
            changed = True
        elif t == "state":
            st.session_state.agent_state = msg["state"]
            if msg["state"] == "listening":
                st.session_state.waiting_response = False
            changed = True
        elif t == "interrupted":
            st.session_state.agent_state = "interrupted"
            st.session_state.waiting_response = False
            changed = True

    # ── Drain TTS audio queue (background thread → main thread) ──────
    tts_q: queue.Queue = st.session_state.tts_queue
    while not tts_q.empty():
        try:
            wav = tts_q.get_nowait()
            st.session_state.pending_audio = wav
            changed = True
        except queue.Empty:
            break

    # Clear tts_thread ref once it's done
    tts_t = st.session_state.get("tts_thread")
    if tts_t is not None and not tts_t.is_alive():
        st.session_state.tts_thread = None

    return changed


def _apply_ui_update(ui: dict) -> None:
    # Always apply active_town — including null (clears persona card).
    # Using "active_town" in ui to distinguish "not provided" from "set to null".
    if "active_town" in ui:
        st.session_state.active_town = ui["active_town"] or None
    if ui.get("highlight_towns"):
        st.session_state.highlight_towns = ui["highlight_towns"]
    chart = ui.get("chart", {})
    if chart and chart.get("chart_type", "none") != "none":
        st.session_state.current_chart_data = chart
    if ui.get("show_calculator"):
        st.session_state.show_calculator = True
    if ui.get("calculator_home_price"):
        try:
            price = int(ui["calculator_home_price"])
            # Clamp to slider range
            price = max(100_000, min(1_000_000, price))
            st.session_state.calculator_home_price = price
        except (ValueError, TypeError):
            pass
    if ui.get("show_listings"):
        st.session_state.show_listings = True


# ---------------------------------------------------------------------------
# Gemini TTS — persistent Live API session for fast text-to-speech
# ---------------------------------------------------------------------------
#
# Opening a new Gemini Live WebSocket per TTS call costs ~3-5 s just for
# the handshake.  We keep a SINGLE persistent session alive across calls
# on a dedicated background event loop.  First call still pays the setup,
# but subsequent calls skip it and only wait for audio generation (~2-4 s).
# If the session dies (timeout, network error), it reconnects automatically.
#
# Thread model:
#   _tts_event_loop  — runs forever in a daemon thread
#   _tts_session     — Gemini Live session living on that loop
#   _generate_penny_audio()  — called from ANY thread; submits a coroutine
#                              to the loop and waits for the result.

LIVE_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-native-audio-latest")

_TTS_SYSTEM_INSTRUCTION = (
    "You are Penny, a warm Connecticut Town Advisor. "
    "Read the following text aloud in a friendly, natural tone. "
    "Say ONLY what is given — do not add or change anything."
)

# ── Persistent event loop (one per process) ────────────────────────────────

_tts_event_loop: asyncio.AbstractEventLoop | None = None
_tts_loop_lock = threading.Lock()


def _ensure_tts_loop() -> asyncio.AbstractEventLoop:
    """Return the persistent TTS event loop, creating it if needed."""
    global _tts_event_loop
    with _tts_loop_lock:
        if _tts_event_loop is None or _tts_event_loop.is_closed():
            _tts_event_loop = asyncio.new_event_loop()
            t = threading.Thread(
                target=_tts_event_loop.run_forever,
                daemon=True,
                name="TTS-EventLoop",
            )
            t.start()
            print("[tts] event loop started")
    return _tts_event_loop


# ── Persistent Gemini Live session (lives on the event loop) ───────────────

_live_session = None
_live_cm = None  # async context manager returned by connect()


async def _get_or_create_session():
    """Return the live TTS session, connecting if needed."""
    global _live_session, _live_cm

    if _live_session is not None:
        return _live_session

    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
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


async def _close_tts_session():
    """Tear down the live session so the next call reconnects."""
    global _live_session, _live_cm
    if _live_cm is not None:
        try:
            await _live_cm.__aexit__(None, None, None)
        except Exception:
            pass
    _live_session = None
    _live_cm = None


async def _tts_generate(text: str) -> bytes | None:
    """Send text to the persistent Live session and return WAV bytes."""
    global _live_session

    session = await _get_or_create_session()
    try:
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

        if not audio_chunks:
            return None

        pcm = b"".join(audio_chunks)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)
            wf.writeframes(pcm)
        return buf.getvalue()

    except Exception as exc:
        print(f"[tts] session error ({exc}) — will reconnect next time")
        await _close_tts_session()
        return None


# ── Public API (callable from any thread) ──────────────────────────────────

def _generate_penny_audio(text: str) -> bytes | None:
    """Generate Penny's voice audio.  Reuses persistent Live API session."""
    if not text or len(text) < 5:
        return None
    loop = _ensure_tts_loop()
    future = asyncio.run_coroutine_threadsafe(_tts_generate(text), loop)
    try:
        return future.result(timeout=30)
    except Exception as exc:
        print(f"[tts] generation failed: {exc}")
        return None


def _prewarm_tts() -> None:
    """Open the Live session in the background so the first TTS call is fast."""
    loop = _ensure_tts_loop()
    asyncio.run_coroutine_threadsafe(_get_or_create_session(), loop)


# Pre-warm at import time — session will be ready by the time the user clicks
_prewarm_tts()


# ── Background TTS worker (non-blocking for Streamlit render) ──────────────

def _tts_background_worker(text: str, tts_q: queue.Queue) -> None:
    """Background thread: generates Penny's audio and puts it on a queue.

    Uses a thread-safe queue (NOT st.session_state) because Streamlit's
    session state is not safely writable from background threads.
    The main render loop drains tts_q and plays the audio.
    """
    try:
        wav = _generate_penny_audio(text)
        if wav:
            tts_q.put(wav)
            print(f"[tts-bg] audio ready ({len(wav):,} bytes)")
        else:
            print("[tts-bg] no audio returned")
    except Exception as exc:
        print(f"[tts-bg] failed: {exc}")


def _start_tts_background(text: str) -> None:
    """Kick off TTS generation in a daemon thread (non-blocking)."""
    if not text or len(text) < 5:
        return
    tts_q: queue.Queue = st.session_state.tts_queue
    t = threading.Thread(
        target=_tts_background_worker,
        args=(text, tts_q),
        daemon=True,
        name="PennyTTS",
    )
    t.start()
    st.session_state.tts_thread = t


# ---------------------------------------------------------------------------
# Voice → UI extraction (lightweight follow-up after Live API transcript)
# ---------------------------------------------------------------------------

def _extract_ui_from_voice(transcript: str) -> None:
    """Parse Penny's voice transcript to drive charts, persona, calculator.

    Makes a quick generate_content call that takes what Penny said and
    returns the matching ui_update JSON (chart, active_town, etc.).
    The voice_response is ignored — it's already in chat from the Live API.
    """
    if not transcript or len(transcript) < 10:
        return
    try:
        client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
        prompt = (
            "Penny (the CT Town Advisor) just gave this voice response to a "
            "user question.  Based on what she said, generate the matching "
            "ui_update JSON.  Set voice_response to an empty string — it is "
            "already displayed.\n\n"
            f'Penny said: "{transcript}"'
        )
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=build_context() + [
                types.Content(role="user", parts=[types.Part(text=prompt)])
            ],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
            ),
        )
        result = json.loads(response.text)
        ui = result.get("ui_update", {})
        if ui:
            _apply_ui_update(ui)
            print(f"[voice-ui] applied: active_town={ui.get('active_town')}, "
                  f"chart={ui.get('chart', {}).get('chart_type', 'none')}, "
                  f"calculator={ui.get('show_calculator')}, "
                  f"listings={ui.get('show_listings')}")
    except Exception as exc:
        print(f"[voice-ui] extraction failed: {exc}")


# ---------------------------------------------------------------------------
# Text query (direct generate_content — synchronous, fast path)
# ---------------------------------------------------------------------------

def _send_text_query(query: str) -> None:
    """Send text query via direct generate_content (always synchronous).
    The Live voice agent runs independently for microphone input only."""
    st.session_state.chat_history.append({"role": "user", "content": query})
    st.session_state.agent_state = "thinking"
    st.session_state.waiting_response = True
    _direct_generate(query)


def _direct_generate(query: str) -> None:
    """Call Gemini generate_content synchronously and apply the result."""
    try:
        client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
        user_turn = types.Content(
            role="user", parts=[types.Part(text=query)]
        )
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=build_context() + [user_turn],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
            ),
        )
        penny = json.loads(response.text)
        voice = penny.get("voice_response", "")
        ui    = penny.get("ui_update", {})
        if voice:
            st.session_state.chat_history.append(
                {"role": "assistant", "content": voice}
            )
            # Generate Penny's voice audio in background thread —
            # text + charts appear immediately, audio plays when ready.
            _start_tts_background(voice)
        if ui:
            _apply_ui_update(ui)
    except Exception as exc:
        st.session_state.chat_history.append(
            {"role": "assistant", "content": f"_(Error: {exc})_"}
        )
    finally:
        st.session_state.agent_state = "listening"
        st.session_state.waiting_response = False


def _send_audio_query(audio_bytes: bytes, mime_type: str = "audio/wav") -> None:
    """Send browser-recorded audio to Gemini generate_content (Cloud Run path).
    Audio is sent as inline_data alongside the system prompt and context."""
    st.session_state.agent_state = "thinking"
    st.session_state.waiting_response = True
    try:
        client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
        audio_part = types.Part(
            inline_data=types.Blob(mime_type=mime_type, data=audio_bytes)
        )
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=build_context() + [
                types.Content(role="user", parts=[
                    types.Part(text="(Voice message — transcribe and answer)"),
                    audio_part,
                ])
            ],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
            ),
        )
        penny = json.loads(response.text)
        voice = penny.get("voice_response", "")
        ui    = penny.get("ui_update", {})
        if voice:
            st.session_state.chat_history.append(
                {"role": "assistant", "content": voice}
            )
        if ui:
            _apply_ui_update(ui)
    except Exception as exc:
        st.session_state.chat_history.append(
            {"role": "assistant", "content": f"_(Audio error: {exc})_"}
        )
    finally:
        st.session_state.agent_state = "listening"
        st.session_state.waiting_response = False


# ---------------------------------------------------------------------------
# Plotly helpers
# ---------------------------------------------------------------------------

_CHART_COLORS = [ACCENT, "#00FF88", "#FFB300", "#FF6B35", "#9C27B0", "#FF4081"]
_DARK_LAYOUT  = dict(
    paper_bgcolor=BG,
    plot_bgcolor=CARD_BG,
    font=dict(color=TEXT, family="Inter, sans-serif"),
    margin=dict(t=44, b=36, l=32, r=20),
    legend=dict(
        orientation="h", yanchor="top", y=-0.18,
        xanchor="left", x=0, font=dict(size=11),
    ),
)


def _make_chart(chart: dict) -> go.Figure | None:
    """Convert Penny's chart dict → dark-themed Plotly Figure."""
    if not chart or chart.get("chart_type", "none") == "none":
        return None
    ctype    = chart.get("chart_type", "bar")
    x_labels = chart.get("x_labels", [])
    datasets = chart.get("datasets", [])
    title    = chart.get("title", "")

    fig = go.Figure()
    for i, ds in enumerate(datasets):
        c = _CHART_COLORS[i % len(_CHART_COLORS)]
        vals = [float(v) for v in ds.get("values", [])]
        if ctype == "bar":
            # Single dataset → per-bar town colors; multi-dataset → per-category color
            if len(datasets) == 1:
                marker_color = [
                    TOWN_COLORS.get(lbl, _CHART_COLORS[j % len(_CHART_COLORS)])
                    for j, lbl in enumerate(x_labels)
                ]
            else:
                marker_color = c
            fig.add_trace(go.Bar(
                name=ds.get("label", ""),
                x=x_labels, y=vals,
                marker_color=marker_color,
                text=[f"${v/1e6:.1f}M" if v >= 1e6 else f"{v:,.0f}"
                      for v in vals],
                textposition="outside",
                textfont=dict(size=10, color=TEXT),
            ))
        elif ctype == "pie":
            fig.add_trace(go.Pie(
                labels=x_labels, values=vals,
                marker=dict(colors=_CHART_COLORS[:len(vals)]),
                textfont=dict(color=TEXT),
            ))
        elif ctype == "radar":
            fig.add_trace(go.Scatterpolar(
                r=vals, theta=x_labels,
                fill="toself", name=ds.get("label", ""),
                line=dict(color=c),
            ))
    layout = dict(
        title=dict(text=title, font=dict(size=14, color=TEXT), x=0),
        barmode="group",
        **_DARK_LAYOUT,
    )
    if ctype == "radar":
        layout["polar"] = dict(
            bgcolor=CARD_BG,
            radialaxis=dict(visible=True, gridcolor=BORDER, color=MUTED),
            angularaxis=dict(gridcolor=BORDER, color=MUTED),
        )
    fig.update_layout(**layout)
    return fig


def _make_map(highlight_towns: list[str]) -> go.Figure:
    """Scatter mapbox of the three CT towns; highlighted ones glow."""
    towns = list(TOWN_COORDS.keys())
    lats  = [TOWN_COORDS[t][0] for t in towns]
    lons  = [TOWN_COORDS[t][1] for t in towns]
    colors = [TOWN_COLORS[t] if t in highlight_towns else "#334466"
              for t in towns]
    sizes  = [28 if t in highlight_towns else 15 for t in towns]

    fig = go.Figure(go.Scattermap(
        lat=lats, lon=lons,
        mode="markers+text",
        marker=dict(size=sizes, color=colors, opacity=0.9),
        text=towns,
        textposition="top center",
        textfont=dict(size=12, color=TEXT),
        hoverinfo="text",
    ))
    fig.update_layout(
        map=dict(
            style="carto-darkmatter",
            zoom=9.8,
            center=dict(lat=41.445, lon=-72.862),
        ),
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor=BG,
        height=260,
    )
    return fig


# ---------------------------------------------------------------------------
# Tax calculator
# ---------------------------------------------------------------------------

def _compute_tax(home_price: int, town_name: str) -> tuple[int, int]:
    """Return (annual_tax, monthly_tax) based on CT 70 % assessment ratio."""
    town = get_town_data(town_name)
    mill_rate = float(town.get("mill_rate") or 0)
    assessed  = home_price * CT_ASSESS_RATIO
    annual    = int(assessed * mill_rate / 1000)
    return annual, annual // 12


# ---------------------------------------------------------------------------
# Persona card
# ---------------------------------------------------------------------------

def _render_persona_card(town_name: str | None) -> None:
    if not town_name:
        st.markdown(
            '<div class="persona-empty">'
            '🏠 Ask Penny about a town to see its profile'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    town    = get_town_data(town_name)
    color   = TOWN_COLORS.get(town_name, ACCENT)
    avatar  = AVATAR_PATHS.get(town_name)
    mill    = town.get("mill_rate")
    budget  = town.get("total_budget", 0)
    edu_pct = (town.get("departments", {})
                   .get("education", {})
                   .get("percent", 0))

    budget_str = f"${budget/1e6:.0f}M" if budget else "N/A"
    mill_str   = f"{mill}" if mill else "N/A"

    # Embed avatar as base64 so the whole card is one HTML block,
    # keeping flexbox layout intact (multi-call approach breaks flex).
    # Cache the base64 strings in session state to avoid re-reading the
    # file on every Streamlit render (the polling loop re-renders every
    # 0.3 s and will exhaust OS file descriptors otherwise).
    img_html = ""
    if avatar and avatar.exists():
        cache_key = f"_avatar_b64_{town_name}"
        if cache_key not in st.session_state:
            st.session_state[cache_key] = base64.b64encode(
                avatar.read_bytes()
            ).decode()
        img_b64 = st.session_state[cache_key]
        img_html = (
            f'<img src="data:image/png;base64,{img_b64}" '
            f'width="150" style="border-radius:12px;margin-bottom:8px" />'
        )

    st.markdown(f"""
<div class="persona-card" style="box-shadow:0 0 20px {color}44;border-color:{color}66;">
  {img_html}
  <div style="font-size:1.15rem;font-weight:700;margin:8px 0 2px">{town_name}</div>
  <div style="font-size:0.78rem;color:{color};margin-bottom:10px">{town.get("persona","")}</div>
  <div class="stat-row">
    <div class="stat-item">
      <div class="stat-val">{mill_str}</div>
      <div class="stat-lbl">Mill Rate</div>
    </div>
    <div class="stat-item">
      <div class="stat-val">{budget_str}</div>
      <div class="stat-lbl">Total Budget</div>
    </div>
    <div class="stat-item">
      <div class="stat-val">{edu_pct}%</div>
      <div class="stat-lbl">Education</div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Zillow listings
# ---------------------------------------------------------------------------

# Zillow search URL slug per town
_ZILLOW_SLUGS: dict[str, str] = {
    "Wallingford": "wallingford-ct",
    "North Haven": "north-haven-ct",
    "Cheshire":    "cheshire-ct",
}


def _render_listings(focus_town: str | None) -> None:
    """Show Zillow listing links + median home price for each town."""
    st.markdown(
        '<div class="section-header">🏡 Homes for Sale</div>',
        unsafe_allow_html=True,
    )

    # Determine which towns to show — focus town first, then the rest
    all_names = [t["town"] for t in get_all_towns()]
    if focus_town and focus_town in all_names:
        ordered = [focus_town] + [t for t in all_names if t != focus_town]
    else:
        ordered = all_names

    cards_html = ""
    for town_name in ordered:
        town = get_town_data(town_name)
        color = TOWN_COLORS.get(town_name, ACCENT)
        slug = _ZILLOW_SLUGS.get(town_name, town_name.lower().replace(" ", "-") + "-ct")
        zillow_url = f"https://www.zillow.com/{slug}/"
        median = town.get("median_home_price", 0)
        median_str = f"${median:,}" if median else "N/A"
        mill = town.get("mill_rate", 0)
        is_focus = town_name == focus_town

        # Estimate annual tax for median home
        assessed = median * CT_ASSESS_RATIO
        annual_tax = int(assessed * float(mill) / 1000) if mill else 0
        tax_str = f"${annual_tax:,}/yr" if annual_tax else "N/A"

        border_style = f"border-color:{color}66;" if is_focus else ""
        glow_style = f"box-shadow:0 0 12px {color}33;" if is_focus else ""

        cards_html += f"""
<a href="{zillow_url}" target="_blank" rel="noopener"
   style="text-decoration:none;color:inherit;display:block">
<div style="background:{CARD_BG};border-radius:12px;padding:14px 16px;
            border:1px solid {BORDER};margin-bottom:8px;
            transition:all 0.2s;cursor:pointer;{border_style}{glow_style}">
  <div style="display:flex;justify-content:space-between;align-items:center">
    <div>
      <span style="font-weight:700;font-size:0.95rem;color:{color}">{town_name}</span>
      <div style="font-size:0.72rem;color:{MUTED};margin-top:2px">
        Median: {median_str} · Tax: {tax_str} · Mill rate: {mill}
      </div>
    </div>
    <div style="font-size:0.78rem;color:{ACCENT};white-space:nowrap">
      View on Zillow →
    </div>
  </div>
</div>
</a>"""

    st.markdown(cards_html, unsafe_allow_html=True)
    st.markdown(
        f'<div style="font-size:0.68rem;color:{MUTED};margin-top:4px;text-align:center">'
        f'Median prices from town budget data · Click a town to browse Zillow</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

def _render_header() -> None:
    state  = st.session_state.agent_state
    icon, label, color = STATUS_CONFIG.get(state, STATUS_CONFIG["ready"])

    h_col, s_col = st.columns([4, 1])
    with h_col:
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:12px;padding:4px 0">'
            f'  <span style="font-size:2rem">🏠</span>'
            f'  <div>'
            f'    <h1 style="margin:0;font-size:1.75rem;color:{TEXT}">Penny</h1>'
            f'    <p style="margin:0;font-size:0.83rem;color:{MUTED}">'
            f'      CT Town Advisor · Powered by Gemini</p>'
            f'  </div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with s_col:
        st.markdown(
            f'<div style="text-align:right;padding-top:12px">'
            f'  <span class="status-pill" '
            f'        style="color:{color};border-color:{color}44;'
            f'               background:{color}11">'
            f'    {icon} {label}'
            f'  </span>'
            f'</div>',
            unsafe_allow_html=True,
        )
    st.markdown(
        f'<hr style="border:1px solid {BORDER};margin:8px 0 16px">',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    _inject_css()
    _init_session_state()

    # Track re-runs to diagnose WebSocket disconnects
    if "rerun_count" not in st.session_state:
        st.session_state.rerun_count = 0
    st.session_state.rerun_count += 1
    print(f"[streamlit] render #{st.session_state.rerun_count}")

    # PennyAgent uses pyaudio which requires a real audio device.
    # On Cloud Run (and Docker with K_SERVICE set) there is no audio hardware —
    # voice input is handled by the browser WebSocket component instead.
    if not IS_CLOUD_RUN:
        _init_agent()

    # Drain any pending agent callbacks (no-op on Cloud Run)
    _drain_queue()

    _render_header()

    col_left, col_right = st.columns([55, 45])

    # ── LEFT COLUMN ────────────────────────────────────────────────────────
    with col_left:

        # Persona card
        _render_persona_card(st.session_state.active_town)

        # Starter chips
        st.markdown('<div class="section-header">Quick questions</div>',
                    unsafe_allow_html=True)
        chip_cols = st.columns(2)
        for idx, q_text in enumerate(STARTERS):
            with chip_cols[idx % 2]:
                if st.button(q_text, key=f"chip_{idx}", use_container_width=True):
                    st.session_state.pending_query = q_text

        st.markdown(
            f'<hr style="border:1px solid {BORDER};margin:12px 0">',
            unsafe_allow_html=True,
        )

        # Chat history (last 5 exchanges)
        history = st.session_state.chat_history[-10:]  # last 5 pairs
        if history:
            st.markdown('<div class="chat-wrap">', unsafe_allow_html=True)
            for msg in history:
                if msg["role"] == "user":
                    st.markdown(
                        f'<div class="chat-label">You</div>'
                        f'<div class="chat-bubble-user">{msg["content"]}</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        f'<div class="chat-label" '
                        f'     style="color:{ACCENT}">Penny</div>'
                        f'<div class="chat-bubble-penny">{msg["content"]}</div>',
                        unsafe_allow_html=True,
                    )
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.markdown(
                f'<div style="color:{MUTED};font-size:0.85rem;'
                f'            text-align:center;padding:20px 0">'
                f'Ask Penny anything about CT towns 👆</div>',
                unsafe_allow_html=True,
            )

        # ── Penny's voice playback (Gemini TTS) ──────────────────────────
        pending_audio = st.session_state.pop("pending_audio", None) \
            if st.session_state.get("pending_audio") else None
        if pending_audio:
            st.audio(pending_audio, format="audio/wav", autoplay=True)

        # ── Voice input ───────────────────────────────────────────────────
        if IS_CLOUD_RUN:
            # Cloud Run: browser WebSocket audio component
            # Browser mic → WebSocket → FastAPI → Gemini Live
            voice_result = _audio_ws_component(key="voice_ws", default=None)
            if (
                voice_result is not None
                and voice_result.get("type") == "turn_complete"
                and voice_result.get("turn_id", -1)
                    > st.session_state.last_voice_turn_id
            ):
                st.session_state.last_voice_turn_id = voice_result["turn_id"]
                text = voice_result.get("text", "").strip()
                if text:
                    st.session_state.chat_history.append(
                        {"role": "assistant", "content": text}
                    )
                    # Extract UI updates (chart, persona, calculator) from
                    # the voice transcript via a quick generate_content call.
                    _extract_ui_from_voice(text)
                    # Do NOT call st.rerun() here.
                    # setComponentValue already triggers a Streamlit re-run.
                    # A second st.rerun() causes a double re-render that can
                    # reload the component iframe and kill the WebSocket.
        else:
            # Local: pyaudio mic streaming via PennyAgent background thread
            input_cols = st.columns([1, 5])
            with input_cols[0]:
                mic_label = "🎙️" if not st.session_state.mic_active else "🔴"
                pulse_cls = "mic-pulse" if st.session_state.mic_active else ""
                st.markdown(f'<div class="{pulse_cls}">', unsafe_allow_html=True)
                if st.button(mic_label, key="mic_btn", help="Toggle microphone"):
                    st.session_state.mic_active = not st.session_state.mic_active
                    st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)

        # ── Text input ────────────────────────────────────────────────────
        user_input = st.chat_input(
            placeholder="Ask about CT towns…",
            key="chat_input",
        )

        # Resolve query (text input or starter chip)
        pending = st.session_state.pop("pending_query", None) \
            if "pending_query" in st.session_state else None
        query = user_input or pending
        if query:
            _send_text_query(query)
            st.rerun()

    # ── RIGHT COLUMN ───────────────────────────────────────────────────────
    with col_right:

        # Chart panel
        st.markdown('<div class="section-header">Chart</div>',
                    unsafe_allow_html=True)
        chart_data = st.session_state.current_chart_data
        fig = _make_chart(chart_data) if chart_data else None
        if fig:
            st.plotly_chart(fig, width="stretch",
                            config={"displayModeBar": False})
        else:
            st.markdown(
                f'<div style="background:{CARD_BG};border:1px dashed {BORDER};'
                f'border-radius:14px;padding:28px;text-align:center;'
                f'color:{MUTED};font-size:0.85rem">'
                f'Charts appear here when Penny compares towns.<br>'
                f'<span style="opacity:0.6">Try: "Compare education spending"</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

        st.markdown(
            f'<hr style="border:1px solid {BORDER};margin:12px 0">',
            unsafe_allow_html=True,
        )

        # CT town map
        st.markdown('<div class="section-header">CT Towns</div>',
                    unsafe_allow_html=True)
        highlight = st.session_state.highlight_towns
        st.plotly_chart(
            _make_map(highlight),
            width="stretch",
            config={"displayModeBar": False},
        )

        # Tax calculator (visible when Penny sets show_calculator)
        if st.session_state.show_calculator:
            st.markdown(
                f'<hr style="border:1px solid {BORDER};margin:12px 0">',
                unsafe_allow_html=True,
            )
            st.markdown('<div class="section-header">🧮 Tax Calculator</div>',
                        unsafe_allow_html=True)
            st.markdown('<div class="calc-panel">', unsafe_allow_html=True)

            default_price = st.session_state.get("calculator_home_price", 400_000)
            home_price = st.slider(
                "Home value",
                min_value=100_000,
                max_value=1_000_000,
                value=default_price,
                step=10_000,
                format="$%d",
                key="calc_price",
            )
            all_towns  = [t["town"] for t in get_all_towns()]
            default_ix = (
                all_towns.index(st.session_state.active_town)
                if st.session_state.active_town in all_towns else 0
            )
            calc_town = st.selectbox(
                "Town",
                options=all_towns,
                index=default_ix,
                key="calc_town",
            )
            annual, monthly = _compute_tax(home_price, calc_town)
            m1, m2 = st.columns(2)
            m1.metric("Annual Tax",  f"${annual:,}")
            m2.metric("Monthly Tax", f"${monthly:,}")

            mill = get_town_data(calc_town).get("mill_rate")
            st.markdown(
                f'<div style="font-size:0.72rem;color:{MUTED};margin-top:8px">'
                f'Mill rate {mill} · Assessed at 70% FMV</div>',
                unsafe_allow_html=True,
            )
            st.markdown("</div>", unsafe_allow_html=True)

        # Listings panel (visible when Penny sets show_listings)
        if st.session_state.show_listings:
            st.markdown(
                f'<hr style="border:1px solid {BORDER};margin:12px 0">',
                unsafe_allow_html=True,
            )
            _render_listings(st.session_state.active_town)

    # ── Polling — keep UI live while agent is active or TTS is generating ──
    tts_t = st.session_state.get("tts_thread")
    tts_running = tts_t is not None and tts_t.is_alive()
    if st.session_state.waiting_response or \
       st.session_state.agent_state in ("thinking", "speaking") or \
       tts_running:
        time.sleep(0.3)
        st.rerun()


if __name__ == "__main__":
    main()
