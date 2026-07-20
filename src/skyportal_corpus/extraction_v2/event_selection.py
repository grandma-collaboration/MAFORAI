from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from skyportal_corpus.canonical.document import iter_real_circulars
from skyportal_corpus.extraction_v2.event_grouping import (
    canonical_aliases,
    circular_matches_event,
    group_event_circulars,
)
from skyportal_corpus.extraction_v2.event_registry import (
    DEFAULT_EVENT_REGISTRY_PATH,
    FIELD_SEPARATOR,
    FLAG_SEPARATOR,
)
from skyportal_corpus.extraction_v2.identity_index import (
    DEFAULT_IDENTITY_INDEX_META_PATH,
    DEFAULT_IDENTITY_INDEX_PATH,
    load_identity_index_meta,
    read_identity_index,
    validate_identity_index_meta,
)


MJD_UNIX_EPOCH = 40587.0


def select_event_candidates(
    source_id: str,
    *,
    registry_path: str | Path = DEFAULT_EVENT_REGISTRY_PATH,
    index_path: str | Path = DEFAULT_IDENTITY_INDEX_PATH,
) -> dict[str, Any]:
    """Select one event's Circulars using the reusable identity index and live verification."""
    registry_row = load_registry_event(registry_path, source_id)
    canonical_source_id = registry_row["source_id"]
    terms = _split_field(registry_row.get("terms"))
    if not terms:
        raise ValueError(f"Registry event {canonical_source_id} has no terms")

    index_file = Path(index_path)
    metadata_path = index_file.with_name(DEFAULT_IDENTITY_INDEX_META_PATH.name)
    metadata = load_identity_index_meta(metadata_path)
    validate_identity_index_meta(metadata)
    index_records = read_identity_index(index_file)
    alias_entries = list(canonical_aliases(terms).values())

    selected: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    decisions_by_id: dict[int, dict[str, Any]] = {}
    trigger_time = _optional_float(registry_row.get("trigger_time"))
    for record in index_records:
        belongs, reason, evidence = circular_matches_event(
            subject_identities=list(record.get("subject_identities") or []),
            body_identities=list(record.get("body_identities") or []),
            event_alias_info={
                "aliases": alias_entries,
                "body_text": str(record.get("body_text") or ""),
            },
        )
        item = {
            "circular_id": int(record["circular_id"]),
            "subject": str(record.get("subject") or ""),
            "created_on": _optional_text(record.get("created_on")),
            "reason": reason,
            "evidence": evidence,
            "delta_days": delta_days(record.get("created_on"), trigger_time),
        }
        if belongs:
            selected.append(item)
            decisions_by_id[item["circular_id"]] = item
        elif reason == "confirmed_other_event":
            conflicts.append(item)

    selected_ids = {item["circular_id"] for item in selected}
    min_year = int(metadata["min_year"])
    selected_records = [
        circular
        for circular in iter_real_circulars(min_year=min_year)
        if int(circular["circular_id"]) in selected_ids
    ]
    resolved_ids = {int(circular["circular_id"]) for circular in selected_records}
    unresolved = sorted(selected_ids - resolved_ids)
    if unresolved:
        raise ValueError(f"Indexed Circulars missing from live corpus: {unresolved}")

    title = str(registry_row.get("title") or canonical_source_id)
    grouped = group_event_circulars(
        source_id=canonical_source_id,
        aliases=terms,
        circulars=selected_records,
        title=title,
    )
    live_included = {int(item["circular_id"]): item for item in grouped["included"]}
    if set(live_included) != selected_ids:
        raise AssertionError(
            "Identity index and live grouping disagree: "
            f"index_only={sorted(selected_ids - set(live_included))}, "
            f"live_only={sorted(set(live_included) - selected_ids)}"
        )
    for circular_id, live_item in live_included.items():
        indexed_item = decisions_by_id[circular_id]
        if (
            live_item["reason"] != indexed_item["reason"]
            or live_item["evidence"] != indexed_item["evidence"]
        ):
            raise AssertionError(
                f"Identity index evidence drift for Circular {circular_id}: "
                f"indexed={indexed_item}, live={live_item}"
            )

    selected.sort(key=_selection_sort_key)
    conflicts.sort(key=_selection_sort_key)
    body_only = [item for item in selected if item["reason"] == "body_mention"]
    body_only_identity = [
        item for item in body_only if "identity" in item["evidence"]
    ]
    body_only_name = [
        item
        for item in body_only
        if item["evidence"].get("match_type") == "body_name_match"
    ]
    far_in_time = [
        item
        for item in selected
        if item["delta_days"] is not None and abs(float(item["delta_days"])) > 365.0
    ]
    flags = _split_flags(registry_row.get("flags"))
    merged_source_ids = _split_field(registry_row.get("merged_source_ids"))

    return {
        "requested_source_id": source_id,
        "source_id": canonical_source_id,
        "gcn_source_type": str(registry_row.get("gcn_source_type") or ""),
        "title": title,
        "terms": terms,
        "merged_source_ids": merged_source_ids,
        "tns_name": _split_field(registry_row.get("tns_name")),
        "trigger_time": trigger_time,
        "flags": flags,
        "min_year": min_year,
        "n_scanned": len(index_records),
        "n_included": len(selected),
        "n_excluded": len(index_records) - len(selected),
        "included": selected,
        "included_records": sorted(selected_records, key=_circular_sort_key),
        "excluded_conflicts": conflicts,
        "body_only": body_only,
        "body_only_identity": body_only_identity,
        "body_only_name": body_only_name,
        "far_in_time": far_in_time,
        "authoritative_group": grouped,
    }


def load_registry_event(path: str | Path, source_id: str) -> dict[str, str]:
    """Load a canonical registry row by canonical or absorbed source ID."""
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        rows = [dict(row) for row in csv.DictReader(handle)]
    for row in rows:
        if row.get("source_id") == source_id:
            return row
    for row in rows:
        if source_id in _split_field(row.get("merged_source_ids")):
            return row
    raise KeyError(f"Source ID not found in registry: {source_id}")


def delta_days(created_on: Any, trigger_time: float | None) -> float | None:
    """Return informational Circular-to-trigger separation in days."""
    if trigger_time is None:
        return None
    created_text = str(created_on or "").strip()
    if not created_text:
        return None
    try:
        created = datetime.fromisoformat(created_text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    created_mjd = created.timestamp() / 86400.0 + MJD_UNIX_EPOCH
    return created_mjd - trigger_time


def _split_field(value: Any) -> list[str]:
    return [item.strip() for item in str(value or "").split("|") if item.strip()]


def _split_flags(value: Any) -> list[str]:
    return [item.strip() for item in str(value or "").split(FLAG_SEPARATOR) if item.strip()]


def _optional_float(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _selection_sort_key(item: dict[str, Any]) -> tuple[str, int]:
    return str(item.get("created_on") or ""), int(item["circular_id"])


def _circular_sort_key(item: dict[str, Any]) -> tuple[str, int]:
    return str(item.get("created_on") or ""), int(item["circular_id"])


__all__ = [
    "delta_days",
    "load_registry_event",
    "select_event_candidates",
]
