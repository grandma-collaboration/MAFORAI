"""Operational scaffolding for selecting sources from one saved inventory."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core import resolve_project_path

DEFAULT_SELECTION_OUTPUT = "data/samples/selected_sources_for_bundles.json"
GRANDMA_GROUP_ID = 3
KNC_GROUP_ID = 38
BASE_CRITERIA = [
    "group_ids=3",
    "hasFollowupRequest=true",
    "numberDetections>=2",
]
FAMILY_RULES = {
    "grb_like": "id starts with GCN or GRB",
    "non_grb": "not GCN, not GRB, not EP",
}
PRIORITY_RULES = {
    "high": "redshift < 1 or redshift > 4",
    "medium": "has redshift or (comment_exists and num_det_global >= 5)",
    "low": "everything else in the base inventory",
}
PRIORITY_RANK = {
    "high": 0,
    "medium": 1,
    "low": 2,
}


def save_json(path: Path, data: Any) -> None:
    """Save JSON data to disk."""
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def load_inventory_manifest(inventory_dir: Path) -> dict[str, Any]:
    """Load the manifest for one saved source-inventory run."""
    manifest_path = inventory_dir / "manifest.json"

    if not manifest_path.exists():
        raise FileNotFoundError(f"Inventory manifest not found: {manifest_path}")

    with manifest_path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)

    if not isinstance(manifest, dict):
        raise ValueError(f"Inventory manifest must be a JSON object: {manifest_path}")

    return manifest


def load_inventory_sources(inventory_dir: Path) -> list[dict[str, Any]]:
    """Load every source row saved under one inventory directory."""
    sources: list[dict[str, Any]] = []

    for page_path in sorted(inventory_dir.glob("sources_page_*.json")):
        with page_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        page_sources = payload.get("data", {}).get("sources", [])
        if not isinstance(page_sources, list):
            continue

        for source in page_sources:
            if isinstance(source, dict):
                sources.append(source)

    if not sources:
        raise ValueError(f"No sources found in inventory directory: {inventory_dir}")

    return sources


def classify_source_family(source_id: str) -> str:
    """Classify a source ID into the family buckets used by bundle selection."""
    if source_id.startswith("GCN") or source_id.startswith("GRB"):
        return "grb_like"
    if source_id.startswith("EP"):
        return "ep"
    return "non_grb"


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


def build_selection_reasons(source: dict[str, Any], redshift: float | None, num_det_global: int) -> list[str]:
    """Build the explicit list of criteria that explain one source selection."""
    reasons = [
        "in_grandma_group",
        "has_followup",
        "at_least_2_detections",
    ]

    if redshift is not None:
        reasons.append("has_redshift")
        if redshift < 1 or redshift > 4:
            reasons.append("redshift_extreme")

    if source.get("comment_exists"):
        reasons.append("has_comments")

    if num_det_global >= 5:
        reasons.append("num_det_global_gte_5")

    return reasons


def assign_priority(redshift: float | None, comment_exists: bool, num_det_global: int) -> str:
    """Assign one simple priority bucket from the agreed rules."""
    if redshift is not None and (redshift < 1 or redshift > 4):
        return "high"
    if redshift is not None or (comment_exists and num_det_global >= 5):
        return "medium"
    return "low"


def build_selected_event(source: dict[str, Any]) -> dict[str, Any]:
    """Build the compact selected-event record written to the final JSON."""
    source_id = str(source.get("id", ""))
    source_family = classify_source_family(source_id)
    redshift = source.get("redshift")
    if not isinstance(redshift, (int, float)):
        redshift = None

    num_det_global = extract_num_det_global(source)
    comment_exists = bool(source.get("comment_exists"))
    priority = assign_priority(redshift, comment_exists, num_det_global)

    return {
        "id": source_id,
        "source_family": source_family,
        "priority": priority,
        "selection_reasons": build_selection_reasons(source, redshift, num_det_global),
        "selection_context": {
            "redshift": redshift,
            "num_det_global": num_det_global,
            "comment_exists": comment_exists,
            "groups": extract_relevant_groups(source),
        },
        "source_summary": source.get("summary"),
    }


def candidate_sort_key(candidate: dict[str, Any]) -> tuple[int, int, int, str]:
    """Sort candidates deterministically within each family."""
    context = candidate.get("selection_context", {})
    comment_exists = bool(context.get("comment_exists"))
    num_det_global = context.get("num_det_global")
    if not isinstance(num_det_global, int):
        num_det_global = 0

    return (
        PRIORITY_RANK[candidate["priority"]],
        0 if comment_exists else 1,
        -num_det_global,
        candidate["id"],
    )


def split_candidates_by_family(sources: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build selected-event candidates and split them into the kept families."""
    grb_like: list[dict[str, Any]] = []
    non_grb: list[dict[str, Any]] = []

    for source in sources:
        candidate = build_selected_event(source)

        if candidate["source_family"] == "grb_like":
            grb_like.append(candidate)
        elif candidate["source_family"] == "non_grb":
            non_grb.append(candidate)

    grb_like.sort(key=candidate_sort_key)
    non_grb.sort(key=candidate_sort_key)

    return grb_like, non_grb


def summarize_priorities(candidates: list[dict[str, Any]]) -> dict[str, int]:
    """Count candidates by priority bucket."""
    counts = Counter(candidate["priority"] for candidate in candidates)
    return {
        "high": counts.get("high", 0),
        "medium": counts.get("medium", 0),
        "low": counts.get("low", 0),
    }


def default_selection_output_path(manifest: dict[str, Any]) -> Path:
    """Build the default JSON output path for one selection run."""
    run_label = manifest.get("run_label")
    if isinstance(run_label, str) and run_label.strip():
        filename = f"selected_sources_for_bundles_{run_label.strip()}.json"
    else:
        filename = Path(DEFAULT_SELECTION_OUTPUT).name

    return resolve_project_path(Path(DEFAULT_SELECTION_OUTPUT).parent / filename)


def build_selection_contract(
    inventory_dir: Path,
    output_path: Path,
    manifest: dict[str, Any],
    sources: list[dict[str, Any]],
    target_grb_like: int,
    target_non_grb: int,
) -> dict[str, Any]:
    """Build the initial JSON contract for the later selection step."""
    family_counts = Counter(
        classify_source_family(str(source.get("id", ""))) for source in sources
    )
    grb_like_candidates, non_grb_candidates = split_candidates_by_family(sources)
    selected_grb_like = grb_like_candidates[:target_grb_like]
    selected_non_grb = non_grb_candidates[:target_non_grb]

    return {
        "selection_run": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "inventory_dir": str(inventory_dir),
            "inventory_run_label": manifest.get("run_label"),
            "inventory_profile_name": manifest.get("profile_name"),
            "output_file": str(output_path),
            "target_counts": {
                "grb_like": target_grb_like,
                "non_grb": target_non_grb,
            },
        },
        "criteria": {
            "base": BASE_CRITERIA,
            "family_rules": FAMILY_RULES,
            "priority_rules": PRIORITY_RULES,
        },
        "selected": {
            "grb_like": selected_grb_like,
            "non_grb": selected_non_grb,
        },
        "summary": {
            "input_counts": {
                "total_sources": len(sources),
                "grb_like_candidates": family_counts.get("grb_like", 0),
                "non_grb_candidates": family_counts.get("non_grb", 0),
                "excluded_ep_candidates": family_counts.get("ep", 0),
            },
            "candidate_priority_counts": {
                "grb_like": summarize_priorities(grb_like_candidates),
                "non_grb": summarize_priorities(non_grb_candidates),
            },
            "selected_counts": {
                "grb_like": len(selected_grb_like),
                "non_grb": len(selected_non_grb),
            },
        },
    }


def run_source_selection(args: argparse.Namespace) -> None:
    """Create the initial source-selection contract for one saved inventory."""
    inventory_dir = resolve_project_path(args.inventory_dir)
    manifest = load_inventory_manifest(inventory_dir)
    sources = load_inventory_sources(inventory_dir)

    if args.output:
        output_path = resolve_project_path(args.output)
    else:
        output_path = default_selection_output_path(manifest)

    payload = build_selection_contract(
        inventory_dir=inventory_dir,
        output_path=output_path,
        manifest=manifest,
        sources=sources,
        target_grb_like=args.target_grb_like,
        target_non_grb=args.target_non_grb,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_json(output_path, payload)

    print(f"Wrote selection contract: {output_path}")
    print(
        "Input counts:",
        payload["summary"]["input_counts"],
    )
