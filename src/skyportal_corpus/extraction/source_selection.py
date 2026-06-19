"""Helpers for building the compact GCN-derived base from saved inventories."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core import resolve_project_path

DEFAULT_GCN_GRANDMA_OUTPUT = "data/interim/skyportal/gcn_grandma.json"
GRANDMA_GROUP_ID = 3
KNC_GROUP_ID = 38
GCN_DERIVED_RULES = {
    "grb": "id starts with GRB",
    "gw": "id starts with GW",
    "ep": "id starts with EP",
    "gcn": "id starts with GCN",
}
GCN_DERIVED_MATCH_FIELDS = [
    "source id starts with GCN, GRB, GW, or EP",
    "or one alias starts with GCN, GRB, GW, or EP",
]


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
    source_id = source_id.strip()
    if source_id.startswith("GRB"):
        return "grb"
    if source_id.startswith("GW"):
        return "gw"
    if source_id.startswith("EP"):
        return "ep"
    if source_id.startswith("GCN"):
        return "gcn"
    return "other"


def extract_aliases(source: dict[str, Any]) -> list[str]:
    """Extract the compact alias list for one source row."""
    raw_aliases = source.get("alias")
    if isinstance(raw_aliases, str):
        raw_items = [raw_aliases]
    elif isinstance(raw_aliases, list):
        raw_items = raw_aliases
    else:
        return []

    aliases: list[str] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, str):
            continue

        alias = raw_item.strip()
        if alias and alias not in aliases:
            aliases.append(alias)

    return aliases


def classify_gcn_derived_source(source: dict[str, Any]) -> str:
    """Classify one source row using both the main ID and its aliases."""
    source_id = str(source.get("id", "")).strip()
    source_type = classify_gcn_derived_type(source_id)
    if source_type != "other":
        return source_type

    for alias in extract_aliases(source):
        alias_type = classify_gcn_derived_type(alias)
        if alias_type != "other":
            return alias_type

    return "other"


def is_gcn_derived_source(source: dict[str, Any]) -> bool:
    """Return whether the source row follows the GCN-derived naming scheme."""
    return classify_gcn_derived_source(source) != "other"


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


def extract_trigger_time(source: dict[str, Any]) -> float | None:
    """Extract the inventory-level trigger time (`t0`) when present."""
    trigger_time = source.get("t0")
    if not isinstance(trigger_time, (int, float)):
        return None
    return float(trigger_time)


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


def extract_tags(source: dict[str, Any]) -> list[str]:
    """Extract the compact list of raw SkyPortal tag names from one source row."""
    raw_tags = source.get("tags")
    if not isinstance(raw_tags, list):
        return []

    tags: list[str] = []
    for raw_tag in raw_tags:
        if not isinstance(raw_tag, dict):
            continue

        tag_name = raw_tag.get("name")
        if not isinstance(tag_name, str):
            continue

        tag_name = tag_name.strip()
        if tag_name and tag_name not in tags:
            tags.append(tag_name)

    return tags


def extract_has_host(source: dict[str, Any]) -> bool:
    """Return whether the source row exposes a host association."""
    host_id = source.get("host_id")
    return isinstance(host_id, int)


def extract_spectrum_exists(source: dict[str, Any]) -> bool:
    """Return whether the source row exposes the compact spectrum flag."""
    return bool(source.get("spectrum_exists"))


def build_gcn_grandma_event(source: dict[str, Any]) -> dict[str, Any] | None:
    """Build one compact GCN-derived source record."""
    source_id = str(source.get("id", "")).strip()
    source_type = classify_gcn_derived_source(source)
    if source_type == "other":
        return None

    redshift = source.get("redshift")
    if not isinstance(redshift, (int, float)):
        redshift = None

    return {
        "id": source_id,
        "gcn_source_type": source_type,
        "aliases": extract_aliases(source),
        "redshift": redshift,
        "trigger_time": extract_trigger_time(source),
        "comment_exists": bool(source.get("comment_exists")),
        "spectrum_exists": extract_spectrum_exists(source),
        "num_det_global": extract_num_det_global(source),
        "has_host": extract_has_host(source),
        "groups": extract_relevant_groups(source),
        "classification_labels": extract_classification_labels(source),
        "tags": extract_tags(source),
        "source_summary": source.get("summary"),
    }


def merge_unique_strings(existing: Any, incoming: Any) -> list[str]:
    """Merge two compact string lists while preserving order."""
    merged: list[str] = []

    if not isinstance(existing, list):
        existing = []
    if not isinstance(incoming, list):
        incoming = []

    for item in existing + incoming:
        if item not in merged:
            merged.append(item)

    return merged


def merge_gcn_grandma_event(
    existing: dict[str, Any],
    incoming: dict[str, Any],
) -> dict[str, Any]:
    """Merge two compact GCN-derived event records for the same source ID."""
    merged = dict(existing)
    merged["aliases"] = merge_unique_strings(
        existing.get("aliases", []),
        incoming.get("aliases", []),
    )
    merged["comment_exists"] = bool(existing.get("comment_exists")) or bool(
        incoming.get("comment_exists")
    )
    merged["spectrum_exists"] = bool(existing.get("spectrum_exists")) or bool(
        incoming.get("spectrum_exists")
    )

    existing_num_det_global = existing.get("num_det_global")
    if not isinstance(existing_num_det_global, int):
        existing_num_det_global = 0
    incoming_num_det_global = incoming.get("num_det_global")
    if not isinstance(incoming_num_det_global, int):
        incoming_num_det_global = 0
    merged["num_det_global"] = max(existing_num_det_global, incoming_num_det_global)

    merged["has_host"] = bool(existing.get("has_host")) or bool(incoming.get("has_host"))
    merged["groups"] = merge_unique_strings(
        existing.get("groups", []),
        incoming.get("groups", []),
    )
    merged["classification_labels"] = merge_unique_strings(
        existing.get("classification_labels", []),
        incoming.get("classification_labels", []),
    )
    merged["tags"] = merge_unique_strings(
        existing.get("tags", []),
        incoming.get("tags", []),
    )

    if not isinstance(merged.get("redshift"), (int, float)) and isinstance(
        incoming.get("redshift"), (int, float)
    ):
        merged["redshift"] = incoming["redshift"]

    if not isinstance(merged.get("trigger_time"), (int, float)) and isinstance(
        incoming.get("trigger_time"), (int, float)
    ):
        merged["trigger_time"] = incoming["trigger_time"]

    existing_summary = existing.get("source_summary")
    incoming_summary = incoming.get("source_summary")
    if (
        not isinstance(existing_summary, str)
        or not existing_summary.strip()
    ) and isinstance(incoming_summary, str):
        merged["source_summary"] = incoming_summary

    return merged


def merge_gcn_grandma_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge duplicate compact records coming from multiple inventory runs."""
    merged_by_id: dict[str, dict[str, Any]] = {}

    for event in events:
        source_id = str(event.get("id", ""))
        if source_id not in merged_by_id:
            merged_by_id[source_id] = event
            continue

        merged_by_id[source_id] = merge_gcn_grandma_event(merged_by_id[source_id], event)

    return list(merged_by_id.values())


def build_inventory_run(
    inventory_dir: Path,
    manifest: dict[str, Any],
    sources: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build one in-memory inventory-run descriptor for the selection workflow."""
    return {
        "inventory_dir": inventory_dir,
        "manifest": manifest,
        "sources": sources,
    }


def build_gcn_grandma_contract(
    inventory_runs: list[dict[str, Any]],
    output_path: Path,
) -> dict[str, Any]:
    """Build the base list of all GCN-derived sources from several inventories."""
    raw_gcn_sources: list[dict[str, Any]] = []
    raw_source_count = 0
    inventory_dirs: list[str] = []
    inventory_run_labels: list[str] = []
    inventory_profile_names: list[str] = []

    for inventory_run in inventory_runs:
        inventory_dir = inventory_run["inventory_dir"]
        manifest = inventory_run["manifest"]
        sources = inventory_run["sources"]

        inventory_dirs.append(str(inventory_dir))
        run_label = manifest.get("run_label")
        if isinstance(run_label, str) and run_label not in inventory_run_labels:
            inventory_run_labels.append(run_label)

        profile_name = manifest.get("profile_name")
        if isinstance(profile_name, str) and profile_name not in inventory_profile_names:
            inventory_profile_names.append(profile_name)

        raw_source_count += len(sources)

        for source in sources:
            event = build_gcn_grandma_event(source)
            if event is not None:
                raw_gcn_sources.append(event)

    gcn_sources = merge_gcn_grandma_events(raw_gcn_sources)
    gcn_sources.sort(key=lambda item: (item["gcn_source_type"], item["id"]))
    subtype_counts = Counter(item["gcn_source_type"] for item in gcn_sources)
    inventory_run_label = "_".join(inventory_run_labels) if inventory_run_labels else "gcn_union"

    return {
        "gcn_grandma_run": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "inventory_dirs": inventory_dirs,
            "inventory_run_label": inventory_run_label,
            "inventory_run_labels": inventory_run_labels,
            "inventory_profile_names": inventory_profile_names,
            "output_file": str(output_path),
        },
        "criteria": {
            "base": [
                "union of inventory profiles gcn, grb, ep, and grandma_base",
            ],
            "gcn_derived_id_rules": GCN_DERIVED_RULES,
            "gcn_derived_match_fields": GCN_DERIVED_MATCH_FIELDS,
        },
        "sources": gcn_sources,
        "summary": {
            "input_counts": {
                "inventory_runs": len(inventory_runs),
                "total_inventory_rows": raw_source_count,
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


def default_gcn_grandma_output_path() -> Path:
    """Build the default JSON output path for the GCN-derived base list."""
    return resolve_project_path(DEFAULT_GCN_GRANDMA_OUTPUT)


def write_payload(output_path: Path, payload: dict[str, Any]) -> None:
    """Persist one built selection payload to disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_json(output_path, payload)


def run_gcn_grandma_build(
    inventory_dirs: list[str | Path],
    output: str | Path | None = None,
) -> Path:
    """Build the enriched GCN-derived base list from several inventory runs."""
    inventory_runs: list[dict[str, Any]] = []

    for inventory_dir in inventory_dirs:
        resolved_inventory_dir = resolve_project_path(inventory_dir)
        manifest = load_inventory_manifest(resolved_inventory_dir)
        sources = load_inventory_sources(resolved_inventory_dir)
        inventory_runs.append(
            build_inventory_run(
                inventory_dir=resolved_inventory_dir,
                manifest=manifest,
                sources=sources,
            )
        )

    output_path = (
        resolve_project_path(output)
        if output is not None
        else default_gcn_grandma_output_path()
    )
    payload = build_gcn_grandma_contract(
        inventory_runs=inventory_runs,
        output_path=output_path,
    )
    write_payload(output_path, payload)
    print(f"Wrote GCN-derived base list: {output_path}")
    print("Input counts:", payload["summary"]["input_counts"])
    return output_path
