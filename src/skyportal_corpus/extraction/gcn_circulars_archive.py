"""Download the GCN circulars JSON archive into one timestamped raw-data run."""

from __future__ import annotations

import argparse
import json
import logging
import tarfile
import time
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

import requests

from ..core import build_run_output_dir, resolve_project_path

DEFAULT_GCN_CIRCULARS_ARCHIVE_URL = "https://gcn.nasa.gov/circulars/archive.json.tar.gz"
DEFAULT_GCN_CIRCULARS_OUTPUT_DIR = "data/raw/gcn/circulars/archive_json"
DEFAULT_ARCHIVE_FILENAME = "gcn_circulars_json.tar.gz"
DEFAULT_EXTRACTED_DIRNAME = "extracted"
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_SECONDS = 2.0
DEFAULT_CHUNK_SIZE_BYTES = 1024 * 1024


def generate_run_id() -> str:
    """Build the standard timestamp-based run identifier."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def save_json(path: Path, data: Any) -> None:
    """Save JSON data to disk."""
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, default=str)


def setup_archive_logging(output_dir: Path) -> None:
    """Configure logging to console and file for one download run."""
    log_file = output_dir / "download_circulars_archive.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
        force=True,
    )


def compute_sha256(path: Path) -> str:
    """Compute a SHA-256 checksum for one file on disk."""
    digest = sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(DEFAULT_CHUNK_SIZE_BYTES), b""):
            digest.update(chunk)

    return digest.hexdigest()


def download_archive_file(
    *,
    url: str,
    destination: Path,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    max_retries: int = DEFAULT_MAX_RETRIES,
    backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
    chunk_size_bytes: int = DEFAULT_CHUNK_SIZE_BYTES,
) -> dict[str, Any]:
    """Download one remote archive to disk with simple retry handling."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_destination = destination.with_suffix(destination.suffix + ".part")

    with requests.Session() as session:
        session.headers.update({"User-Agent": "MAFORAI-gcn-archive-downloader/0.1"})

        for attempt in range(1, max_retries + 2):
            try:
                logging.info("Downloading %s (attempt %s)", url, attempt)
                with session.get(url, stream=True, timeout=timeout_seconds) as response:
                    response.raise_for_status()

                    total_bytes = 0
                    with temp_destination.open("wb") as handle:
                        for chunk in response.iter_content(chunk_size=chunk_size_bytes):
                            if not chunk:
                                continue
                            handle.write(chunk)
                            total_bytes += len(chunk)

                temp_destination.replace(destination)
                return {
                    "url": url,
                    "destination": str(destination),
                    "http_status_code": response.status_code,
                    "content_type": response.headers.get("Content-Type"),
                    "content_length_header": response.headers.get("Content-Length"),
                    "attempts_used": attempt,
                    "downloaded_bytes": total_bytes,
                }

            except requests.RequestException as exc:
                logging.warning("Download attempt %s failed: %s", attempt, exc)

                if temp_destination.exists():
                    temp_destination.unlink()

                if attempt > max_retries:
                    raise RuntimeError(
                        f"Failed to download {url} after {attempt} attempts"
                    ) from exc

                sleep_seconds = backoff_seconds * attempt
                logging.info("Sleeping %.1f seconds before retry", sleep_seconds)
                time.sleep(sleep_seconds)

    raise RuntimeError(f"Failed to download {url}")  # pragma: no cover


def extract_archive_file(archive_path: Path, extract_dir: Path) -> list[str]:
    """Extract a tar.gz archive and return the extracted relative paths."""
    extract_dir.mkdir(parents=True, exist_ok=True)

    with tarfile.open(archive_path, mode="r:gz") as archive:
        archive.extractall(path=extract_dir)
        extracted_paths = [
            member.name
            for member in archive.getmembers()
            if member.isfile()
        ]

    return sorted(extracted_paths)


def run_gcn_circulars_archive_download(args: argparse.Namespace) -> None:
    """Download the GCN circulars JSON archive from the parsed CLI arguments."""
    run_id = generate_run_id()
    base_output_dir = resolve_project_path(args.output_dir)
    run_dir = build_run_output_dir(base_output_dir, run_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    setup_archive_logging(run_dir)

    archive_path = run_dir / DEFAULT_ARCHIVE_FILENAME
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "created_at": run_id,
        "url": args.url,
        "output_directory": str(run_dir),
        "archive_file": archive_path.name,
        "extract_requested": bool(args.extract),
        "extract_directory": None,
        "extracted_files": [],
        "download": None,
        "counts": {
            "extracted_files": 0,
        },
        "errors": [],
    }

    logging.info("Starting GCN circulars archive download")
    logging.info("URL: %s", args.url)
    logging.info("Output directory: %s", run_dir)
    logging.info("Extract after download: %s", "yes" if args.extract else "no")

    try:
        download_meta = download_archive_file(url=args.url, destination=archive_path)
        manifest["download"] = {
            **download_meta,
            "sha256": compute_sha256(archive_path),
        }

        if args.extract:
            extract_dir = run_dir / DEFAULT_EXTRACTED_DIRNAME
            extracted_files = extract_archive_file(archive_path, extract_dir)
            manifest["extract_directory"] = str(extract_dir)
            manifest["extracted_files"] = extracted_files
            manifest["counts"]["extracted_files"] = len(extracted_files)
            logging.info("Extracted %s files", len(extracted_files))

        logging.info("Download completed successfully")

    except Exception as exc:
        manifest["errors"].append({"error": str(exc)})
        logging.exception("GCN circulars archive download failed")
        raise

    finally:
        save_json(run_dir / "manifest.json", manifest)
