"""
Unit tests for src/chart_parser.py

Cases:
  1. Response with a valid chart JSON block
  2. Response with no chart block
  3. Response with a malformed JSON block
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.chart_parser import ChartData, Dataset, parse_response


# ---------------------------------------------------------------------------
# Case 1: valid chart block
# ---------------------------------------------------------------------------

RESPONSE_WITH_CHART = """\
Cheshire spends more on education than Wallingford based on the 2025 budgets.
Cheshire allocates $28.4M while Wallingford allocates $24.1M to education.

```json
{"chart_type": "bar", "title": "Education Spending 2025", "x_labels": ["Cheshire", "Wallingford"], "datasets": [{"label": "Education Spending ($M)", "values": [28.4, 24.1]}], "highlight_towns": ["Cheshire"]}
```"""


def test_parse_response_with_chart():
    text, chart = parse_response(RESPONSE_WITH_CHART)

    # Clean text has no JSON fence
    assert "```" not in text
    assert "Cheshire spends more on education" in text

    # ChartData is populated correctly
    assert isinstance(chart, ChartData)
    assert chart.chart_type == "bar"
    assert chart.title == "Education Spending 2025"
    assert chart.x_labels == ["Cheshire", "Wallingford"]
    assert len(chart.datasets) == 1
    assert isinstance(chart.datasets[0], Dataset)
    assert chart.datasets[0].label == "Education Spending ($M)"
    assert chart.datasets[0].values == [28.4, 24.1]
    assert chart.highlight_towns == ["Cheshire"]


# ---------------------------------------------------------------------------
# Case 2: no chart block
# ---------------------------------------------------------------------------

RESPONSE_WITHOUT_CHART = """\
Wallingford is a great town for families. It has strong schools,
low crime, and a manageable cost of living based on the 2025 budget documents.
There is no direct town comparison in this question, so no chart is needed."""


def test_parse_response_without_chart():
    text, chart = parse_response(RESPONSE_WITHOUT_CHART)

    # Text returned unchanged (stripped)
    assert text == RESPONSE_WITHOUT_CHART.strip()
    assert chart is None


# ---------------------------------------------------------------------------
# Case 3: malformed JSON block
# ---------------------------------------------------------------------------

RESPONSE_WITH_MALFORMED_JSON = """\
North Haven has a higher per-pupil spending than Cheshire.

```json
{"chart_type": "bar", "title": "Per-Pupil Spending", "x_labels": ["North Haven", "Cheshire"], INVALID JSON HERE
```"""


def test_parse_response_with_malformed_json():
    text, chart = parse_response(RESPONSE_WITH_MALFORMED_JSON)

    # Malformed JSON means regex didn't match — raw text returned, no crash
    assert "North Haven has a higher per-pupil spending" in text
    assert chart is None


# ---------------------------------------------------------------------------
# Run directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_parse_response_with_chart()
    print("PASS  test_parse_response_with_chart")

    test_parse_response_without_chart()
    print("PASS  test_parse_response_without_chart")

    test_parse_response_with_malformed_json()
    print("PASS  test_parse_response_with_malformed_json")

    print("\nAll tests passed.")
