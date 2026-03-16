"""
gen_arch.py — generate penny_architecture.png
Run: python gen_arch.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import matplotlib.patheffects as pe

# ── Palette ────────────────────────────────────────────────────────────────
BG       = "#0a0e1a"
CARD     = "#0f1525"
BORDER   = "#1a2a4a"
ACCENT   = "#00d4ff"
GREEN    = "#00FF88"
AMBER    = "#FFB300"
PURPLE   = "#9C27B0"
BLUE     = "#2196F3"
MUTED    = "#8899aa"
TEXT     = "#e0e6f0"
TEXT_DIM = "#7a8fa8"

fig, ax = plt.subplots(figsize=(18, 11))
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)
ax.set_xlim(0, 18)
ax.set_ylim(0, 11)
ax.axis("off")


# ── Helper functions ────────────────────────────────────────────────────────

def card(x, y, w, h, label, sublabel="", color=ACCENT, icon=""):
    """Draw a rounded card."""
    box = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.08",
        linewidth=1.2,
        edgecolor=color + "88",
        facecolor=CARD,
        zorder=3,
    )
    ax.add_patch(box)
    # glow border
    glow = FancyBboxPatch(
        (x - 0.02, y - 0.02), w + 0.04, h + 0.04,
        boxstyle="round,pad=0.1",
        linewidth=0.5,
        edgecolor=color + "33",
        facecolor="none",
        zorder=2,
    )
    ax.add_patch(glow)

    cy = y + h / 2
    if icon:
        ax.text(x + 0.22, cy + (0.12 if sublabel else 0), icon,
                ha="center", va="center", fontsize=13, zorder=5)
        tx = x + 0.5
    else:
        tx = x + w / 2

    ha = "left" if icon else "center"
    ax.text(tx, cy + (0.13 if sublabel else 0), label,
            ha=ha, va="center", fontsize=8.5, fontweight="bold",
            color=TEXT, zorder=5)
    if sublabel:
        ax.text(tx, cy - 0.17, sublabel,
                ha=ha, va="center", fontsize=6.8,
                color=TEXT_DIM, zorder=5)


def section_label(x, y, text):
    ax.text(x, y, text, ha="left", va="center",
            fontsize=7, fontweight="bold",
            color=MUTED, style="italic",
            letter_spacing=1,
            zorder=5)


def arrow(x1, y1, x2, y2, color=ACCENT, label="", style="->"):
    ax.annotate(
        "", xy=(x2, y2), xytext=(x1, y1),
        arrowprops=dict(
            arrowstyle=style,
            color=color + "cc",
            lw=1.4,
            connectionstyle="arc3,rad=0.0",
        ),
        zorder=4,
    )
    if label:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        ax.text(mx + 0.05, my + 0.08, label,
                ha="left", va="bottom",
                fontsize=6.5, color=color + "bb", zorder=6)


def h_line(y, color=BORDER):
    ax.axhline(y, color=color, linewidth=0.5, alpha=0.4, zorder=1)


# ── Title ───────────────────────────────────────────────────────────────────
ax.text(9, 10.55, "Penny — CT Town Advisor",
        ha="center", va="center",
        fontsize=18, fontweight="bold", color=TEXT, zorder=5)
ax.text(9, 10.2, "System Architecture  ·  Gemini 2.5 Flash  ·  Live API  ·  Streamlit  ·  FastAPI",
        ha="center", va="center",
        fontsize=8.5, color=MUTED, zorder=5)

# ── Row 1: User inputs ──────────────────────────────────────────────────────
section_label(0.2, 9.75, "USER")
card(0.4,  9.2, 3.2, 0.9,  "Text Input",       "Type questions in chat",      ACCENT, "⌨️")
card(4.3,  9.2, 3.2, 0.9,  "Voice Input",       "Browser mic (Cloud Run)",     GREEN,  "🎙️")
card(8.2,  9.2, 3.2, 0.9,  "Quick Questions",   "One-click starter chips",     AMBER,  "⚡")
card(12.1, 9.2, 5.5, 0.9,  "Voice Output",      "Penny speaks via Gemini TTS", PURPLE, "🔊")

# ── Row 2: Streamlit frontend ────────────────────────────────────────────────
section_label(0.2, 8.6, "FRONTEND")
card(0.4, 7.75, 17.2, 1.1, "", color=BLUE)
# inner items
items = [
    (1.0,  8.2, "💬 Chat UI"),
    (3.6,  8.2, "🗺️ Mapbox Map"),
    (6.2,  8.2, "📊 Plotly Charts"),
    (9.0,  8.2, "🏠 Persona Cards"),
    (11.8, 8.2, "🧮 Tax Calculator"),
    (14.4, 8.2, "🏡 Zillow Listings"),
]
for xi, yi, txt in items:
    ax.text(xi, yi, txt, ha="left", va="center",
            fontsize=8, color=TEXT, fontweight="bold", zorder=6)
ax.text(9, 7.9, "app/main.py  ·  Streamlit  ·  dark-theme Plotly  ·  st_components for JS injection",
        ha="center", va="center", fontsize=7, color=TEXT_DIM, zorder=6)

# ── Arrows from user row to frontend ────────────────────────────────────────
arrow(2.0,  9.2,  2.0,  8.85,  ACCENT)
arrow(5.9,  9.2,  5.9,  8.85,  GREEN)
arrow(9.8,  9.2,  9.8,  8.85,  AMBER)
arrow(14.85, 9.2, 14.85, 8.85, PURPLE)

# ── Row 3: Three processing paths ────────────────────────────────────────────
section_label(0.2, 7.25, "PROCESSING PATHS")

# Path A — Text (generate_content)
card(0.4, 6.1, 3.8, 1.4,
     "Text Query Path",
     "generate_content (synchronous)",
     ACCENT, "📝")
ax.text(0.65, 6.75, "gemini-2.5-flash", fontsize=7, color=ACCENT + "cc", zorder=6)
ax.text(0.65, 6.52, "JSON: {voice_response, ui_update}", fontsize=6.5, color=TEXT_DIM, zorder=6)
ax.text(0.65, 6.32, "→ charts, calculator, persona card", fontsize=6.5, color=TEXT_DIM, zorder=6)

# Path B — Voice (Live API via WebSocket proxy)
card(5.0, 6.1, 5.2, 1.4,
     "Voice Streaming Path",
     "Browser → FastAPI → Gemini Live API",
     GREEN, "🎙️")
ax.text(5.25, 6.75, "api/main.py  ·  FastAPI WebSocket proxy", fontsize=7, color=GREEN + "cc", zorder=6)
ax.text(5.25, 6.52, "PCM 16kHz mic → Gemini Live → PCM 24kHz", fontsize=6.5, color=TEXT_DIM, zorder=6)
ax.text(5.25, 6.32, "Transcript → UI extraction (generate_content)", fontsize=6.5, color=TEXT_DIM, zorder=6)

# Path C — TTS session (persistent)
card(11.0, 6.1, 6.0, 1.4,
     "TTS Session Path",
     "src/tts_session.py  (persistent, pre-warmed)",
     AMBER, "🔊")
ax.text(11.25, 6.75, "Persistent asyncio loop (runs once via import cache)", fontsize=7, color=AMBER + "cc", zorder=6)
ax.text(11.25, 6.52, "Gemini Live send_client_content → PCM 24kHz", fontsize=6.5, color=TEXT_DIM, zorder=6)
ax.text(11.25, 6.32, "start_background() → queue.Queue → st.audio(autoplay)", fontsize=6.5, color=TEXT_DIM, zorder=6)

# Arrows frontend → paths
arrow(2.0,  7.75, 2.0,  7.5,  ACCENT, "text query")
arrow(7.0,  7.75, 7.0,  7.5,  GREEN,  "PCM audio")
arrow(14.85, 7.75, 14.85, 7.5, AMBER, "TTS text")

# ── Row 4: Gemini API ────────────────────────────────────────────────────────
section_label(0.2, 5.65, "GEMINI API")

card(0.4,  4.85, 3.8, 1.15, "gemini-2.5-flash",    "generate_content · sync text",      ACCENT, "✨")
card(5.0,  4.85, 5.2, 1.15, "gemini-2.5-flash-native-audio-latest",
                                                     "Live API · voice streaming",         GREEN,  "🎧")
card(11.0, 4.85, 4.0, 1.15, "gemini-2.5-flash-native-audio-latest",
                                                     "Live API · TTS (send_client_content)",AMBER, "🔉")
card(15.2, 4.85, 2.4, 1.15, "imagen-4.0-fast",      "generate_images · avatars",         PURPLE, "🎨")

# Arrows paths → Gemini
arrow(2.0,  6.1,  2.0,  6.0,  ACCENT)
arrow(7.0,  6.1,  7.0,  6.0,  GREEN)
arrow(14.85, 6.1, 14.85, 6.0, AMBER)

# ── Row 5: Source builder / context ─────────────────────────────────────────
section_label(0.2, 4.35, "CONTEXT & DATA")

card(0.4,  3.55, 4.0, 1.15, "context_builder.py",
     "system prompt  ·  SYSTEM_PROMPT (module-level)", BLUE, "📋")
ax.text(0.65, 3.9,  "All 3 town JSON files embedded in prompt",  fontsize=6.5, color=TEXT_DIM, zorder=6)
ax.text(0.65, 3.7,  "Mill rates · budgets · personas · key facts", fontsize=6.5, color=TEXT_DIM, zorder=6)

card(4.8,  3.55, 3.8, 1.15, "data/json/",
     "cheshire · north_haven · wallingford", BLUE + "88", "📁")
ax.text(5.05, 3.9,  "town, budget_year, total_budget",           fontsize=6.5, color=TEXT_DIM, zorder=6)
ax.text(5.05, 3.7,  "mill_rate, departments, key_facts …",       fontsize=6.5, color=TEXT_DIM, zorder=6)

card(8.9,  3.55, 3.6, 1.15, "data/pdf/",
     "CT budget PDFs (FY2025)", BLUE + "88", "📄")
ax.text(9.15, 3.9,  "Source documents",                          fontsize=6.5, color=TEXT_DIM, zorder=6)
ax.text(9.15, 3.7,  "extract_town_data.py → JSON",               fontsize=6.5, color=TEXT_DIM, zorder=6)

card(12.8, 3.55, 4.8, 1.15, "app/assets/",
     "AI-generated town avatars (Imagen)", PURPLE + "88", "🖼️")
ax.text(13.05, 3.9, "cheshire_avatar.png",                       fontsize=6.5, color=TEXT_DIM, zorder=6)
ax.text(13.05, 3.7, "north_haven_avatar.png · wallingford_avatar.png", fontsize=6.5, color=TEXT_DIM, zorder=6)

# Context → text path
arrow(2.4, 4.85, 2.4, 4.7, BLUE)
arrow(6.7, 4.85, 6.7, 4.7, BLUE + "66")

# ── Row 6: Response schema box ───────────────────────────────────────────────
section_label(0.2, 3.05, "RESPONSE SCHEMA")

schema_box = FancyBboxPatch(
    (0.4, 1.85), 17.2, 1.35,
    boxstyle="round,pad=0.08",
    linewidth=1,
    edgecolor=ACCENT + "44",
    facecolor="#060c18",
    zorder=3,
)
ax.add_patch(schema_box)

schema_text = (
    '{ "voice_response": "<≤3 sentences Penny says aloud — always cites a real number>",\n'
    '  "ui_update": { "active_town": "Wallingford",  "highlight_towns": ["Wallingford"],\n'
    '                 "chart": { "chart_type": "bar|pie|radar|none", "title": "...", "x_labels": [...], "datasets": [...] },\n'
    '                 "show_listings": false,  "show_calculator": true,  "calculator_home_price": 500000 } }'
)
ax.text(0.65, 3.08, schema_text,
        ha="left", va="top",
        fontsize=7.2, color=ACCENT + "dd",
        fontfamily="monospace", zorder=6,
        linespacing=1.6)

# ── Row 7: Deployment & tech stack ───────────────────────────────────────────
section_label(0.2, 1.6, "DEPLOYMENT & TECH STACK")

techs = [
    (0.4,  "🚀 Cloud Run",    "2 vCPU · 2 GiB · min 1 / max 3"),
    (3.5,  "🐳 Docker",       "Multi-stage Python 3.11"),
    (6.6,  "🔒 Secret Mgr",   "GOOGLE_API_KEY"),
    (9.7,  "🔀 nginx",        ":8080 → :8501 + :8081"),
    (12.8, "🧪 pytest",       "6 test modules · 92 tests"),
    (15.5, "⚡ FastAPI",       "uvicorn · async WebSocket"),
]
for xi, title, sub in techs:
    card(xi, 0.35, 2.8, 1.1, title, sub, MUTED, "")

plt.tight_layout(pad=0)
plt.savefig(
    "/Users/karthikishoresounder/Documents/AI_Projects/ct-town-advisor/penny_architecture.png",
    dpi=150,
    bbox_inches="tight",
    facecolor=BG,
    edgecolor="none",
)
print("Saved penny_architecture.png")
