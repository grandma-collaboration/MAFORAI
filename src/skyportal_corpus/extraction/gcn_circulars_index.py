"""Build a normalized tabular index from extracted GCN circular JSON files."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from ..core import resolve_project_path

DEFAULT_CIRCULARS_INPUT_DIR = (
    "data/raw/gcn/circulars/archive_json/20260610_112607/extracted/archive.json"
)
DEFAULT_CIRCULARS_INDEX_OUTPUT_DIR = "data/interim/gcn/circulars"
REQUIRED_FIELDS = ("body", "circularId", "createdOn", "subject", "submitter")
OPTIONAL_FIELDS = (
    "bibcode",
    "eventId",
    "email",
    "submittedHow",
    "format",
    "editedBy",
    "editedOn",
)


def setup_circulars_index_logging(output_dir: Path) -> None:
    """Configure logging to console and file for one indexing run."""
    log_file = output_dir / "circulars_index.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
        force=True,
    )


def save_json(path: Path, data: Any) -> None:
    """Save JSON data to disk."""
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, default=str)


def infer_archive_run_id(input_dir: Path) -> str | None:
    """Infer the archive run ID from the input directory path when possible."""
    for part in input_dir.parts:
        if len(part) == 15 and part[8] == "_" and part.replace("_", "").isdigit():
            return part
    return None


def safe_timestamp_to_iso(value: object) -> str | None:
    """Convert a millisecond epoch timestamp into an ISO UTC datetime."""
    if value is None or isinstance(value, bool):
        return None

    try:
        timestamp_ms = float(value)
    except (TypeError, ValueError):
        return None

    try:
        return datetime.fromtimestamp(
            timestamp_ms / 1000.0,
            tz=timezone.utc,
        ).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def compute_text_hash(text: str) -> str:
    """Compute a SHA256 hash for one text value."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def schema_signature(data: dict[str, object]) -> str:
    """Build a compact signature from the sorted top-level JSON keys."""
    return "|".join(sorted(data.keys()))


def load_json_object(path: Path) -> dict[str, object]:
    """Load one JSON object from disk."""
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")

    return payload


def build_row(
    path: Path,
    archive_run_id: str | None,
    processed_at: str,
) -> dict[str, object]:
    """Build one normalized table row from one raw circular JSON file."""
    data = load_json_object(path)

    body = data.get("body")
    if not isinstance(body, str):
        body = ""

    subject = data.get("subject")
    if not isinstance(subject, str):
        subject = ""

    circular_id_raw = str(data.get("circularId"))
    created_on = data.get("createdOn")
    edited_on = data.get("editedOn")

    return {
        "archive_run_id": archive_run_id,
        "raw_file_name": path.name,
        "raw_file_path": str(path.resolve()),
        "circular_id_raw": circular_id_raw,
        "circular_id": circular_id_raw,
        "bibcode": data.get("bibcode"),
        "event_id": data.get("eventId"),
        "subject": subject,
        "body": body,
        "created_on": created_on,
        "created_at_iso": safe_timestamp_to_iso(created_on),
        "submitter": data.get("submitter"),
        "email": data.get("email"),
        "submitted_how": data.get("submittedHow"),
        "format": data.get("format"),
        "edited_by": data.get("editedBy"),
        "edited_on": edited_on,
        "edited_at_iso": safe_timestamp_to_iso(edited_on),
        "body_length": len(body),
        "subject_length": len(subject),
        "body_hash": compute_text_hash(body),
        "schema_signature": schema_signature(data),
        "processed_at": processed_at,
    }


def write_error_record(path: Path, raw_file_path: Path, exc: Exception) -> None:
    """Append one file-level indexing error to the JSONL error log."""
    error_record = {
        "raw_file_path": str(raw_file_path.resolve()),
        "error_type": type(exc).__name__,
        "error_message": str(exc),
    }

    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(error_record, ensure_ascii=False) + "\n")


def infer_output_year(created_at_iso: object) -> str:
    """Infer the year-based output partition from one ISO timestamp."""
    if isinstance(created_at_iso, str) and len(created_at_iso) >= 4:
        year = created_at_iso[:4]
        if year.isdigit():
            return year
    return "unknown"


def write_dataframe_outputs(
    dataframe: pd.DataFrame,
    output_dir: Path,
) -> dict[str, dict[str, object]]:
    """Write one CSV and one Parquet file per year partition."""
    if dataframe.empty:
        year_groups = [("unknown", dataframe)]
    else:
        partition_series = dataframe["created_at_iso"].map(infer_output_year)
        year_groups = list(dataframe.groupby(partition_series, sort=True, dropna=False))

    output_files: dict[str, dict[str, object]] = {}

    for year, year_frame in year_groups:
        year_dir = output_dir / str(year)
        year_dir.mkdir(parents=True, exist_ok=True)

        csv_path = year_dir / "circulars_index.csv"
        parquet_path = year_dir / "circulars_index.parquet"

        year_frame.to_csv(csv_path, index=False)

        try:
            year_frame.to_parquet(parquet_path, index=False)
        except (ImportError, ModuleNotFoundError, ValueError) as exc:
            raise RuntimeError(
                "Writing Parquet requires 'pyarrow' or 'fastparquet' to be installed."
            ) from exc

        output_files[str(year)] = {
            "csv": str(csv_path.resolve()),
            "parquet": str(parquet_path.resolve()),
            "rows": int(len(year_frame)),
        }

    return output_files


def build_report(
    *,
    input_dir: Path,
    output_dir: Path,
    processed_at: str,
    total_files_seen: int,
    rows: list[dict[str, object]],
    total_errors: int,
    required_field_counts: dict[str, int],
    optional_field_counts: dict[str, int],
    output_files: dict[str, dict[str, object]],
) -> dict[str, object]:
    """Build the summary report for one indexing run."""
    signature_counts = Counter(
        str(row["schema_signature"])
        for row in rows
    )

    return {
        "input_dir": str(input_dir.resolve()),
        "output_dir": str(output_dir.resolve()),
        "processed_at": processed_at,
        "total_files_seen": total_files_seen,
        "total_indexed": len(rows),
        "total_errors": total_errors,
        "unique_schema_signatures": len(signature_counts),
        "required_field_counts": required_field_counts,
        "optional_field_counts": optional_field_counts,
        "top_schema_signatures": [
            {"schema_signature": signature, "count": count}
            for signature, count in signature_counts.most_common(25)
        ],
        "indexed_by_year": {
            year: int(file_info["rows"])
            for year, file_info in output_files.items()
        },
        "output_files": {
            "report": str((output_dir / "index_report.json").resolve()),
            "errors": str((output_dir / "index_errors.jsonl").resolve()),
            "log": str((output_dir / "circulars_index.log").resolve()),
            "by_year": output_files,
        },
    }


def run_gcn_circulars_index_build(args: argparse.Namespace) -> None:
    """Build the normalized circular index from extracted raw JSON files."""
    input_dir = resolve_project_path(args.input_dir)
    output_dir = resolve_project_path(args.output_dir)

    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")
    if not input_dir.is_dir():
        raise NotADirectoryError(f"Input path is not a directory: {input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    setup_circulars_index_logging(output_dir)

    archive_run_id = infer_archive_run_id(input_dir)
    processed_at = datetime.now(timezone.utc).isoformat()
    json_paths = sorted(input_dir.rglob("*.json"))
    error_path = output_dir / "index_errors.jsonl"
    error_path.write_text("", encoding="utf-8")

    rows: list[dict[str, object]] = []
    total_errors = 0
    required_field_counts = Counter()
    optional_field_counts = Counter()

    logging.info("Starting GCN circulars indexing")
    logging.info("Input directory: %s", input_dir)
    logging.info("Output directory: %s", output_dir)
    logging.info("Archive run ID: %s", archive_run_id or "not inferred")
    logging.info("JSON files found: %s", len(json_paths))

    for path in json_paths:
        try:
            data = load_json_object(path)
            for field_name in REQUIRED_FIELDS:
                if field_name in data:
                    required_field_counts[field_name] += 1
            for field_name in OPTIONAL_FIELDS:
                if field_name in data:
                    optional_field_counts[field_name] += 1

            rows.append(build_row(path, archive_run_id, processed_at))
        except Exception as exc:
            total_errors += 1
            write_error_record(error_path, path, exc)

    dataframe = pd.DataFrame(rows)
    output_files = write_dataframe_outputs(dataframe, output_dir)

    report = build_report(
        input_dir=input_dir,
        output_dir=output_dir,
        processed_at=processed_at,
        total_files_seen=len(json_paths),
        rows=rows,
        total_errors=total_errors,
        required_field_counts={field: required_field_counts.get(field, 0) for field in REQUIRED_FIELDS},
        optional_field_counts={field: optional_field_counts.get(field, 0) for field in OPTIONAL_FIELDS},
        output_files=output_files,
    )
    save_json(output_dir / "index_report.json", report)

    logging.info("Indexed rows: %s", len(rows))
    logging.info("Errors: %s", total_errors)
    logging.info("Year partitions written: %s", len(output_files))
    logging.info("Wrote report: %s", output_dir / "index_report.json")
