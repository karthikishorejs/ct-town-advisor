"""
chart_parser.py
---------------
Parses Gemini's raw text response to extract an optional chart JSON block
appended at the end inside a ```json ... ``` fence.

Public API:
    parse_response(raw: str) -> tuple[str, ChartData | None]
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field


# Matches a ```json ... ``` block at the end of the response (with optional
# trailing whitespace). The block must be the last thing in the string.
_CHART_PATTERN = re.compile(
    r"```json\s*(\{.*?\})\s*```\s*$",
    re.DOTALL,
)


@dataclass
class Dataset:
    label: str
    values: list[float]


@dataclass
class ChartData:
    chart_type: str
    title: str
    x_labels: list[str]
    datasets: list[Dataset]
    highlight_towns: list[str] = field(default_factory=list)


def parse_response(raw: str) -> tuple[str, ChartData | None]:
    """
    Parse a raw Gemini text response into clean text and optional ChartData.

    Args:
        raw: The full text response from Gemini, potentially containing a
             ```json { ... } ``` block at the end.

    Returns:
        A tuple of:
          - clean_text: the response with the JSON block stripped out
          - chart_data: a ChartData instance, or None if no valid block found
    """
    match = _CHART_PATTERN.search(raw)
    if not match:
        return raw.strip(), None

    # Strip the json block from the text
    clean_text = raw[: match.start()].strip()
    json_str = match.group(1)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        # Malformed JSON — return clean text without crashing
        return clean_text, None

    try:
        datasets = [
            Dataset(
                label=str(ds["label"]),
                values=[float(v) for v in ds["values"]],
            )
            for ds in data.get("datasets", [])
        ]
        chart = ChartData(
            chart_type=str(data.get("chart_type", "bar")),
            title=str(data.get("title", "")),
            x_labels=[str(l) for l in data.get("x_labels", [])],
            datasets=datasets,
            highlight_towns=[str(t) for t in data.get("highlight_towns", [])],
        )
    except (KeyError, TypeError, ValueError):
        # Structurally invalid — missing required fields or wrong types
        return clean_text, None

    return clean_text, chart
