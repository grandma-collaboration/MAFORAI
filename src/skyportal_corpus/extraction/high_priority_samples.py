"""Export a compact shared sample for the current high-priority source set."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core import resolve_project_path

DEFAULT_SELECTED_SOURCES_PATH = "data/samples/selected_sources_for_bundles.json"
DEFAULT_SAMPLES_DIR = "data/samples"


def load_json_object(path: Path) -> dict[str, Any]:
    """Load one JSON object from disk."""
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")

    return payload


def load_optional_json_object(path: Path) -> dict[str, Any]:
    """Load one JSON object from disk, or return an empty payload if missing."""
    if not path.exists():
        return {"data": None}
    return load_json_object(path)


def save_json(path: Path, data: Any) -> None:
    """Save JSON data to disk."""
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, default=str)


def count_list_items(payload: dict[str, Any], nested_key: str | None = None) -> int:
    """Count items in a response payload list or nested list."""
    data = payload.get("data")
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict) and nested_key:
        nested = data.get(nested_key)
        if isinstance(nested, list):
            return len(nested)
    return 0


def has_nonempty_data(payload: dict[str, Any]) -> bool:
    """Return whether the payload carries non-empty data."""
    data = payload.get("data")
    if isinstance(data, list):
        return len(data) > 0
    if isinstance(data, dict):
        return len(data) > 0
    return False


def build_selected_sources_input_path(path_value: str | Path | None) -> Path:
    """Resolve the selected sources input path."""
    if path_value is None:
        return resolve_project_path(DEFAULT_SELECTED_SOURCES_PATH)
    return resolve_project_path(path_value)


def filter_high_priority_sources(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Keep only the current high-priority events."""
    selected_sources = payload.get("selected_sources", [])
    if not isinstance(selected_sources, list):
        raise ValueError("Expected 'selected_sources' list in selected sources file")

    return [
        event
        for event in selected_sources
        if isinstance(event, dict) and event.get("priority") == "high"
    ]


def build_high_priority_sample_contract(
    selected_sources_path: Path,
    bundle_run_dir: Path,
    high_priority_sources: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the shared JSON contract for the current high-priority sample."""
    return {
        "sample_run": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "priority_filter": "high",
            "selected_sources_file": str(selected_sources_path),
            "bundle_run_directory": str(bundle_run_dir),
        },
        "summary": {
            "n_sources": len(high_priority_sources),
        },
        "sources": high_priority_sources,
    }


def build_bundle_summary_row(source_event: dict[str, Any], bundle_dir: Path) -> dict[str, Any]:
    """Build one compact per-source availability row from one fetched bundle."""
    source_payload = load_optional_json_object(bundle_dir / "source.json")
    source_data = source_payload.get("data", {}) if isinstance(source_payload, dict) else {}
    if not isinstance(source_data, dict):
        source_data = {}

    bundle_manifest = load_json_object(bundle_dir / "bundle_manifest.json")
    counts = bundle_manifest.get("counts", {})
    if not isinstance(counts, dict):
        counts = {}

    photometry_flux = load_optional_json_object(bundle_dir / "photometry_flux.json")
    photometry_mag = load_optional_json_object(bundle_dir / "photometry_mag.json")
    comments = load_optional_json_object(bundle_dir / "comments.json")
    classifications = load_optional_json_object(bundle_dir / "classifications.json")
    spectra = load_optional_json_object(bundle_dir / "spectra.json")
    annotations = load_optional_json_object(bundle_dir / "annotations.json")
    associated_gcns = load_optional_json_object(bundle_dir / "associated_gcns.json")
    phot_stat = load_optional_json_object(bundle_dir / "phot_stat.json")

    n_photometry_flux = count_list_items(photometry_flux)
    n_photometry_mag = count_list_items(photometry_mag)
    n_comments = count_list_items(comments)
    n_classifications = count_list_items(classifications)
    n_spectra = count_list_items(spectra, nested_key="spectra")
    n_annotations = count_list_items(annotations)
    n_associated_gcns = count_list_items(associated_gcns, nested_key="gcns")
    n_followup_requests = len(source_data.get("followup_requests", [])) if isinstance(source_data.get("followup_requests"), list) else 0

    return {
        "source_id": source_event.get("id"),
        "gcn_source_type": source_event.get("gcn_source_type"),
        "priority": source_event.get("priority"),
        "selection_score": source_event.get("selection_score"),
        "redshift": source_event.get("selection_context", {}).get("redshift"),
        "has_photometry_flux": n_photometry_flux > 0,
        "n_photometry_flux_points": n_photometry_flux,
        "has_photometry_mag": n_photometry_mag > 0,
        "n_photometry_mag_points": n_photometry_mag,
        "has_comments": n_comments > 0,
        "n_comments": n_comments,
        "has_classification": n_classifications > 0,
        "n_classifications": n_classifications,
        "has_spectra": n_spectra > 0,
        "n_spectra": n_spectra,
        "has_followup_requests": n_followup_requests > 0,
        "n_followup_requests": n_followup_requests,
        "has_associated_gcns": n_associated_gcns > 0,
        "n_associated_gcns": n_associated_gcns,
        "has_annotations": n_annotations > 0,
        "n_annotations": n_annotations,
        "has_phot_stat": has_nonempty_data(phot_stat),
        "has_summary": isinstance(source_data.get("summary"), str) and bool(source_data.get("summary").strip()),
        "has_tns_info": source_data.get("tns_info") is not None,
        "bundle_endpoint_failures": counts.get("endpoint_requests_failed"),
        "bundle_complete": counts.get("endpoint_requests_failed", 0) == 0,
    }


def write_bundle_summary_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write the per-source availability summary to CSV."""
    if not rows:
        raise ValueError("No rows available for bundle summary export")

    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run_high_priority_sample_export(args: argparse.Namespace) -> None:
    """Export the current high-priority shared sample into data/samples."""
    selected_sources_path = build_selected_sources_input_path(args.selected_sources_path)
    bundle_run_dir = resolve_project_path(args.bundle_run_dir)
    output_dir = resolve_project_path(args.output_dir or DEFAULT_SAMPLES_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    selected_payload = load_json_object(selected_sources_path)
    high_priority_sources = filter_high_priority_sources(selected_payload)

    sample_payload = build_high_priority_sample_contract(
        selected_sources_path=selected_sources_path,
        bundle_run_dir=bundle_run_dir,
        high_priority_sources=high_priority_sources,
    )
    sample_json_path = output_dir / "selected_sources_high.json"
    save_json(sample_json_path, sample_payload)

    summary_rows = [
        build_bundle_summary_row(source_event, bundle_run_dir / str(source_event["id"]))
        for source_event in high_priority_sources
    ]
    summary_rows.sort(key=lambda row: str(row["source_id"]))
    summary_csv_path = output_dir / "selected_sources_high_bundle_summary.csv"
    write_bundle_summary_csv(summary_csv_path, summary_rows)

    print(f"Wrote high-priority sample: {sample_json_path}")
    print(f"Wrote high-priority bundle summary: {summary_csv_path}")
    print(f"Sources exported: {len(high_priority_sources)}")
