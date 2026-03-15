"""
pdf_loader.py
-------------
Loads PDF files from the /data directory into base64-encoded format
ready to send to the Gemini API as inline file parts.

Each PDF is tagged with a town_name derived from its filename.
A helper (download_if_empty) fetches PDFs from GCS when /data is empty.
"""

from __future__ import annotations

import base64
import os
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _town_name_from_filename(filename: str) -> str:
    """
    Derive a human-readable town name from a PDF filename.

    Examples:
        "greenwich_annual_report.pdf"  -> "Greenwich"
        "New-Haven-Budget-2024.pdf"    -> "New Haven"
        "stamford.pdf"                 -> "Stamford"
        "west_hartford_2023.pdf"       -> "West Hartford"
    """
    stem = Path(filename).stem
    # Replace separators with spaces
    name = re.sub(r"[-_]+", " ", stem)
    # Drop trailing year / numeric suffixes (e.g. "2023", "FY24")
    name = re.sub(r"\s+\d{4}$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+fy\d{2,4}$", "", name, flags=re.IGNORECASE)
    # Drop common generic suffixes so the town name stays clean
    for suffix in (
        "annual report", "budget", "report", "data", "doc", "document"
    ):
        name = re.sub(rf"\s+{re.escape(suffix)}$", "", name, flags=re.IGNORECASE)
    # Title-case and strip
    return name.strip().title()


def load_pdfs_as_base64(data_dir: Path = DATA_DIR) -> list[dict[str, str]]:
    """
    Read every .pdf in *data_dir* and return a list of dicts with:

        {
            "town_name": str,   # human-readable name derived from filename
            "pdf_data":  str,   # standard base64-encoded PDF bytes
        }

    These dicts map directly to Gemini inline_data parts:

        types.Part(
            inline_data=types.Blob(
                mime_type="application/pdf",
                data=base64.b64decode(entry["pdf_data"]),
            )
        )

    Raises:
        FileNotFoundError: if data_dir does not exist.
        ValueError:        if no PDF files are found in data_dir.
    """
    if not data_dir.exists():
        raise FileNotFoundError(f"Data directory not found: {data_dir}")

    pdf_files = sorted(data_dir.glob("*.pdf"))

    if not pdf_files:
        raise ValueError(
            f"No PDF files found in {data_dir}. "
            "Run download_if_empty() first or place PDFs in /data."
        )

    results: list[dict[str, str]] = []
    for pdf_path in pdf_files:
        town_name = _town_name_from_filename(pdf_path.name)
        print(f"Loading PDF: {pdf_path.name!r} → town: {town_name!r}")
        raw_bytes = pdf_path.read_bytes()
        pdf_data = base64.b64encode(raw_bytes).decode("ascii")
        results.append({"town_name": town_name, "pdf_data": pdf_data})

    return results


def download_if_empty(
    bucket_name: str | None = None,
    prefix: str = "pdfs/",
    data_dir: Path = DATA_DIR,
) -> list[Path]:
    """
    Download PDFs from GCS into *data_dir* **only** when the directory
    contains no .pdf files.  Useful for cold-start in Cloud Run / Docker.

    Args:
        bucket_name: GCS bucket name; falls back to the GCS_BUCKET_NAME env var.
        prefix:      Blob prefix to list inside the bucket (default ``"pdfs/"``).
        data_dir:    Local destination directory (default ``/data``).

    Returns:
        List of local Paths that were downloaded.  Empty list if the
        directory already had PDFs or if no bucket name is configured.
    """
    existing = list(data_dir.glob("*.pdf")) if data_dir.exists() else []
    if existing:
        print(
            f"/data already contains {len(existing)} PDF(s) — skipping GCS sync."
        )
        return []

    bucket_name = bucket_name or os.getenv("GCS_BUCKET_NAME")
    if not bucket_name:
        print(
            "GCS_BUCKET_NAME not set and /data is empty. "
            "Place PDF files in /data manually."
        )
        return []

    # Lazy import keeps startup fast when GCS is not needed
    from google.cloud import storage  # type: ignore[import-untyped]

    data_dir.mkdir(parents=True, exist_ok=True)
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blobs = [b for b in bucket.list_blobs(prefix=prefix) if b.name.lower().endswith(".pdf")]

    if not blobs:
        print(f"No PDFs found at gs://{bucket_name}/{prefix}")
        return []

    downloaded: list[Path] = []
    for blob in blobs:
        local_path = data_dir / Path(blob.name).name
        print(f"Downloading gs://{bucket_name}/{blob.name} → {local_path}")
        blob.download_to_filename(str(local_path))
        downloaded.append(local_path)

    print(f"Downloaded {len(downloaded)} PDF(s) from GCS.")
    return downloaded
