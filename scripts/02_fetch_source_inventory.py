"""
Fetch a raw SkyPortal source inventory.

This script queries GET /api/sources using pagination and saves each raw
API response as JSON. It does not normalize, clean, or select features.

Outputs:
- sources_page_XXX.json
- manifest.json
- source_inventory.log

Each run is stored under:
- data/raw/skyportal/inventory/source_inventory_<run_label>_<timestamp>/
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests


DEFAULT_BASE_URL = "https://skyportal-icare.ijclab.in2p3.fr/api"
DEFAULT_OUTPUT_DIR = "data/raw/skyportal/inventory"
DEFAULT_NUM_PER_PAGE = 100
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_RETRIES = 3


def load_dotenv_if_available() -> None:
    """Load .env file if python-dotenv is installed."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass


def get_token() -> str:
    """Read SkyPortal API token from environment."""
    load_dotenv_if_available()

    token = os.getenv("SKYPORTAL_API_TOKEN")
    if not token:
        raise ValueError(
            "SKYPORTAL_API_TOKEN is not set. "
            "Create a local .env file or export the variable manually."
        )

    return token


def setup_logging(output_dir: Path) -> None:
    """Configure logging to console and file."""
    log_file = output_dir / "source_inventory.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )


def save_json(path: Path, data: Any) -> None:
    """Save JSON data to disk."""
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def parse_query_params(raw_params: list[str]) -> dict[str, str]:
    """
    Parse optional query parameters passed as key=value.

    Example:
        --query-param hasSpectrum=true
        --query-param group_ids=1
    """
    params: dict[str, str] = {}

    for item in raw_params:
        if "=" not in item:
            raise ValueError(
                f"Invalid query parameter '{item}'. Expected format: key=value"
            )

        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not key:
            raise ValueError(f"Invalid query parameter '{item}': empty key")

        params[key] = value

    return params


def api_get_with_retries(
    session: requests.Session,
    url: str,
    params: dict[str, Any],
    timeout: int,
    max_retries: int,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """
    Perform GET request with retries.

    Returns:
        payload: parsed JSON payload or None
        metadata: request metadata and possible error information
    """
    metadata: dict[str, Any] = {
        "url": url,
        "params": params,
        "http_status_code": None,
        "elapsed_seconds": None,
        "json_valid": False,
        "error": None,
    }

    for attempt in range(1, max_retries + 1):
        start = time.perf_counter()

        try:
            response = session.get(url, params=params, timeout=timeout)
            elapsed = time.perf_counter() - start

            metadata["http_status_code"] = response.status_code
            metadata["elapsed_seconds"] = round(elapsed, 3)

            try:
                payload = response.json()
                metadata["json_valid"] = True

            except ValueError:
                metadata["error"] = "Response is not valid JSON"
                return None, metadata

            if response.status_code == 200:
                return payload, metadata

            metadata["error"] = (
                f"HTTP {response.status_code}: "
                f"{payload.get('message') if isinstance(payload, dict) else 'unknown'}"
            )

            logging.warning(
                "HTTP error on attempt %s/%s: %s",
                attempt,
                max_retries,
                metadata["error"],
            )

        except requests.exceptions.RequestException as exc:
            elapsed = time.perf_counter() - start
            metadata["elapsed_seconds"] = round(elapsed, 3)
            metadata["error"] = str(exc)

            logging.warning(
                "Request failed on attempt %s/%s: %s",
                attempt,
                max_retries,
                exc,
            )

        time.sleep(2 * attempt)

    return None, metadata


def extract_sources_from_payload(payload: dict[str, Any]) -> tuple[list[Any], int | None]:
    """
    Extract sources list and totalMatches from a SkyPortal /sources response.

    Expected structure:
    {
        "status": "success",
        "data": {
            "totalMatches": ...,
            "sources": [...],
            "pageNumber": ...,
            "numPerPage": ...
        }
    }
    """
    data = payload.get("data", {})

    if not isinstance(data, dict):
        return [], None

    sources = data.get("sources", [])
    total_matches = data.get("totalMatches")

    if not isinstance(sources, list):
        sources = []

    if not isinstance(total_matches, int):
        total_matches = None

    return sources, total_matches


def sanitize_label(label: str) -> str:
    """Convert a human-readable run label into a safe folder-name fragment."""
    return (
        label.strip()
        .lower()
        .replace(" ", "_")
        .replace("/", "_")
        .replace("\\", "_")
    )

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch raw paginated source inventory from SkyPortal."
    )
    parser.add_argument(
        "--run-label",
        default=None,
        help="Optional semantic label for the run, e.g. has_spectrum, gcn, classified.",
    )

    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"SkyPortal API base URL. Default: {DEFAULT_BASE_URL}",
    )

    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Base output directory. Default: {DEFAULT_OUTPUT_DIR}",
    )

    parser.add_argument(
        "--num-per-page",
        type=int,
        default=DEFAULT_NUM_PER_PAGE,
        help=f"Number of sources per page. Default: {DEFAULT_NUM_PER_PAGE}",
    )

    parser.add_argument(
        "--start-page",
        type=int,
        default=1,
        help="First page number to fetch. Default: 1",
    )

    parser.add_argument(
        "--max-pages",
        type=int,
        default=5,
        help=(
            "Maximum number of pages to fetch. Default: 5. "
            "Use 0 to continue until the API-reported total is reached."
        ),
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Request timeout in seconds. Default: {DEFAULT_TIMEOUT_SECONDS}",
    )

    parser.add_argument(
        "--max-retries",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help=f"Maximum retries per page. Default: {DEFAULT_MAX_RETRIES}",
    )

    parser.add_argument(
        "--sleep",
        type=float,
        default=0.3,
        help="Sleep time between page requests in seconds. Default: 0.3",
    )

    parser.add_argument(
        "--query-param",
        action="append",
        default=[],
        help=(
            "Additional query parameter as key=value. "
            "Can be used multiple times."
        ),
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.num_per_page <= 0:
        raise ValueError("--num-per-page must be positive")

    if args.start_page <= 0:
        raise ValueError("--start-page must be positive")

    if args.max_pages < 0:
        raise ValueError("--max-pages must be >= 0")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if args.run_label:
        label = sanitize_label(args.run_label)
        run_name = f"source_inventory_{label}_{timestamp}"
    else:
        run_name = f"source_inventory_{timestamp}"

    run_dir = Path(args.output_dir) / run_name

    
    run_dir.mkdir(parents=True, exist_ok=True)

    setup_logging(run_dir)

    token = get_token()

    session = requests.Session()
    session.headers.update({"Authorization": f"token {token}"})

    url = f"{args.base_url.rstrip('/')}/sources"
    extra_params = parse_query_params(args.query_param)

    manifest: dict[str, Any] = {
        "run_id": f"source_inventory_{timestamp}",
        "run_label": args.run_label,
        "created_at": timestamp,
        "base_url": args.base_url.rstrip("/"),
        "endpoint": "/sources",
        "output_directory": str(run_dir),
        "query_parameters": {
            **extra_params,
            "numPerPage": args.num_per_page,
        },
        "pagination": {
            "start_page": args.start_page,
            "max_pages": args.max_pages,
        },
        "api_reported_total_matches": None,
        "pages": [],
        "counts": {
            "pages_attempted": 0,
            "pages_saved": 0,
            "sources_seen_in_saved_pages": 0,
        },
        "stopped_reason": None,
        "errors": [],
    }

    logging.info("Starting source inventory fetch")
    logging.info("URL: %s", url)
    logging.info("Output directory: %s", run_dir)
    logging.info("numPerPage: %s", args.num_per_page)
    logging.info("max_pages: %s", args.max_pages)

    current_page = args.start_page
    pages_fetched = 0

    while True:
        if args.max_pages != 0 and pages_fetched >= args.max_pages:
            manifest["stopped_reason"] = "max_pages_reached"
            break

        params: dict[str, Any] = {
            **extra_params,
            "pageNumber": current_page,
            "numPerPage": args.num_per_page,
        }

        logging.info("Fetching page %s", current_page)
        manifest["counts"]["pages_attempted"] += 1

        payload, request_meta = api_get_with_retries(
            session=session,
            url=url,
            params=params,
            timeout=args.timeout,
            max_retries=args.max_retries,
        )

        page_info: dict[str, Any] = {
            "page_number": current_page,
            "params": params,
            "request": request_meta,
            "saved": False,
            "response_file": None,
            "api_status": None,
            "api_message": None,
            "n_sources": 0,
            "total_matches": None,
        }

        if payload is None:
            error_entry = {
                "page_number": current_page,
                "error": request_meta.get("error"),
                "http_status_code": request_meta.get("http_status_code"),
            }
            manifest["errors"].append(error_entry)
            manifest["pages"].append(page_info)
            manifest["stopped_reason"] = "request_failed"
            logging.error("Stopping because page %s failed", current_page)
            break

        page_info["api_status"] = payload.get("status")
        page_info["api_message"] = payload.get("message")

        output_file = run_dir / f"sources_page_{current_page:03d}.json"
        save_json(output_file, payload)

        sources, total_matches = extract_sources_from_payload(payload)

        page_info["saved"] = True
        page_info["response_file"] = output_file.name
        page_info["n_sources"] = len(sources)
        page_info["total_matches"] = total_matches

        manifest["counts"]["pages_saved"] += 1
        manifest["counts"]["sources_seen_in_saved_pages"] += len(sources)

        if total_matches is not None:
            manifest["api_reported_total_matches"] = total_matches

        manifest["pages"].append(page_info)

        logging.info(
            "Saved page %s with %s sources. API totalMatches=%s",
            current_page,
            len(sources),
            total_matches,
        )

        pages_fetched += 1

        if len(sources) == 0:
            manifest["stopped_reason"] = "empty_sources_page"
            break

        if total_matches is not None:
            seen_until_now = (
                (current_page - args.start_page) * args.num_per_page + len(sources)
            )

            if seen_until_now >= total_matches:
                manifest["stopped_reason"] = "api_total_matches_reached"
                break

        current_page += 1
        time.sleep(args.sleep)

    if manifest["stopped_reason"] is None:
        manifest["stopped_reason"] = "completed"

    manifest_file = run_dir / "manifest.json"
    save_json(manifest_file, manifest)

    logging.info("Inventory fetch complete")
    logging.info("Pages saved: %s", manifest["counts"]["pages_saved"])
    logging.info(
        "Sources seen in saved pages: %s",
        manifest["counts"]["sources_seen_in_saved_pages"],
    )
    logging.info("Stopped reason: %s", manifest["stopped_reason"])
    logging.info("Manifest saved to %s", manifest_file)


if __name__ == "__main__":
    main()
