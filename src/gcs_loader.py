"""
gcs_loader.py
-------------
Optional helper to download PDF files from a Google Cloud Storage bucket
into the local /data directory before the app starts.
Falls back to local /data if GCS_BUCKET_NAME is not set.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def sync_pdfs_from_gcs(
    bucket_name: str | None = None,
    prefix: str = "pdfs/",
    dest_dir: Path = DATA_DIR,
) -> list[Path]:
    """
    Download all PDFs under `prefix` from `bucket_name` to `dest_dir`.

    Returns a list of local paths that were downloaded.
    Skips files that already exist locally (simple mtime-based check).
    """
    bucket_name = bucket_name or os.getenv("GCS_BUCKET_NAME")
    if not bucket_name:
        print("GCS_BUCKET_NAME not set — skipping GCS sync, using local /data.")
        return []

    from google.cloud import storage  # imported lazily to keep startup fast

    dest_dir.mkdir(parents=True, exist_ok=True)
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blobs = list(bucket.list_blobs(prefix=prefix))

    downloaded: list[Path] = []
    for blob in blobs:
        if not blob.name.lower().endswith(".pdf"):
            continue
        local_path = dest_dir / Path(blob.name).name
        if local_path.exists():
            print(f"Already exists locally, skipping: {local_path.name}")
            continue
        print(f"Downloading gs://{bucket_name}/{blob.name} → {local_path}")
        blob.download_to_filename(str(local_path))
        downloaded.append(local_path)

    return downloaded
