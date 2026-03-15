"""
chart_builder.py
----------------
Utility helpers for validating and post-processing Plotly chart JSON
returned by the Gemini `return_chart` tool call.
"""

from __future__ import annotations

import json


REQUIRED_PLOTLY_KEYS = {"data"}


def is_valid_chart(chart_dict: dict) -> bool:
    """Basic sanity check — Plotly figure must have a 'data' list."""
    return bool(chart_dict) and REQUIRED_PLOTLY_KEYS.issubset(chart_dict.keys())


def apply_ct_theme(chart_dict: dict) -> dict:
    """
    Apply a consistent Connecticut-branded colour theme to any Plotly figure.
    Mutates and returns the dict.
    """
    layout = chart_dict.setdefault("layout", {})
    layout.setdefault("template", "plotly_white")
    layout.setdefault("font", {"family": "Inter, sans-serif", "color": "#1a1a2e"})
    layout.setdefault("paper_bgcolor", "#f8f9fa")
    layout.setdefault("plot_bgcolor", "#ffffff")

    # CT state colours: navy + gold
    ct_colors = ["#002868", "#BF0A30", "#f4a300", "#4e9af1", "#6dbf67"]
    for trace in chart_dict.get("data", []):
        if "marker" in trace and "color" not in trace["marker"]:
            trace["marker"]["color"] = ct_colors[0]

    return chart_dict


def chart_from_json_string(raw_json: str) -> dict | None:
    """
    Parse a raw JSON string into a validated + themed Plotly figure dict.
    Returns None if parsing or validation fails.
    """
    try:
        chart = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError):
        return None

    if not is_valid_chart(chart):
        return None

    return apply_ct_theme(chart)
