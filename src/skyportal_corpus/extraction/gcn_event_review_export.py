"""Export a curated astronomer-facing Excel workbook from the review table."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd

from ..core import resolve_project_path
from .gcn_event_matching import ensure_output_dir
from .gcn_event_review import (
    DEFAULT_GCN_EVENT_REVIEW_OUTPUT_DIR,
    EVENT_REVIEW_COLUMNS,
    EVENT_REVIEW_TABLE_CSV,
)

DEFAULT_GCN_ASTRONOMER_REVIEW_OUTPUT_DIR = (
    f"{DEFAULT_GCN_EVENT_REVIEW_OUTPUT_DIR}/astronomer_review"
)
DEFAULT_GCN_ASTRONOMER_REVIEW_XLSX_PATH = (
    f"{DEFAULT_GCN_ASTRONOMER_REVIEW_OUTPUT_DIR}/gcn_event_review_for_astronomer_high.xlsx"
)
DEFAULT_GCN_EVENT_REVIEW_CSV_PATH = (
    f"{DEFAULT_GCN_EVENT_REVIEW_OUTPUT_DIR}/{EVENT_REVIEW_TABLE_CSV}"
)

REVIEW_HIGH_COLUMNS = [
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

REVIEW_HIGH_STATUS_ORDER = {
    "possible_conflict": 0,
    "missing_in_skyportal": 1,
    "complementary_context": 2,
    "gcn_only_context_flag": 3,
}

FIELD_ORDER = {
    "redshift": 0,
    "trigger_time": 1,
    "t90": 2,
    "duration_class": 3,
    "spectroscopy": 4,
    "counterpart": 5,
    "host_candidate": 6,
}

ALLOWED_FIELDS_BY_STATUS = {
    "complementary_context": {"t90", "counterpart"},
    "gcn_only_context_flag": {"counterpart", "host_candidate"},
}


def setup_console_logging() -> None:
    """Configure simple console logging for one run."""
    logging.basicConfig(level=logging.INFO, format="%(message)s", force=True)


def require_openpyxl() -> None:
    """Fail early with a clear message when the Excel writer is unavailable."""
    try:
        import openpyxl  # noqa: F401
    except ImportError as error:  # pragma: no cover - exercised only without dependency
        raise RuntimeError(
            "openpyxl is required to export the astronomer review workbook. "
            "Install project dependencies so pandas can write .xlsx files."
        ) from error


def validate_review_dataframe(review_dataframe: pd.DataFrame) -> None:
    """Check that the canonical review table exposes the expected columns."""
    required_columns = set(EVENT_REVIEW_COLUMNS)
    missing_columns = sorted(required_columns.difference(review_dataframe.columns))
    if missing_columns:
        raise ValueError(
            "The review table is missing required columns: "
            + ", ".join(missing_columns)
        )


def build_astronomer_review_dataframe(review_dataframe: pd.DataFrame) -> pd.DataFrame:
    """Filter and reorder the canonical review table for astronomer delivery."""
    validate_review_dataframe(review_dataframe)
    if review_dataframe.empty:
        return pd.DataFrame(columns=REVIEW_HIGH_COLUMNS)

    statuses = review_dataframe["comparison_status"].astype(str)
    fields = review_dataframe["field_name"].astype(str)

    include_mask = (
        statuses.eq("possible_conflict")
        | statuses.eq("missing_in_skyportal")
        | (
            statuses.eq("complementary_context")
            & fields.isin(ALLOWED_FIELDS_BY_STATUS["complementary_context"])
        )
        | (
            statuses.eq("gcn_only_context_flag")
            & fields.isin(ALLOWED_FIELDS_BY_STATUS["gcn_only_context_flag"])
        )
    )

    filtered = review_dataframe.loc[include_mask, REVIEW_HIGH_COLUMNS].copy()
    if filtered.empty:
        return filtered

    filtered["_status_rank"] = (
        filtered["comparison_status"].map(REVIEW_HIGH_STATUS_ORDER).fillna(99)
    )
    filtered["_field_rank"] = filtered["field_name"].map(FIELD_ORDER).fillna(99)
    filtered = (
        filtered.sort_values(
            by=["_status_rank", "_field_rank", "source_id", "circular_id"],
            kind="stable",
        )
        .drop(columns=["_status_rank", "_field_rank"])
        .reset_index(drop=True)
    )
    return filtered


def build_legend_dataframe() -> pd.DataFrame:
    """Build the second worksheet that explains the curated export."""
    lines = [
        "Astronomer Review Legend",
        "",
        "This workbook is a curated subset of the full review table.",
        "It intentionally excludes same_or_consistent rows.",
        "",
        "Included comparison_status values:",
        "- possible_conflict: GCN and SkyPortal look inconsistent and need review.",
        "- missing_in_skyportal: GCN provides a value that SkyPortal does not have.",
        "- complementary_context: SkyPortal has partial context and GCN adds useful information.",
        "- gcn_only_context_flag: GCN adds contextual information not present in SkyPortal.",
        "",
        "Field-level export rules in this workbook:",
        "- complementary_context rows are kept only for t90 and counterpart.",
        "- gcn_only_context_flag rows are kept only for counterpart and host_candidate.",
        "",
        "Interpretation notes:",
        "- afterglow is reviewed under counterpart; it is not a separate field_name.",
        "- host_candidate is the operational review field for host-galaxy context.",
        "- circular_id and evidence_text may compact more than one GCN Circular for counterpart rows.",
    ]
    return pd.DataFrame({"Astronomer Review Legend": lines})


def write_astronomer_review_workbook(
    review_high_dataframe: pd.DataFrame,
    legend_dataframe: pd.DataFrame,
    output_path: Path,
) -> None:
    """Write the curated workbook with the review and legend sheets."""
    require_openpyxl()
    ensure_output_dir(output_path.parent)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        review_high_dataframe.to_excel(writer, sheet_name="review_high", index=False)
        legend_dataframe.to_excel(writer, sheet_name="legend", index=False)


def run_gcn_astronomer_review_xlsx_export(args: argparse.Namespace) -> None:
    """Export the curated astronomer-facing review workbook."""
    setup_console_logging()
    review_table_path = resolve_project_path(args.review_table_path)
    output_path = resolve_project_path(args.output_path)

    review_dataframe = pd.read_csv(review_table_path)
    review_high_dataframe = build_astronomer_review_dataframe(review_dataframe)
    legend_dataframe = build_legend_dataframe()
    write_astronomer_review_workbook(
        review_high_dataframe,
        legend_dataframe,
        output_path,
    )

    logging.info("Input review rows: %s", len(review_dataframe))
    logging.info("Exported workbook rows: %s", len(review_high_dataframe))
    if not review_high_dataframe.empty:
        logging.info(
            "Statuses exported: %s",
            review_high_dataframe["comparison_status"].value_counts().to_dict(),
        )
        logging.info(
            "Fields exported: %s",
            review_high_dataframe["field_name"].value_counts().to_dict(),
        )
    logging.info("Wrote workbook: %s", output_path)
