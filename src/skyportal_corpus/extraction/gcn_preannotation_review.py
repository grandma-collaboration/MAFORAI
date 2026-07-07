"""Build a human-review table for one pilot INCEpTION preannotation event."""

from __future__ import annotations

import argparse
import logging
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from ..core import resolve_project_path
from .gcn_inception_dossiers import load_body_from_raw_json, normalize_newlines
from .gcn_preannotation_candidates import (
    DEFAULT_GCN_PREANNOTATION_CANDIDATES_PARQUET_PATH,
    QUALITY_FLAG_AMBIGUOUS,
    QUALITY_FLAG_MISMATCH,
    QUALITY_FLAG_OFFSET_NOT_FOUND,
    setup_console_logging,
)

DEFAULT_GCN_PREANNOTATION_PILOT_OUTPUT_DIR = "data/interim/gcn/preannotations/pilot"
DEFAULT_GCN_PREANNOTATION_PILOT_SOURCE_ID = "2026owq"

PILOT_REVIEW_COLUMNS = [
    "row_id",
    "source_id",
    "document_name",
    "circular_id",
    "subject",
    "created_on",
    "claim_type",
    "evidence_text",
    "value",
    "unit",
    "claim_confidence",
    "extraction_rule",
    "inception_layer",
    "inception_label",
    "measurement_type",
    "target",
    "certainty",
    "dossier_begin_offset",
    "dossier_end_offset",
    "body_begin_offset",
    "body_end_offset",
    "offset_valid",
    "offset_scope",
    "preannotation_status",
    "ready_for_preannotation",
    "ready_for_candidate_review",
    "ready_for_inception_preannotation",
    "needs_llm_verification",
    "needs_human_review",
    "risk_level",
    "risk_reason",
    "recommended_action",
    "quality_flags",
    "context_before",
    "context_after",
    "evidence_with_context",
    "review_decision",
    "reviewer_notes",
    "identity_warning",
    "manual_priority",
]

REVIEW_DECISION_VALUES = ["accept", "reject", "needs_fix", "needs_llm", "unsure"]

MANUAL_PRIORITY_ORDER = {
    "1_high_priority_ready": 1,
    "2_review_scientific_candidate": 2,
    "3_needs_llm_or_context": 3,
    "4_offset_or_mapping_issue": 4,
    "5_identity_warning": 5,
}

CLAIM_TYPE_ORDER = {
    "trigger_time_t0": 1,
    "duration_t90": 2,
    "spectroscopy_mention": 3,
    "counterpart_type": 4,
    "host_candidate_mention": 5,
    "redshift": 6,
    "classification_or_interpretation": 7,
    "detection_status": 8,
    "instrument_mention": 9,
    "duration_class": 10,
    "upper_limit_simple": 11,
}

IDENTITY_WARNING_VALUE = "possible_event_identity_or_matching_conflict"
IDENTITY_CONFLICT_FLAG = "event_identity_conflict_260610A_vs_260610B"


def load_preannotation_candidates(path_value: str | Path) -> pd.DataFrame:
    """Load pilot candidates from parquet or CSV."""
    path = resolve_project_path(path_value)
    if not path.exists():
        raise FileNotFoundError(f"Preannotation candidates path not found: {path}")

    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    if path.suffix == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"Unsupported preannotation candidates path: {path}")


def load_dossier_text(path_value: str | Path, cache: dict[str, str]) -> str:
    """Load one dossier text with a small cache."""
    path = resolve_project_path(path_value)
    key = str(path)
    if key in cache:
        return cache[key]
    if not path.exists():
        cache[key] = ""
        return ""
    text = normalize_newlines(path.read_text(encoding="utf-8"))
    cache[key] = text
    return text


def load_body_text(path_value: str | Path, cache: dict[str, str]) -> str:
    """Load one raw GCN body text with a small cache."""
    path = resolve_project_path(path_value)
    key = str(path)
    if key in cache:
        return cache[key]
    text = load_body_from_raw_json(path)
    cache[key] = text
    return text


def as_bool(value: object) -> bool:
    """Convert current table booleans and yes/no labels into bool."""
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"true", "1", "yes", "y"}


def parse_offset(value: object) -> int | None:
    """Parse one numeric offset field coming from CSV/parquet."""
    if value is None or pd.isna(value):
        return None
    return int(value)


def normalize_context_fragment(text: str) -> str:
    """Make context easier to read in CSV without changing the selected evidence."""
    return " ".join(normalize_newlines(text).split())


def validate_span(text: str, begin: int | None, end: int | None, evidence_text: str) -> bool:
    """Validate that one candidate offset still points to the expected evidence text."""
    if begin is None or end is None:
        return False
    if begin < 0 or end < begin or end > len(text):
        return False
    return text[begin:end] == evidence_text


def build_context_fields(
    *,
    text: str,
    begin: int,
    end: int,
    radius: int = 150,
) -> tuple[str, str, str]:
    """Build the before/after snippets and the marked evidence context."""
    context_before = text[max(0, begin - radius) : begin]
    evidence_text = text[begin:end]
    context_after = text[end : min(len(text), end + radius)]
    return (
        normalize_context_fragment(context_before),
        normalize_context_fragment(context_after),
        normalize_context_fragment(f"{context_before}[[{evidence_text}]]{context_after}"),
    )


def subject_has_identity_conflict(subject: str) -> bool:
    """Return whether one subject shows the known 260610A vs 260610B conflict."""
    return bool(re.search(r"\bGRB\s*260610A\b", str(subject or ""), re.IGNORECASE))


def choose_context_source(
    row: pd.Series,
    *,
    dossier_cache: dict[str, str],
    body_cache: dict[str, str],
) -> tuple[str, str, bool, list[str]]:
    """Choose the best available context source and validate its offsets."""
    evidence_text = str(row.get("evidence_text") or "")
    quality_flags = {
        flag for flag in str(row.get("quality_flags") or "").split(";") if flag
    }

    dossier_path = str(row.get("dossier_path") or "").strip()
    dossier_begin = parse_offset(row.get("dossier_begin_offset"))
    dossier_end = parse_offset(row.get("dossier_end_offset"))
    if dossier_path:
        dossier_text = load_dossier_text(dossier_path, dossier_cache)
        if dossier_text and validate_span(dossier_text, dossier_begin, dossier_end, evidence_text):
            return "dossier", dossier_text, True, sorted(quality_flags)
        if dossier_begin is not None or dossier_end is not None:
            quality_flags.add(QUALITY_FLAG_MISMATCH)

    raw_file_path = str(row.get("raw_file_path") or "").strip()
    body_begin = parse_offset(row.get("body_begin_offset"))
    body_end = parse_offset(row.get("body_end_offset"))
    if raw_file_path:
        body_text = load_body_text(raw_file_path, body_cache)
        if body_text and validate_span(body_text, body_begin, body_end, evidence_text):
            return "body", body_text, True, sorted(quality_flags)
        if body_begin is not None or body_end is not None:
            quality_flags.add(QUALITY_FLAG_MISMATCH)

    subject = normalize_newlines(str(row.get("subject") or ""))
    subject_begin = parse_offset(row.get("subject_begin_offset"))
    subject_end = parse_offset(row.get("subject_end_offset"))
    if subject and validate_span(subject, subject_begin, subject_end, evidence_text):
        return "subject", subject, True, sorted(quality_flags)
    if subject_begin is not None or subject_end is not None:
        quality_flags.add(QUALITY_FLAG_MISMATCH)

    if QUALITY_FLAG_OFFSET_NOT_FOUND not in quality_flags:
        quality_flags.add(QUALITY_FLAG_OFFSET_NOT_FOUND)
    return "none", "", False, sorted(quality_flags)


def determine_manual_priority(row: dict[str, Any]) -> str:
    """Assign a compact manual-review priority bucket."""
    if row["identity_warning"]:
        return "5_identity_warning"
    if not row["offset_valid"] or row["offset_scope"] == "none":
        return "4_offset_or_mapping_issue"
    if row["preannotation_status"] in {
        "not_ready_no_offsets",
        "not_ready_ambiguous_offsets",
        "not_mapped",
    } or QUALITY_FLAG_MISMATCH in row["quality_flags"].split(";"):
        return "4_offset_or_mapping_issue"
    if row["claim_type"] in {
        "redshift",
        "classification_or_interpretation",
        "detection_status",
    }:
        return "3_needs_llm_or_context"
    if row["inception_label"] in {
        "SPECTROSCOPY",
        "COUNTERPART_ASSOCIATION",
        "HOST_CONTEXT",
        "LIGHTCURVE_EVOLUTION",
    }:
        return "2_review_scientific_candidate"
    if row["inception_label"] in {"TRIGGER_TIME", "T90"} and row["offset_valid"]:
        return "1_high_priority_ready"
    return "4_offset_or_mapping_issue"


def build_row_id(review_rows: list[dict[str, Any]]) -> None:
    """Assign a stable, readable row_id after sorting."""
    counters: defaultdict[tuple[str, str], int] = defaultdict(int)
    for row in review_rows:
        key = (str(row["circular_id"]), str(row["claim_type"]))
        counters[key] += 1
        row["row_id"] = (
            f"{row['source_id']}__{row['circular_id']}__{row['claim_type']}__{counters[key]:02d}"
        )


def build_review_row(
    row: pd.Series,
    *,
    dossier_cache: dict[str, str],
    body_cache: dict[str, str],
) -> dict[str, Any]:
    """Build one human-review row from one preannotation candidate row."""
    offset_scope, context_text, offset_valid, quality_flags = choose_context_source(
        row,
        dossier_cache=dossier_cache,
        body_cache=body_cache,
    )

    context_before = ""
    context_after = ""
    evidence_with_context = ""
    evidence_text = str(row.get("evidence_text") or "")

    if offset_valid and offset_scope == "dossier":
        begin = parse_offset(row.get("dossier_begin_offset"))
        end = parse_offset(row.get("dossier_end_offset"))
        context_before, context_after, evidence_with_context = build_context_fields(
            text=context_text,
            begin=begin,
            end=end,
        )
    elif offset_valid and offset_scope == "body":
        begin = parse_offset(row.get("body_begin_offset"))
        end = parse_offset(row.get("body_end_offset"))
        context_before, context_after, evidence_with_context = build_context_fields(
            text=context_text,
            begin=begin,
            end=end,
        )
    elif offset_valid and offset_scope == "subject":
        begin = parse_offset(row.get("subject_begin_offset"))
        end = parse_offset(row.get("subject_end_offset"))
        context_before, context_after, evidence_with_context = build_context_fields(
            text=context_text,
            begin=begin,
            end=end,
        )

    needs_llm = as_bool(row.get("needs_llm_verification"))
    needs_human = as_bool(row.get("needs_human_review"))
    ready_for_preannotation = as_bool(row.get("can_preannotate")) and not needs_llm
    preannotation_status = str(row.get("preannotation_status") or "")
    identity_warning = ""
    quality_flag_set = {flag for flag in quality_flags if flag}

    if str(row.get("circular_id") or "") == "44891" or subject_has_identity_conflict(
        str(row.get("subject") or "")
    ):
        identity_warning = IDENTITY_WARNING_VALUE
        needs_human = True
        ready_for_preannotation = False
        preannotation_status = "needs_human_review_identity_conflict"
        quality_flag_set.add(IDENTITY_CONFLICT_FLAG)

    ready_for_inception_preannotation = (
        preannotation_status == "ready_for_preannotation"
        and offset_valid
        and offset_scope == "dossier"
        and not identity_warning
    )

    risk_level = str(row.get("risk_level") or "")
    recommended_action = str(row.get("recommended_action") or "")
    if identity_warning:
        risk_level = "high"
        recommended_action = "verify_event_identity_before_preannotation"

    review_row = {
        "row_id": "",
        "source_id": str(row.get("source_id") or ""),
        "document_name": str(row.get("document_name") or ""),
        "circular_id": str(row.get("circular_id") or ""),
        "subject": str(row.get("subject") or ""),
        "created_on": str(row.get("created_at_iso") or ""),
        "claim_type": str(row.get("claim_type") or ""),
        "evidence_text": evidence_text,
        "value": str(row.get("value") or ""),
        "unit": str(row.get("unit") or ""),
        "claim_confidence": str(row.get("claim_confidence") or ""),
        "extraction_rule": str(row.get("extraction_rule") or ""),
        "inception_layer": str(row.get("inception_layer") or ""),
        "inception_label": str(row.get("inception_label") or ""),
        "measurement_type": str(row.get("measurement_type") or ""),
        "target": str(row.get("target") or ""),
        "certainty": str(row.get("certainty") or ""),
        "dossier_begin_offset": parse_offset(row.get("dossier_begin_offset")),
        "dossier_end_offset": parse_offset(row.get("dossier_end_offset")),
        "body_begin_offset": parse_offset(row.get("body_begin_offset")),
        "body_end_offset": parse_offset(row.get("body_end_offset")),
        "offset_valid": offset_valid,
        "offset_scope": offset_scope,
        "preannotation_status": preannotation_status,
        "ready_for_preannotation": ready_for_preannotation,
        "ready_for_candidate_review": True,
        "ready_for_inception_preannotation": ready_for_inception_preannotation,
        "needs_llm_verification": needs_llm,
        "needs_human_review": needs_human,
        "risk_level": risk_level,
        "risk_reason": str(row.get("risk_reason") or ""),
        "recommended_action": recommended_action,
        "quality_flags": ";".join(sorted(quality_flag_set)),
        "context_before": context_before,
        "context_after": context_after,
        "evidence_with_context": evidence_with_context,
        "review_decision": "",
        "reviewer_notes": "",
        "identity_warning": identity_warning,
        "manual_priority": "",
    }
    review_row["manual_priority"] = determine_manual_priority(review_row)
    return review_row


def build_pilot_review_table(
    candidates_dataframe: pd.DataFrame,
    *,
    source_id: str,
) -> pd.DataFrame:
    """Build the pilot review table for one event."""
    filtered = candidates_dataframe[
        candidates_dataframe["source_id"].astype(str) == source_id
    ].copy()
    if filtered.empty:
        raise ValueError(f"No preannotation candidates found for source_id: {source_id}")

    dossier_cache: dict[str, str] = {}
    body_cache: dict[str, str] = {}
    review_rows = [
        build_review_row(row, dossier_cache=dossier_cache, body_cache=body_cache)
        for _, row in filtered.iterrows()
    ]

    review_rows.sort(
        key=lambda item: (
            MANUAL_PRIORITY_ORDER.get(item["manual_priority"], 99),
            str(item["circular_id"]),
            CLAIM_TYPE_ORDER.get(item["claim_type"], 99),
            item["claim_type"],
        )
    )
    build_row_id(review_rows)
    return pd.DataFrame(review_rows, columns=PILOT_REVIEW_COLUMNS)


def write_review_report(
    dataframe: pd.DataFrame,
    *,
    source_id: str,
    output_path: Path,
) -> None:
    """Write the Markdown report for the pilot review table."""
    claim_counts = dataframe["claim_type"].value_counts().sort_values(ascending=False)
    status_counts = dataframe["preannotation_status"].value_counts().sort_values(ascending=False)
    priority_counts = dataframe["manual_priority"].value_counts().sort_values(ascending=False)
    identity_rows = dataframe[dataframe["identity_warning"] != ""]

    lines = [
        f"# Pilot Review Report: {source_id}",
        "",
        "## Summary",
        "",
        f"- Total rows: {len(dataframe)}",
        f"- Identity warning rows: {len(identity_rows)}",
        f"- Rows with valid dossier offsets: {int(((dataframe['offset_scope'] == 'dossier') & (dataframe['offset_valid'])).sum())}",
        f"- Rows without valid offsets: {int((~dataframe['offset_valid']).sum())}",
        f"- Rows needs_llm_verification: {int(dataframe['needs_llm_verification'].sum())}",
        f"- Rows ready_for_inception_preannotation: {int(dataframe['ready_for_inception_preannotation'].sum())}",
        "",
        "## Counts by Claim Type",
        "",
    ]
    for claim_type, count in claim_counts.items():
        lines.append(f"- `{claim_type}`: {int(count)}")

    lines.extend(["", "## Counts by Preannotation Status", ""])
    for status, count in status_counts.items():
        lines.append(f"- `{status}`: {int(count)}")

    lines.extend(["", "## Counts by Manual Priority", ""])
    for priority, count in priority_counts.items():
        lines.append(f"- `{priority}`: {int(count)}")

    lines.extend(["", "## Rows Affected by Circular 44891 / GRB 260610A", ""])
    if identity_rows.empty:
        lines.append("- none")
    else:
        for _, row in identity_rows.iterrows():
            lines.append(
                f"- `{row['row_id']}` | circular `{row['circular_id']}` | "
                f"{row['claim_type']} | status=`{row['preannotation_status']}` | "
                f"subject=`{row['subject']}`"
            )

    lines.extend(
        [
            "",
            "## Manual Review Instructions",
            "",
            "1. Revisar primero las filas `1_high_priority_ready`, especialmente TRIGGER_TIME y T90.",
            "2. Verificar manualmente que el span marcado en `evidence_with_context` corresponde a la anotación esperada.",
            "3. No aceptar automáticamente redshift, detection_status ni classification_or_interpretation; esos deben ir a revisión contextual o LLM.",
            "4. Revisar todas las filas con `identity_warning` antes de cualquier preanotación.",
            "5. No usar filas sin dossier offsets válidos para UIMA CAS / INCEpTION preannotation.",
            "",
            "## Reviewer Fields",
            "",
            "- `review_decision`: keep empty by default. Suggested values for manual use: "
            + ", ".join(f"`{value}`" for value in REVIEW_DECISION_VALUES),
            "- `reviewer_notes`: keep empty by default and fill only during manual review.",
        ]
    )

    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def run_gcn_pilot_review_table_build(args: argparse.Namespace) -> None:
    """Build the human-review table for one pilot event."""
    setup_console_logging()

    candidates = load_preannotation_candidates(args.candidates_path)
    review_table = build_pilot_review_table(candidates, source_id=args.source_id)

    output_dir = resolve_project_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_path = output_dir / f"{args.source_id}_review_table.csv"
    report_path = output_dir / f"{args.source_id}_review_report.md"

    review_table.to_csv(csv_path, index=False)
    write_review_report(review_table, source_id=args.source_id, output_path=report_path)

    logging.info("CSV: %s", csv_path)
    logging.info("Total rows: %s", len(review_table))
    logging.info(
        "ready_for_inception_preannotation: %s",
        int(review_table["ready_for_inception_preannotation"].sum()),
    )
    logging.info(
        "needs_llm_verification: %s",
        int(review_table["needs_llm_verification"].sum()),
    )
    logging.info(
        "identity_warning count: %s",
        int((review_table["identity_warning"] != "").sum()),
    )
    logging.info(
        "rows with valid dossier offsets: %s",
        int(((review_table["offset_scope"] == "dossier") & (review_table["offset_valid"])).sum()),
    )
    logging.info(
        "rows without valid offsets: %s",
        int((~review_table["offset_valid"]).sum()),
    )
