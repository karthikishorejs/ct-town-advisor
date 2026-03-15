"""
Unit tests for src/chart_builder.py

Tests:
  1. is_valid_chart with valid figure
  2. is_valid_chart with missing 'data' key
  3. is_valid_chart with empty dict
  4. is_valid_chart with None
  5. apply_ct_theme applies defaults
  6. apply_ct_theme preserves existing layout
  7. apply_ct_theme sets marker colors
  8. chart_from_json_string with valid JSON
  9. chart_from_json_string with invalid JSON
  10. chart_from_json_string with valid JSON but no 'data' key
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.chart_builder import (
    apply_ct_theme,
    chart_from_json_string,
    is_valid_chart,
)


# ---------------------------------------------------------------------------
# is_valid_chart
# ---------------------------------------------------------------------------

class TestIsValidChart:

    def test_valid_chart(self):
        """Chart with 'data' key should be valid."""
        chart = {"data": [{"type": "bar", "x": [1, 2], "y": [3, 4]}]}
        assert is_valid_chart(chart) is True

    def test_valid_chart_with_layout(self):
        """Chart with 'data' and 'layout' keys should be valid."""
        chart = {
            "data": [{"type": "bar"}],
            "layout": {"title": "Test"},
        }
        assert is_valid_chart(chart) is True

    def test_missing_data_key(self):
        """Chart without 'data' key should be invalid."""
        chart = {"layout": {"title": "Test"}}
        assert is_valid_chart(chart) is False

    def test_empty_dict(self):
        """Empty dict should be invalid."""
        assert is_valid_chart({}) is False

    def test_none(self):
        """None should be invalid."""
        assert is_valid_chart(None) is False

    def test_empty_data_list(self):
        """Chart with empty data list should be valid (has the key)."""
        chart = {"data": []}
        assert is_valid_chart(chart) is True


# ---------------------------------------------------------------------------
# apply_ct_theme
# ---------------------------------------------------------------------------

class TestApplyCTTheme:

    def test_applies_template(self):
        """Should set template to plotly_white."""
        chart = {"data": [{"type": "bar"}]}
        result = apply_ct_theme(chart)
        assert result["layout"]["template"] == "plotly_white"

    def test_applies_font(self):
        """Should set font family."""
        chart = {"data": []}
        result = apply_ct_theme(chart)
        assert "Inter" in result["layout"]["font"]["family"]

    def test_applies_background_colors(self):
        """Should set paper and plot background colors."""
        chart = {"data": []}
        result = apply_ct_theme(chart)
        assert result["layout"]["paper_bgcolor"] == "#f8f9fa"
        assert result["layout"]["plot_bgcolor"] == "#ffffff"

    def test_preserves_existing_layout(self):
        """Should not overwrite existing layout properties."""
        chart = {
            "data": [],
            "layout": {"template": "seaborn", "title": "Custom"},
        }
        result = apply_ct_theme(chart)
        assert result["layout"]["template"] == "seaborn"
        assert result["layout"]["title"] == "Custom"

    def test_applies_marker_colors(self):
        """Should set marker color on traces that have 'marker' but no 'color'."""
        chart = {
            "data": [
                {"type": "bar", "marker": {}},
            ]
        }
        result = apply_ct_theme(chart)
        assert result["data"][0]["marker"]["color"] == "#002868"

    def test_does_not_overwrite_existing_marker_color(self):
        """Should preserve existing marker color."""
        chart = {
            "data": [
                {"type": "bar", "marker": {"color": "#FF0000"}},
            ]
        }
        result = apply_ct_theme(chart)
        assert result["data"][0]["marker"]["color"] == "#FF0000"

    def test_returns_same_dict(self):
        """apply_ct_theme mutates and returns the same dict object."""
        chart = {"data": []}
        result = apply_ct_theme(chart)
        assert result is chart


# ---------------------------------------------------------------------------
# chart_from_json_string
# ---------------------------------------------------------------------------

class TestChartFromJsonString:

    def test_valid_json_with_data(self):
        """Valid JSON with 'data' key should return themed dict."""
        raw = json.dumps({
            "data": [{"type": "bar", "x": [1], "y": [2]}],
            "layout": {"title": "Test"},
        })
        result = chart_from_json_string(raw)
        assert result is not None
        assert "data" in result
        assert result["layout"]["template"] == "plotly_white"

    def test_invalid_json(self):
        """Invalid JSON string should return None."""
        result = chart_from_json_string("not json {{{")
        assert result is None

    def test_valid_json_no_data_key(self):
        """Valid JSON but missing 'data' key should return None."""
        raw = json.dumps({"layout": {"title": "Test"}})
        result = chart_from_json_string(raw)
        assert result is None

    def test_none_input(self):
        """None input should return None."""
        result = chart_from_json_string(None)
        assert result is None

    def test_empty_string(self):
        """Empty string should return None."""
        result = chart_from_json_string("")
        assert result is None
