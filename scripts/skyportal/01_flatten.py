"""Flatten the fixed SkyPortal raw captures into interim Parquet tables."""

from __future__ import annotations

import json
import re
from collections import Counter, OrderedDict
from pathlib import Path
from typing import Any, Iterable, Sequence

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
INVENTORY_ROOT = REPO_ROOT / "data/raw/skyportal/inventory"
DETAIL_ROOT = REPO_ROOT / "data/raw/skyportal/source_detail_20260724"
OUTPUT_ROOT = REPO_ROOT / "data/interim/skyportal_corpus"

LISTING_CAPTURE_RUN = "20260720"
DETAIL_CAPTURE_RUN = "20260724"
LISTING_DIRECTORY_RE = re.compile(
    r"source_inventory_(?P<profile>grandma_base|grb|ep|gcn)_20260720_\d{6}$"
)
EXPECTED_PROFILES = {"grandma_base", "grb", "ep", "gcn"}

DETAIL_ACCESS_PATHS: dict[str, tuple[str, ...]] = {
    "comments": ("payload", "data"),
    "photometry": ("payload", "data"),
    "spectra": ("payload", "data", "spectra"),
    "followup_requests": ("payload", "data", "followup_requests"),
}

EXPECTED_CONTROLS = OrderedDict(
    [
        ("sources.parquet", 982),
        ("distinct source identifiers", 800),
        ("comments.parquet", 2950),
        ("photometry.parquet", 7968),
        ("spectra.parquet", 1),
        ("followup_requests.parquet", 2359),
    ]
)


def load_json(path: Path) -> Any:
    """Load one raw JSON file and retain its original JSON value types."""
    try:
        with path.open(encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Failed to parse raw JSON file: {path}") from exc


def access_record_list(payload: Any, access_path: Sequence[str], path: Path) -> list[dict[str, Any]]:
    """Descend an inspected access path and require a list of record objects."""
    value = payload
    traversed: list[str] = []
    for key in access_path:
        traversed.append(key)
        if not isinstance(value, dict) or key not in value:
            dotted = ".".join(traversed)
            raise KeyError(f"Missing access path '{dotted}' in raw file: {path}")
        value = value[key]
    if not isinstance(value, list):
        dotted = ".".join(access_path)
        raise TypeError(
            f"Access path '{dotted}' is {type(value).__name__}, not list, in raw file: {path}"
        )
    for index, record in enumerate(value):
        if not isinstance(record, dict):
            dotted = ".".join(access_path)
            raise TypeError(
                f"Record {index} at '{dotted}' is {type(record).__name__}, not dict, "
                f"in raw file: {path}"
            )
    return value


def add_listing_provenance(
    record: dict[str, Any], profile: str, source_file: str
) -> dict[str, Any]:
    """Add capture metadata without changing the source record."""
    provenance = {
        "source_profile": profile,
        "source_file": source_file,
        "capture_run": LISTING_CAPTURE_RUN,
    }
    return add_provenance(record, provenance)


def add_detail_provenance(
    record: dict[str, Any], source_dir: str, source_file: str
) -> dict[str, Any]:
    """Add capture metadata without changing the detail record."""
    provenance = {
        "source_dir": source_dir,
        "source_file": source_file,
        "capture_run": DETAIL_CAPTURE_RUN,
    }
    return add_provenance(record, provenance)


def add_provenance(record: dict[str, Any], provenance: dict[str, str]) -> dict[str, Any]:
    collisions = sorted(set(record) & set(provenance))
    if collisions:
        raise ValueError(f"Raw record collides with provenance columns: {collisions}")
    combined = dict(record)
    combined.update(provenance)
    return combined


def load_sources() -> list[dict[str, Any]]:
    """Read every paginated source record from the fixed July listing capture."""
    rows: list[dict[str, Any]] = []
    profiles_found: set[str] = set()
    directories = sorted(INVENTORY_ROOT.glob("source_inventory_*_20260720_*"))
    for directory in directories:
        if not directory.is_dir():
            continue
        match = LISTING_DIRECTORY_RE.fullmatch(directory.name)
        if match is None:
            raise ValueError(f"Unexpected July listing directory name: {directory}")
        profile = match.group("profile")
        profiles_found.add(profile)
        page_files = sorted(directory.glob("sources_page_*.json"))
        if not page_files:
            raise RuntimeError(f"No paginated listing JSON files found in: {directory}")
        for path in page_files:
            records = access_record_list(load_json(path), ("data", "sources"), path)
            rows.extend(add_listing_provenance(record, profile, path.name) for record in records)
    if profiles_found != EXPECTED_PROFILES:
        raise RuntimeError(
            f"July listing profiles differ from fixed perimeter: observed={sorted(profiles_found)}, "
            f"expected={sorted(EXPECTED_PROFILES)}"
        )
    if not rows:
        raise RuntimeError("Access path 'data.sources' returned zero source records")
    return rows


def load_detail(record_type: str) -> list[dict[str, Any]]:
    """Read one detail collection from every file present in the fixed capture."""
    access_path = DETAIL_ACCESS_PATHS[record_type]
    rows: list[dict[str, Any]] = []
    paths = sorted(DETAIL_ROOT.glob(f"*/{record_type}.json"))
    if not paths:
        raise RuntimeError(f"No raw detail files found for record type: {record_type}")
    for path in paths:
        records = access_record_list(load_json(path), access_path, path)
        rows.extend(
            add_detail_provenance(record, path.parent.name, path.name)
            for record in records
        )
    if not rows:
        dotted = ".".join(access_path)
        raise RuntimeError(
            f"Access path '{dotted}' returned zero records for record type: {record_type}"
        )
    return rows


def discover_dict_paths(value: Any, prefix: str, paths: set[str]) -> None:
    """Find paths that are dictionaries in at least one raw record."""
    if isinstance(value, dict):
        if prefix:
            paths.add(prefix)
        for key, child in value.items():
            child_path = f"{prefix}.{key}" if prefix else key
            discover_dict_paths(child, child_path, paths)


def flatten_record(
    value: dict[str, Any],
    dict_paths: set[str],
    serialized_lists: set[str],
    prefix: str = "",
) -> dict[str, Any]:
    """Flatten dictionaries and serialize list values without changing their contents."""
    flat: dict[str, Any] = {}
    for key, child in value.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(child, dict):
            if not child:
                raise ValueError(
                    f"Empty dictionary at '{path}' cannot be flattened without adding a policy"
                )
            flat.update(flatten_record(child, dict_paths, serialized_lists, path))
        elif isinstance(child, list):
            flat[path] = json.dumps(
                child,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            serialized_lists.add(path)
        elif child is None and path in dict_paths:
            continue
        else:
            flat[path] = child
    return flat


def json_scalar(value: Any) -> str:
    """Represent one mixed-type scalar as an unambiguous JSON literal string."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def build_dataframe(
    records: list[dict[str, Any]],
) -> tuple[pd.DataFrame, dict[str, str]]:
    """Build a stable object-backed table while preserving varying JSON scalar types."""
    dict_paths: set[str] = set()
    for record in records:
        discover_dict_paths(record, "", dict_paths)

    serialized_lists: set[str] = set()
    flattened = [flatten_record(record, dict_paths, serialized_lists) for record in records]
    column_order = list(dict.fromkeys(key for record in flattened for key in record))

    serialized: dict[str, str] = {
        column: "nested list retained as a JSON string"
        for column in sorted(serialized_lists)
    }
    columns: dict[str, pd.Series] = {}
    for column in column_order:
        values = [record.get(column) for record in flattened]
        non_null_types = {type(value) for value in values if value is not None}
        if len(non_null_types) > 1:
            values = [None if value is None else json_scalar(value) for value in values]
            serialized[column] = (
                "varying raw scalar types retained as JSON literal strings: "
                + ", ".join(sorted(value_type.__name__ for value_type in non_null_types))
            )
        columns[column] = pd.Series(values, dtype=object)
    return pd.DataFrame(columns), serialized


def cleaning_notes(table_name: str, frame: pd.DataFrame) -> list[str]:
    """Measure visible text anomalies without changing them."""
    notes: list[str] = []
    whitespace_counts: Counter[str] = Counter()
    replacement_counts: Counter[str] = Counter()
    for column in frame.columns:
        for value in frame[column]:
            if not isinstance(value, str):
                continue
            if value != value.strip():
                whitespace_counts[column] += 1
            if "\ufffd" in value:
                replacement_counts[column] += 1
    if whitespace_counts:
        notes.append(
            f"{table_name}: surrounding whitespace is present and unchanged: "
            + ", ".join(f"{column}={count}" for column, count in sorted(whitespace_counts.items()))
        )
    if replacement_counts:
        notes.append(
            f"{table_name}: U+FFFD is present and unchanged: "
            + ", ".join(f"{column}={count}" for column, count in sorted(replacement_counts.items()))
        )
    return notes


def print_controls(observed: OrderedDict[str, int]) -> bool:
    """Print all controls and return whether every one passed."""
    print("CONTROLS")
    print("| control | expected | observed | status |")
    print("|---|---:|---:|---|")
    passed = True
    for name, expected in EXPECTED_CONTROLS.items():
        actual = observed[name]
        status = "PASS" if actual == expected else "FAIL"
        passed = passed and status == "PASS"
        print(f"| {name} | {expected} | {actual} | {status} |")
    return passed


def print_summary(
    frames: OrderedDict[str, pd.DataFrame],
    serialized: dict[str, dict[str, str]],
    notes: Iterable[str],
) -> None:
    """Print the complete deterministic flattening summary."""
    print("\nTABLES")
    for name, frame in frames.items():
        print(f"- {name}: rows={len(frame)}, columns={len(frame.columns)}")
        print(f"  columns={list(frame.columns)}")

    print("\nSERIALIZED JSON COLUMNS")
    for name, columns in serialized.items():
        if not columns:
            print(f"- {name}: none")
            continue
        for column, reason in sorted(columns.items()):
            print(f"- {name}.{column}: {reason}")

    print("\nCLEANING NOTES - OBSERVED, NOT CHANGED")
    note_list = list(notes)
    if not note_list:
        print("- None observed by the limited whitespace and U+FFFD checks.")
    else:
        for note in note_list:
            print(f"- {note}")
    print("- sources.parquet intentionally retains repeated source identifiers across profiles.")


def main() -> None:
    raw_tables: OrderedDict[str, list[dict[str, Any]]] = OrderedDict(
        [
            ("sources.parquet", load_sources()),
            ("comments.parquet", load_detail("comments")),
            ("photometry.parquet", load_detail("photometry")),
            ("spectra.parquet", load_detail("spectra")),
            ("followup_requests.parquet", load_detail("followup_requests")),
        ]
    )

    frames: OrderedDict[str, pd.DataFrame] = OrderedDict()
    serialized: dict[str, dict[str, str]] = {}
    notes: list[str] = []
    for name, records in raw_tables.items():
        frame, serialized_columns = build_dataframe(records)
        frames[name] = frame
        serialized[name] = serialized_columns
        notes.extend(cleaning_notes(name, frame))

    observed = OrderedDict(
        [
            ("sources.parquet", len(frames["sources.parquet"])),
            ("distinct source identifiers", frames["sources.parquet"]["id"].nunique(dropna=False)),
            ("comments.parquet", len(frames["comments.parquet"])),
            ("photometry.parquet", len(frames["photometry.parquet"])),
            ("spectra.parquet", len(frames["spectra.parquet"])),
            ("followup_requests.parquet", len(frames["followup_requests.parquet"])),
        ]
    )
    if not print_controls(observed):
        access_paths = {
            "sources.parquet": "data.sources",
            **{
                f"{record_type}.parquet": ".".join(access_path)
                for record_type, access_path in DETAIL_ACCESS_PATHS.items()
            },
        }
        print(f"Access paths used: {access_paths}")
        raise RuntimeError("At least one flattening control failed; no Parquet file was written")

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    for name, frame in frames.items():
        frame.to_parquet(
            OUTPUT_ROOT / name,
            engine="pyarrow",
            index=False,
            compression="zstd",
        )

    print_summary(frames, serialized, notes)


if __name__ == "__main__":
    main()
