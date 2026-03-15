"""
extract_town_data.py
--------------------
One-shot PDF extraction: sends each CT town budget PDF to Gemini in a single
request (no page-by-page splitting) and extracts structured town data as JSON.

Output files:
    data/cheshire.json
    data/north_haven.json
    data/wallingford.json

Usage:
    python src/extract_town_data.py
"""

from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Ensure project root is importable regardless of working directory
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import google.genai as genai
from google.genai import types

from src.pdf_loader import DATA_DIR, load_pdfs_as_base64

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MODEL = "gemini-2.5-flash"

# Persona assigned to each town (name → persona label)
PERSONA_MAP: dict[str, str] = {
    "Wallingford": "The Education Champion",
    "North Haven": "The Balanced Budgeter",
    "Cheshire": "The Safe Haven",
}

OUTPUT_DIR = ROOT / "data"

# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------
EXTRACTION_PROMPT_TEMPLATE = """\
You are a municipal budget analyst. Carefully read the entire CT town budget \
PDF for {town_name} and extract the data below as valid JSON.

Rules:
1. Only use values explicitly stated in the document — set unknown fields to null.
2. All dollar amounts must be plain integers (no commas, no symbols).
3. Percentages: (department_amount / total_budget) * 100, rounded to 1 decimal.
   If total_budget is null, set percent to null.
4. budget_year: string like "2025-26" or "FY2025".
5. mill_rate: property tax rate in mills (e.g. 32.5) — a float.
6. median_home_price: median residential assessed or sale value in dollars — integer.
7. population: integer.
8. "persona" MUST be exactly: "{persona}"
9. "persona_description": 2–3 warm, friendly sentences capturing this town's \
character based on its budget priorities.
10. key_facts: 3–5 notable facts drawn from the document.
11. strengths: 2–3 budget or community strengths.
12. weaknesses: 2–3 budget challenges or areas of concern.

Return ONLY valid JSON — no markdown fences, no explanation — matching this \
exact structure:
{{
  "town": "{town_name}",
  "budget_year": null,
  "total_budget": null,
  "mill_rate": null,
  "median_home_price": null,
  "population": null,
  "persona": "{persona}",
  "persona_description": null,
  "departments": {{
    "education":     {{"amount": null, "percent": null}},
    "public_safety": {{"amount": null, "percent": null}},
    "infrastructure":{{"amount": null, "percent": null}},
    "debt_service":  {{"amount": null, "percent": null}},
    "health_services":{{"amount": null, "percent": null}},
    "administration":{{"amount": null, "percent": null}}
  }},
  "key_facts":  [],
  "strengths":  [],
  "weaknesses": []
}}
"""


def _build_prompt(town_name: str, persona: str) -> str:
    return EXTRACTION_PROMPT_TEMPLATE.format(town_name=town_name, persona=persona)


def _output_path(town_name: str) -> Path:
    """Convert 'North Haven' → data/north_haven.json."""
    filename = town_name.lower().replace(" ", "_") + ".json"
    return OUTPUT_DIR / filename


def extract_town(client: genai.Client, pdf_entry: dict[str, str]) -> dict:
    """Send one PDF to Gemini and return parsed JSON dict."""
    town_name = pdf_entry["town_name"]
    persona = PERSONA_MAP.get(town_name, "The Town Advisor")
    prompt = _build_prompt(town_name, persona)

    raw_bytes = base64.b64decode(pdf_entry["pdf_data"])

    response = client.models.generate_content(
        model=MODEL,
        contents=[
            types.Content(
                role="user",
                parts=[
                    types.Part(
                        inline_data=types.Blob(
                            mime_type="application/pdf",
                            data=raw_bytes,
                        )
                    ),
                    types.Part(text=prompt),
                ],
            )
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )

    return json.loads(response.text)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GOOGLE_API_KEY is not set. Add it to your .env file or environment."
        )

    client = genai.Client(api_key=api_key)

    print("Loading PDFs from data/...")
    pdf_entries = load_pdfs_as_base64(DATA_DIR)
    town_names = [e["town_name"] for e in pdf_entries]
    print(f"Found {len(pdf_entries)} PDF(s): {town_names}\n")

    succeeded: list[tuple[str, Path]] = []
    failed: list[tuple[str, str]] = []

    for entry in pdf_entries:
        town_name = entry["town_name"]
        print(f"[{town_name}] Sending to Gemini ({MODEL})...")
        try:
            data = extract_town(client, entry)
            out = _output_path(town_name)
            out.write_text(json.dumps(data, indent=2))
            succeeded.append((town_name, out))
            print(f"[{town_name}] Saved → {out.relative_to(ROOT)}")
        except Exception as exc:
            failed.append((town_name, str(exc)))
            print(f"[{town_name}] ERROR: {exc}")

    # Summary
    print("\n" + "=" * 50)
    print("Summary")
    print("=" * 50)
    for town, path in succeeded:
        print(f"  OK    {town:15s}  →  {path.relative_to(ROOT)}")
    for town, err in failed:
        print(f"  FAIL  {town:15s}  →  {err}")

    if failed:
        sys.exit(f"\n{len(failed)} town(s) failed. See errors above.")
    else:
        print(f"\nAll {len(succeeded)} town(s) extracted successfully.")


if __name__ == "__main__":
    main()
