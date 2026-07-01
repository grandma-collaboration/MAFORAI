"""Build blind plain-text dossiers for pilot annotation in INCEpTION."""

from __future__ import annotations

import argparse
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from ..core import resolve_project_path
from .gcn_event_matching import (
    DEFAULT_GCN_EVENT_MATCHING_ASSOCIATIONS_PATH,
    DEFAULT_GCN_EVENT_MATCHING_SELECTED_SOURCES_PATH,
    ensure_output_dir,
    load_json_object,
)

DEFAULT_GCN_INCEPTION_DOSSIERS_OUTPUT_DIR = (
    "data/interim/gcn/event_validation/inception_dossiers"
)

DEFAULT_GCN_INCEPTION_CIRCULARS_ROOT = "data/interim/gcn/circulars"

DOSSIER_SUFFIX = "_inception_dossier.txt"
MANIFEST_SUFFIX = "_inception_dossier_manifest.json"

CONFIDENCE_ORDER = {
    "high_confidence": 0,
    "medium_confidence": 1,
    "low_confidence": 2,
}

DOSSIER_INTRO = """EVENT DOSSIER — PILOT ANNOTATION
=================================

EVENT:
{title}

SOURCE_ID:
{source_id}

ALIASES:
{aliases_block}

PURPOSE OF THIS DOCUMENT:
This dossier is for pilot annotation in INCEpTION.
The annotator should select scientifically useful evidence in the text using the ASTRO_EVIDENCE layer, then fill the EVENT_SUMMARY document metadata.

IMPORTANT:
This is a blind scientific annotation dossier. It intentionally does not include automatic extraction results.
The goal is to let the astronomer independently select the useful information and indicate the best event-level values.

WHAT TO ANNOTATE:
- trigger time
- trigger instrument
- localization / coordinates / uncertainty
- counterpart association
- photometric detections
- photometric upper limits
- photometry tables
- event redshift
- redshift context not necessarily associated with the event
- T90
- general duration
- spectroscopy
- high-energy properties
- host context
- classification / physical interpretation
- follow-up actions
- negative statements

WHAT NOT TO ANNOTATE:
- author lists
- affiliations
- acknowledgements
- generic telescope descriptions
- generic mission descriptions
- long lists of GCN references
- repeated event names unless they establish an alias or association
- institutional text unless it contains scientific information about the event

EVENT_SUMMARY FIELDS TO COMPLETE IN INCEpTION DOCUMENT METADATA:
- canonical_event_name
- main_counterpart_name
- best_trigger_time
- best_trigger_time_source
- best_redshift_value
- best_redshift_method
- best_redshift_source
- best_redshift_comment
- best_t90_value
- best_t90_instrument
- best_t90_energy_band
- best_t90_source
- best_t90_comment
- best_localization_value
- best_localization_source
- main_counterpart_status
- main_host_status
- main_classification
- main_interpretation
- negative_flags
- corpus_value
- review_priority
- astronomer_notes

ANNOTATION UNIT:
Select the smallest text span that contains the full scientific evidence.
For photometry tables, select the full table block instead of each individual cell.
For ambiguous values, add a short comment.
"""


def setup_console_logging() -> None:
    """Configure simple console logging for one run."""
    logging.basicConfig(level=logging.INFO, format="%(message)s", force=True)


def save_json(path: Path, data: Any) -> None:
    """Save JSON data to disk."""
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, default=str)


def normalize_newlines(text: str) -> str:
    """Normalize line endings without otherwise reshaping the text."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def safe_source_id(source_id: str) -> str:
    """Build a filesystem-safe source identifier."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", source_id.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("._")
    return cleaned or "event"


def load_selected_sources_lookup(path_value: str | Path) -> dict[str, dict[str, Any]]:
    """Load the selected-sources JSON and index it by source id."""
    payload = load_json_object(resolve_project_path(path_value))
    sources = payload.get("sources")
    if not isinstance(sources, list):
        sources = payload.get("selected_sources")
    if not isinstance(sources, list):
        raise ValueError(
            "Selected-sources payload must contain a 'sources' or 'selected_sources' list"
        )

    lookup: dict[str, dict[str, Any]] = {}
    for item in sources:
        if not isinstance(item, dict):
            continue
        source_id = str(item.get("id") or "").strip()
        if source_id:
            lookup[source_id] = item
    return lookup


def normalize_aliases(source_row: dict[str, Any] | None) -> list[str]:
    """Extract unique aliases from one source row."""
    if not isinstance(source_row, dict):
        return []

    raw_aliases = source_row.get("aliases", [])
    if not isinstance(raw_aliases, list):
        raw_aliases = source_row.get("selection_context", {}).get("aliases", [])
    if not isinstance(raw_aliases, list):
        return []

    aliases: list[str] = []
    for alias in raw_aliases:
        text = str(alias).strip()
        if text and text not in aliases:
            aliases.append(text)
    return aliases


def build_default_title(
    source_id: str,
    *,
    source_row: dict[str, Any] | None,
    explicit_title: str | None,
) -> str:
    """Build the dossier title."""
    if explicit_title is not None and explicit_title.strip():
        return explicit_title.strip()

    aliases = normalize_aliases(source_row)
    if aliases:
        primary_alias = aliases[0]
        if primary_alias != source_id:
            return f"{primary_alias} / {source_id}"
    return source_id


def load_associations_dataframe(path_value: str | Path) -> pd.DataFrame:
    """Load associations from parquet or CSV."""
    path = resolve_project_path(path_value)
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    if path.suffix == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"Unsupported associations path: {path}")


def choose_best_association_rows(source_rows: pd.DataFrame) -> pd.DataFrame:
    """Deduplicate one event's associations down to one best row per circular."""
    if source_rows.empty:
        return source_rows.copy()

    sortable = source_rows.copy()
    sortable["_score_rank"] = pd.to_numeric(
        sortable["best_match_score"],
        errors="coerce",
    ).fillna(-1)
    sortable["_confidence_rank"] = sortable["best_confidence_level"].map(
        lambda value: CONFIDENCE_ORDER.get(str(value), 99)
    )
    sortable["_created_at"] = sortable["created_at_iso"].fillna("").astype(str)
    sortable = sortable.sort_values(
        by=[
            "circular_id",
            "_score_rank",
            "_confidence_rank",
            "_created_at",
        ],
        ascending=[True, False, True, True],
        kind="stable",
    )
    best = sortable.drop_duplicates(subset=["circular_id"], keep="first").copy()
    return best.drop(
        columns=["_score_rank", "_confidence_rank", "_created_at"],
        errors="ignore",
    )


def circular_sort_key(row: pd.Series) -> tuple[int, str, int | str]:
    """Build the deterministic sort key for one circular row."""
    created_at = str(row.get("created_at_iso") or "").strip()
    missing_date = 0 if created_at else 1

    circular_id = str(row.get("circular_id") or "").strip()
    try:
        circular_sort_value: int | str = int(circular_id)
    except ValueError:
        circular_sort_value = circular_id

    return (missing_date, created_at, circular_sort_value)


def load_body_from_raw_json(raw_file_path: object) -> str:
    """Load the body text from the raw circular JSON path when available."""
    path_text = str(raw_file_path or "").strip()
    if not path_text:
        return ""

    path = Path(path_text)
    if not path.exists():
        return ""

    payload = load_json_object(path)
    body = payload.get("body")
    if isinstance(body, str):
        return normalize_newlines(body).strip()
    return ""


def load_body_from_index(
    *,
    circular_id: str,
    year: object,
    gcn_root: str | Path,
) -> str:
    """Fallback loader using the normalized year-partitioned GCN index."""
    if year is None or str(year).strip() == "":
        return ""

    year_text = str(year).strip()
    root = resolve_project_path(gcn_root)
    parquet_path = root / year_text / "circulars_index.parquet"
    csv_path = root / year_text / "circulars_index.csv"

    if parquet_path.exists():
        dataframe = pd.read_parquet(parquet_path)
    elif csv_path.exists():
        dataframe = pd.read_csv(csv_path)
    else:
        return ""

    matches = dataframe[dataframe["circular_id"].astype(str) == str(circular_id)]
    if matches.empty:
        return ""

    body = matches.iloc[0].get("body")
    if isinstance(body, str):
        return normalize_newlines(body).strip()
    return ""


def resolve_circular_body(row: pd.Series, *, gcn_root: str | Path) -> str:
    """Resolve the text body for one circular row with fallback."""
    body = load_body_from_raw_json(row.get("raw_file_path"))
    if body:
        return body

    body = load_body_from_index(
        circular_id=str(row.get("circular_id") or "").strip(),
        year=row.get("year"),
        gcn_root=gcn_root,
    )
    if body:
        return body

    return "[Body unavailable]"


def build_aliases_block(aliases: list[str]) -> str:
    """Render aliases as the dossier bullet list."""
    if not aliases:
        return "- none"
    return "\n".join(f"- {alias}" for alias in aliases)


def build_circular_section(row: pd.Series, *, body: str) -> str:
    """Render one circular section in the dossier."""
    circular_id = str(row.get("circular_id") or "").strip()
    created_at = str(row.get("created_at_iso") or "").strip() or "missing"
    subject = str(row.get("subject") or "").strip() or "(missing subject)"
    return (
        "================================================================================\n"
        f"CIRCULAR {circular_id}\n"
        f"CREATED_AT: {created_at}\n"
        f"SUBJECT: {subject}\n"
        "================================================================================\n\n"
        f"{body}\n"
    )


def build_inception_dossier_text(
    *,
    source_id: str,
    title: str,
    aliases: list[str],
    circular_rows: pd.DataFrame,
    gcn_root: str | Path,
) -> str:
    """Build the full blind plain-text dossier."""
    header = DOSSIER_INTRO.format(
        title=title,
        source_id=source_id,
        aliases_block=build_aliases_block(aliases),
    ).rstrip()

    sections: list[str] = [header]
    for _, row in circular_rows.iterrows():
        sections.append(
            build_circular_section(
                row,
                body=resolve_circular_body(row, gcn_root=gcn_root),
            )
        )

    return "\n\n".join(sections).rstrip() + "\n"


def build_manifest(
    *,
    source_id: str,
    title: str,
    circular_rows: pd.DataFrame,
    output_path: Path,
) -> dict[str, Any]:
    """Build the simple manifest stored next to the dossier."""
    return {
        "source_id": source_id,
        "title": title,
        "n_circulars": int(len(circular_rows)),
        "circular_ids": [str(value) for value in circular_rows["circular_id"].tolist()],
        "output_path": str(output_path),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def write_text(path: Path, text: str) -> None:
    """Write the dossier text to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run_gcn_inception_event_dossier_build(args: argparse.Namespace) -> None:
    """Build one blind INCEpTION pilot dossier for a matched event."""
    setup_console_logging()

    source_id = str(args.source_id).strip()
    if not source_id:
        raise ValueError("--source-id must not be empty")

    associations = load_associations_dataframe(args.associations_path)
    source_rows = associations[associations["source_id"].astype(str) == source_id]
    if source_rows.empty:
        raise ValueError(f"No matched GCN associations found for source_id: {source_id}")

    source_rows = choose_best_association_rows(source_rows)
    source_rows = source_rows.copy()
    source_rows["_sort_key"] = source_rows.apply(circular_sort_key, axis=1)
    source_rows = source_rows.sort_values(by="_sort_key", kind="stable").drop(
        columns=["_sort_key"]
    )

    selected_sources_lookup = load_selected_sources_lookup(args.selected_sources_path)
    source_row = selected_sources_lookup.get(source_id)
    aliases = normalize_aliases(source_row)
    title = build_default_title(
        source_id,
        source_row=source_row,
        explicit_title=args.title,
    )

    dossier_text = build_inception_dossier_text(
        source_id=source_id,
        title=title,
        aliases=aliases,
        circular_rows=source_rows,
        gcn_root=args.gcn_root,
    )

    output_dir = ensure_output_dir(args.output_dir)
    safe_id = safe_source_id(source_id)
    output_path = output_dir / f"{safe_id}{DOSSIER_SUFFIX}"
    manifest_path = output_dir / f"{safe_id}{MANIFEST_SUFFIX}"

    write_text(output_path, dossier_text)
    save_json(
        manifest_path,
        build_manifest(
            source_id=source_id,
            title=title,
            circular_rows=source_rows,
            output_path=output_path,
        ),
    )

    logging.info("Source ID: %s", source_id)
    logging.info("Title: %s", title)
    logging.info("Circulars included: %s", len(source_rows))
    logging.info("Dossier path: %s", output_path)
    logging.info("Manifest path: %s", manifest_path)
    if getattr(args, "include_low_confidence", False):
        logging.info(
            "--include-low-confidence is accepted for compatibility; all matched Circulars are already included by default."
        )
