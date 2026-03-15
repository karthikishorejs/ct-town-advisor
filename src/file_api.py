"""
file_api.py
-----------
Uploads PDF files to the Gemini File API and caches their URIs locally.

Gemini File API stores files for 48 hours. On each app start we check
whether cached URIs are still valid; if not, we re-upload.

Public API:
    ensure_files_uploaded(pdf_entries) -> list[dict]
        Returns enriched entries with "file_uri" added to each dict.

Cache file: data/.file_api_cache.json
    {"filename": {"uri": "...", "expires_at": "<ISO timestamp>"}}
"""

from __future__ import annotations

import json
import os
import tempfile
import base64
from datetime import datetime, timezone, timedelta
from pathlib import Path

from dotenv import load_dotenv
from google import genai

load_dotenv()

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CACHE_FILE = DATA_DIR / ".file_api_cache.json"

# Gemini File API files expire after 48h; re-upload with 1h safety margin
EXPIRY_HOURS = 47


def _load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_FILE.write_text(json.dumps(cache, indent=2))


def _is_valid(entry: dict) -> bool:
    """Return True if the cached URI hasn't expired yet."""
    try:
        expires_at = datetime.fromisoformat(entry["expires_at"])
        return datetime.now(timezone.utc) < expires_at
    except (KeyError, ValueError):
        return False


def _upload_pdf(client: genai.Client, pdf_entry: dict) -> str:
    """
    Upload a single PDF to the Gemini File API.
    Returns the file URI string.
    """
    town = pdf_entry["town_name"]
    raw_bytes = base64.b64decode(pdf_entry["pdf_data"])

    # Write to a named temp file so the SDK can infer mime type from extension
    with tempfile.NamedTemporaryFile(
        suffix=".pdf", prefix=f"{town.replace(' ', '_')}_", delete=False
    ) as tmp:
        tmp.write(raw_bytes)
        tmp_path = tmp.name

    try:
        print(f"Uploading {town} PDF to Gemini File API ({len(raw_bytes) // 1024:,} KB)…")
        response = client.files.upload(
            file=tmp_path,
            config={"mime_type": "application/pdf", "display_name": f"{town} Budget PDF"},
        )
        print(f"  Uploaded: {response.uri}")
        return response.uri
    finally:
        os.unlink(tmp_path)


def ensure_files_uploaded(
    pdf_entries: list[dict[str, str]],
) -> list[dict[str, str]]:
    """
    Ensure all PDFs are uploaded to the Gemini File API.

    For each entry in pdf_entries, checks the local cache for a valid URI.
    Uploads only if the cache is missing or expired.

    Args:
        pdf_entries: Output of pdf_loader.load_pdfs_as_base64() —
                     list of {"town_name": str, "pdf_data": str}.

    Returns:
        Enriched list with "file_uri" added:
        [{"town_name": str, "pdf_data": str, "file_uri": str}, ...]
    """
    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    cache = _load_cache()
    enriched: list[dict[str, str]] = []
    cache_dirty = False

    for entry in pdf_entries:
        town = entry["town_name"]
        cached = cache.get(town, {})

        if cached and _is_valid(cached):
            print(f"Using cached File API URI for {town}: {cached['uri']}")
            file_uri = cached["uri"]
        else:
            file_uri = _upload_pdf(client, entry)
            expires_at = (
                datetime.now(timezone.utc) + timedelta(hours=EXPIRY_HOURS)
            ).isoformat()
            cache[town] = {"uri": file_uri, "expires_at": expires_at}
            cache_dirty = True

        enriched.append({**entry, "file_uri": file_uri})

    if cache_dirty:
        _save_cache(cache)

    return enriched
