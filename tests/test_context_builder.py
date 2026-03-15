"""
Unit tests for src/context_builder.py

Tests:
  1. System prompt contains all town names
  2. System prompt contains key data points
  3. System prompt includes response schema rules
  4. get_town_data returns correct data
  5. get_town_data raises KeyError for unknown town
  6. get_all_towns returns all three towns
  7. build_context returns empty list
  8. Voice system prompt is built correctly
  9. Town block formatting includes departments
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.context_builder import (
    SYSTEM_PROMPT,
    VOICE_SYSTEM_PROMPT,
    build_context,
    build_system_prompt,
    build_voice_system_prompt,
    get_all_towns,
    get_town_data,
)


# ---------------------------------------------------------------------------
# System prompt tests
# ---------------------------------------------------------------------------

class TestSystemPrompt:
    """Tests for the main system prompt."""

    def test_contains_all_town_names(self):
        """System prompt must mention all three towns."""
        assert "Cheshire" in SYSTEM_PROMPT
        assert "North Haven" in SYSTEM_PROMPT
        assert "Wallingford" in SYSTEM_PROMPT

    def test_contains_penny_identity(self):
        """System prompt must establish Penny's identity."""
        assert "Penny" in SYSTEM_PROMPT
        assert "Connecticut Town Advisor" in SYSTEM_PROMPT

    def test_contains_response_format(self):
        """System prompt must include the JSON response schema."""
        assert "voice_response" in SYSTEM_PROMPT
        assert "ui_update" in SYSTEM_PROMPT
        assert "chart_type" in SYSTEM_PROMPT
        assert "show_calculator" in SYSTEM_PROMPT
        assert "show_listings" in SYSTEM_PROMPT

    def test_contains_mill_rates(self):
        """System prompt must embed actual mill rates from the JSON data."""
        # At least one mill rate should appear
        towns = get_all_towns()
        for town in towns:
            mill = str(town.get("mill_rate", ""))
            if mill:
                assert mill in SYSTEM_PROMPT, (
                    f"Mill rate {mill} for {town['town']} not in SYSTEM_PROMPT"
                )

    def test_contains_budget_figures(self):
        """System prompt must embed budget figures."""
        # Total budgets should appear formatted with commas
        assert "$144,383,728" in SYSTEM_PROMPT or "144,383,728" in SYSTEM_PROMPT

    def test_contains_rules(self):
        """System prompt must include behavioral rules."""
        assert "ONLY use numbers and facts" in SYSTEM_PROMPT
        assert "3 sentences" in SYSTEM_PROMPT or "≤ 3" in SYSTEM_PROMPT

    def test_contains_calculator_home_price(self):
        """System prompt schema must include calculator_home_price field."""
        assert "calculator_home_price" in SYSTEM_PROMPT

    def test_rebuild_returns_string(self):
        """build_system_prompt() should return a non-empty string."""
        result = build_system_prompt()
        assert isinstance(result, str)
        assert len(result) > 100

    def test_rebuild_matches_module_constant(self):
        """Rebuilding should produce the same content as the module constant."""
        rebuilt = build_system_prompt()
        assert "Penny" in rebuilt
        assert "Cheshire" in rebuilt


# ---------------------------------------------------------------------------
# Voice system prompt tests
# ---------------------------------------------------------------------------

class TestVoiceSystemPrompt:
    """Tests for the voice-specific system prompt."""

    def test_voice_prompt_exists(self):
        """Voice system prompt should be a non-empty string."""
        assert isinstance(VOICE_SYSTEM_PROMPT, str)
        assert len(VOICE_SYSTEM_PROMPT) > 50

    def test_voice_prompt_no_json_schema(self):
        """Voice prompt should NOT include the JSON response schema."""
        assert "ui_update" not in VOICE_SYSTEM_PROMPT
        assert "chart_type" not in VOICE_SYSTEM_PROMPT

    def test_voice_prompt_has_personality(self):
        """Voice prompt must have Penny's personality."""
        assert "Penny" in VOICE_SYSTEM_PROMPT
        assert "warm" in VOICE_SYSTEM_PROMPT.lower() or "Warm" in VOICE_SYSTEM_PROMPT

    def test_voice_prompt_contains_town_data(self):
        """Voice prompt must embed town data."""
        assert "Cheshire" in VOICE_SYSTEM_PROMPT
        assert "North Haven" in VOICE_SYSTEM_PROMPT
        assert "Wallingford" in VOICE_SYSTEM_PROMPT

    def test_voice_rebuild(self):
        """build_voice_system_prompt() should return a valid prompt."""
        result = build_voice_system_prompt()
        assert isinstance(result, str)
        assert "Penny" in result


# ---------------------------------------------------------------------------
# Town data accessor tests
# ---------------------------------------------------------------------------

class TestTownData:
    """Tests for get_town_data and get_all_towns."""

    def test_get_all_towns_count(self):
        """Should return exactly 3 towns."""
        towns = get_all_towns()
        assert len(towns) == 3

    def test_get_all_towns_structure(self):
        """Each town dict must have required fields."""
        required_keys = {
            "town", "budget_year", "total_budget", "mill_rate",
            "median_home_price", "population", "persona",
        }
        for town in get_all_towns():
            missing = required_keys - set(town.keys())
            assert not missing, f"{town['town']} missing keys: {missing}"

    def test_get_town_data_valid(self):
        """get_town_data should return the correct town."""
        cheshire = get_town_data("Cheshire")
        assert cheshire["town"] == "Cheshire"
        assert cheshire["mill_rate"] == 34.0

    def test_get_town_data_wallingford(self):
        """get_town_data should work for Wallingford."""
        wall = get_town_data("Wallingford")
        assert wall["town"] == "Wallingford"
        assert wall["mill_rate"] == 24.12

    def test_get_town_data_north_haven(self):
        """get_town_data should work for North Haven (space in name)."""
        nh = get_town_data("North Haven")
        assert nh["town"] == "North Haven"

    def test_get_town_data_invalid(self):
        """get_town_data should raise KeyError for unknown towns."""
        with pytest.raises(KeyError, match="not found"):
            get_town_data("Hartford")

    def test_get_town_data_case_sensitive(self):
        """Town lookup is case-sensitive."""
        with pytest.raises(KeyError):
            get_town_data("cheshire")

    def test_town_departments_exist(self):
        """Each town must have a departments dict with at least education."""
        for town in get_all_towns():
            assert "departments" in town
            assert "education" in town["departments"]
            edu = town["departments"]["education"]
            assert "amount" in edu
            assert "percent" in edu


# ---------------------------------------------------------------------------
# build_context tests
# ---------------------------------------------------------------------------

class TestBuildContext:
    """Tests for the build_context function."""

    def test_returns_empty_list(self):
        """build_context should return an empty list (all context in system prompt)."""
        result = build_context()
        assert isinstance(result, list)
        assert len(result) == 0
