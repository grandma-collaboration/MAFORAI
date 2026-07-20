"""Helpers for matching selected SkyPortal events against GCN Circulars."""

from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path
from typing import Any

import pandas as pd

from ..core import resolve_project_path
from .source_selection import DEFAULT_GCN_GRANDMA_OUTPUT

DEFAULT_GCN_EVENT_INPUT_PATH = DEFAULT_GCN_GRANDMA_OUTPUT
DEFAULT_GCN_EVENT_MATCHING_SELECTED_SOURCES_PATH = DEFAULT_GCN_EVENT_INPUT_PATH
DEFAULT_GCN_EVENT_MATCHING_OUTPUT_DIR = "data/interim/gcn/event_matching"
DEFAULT_GCN_EVENT_MATCHING_GCN_ROOT = "data/interim/gcn/circulars"
DEFAULT_GCN_EVENT_MATCHING_YEAR_FROM = 2023
DEFAULT_GCN_EVENT_MATCHING_YEAR_TO = 2026

EVENT_SEARCH_TERMS_PARQUET = "event_search_terms.parquet"
EVENT_SEARCH_TERMS_CSV = "event_search_terms.csv"
EVENT_GCN_MATCHES_PARQUET = "event_gcn_matches.parquet"
EVENT_GCN_MATCHES_CSV = "event_gcn_matches.csv"
EVENT_GCN_ASSOCIATIONS_PARQUET = "event_gcn_associations.parquet"
EVENT_GCN_ASSOCIATIONS_CSV = "event_gcn_associations.csv"
EVENT_GCN_MATCH_SUMMARY_CSV = "event_gcn_match_summary.csv"
DEFAULT_GCN_EVENT_MATCHING_TERMS_PATH = (
    f"{DEFAULT_GCN_EVENT_MATCHING_OUTPUT_DIR}/{EVENT_SEARCH_TERMS_PARQUET}"
)
DEFAULT_GCN_EVENT_MATCHING_MATCHES_PATH = (
    f"{DEFAULT_GCN_EVENT_MATCHING_OUTPUT_DIR}/{EVENT_GCN_MATCHES_PARQUET}"
)
DEFAULT_GCN_EVENT_MATCHING_ASSOCIATIONS_PATH = (
    f"{DEFAULT_GCN_EVENT_MATCHING_OUTPUT_DIR}/{EVENT_GCN_ASSOCIATIONS_PARQUET}"
)
DEFAULT_GCN_EVENT_MATCHING_SUMMARY_PATH = (
    f"{DEFAULT_GCN_EVENT_MATCHING_OUTPUT_DIR}/{EVENT_GCN_MATCH_SUMMARY_CSV}"
)
DEFAULT_GCN_CIRCULARS_ROOT_DIR = DEFAULT_GCN_EVENT_MATCHING_GCN_ROOT
DEFAULT_GCN_YEAR_FROM = DEFAULT_GCN_EVENT_MATCHING_YEAR_FROM
DEFAULT_GCN_YEAR_TO = DEFAULT_GCN_EVENT_MATCHING_YEAR_TO

EVENT_SEARCH_TERMS_COLUMNS = [
    "source_id",
    "gcn_source_type",
    "origin_field",
    "origin_value",
    "search_term",
    "search_term_normalized",
    "variant_type",
    "variant_rank",
    "is_trigger_like",
    "groups",
]
EVENT_GCN_MATCHES_COLUMNS = [
    "source_id",
    "search_term",
    "search_term_normalized",
    "variant_type",
    "origin_field",
    "origin_value",
    "matched_field",
    "match_type",
    "match_score",
    "confidence_level",
    "circular_id",
    "gcn_event_id",
    "subject",
    "created_at_iso",
    "raw_file_path",
    "year",
    "evidence_text",
]
EVENT_GCN_ASSOCIATIONS_COLUMNS = [
    "source_id",
    "circular_id",
    "gcn_event_id",
    "subject",
    "created_at_iso",
    "year",
    "best_matched_term",
    "best_matched_field",
    "best_match_type",
    "best_match_score",
    "best_confidence_level",
    "evidence_text",
    "raw_file_path",
    "matched_terms",
    "matched_fields",
]
EVENT_GCN_MATCH_SUMMARY_COLUMNS = [
    "source_id",
    "n_search_terms",
    "n_matches",
    "n_matched_circulars",
    "n_high_confidence_matches",
    "n_medium_confidence_matches",
    "n_low_confidence_matches",
    "n_subject_matches",
    "n_event_id_matches",
    "n_body_matches",
    "best_match_score",
    "best_confidence_level",
    "matched_terms",
    "status",
]

MATCH_STATUS_ORDER = {
    "matched": 0,
    "medium_match": 1,
    "weak_match": 2,
    "no_match": 3,
}

FIELD_ORDER = {
    "subject": 0,
    "event_id": 1,
    "body": 2,
}

CANONICAL_EVENT_PATTERN = re.compile(
    r"^(GRB|EP|GW)[\s_-]*([0-9]{6}(?:\.[0-9]+)?[A-Za-z]?(?:-[A-Za-z0-9]+)?)$",
    re.IGNORECASE,
)
TNS_EVENT_PATTERN = re.compile(
    r"^(AT|SN)[\s_-]*(2[0-9]{3}[A-Za-z]{2,4})$",
    re.IGNORECASE,
)
TRIGGER_LIKE_PATTERN = re.compile(
    r"^(GRB|GCN|EP|GW)[-_][0-9]{6}_[0-9]{6}$",
    re.IGNORECASE,
)
def setup_console_logging() -> None:
    """Configure simple console logging for one run."""
    logging.basicConfig(level=logging.INFO, format="%(message)s", force=True)


def load_json_object(path: Path) -> dict[str, Any]:
    """Load one JSON object from disk."""
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")

    return payload


def save_json(path: Path, data: Any) -> None:
    """Save JSON data to disk."""
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, default=str)


def ensure_output_dir(path_value: str | Path) -> Path:
    """Resolve and create one output directory."""
    output_dir = resolve_project_path(path_value)
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def normalize_whitespace(text: str) -> str:
    """Collapse repeated whitespace into single spaces."""
    return " ".join(text.replace("\u00A0", " ").strip().split())


def normalize_search_term(text: str) -> str:
    """Build one conservative normalized value for comparisons."""
    cleaned = normalize_whitespace(text)
    upper = cleaned.upper().replace("–", "-").replace("—", "-")
    match = CANONICAL_EVENT_PATTERN.match(upper)
    if match is not None:
        return f"{match.group(1)}{match.group(2)}"
    tns_match = TNS_EVENT_PATTERN.match(upper)
    if tns_match is not None:
        return f"{tns_match.group(1)}{tns_match.group(2)}"
    return upper


def build_conservative_variants(term: str) -> list[dict[str, Any]]:
    """Build conservative event-name formatting variants."""
    cleaned = normalize_whitespace(term)
    match = CANONICAL_EVENT_PATTERN.match(cleaned)
    if match is None:
        match = TNS_EVENT_PATTERN.match(cleaned)
        if match is None:
            return []

    prefix = match.group(1)
    code = match.group(2)
    compact = f"{prefix}{code}"
    spaced = f"{prefix} {code}"

    variants: list[dict[str, Any]] = []
    if compact != cleaned:
        variants.append(
            {
                "search_term": compact,
                "variant_type": "compact_variant",
                "variant_rank": 1,
            }
        )
    if spaced != cleaned:
        variants.append(
            {
                "search_term": spaced,
                "variant_type": "spaced_variant",
                "variant_rank": 1,
            }
        )
    return variants


def is_trigger_like_term(term: str) -> bool:
    """Return whether a term looks like an internal timestamp-like trigger."""
    cleaned = normalize_whitespace(term)
    return TRIGGER_LIKE_PATTERN.match(cleaned) is not None


def confidence_level_from_score(score: int) -> str:
    """Map one score to its confidence bucket."""
    if score >= 80:
        return "high_confidence"
    if score >= 60:
        return "medium_confidence"
    return "low_confidence"


def classify_match_score(
    *,
    matched_field: str,
    variant_type: str,
    is_trigger_like: bool,
) -> tuple[int, str]:
    """Assign the configured score and match class to one field hit."""
    if is_trigger_like:
        return 40, "trigger_like"

    if matched_field == "event_id":
        return 95, "original_term" if variant_type == "original" else "generated_variant"
    if matched_field == "subject":
        return (100, "original_term") if variant_type == "original" else (80, "generated_variant")
    if matched_field == "body":
        return (75, "original_term") if variant_type == "original" else (60, "generated_variant")

    raise ValueError(f"Unsupported matched field: {matched_field}")


def join_unique_strings(values: list[str]) -> str:
    """Join unique string values with a readable separator."""
    seen: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.append(value)
    return " | ".join(seen)


def choose_preferred_term_row(
    existing: dict[str, Any],
    incoming: dict[str, Any],
) -> dict[str, Any]:
    """Choose the preferred row when two identical search terms collide."""
    existing_key = (
        1 if existing["is_trigger_like"] else 0,
        0 if existing["origin_field"] == "alias" else 1,
        existing["variant_rank"],
        len(existing["search_term"]),
    )
    incoming_key = (
        1 if incoming["is_trigger_like"] else 0,
        0 if incoming["origin_field"] == "alias" else 1,
        incoming["variant_rank"],
        len(incoming["search_term"]),
    )
    if incoming_key < existing_key:
        return incoming
    return existing


def deduplicate_term_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate search-term rows while preserving the strongest variant."""
    deduplicated: dict[tuple[str, str], dict[str, Any]] = {}

    for row in rows:
        key = (str(row["source_id"]), str(row["search_term"]).upper())
        if key not in deduplicated:
            deduplicated[key] = row
            continue
        deduplicated[key] = choose_preferred_term_row(deduplicated[key], row)

    return list(deduplicated.values())


def extract_selected_sources(path: Path) -> list[dict[str, Any]]:
    """Load one supported event-universe file from disk."""
    if path.suffix == ".json":
        payload = load_json_object(path)
        if isinstance(payload.get("sources"), list):
            return [
                normalize_event_record(item)
                for item in payload["sources"]
                if isinstance(item, dict)
            ]
        raise ValueError(f"Expected 'sources' list in {path}")

    if path.suffix == ".parquet":
        dataframe = pd.read_parquet(path)
    elif path.suffix == ".csv":
        dataframe = pd.read_csv(path)
    else:
        raise ValueError(f"Unsupported event-universe input: {path}")

    return [
        normalize_event_record(record)
        for record in dataframe.to_dict(orient="records")
        if isinstance(record, dict)
    ]


def parse_list_like(value: object) -> list[str]:
    """Parse a compact string/list field into a list of strings."""
    if isinstance(value, list):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("[") and text.endswith("]"):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return [
                    item.strip()
                    for item in parsed
                    if isinstance(item, str) and item.strip()
                ]
        return [text]

    return []


def normalize_event_record(event: dict[str, Any]) -> dict[str, Any]:
    """Normalize one event record from the compact gcn_grandma base."""
    source_id = str(event.get("source_id") or event.get("id") or "").strip()

    aliases = parse_list_like(event.get("aliases"))
    groups = parse_list_like(event.get("groups"))

    normalized = dict(event)
    normalized["id"] = source_id
    normalized["source_id"] = source_id
    normalized["aliases"] = aliases
    normalized["groups"] = groups
    return normalized


def build_groups_string(event: dict[str, Any]) -> str:
    """Build a readable groups string from one selected event."""
    groups = event.get("groups", [])
    if not isinstance(groups, list):
        return ""
    group_names = [group for group in groups if isinstance(group, str) and group.strip()]
    return join_unique_strings(group_names)


def build_event_search_term_rows(event: dict[str, Any]) -> list[dict[str, Any]]:
    """Build all search-term rows for one selected event."""
    source_id = str(event.get("id") or event.get("source_id") or "").strip()
    if not source_id:
        return []

    gcn_source_type = event.get("gcn_source_type")
    if not isinstance(gcn_source_type, str):
        gcn_source_type = ""

    groups = build_groups_string(event)
    aliases = event.get("aliases", [])
    if not isinstance(aliases, list):
        aliases = []

    candidate_origins: list[tuple[str, str]] = [("id", source_id)]
    for alias in aliases:
        if isinstance(alias, str) and alias.strip():
            candidate_origins.append(("alias", normalize_whitespace(alias)))
    tns_name = event.get("tns_name")
    if isinstance(tns_name, str) and tns_name.strip():
        candidate_origins.append(("tns_name", normalize_whitespace(tns_name)))

    rows: list[dict[str, Any]] = []
    for origin_field, origin_value in candidate_origins:
        cleaned_origin_value = normalize_whitespace(origin_value)
        if not cleaned_origin_value:
            continue

        term_variants = [
            {
                "search_term": cleaned_origin_value,
                "variant_type": "original",
                "variant_rank": 0,
            },
            *build_conservative_variants(cleaned_origin_value),
        ]

        for variant in term_variants:
            search_term = normalize_whitespace(str(variant["search_term"]))
            if not search_term:
                continue

            rows.append(
                {
                    "source_id": source_id,
                    "gcn_source_type": gcn_source_type,
                    "origin_field": origin_field,
                    "origin_value": cleaned_origin_value,
                    "search_term": search_term,
                    "search_term_normalized": normalize_search_term(search_term),
                    "variant_type": variant["variant_type"],
                    "variant_rank": int(variant["variant_rank"]),
                    "is_trigger_like": is_trigger_like_term(search_term),
                    "groups": groups,
                }
            )

    return deduplicate_term_rows(rows)


def build_event_search_terms_dataframe(selected_sources: list[dict[str, Any]]) -> pd.DataFrame:
    """Build the full event search-terms table."""
    rows: list[dict[str, Any]] = []
    for event in selected_sources:
        rows.extend(build_event_search_term_rows(event))

    dataframe = pd.DataFrame(rows, columns=EVENT_SEARCH_TERMS_COLUMNS)
    if dataframe.empty:
        return dataframe

    dataframe = dataframe.sort_values(
        by=["source_id", "variant_rank", "origin_field", "search_term"],
        kind="stable",
    ).reset_index(drop=True)
    return dataframe


def write_dataframe_pair(
    dataframe: pd.DataFrame,
    output_dir: Path,
    *,
    csv_name: str,
    parquet_name: str,
) -> tuple[Path, Path]:
    """Write one dataframe to CSV and Parquet."""
    csv_path = output_dir / csv_name
    parquet_path = output_dir / parquet_name
    dataframe.to_csv(csv_path, index=False)
    dataframe.to_parquet(parquet_path, index=False)
    return csv_path, parquet_path


def run_gcn_event_search_terms_build(args: argparse.Namespace) -> None:
    """Build the reviewable event search-term tables."""
    setup_console_logging()
    selected_sources_path = resolve_project_path(args.selected_sources)
    output_dir = ensure_output_dir(args.output_dir)

    selected_sources = extract_selected_sources(selected_sources_path)
    dataframe = build_event_search_terms_dataframe(selected_sources)
    csv_path, parquet_path = write_dataframe_pair(
        dataframe,
        output_dir,
        csv_name=EVENT_SEARCH_TERMS_CSV,
        parquet_name=EVENT_SEARCH_TERMS_PARQUET,
    )

    events_without_aliases = sum(
        1
        for event in selected_sources
        if not isinstance(event.get("aliases"), list) or len(event.get("aliases", [])) == 0
    )

    logging.info("Selected events read: %s", len(selected_sources))
    logging.info("Search terms generated: %s", len(dataframe))
    logging.info("Events without aliases: %s", events_without_aliases)
    logging.info("Wrote CSV: %s", csv_path)
    logging.info("Wrote Parquet: %s", parquet_path)


def load_event_search_terms_dataframe(path: Path) -> pd.DataFrame:
    """Load the event search-term parquet file."""
    dataframe = pd.read_parquet(path)
    return dataframe


def load_gcn_circulars_dataframe(
    gcn_root: Path,
    *,
    year_from: int,
    year_to: int,
) -> tuple[pd.DataFrame, list[int]]:
    """Load the selected yearly GCN partitions into one dataframe."""
    if year_from > year_to:
        raise ValueError("year_from must be smaller than or equal to year_to")

    columns = [
        "circular_id",
        "event_id",
        "subject",
        "body",
        "created_at_iso",
        "raw_file_path",
        "raw_file_name",
        "archive_run_id",
    ]
    frames: list[pd.DataFrame] = []
    loaded_years: list[int] = []

    for year in range(year_from, year_to + 1):
        parquet_path = gcn_root / str(year) / "circulars_index.parquet"
        if not parquet_path.exists():
            raise FileNotFoundError(f"GCN year parquet not found: {parquet_path}")

        frame = pd.read_parquet(parquet_path, columns=columns)
        frame["year"] = year
        frames.append(frame)
        loaded_years.append(year)

    dataframe = pd.concat(frames, ignore_index=True)
    for field_name in ("subject", "event_id", "body"):
        dataframe[field_name] = dataframe[field_name].fillna("").astype(str)
        dataframe[f"_{field_name}_upper"] = dataframe[field_name].str.upper()

    dataframe["_event_id_normalized"] = dataframe["event_id"].map(normalize_search_term)
    return dataframe, loaded_years


def find_conservative_span(text: str, term: str) -> tuple[int, int] | None:
    """Find the first conservative match span using literal matching plus boundaries."""
    if not term:
        return None

    start_index = 0
    while True:
        index = text.find(term, start_index)
        if index < 0:
            return None

        end_index = index + len(term)
        previous_ok = index == 0 or not text[index - 1].isalnum()
        next_ok = end_index == len(text) or not text[end_index].isalnum()
        if previous_ok and next_ok:
            return index, end_index

        start_index = index + 1


def build_evidence_window(text: str, span: tuple[int, int], *, radius: int = 90) -> str:
    """Build a short evidence fragment around one match span."""
    start = max(0, span[0] - radius)
    end = min(len(text), span[1] + radius)
    fragment = text[start:end].replace("\n", " ").strip()
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{fragment}{suffix}"


def build_match_record(
    *,
    term_row: dict[str, Any],
    circular_row: pd.Series,
    matched_field: str,
    evidence_text: str,
) -> dict[str, Any]:
    """Build one detailed event-circular match record."""
    match_score, match_type = classify_match_score(
        matched_field=matched_field,
        variant_type=str(term_row["variant_type"]),
        is_trigger_like=bool(term_row["is_trigger_like"]),
    )
    return {
        "source_id": term_row["source_id"],
        "search_term": term_row["search_term"],
        "search_term_normalized": term_row["search_term_normalized"],
        "variant_type": term_row["variant_type"],
        "origin_field": term_row["origin_field"],
        "origin_value": term_row["origin_value"],
        "matched_field": matched_field,
        "match_type": match_type,
        "match_score": match_score,
        "confidence_level": confidence_level_from_score(match_score),
        "circular_id": str(circular_row["circular_id"]),
        "gcn_event_id": circular_row["event_id"],
        "subject": circular_row["subject"],
        "created_at_iso": circular_row["created_at_iso"],
        "raw_file_path": circular_row["raw_file_path"],
        "year": int(circular_row["year"]),
        "evidence_text": evidence_text,
    }


def find_event_id_matches(
    term_row: dict[str, Any],
    gcn_dataframe: pd.DataFrame,
) -> list[dict[str, Any]]:
    """Find strong event_id matches for one search term."""
    normalized_term = str(term_row["search_term_normalized"])
    if not normalized_term:
        return []

    matches = gcn_dataframe[gcn_dataframe["_event_id_normalized"] == normalized_term]
    rows: list[dict[str, Any]] = []
    for _, circular_row in matches.iterrows():
        rows.append(
            build_match_record(
                term_row=term_row,
                circular_row=circular_row,
                matched_field="event_id",
                evidence_text=str(circular_row["event_id"]).strip(),
            )
        )
    return rows


def find_text_field_matches(
    term_row: dict[str, Any],
    gcn_dataframe: pd.DataFrame,
    *,
    field_name: str,
) -> list[dict[str, Any]]:
    """Find conservative literal matches in one text field."""
    search_term = str(term_row["search_term"])
    if not search_term:
        return []

    search_term_upper = search_term.upper()
    field_upper_name = f"_{field_name}_upper"
    candidate_mask = gcn_dataframe[field_upper_name].str.contains(
        search_term_upper,
        regex=False,
        na=False,
    )
    if not bool(candidate_mask.any()):
        return []

    rows: list[dict[str, Any]] = []
    candidates = gcn_dataframe[candidate_mask]
    for _, circular_row in candidates.iterrows():
        span = find_conservative_span(
            str(circular_row[field_upper_name]),
            search_term_upper,
        )
        if span is None:
            continue

        original_text = str(circular_row[field_name])
        evidence_text = (
            original_text
            if field_name == "subject"
            else build_evidence_window(original_text, span)
        )
        rows.append(
            build_match_record(
                term_row=term_row,
                circular_row=circular_row,
                matched_field=field_name,
                evidence_text=evidence_text,
            )
        )
    return rows


def build_event_gcn_matches_dataframe(
    terms_dataframe: pd.DataFrame,
    gcn_dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """Build the detailed event-circular match table."""
    rows: list[dict[str, Any]] = []

    for term_row in terms_dataframe.to_dict(orient="records"):
        rows.extend(find_event_id_matches(term_row, gcn_dataframe))
        rows.extend(find_text_field_matches(term_row, gcn_dataframe, field_name="subject"))
        rows.extend(find_text_field_matches(term_row, gcn_dataframe, field_name="body"))

    dataframe = pd.DataFrame(rows, columns=EVENT_GCN_MATCHES_COLUMNS)
    if dataframe.empty:
        return dataframe

    dataframe = dataframe.sort_values(
        by=["source_id", "circular_id", "match_score", "matched_field", "search_term"],
        ascending=[True, True, False, True, True],
        kind="stable",
    ).reset_index(drop=True)
    return dataframe


def run_gcn_event_match_build(args: argparse.Namespace) -> None:
    """Match selected-event search terms against yearly GCN circular indices."""
    setup_console_logging()
    terms_path = resolve_project_path(args.terms_path)
    gcn_root = resolve_project_path(args.gcn_root)
    output_dir = ensure_output_dir(args.output_dir)

    terms_dataframe = load_event_search_terms_dataframe(terms_path)
    gcn_dataframe, loaded_years = load_gcn_circulars_dataframe(
        gcn_root,
        year_from=args.year_from,
        year_to=args.year_to,
    )
    matches_dataframe = build_event_gcn_matches_dataframe(terms_dataframe, gcn_dataframe)
    csv_path, parquet_path = write_dataframe_pair(
        matches_dataframe,
        output_dir,
        csv_name=EVENT_GCN_MATCHES_CSV,
        parquet_name=EVENT_GCN_MATCHES_PARQUET,
    )

    matched_source_count = (
        int(matches_dataframe["source_id"].nunique()) if not matches_dataframe.empty else 0
    )

    logging.info("GCN years loaded: %s", ", ".join(str(year) for year in loaded_years))
    logging.info("GCN circulars loaded: %s", len(gcn_dataframe))
    logging.info("Matches found: %s", len(matches_dataframe))
    logging.info("Events with at least one match: %s", matched_source_count)
    logging.info("Wrote CSV: %s", csv_path)
    logging.info("Wrote Parquet: %s", parquet_path)


def build_event_gcn_associations_dataframe(matches_dataframe: pd.DataFrame) -> pd.DataFrame:
    """Deduplicate detailed matches into one best row per event-circular pair."""
    if matches_dataframe.empty:
        return pd.DataFrame(columns=EVENT_GCN_ASSOCIATIONS_COLUMNS)

    rows: list[dict[str, Any]] = []
    group_columns = ["source_id", "circular_id"]
    grouped = matches_dataframe.groupby(group_columns, sort=True, dropna=False)

    for (_, _), group in grouped:
        best_group = group.assign(
            _matched_field_rank=group["matched_field"].map(FIELD_ORDER).fillna(99)
        ).sort_values(
            by=["match_score", "_matched_field_rank", "search_term"],
            ascending=[False, True, True],
            kind="stable",
        )
        best_row = best_group.iloc[0]
        rows.append(
            {
                "source_id": best_row["source_id"],
                "circular_id": best_row["circular_id"],
                "gcn_event_id": best_row["gcn_event_id"],
                "subject": best_row["subject"],
                "created_at_iso": best_row["created_at_iso"],
                "year": int(best_row["year"]),
                "best_matched_term": best_row["search_term"],
                "best_matched_field": best_row["matched_field"],
                "best_match_type": best_row["match_type"],
                "best_match_score": int(best_row["match_score"]),
                "best_confidence_level": best_row["confidence_level"],
                "evidence_text": best_row["evidence_text"],
                "raw_file_path": best_row["raw_file_path"],
                "matched_terms": join_unique_strings(group["search_term"].tolist()),
                "matched_fields": join_unique_strings(group["matched_field"].tolist()),
            }
        )

    dataframe = pd.DataFrame(rows, columns=EVENT_GCN_ASSOCIATIONS_COLUMNS)
    if dataframe.empty:
        return dataframe

    dataframe = dataframe.sort_values(
        by=["source_id", "best_match_score", "created_at_iso", "circular_id"],
        ascending=[True, False, True, True],
        kind="stable",
    ).reset_index(drop=True)
    return dataframe


def choose_best_confidence(matches_dataframe: pd.DataFrame) -> tuple[int, str]:
    """Return the best score and confidence for one source-level subset."""
    if matches_dataframe.empty:
        return 0, ""

    best_score = int(matches_dataframe["match_score"].max())
    return best_score, confidence_level_from_score(best_score)


def build_event_gcn_match_summary_dataframe(
    terms_dataframe: pd.DataFrame,
    matches_dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """Build the per-event review summary, including events with no match."""
    all_source_ids = sorted(str(source_id) for source_id in terms_dataframe["source_id"].dropna().unique())
    association_frame = build_event_gcn_associations_dataframe(matches_dataframe)

    rows: list[dict[str, Any]] = []
    for source_id in all_source_ids:
        source_terms = terms_dataframe[terms_dataframe["source_id"] == source_id]
        source_matches = matches_dataframe[matches_dataframe["source_id"] == source_id]
        source_associations = association_frame[association_frame["source_id"] == source_id]

        best_match_score, best_confidence_level = choose_best_confidence(source_matches)
        if best_confidence_level == "high_confidence":
            status = "matched"
        elif best_confidence_level == "medium_confidence":
            status = "medium_match"
        elif not source_matches.empty:
            status = "weak_match"
        else:
            status = "no_match"

        rows.append(
            {
                "source_id": source_id,
                "n_search_terms": int(source_terms["search_term"].nunique()),
                "n_matches": int(len(source_matches)),
                "n_matched_circulars": int(source_associations["circular_id"].nunique()),
                "n_high_confidence_matches": int(
                    (source_matches["confidence_level"] == "high_confidence").sum()
                ),
                "n_medium_confidence_matches": int(
                    (source_matches["confidence_level"] == "medium_confidence").sum()
                ),
                "n_low_confidence_matches": int(
                    (source_matches["confidence_level"] == "low_confidence").sum()
                ),
                "n_subject_matches": int((source_matches["matched_field"] == "subject").sum()),
                "n_event_id_matches": int((source_matches["matched_field"] == "event_id").sum()),
                "n_body_matches": int((source_matches["matched_field"] == "body").sum()),
                "best_match_score": best_match_score,
                "best_confidence_level": best_confidence_level,
                "matched_terms": join_unique_strings(source_matches["search_term"].tolist()),
                "status": status,
            }
        )

    dataframe = pd.DataFrame(rows, columns=EVENT_GCN_MATCH_SUMMARY_COLUMNS)
    dataframe["_status_rank"] = dataframe["status"].map(MATCH_STATUS_ORDER).fillna(99)
    dataframe = dataframe.sort_values(
        by=["_status_rank", "best_match_score", "n_matched_circulars", "n_matches", "source_id"],
        ascending=[True, False, False, False, True],
        kind="stable",
    ).drop(columns=["_status_rank"]).reset_index(drop=True)
    return dataframe


def filter_match_summary_to_matched(summary_dataframe: pd.DataFrame) -> pd.DataFrame:
    """Keep only events that have at least one GCN match."""
    filtered = summary_dataframe[summary_dataframe["status"] != "no_match"].copy()
    return filtered.reset_index(drop=True)


def run_gcn_event_match_summary_build(args: argparse.Namespace) -> None:
    """Build deduplicated associations and the per-event review summary."""
    setup_console_logging()
    matches_path = resolve_project_path(args.matches_path)
    terms_path = resolve_project_path(args.terms_path)
    output_dir = ensure_output_dir(args.output_dir)

    matches_dataframe = pd.read_parquet(matches_path)
    terms_dataframe = pd.read_parquet(terms_path)

    associations_dataframe = build_event_gcn_associations_dataframe(matches_dataframe)
    summary_dataframe = build_event_gcn_match_summary_dataframe(
        terms_dataframe,
        matches_dataframe,
    )

    associations_csv_path, associations_parquet_path = write_dataframe_pair(
        associations_dataframe,
        output_dir,
        csv_name=EVENT_GCN_ASSOCIATIONS_CSV,
        parquet_name=EVENT_GCN_ASSOCIATIONS_PARQUET,
    )
    summary_csv_path = output_dir / EVENT_GCN_MATCH_SUMMARY_CSV
    summary_dataframe.to_csv(summary_csv_path, index=False)

    status_counts = summary_dataframe["status"].value_counts().to_dict()
    logging.info("Total events: %s", len(summary_dataframe))
    logging.info("matched: %s", int(status_counts.get("matched", 0)))
    logging.info("medium_match: %s", int(status_counts.get("medium_match", 0)))
    logging.info("weak_match: %s", int(status_counts.get("weak_match", 0)))
    logging.info("no_match: %s", int(status_counts.get("no_match", 0)))
    logging.info("Wrote associations CSV: %s", associations_csv_path)
    logging.info("Wrote associations Parquet: %s", associations_parquet_path)
    logging.info("Wrote summary CSV: %s", summary_csv_path)
