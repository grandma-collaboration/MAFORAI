"""Helpers for compact event-level GCN enrichment candidates."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from ..core import resolve_project_path
from .gcn_core_claims import (
    DEFAULT_GCN_CORE_CLAIMS_PATH,
    DETECTION_VALUES,
    NON_DETECTION_VALUES,
    claim_confidence_rank,
    infer_redshift_method,
    parse_float_or_none,
)
from .gcn_event_matching import (
    DEFAULT_GCN_EVENT_MATCHING_SUMMARY_PATH,
    ensure_output_dir,
    filter_match_summary_to_matched,
    parse_list_like,
    save_json,
)
from .source_selection import DEFAULT_GCN_GRANDMA_OUTPUT

DEFAULT_GCN_EVENT_ENRICHMENT_OUTPUT_DIR = "data/interim/gcn/event_enrichment"
DEFAULT_GCN_EVENT_ENRICHMENT_INPUT_PATH = DEFAULT_GCN_GRANDMA_OUTPUT
DEFAULT_GCN_EVENT_BEST_CLAIMS_PATH = (
    f"{DEFAULT_GCN_EVENT_ENRICHMENT_OUTPUT_DIR}/gcn_event_best_claims.parquet"
)
DEFAULT_GCN_EVENT_ENRICHMENT_COMPARISON_PATH = (
    f"{DEFAULT_GCN_EVENT_ENRICHMENT_OUTPUT_DIR}/event_enrichment_comparison.parquet"
)

BEST_CLAIMS_CSV = "gcn_event_best_claims.csv"
BEST_CLAIMS_PARQUET = "gcn_event_best_claims.parquet"
BEST_CLAIMS_REPORT_JSON = "gcn_event_best_claims_report.json"
ENRICHMENT_COMPARISON_CSV = "event_enrichment_comparison.csv"
ENRICHMENT_COMPARISON_PARQUET = "event_enrichment_comparison.parquet"
ENRICHMENT_REPORT_JSON = "enrichment_report.json"

BEST_CLAIMS_COLUMNS = [
    "source_id",
    "has_gcn_match",
    "match_status",
    "n_matched_circulars",
    "n_claims",
    "n_circulars_with_claims",
    "best_trigger_time",
    "best_trigger_time_circular_id",
    "best_trigger_time_evidence",
    "best_t90_seconds",
    "best_t90_unit",
    "best_t90_circular_id",
    "best_t90_evidence",
    "best_duration_class",
    "best_duration_class_evidence",
    "best_redshift",
    "best_redshift_method",
    "best_redshift_circular_id",
    "best_redshift_evidence",
    "has_counterpart",
    "counterpart_types",
    "has_detection",
    "has_non_detection",
    "has_upper_limit",
    "has_spectroscopy",
    "has_host_candidate",
    "instruments_found",
    "classification_flags",
    "claim_types_found",
]

ENRICHMENT_COMPARISON_COLUMNS = [
    "source_id",
    "has_gcn_match",
    "match_status",
    "n_matched_circulars",
    "n_claims",
    "skyportal_has_redshift",
    "gcn_has_redshift",
    "gcn_adds_redshift",
    "skyportal_has_classification",
    "gcn_has_classification",
    "gcn_adds_classification",
    "skyportal_has_spectroscopy",
    "gcn_has_spectroscopy",
    "gcn_adds_spectroscopy",
    "skyportal_has_host",
    "gcn_has_host_candidate",
    "gcn_adds_host_candidate",
    "gcn_has_t90",
    "skyportal_has_trigger_time",
    "gcn_has_trigger_time",
    "gcn_adds_trigger_time",
    "gcn_has_counterpart",
    "gcn_has_detection",
    "gcn_has_non_detection",
    "gcn_has_upper_limit",
    "n_enrichment_fields",
    "enrichment_priority",
]

TRIGGER_TIME_RULE_PRIORITY = {
    "trigger_t0_explicit": 0,
    "trigger_iso_timestamp": 1,
    "trigger_ut_context": 2,
    "trigger_mjd": 3,
    "trigger_relative_t": 4,
    "trigger_tb_explicit": 5,
}
T90_RULE_PRIORITY = {
    "duration_t90_explicit": 0,
    "duration_t90_about": 1,
}
REDSHIFT_METHOD_PRIORITY = {
    "spectroscopic": 0,
    "host": 1,
    "photometric": 2,
    "tentative": 3,
    "unknown": 4,
}


def setup_console_logging() -> None:
    """Configure simple console logging for one run."""
    logging.basicConfig(level=logging.INFO, format="%(message)s", force=True)


def is_missing_value(value: object) -> bool:
    """Return whether one value should be treated as missing."""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return bool(pd.isna(value))


def unique_join(values: list[object]) -> str:
    """Join unique present values into one compact semicolon-separated string."""
    ordered: list[str] = []
    for value in values:
        if is_missing_value(value):
            continue
        text = str(value).strip()
        if text not in ordered:
            ordered.append(text)
    return ";".join(ordered)


def load_skyportal_event_rows(path: str | Path) -> list[dict[str, Any]]:
    """Load one supported SkyPortal event input file."""
    events_path = resolve_project_path(path)
    if events_path.suffix == ".json":
        with events_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        if not isinstance(payload, dict):
            raise ValueError("JSON event input must be a JSON object")
        if isinstance(payload.get("sources"), list):
            return [item for item in payload["sources"] if isinstance(item, dict)]
        raise ValueError("JSON event input must contain 'sources'")

    if events_path.suffix == ".parquet":
        dataframe = pd.read_parquet(events_path)
    elif events_path.suffix == ".csv":
        dataframe = pd.read_csv(events_path)
    else:
        raise ValueError(f"Unsupported event input path: {events_path}")

    return [row for row in dataframe.to_dict(orient="records") if isinstance(row, dict)]


def add_claim_sort_columns(
    claims_dataframe: pd.DataFrame,
    *,
    rule_priority: dict[str, int] | None = None,
    numeric_column: str | None = None,
) -> pd.DataFrame:
    """Add shared sort columns to one candidate-claims dataframe."""
    sortable = claims_dataframe.copy()
    sortable["_confidence_rank"] = sortable["claim_confidence"].map(claim_confidence_rank)
    if rule_priority is None:
        sortable["_rule_rank"] = 99
    else:
        sortable["_rule_rank"] = sortable["extraction_rule"].map(rule_priority).fillna(99)

    sortable["_source_field_rank"] = sortable["source_field"].map({"body": 0, "subject": 1}).fillna(9)

    if numeric_column is not None:
        sortable["_has_numeric_value"] = sortable[numeric_column].map(
            lambda value: 0 if parse_float_or_none(value) is not None else 1
        )
    else:
        sortable["_has_numeric_value"] = 0

    sortable["_match_rank"] = -pd.to_numeric(sortable["best_match_score"], errors="coerce").fillna(0)
    return sortable


def pick_best_redshift_claim(claims_dataframe: pd.DataFrame) -> dict[str, Any] | None:
    """Pick the best redshift claim for one event."""
    redshift_claims = claims_dataframe[claims_dataframe["claim_type"] == "redshift"]
    if redshift_claims.empty:
        return None

    sortable = add_claim_sort_columns(redshift_claims).copy()
    sortable["_method_rank"] = sortable["evidence_text"].map(
        lambda value: REDSHIFT_METHOD_PRIORITY.get(
            infer_redshift_method(str(value)),
            99,
        )
    )
    sortable = sortable.sort_values(
        by=[
            "_method_rank",
            "_confidence_rank",
            "_source_field_rank",
            "_match_rank",
            "created_at_iso",
            "circular_id",
        ],
        kind="stable",
    )
    return sortable.iloc[0].to_dict()


def pick_best_t90_claim(claims_dataframe: pd.DataFrame) -> dict[str, Any] | None:
    """Pick the best duration-T90 claim for one event."""
    t90_claims = claims_dataframe[claims_dataframe["claim_type"] == "duration_t90"]
    if t90_claims.empty:
        return None

    sortable = add_claim_sort_columns(
        t90_claims,
        rule_priority=T90_RULE_PRIORITY,
        numeric_column="normalized_value",
    ).sort_values(
        by=[
            "_has_numeric_value",
            "_confidence_rank",
            "_rule_rank",
            "_source_field_rank",
            "_match_rank",
            "created_at_iso",
            "circular_id",
        ],
        kind="stable",
    )
    return sortable.iloc[0].to_dict()


def pick_best_duration_class_claim(claims_dataframe: pd.DataFrame) -> dict[str, Any] | None:
    """Pick the best duration-class claim for one event."""
    duration_class_claims = claims_dataframe[
        claims_dataframe["claim_type"] == "duration_class"
    ]
    if duration_class_claims.empty:
        return None

    sortable = add_claim_sort_columns(duration_class_claims).sort_values(
        by=[
            "_confidence_rank",
            "_source_field_rank",
            "_match_rank",
            "created_at_iso",
            "circular_id",
        ],
        kind="stable",
    )
    return sortable.iloc[0].to_dict()


def pick_best_trigger_time_claim(claims_dataframe: pd.DataFrame) -> dict[str, Any] | None:
    """Pick the best trigger-time claim for one event."""
    trigger_time_claims = claims_dataframe[
        claims_dataframe["claim_type"] == "trigger_time_t0"
    ]
    if trigger_time_claims.empty:
        return None

    sortable = add_claim_sort_columns(
        trigger_time_claims,
        rule_priority=TRIGGER_TIME_RULE_PRIORITY,
    ).sort_values(
        by=[
            "_confidence_rank",
            "_rule_rank",
            "_source_field_rank",
            "_match_rank",
            "created_at_iso",
            "circular_id",
        ],
        kind="stable",
    )
    return sortable.iloc[0].to_dict()


def build_event_best_claims_dataframe(
    claims_dataframe: pd.DataFrame,
    match_summary_dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """Build one compact event-level best-claims table."""
    rows: list[dict[str, Any]] = []

    for match_row in match_summary_dataframe.to_dict(orient="records"):
        source_id = str(match_row["source_id"])
        source_claims = claims_dataframe[claims_dataframe["source_id"] == source_id]

        trigger_time_claim = pick_best_trigger_time_claim(source_claims)
        t90_claim = pick_best_t90_claim(source_claims)
        duration_class_claim = pick_best_duration_class_claim(source_claims)
        redshift_claim = pick_best_redshift_claim(source_claims)

        detection_values = {
            str(value)
            for value in source_claims.loc[
                source_claims["claim_type"] == "detection_status",
                "normalized_value",
            ].tolist()
            if not is_missing_value(value)
        }
        counterpart_types = unique_join(
            source_claims.loc[
                source_claims["claim_type"] == "counterpart_type",
                "normalized_value",
            ].tolist()
        )

        row = {
            "source_id": source_id,
            "has_gcn_match": bool(str(match_row.get("status", "")) != "no_match"),
            "match_status": str(match_row.get("status", "")),
            "n_matched_circulars": int(match_row.get("n_matched_circulars", 0) or 0),
            "n_claims": int(len(source_claims)),
            "n_circulars_with_claims": (
                int(source_claims["circular_id"].nunique()) if not source_claims.empty else 0
            ),
            "best_trigger_time": (
                str(trigger_time_claim.get("normalized_value") or trigger_time_claim.get("raw_value"))
                if trigger_time_claim is not None
                else ""
            ),
            "best_trigger_time_circular_id": (
                str(trigger_time_claim.get("circular_id", ""))
                if trigger_time_claim is not None
                else ""
            ),
            "best_trigger_time_evidence": (
                str(trigger_time_claim.get("evidence_text", ""))
                if trigger_time_claim is not None
                else ""
            ),
            "best_t90_seconds": (
                parse_float_or_none(t90_claim.get("normalized_value"))
                if t90_claim is not None
                else None
            ),
            "best_t90_unit": (
                "sec"
                if t90_claim is not None
                else ""
            ),
            "best_t90_circular_id": (
                str(t90_claim.get("circular_id", ""))
                if t90_claim is not None
                else ""
            ),
            "best_t90_evidence": (
                str(t90_claim.get("evidence_text", ""))
                if t90_claim is not None
                else ""
            ),
            "best_duration_class": (
                str(duration_class_claim.get("normalized_value") or duration_class_claim.get("raw_value"))
                if duration_class_claim is not None
                else ""
            ),
            "best_duration_class_evidence": (
                str(duration_class_claim.get("evidence_text", ""))
                if duration_class_claim is not None
                else ""
            ),
            "best_redshift": (
                parse_float_or_none(redshift_claim.get("normalized_value"))
                if redshift_claim is not None
                else None
            ),
            "best_redshift_method": (
                infer_redshift_method(str(redshift_claim.get("evidence_text", "")))
                if redshift_claim is not None
                else ""
            ),
            "best_redshift_circular_id": (
                str(redshift_claim.get("circular_id", ""))
                if redshift_claim is not None
                else ""
            ),
            "best_redshift_evidence": (
                str(redshift_claim.get("evidence_text", ""))
                if redshift_claim is not None
                else ""
            ),
            "has_counterpart": bool(counterpart_types),
            "counterpart_types": counterpart_types,
            "has_detection": bool(detection_values & DETECTION_VALUES),
            "has_non_detection": bool(detection_values & NON_DETECTION_VALUES),
            "has_upper_limit": bool(
                "upper_limit" in detection_values
                or (source_claims["claim_type"] == "upper_limit_simple").any()
            ),
            "has_spectroscopy": bool(
                (source_claims["claim_type"] == "spectroscopy_mention").any()
            ),
            "has_host_candidate": bool(
                (source_claims["claim_type"] == "host_candidate_mention").any()
            ),
            "instruments_found": unique_join(
                source_claims.loc[
                    source_claims["claim_type"] == "instrument_mention",
                    "normalized_value",
                ].tolist()
            ),
            "classification_flags": unique_join(
                source_claims.loc[
                    source_claims["claim_type"] == "classification_or_interpretation",
                    "normalized_value",
                ].tolist()
            ),
            "claim_types_found": unique_join(source_claims["claim_type"].tolist()),
        }
        rows.append(row)

    dataframe = pd.DataFrame(rows, columns=BEST_CLAIMS_COLUMNS)
    return dataframe.sort_values(by=["source_id"], kind="stable").reset_index(drop=True)


def build_event_best_claims_report(
    best_claims_dataframe: pd.DataFrame,
    *,
    output_dir: Path,
) -> dict[str, Any]:
    """Build one compact JSON report for the best-claims table."""
    return {
        "n_events_total": int(len(best_claims_dataframe)),
        "n_events_with_gcn_match": int(best_claims_dataframe["has_gcn_match"].sum()),
        "n_events_with_claims": int((best_claims_dataframe["n_claims"] > 0).sum()),
        "n_events_with_redshift": int(best_claims_dataframe["best_redshift"].notna().sum()),
        "n_events_with_t90": int(best_claims_dataframe["best_t90_seconds"].notna().sum()),
        "n_events_with_trigger_time": int(best_claims_dataframe["best_trigger_time"].astype(str).str.len().gt(0).sum()),
        "n_events_with_counterpart": int(best_claims_dataframe["has_counterpart"].sum()),
        "n_events_with_detection": int(best_claims_dataframe["has_detection"].sum()),
        "n_events_with_non_detection": int(best_claims_dataframe["has_non_detection"].sum()),
        "n_events_with_upper_limit": int(best_claims_dataframe["has_upper_limit"].sum()),
        "n_events_with_spectroscopy": int(best_claims_dataframe["has_spectroscopy"].sum()),
        "n_events_with_host_candidate": int(best_claims_dataframe["has_host_candidate"].sum()),
        "output_files": {
            "best_claims_csv": str((output_dir / BEST_CLAIMS_CSV).resolve()),
            "best_claims_parquet": str((output_dir / BEST_CLAIMS_PARQUET).resolve()),
            "report": str((output_dir / BEST_CLAIMS_REPORT_JSON).resolve()),
        },
    }


def extract_selected_source_base_row(event: dict[str, Any]) -> dict[str, Any]:
    """Extract the pragmatic base SkyPortal fields from gcn_grandma.json."""
    source_id = str(event.get("source_id") or event.get("id") or "")
    classification_labels = parse_list_like(event.get("classification_labels"))
    has_redshift = not is_missing_value(event.get("redshift"))

    has_spectroscopy = False
    if "has_spectra" in event:
        has_spectroscopy = bool(event.get("has_spectra", False))
    elif "spectrum_exists" in event:
        has_spectroscopy = bool(event.get("spectrum_exists", False))
    elif "skyportal_has_spectroscopy" in event:
        has_spectroscopy = bool(event.get("skyportal_has_spectroscopy", False))

    has_host = False
    if "has_host" in event:
        has_host = bool(event.get("has_host", False))

    has_trigger_time = not is_missing_value(event.get("trigger_time"))

    has_classification = False
    if "has_classification" in event:
        has_classification = bool(event.get("has_classification", False))
    else:
        has_classification = len(classification_labels) > 0

    return {
        "source_id": source_id,
        "skyportal_has_redshift": has_redshift,
        "skyportal_has_classification": has_classification,
        "skyportal_has_spectroscopy": has_spectroscopy,
        "skyportal_has_host": has_host,
        "skyportal_has_trigger_time": has_trigger_time,
    }


def compute_enrichment_priority(row: dict[str, Any]) -> str:
    """Compute one compact enrichment-priority label."""
    if not bool(row.get("has_gcn_match", False)) or int(row.get("n_claims", 0) or 0) == 0:
        return "none"

    if (
        bool(row.get("gcn_adds_redshift", False))
        or bool(row.get("gcn_has_t90", False))
        or (
            bool(row.get("gcn_has_counterpart", False))
            and bool(row.get("gcn_adds_spectroscopy", False))
        )
    ):
        return "high"

    if (
        bool(row.get("gcn_adds_trigger_time", False))
        or bool(row.get("gcn_adds_host_candidate", False))
        or bool(row.get("gcn_has_upper_limit", False))
        or bool(row.get("gcn_has_non_detection", False))
    ):
        return "medium"

    if int(row.get("n_enrichment_fields", 0) or 0) > 0:
        return "low"

    return "none"


def count_enrichment_fields(row: dict[str, Any]) -> int:
    """Count the tracked enrichment signals currently exposed in the comparison table."""
    enrichment_flags = [
        row.get("gcn_adds_redshift", False),
        row.get("gcn_adds_classification", False),
        row.get("gcn_adds_spectroscopy", False),
        row.get("gcn_adds_host_candidate", False),
        row.get("gcn_has_t90", False),
        row.get("gcn_adds_trigger_time", False),
        row.get("gcn_has_counterpart", False),
        row.get("gcn_has_detection", False),
        row.get("gcn_has_non_detection", False),
        row.get("gcn_has_upper_limit", False),
    ]
    return int(sum(bool(flag) for flag in enrichment_flags))


def build_event_enrichment_comparison_dataframe(
    selected_sources_rows: list[dict[str, Any]],
    best_claims_dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """Compare compact GCN enrichment candidates against fuller SkyPortal metadata."""
    selected_sources_lookup = {}
    for event in selected_sources_rows:
        if not isinstance(event, dict):
            continue
        base_row = extract_selected_source_base_row(event)
        selected_sources_lookup[base_row["source_id"]] = base_row

    rows: list[dict[str, Any]] = []
    matched_best_claims = best_claims_dataframe[
        best_claims_dataframe["has_gcn_match"].fillna(False).astype(bool)
    ]
    for best_claims_row in matched_best_claims.to_dict(orient="records"):
        source_id = str(best_claims_row["source_id"])
        base_row = selected_sources_lookup.get(source_id)
        if base_row is None:
            continue

        gcn_has_redshift = not is_missing_value(best_claims_row.get("best_redshift"))
        gcn_has_classification = not is_missing_value(
            best_claims_row.get("classification_flags")
        )
        gcn_has_spectroscopy = bool(best_claims_row.get("has_spectroscopy", False))
        gcn_has_host_candidate = bool(best_claims_row.get("has_host_candidate", False))
        gcn_has_t90 = not is_missing_value(best_claims_row.get("best_t90_seconds"))
        gcn_has_trigger_time = not is_missing_value(
            best_claims_row.get("best_trigger_time")
        )
        gcn_has_counterpart = bool(best_claims_row.get("has_counterpart", False))
        gcn_has_detection = bool(best_claims_row.get("has_detection", False))
        gcn_has_non_detection = bool(best_claims_row.get("has_non_detection", False))
        gcn_has_upper_limit = bool(best_claims_row.get("has_upper_limit", False))

        row = {
            "source_id": source_id,
            "has_gcn_match": bool(best_claims_row.get("has_gcn_match", False)),
            "match_status": str(best_claims_row.get("match_status", "")),
            "n_matched_circulars": int(best_claims_row.get("n_matched_circulars", 0) or 0),
            "n_claims": int(best_claims_row.get("n_claims", 0) or 0),
            "skyportal_has_redshift": base_row["skyportal_has_redshift"],
            "gcn_has_redshift": gcn_has_redshift,
            "gcn_adds_redshift": (not base_row["skyportal_has_redshift"]) and gcn_has_redshift,
            "skyportal_has_classification": base_row["skyportal_has_classification"],
            "gcn_has_classification": gcn_has_classification,
            "gcn_adds_classification": (not base_row["skyportal_has_classification"]) and gcn_has_classification,
            "skyportal_has_spectroscopy": base_row["skyportal_has_spectroscopy"],
            "gcn_has_spectroscopy": gcn_has_spectroscopy,
            "gcn_adds_spectroscopy": (not base_row["skyportal_has_spectroscopy"]) and gcn_has_spectroscopy,
            "skyportal_has_host": base_row["skyportal_has_host"],
            "gcn_has_host_candidate": gcn_has_host_candidate,
            "gcn_adds_host_candidate": (not base_row["skyportal_has_host"]) and gcn_has_host_candidate,
            "gcn_has_t90": gcn_has_t90,
            "skyportal_has_trigger_time": base_row["skyportal_has_trigger_time"],
            "gcn_has_trigger_time": gcn_has_trigger_time,
            "gcn_adds_trigger_time": (
                (not base_row["skyportal_has_trigger_time"]) and gcn_has_trigger_time
            ),
            "gcn_has_counterpart": gcn_has_counterpart,
            "gcn_has_detection": gcn_has_detection,
            "gcn_has_non_detection": gcn_has_non_detection,
            "gcn_has_upper_limit": gcn_has_upper_limit,
        }

        row["n_enrichment_fields"] = count_enrichment_fields(row)
        row["enrichment_priority"] = compute_enrichment_priority(row)

        rows.append(row)

    dataframe = pd.DataFrame(rows, columns=ENRICHMENT_COMPARISON_COLUMNS)
    return dataframe.sort_values(by=["source_id"], kind="stable").reset_index(drop=True)


def build_event_enrichment_report(
    comparison_dataframe: pd.DataFrame,
    *,
    output_dir: Path,
) -> dict[str, Any]:
    """Build one compact report for the event-enrichment comparison."""
    return {
        "n_events_total": int(len(comparison_dataframe)),
        "n_events_with_gcn_match": int(comparison_dataframe["has_gcn_match"].sum()),
        "n_events_with_claims": int((comparison_dataframe["n_claims"] > 0).sum()),
        "n_events_with_enrichment": int((comparison_dataframe["n_enrichment_fields"] > 0).sum()),
        "n_high_priority": int((comparison_dataframe["enrichment_priority"] == "high").sum()),
        "n_medium_priority": int((comparison_dataframe["enrichment_priority"] == "medium").sum()),
        "n_low_priority": int((comparison_dataframe["enrichment_priority"] == "low").sum()),
        "n_gcn_adds_redshift": int(comparison_dataframe["gcn_adds_redshift"].sum()),
        "n_gcn_adds_classification": int(comparison_dataframe["gcn_adds_classification"].sum()),
        "n_gcn_adds_spectroscopy": int(comparison_dataframe["gcn_adds_spectroscopy"].sum()),
        "n_gcn_adds_host_candidate": int(comparison_dataframe["gcn_adds_host_candidate"].sum()),
        "n_gcn_has_t90": int(comparison_dataframe["gcn_has_t90"].sum()),
        "n_gcn_has_trigger_time": int(comparison_dataframe["gcn_has_trigger_time"].sum()),
        "n_gcn_adds_trigger_time": int(comparison_dataframe["gcn_adds_trigger_time"].sum()),
        "n_gcn_has_counterpart": int(comparison_dataframe["gcn_has_counterpart"].sum()),
        "output_files": {
            "comparison_csv": str((output_dir / ENRICHMENT_COMPARISON_CSV).resolve()),
            "comparison_parquet": str((output_dir / ENRICHMENT_COMPARISON_PARQUET).resolve()),
            "report": str((output_dir / ENRICHMENT_REPORT_JSON).resolve()),
        },
    }


def run_gcn_event_best_claims_build(args: argparse.Namespace) -> None:
    """Build compact event-level best-claims candidates from existing GCN claims."""
    setup_console_logging()
    claims_path = resolve_project_path(args.claims_path)
    match_summary_path = resolve_project_path(args.match_summary_path)
    output_dir = ensure_output_dir(args.output_dir)

    claims_dataframe = pd.read_parquet(claims_path)
    match_summary_dataframe = pd.read_csv(match_summary_path)
    match_summary_dataframe = filter_match_summary_to_matched(match_summary_dataframe)
    best_claims_dataframe = build_event_best_claims_dataframe(
        claims_dataframe,
        match_summary_dataframe,
    )

    csv_path = output_dir / BEST_CLAIMS_CSV
    parquet_path = output_dir / BEST_CLAIMS_PARQUET
    best_claims_dataframe.to_csv(csv_path, index=False)
    best_claims_dataframe.to_parquet(parquet_path, index=False)

    report = build_event_best_claims_report(
        best_claims_dataframe,
        output_dir=output_dir,
    )
    save_json(output_dir / BEST_CLAIMS_REPORT_JSON, report)

    logging.info("Events summarized: %s", len(best_claims_dataframe))
    logging.info("Events with claims: %s", int((best_claims_dataframe['n_claims'] > 0).sum()))
    logging.info("Wrote CSV: %s", csv_path)
    logging.info("Wrote Parquet: %s", parquet_path)
    logging.info("Wrote report: %s", output_dir / BEST_CLAIMS_REPORT_JSON)


def run_gcn_event_enrichment_comparison(args: argparse.Namespace) -> None:
    """Compare GCN best-claim candidates against the selected SkyPortal metadata."""
    setup_console_logging()
    selected_sources_path = resolve_project_path(args.selected_sources)
    best_claims_path = resolve_project_path(args.best_claims_path)
    output_dir = ensure_output_dir(args.output_dir)

    selected_sources_rows = load_skyportal_event_rows(selected_sources_path)
    best_claims_dataframe = pd.read_parquet(best_claims_path)
    comparison_dataframe = build_event_enrichment_comparison_dataframe(
        selected_sources_rows,
        best_claims_dataframe,
    )

    csv_path = output_dir / ENRICHMENT_COMPARISON_CSV
    parquet_path = output_dir / ENRICHMENT_COMPARISON_PARQUET
    comparison_dataframe.to_csv(csv_path, index=False)
    comparison_dataframe.to_parquet(parquet_path, index=False)

    report = build_event_enrichment_report(
        comparison_dataframe,
        output_dir=output_dir,
    )
    save_json(output_dir / ENRICHMENT_REPORT_JSON, report)

    logging.info("Events compared: %s", len(comparison_dataframe))
    logging.info("Events with enrichment fields: %s", int((comparison_dataframe['n_enrichment_fields'] > 0).sum()))
    logging.info("Wrote CSV: %s", csv_path)
    logging.info("Wrote Parquet: %s", parquet_path)
    logging.info("Wrote report: %s", output_dir / ENRICHMENT_REPORT_JSON)
