"""
Shared test fixtures for ct-town-advisor tests.
"""

import json
import sys
from pathlib import Path

import pytest

# Ensure project root is on sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Sample town data (matches the real JSON schema but with test-friendly values)
# ---------------------------------------------------------------------------

SAMPLE_CHESHIRE = {
    "town": "Cheshire",
    "budget_year": "FY2025",
    "total_budget": 144383728,
    "mill_rate": 34.0,
    "median_home_price": 390000,
    "population": 29000,
    "persona": "The Safe Haven",
    "persona_description": "A nurturing and secure community.",
    "departments": {
        "education": {"amount": 89542609, "percent": 62.0},
        "public_safety": {"amount": 9073375, "percent": 6.3},
        "infrastructure": {"amount": 7888688, "percent": 5.5},
        "debt_service": {"amount": 9221592, "percent": 6.4},
        "health_services": {"amount": 1854450, "percent": 1.3},
        "administration": {"amount": 26803014, "percent": 18.6},
    },
    "key_facts": [
        "Education is the largest expenditure at 62.0% of the budget."
    ],
    "strengths": [
        "Strong investment in education."
    ],
    "weaknesses": [
        "Budget increases in some departments."
    ],
}

SAMPLE_WALLINGFORD = {
    "town": "Wallingford",
    "budget_year": "FY2025-2026",
    "total_budget": 204050153,
    "mill_rate": 24.12,
    "median_home_price": 277618,
    "population": 45000,
    "persona": "The Education Champion",
    "persona_description": "A town that leads in educational investment.",
    "departments": {
        "education": {"amount": 121722102, "percent": 59.7},
        "public_safety": {"amount": 25505846, "percent": 12.5},
    },
    "key_facts": ["Wallingford has the largest population of the three towns."],
    "strengths": ["Highest total budget allocation for education."],
    "weaknesses": ["Higher overall spending may lead to future tax pressure."],
}

SAMPLE_NORTH_HAVEN = {
    "town": "North Haven",
    "budget_year": "FY2025",
    "total_budget": 137600000,
    "mill_rate": 36.55,
    "median_home_price": 301000,
    "population": 24000,
    "persona": "The Balanced Town",
    "persona_description": "A balanced approach to municipal services.",
    "departments": {
        "education": {"amount": 68500000, "percent": 49.8},
        "public_safety": {"amount": 15200000, "percent": 11.0},
    },
    "key_facts": ["North Haven balances services across departments."],
    "strengths": ["Balanced budget allocation."],
    "weaknesses": ["Highest mill rate among the three towns."],
}


@pytest.fixture
def sample_towns():
    """Return a list of all three sample town dicts."""
    return [SAMPLE_CHESHIRE, SAMPLE_WALLINGFORD, SAMPLE_NORTH_HAVEN]


@pytest.fixture
def cheshire_data():
    """Return sample Cheshire town data."""
    return SAMPLE_CHESHIRE.copy()


@pytest.fixture
def wallingford_data():
    """Return sample Wallingford town data."""
    return SAMPLE_WALLINGFORD.copy()


@pytest.fixture
def sample_ui_update():
    """Return a sample Penny ui_update dict."""
    return {
        "active_town": "Wallingford",
        "highlight_towns": ["Wallingford", "Cheshire"],
        "chart": {
            "chart_type": "bar",
            "title": "Education Spending Comparison",
            "x_labels": ["Wallingford", "Cheshire", "North Haven"],
            "datasets": [
                {
                    "label": "Education ($M)",
                    "values": [121.7, 89.5, 68.5],
                }
            ],
        },
        "show_listings": False,
        "show_calculator": False,
        "calculator_home_price": None,
    }


@pytest.fixture
def sample_penny_response():
    """Return a sample full Penny JSON response."""
    return {
        "voice_response": "Wallingford leads in education spending with $121.7 million, "
                          "which is about 60% of their total budget!",
        "ui_update": {
            "active_town": "Wallingford",
            "highlight_towns": ["Wallingford", "Cheshire"],
            "chart": {
                "chart_type": "bar",
                "title": "Education Spending",
                "x_labels": ["Wallingford", "Cheshire"],
                "datasets": [
                    {"label": "Spending ($M)", "values": [121.7, 89.5]}
                ],
            },
            "show_listings": False,
            "show_calculator": False,
            "calculator_home_price": None,
        },
    }
