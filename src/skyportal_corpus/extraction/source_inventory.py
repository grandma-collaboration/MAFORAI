"""Operational logic for raw SkyPortal source-inventory extraction."""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from ..core import (
    ResolvedInventoryProfile,
    SkyPortalConfig,
    build_run_output_dir,
    load_skyportal_config,
    merge_cli_overrides,
    resolve_inventory_profile,
)
from .skyportal_client import SkyPortalClient


def setup_inventory_logging(output_dir: Path) -> None:
    """Configure logging to console and file for one inventory run."""
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
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, default=str)


def parse_query_params(raw_params: list[str]) -> dict[str, str]:
    """Parse repeated `key=value` query-parameter arguments."""
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


def extract_sources_from_payload(payload: dict[str, Any]) -> tuple[list[Any], int | None]:
    """Extract source rows and `totalMatches` from `/api/sources` payloads."""
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


def build_base_inventory_profile(
    config: SkyPortalConfig,
    profile_name: str | None,
) -> ResolvedInventoryProfile:
    """Build the inventory profile that will later receive CLI overrides."""
    if profile_name:
        return resolve_inventory_profile(config, profile_name)

    defaults = config.inventory.defaults
    return ResolvedInventoryProfile(
        name="adhoc",
        description="Ad hoc inventory run without a named profile.",
        run_label="",
        output_dir=config.paths.inventory,
        num_per_page=defaults.num_per_page,
        start_page=defaults.start_page,
        max_pages=defaults.max_pages,
        timeout_seconds=defaults.timeout_seconds,
        max_retries=defaults.max_retries,
        sleep_seconds=defaults.sleep_seconds,
        query_params={},
    )


def run_source_inventory(args: argparse.Namespace) -> None:
    """Run one raw paginated `/api/sources` extraction from parsed CLI args."""
    config = load_skyportal_config(args.config)
    base_profile = build_base_inventory_profile(config, args.profile)
    cli_query_params = parse_query_params(args.query_param)
    effective_profile = merge_cli_overrides(
        base_profile,
        {
            "run_label": args.run_label,
            "output_dir": args.output_dir,
            "num_per_page": args.num_per_page,
            "start_page": args.start_page,
            "max_pages": args.max_pages,
            "timeout": args.timeout,
            "max_retries": args.max_retries,
            "sleep": args.sleep,
            "query_params": cli_query_params,
        },
    )
    effective_base_url = (args.base_url or config.skyportal.base_url).rstrip("/")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if effective_profile.run_label:
        label = sanitize_label(effective_profile.run_label)
        run_name = f"source_inventory_{label}_{timestamp}"
    else:
        run_name = f"source_inventory_{timestamp}"

    run_dir = build_run_output_dir(effective_profile.output_dir, run_name)
    run_dir.mkdir(parents=True, exist_ok=True)

    setup_inventory_logging(run_dir)

    client = SkyPortalClient.from_config(config)
    client.base_url = effective_base_url

    manifest: dict[str, Any] = {
        "run_id": f"source_inventory_{timestamp}",
        "run_label": effective_profile.run_label or None,
        "profile_name": args.profile,
        "created_at": timestamp,
        "config_file": str(config.source_path),
        "base_url": effective_base_url,
        "endpoint": "/sources",
        "output_directory": str(run_dir),
        "query_parameters": {
            **effective_profile.query_params,
            "numPerPage": effective_profile.num_per_page,
        },
        "pagination": {
            "start_page": effective_profile.start_page,
            "max_pages": effective_profile.max_pages,
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
    logging.info("Config file: %s", config.source_path)
    logging.info("Profile: %s", args.profile or "adhoc")
    logging.info("Base URL: %s", effective_base_url)
    logging.info("Output directory: %s", run_dir)
    logging.info("numPerPage: %s", effective_profile.num_per_page)
    logging.info("max_pages: %s", effective_profile.max_pages)

    current_page = effective_profile.start_page
    pages_fetched = 0

    while True:
        if (
            effective_profile.max_pages != 0
            and pages_fetched >= effective_profile.max_pages
        ):
            manifest["stopped_reason"] = "max_pages_reached"
            break

        params: dict[str, Any] = {
            **effective_profile.query_params,
            "pageNumber": current_page,
            "numPerPage": effective_profile.num_per_page,
        }

        logging.info("Fetching page %s", current_page)
        manifest["counts"]["pages_attempted"] += 1

        payload, request_meta = client.get_json(
            "/sources",
            params=params,
            timeout_seconds=effective_profile.timeout_seconds,
            max_retries=effective_profile.max_retries,
            logger=logging.getLogger(__name__),
        )

        page_info: dict[str, Any] = {
            "page_number": current_page,
            "params": params,
            "request": request_meta.as_dict(),
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
                "error": request_meta.error,
                "http_status_code": request_meta.http_status_code,
            }
            manifest["errors"].append(error_entry)
            manifest["pages"].append(page_info)
            manifest["stopped_reason"] = "request_failed"
            logging.error("Stopping because page %s failed", current_page)
            break

        page_info["api_status"] = request_meta.api_status
        page_info["api_message"] = request_meta.api_message

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
                (current_page - effective_profile.start_page)
                * effective_profile.num_per_page
                + len(sources)
            )

            if seen_until_now >= total_matches:
                manifest["stopped_reason"] = "api_total_matches_reached"
                break

        current_page += 1
        time.sleep(effective_profile.sleep_seconds)

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

