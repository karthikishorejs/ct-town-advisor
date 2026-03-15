"""
generate_avatars.py
-------------------
Generates one avatar PNG per CT town using Gemini 2.0 Flash image generation
(gemini-2.0-flash-exp with response_modalities=["IMAGE"]).

All three towns are generated in parallel via asyncio.to_thread so the
synchronous google-genai SDK doesn't block the event loop.

Output:
    app/assets/cheshire_avatar.png
    app/assets/north_haven_avatar.png
    app/assets/wallingford_avatar.png

Usage:
    python src/generate_avatars.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import google.genai as genai
from google.genai import types

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
JSON_DIR = ROOT / "data" / "json"
ASSETS_DIR = ROOT / "app" / "assets"
MODEL = "imagen-4.0-fast-generate-001"

# town_name → output filename stem
TOWN_FILES: dict[str, str] = {
    "Cheshire": "cheshire_avatar.png",
    "North Haven": "north_haven_avatar.png",
    "Wallingford": "wallingford_avatar.png",
}

# JSON filename derived from town name
JSON_FILES: dict[str, str] = {
    "Cheshire": "cheshire.json",
    "North Haven": "north_haven.json",
    "Wallingford": "wallingford.json",
}

AVATAR_PROMPT = (
    "A friendly warm flat illustration avatar character "
    "representing a CT town persona called '{persona}'. "
    "{persona_description} "
    "Clean flat design style, vibrant colors, circular framing, "
    "professional illustration, transparent background. No text."
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def load_town_persona(town_name: str) -> tuple[str, str]:
    """Return (persona, persona_description) from the town JSON."""
    json_path = JSON_DIR / JSON_FILES[town_name]
    data = json.loads(json_path.read_text())
    return data["persona"], data["persona_description"]


def _generate_sync(
    client: genai.Client,
    town_name: str,
    persona: str,
    persona_description: str,
    output_path: Path,
) -> Path:
    """Synchronous generation call — run inside asyncio.to_thread."""
    prompt = AVATAR_PROMPT.format(
        persona=persona,
        persona_description=persona_description,
    )

    response = client.models.generate_images(
        model=MODEL,
        prompt=prompt,
        config=types.GenerateImagesConfig(number_of_images=1),
    )

    if not response.generated_images:
        raise RuntimeError(f"[{town_name}] Imagen returned no images.")

    image_data = response.generated_images[0].image.image_bytes
    output_path.write_bytes(image_data)
    return output_path


# ---------------------------------------------------------------------------
# Async orchestration
# ---------------------------------------------------------------------------
async def generate_avatar(
    client: genai.Client,
    town_name: str,
) -> tuple[str, Path]:
    """Generate (or skip if cached) avatar for one town. Returns (town_name, path)."""
    output_path = ASSETS_DIR / TOWN_FILES[town_name]

    if output_path.exists():
        print(f"[{town_name}] Cached — skipping ({output_path.name})")
        return town_name, output_path

    print(f"[{town_name}] Generating avatar...")
    persona, persona_description = load_town_persona(town_name)

    path = await asyncio.to_thread(
        _generate_sync,
        client,
        town_name,
        persona,
        persona_description,
        output_path,
    )
    print(f"[{town_name}] Saved → {path.relative_to(ROOT)}")
    return town_name, path


async def generate_all_avatars(client: genai.Client) -> dict[str, Path]:
    """Run all three avatar generations in parallel."""
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    tasks = [generate_avatar(client, town) for town in TOWN_FILES]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    avatars: dict[str, Path] = {}
    for result in results:
        if isinstance(result, Exception):
            print(f"ERROR: {result}")
        else:
            town_name, path = result
            avatars[town_name] = path

    return avatars


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def run() -> dict[str, Path]:
    """Public entry point — returns {town_name: image_path}."""
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GOOGLE_API_KEY is not set. Add it to your .env file."
        )

    client = genai.Client(api_key=api_key)
    avatars = asyncio.run(generate_all_avatars(client))

    if avatars:
        print("\n✅ All avatars ready!")
    return avatars


if __name__ == "__main__":
    run()
