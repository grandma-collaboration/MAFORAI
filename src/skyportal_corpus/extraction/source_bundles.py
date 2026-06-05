"""Fetch per-source SkyPortal bundles from a selected source list."""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from ..core import (
    build_run_output_dir,
    default_skyportal_config_path,
    load_skyportal_config,
    resolve_project_path,
    source_bundles_output_dir,
)
from .skyportal_client import SkyPortalClient

DEFAULT_SELECTED_SOURCES_PATH = "data/samples/selected_sources_for_bundles.json"

BUNDLE_ENDPOINTS = (
    {
        "name": "source",
        "path_template": "/sources/{source_id}",
        "params": None,
        "output_file": "source.json",
    },
    {
        "name": "photometry_flux",
        "path_template": "/sources/{source_id}/photometry",
        "params": {"format": "flux"},
        "output_file": "photometry_flux.json",
    },
    {
        "name": "photometry_mag",
        "path_template": "/sources/{source_id}/photometry",
        "params": {"format": "mag"},
        "output_file": "photometry_mag.json",
    },
    {
        "name": "phot_stat",
        "path_template": "/sources/{source_id}/phot_stat",
        "params": None,
        "output_file": "phot_stat.json",
    },
    {
        "name": "comments",
        "path_template": "/sources/{source_id}/comments",
        "params": None,
        "output_file": "comments.json",
    },
    {
        "name": "classifications",
        "path_template": "/sources/{source_id}/classifications",
        "params": None,
        "output_file": "classifications.json",
    },
    {
        "name": "spectra",
        "path_template": "/sources/{source_id}/spectra",
        "params": None,
        "output_file": "spectra.json",
    },
    {
        "name": "annotations",
        "path_template": "/sources/{source_id}/annotations",
        "params": None,
        "output_file": "annotations.json",
    },
    {
        "name": "associated_gcns",
        "path_template": "/associated_gcns/{source_id}",
        "params": None,
        "output_file": "associated_gcns.json",
    },
    {
        "name": "position",
        "path_template": "/sources/{source_id}/position",
        "params": None,
        "output_file": "position.json",
    },
    {
        "name": "offsets",
        "path_template": "/sources/{source_id}/offsets",
        "params": None,
        "output_file": "offsets.json",
    },
    {
        "name": "color_mag",
        "path_template": "/sources/{source_id}/color_mag",
        "params": None,
        "output_file": "color_mag.json",
    },
)


def save_json(path: Path, data: Any) -> None:
    """Save JSON data to disk."""
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, default=str)


def load_json_object(path: Path) -> dict[str, Any]:
    """Load one JSON object from disk."""
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")

    return payload


def setup_bundle_logging(output_dir: Path) -> None:
    """Configure logging to console and file for one bundle run."""
    log_file = output_dir / "source_bundles.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
        force=True,
    )


def sanitize_source_id(source_id: str) -> str:
    """Keep source IDs readable while avoiding accidental nested paths."""
    return source_id.replace("/", "_").replace("\\", "_").strip()


def build_selected_sources_input_path(path_value: str | Path | None) -> Path:
    """Resolve the selected-sources input path."""
    if path_value is None:
        return resolve_project_path(DEFAULT_SELECTED_SOURCES_PATH)
    return resolve_project_path(path_value)


def filter_selected_sources(
    payload: dict[str, Any],
    *,
    priority: str,
) -> list[dict[str, Any]]:
    """Keep only the selected events matching one priority bucket."""
    selected_sources = payload.get("selected_sources", [])
    if not isinstance(selected_sources, list):
        raise ValueError("Expected 'selected_sources' list in selected sources file")

    filtered = [
        event
        for event in selected_sources
        if isinstance(event, dict) and event.get("priority") == priority
    ]
    return filtered


def build_endpoint_path(path_template: str, source_id: str) -> str:
    """Render one endpoint path for one source ID."""
    return path_template.format(source_id=source_id)


def fetch_one_source_bundle(
    client: SkyPortalClient,
    source_event: dict[str, Any],
    source_dir: Path,
    *,
    timeout_seconds: int,
    max_retries: int,
) -> tuple[dict[str, Any], int, int]:
    """Fetch the configured endpoint bundle for one selected source."""
    source_id = str(source_event.get("id", ""))
    endpoint_results: list[dict[str, Any]] = []
    success_count = 0
    failure_count = 0

    for endpoint in BUNDLE_ENDPOINTS:
        path = build_endpoint_path(endpoint["path_template"], source_id)
        payload, request_meta = client.get_json(
            path,
            params=endpoint["params"],
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            logger=logging.getLogger(__name__),
        )

        endpoint_record = {
            "name": endpoint["name"],
            "path": path,
            "params": endpoint["params"],
            "output_file": endpoint["output_file"],
            "saved": False,
            "request": request_meta.as_dict(),
        }

        if payload is None:
            failure_count += 1
            endpoint_results.append(endpoint_record)
            logging.warning(
                "Failed endpoint %s for %s: %s",
                endpoint["name"],
                source_id,
                request_meta.error,
            )
            continue

        save_json(source_dir / endpoint["output_file"], payload)
        endpoint_record["saved"] = True
        success_count += 1
        endpoint_results.append(endpoint_record)

    source_manifest = {
        "source_id": source_id,
        "priority": source_event.get("priority"),
        "gcn_source_type": source_event.get("gcn_source_type"),
        "source_directory": str(source_dir),
        "selection_context": source_event.get("selection_context"),
        "selection_reasons": source_event.get("selection_reasons"),
        "source_summary": source_event.get("source_summary"),
        "counts": {
            "endpoint_requests_attempted": len(BUNDLE_ENDPOINTS),
            "endpoint_requests_succeeded": success_count,
            "endpoint_requests_failed": failure_count,
        },
        "endpoints": endpoint_results,
    }

    save_json(source_dir / "bundle_manifest.json", source_manifest)
    return source_manifest, success_count, failure_count


def run_source_bundles(args: argparse.Namespace) -> None:
    """Fetch per-source bundles from the selected-sources file."""
    config = load_skyportal_config(args.config)
    selected_sources_path = build_selected_sources_input_path(args.selected_sources_path)
    selected_payload = load_json_object(selected_sources_path)
    selected_sources = filter_selected_sources(selected_payload, priority=args.priority)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_output_dir = (
        resolve_project_path(args.output_dir)
        if args.output_dir
        else source_bundles_output_dir(config)
    )
    run_dir = build_run_output_dir(base_output_dir, f"source_bundle_run_{timestamp}")
    run_dir.mkdir(parents=True, exist_ok=True)

    setup_bundle_logging(run_dir)

    client = SkyPortalClient.from_config(config)
    if args.base_url:
        client.base_url = args.base_url.rstrip("/")

    manifest: dict[str, Any] = {
        "run_id": f"source_bundle_run_{timestamp}",
        "created_at": timestamp,
        "config_file": str(config.source_path),
        "base_url": client.base_url,
        "selected_sources_file": str(selected_sources_path),
        "priority_filter": args.priority,
        "output_directory": str(run_dir),
        "endpoints": [
            {
                "name": endpoint["name"],
                "path_template": endpoint["path_template"],
                "params": endpoint["params"],
                "output_file": endpoint["output_file"],
            }
            for endpoint in BUNDLE_ENDPOINTS
        ],
        "counts": {
            "selected_sources_available": len(selected_payload.get("selected_sources", []))
            if isinstance(selected_payload.get("selected_sources", []), list)
            else None,
            "selected_sources_kept": len(selected_sources),
            "sources_attempted": 0,
            "sources_completed": 0,
            "sources_with_errors": 0,
            "endpoint_requests_attempted": 0,
            "endpoint_requests_succeeded": 0,
            "endpoint_requests_failed": 0,
        },
        "sources": [],
    }

    logging.info("Starting source bundle fetch")
    logging.info("Selected sources file: %s", selected_sources_path)
    logging.info("Priority filter: %s", args.priority)
    logging.info("Output directory: %s", run_dir)
    logging.info("Sources kept: %s", len(selected_sources))

    for source_event in selected_sources:
        source_id = str(source_event.get("id", "")).strip()
        if not source_id:
            continue

        manifest["counts"]["sources_attempted"] += 1
        source_dir = run_dir / sanitize_source_id(source_id)
        source_dir.mkdir(parents=True, exist_ok=True)
        logging.info("Fetching source bundle for %s", source_id)

        source_manifest, success_count, failure_count = fetch_one_source_bundle(
            client,
            source_event,
            source_dir,
            timeout_seconds=args.timeout,
            max_retries=args.max_retries,
        )

        manifest["counts"]["endpoint_requests_attempted"] += len(BUNDLE_ENDPOINTS)
        manifest["counts"]["endpoint_requests_succeeded"] += success_count
        manifest["counts"]["endpoint_requests_failed"] += failure_count

        if failure_count == 0:
            manifest["counts"]["sources_completed"] += 1
        else:
            manifest["counts"]["sources_with_errors"] += 1

        manifest["sources"].append(
            {
                "source_id": source_id,
                "priority": source_event.get("priority"),
                "gcn_source_type": source_event.get("gcn_source_type"),
                "source_directory": source_manifest["source_directory"],
                "endpoint_requests_succeeded": success_count,
                "endpoint_requests_failed": failure_count,
            }
        )

        time.sleep(args.sleep)

    save_json(run_dir / "manifest.json", manifest)
    logging.info("Finished source bundle fetch")
    logging.info("Completed sources: %s", manifest["counts"]["sources_completed"])
    logging.info("Sources with errors: %s", manifest["counts"]["sources_with_errors"])
    logging.info(
        "Endpoint requests: %s success / %s failed",
        manifest["counts"]["endpoint_requests_succeeded"],
        manifest["counts"]["endpoint_requests_failed"],
    )
