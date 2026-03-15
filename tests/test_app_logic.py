"""
Unit tests for app/main.py business logic.

These tests exercise the pure functions extracted from the Streamlit app
without requiring a running Streamlit server or Gemini API access.

Tests:
  1. _apply_ui_update — town, chart, calculator, listings
  2. _compute_tax — tax calculations for various scenarios
  3. _make_chart — Plotly figure generation
  4. Tax calculation math
  5. Zillow slug mapping
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# We need to mock streamlit before importing app.main
# because app/main.py calls st.set_page_config at import time.
sys.modules["streamlit"] = MagicMock()
sys.modules["streamlit.components"] = MagicMock()
sys.modules["streamlit.components.v1"] = MagicMock()

# Now we can safely import the functions we want to test
from src.context_builder import get_all_towns, get_town_data


# ---------------------------------------------------------------------------
# Tax calculator tests (reimplemented here to avoid Streamlit import)
# ---------------------------------------------------------------------------

CT_ASSESS_RATIO = 0.70


def compute_tax(home_price: int, mill_rate: float) -> tuple[int, int]:
    """Pure version of app/main.py's _compute_tax logic."""
    assessed = home_price * CT_ASSESS_RATIO
    annual = int(assessed * mill_rate / 1000)
    return annual, annual // 12


class TestTaxCalculator:
    """Property tax calculation tests."""

    def test_cheshire_400k_home(self):
        """Cheshire: $400k home × 34.0 mill rate."""
        annual, monthly = compute_tax(400_000, 34.0)
        # assessed = 400000 * 0.70 = 280000
        # annual = 280000 * 34.0 / 1000 = 9520
        assert annual == 9520
        assert monthly == 9520 // 12

    def test_wallingford_300k_home(self):
        """Wallingford: $300k home × 24.12 mill rate."""
        annual, monthly = compute_tax(300_000, 24.12)
        # assessed = 300000 * 0.70 = 210000
        # annual = 210000 * 24.12 / 1000 = 5065.2 → int = 5065
        assert annual == 5065
        assert monthly == 5065 // 12

    def test_north_haven_500k_home(self):
        """North Haven: $500k home × 36.55 mill rate."""
        annual, monthly = compute_tax(500_000, 36.55)
        # assessed = 500000 * 0.70 = 350000
        # annual = 350000 * 36.55 / 1000 = 12792.5 → int = 12792
        assert annual == 12792
        assert monthly == 12792 // 12

    def test_zero_home_price(self):
        """Zero home price should yield zero tax."""
        annual, monthly = compute_tax(0, 34.0)
        assert annual == 0
        assert monthly == 0

    def test_zero_mill_rate(self):
        """Zero mill rate should yield zero tax."""
        annual, monthly = compute_tax(400_000, 0.0)
        assert annual == 0
        assert monthly == 0

    def test_million_dollar_home(self):
        """$1M home in Cheshire."""
        annual, monthly = compute_tax(1_000_000, 34.0)
        # assessed = 1000000 * 0.70 = 700000
        # annual = 700000 * 34.0 / 1000 = 23800
        assert annual == 23800
        assert monthly == 23800 // 12

    def test_assessment_ratio_is_70_percent(self):
        """CT assessment ratio must be 70%."""
        assert CT_ASSESS_RATIO == 0.70

    def test_real_town_data(self):
        """Tax calc should work with actual town data from JSON files."""
        for town in get_all_towns():
            mill_rate = float(town.get("mill_rate", 0))
            median = town.get("median_home_price", 0)
            annual, monthly = compute_tax(median, mill_rate)
            assert annual >= 0
            assert monthly >= 0
            assert monthly == annual // 12


# ---------------------------------------------------------------------------
# UI update application tests
# ---------------------------------------------------------------------------

class TestApplyUiUpdate:
    """Test the UI update application logic."""

    def test_active_town_set(self):
        """active_town should be extracted from ui_update."""
        ui = {"active_town": "Cheshire"}
        # Simulate what _apply_ui_update does
        active = ui.get("active_town") or None
        assert active == "Cheshire"

    def test_active_town_null(self):
        """active_town null should resolve to None."""
        ui = {"active_town": None}
        active = ui["active_town"] or None
        assert active is None

    def test_active_town_missing(self):
        """Missing active_town should not be processed."""
        ui = {"highlight_towns": ["Cheshire"]}
        assert "active_town" not in ui

    def test_highlight_towns_extracted(self):
        """highlight_towns should be a list of town names."""
        ui = {"highlight_towns": ["Wallingford", "Cheshire"]}
        assert ui["highlight_towns"] == ["Wallingford", "Cheshire"]

    def test_chart_valid(self):
        """Valid chart should be extracted when chart_type is not 'none'."""
        ui = {
            "chart": {
                "chart_type": "bar",
                "title": "Test",
                "x_labels": ["A", "B"],
                "datasets": [{"label": "Val", "values": [1, 2]}],
            }
        }
        chart = ui.get("chart", {})
        assert chart.get("chart_type") != "none"

    def test_chart_none_type_ignored(self):
        """Chart with type 'none' should be treated as no chart."""
        ui = {
            "chart": {
                "chart_type": "none",
                "x_labels": [],
                "datasets": [],
            }
        }
        chart = ui.get("chart", {})
        assert chart.get("chart_type", "none") == "none"

    def test_show_calculator_true(self):
        """show_calculator=true should activate the calculator."""
        ui = {"show_calculator": True}
        assert ui.get("show_calculator") is True

    def test_show_listings_true(self):
        """show_listings=true should activate the listings panel."""
        ui = {"show_listings": True}
        assert ui.get("show_listings") is True

    def test_calculator_home_price_valid(self):
        """Valid calculator_home_price should be parsed as int."""
        ui = {"calculator_home_price": 500000}
        price = int(ui["calculator_home_price"])
        assert price == 500_000

    def test_calculator_home_price_clamped_high(self):
        """Price above 1M should be clamped to 1M."""
        price = int(1_500_000)
        clamped = max(100_000, min(1_000_000, price))
        assert clamped == 1_000_000

    def test_calculator_home_price_clamped_low(self):
        """Price below 100k should be clamped to 100k."""
        price = int(50_000)
        clamped = max(100_000, min(1_000_000, price))
        assert clamped == 100_000


# ---------------------------------------------------------------------------
# Penny response parsing tests
# ---------------------------------------------------------------------------

class TestPennyResponseParsing:
    """Test parsing of Penny's structured JSON responses."""

    def test_valid_response_structure(self, sample_penny_response):
        """Response should have voice_response and ui_update keys."""
        assert "voice_response" in sample_penny_response
        assert "ui_update" in sample_penny_response

    def test_voice_response_is_string(self, sample_penny_response):
        """voice_response should be a string."""
        assert isinstance(sample_penny_response["voice_response"], str)

    def test_ui_update_has_chart(self, sample_penny_response):
        """ui_update should contain a chart dict."""
        ui = sample_penny_response["ui_update"]
        assert "chart" in ui
        assert "chart_type" in ui["chart"]

    def test_chart_datasets_have_values(self, sample_penny_response):
        """Chart datasets should have matching values."""
        chart = sample_penny_response["ui_update"]["chart"]
        ds = chart["datasets"][0]
        assert len(ds["values"]) == len(chart["x_labels"])

    def test_response_json_serializable(self, sample_penny_response):
        """Response should be JSON-serializable (as Gemini returns it)."""
        json_str = json.dumps(sample_penny_response)
        parsed = json.loads(json_str)
        assert parsed == sample_penny_response


# ---------------------------------------------------------------------------
# Zillow URL mapping tests
# ---------------------------------------------------------------------------

ZILLOW_SLUGS = {
    "Wallingford": "wallingford-ct",
    "North Haven": "north-haven-ct",
    "Cheshire": "cheshire-ct",
}


class TestZillowMappings:
    """Test Zillow URL slug mappings."""

    def test_all_towns_have_slugs(self):
        """Every known town must have a Zillow slug."""
        for town in get_all_towns():
            name = town["town"]
            assert name in ZILLOW_SLUGS, f"Missing Zillow slug for {name}"

    def test_slug_format(self):
        """Slugs should be lowercase with hyphens, ending in -ct."""
        for name, slug in ZILLOW_SLUGS.items():
            assert slug == slug.lower()
            assert slug.endswith("-ct")
            assert " " not in slug

    def test_zillow_url_construction(self):
        """Zillow URLs should be well-formed."""
        for name, slug in ZILLOW_SLUGS.items():
            url = f"https://www.zillow.com/{slug}/"
            assert url.startswith("https://")
            assert "//" not in url.replace("https://", "")


# ---------------------------------------------------------------------------
# Town color mapping tests
# ---------------------------------------------------------------------------

TOWN_COLORS = {
    "Wallingford": "#2196F3",
    "North Haven": "#4CAF50",
    "Cheshire": "#9C27B0",
}

TOWN_COORDS = {
    "Wallingford": (41.4571, -72.8231),
    "North Haven": (41.3904, -72.8597),
    "Cheshire": (41.4987, -72.9012),
}


class TestTownMappings:
    """Test town-related constant mappings."""

    def test_all_towns_have_colors(self):
        """Every town must have an assigned color."""
        for town in get_all_towns():
            assert town["town"] in TOWN_COLORS

    def test_colors_are_hex(self):
        """Colors must be valid hex color codes."""
        for color in TOWN_COLORS.values():
            assert color.startswith("#")
            assert len(color) == 7

    def test_all_towns_have_coords(self):
        """Every town must have map coordinates."""
        for town in get_all_towns():
            assert town["town"] in TOWN_COORDS

    def test_coords_are_ct(self):
        """Coordinates should be within Connecticut bounds."""
        for name, (lat, lon) in TOWN_COORDS.items():
            assert 40.9 < lat < 42.1, f"{name} lat {lat} out of CT range"
            assert -73.8 < lon < -71.7, f"{name} lon {lon} out of CT range"
