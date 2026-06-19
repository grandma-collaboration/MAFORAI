"""Helpers for building the SkyPortal-side baseline before GCN comparison."""

from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path
from typing import Any

import pandas as pd

from ..core import resolve_project_path
from .gcn_core_claims import (
    DETECTION_VALUES,
    NON_DETECTION_VALUES,
    extract_claims_from_text,
    parse_float_or_none,
)
from .gcn_event_matching import parse_list_like
from .source_selection import DEFAULT_GCN_GRANDMA_OUTPUT

DEFAULT_SKYPORTAL_EVENT_BASELINE_OUTPUT_DIR = "data/interim/skyportal"
DEFAULT_SKYPORTAL_EVENT_BASELINE_INPUT_PATH = DEFAULT_GCN_GRANDMA_OUTPUT
SKYPORTAL_BASELINE_CSV = "skyportal_event_baseline.csv"
SKYPORTAL_BASELINE_PARQUET = "skyportal_event_baseline.parquet"
DEFAULT_SKYPORTAL_EVENT_BASELINE_CSV_PATH = (
    f"{DEFAULT_SKYPORTAL_EVENT_BASELINE_OUTPUT_DIR}/{SKYPORTAL_BASELINE_CSV}"
)
DEFAULT_SKYPORTAL_EVENT_BASELINE_PARQUET_PATH = (
    f"{DEFAULT_SKYPORTAL_EVENT_BASELINE_OUTPUT_DIR}/{SKYPORTAL_BASELINE_PARQUET}"
)

SKYPORTAL_BASELINE_COLUMNS = [
    "source_id",
    "groups",
    "gcn_source_type",
    "native_redshift",
    "native_trigger_time",
    "native_spectrum_exists",
    "native_has_host",
    "native_comment_exists",
    "native_num_det_global",
    "native_classification_labels",
    "has_source_summary",
    "summary_claim_types_found",
    "summary_redshift_values",
    "summary_trigger_time_values",
    "summary_t90_values",
    "summary_duration_classes",
    "summary_counterpart_types",
    "summary_has_detection",
    "summary_has_non_detection",
    "summary_has_upper_limit",
    "summary_has_spectroscopy",
    "summary_has_host_candidate",
    "summary_classification_flags",
    "summary_instruments_found",
    "tag_temporal_classes",
    "tag_counterpart_contexts",
    "tag_instrument_contexts",
    "tag_followup_contexts",
    "tag_classification_contexts",
    "baseline_redshift_values",
    "baseline_trigger_time_values",
    "baseline_t90_values",
    "baseline_duration_classes",
    "baseline_counterpart_contexts",
    "baseline_classification_flags",
    "baseline_instrument_contexts",
    "baseline_followup_contexts",
    "baseline_has_redshift",
    "baseline_has_trigger_time",
    "baseline_has_t90",
    "baseline_has_duration_class",
    "baseline_has_counterpart",
    "baseline_has_detection",
    "baseline_has_non_detection",
    "baseline_has_upper_limit",
    "baseline_has_spectroscopy",
    "baseline_has_host_candidate",
    "baseline_has_classification",
]

SUMMARY_CONTEXT_CLAIM_TYPES = {
    "redshift",
    "trigger_time_t0",
    "duration_t90",
    "duration_class",
    "counterpart_type",
    "detection_status",
    "upper_limit_simple",
    "spectroscopy_mention",
    "host_candidate_mention",
    "classification_or_interpretation",
    "instrument_mention",
}
TEMPORAL_TAG_MAP = {
    "longgrb": "long",
    "shortgrb": "short",
    "ultralong": "ultralong",
}
COUNTERPART_TAG_MAP = {
    "optical": "optical",
    "nooptical": "no_optical",
    "lat": "lat",
}
INSTRUMENT_TAG_MAP = {
    "swift": "swift",
    "fermi": "fermi",
    "svom": "svom",
    "ep": "ep",
    "integral": "integral",
}
FOLLOWUP_TAG_MAP = {
    "followup": "followup",
    "nofollowup": "no_followup",
}
CLASSIFICATION_TAG_MAP = {
    "supernova": "supernova",
    "cv": "cv",
    "gwcandidate": "gw_candidate",
    "bbh": "bbh",
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
    """Load one supported SkyPortal-side input artifact."""
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


def parse_compact_values(value: object) -> list[str]:
    """Parse one compact list-like field into plain string values."""
    if isinstance(value, list):
        values: list[str] = []
        for item in value:
            if isinstance(item, str):
                text = item.strip()
                if text:
                    values.append(text)
        return values

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("[") and text.endswith("]"):
            return parse_list_like(text)
        return [item.strip() for item in text.split(";") if item.strip()]

    if isinstance(value, bool):
        return []

    if isinstance(value, (int, float)) and not is_missing_value(value):
        return [str(value)]

    return []


def collect_unique_values(*values: object) -> list[str]:
    """Collect ordered unique compact values across many fields."""
    ordered: list[str] = []
    for value in values:
        for item in parse_compact_values(value):
            if item not in ordered:
                ordered.append(item)
    return ordered


def claim_value_text(claim_row: dict[str, Any]) -> str:
    """Return the most useful display value for one claim row."""
    normalized_value = str(claim_row.get("normalized_value") or "").strip()
    if normalized_value:
        return normalized_value
    return str(claim_row.get("raw_value") or "").strip()


def normalize_tag_key(tag_name: str) -> str:
    """Build one compact key for allowed SkyPortal tag mappings."""
    return re.sub(r"[\s_-]+", "", tag_name.strip().lower())


def normalize_event_tags(tags: object) -> dict[str, str]:
    """Normalize only the approved semantic SkyPortal tag families."""
    temporal_classes: list[str] = []
    counterpart_contexts: list[str] = []
    instrument_contexts: list[str] = []
    followup_contexts: list[str] = []
    classification_contexts: list[str] = []

    for raw_tag in parse_compact_values(tags):
        normalized_key = normalize_tag_key(raw_tag)

        if normalized_key in TEMPORAL_TAG_MAP:
            value = TEMPORAL_TAG_MAP[normalized_key]
            if value not in temporal_classes:
                temporal_classes.append(value)
            continue

        if normalized_key in COUNTERPART_TAG_MAP:
            value = COUNTERPART_TAG_MAP[normalized_key]
            if value not in counterpart_contexts:
                counterpart_contexts.append(value)
            continue

        if normalized_key in INSTRUMENT_TAG_MAP:
            value = INSTRUMENT_TAG_MAP[normalized_key]
            if value not in instrument_contexts:
                instrument_contexts.append(value)
            continue

        if normalized_key in FOLLOWUP_TAG_MAP:
            value = FOLLOWUP_TAG_MAP[normalized_key]
            if value not in followup_contexts:
                followup_contexts.append(value)
            continue

        if normalized_key in CLASSIFICATION_TAG_MAP:
            value = CLASSIFICATION_TAG_MAP[normalized_key]
            if value not in classification_contexts:
                classification_contexts.append(value)

    return {
        "tag_temporal_classes": unique_join(temporal_classes),
        "tag_counterpart_contexts": unique_join(counterpart_contexts),
        "tag_instrument_contexts": unique_join(instrument_contexts),
        "tag_followup_contexts": unique_join(followup_contexts),
        "tag_classification_contexts": unique_join(classification_contexts),
    }


def build_summary_claim_association(source_id: str) -> dict[str, Any]:
    """Build one synthetic association mapping for source-summary extraction."""
    return {
        "source_id": source_id,
        "circular_id": "skyportal_summary",
        "year": 0,
        "created_at_iso": "",
        "subject": f"{source_id} source_summary",
        "raw_file_path": "",
        "best_match_score": 0,
        "best_confidence_level": "skyportal_summary",
    }


def extract_summary_claim_rows(source_id: str, summary_text: object) -> list[dict[str, Any]]:
    """Reuse the GCN claim extractor directly on one SkyPortal source summary."""
    if not isinstance(summary_text, str) or not summary_text.strip():
        return []

    association = build_summary_claim_association(source_id)
    return [
        row
        for row in extract_claims_from_text(
            association,
            summary_text.strip(),
            source_field="body",
        )
        if str(row.get("claim_type")) in SUMMARY_CONTEXT_CLAIM_TYPES
    ]


def summarize_source_summary_claims(
    source_id: str,
    summary_text: object,
) -> dict[str, Any]:
    """Extract and aggregate the compact claim view from source_summary."""
    summary_claim_rows = extract_summary_claim_rows(source_id, summary_text)
    detection_values = {
        str(row.get("normalized_value"))
        for row in summary_claim_rows
        if str(row.get("claim_type")) == "detection_status"
        and not is_missing_value(row.get("normalized_value"))
    }

    return {
        "has_source_summary": isinstance(summary_text, str) and bool(summary_text.strip()),
        "summary_claim_types_found": unique_join(
            [row.get("claim_type", "") for row in summary_claim_rows]
        ),
        "summary_redshift_values": unique_join(
            [
                claim_value_text(row)
                for row in summary_claim_rows
                if str(row.get("claim_type")) == "redshift"
            ]
        ),
        "summary_trigger_time_values": unique_join(
            [
                claim_value_text(row)
                for row in summary_claim_rows
                if str(row.get("claim_type")) == "trigger_time_t0"
            ]
        ),
        "summary_t90_values": unique_join(
            [
                claim_value_text(row)
                for row in summary_claim_rows
                if str(row.get("claim_type")) == "duration_t90"
            ]
        ),
        "summary_duration_classes": unique_join(
            [
                claim_value_text(row)
                for row in summary_claim_rows
                if str(row.get("claim_type")) == "duration_class"
            ]
        ),
        "summary_counterpart_types": unique_join(
            [
                claim_value_text(row)
                for row in summary_claim_rows
                if str(row.get("claim_type")) == "counterpart_type"
            ]
        ),
        "summary_has_detection": bool(detection_values & DETECTION_VALUES),
        "summary_has_non_detection": bool(detection_values & NON_DETECTION_VALUES),
        "summary_has_upper_limit": bool(
            "upper_limit" in detection_values
            or any(
                str(row.get("claim_type")) == "upper_limit_simple"
                for row in summary_claim_rows
            )
        ),
        "summary_has_spectroscopy": any(
            str(row.get("claim_type")) == "spectroscopy_mention"
            for row in summary_claim_rows
        ),
        "summary_has_host_candidate": any(
            str(row.get("claim_type")) == "host_candidate_mention"
            for row in summary_claim_rows
        ),
        "summary_classification_flags": unique_join(
            [
                claim_value_text(row)
                for row in summary_claim_rows
                if str(row.get("claim_type")) == "classification_or_interpretation"
            ]
        ),
        "summary_instruments_found": unique_join(
            [
                claim_value_text(row)
                for row in summary_claim_rows
                if str(row.get("claim_type")) == "instrument_mention"
            ]
        ),
    }


def build_skyportal_event_baseline_row(event: dict[str, Any]) -> dict[str, Any] | None:
    """Build one compact SkyPortal baseline row from gcn_grandma.json."""
    source_id = str(event.get("source_id") or event.get("id") or "").strip()
    if not source_id:
        return None

    native_redshift = parse_float_or_none(event.get("redshift"))
    native_trigger_time = parse_float_or_none(event.get("trigger_time"))
    native_spectrum_exists = bool(
        event.get("spectrum_exists", event.get("has_spectra", False))
    )
    native_has_host = bool(event.get("has_host", False))
    native_comment_exists = bool(event.get("comment_exists", False))
    native_num_det_global = int(parse_float_or_none(event.get("num_det_global")) or 0)
    native_classification_labels = unique_join(
        parse_compact_values(event.get("classification_labels", []))
    )
    groups = unique_join(parse_compact_values(event.get("groups", [])))

    summary_row = summarize_source_summary_claims(
        source_id,
        event.get("source_summary") or event.get("summary"),
    )
    tags_row = normalize_event_tags(event.get("tags", []))

    baseline_redshift_values = unique_join(
        collect_unique_values(native_redshift, summary_row["summary_redshift_values"])
    )
    baseline_trigger_time_values = unique_join(
        collect_unique_values(native_trigger_time, summary_row["summary_trigger_time_values"])
    )
    baseline_t90_values = unique_join(
        collect_unique_values(summary_row["summary_t90_values"])
    )
    baseline_duration_classes = unique_join(
        collect_unique_values(
            summary_row["summary_duration_classes"],
            tags_row["tag_temporal_classes"],
        )
    )
    baseline_counterpart_contexts = unique_join(
        collect_unique_values(
            summary_row["summary_counterpart_types"],
            tags_row["tag_counterpart_contexts"],
        )
    )
    baseline_classification_flags = unique_join(
        collect_unique_values(
            native_classification_labels,
            summary_row["summary_classification_flags"],
            tags_row["tag_classification_contexts"],
        )
    )
    baseline_instrument_contexts = unique_join(
        collect_unique_values(
            summary_row["summary_instruments_found"],
            tags_row["tag_instrument_contexts"],
        )
    )
    baseline_followup_contexts = unique_join(
        collect_unique_values(tags_row["tag_followup_contexts"])
    )

    positive_counterpart_contexts = [
        value
        for value in collect_unique_values(baseline_counterpart_contexts)
        if value != "no_optical"
    ]

    return {
        "source_id": source_id,
        "groups": groups,
        "gcn_source_type": str(event.get("gcn_source_type") or ""),
        "native_redshift": native_redshift,
        "native_trigger_time": native_trigger_time,
        "native_spectrum_exists": native_spectrum_exists,
        "native_has_host": native_has_host,
        "native_comment_exists": native_comment_exists,
        "native_num_det_global": native_num_det_global,
        "native_classification_labels": native_classification_labels,
        **summary_row,
        **tags_row,
        "baseline_redshift_values": baseline_redshift_values,
        "baseline_trigger_time_values": baseline_trigger_time_values,
        "baseline_t90_values": baseline_t90_values,
        "baseline_duration_classes": baseline_duration_classes,
        "baseline_counterpart_contexts": baseline_counterpart_contexts,
        "baseline_classification_flags": baseline_classification_flags,
        "baseline_instrument_contexts": baseline_instrument_contexts,
        "baseline_followup_contexts": baseline_followup_contexts,
        "baseline_has_redshift": bool(collect_unique_values(baseline_redshift_values)),
        "baseline_has_trigger_time": bool(
            collect_unique_values(baseline_trigger_time_values)
        ),
        "baseline_has_t90": bool(collect_unique_values(baseline_t90_values)),
        "baseline_has_duration_class": bool(
            collect_unique_values(baseline_duration_classes)
        ),
        "baseline_has_counterpart": bool(positive_counterpart_contexts),
        "baseline_has_detection": bool(summary_row["summary_has_detection"]),
        "baseline_has_non_detection": bool(summary_row["summary_has_non_detection"]),
        "baseline_has_upper_limit": bool(summary_row["summary_has_upper_limit"]),
        "baseline_has_spectroscopy": bool(
            native_spectrum_exists or summary_row["summary_has_spectroscopy"]
        ),
        "baseline_has_host_candidate": bool(
            native_has_host or summary_row["summary_has_host_candidate"]
        ),
        "baseline_has_classification": bool(
            collect_unique_values(baseline_classification_flags)
        ),
    }


def build_skyportal_event_baseline_dataframe(
    selected_sources_rows: list[dict[str, Any]],
) -> pd.DataFrame:
    """Build the compact SkyPortal baseline used before final GCN comparison."""
    rows: list[dict[str, Any]] = []
    for event in selected_sources_rows:
        if not isinstance(event, dict):
            continue
        row = build_skyportal_event_baseline_row(event)
        if row is not None:
            rows.append(row)

    dataframe = pd.DataFrame(rows, columns=SKYPORTAL_BASELINE_COLUMNS)
    return dataframe.sort_values(by=["source_id"], kind="stable").reset_index(drop=True)


def ensure_output_dir(path_value: str | Path) -> Path:
    """Resolve and create one output directory."""
    output_dir = resolve_project_path(path_value)
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def run_skyportal_event_baseline_build(args: argparse.Namespace) -> None:
    """Build the compact SkyPortal-side baseline from gcn_grandma.json."""
    setup_console_logging()
    selected_sources_path = resolve_project_path(args.selected_sources)
    output_dir = ensure_output_dir(args.output_dir)

    selected_sources_rows = load_skyportal_event_rows(selected_sources_path)
    baseline_dataframe = build_skyportal_event_baseline_dataframe(selected_sources_rows)

    csv_path = output_dir / SKYPORTAL_BASELINE_CSV
    parquet_path = output_dir / SKYPORTAL_BASELINE_PARQUET
    baseline_dataframe.to_csv(csv_path, index=False)
    baseline_dataframe.to_parquet(parquet_path, index=False)

    logging.info("SkyPortal events loaded: %s", len(selected_sources_rows))
    logging.info("Baseline rows written: %s", len(baseline_dataframe))
    logging.info(
        "Rows with source_summary: %s",
        int(baseline_dataframe["has_source_summary"].sum()) if not baseline_dataframe.empty else 0,
    )
    if not baseline_dataframe.empty:
        tag_contexts = (
            baseline_dataframe[
                [
                    "tag_temporal_classes",
                    "tag_counterpart_contexts",
                    "tag_instrument_contexts",
                    "tag_followup_contexts",
                    "tag_classification_contexts",
                ]
            ]
            .fillna("")
            .astype(str)
            .agg("".join, axis=1)
            .str.len()
            .gt(0)
            .sum()
        )
    else:
        tag_contexts = 0
    logging.info("Rows with normalized tag context: %s", int(tag_contexts))
    logging.info("Wrote CSV: %s", csv_path)
    logging.info("Wrote Parquet: %s", parquet_path)
