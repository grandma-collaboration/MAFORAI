"""Build one review-oriented table for astronomer validation of GCN enrichment."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from ..core import resolve_project_path
from .gcn_core_claims import (
    DEFAULT_GCN_CORE_CLAIMS_PATH,
    infer_redshift_method,
    parse_float_or_none,
)
from .gcn_event_enrichment import (
    DEFAULT_GCN_EVENT_BEST_CLAIMS_PATH,
    DEFAULT_GCN_EVENT_ENRICHMENT_INPUT_PATH,
    REDSHIFT_METHOD_PRIORITY,
    T90_RULE_PRIORITY,
    TRIGGER_TIME_RULE_PRIORITY,
    add_claim_sort_columns,
    is_missing_value,
    load_skyportal_event_rows,
    trigger_time_value_rank,
)
from .gcn_event_matching import ensure_output_dir, parse_list_like

DEFAULT_GCN_EVENT_REVIEW_OUTPUT_DIR = "data/interim/gcn/event_validation"
EVENT_REVIEW_TABLE_CSV = "gcn_event_review_table.csv"
EVENT_REVIEW_TABLE_PARQUET = "gcn_event_review_table.parquet"

EVENT_REVIEW_COLUMNS = [
    "source_id",
    "groups",
    "field_name",
    "skyportal_value",
    "gcn_candidate_value",
    "gcn_candidate_context",
    "comparison_status",
    "circular_id",
    "evidence_text",
    "claim_confidence",
    "review_priority",
    "astronomer_decision",
    "validated_value",
    "astronomer_notes",
]

FIELD_ORDER = {
    "redshift": 0,
    "trigger_time": 1,
    "t90": 2,
    "duration_class": 3,
    "spectroscopy": 4,
    "counterpart": 5,
    "host_candidate": 6,
}

PRIORITY_ORDER = {
    "high": 0,
    "medium": 1,
    "low": 2,
}


def setup_console_logging() -> None:
    """Configure simple console logging for one run."""
    logging.basicConfig(level=logging.INFO, format="%(message)s", force=True)


def unique_join(values: list[str]) -> str:
    """Join unique non-empty strings with a pipe separator."""
    ordered: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in ordered:
            ordered.append(text)
    return " | ".join(ordered)


def format_review_value(value: object) -> str:
    """Format one value for the CSV/parquet review table."""
    if is_missing_value(value):
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:g}"
    if isinstance(value, int):
        return str(value)
    return str(value).strip()


def extract_review_base_row(event: dict[str, Any]) -> dict[str, Any]:
    """Extract only the SkyPortal fields needed for the review table."""
    groups = unique_join([str(item) for item in parse_list_like(event.get("groups")) if str(item).strip()])

    has_spectroscopy = False
    if "has_spectra" in event:
        has_spectroscopy = bool(event.get("has_spectra", False))
    elif "spectrum_exists" in event:
        has_spectroscopy = bool(event.get("spectrum_exists", False))

    return {
        "source_id": str(event.get("source_id") or event.get("id") or "").strip(),
        "groups": groups,
        "redshift": event.get("redshift"),
        "trigger_time": event.get("trigger_time"),
        "spectroscopy": has_spectroscopy,
        "host_candidate": bool(event.get("has_host", False)),
    }


def pick_best_claim_for_field(
    claims_dataframe: pd.DataFrame,
    *,
    field_name: str,
) -> dict[str, Any] | None:
    """Pick one best claim row for one review field."""
    if field_name == "redshift":
        field_claims = claims_dataframe[claims_dataframe["claim_type"] == "redshift"]
        if field_claims.empty:
            return None
        sortable = add_claim_sort_columns(field_claims).copy()
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

    if field_name == "trigger_time":
        field_claims = claims_dataframe[claims_dataframe["claim_type"] == "trigger_time_t0"]
        if field_claims.empty:
            return None
        sortable = add_claim_sort_columns(
            field_claims,
            rule_priority=TRIGGER_TIME_RULE_PRIORITY,
        ).copy()
        sortable["_trigger_value_rank"] = sortable["normalized_value"].map(trigger_time_value_rank)
        sortable = sortable.sort_values(
            by=[
                "_confidence_rank",
                "_trigger_value_rank",
                "_rule_rank",
                "_source_field_rank",
                "_match_rank",
                "created_at_iso",
                "circular_id",
            ],
            kind="stable",
        )
        return sortable.iloc[0].to_dict()

    if field_name == "t90":
        field_claims = claims_dataframe[claims_dataframe["claim_type"] == "duration_t90"]
        if field_claims.empty:
            return None
        sortable = add_claim_sort_columns(
            field_claims,
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

    if field_name == "duration_class":
        field_claims = claims_dataframe[claims_dataframe["claim_type"] == "duration_class"]
        if field_claims.empty:
            return None
        sortable = add_claim_sort_columns(field_claims).sort_values(
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

    if field_name == "counterpart":
        field_claims = claims_dataframe[claims_dataframe["claim_type"] == "counterpart_type"]
        if field_claims.empty:
            return None
        sortable = add_claim_sort_columns(field_claims).sort_values(
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

    if field_name == "spectroscopy":
        field_claims = claims_dataframe[claims_dataframe["claim_type"] == "spectroscopy_mention"]
        if field_claims.empty:
            return None
        sortable = add_claim_sort_columns(field_claims).sort_values(
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

    if field_name == "host_candidate":
        field_claims = claims_dataframe[claims_dataframe["claim_type"] == "host_candidate_mention"]
        if field_claims.empty:
            return None
        sortable = add_claim_sort_columns(field_claims).sort_values(
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

    raise ValueError(f"Unsupported review field: {field_name}")


def build_candidate_value_and_context(
    field_name: str,
    claim: dict[str, Any],
) -> tuple[str, str]:
    """Map one best claim into review-table value and compact context."""
    if field_name == "redshift":
        return (
            format_review_value(parse_float_or_none(claim.get("normalized_value"))),
            infer_redshift_method(str(claim.get("evidence_text", ""))),
        )

    if field_name == "trigger_time":
        value = claim.get("normalized_value") or claim.get("raw_value")
        return (
            format_review_value(value),
            format_review_value(claim.get("extraction_rule")),
        )

    if field_name == "t90":
        return (
            format_review_value(parse_float_or_none(claim.get("normalized_value"))),
            format_review_value(claim.get("raw_value")),
        )

    if field_name == "duration_class":
        return (
            format_review_value(claim.get("normalized_value") or claim.get("raw_value")),
            format_review_value(claim.get("raw_value")),
        )

    if field_name == "counterpart":
        return (
            format_review_value(claim.get("normalized_value")),
            format_review_value(claim.get("raw_value")),
        )

    if field_name == "spectroscopy":
        context = claim.get("instrument_if_any") or claim.get("raw_value")
        return ("true", format_review_value(context))

    if field_name == "host_candidate":
        return ("true", format_review_value(claim.get("raw_value")))

    raise ValueError(f"Unsupported review field: {field_name}")


def comparison_status_for_row(
    *,
    field_name: str,
    skyportal_value: object,
    gcn_candidate_value: str,
) -> str:
    """Classify the review relationship between SkyPortal and the GCN candidate."""
    if field_name in {"spectroscopy", "counterpart", "host_candidate"}:
        if not format_review_value(skyportal_value) or format_review_value(skyportal_value) == "false":
            return "gcn_only_context_flag"
        return "complementary_context"

    if not format_review_value(skyportal_value):
        return "missing_in_skyportal"

    if field_name == "redshift":
        sky_value = parse_float_or_none(skyportal_value)
        gcn_value = parse_float_or_none(gcn_candidate_value)
        if sky_value is not None and gcn_value is not None:
            if abs(sky_value - gcn_value) <= 0.05:
                return "same_or_consistent"
            return "possible_conflict"
        return "complementary_context"

    if field_name == "trigger_time":
        sky_value = parse_float_or_none(skyportal_value)
        gcn_value = parse_float_or_none(gcn_candidate_value)
        if sky_value is not None and gcn_value is not None and abs(sky_value - gcn_value) <= 1e-6:
            return "same_or_consistent"
        if format_review_value(skyportal_value) == format_review_value(gcn_candidate_value):
            return "same_or_consistent"
        return "complementary_context"

    if field_name == "t90":
        sky_value = parse_float_or_none(skyportal_value)
        gcn_value = parse_float_or_none(gcn_candidate_value)
        if sky_value is not None and gcn_value is not None:
            if abs(sky_value - gcn_value) <= 0.5:
                return "same_or_consistent"
            return "possible_conflict"
        return "complementary_context"

    if field_name == "duration_class":
        if format_review_value(skyportal_value).lower() == format_review_value(gcn_candidate_value).lower():
            return "same_or_consistent"
        return "missing_in_skyportal"

    return "complementary_context"


def review_priority_for_row(field_name: str, comparison_status: str) -> str:
    """Assign one compact review priority."""
    if comparison_status == "possible_conflict":
        return "high"
    if field_name in {"redshift", "trigger_time", "t90"}:
        return "high"
    if field_name in {"duration_class", "counterpart", "spectroscopy", "host_candidate"}:
        return "medium"
    return "low"


def build_event_review_table_dataframe(
    selected_sources_rows: list[dict[str, Any]],
    best_claims_dataframe: pd.DataFrame,
    claims_dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """Build the final astronomer-facing validation table."""
    base_lookup: dict[str, dict[str, Any]] = {}
    for event in selected_sources_rows:
        if not isinstance(event, dict):
            continue
        base_row = extract_review_base_row(event)
        if base_row["source_id"]:
            base_lookup[base_row["source_id"]] = base_row

    rows: list[dict[str, Any]] = []
    matched_best_claims = best_claims_dataframe[
        best_claims_dataframe["has_gcn_match"].fillna(False).astype(bool)
    ]

    for best_claims_row in matched_best_claims.to_dict(orient="records"):
        source_id = str(best_claims_row.get("source_id", "")).strip()
        if not source_id or source_id not in base_lookup:
            continue

        base_row = base_lookup[source_id]
        source_claims = claims_dataframe[claims_dataframe["source_id"] == source_id]
        if source_claims.empty:
            continue

        field_specs = [
            ("redshift", base_row.get("redshift")),
            ("trigger_time", base_row.get("trigger_time")),
            ("t90", None),
            ("duration_class", None),
            ("counterpart", None),
            ("spectroscopy", base_row.get("spectroscopy")),
            ("host_candidate", base_row.get("host_candidate")),
        ]

        for field_name, skyportal_value in field_specs:
            claim = pick_best_claim_for_field(source_claims, field_name=field_name)
            if claim is None:
                continue

            gcn_candidate_value, gcn_candidate_context = build_candidate_value_and_context(
                field_name,
                claim,
            )
            comparison_status = comparison_status_for_row(
                field_name=field_name,
                skyportal_value=skyportal_value,
                gcn_candidate_value=gcn_candidate_value,
            )
            review_priority = review_priority_for_row(field_name, comparison_status)

            rows.append(
                {
                    "source_id": source_id,
                    "groups": base_row.get("groups", ""),
                    "field_name": field_name,
                    "skyportal_value": format_review_value(skyportal_value),
                    "gcn_candidate_value": gcn_candidate_value,
                    "gcn_candidate_context": gcn_candidate_context,
                    "comparison_status": comparison_status,
                    "circular_id": format_review_value(claim.get("circular_id")),
                    "evidence_text": format_review_value(claim.get("evidence_text")),
                    "claim_confidence": format_review_value(claim.get("claim_confidence")),
                    "review_priority": review_priority,
                    "astronomer_decision": "pending",
                    "validated_value": "",
                    "astronomer_notes": "",
                }
            )

    dataframe = pd.DataFrame(rows, columns=EVENT_REVIEW_COLUMNS)
    if dataframe.empty:
        return dataframe

    dataframe["_priority_rank"] = dataframe["review_priority"].map(PRIORITY_ORDER).fillna(99)
    dataframe["_field_rank"] = dataframe["field_name"].map(FIELD_ORDER).fillna(99)
    dataframe = dataframe.sort_values(
        by=["_priority_rank", "source_id", "_field_rank", "circular_id"],
        kind="stable",
    ).drop(columns=["_priority_rank", "_field_rank"]).reset_index(drop=True)
    return dataframe


def run_gcn_event_review_table_build(args: argparse.Namespace) -> None:
    """Build the final review table used for astronomer validation."""
    setup_console_logging()
    selected_sources_path = resolve_project_path(args.selected_sources)
    best_claims_path = resolve_project_path(args.best_claims_path)
    claims_path = resolve_project_path(args.claims_path)
    output_dir = ensure_output_dir(args.output_dir)

    selected_sources_rows = load_skyportal_event_rows(selected_sources_path)
    best_claims_dataframe = pd.read_parquet(best_claims_path)
    claims_dataframe = pd.read_parquet(claims_path)

    review_dataframe = build_event_review_table_dataframe(
        selected_sources_rows,
        best_claims_dataframe,
        claims_dataframe,
    )

    csv_path = output_dir / EVENT_REVIEW_TABLE_CSV
    parquet_path = output_dir / EVENT_REVIEW_TABLE_PARQUET
    review_dataframe.to_csv(csv_path, index=False)
    review_dataframe.to_parquet(parquet_path, index=False)

    logging.info("Review rows written: %s", len(review_dataframe))
    if not review_dataframe.empty:
        logging.info("Unique events covered: %s", int(review_dataframe["source_id"].nunique()))
        logging.info(
            "Fields covered: %s",
            unique_join(review_dataframe["field_name"].tolist()),
        )
    logging.info("Wrote CSV: %s", csv_path)
    logging.info("Wrote Parquet: %s", parquet_path)
