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
    REDSHIFT_METHOD_PRIORITY,
    T90_RULE_PRIORITY,
    TRIGGER_TIME_RULE_PRIORITY,
    add_claim_sort_columns,
    trigger_time_value_rank,
)
from .gcn_event_matching import ensure_output_dir
from .skyportal_event_baseline import (
    is_missing_value,
    load_skyportal_event_rows,
    parse_compact_values,
)

DEFAULT_GCN_EVENT_REVIEW_OUTPUT_DIR = "data/interim/gcn/event_validation"
EVENT_REVIEW_TABLE_CSV = "gcn_event_review_table.csv"
EVENT_REVIEW_TABLE_PARQUET = "gcn_event_review_table.parquet"

EVENT_REVIEW_COLUMNS = [
    "source_id",
    "groups",
    "field_name",
    "skyportal_value",
    "skyportal_value_source",
    "gcn_candidate_value",
    "gcn_candidate_context",
    "comparison_status",
    "circular_id",
    "evidence_text",
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

COMPARISON_STATUS_ORDER = {
    "possible_conflict": 0,
    "missing_in_skyportal": 1,
    "gcn_only_context_flag": 2,
    "complementary_context": 3,
    "same_or_consistent": 4,
}
COUNTERPART_VALUE_ORDER = {
    "optical": 0,
    "xray": 1,
    "nir": 2,
    "radio": 3,
    "uv": 4,
    "candidate_counterpart": 5,
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


def compact_semicolon_join(values: list[object]) -> str:
    """Join unique present values into one compact semicolon-separated string."""
    ordered: list[str] = []
    for value in values:
        text = format_review_value(value)
        if text and text not in ordered:
            ordered.append(text)
    return ";".join(ordered)


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


def has_compact_value(value: object) -> bool:
    """Return whether a compact baseline field contains at least one value."""
    return bool(parse_compact_values(value))


def join_source_labels(*labels: str) -> str:
    """Join source labels in the required stable order without duplicates."""
    ordered: list[str] = []
    for label in labels:
        text = label.strip()
        if text and text not in ordered:
            ordered.append(text)
    return "+".join(ordered)


def resolve_skyportal_value_source(event: dict[str, Any], *, field_name: str) -> str:
    """Resolve the provenance of one SkyPortal-side value kept in the baseline."""
    if field_name == "redshift":
        return join_source_labels(
            "native" if not is_missing_value(event.get("native_redshift")) else "",
            "summary_extracted" if has_compact_value(event.get("summary_redshift_values")) else "",
        )

    if field_name == "trigger_time":
        return join_source_labels(
            "native" if not is_missing_value(event.get("native_trigger_time")) else "",
            "summary_extracted"
            if has_compact_value(event.get("summary_trigger_time_values"))
            else "",
        )

    if field_name == "t90":
        return join_source_labels(
            "summary_extracted" if has_compact_value(event.get("summary_t90_values")) else "",
        )

    if field_name == "duration_class":
        return join_source_labels(
            "summary_extracted"
            if has_compact_value(event.get("summary_duration_classes"))
            else "",
            "tag_normalized" if has_compact_value(event.get("tag_temporal_classes")) else "",
        )

    if field_name == "counterpart":
        return join_source_labels(
            "summary_extracted"
            if has_compact_value(event.get("summary_counterpart_types"))
            else "",
            "tag_normalized"
            if has_compact_value(event.get("tag_counterpart_contexts"))
            else "",
        )

    if field_name == "spectroscopy":
        return join_source_labels(
            "native" if bool(event.get("native_spectrum_exists", False)) else "",
            "summary_extracted"
            if bool(event.get("summary_has_spectroscopy", False))
            else "",
        )

    if field_name == "host_candidate":
        return join_source_labels(
            "native" if bool(event.get("native_has_host", False)) else "",
            "summary_extracted"
            if bool(event.get("summary_has_host_candidate", False))
            else "",
        )

    raise ValueError(f"Unsupported SkyPortal review field: {field_name}")


def extract_review_base_row(event: dict[str, Any]) -> dict[str, Any]:
    """Extract only the baseline-backed SkyPortal fields needed for the review table."""
    groups = unique_join(parse_compact_values(event.get("groups")))
    return {
        "source_id": str(event.get("source_id") or event.get("id") or "").strip(),
        "groups": groups,
        "redshift": event.get("baseline_redshift_values"),
        "redshift_source": resolve_skyportal_value_source(event, field_name="redshift"),
        "trigger_time": event.get("baseline_trigger_time_values"),
        "trigger_time_source": resolve_skyportal_value_source(event, field_name="trigger_time"),
        "t90": event.get("baseline_t90_values"),
        "t90_source": resolve_skyportal_value_source(event, field_name="t90"),
        "duration_class": event.get("baseline_duration_classes"),
        "duration_class_source": resolve_skyportal_value_source(
            event,
            field_name="duration_class",
        ),
        "counterpart": event.get("baseline_counterpart_contexts"),
        "counterpart_source": resolve_skyportal_value_source(
            event,
            field_name="counterpart",
        ),
        "spectroscopy": bool(event.get("baseline_has_spectroscopy", False)),
        "spectroscopy_source": resolve_skyportal_value_source(
            event,
            field_name="spectroscopy",
        ),
        "host_candidate": bool(event.get("baseline_has_host_candidate", False)),
        "host_candidate_source": resolve_skyportal_value_source(
            event,
            field_name="host_candidate",
        ),
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


def build_counterpart_review_bundle(
    claims_dataframe: pd.DataFrame,
) -> dict[str, str] | None:
    """Build one compact counterpart bundle using the union of representative claims."""
    counterpart_claims = claims_dataframe[claims_dataframe["claim_type"] == "counterpart_type"]
    if counterpart_claims.empty:
        return None

    sortable = add_claim_sort_columns(counterpart_claims).sort_values(
        by=[
            "_confidence_rank",
            "_source_field_rank",
            "_match_rank",
            "created_at_iso",
            "circular_id",
        ],
        kind="stable",
    )

    representatives: dict[str, dict[str, Any]] = {}
    for row in sortable.to_dict(orient="records"):
        normalized_value = format_review_value(row.get("normalized_value"))
        if normalized_value and normalized_value not in representatives:
            representatives[normalized_value] = row

    if not representatives:
        return None

    ordered_values = sorted(
        representatives,
        key=lambda value: (
            COUNTERPART_VALUE_ORDER.get(value, 99),
            value,
        ),
    )
    ordered_rows = [representatives[value] for value in ordered_values]

    return {
        "gcn_candidate_value": compact_semicolon_join(ordered_values),
        "gcn_candidate_context": compact_semicolon_join(
            [row.get("raw_value") for row in ordered_rows]
        ),
        "circular_id": unique_join(
            [format_review_value(row.get("circular_id")) for row in ordered_rows]
        ),
        "evidence_text": unique_join(
            [
                f"{value}: {format_review_value(row.get('evidence_text'))}"
                for value, row in zip(ordered_values, ordered_rows, strict=False)
            ]
        ),
    }


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
    if field_name in {"spectroscopy", "host_candidate"}:
        if not format_review_value(skyportal_value) or format_review_value(skyportal_value) == "false":
            return "gcn_only_context_flag"
        return "complementary_context"

    if field_name == "counterpart":
        skyportal_values = {
            value.lower()
            for value in parse_compact_values(skyportal_value)
        }
        skyportal_positive_values = {
            value
            for value in skyportal_values
            if value != "no_optical"
        }
        gcn_values = {
            value.lower()
            for value in parse_compact_values(gcn_candidate_value)
        }
        if not gcn_values:
            return "same_or_consistent"
        if not skyportal_positive_values:
            if "no_optical" in skyportal_values:
                return "complementary_context"
            return "gcn_only_context_flag"
        if gcn_values.issubset(skyportal_positive_values):
            return "same_or_consistent"
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
        skyportal_values = {
            value.lower()
            for value in parse_compact_values(skyportal_value)
        }
        gcn_values = {
            value.lower()
            for value in parse_compact_values(gcn_candidate_value)
        }
        if skyportal_values & gcn_values:
            return "same_or_consistent"
        return "possible_conflict"

    return "complementary_context"

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
            ("redshift", base_row.get("redshift"), base_row.get("redshift_source")),
            (
                "trigger_time",
                base_row.get("trigger_time"),
                base_row.get("trigger_time_source"),
            ),
            ("t90", base_row.get("t90"), base_row.get("t90_source")),
            (
                "duration_class",
                base_row.get("duration_class"),
                base_row.get("duration_class_source"),
            ),
            (
                "counterpart",
                base_row.get("counterpart"),
                base_row.get("counterpart_source"),
            ),
            (
                "spectroscopy",
                base_row.get("spectroscopy"),
                base_row.get("spectroscopy_source"),
            ),
            (
                "host_candidate",
                base_row.get("host_candidate"),
                base_row.get("host_candidate_source"),
            ),
        ]

        for field_name, skyportal_value, skyportal_value_source in field_specs:
            if field_name == "counterpart":
                counterpart_bundle = build_counterpart_review_bundle(source_claims)
                if counterpart_bundle is None:
                    continue
                gcn_candidate_value = counterpart_bundle["gcn_candidate_value"]
                gcn_candidate_context = counterpart_bundle["gcn_candidate_context"]
                circular_id = counterpart_bundle["circular_id"]
                evidence_text = counterpart_bundle["evidence_text"]
            else:
                claim = pick_best_claim_for_field(source_claims, field_name=field_name)
                if claim is None:
                    continue
                gcn_candidate_value, gcn_candidate_context = build_candidate_value_and_context(
                    field_name,
                    claim,
                )
                circular_id = format_review_value(claim.get("circular_id"))
                evidence_text = format_review_value(claim.get("evidence_text"))

            comparison_status = comparison_status_for_row(
                field_name=field_name,
                skyportal_value=skyportal_value,
                gcn_candidate_value=gcn_candidate_value,
            )

            rows.append(
                {
                    "source_id": source_id,
                    "groups": base_row.get("groups", ""),
                    "field_name": field_name,
                    "skyportal_value": format_review_value(skyportal_value),
                    "skyportal_value_source": format_review_value(skyportal_value_source),
                    "gcn_candidate_value": gcn_candidate_value,
                    "gcn_candidate_context": gcn_candidate_context,
                    "comparison_status": comparison_status,
                    "circular_id": circular_id,
                    "evidence_text": evidence_text,
                    "astronomer_decision": "pending",
                    "validated_value": "",
                    "astronomer_notes": "",
                }
            )

    dataframe = pd.DataFrame(rows, columns=EVENT_REVIEW_COLUMNS)
    if dataframe.empty:
        return dataframe

    dataframe["_comparison_rank"] = (
        dataframe["comparison_status"].map(COMPARISON_STATUS_ORDER).fillna(99)
    )
    dataframe["_field_rank"] = dataframe["field_name"].map(FIELD_ORDER).fillna(99)
    dataframe = dataframe.sort_values(
        by=["_comparison_rank", "_field_rank", "source_id", "circular_id"],
        kind="stable",
    ).drop(columns=["_comparison_rank", "_field_rank"]).reset_index(drop=True)
    return dataframe


def run_gcn_event_review_table_build(args: argparse.Namespace) -> None:
    """Build the final review table used for astronomer validation."""
    setup_console_logging()
    skyportal_baseline_path = resolve_project_path(args.skyportal_baseline_path)
    best_claims_path = resolve_project_path(args.best_claims_path)
    claims_path = resolve_project_path(args.claims_path)
    output_dir = ensure_output_dir(args.output_dir)

    selected_sources_rows = load_skyportal_event_rows(skyportal_baseline_path)
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
