from __future__ import annotations

import csv
import json
import math
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


DEFAULT_EVENT_SOURCES_PATH = Path("data/interim/skyportal/gcn_grandma.json")
DEFAULT_EVENT_TERMS_PATH = Path("data/interim/gcn/event_matching/event_search_terms.csv")
DEFAULT_EVENT_REGISTRY_PATH = Path("data/interim/gcn/event_matching/event_registry.csv")
REGISTRY_COLUMNS = (
    "source_id",
    "gcn_source_type",
    "title",
    "terms",
    "dropped_terms",
    "merged_source_ids",
    "tns_name",
    "trigger_time",
    "n_terms",
    "flags",
)
FIELD_SEPARATOR = " | "
FLAG_SEPARATOR = ";"
TRIGGER_LIKE_SOURCE_PATTERN = re.compile(
    r"^(?:GRB|GCN|EP|GW)[-_]\d{6}_\d{6}$",
    re.IGNORECASE,
)
SUFFIXLESS_GRB_PATTERN = re.compile(r"^GRB\d{6}$", re.IGNORECASE)
SUFFIXED_GRB_PATTERN = re.compile(r"^GRB\d{6}[A-Z]$", re.IGNORECASE)
SUFFIXLESS_EVENT_FAMILY_PATTERN = re.compile(
    r"^(GRB|EP)(\d{6})$",
    re.IGNORECASE,
)
SUFFIXED_EVENT_FAMILY_PATTERN = re.compile(
    r"^(GRB|EP)(\d{6})[A-Z]$",
    re.IGNORECASE,
)


def load_event_sources(path: str | Path) -> list[dict[str, Any]]:
    """Load compact SkyPortal event records."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    sources = payload.get("sources") if isinstance(payload, dict) else None
    if not isinstance(sources, list):
        raise ValueError(f"Missing sources list in {path}")
    return [dict(item) for item in sources if isinstance(item, Mapping)]


def load_event_term_rows(path: str | Path) -> list[dict[str, str]]:
    """Load flattened event search-term rows."""
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def find_duplicate_groups(
    sources: Iterable[Mapping[str, Any]],
    term_rows: Iterable[Mapping[str, Any]],
) -> list[list[str]]:
    """Find transitive duplicate components using terms, TNS names, and sky-time proximity."""
    source_by_id = {
        str(source.get("id") or source.get("source_id") or ""): source
        for source in sources
        if str(source.get("id") or source.get("source_id") or "")
    }
    union = _UnionFind(source_by_id)

    sources_by_term: dict[str, set[str]] = defaultdict(set)
    for row in term_rows:
        source_id = str(row.get("source_id") or "")
        normalized = str(row.get("search_term_normalized") or "").strip().upper()
        if source_id in source_by_id and len(normalized) >= 6:
            sources_by_term[normalized].add(source_id)
    for members in sources_by_term.values():
        _union_members(union, members)

    sources_by_tns: dict[str, set[str]] = defaultdict(set)
    for source_id, source in source_by_id.items():
        tns_name = str(source.get("tns_name") or "").strip().upper()
        if tns_name:
            sources_by_tns[tns_name].add(source_id)
    for members in sources_by_tns.values():
        _union_members(union, members)

    source_items = sorted(source_by_id.items())
    for index, (left_id, left) in enumerate(source_items):
        left_trigger = _optional_float(left.get("trigger_time"))
        left_position = _position(left)
        if left_trigger is None or left_position is None:
            continue
        for right_id, right in source_items[index + 1 :]:
            right_trigger = _optional_float(right.get("trigger_time"))
            right_position = _position(right)
            if right_trigger != left_trigger or right_position is None:
                continue
            if angular_separation_arcmin(left_position, right_position) < 1.0:
                union.union(left_id, right_id)

    components: dict[str, list[str]] = defaultdict(list)
    for source_id in sorted(source_by_id):
        components[union.find(source_id)].append(source_id)
    groups = [sorted(members) for members in components.values() if len(members) > 1]
    return sorted(groups, key=lambda members: (-len(members), members))


def build_event_registry_rows(
    sources: Iterable[Mapping[str, Any]],
    term_rows: Iterable[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Consolidate duplicate SkyPortal records into deterministic registry rows."""
    source_list = [dict(source) for source in sources]
    terms_list = [dict(row) for row in term_rows]
    source_by_id = {
        str(source.get("id") or source.get("source_id") or ""): source
        for source in source_list
    }
    rows_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in terms_list:
        rows_by_source[str(row.get("source_id") or "")].append(row)

    duplicate_groups = find_duplicate_groups(source_list, terms_list)
    group_by_member: dict[str, list[str]] = {}
    for group in duplicate_groups:
        for source_id in group:
            group_by_member[source_id] = group

    registry_rows: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    consumed: set[str] = set()
    for source_id in sorted(source_by_id):
        if source_id in consumed:
            continue
        members = group_by_member.get(source_id, [source_id])
        consumed.update(members)
        canonical_id = choose_canonical_source_id(members, rows_by_source)
        member_sources = [source_by_id[member] for member in members]
        merged_terms = _merge_terms(members, rows_by_source, canonical_id)
        preferred_terms, dropped_terms = _prefer_suffixed_event_terms(merged_terms)
        normalized_terms = [_normalized_term(item) for item in preferred_terms]
        suffixless = [
            item["search_term"]
            for item in preferred_terms
            if SUFFIXLESS_GRB_PATTERN.fullmatch(_normalized_term(item))
        ]
        has_suffixed_grb = any(
            SUFFIXED_GRB_PATTERN.fullmatch(normalized)
            for normalized in normalized_terms
        )
        flags: list[str] = []
        absorbed = sorted(member for member in members if member != canonical_id)
        if absorbed:
            flags.append("merged_from")
        if suffixless and not has_suffixed_grb:
            flags.append("suffixless_only_terms")

        tns_names = _unique_nonempty(source.get("tns_name") for source in member_sources)
        trigger_times = _unique_floats(source.get("trigger_time") for source in member_sources)
        if len(tns_names) > 1:
            flags.append("multiple_tns_names")
        if len(trigger_times) > 1:
            flags.append("trigger_time_conflict")

        canonical_source = source_by_id[canonical_id]
        trigger_time = _optional_float(canonical_source.get("trigger_time"))
        if trigger_time is None and trigger_times:
            trigger_time = trigger_times[0]
        display_terms = [str(item["search_term"]) for item in preferred_terms]
        dropped_display_terms = [str(item["search_term"]) for item in dropped_terms]
        registry_rows.append(
            {
                "source_id": canonical_id,
                "gcn_source_type": str(canonical_source.get("gcn_source_type") or ""),
                "title": _build_title(members, rows_by_source, canonical_id),
                "terms": FIELD_SEPARATOR.join(display_terms),
                "dropped_terms": FIELD_SEPARATOR.join(dropped_display_terms),
                "merged_source_ids": FIELD_SEPARATOR.join(absorbed),
                "tns_name": FIELD_SEPARATOR.join(tns_names),
                "trigger_time": "" if trigger_time is None else _format_float(trigger_time),
                "n_terms": len(display_terms),
                "flags": FLAG_SEPARATOR.join(flags),
            }
        )
        if len(members) > 1:
            diagnostics.append(
                {
                    "members": sorted(members),
                    "canonical_source_id": canonical_id,
                }
            )

    registry_rows.sort(key=lambda row: str(row["source_id"]))
    diagnostics.sort(key=lambda row: (-len(row["members"]), row["members"]))
    return registry_rows, diagnostics


def choose_canonical_source_id(
    members: Iterable[str],
    rows_by_source: Mapping[str, list[Mapping[str, Any]]],
) -> str:
    """Choose the registry ID using trigger-like priority, term richness, then name."""
    member_list = sorted(set(members))
    trigger_like = [
        member for member in member_list if TRIGGER_LIKE_SOURCE_PATTERN.fullmatch(member)
    ]
    candidates = trigger_like or member_list
    return min(
        candidates,
        key=lambda member: (-_unique_term_count(rows_by_source.get(member, [])), member),
    )


def write_event_registry(
    rows: Iterable[Mapping[str, Any]],
    path: str | Path = DEFAULT_EVENT_REGISTRY_PATH,
) -> Path:
    """Write event registry rows with a stable column order."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REGISTRY_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in REGISTRY_COLUMNS})
    return output_path


def angular_separation_arcmin(
    left: tuple[float, float],
    right: tuple[float, float],
) -> float:
    """Return great-circle separation in arcminutes for two RA/Dec pairs."""
    left_ra, left_dec = map(math.radians, left)
    right_ra, right_dec = map(math.radians, right)
    cosine = (
        math.sin(left_dec) * math.sin(right_dec)
        + math.cos(left_dec) * math.cos(right_dec) * math.cos(left_ra - right_ra)
    )
    angle = math.acos(max(-1.0, min(1.0, cosine)))
    return math.degrees(angle) * 60.0


def suffixless_only_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return registry rows whose GRB family terms have no lettered counterpart."""
    return [
        dict(row)
        for row in rows
        if "suffixless_only_terms" in str(row.get("flags") or "").split(FLAG_SEPARATOR)
    ]


class _UnionFind:
    def __init__(self, members: Iterable[str]) -> None:
        self._parent = {member: member for member in members}

    def find(self, member: str) -> str:
        parent = self._parent[member]
        if parent != member:
            self._parent[member] = self.find(parent)
        return self._parent[member]

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        first, second = sorted((left_root, right_root))
        self._parent[second] = first


def _union_members(union: _UnionFind, members: Iterable[str]) -> None:
    ordered = sorted(set(members))
    for member in ordered[1:]:
        union.union(ordered[0], member)


def _position(source: Mapping[str, Any]) -> tuple[float, float] | None:
    ra = _optional_float(source.get("ra"))
    dec = _optional_float(source.get("dec"))
    if ra is None or dec is None:
        return None
    return ra, dec


def _optional_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _format_float(value: float) -> str:
    return format(value, ".15g")


def _normalized_term(row: Mapping[str, Any]) -> str:
    return str(row.get("search_term_normalized") or "").strip().upper()


def _unique_term_count(rows: Iterable[Mapping[str, Any]]) -> int:
    return len({_normalized_term(row) for row in rows if _normalized_term(row)})


def _merge_terms(
    members: Iterable[str],
    rows_by_source: Mapping[str, list[Mapping[str, Any]]],
    canonical_id: str,
) -> list[dict[str, Any]]:
    member_order = [canonical_id, *sorted(member for member in members if member != canonical_id)]
    selected: dict[str, dict[str, Any]] = {}
    for member in member_order:
        rows = sorted(
            rows_by_source.get(member, []),
            key=lambda row: (
                int(row.get("variant_rank") or 0),
                _origin_rank(str(row.get("origin_field") or "")),
                str(row.get("search_term") or ""),
            ),
        )
        for row in rows:
            normalized = _normalized_term(row)
            if normalized and normalized not in selected:
                selected[normalized] = dict(row)
    return list(selected.values())


def _prefer_suffixed_event_terms(
    terms: Iterable[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Drop degraded suffixless GRB/EP names when a same-date suffix exists."""
    term_list = [dict(term) for term in terms]
    suffixed_families = {
        (match.group(1).upper(), match.group(2))
        for term in term_list
        if (match := SUFFIXED_EVENT_FAMILY_PATTERN.fullmatch(_normalized_term(term)))
        is not None
    }
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for term in term_list:
        match = SUFFIXLESS_EVENT_FAMILY_PATTERN.fullmatch(_normalized_term(term))
        family = None if match is None else (match.group(1).upper(), match.group(2))
        if family is not None and family in suffixed_families:
            dropped.append(term)
        else:
            kept.append(term)
    return kept, dropped


def _origin_rank(origin_field: str) -> int:
    return {"alias": 0, "tns_name": 1, "id": 2}.get(origin_field, 3)


def _build_title(
    members: Iterable[str],
    rows_by_source: Mapping[str, list[Mapping[str, Any]]],
    canonical_id: str,
) -> str:
    originals: list[str] = []
    member_order = [canonical_id, *sorted(member for member in members if member != canonical_id)]
    for origin_field in ("alias", "tns_name", "id"):
        for member in member_order:
            for row in rows_by_source.get(member, []):
                if (
                    str(row.get("origin_field") or "") == origin_field
                    and str(row.get("variant_type") or "") == "original"
                ):
                    value = str(row.get("search_term") or "").strip()
                    normalized = _normalized_term(row)
                    if value and all(_normalize_title_term(item) != normalized for item in originals):
                        originals.append(value)
    return " / ".join(originals) if originals else canonical_id


def _normalize_title_term(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", value).upper()


def _unique_nonempty(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return sorted(result)


def _unique_floats(values: Iterable[Any]) -> list[float]:
    result: list[float] = []
    for value in values:
        number = _optional_float(value)
        if number is not None and number not in result:
            result.append(number)
    return sorted(result)


__all__ = [
    "DEFAULT_EVENT_REGISTRY_PATH",
    "DEFAULT_EVENT_SOURCES_PATH",
    "DEFAULT_EVENT_TERMS_PATH",
    "FIELD_SEPARATOR",
    "REGISTRY_COLUMNS",
    "angular_separation_arcmin",
    "build_event_registry_rows",
    "choose_canonical_source_id",
    "find_duplicate_groups",
    "load_event_sources",
    "load_event_term_rows",
    "suffixless_only_rows",
    "write_event_registry",
]
