"""
context_builder.py
------------------
Loads all three CT town JSON files and builds Penny's Gemini system prompt
with all town data embedded.  Also provides helper accessors for town data.

Public API
----------
  SYSTEM_PROMPT                          module-level str (lazy-built on import)
  build_system_prompt() -> str           rebuild from disk
  build_context()       -> list[Content] empty list; all context lives in system prompt
  get_town_data(name)   -> dict          single town dict
  get_all_towns()       -> list[dict]    all three town dicts

  # Legacy compatibility (used by app/main.py before JSON migration)
  build_content_array_from_uris(entries) -> list[Content]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from google.genai import types

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
JSON_DIR = ROOT / "data" / "json"

_TOWN_FILES = {
    "Cheshire":   "cheshire.json",
    "North Haven": "north_haven.json",
    "Wallingford": "wallingford.json",
}


def _load_all_towns() -> list[dict]:
    towns = []
    for town_name, filename in _TOWN_FILES.items():
        path = JSON_DIR / filename
        data = json.loads(path.read_text())
        towns.append(data)
    return towns


# Loaded once at import time; re-loadable via build_system_prompt()
_TOWNS: list[dict] = _load_all_towns()
_TOWN_INDEX: dict[str, dict] = {t["town"]: t for t in _TOWNS}


# ---------------------------------------------------------------------------
# System prompt builder
# ---------------------------------------------------------------------------
_RESPONSE_SCHEMA = """\
{
  "voice_response": "<string: what Penny says out loud — max 3 sentences, warm \
and conversational, always references real numbers from the data>",
  "ui_update": {
    "active_town": "<string: the single town being focused on, or null>",
    "highlight_towns": ["<town1>", "<town2>"],
    "chart": {
      "chart_type": "<bar|pie|radar|none>",
      "title": "<string>",
      "x_labels": ["<label1>", "<label2>"],
      "datasets": [
        {"label": "<dataset label>", "values": [0, 0, 0]}
      ]
    },
    "show_listings": false,
    "show_calculator": false
  }
}"""


def _format_town_block(t: dict) -> str:
    """Render one town dict as a compact, readable block for the system prompt."""
    depts = t.get("departments", {})
    dept_lines = "\n".join(
        f"    {k}: ${v['amount']:,} ({v['percent']}%)"
        for k, v in depts.items()
        if v.get("amount") is not None
    )
    facts  = "\n".join(f"  - {f}" for f in t.get("key_facts", []))
    strengths  = "\n".join(f"  + {s}" for s in t.get("strengths", []))
    weaknesses = "\n".join(f"  - {w}" for w in t.get("weaknesses", []))

    return f"""\
### {t['town']} — {t.get('persona', '')}
- Budget year : {t.get('budget_year')}
- Total budget: ${t.get('total_budget', 0):,}
- Mill rate   : {t.get('mill_rate')} mills
- Median home : ${t.get('median_home_price', 0):,}
- Population  : {t.get('population', 0):,}
- Persona desc: {t.get('persona_description', '')}

Department spending:
{dept_lines}

Key facts:
{facts}

Strengths:
{strengths}

Weaknesses:
{weaknesses}"""


def build_system_prompt() -> str:
    """Build (or rebuild) the full Penny system prompt with all town data embedded."""
    global _TOWNS, _TOWN_INDEX
    _TOWNS = _load_all_towns()
    _TOWN_INDEX = {t["town"]: t for t in _TOWNS}

    town_blocks = "\n\n".join(_format_town_block(t) for t in _TOWNS)
    town_names  = ", ".join(t["town"] for t in _TOWNS)

    return f"""\
You are Penny, a warm, knowledgeable, and friendly Connecticut Town Advisor.
Your job is to help people decide where to live in CT by explaining town \
budgets, taxes, and services in a way that is clear, honest, and encouraging.

## Your personality
- Warm, approachable, and upbeat — moving is exciting!
- You speak in short, conversational sentences. Never more than 3 sentences \
per response.
- You have a slight New England charm.
- You are grounded in real budget data and NEVER make up or estimate numbers \
that are not in the data below.

## Towns you know about
{town_names}

## Town data (authoritative — use only these numbers)
{town_blocks}

## CRITICAL: Response format
You MUST ALWAYS respond with a valid JSON object and nothing else — no prose \
outside the JSON, no markdown fences. Use exactly this structure:

{_RESPONSE_SCHEMA}

## Rules you must always follow
1. ONLY use numbers and facts from the town data above. Never hallucinate \
figures.
2. voice_response must be ≤ 3 sentences. Be warm, cite a real number.
3. When comparing two or more towns, always include a chart \
(chart_type != "none").
4. When the user asks about homes, buying, renting, or neighborhoods, \
set show_listings to true.
5. When the user asks about taxes, mill rate, or property tax calculations, \
set show_calculator to true.
6. highlight_towns must list every town mentioned in your response.
7. active_town is the single town being focused on; null if comparing multiple.
8. If no chart is relevant, set chart_type to "none" and leave x_labels \
and datasets as empty arrays.
9. chart values must be plain numbers (no commas, no $ symbols).
"""


# ---------------------------------------------------------------------------
# Public accessors
# ---------------------------------------------------------------------------

def build_context() -> list[types.Content]:
    """
    Return an empty content list.

    All context is embedded in SYSTEM_PROMPT / build_system_prompt().
    Pass that string as system_instruction to GenerateContentConfig.

    Usage:
        contents = build_context() + [user_turn]   # → [user_turn]
        response = client.models.generate_content(
            model=MODEL,
            contents=contents,
            config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
        )
    """
    return []


def get_town_data(town_name: str) -> dict:
    """Return the dict for a single town (case-sensitive match on 'town' field)."""
    if town_name not in _TOWN_INDEX:
        available = list(_TOWN_INDEX.keys())
        raise KeyError(f"Town '{town_name}' not found. Available: {available}")
    return _TOWN_INDEX[town_name]


def get_all_towns() -> list[dict]:
    """Return a list of all three town dicts."""
    return list(_TOWNS)


# ---------------------------------------------------------------------------
# Legacy compatibility — used by app/main.py (PDF path)
# ---------------------------------------------------------------------------

def build_content_array_from_uris(
    enriched_entries: list[dict[str, str]],
) -> list[types.Content]:
    """
    Legacy helper: builds a content array from Gemini File API URI entries.

    Kept for backward compatibility with app/main.py's PDF-based flow.
    New code should use build_context() + system_instruction instead.
    """
    parts: list[types.Part] = []
    for entry in enriched_entries:
        parts.append(
            types.Part(
                file_data=types.FileData(
                    mime_type="application/pdf",
                    file_uri=entry["file_uri"],
                )
            )
        )
        parts.append(
            types.Part(text=f"[The PDF above contains budget data for: {entry['town_name']}]")
        )
    return [types.Content(role="user", parts=parts)]


# ---------------------------------------------------------------------------
# Voice system prompt (natural speech — no JSON format)
# ---------------------------------------------------------------------------

def build_voice_system_prompt() -> str:
    """Natural-speech prompt for the native-audio Live API path (no JSON)."""
    town_blocks = "\n\n".join(_format_town_block(t) for t in _TOWNS)
    town_names  = ", ".join(t["town"] for t in _TOWNS)
    return f"""\
You are Penny, a warm, knowledgeable Connecticut Town Advisor.
Help people decide where to live in CT by explaining town budgets, taxes,
and services in a clear, honest, and encouraging way.

## Your personality
- Warm, approachable, and upbeat.
- Speak in short, conversational sentences. Never more than 3 sentences.
- You have a slight New England charm.
- Always ground answers in the real budget data below. Never make up numbers.

## Towns you know about
{town_names}

## Town data (authoritative — use only these numbers)
{town_blocks}

## Rules
1. ONLY use numbers and facts from the town data above.
2. Keep answers to ≤ 3 sentences. Be warm and cite a real number.
3. If information is not in the data, say so clearly.
"""


# ---------------------------------------------------------------------------
# Module-level constants (lazy-built once on import)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT: str = build_system_prompt()
VOICE_SYSTEM_PROMPT: str = build_voice_system_prompt()

print(f"✅ Context built for {len(_TOWNS)} towns: "
      f"{', '.join(t['town'] for t in _TOWNS)}!")
