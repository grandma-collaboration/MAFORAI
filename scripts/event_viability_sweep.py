#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from skyportal_corpus.canonical.document import iter_real_circulars  # noqa: E402
from skyportal_corpus.extraction_v2 import event_selection  # noqa: E402
from skyportal_corpus.extraction_v2.event_grouping import canonical_aliases  # noqa: E402
from skyportal_corpus.extraction_v2.event_registry import (  # noqa: E402
    DEFAULT_EVENT_REGISTRY_PATH,
    FLAG_SEPARATOR,
    TRIGGER_LIKE_SOURCE_PATTERN,
)
from skyportal_corpus.extraction_v2.identity_index import (  # noqa: E402
    DEFAULT_IDENTITY_INDEX_META_PATH,
    DEFAULT_IDENTITY_INDEX_PATH,
    load_identity_index_meta,
    read_identity_index,
    validate_identity_index_meta,
)


DEFAULT_OUTPUT_PATH = Path("data/interim/gcn/event_matching/event_viability.csv")
MJD_UNIX_EPOCH = 40587.0
VIABILITY_COLUMNS = (
    "source_id",
    "gcn_source_type",
    "n_terms",
    "suffixless_only",
    "n_included",
    "n_subject_match",
    "n_body_only",
    "n_body_name_match",
    "n_conflict_excluded",
    "n_far_in_time",
    "trigger_time",
    "first_circular_created_on",
    "last_circular_created_on",
    "flags",
)
EVENT_DATE_PATTERN = re.compile(r"(?:GRB|GCN|EP)[-_ ]?(\d{6})", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit Circular-selection viability for every registered event."
    )
    parser.add_argument("--registry-path", default=str(DEFAULT_EVENT_REGISTRY_PATH))
    parser.add_argument("--index-path", default=str(DEFAULT_IDENTITY_INDEX_PATH))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    registry_path = _project_path(args.registry_path)
    index_path = _project_path(args.index_path)
    output_path = _project_path(args.output)
    started = perf_counter()

    registry_rows = read_registry_rows(registry_path)
    metadata_path = index_path.with_name(DEFAULT_IDENTITY_INDEX_META_PATH.name)
    metadata = load_identity_index_meta(metadata_path)
    validate_identity_index_meta(metadata)
    min_year = int(metadata["min_year"])
    index_records = read_identity_index(index_path)
    circulars = list(iter_real_circulars(min_year=min_year))
    if len(index_records) != int(metadata["n_circulars"]):
        raise ValueError("Identity index row count does not match index metadata")

    viability_rows: list[dict[str, Any]] = []
    zero_reasons: Counter[str] = Counter()
    zero_other_details: dict[str, list[str]] = {}

    def cached_circulars(*, min_year: int) -> Iterable[dict[str, Any]]:
        if min_year != int(metadata["min_year"]):
            raise ValueError(
                f"Requested min_year={min_year} does not match cached corpus scope"
            )
        return iter(circulars)

    with (
        patch.object(event_selection, "load_identity_index_meta", return_value=metadata),
        patch.object(event_selection, "read_identity_index", return_value=index_records),
        patch.object(event_selection, "iter_real_circulars", side_effect=cached_circulars),
    ):
        for registry_row in registry_rows:
            selection = event_selection.select_event_candidates(
                str(registry_row["source_id"]),
                registry_path=registry_path,
                index_path=index_path,
            )
            viability_rows.append(viability_row(selection))
            if int(selection["n_included"]) == 0:
                reason, detail = zero_match_reason(registry_row, min_year=min_year)
                zero_reasons[reason] += 1
                if reason == "other":
                    zero_other_details[str(registry_row["source_id"])] = detail

    write_viability_rows(viability_rows, output_path)
    elapsed = perf_counter() - started
    print_report(
        viability_rows,
        zero_reasons=zero_reasons,
        zero_other_details=zero_other_details,
        output_path=output_path,
        elapsed=elapsed,
        min_year=min_year,
    )


def read_registry_rows(path: Path) -> list[dict[str, str]]:
    """Read canonical registry rows in deterministic source-ID order."""
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = [dict(row) for row in csv.DictReader(handle)]
    return sorted(rows, key=lambda row: str(row.get("source_id") or ""))


def viability_row(selection: Mapping[str, Any]) -> dict[str, Any]:
    """Reduce one authoritative selection to the stable viability schema."""
    included = list(selection.get("included") or [])
    created_values = sorted(
        str(item["created_on"])
        for item in included
        if str(item.get("created_on") or "")
    )
    flags = [str(item) for item in selection.get("flags") or []]
    return {
        "source_id": selection["source_id"],
        "gcn_source_type": selection.get("gcn_source_type") or "",
        "n_terms": len(selection.get("terms") or []),
        "suffixless_only": "suffixless_only_terms" in flags,
        "n_included": int(selection["n_included"]),
        "n_subject_match": sum(
            item.get("reason") == "confirmed_subject_match" for item in included
        ),
        "n_body_only": len(selection.get("body_only") or []),
        "n_body_name_match": len(selection.get("body_only_name") or []),
        "n_conflict_excluded": len(selection.get("excluded_conflicts") or []),
        "n_far_in_time": len(selection.get("far_in_time") or []),
        "trigger_time": _display(selection.get("trigger_time")),
        "first_circular_created_on": created_values[0] if created_values else "",
        "last_circular_created_on": created_values[-1] if created_values else "",
        "flags": FLAG_SEPARATOR.join(flags),
    }


def zero_match_reason(
    registry_row: Mapping[str, Any],
    *,
    min_year: int,
) -> tuple[str, list[str]]:
    """Classify one zero-match event using registry metadata only."""
    terms = _split_terms(registry_row.get("terms"))
    if _event_predates(registry_row, terms, min_year=min_year):
        return "event_predates_corpus_window", []
    if terms and all(TRIGGER_LIKE_SOURCE_PATTERN.fullmatch(term) for term in terms):
        return "only_internal_trigger_id", []
    alias_info = canonical_aliases(terms)
    if not any(bool(item["recognizable"]) for item in alias_info.values()):
        return "no_recognizable_term", []

    details: list[str] = []
    flags = str(registry_row.get("flags") or "").split(FLAG_SEPARATOR)
    if "suffixless_only_terms" in flags:
        details.append("suffixless_only_terms_with_no_match")
    else:
        details.append("recognizable_terms_with_no_match")
    details.append("terms=" + " | ".join(terms))
    return "other", details


def write_viability_rows(rows: Iterable[Mapping[str, Any]], path: Path) -> None:
    """Write viability rows with a stable column order."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=VIABILITY_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in VIABILITY_COLUMNS})


def print_report(
    rows: list[dict[str, Any]],
    *,
    zero_reasons: Counter[str],
    zero_other_details: Mapping[str, list[str]],
    output_path: Path,
    elapsed: float,
    min_year: int,
) -> None:
    """Print the requested viability distribution and diagnostics."""
    distribution = Counter(_included_bucket(int(row["n_included"])) for row in rows)
    viable_by_type = Counter(
        str(row["gcn_source_type"])
        for row in rows
        if int(row["n_included"]) >= 5
    )
    top = sorted(
        rows,
        key=lambda row: (-int(row["n_included"]), str(row["source_id"])),
    )[:15]

    print("EVENT VIABILITY SWEEP")
    print(f"min_year: {min_year}")
    print(f"total_events: {len(rows)}")
    print("n_included_distribution:")
    for bucket in ("0", "1-4", "5-9", "10-19", "20-49", "50+"):
        print(f"  {bucket}: {distribution[bucket]}")
    print(f"zero_events: {distribution['0']}")
    print("zero_match_reasons:")
    for reason in (
        "no_recognizable_term",
        "only_internal_trigger_id",
        "event_predates_corpus_window",
        "other",
    ):
        print(f"  {reason}: {zero_reasons[reason]}")
    print("zero_match_other_details:")
    if not zero_other_details:
        print("  none")
    for source_id in sorted(zero_other_details):
        print(f"  {source_id}: {'; '.join(zero_other_details[source_id])}")
    print("viable_events_by_gcn_source_type:")
    for source_type in sorted({str(row["gcn_source_type"]) for row in rows}):
        print(f"  {source_type}: {viable_by_type[source_type]}")
    print("top_15_by_n_included:")
    print("  source_id | gcn_source_type | n_included")
    for row in top:
        print(
            f"  {row['source_id']} | {row['gcn_source_type']} | {row['n_included']}"
        )
    print(f"wall_clock_seconds: {elapsed:.3f}")
    print(f"output_path: {output_path}")


def _event_predates(
    registry_row: Mapping[str, Any],
    terms: list[str],
    *,
    min_year: int,
) -> bool:
    trigger_time = _optional_float(registry_row.get("trigger_time"))
    if trigger_time is not None:
        timestamp = (trigger_time - MJD_UNIX_EPOCH) * 86400.0
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).year < min_year
    for value in [str(registry_row.get("source_id") or ""), *terms]:
        match = EVENT_DATE_PATTERN.search(value)
        if match is None:
            continue
        try:
            year = datetime.strptime(match.group(1), "%y%m%d").year
        except ValueError:
            continue
        return year < min_year
    return False


def _included_bucket(count: int) -> str:
    if count == 0:
        return "0"
    if count < 5:
        return "1-4"
    if count < 10:
        return "5-9"
    if count < 20:
        return "10-19"
    if count < 50:
        return "20-49"
    return "50+"


def _split_terms(value: Any) -> list[str]:
    return [item.strip() for item in str(value or "").split("|") if item.strip()]


def _optional_float(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _display(value: Any) -> str:
    return "" if value is None else str(value)


def _project_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


if __name__ == "__main__":
    main()
