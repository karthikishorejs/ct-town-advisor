"""
demo_test.py
------------
Tests the full pipeline end-to-end using text queries (no microphone).
Uses generate_content (not Live API) since inline PDFs are not supported
by the Live API — the Live API is for real-time audio only.

Runs 5 queries through Gemini and prints Penny's response + any chart JSON.

Usage:
    python demo_test.py
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, ".")

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

from src.chart_parser import ChartData, parse_response
from src.context_builder import SYSTEM_PROMPT, build_content_array
from src.pdf_loader import download_if_empty, load_pdfs_as_base64

# generate_content supports inline PDFs; use a standard (non-Live) model
GEMINI_MODEL = os.getenv("GEMINI_DEMO_MODEL", "gemini-2.5-flash")

QUERIES = [
    "Is Wallingford a good town for a family with two kids?",
    "Compare education spending across all CT towns and rank them",
    "Which CT town has the lowest property tax rate?",
    "How does the public safety budget in Cheshire compare to North Haven?",
    "I earn $120k, which CT town gives me the best value for money?",
]


def run_query(
    client: genai.Client,
    context_contents: list[types.Content],
    query: str,
) -> tuple[str, ChartData | None]:
    """Send a single text query using generate_content and return parsed result."""
    user_turn = types.Content(
        role="user",
        parts=[types.Part(text=query)],
    )
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=context_contents + [user_turn],
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
        ),
    )
    raw_text = response.text or ""
    return parse_response(raw_text)


def main() -> None:
    print("=" * 70)
    print("CT Town Advisor — Demo Test")
    print(f"Model: {GEMINI_MODEL}")
    print("=" * 70)

    # Load PDFs
    print("\nStep 1: Loading PDFs…")
    download_if_empty()
    pdf_entries = load_pdfs_as_base64()
    context_contents = build_content_array(pdf_entries)
    print(
        f"Loaded {len(pdf_entries)} town PDF(s): "
        f"{[e['town_name'] for e in pdf_entries]}\n"
    )

    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])

    print("Step 2: Running queries…\n")
    print("=" * 70)

    for i, query in enumerate(QUERIES, start=1):
        print(f"\nQuery {i}: {query}")
        print("-" * 70)

        t0 = time.perf_counter()
        clean_text, chart = run_query(client, context_contents, query)
        elapsed = time.perf_counter() - t0

        print(f"Penny's response:\n{clean_text}")
        print()
        if chart:
            print("Chart JSON:")
            print(f"  type            : {chart.chart_type}")
            print(f"  title           : {chart.title}")
            print(f"  x_labels        : {chart.x_labels}")
            for ds in chart.datasets:
                print(f"  dataset '{ds.label}': {ds.values}")
            print(f"  highlight_towns : {chart.highlight_towns}")
        else:
            print("Chart: No chart")

        print(f"\nTime taken: {elapsed:.2f}s")
        print("=" * 70)


if __name__ == "__main__":
    main()
