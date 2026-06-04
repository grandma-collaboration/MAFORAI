"""Helpers for selecting GCN-derived GRANDMA events from saved inventories."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core import resolve_project_path

DEFAULT_SELECTION_OUTPUT = "data/samples/selected_sources_for_bundles.json"
DEFAULT_GCN_GRANDMA_OUTPUT = "data/samples/gcn_grandma.json"
DEFAULT_GCN_GRANDMA_INPUT = "data/samples/gcn_grandma_grandma_base.json"
GRANDMA_GROUP_ID = 3
KNC_GROUP_ID = 38
PRIORITY_RANK = {
    "high": 0,
    "medium": 1,
    "low": 2,
}
GCN_DERIVED_RULES = {
    "grb": "id starts with GRB",
    "gw": "id starts with GW",
    "ep": "id starts with EP",
    "gcn": "id starts with GCN",
}
GCN_BUNDLE_PRIORITY_RULES = {
    "high": "extreme redshift, or redshift+comments+num_det_global>=5, or GO GRANDMA (HIGH PRIORITY)",
    "medium": "known redshift, or comments+num_det_global>=5, or GRB/GO GRANDMA classification support",
    "low": "remaining GCN-derived events",
}


def save_json(path: Path, data: Any) -> None:
    """Save JSON data to disk."""
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def load_json_object(path: Path) -> dict[str, Any]:
    """Load one JSON object from disk."""
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")

    return payload


def load_inventory_manifest(inventory_dir: Path) -> dict[str, Any]:
    """Load the manifest for one saved source-inventory run."""
    manifest_path = inventory_dir / "manifest.json"

    if not manifest_path.exists():
        raise FileNotFoundError(f"Inventory manifest not found: {manifest_path}")

    return load_json_object(manifest_path)


def load_inventory_sources(inventory_dir: Path) -> list[dict[str, Any]]:
    """Load every source row saved under one inventory directory."""
    sources: list[dict[str, Any]] = []

    for page_path in sorted(inventory_dir.glob("sources_page_*.json")):
        payload = load_json_object(page_path)
        page_sources = payload.get("data", {}).get("sources", [])
        if not isinstance(page_sources, list):
            continue

        for source in page_sources:
            if isinstance(source, dict):
                sources.append(source)

    if not sources:
        raise ValueError(f"No sources found in inventory directory: {inventory_dir}")

    return sources


def classify_gcn_derived_type(source_id: str) -> str:
    """Classify a GCN-derived source ID into its subtype."""
    if source_id.startswith("GRB"):
        return "grb"
    if source_id.startswith("GW"):
        return "gw"
    if source_id.startswith("EP"):
        return "ep"
    if source_id.startswith("GCN"):
        return "gcn"
    return "other"


def is_gcn_derived_source(source_id: str) -> bool:
    """Return whether the source ID follows the GCN-derived naming scheme."""
    return classify_gcn_derived_type(source_id) != "other"


def extract_num_det_global(source: dict[str, Any]) -> int:
    """Extract the compact detection count from `photstats` when available."""
    photstats = source.get("photstats")
    if not isinstance(photstats, list) or not photstats:
        return 0

    first_entry = photstats[0]
    if not isinstance(first_entry, dict):
        return 0

    num_det_global = first_entry.get("num_det_global")
    if not isinstance(num_det_global, int):
        return 0

    return num_det_global


def extract_relevant_groups(source: dict[str, Any]) -> list[str]:
    """Keep only the workflow-relevant group names for one source."""
    relevant_names: list[str] = []

    for group in source.get("groups", []):
        if not isinstance(group, dict):
            continue

        group_id = group.get("id")
        group_name = group.get("name")

        if group_id in {GRANDMA_GROUP_ID, KNC_GROUP_ID} and isinstance(group_name, str):
            relevant_names.append(group_name)

    return relevant_names


def extract_classification_labels(source: dict[str, Any]) -> list[str]:
    """Extract the compact list of classification labels from one source row."""
    labels: list[str] = []
    for classification in source.get("classifications", []):
        if not isinstance(classification, dict):
            continue

        label = classification.get("classification")
        if isinstance(label, str) and label not in labels:
            labels.append(label)

    return labels


def extract_has_host(source: dict[str, Any]) -> bool:
    """Return whether the source row exposes a host association."""
    host_id = source.get("host_id")
    return isinstance(host_id, int)


def build_gcn_grandma_event(source: dict[str, Any]) -> dict[str, Any]:
    """Build one compact GCN-derived source record."""
    source_id = str(source.get("id", ""))
    redshift = source.get("redshift")
    if not isinstance(redshift, (int, float)):
        redshift = None

    return {
        "id": source_id,
        "gcn_source_type": classify_gcn_derived_type(source_id),
        "redshift": redshift,
        "comment_exists": bool(source.get("comment_exists")),
        "num_det_global": extract_num_det_global(source),
        "has_host": extract_has_host(source),
        "groups": extract_relevant_groups(source),
        "classification_labels": extract_classification_labels(source),
        "source_summary": source.get("summary"),
    }


def build_gcn_grandma_contract(
    inventory_dir: Path,
    output_path: Path,
    manifest: dict[str, Any],
    sources: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the base list of all GCN-derived GRANDMA sources."""
    gcn_sources = [
        build_gcn_grandma_event(source)
        for source in sources
        if is_gcn_derived_source(str(source.get("id", "")))
    ]
    gcn_sources.sort(key=lambda item: (item["gcn_source_type"], item["id"]))
    subtype_counts = Counter(item["gcn_source_type"] for item in gcn_sources)

    return {
        "gcn_grandma_run": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "inventory_dir": str(inventory_dir),
            "inventory_run_label": manifest.get("run_label"),
            "inventory_profile_name": manifest.get("profile_name"),
            "output_file": str(output_path),
        },
        "criteria": {
            "base": [
                "group_ids=3",
            ],
            "gcn_derived_id_rules": GCN_DERIVED_RULES,
        },
        "sources": gcn_sources,
        "summary": {
            "input_counts": {
                "total_sources": len(sources),
                "gcn_derived_sources": len(gcn_sources),
                "by_type": {
                    "gcn": subtype_counts.get("gcn", 0),
                    "grb": subtype_counts.get("grb", 0),
                    "gw": subtype_counts.get("gw", 0),
                    "ep": subtype_counts.get("ep", 0),
                },
            }
        },
    }


def build_gcn_bundle_selection_reasons(event: dict[str, Any]) -> list[str]:
    """Build the explicit list of reasons for one final GCN-derived candidate."""
    reasons = ["in_gcn_grandma_base"]

    redshift = event.get("redshift")
    if isinstance(redshift, (int, float)):
        reasons.append("has_redshift")
        if redshift < 1 or redshift > 4:
            reasons.append("redshift_extreme")

    if event.get("comment_exists"):
        reasons.append("has_comments")

    num_det_global = event.get("num_det_global")
    if isinstance(num_det_global, int):
        if num_det_global >= 2:
            reasons.append("num_det_global_gte_2")
        if num_det_global >= 5:
            reasons.append("num_det_global_gte_5")

    if event.get("has_host"):
        reasons.append("has_host")

    labels = event.get("classification_labels", [])
    if isinstance(labels, list):
        if "GRB" in labels:
            reasons.append("classified_as_grb")
        if "GO GRANDMA" in labels:
            reasons.append("go_grandma")
        if "GO GRANDMA (HIGH PRIORITY)" in labels:
            reasons.append("go_grandma_high_priority")
        if "STOP GRANDMA" in labels:
            reasons.append("stop_grandma")

    return reasons


def assign_gcn_bundle_priority(event: dict[str, Any]) -> tuple[str, int]:
    """Assign a simple priority and ordering score from one GCN-derived event."""
    redshift = event.get("redshift")
    comment_exists = bool(event.get("comment_exists"))
    num_det_global = event.get("num_det_global")
    if not isinstance(num_det_global, int):
        num_det_global = 0
    labels = event.get("classification_labels", [])
    if not isinstance(labels, list):
        labels = []

    score = 0

    if isinstance(redshift, (int, float)):
        score += 2
        if redshift < 1 or redshift > 4:
            score += 4

    if comment_exists:
        score += 1

    if num_det_global >= 2:
        score += 1
    if num_det_global >= 5:
        score += 2

    if "GRB" in labels:
        score += 2
    if "GO GRANDMA" in labels:
        score += 1
    if "GO GRANDMA (HIGH PRIORITY)" in labels:
        score += 3

    if "GO GRANDMA (HIGH PRIORITY)" in labels:
        return "high", score
    if isinstance(redshift, (int, float)) and (redshift < 1 or redshift > 4):
        return "high", score
    if isinstance(redshift, (int, float)) and comment_exists and num_det_global >= 5:
        return "high", score
    if (
        isinstance(redshift, (int, float))
        or (comment_exists and num_det_global >= 5)
        or "GRB" in labels
        or "GO GRANDMA" in labels
    ):
        return "medium", score
    return "low", score


def build_gcn_bundle_candidate(event: dict[str, Any]) -> dict[str, Any]:
    """Build one final bundle candidate from the GCN-derived GRANDMA base list."""
    priority, score = assign_gcn_bundle_priority(event)
    return {
        "id": event.get("id"),
        "gcn_source_type": event.get("gcn_source_type"),
        "priority": priority,
        "selection_score": score,
        "selection_reasons": build_gcn_bundle_selection_reasons(event),
        "selection_context": {
            "redshift": event.get("redshift"),
            "comment_exists": event.get("comment_exists"),
            "num_det_global": event.get("num_det_global"),
            "has_host": event.get("has_host"),
            "groups": event.get("groups"),
            "classification_labels": event.get("classification_labels"),
        },
        "source_summary": event.get("source_summary"),
    }


def gcn_bundle_candidate_sort_key(candidate: dict[str, Any]) -> tuple[int, int, int, str]:
    """Sort final bundle candidates deterministically."""
    context = candidate.get("selection_context", {})
    num_det_global = context.get("num_det_global")
    if not isinstance(num_det_global, int):
        num_det_global = 0

    return (
        PRIORITY_RANK[candidate["priority"]],
        -candidate["selection_score"],
        -num_det_global,
        candidate["id"],
    )


def build_gcn_bundle_selection_contract(
    gcn_grandma_path: Path,
    output_path: Path,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Build the final prioritized bundle-selection file from the GCN-derived base list."""
    gcn_sources = payload.get("sources", [])
    if not isinstance(gcn_sources, list):
        raise ValueError(f"Expected 'sources' list in {gcn_grandma_path}")

    candidates = [
        build_gcn_bundle_candidate(event)
        for event in gcn_sources
        if isinstance(event, dict)
    ]
    candidates.sort(key=gcn_bundle_candidate_sort_key)
    priority_counts = Counter(candidate["priority"] for candidate in candidates)
    type_counts = Counter(candidate["gcn_source_type"] for candidate in candidates)

    return {
        "selection_run": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "input_file": str(gcn_grandma_path),
            "input_run_label": payload.get("gcn_grandma_run", {}).get("inventory_run_label"),
            "output_file": str(output_path),
        },
        "criteria": {
            "base": [
                "GCN-derived source in GRANDMA",
            ],
            "priority_rules": GCN_BUNDLE_PRIORITY_RULES,
        },
        "selected_sources": candidates,
        "summary": {
            "input_counts": {
                "gcn_derived_sources": len(candidates),
                "by_type": {
                    "gcn": type_counts.get("gcn", 0),
                    "grb": type_counts.get("grb", 0),
                    "gw": type_counts.get("gw", 0),
                    "ep": type_counts.get("ep", 0),
                },
            },
            "priority_counts": {
                "high": priority_counts.get("high", 0),
                "medium": priority_counts.get("medium", 0),
                "low": priority_counts.get("low", 0),
            },
        },
    }


def default_selection_output_path() -> Path:
    """Build the default JSON output path for the final bundle selection."""
    return resolve_project_path(DEFAULT_SELECTION_OUTPUT)


def default_gcn_grandma_output_path(manifest: dict[str, Any]) -> Path:
    """Build the default JSON output path for one GCN-derived GRANDMA list."""
    run_label = manifest.get("run_label")
    if isinstance(run_label, str) and run_label.strip():
        filename = f"gcn_grandma_{run_label.strip()}.json"
    else:
        filename = Path(DEFAULT_GCN_GRANDMA_OUTPUT).name

    return resolve_project_path(Path(DEFAULT_GCN_GRANDMA_OUTPUT).parent / filename)


def default_gcn_grandma_input_path() -> Path:
    """Return the default path to the current GCN-derived GRANDMA base list."""
    return resolve_project_path(DEFAULT_GCN_GRANDMA_INPUT)


def write_payload(output_path: Path, payload: dict[str, Any]) -> None:
    """Persist one built selection payload to disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_json(output_path, payload)


def run_gcn_grandma_build(
    inventory_dir: str | Path,
    output: str | Path | None = None,
) -> Path:
    """Build the enriched GCN-derived GRANDMA base list from one inventory run."""
    resolved_inventory_dir = resolve_project_path(inventory_dir)
    manifest = load_inventory_manifest(resolved_inventory_dir)
    sources = load_inventory_sources(resolved_inventory_dir)
    output_path = (
        resolve_project_path(output)
        if output is not None
        else default_gcn_grandma_output_path(manifest)
    )
    payload = build_gcn_grandma_contract(
        inventory_dir=resolved_inventory_dir,
        output_path=output_path,
        manifest=manifest,
        sources=sources,
    )
    write_payload(output_path, payload)
    print(f"Wrote GCN-derived GRANDMA list: {output_path}")
    print("Input counts:", payload["summary"]["input_counts"])
    return output_path


def run_selected_sources_build(
    gcn_grandma_path: str | Path | None = None,
    output: str | Path | None = None,
) -> Path:
    """Build the final selected-sources file from the GCN-derived GRANDMA base list."""
    resolved_gcn_grandma_path = (
        resolve_project_path(gcn_grandma_path)
        if gcn_grandma_path is not None
        else default_gcn_grandma_input_path()
    )
    output_path = (
        resolve_project_path(output)
        if output is not None
        else default_selection_output_path()
    )
    payload = build_gcn_bundle_selection_contract(
        gcn_grandma_path=resolved_gcn_grandma_path,
        output_path=output_path,
        payload=load_json_object(resolved_gcn_grandma_path),
    )
    write_payload(output_path, payload)
    print(f"Wrote final bundle selection: {output_path}")
    print("Input counts:", payload["summary"]["input_counts"])
    print("Priority counts:", payload["summary"]["priority_counts"])
    return output_path
