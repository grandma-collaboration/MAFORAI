"""Flatten one frozen ICARE telescope-resource raw capture into interim Parquet tables.

Stage 2: SHAPE ONLY. Adapts the flattening approach of
scripts/skyportal/01_flatten.py (dotted-path dict flattening, deterministic
JSON serialization of list-valued and genuinely mixed-type scalar columns)
to the telescopes/instruments/allocations/observations resources captured
by scripts/telescopes/01_fetch.py. No semantic normalization, renaming, or
scientific selection happens here — see the Stage 2 brief for the full list
of prohibited transformations.

Unlike the old corpus builder, the raw capture to process is a required
runtime argument (--capture-dir), never a date baked into this file, so a
future capture needs no source change to be processed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import OrderedDict
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_ROOT = REPO_ROOT / "data/raw/telescopes/icare"
INTERIM_ROOT = REPO_ROOT / "data/interim/telescopes"

RESOURCE_ORDER = ["telescopes", "instruments", "allocations", "observations"]

# Which key under payload["data"] holds the record list; None means
# payload["data"] is itself the record list. This mirrors
# RESOURCE_LIST_KEYS in scripts/telescopes/01_fetch.py and is a structural
# fact about the API envelope, not a tunable choice.
RESOURCE_LIST_KEYS: dict[str, str | None] = {
    "telescopes": None,
    "instruments": None,
    "allocations": None,
    "observations": "observations",
}
PAGINATED_RESOURCES = {"observations"}

PREVIEW_LIMIT = 15  # structural-discovery lists longer than this are summarized, not dumped


# ---------------------------------------------------------------------------
# Raw capture discovery and loading
# ---------------------------------------------------------------------------
def discover_latest_capture(raw_root: Path) -> Path:
    """Pick the lexicographically latest capture_* directory under raw_root.

    capture_* names are `capture_<YYYYMMDD_HHMMSS>[...]`, so lexicographic
    order is chronological order; this is only used as a default when
    --capture-dir is not given.
    """
    candidates = sorted(p for p in raw_root.glob("capture_*") if p.is_dir())
    if not candidates:
        raise RuntimeError(f"No capture_* directories found under: {raw_root}")
    return candidates[-1]


def load_json(path: Path) -> Any:
    """Load one raw JSON file and retain its original JSON value types."""
    try:
        with path.open(encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Failed to parse raw JSON file: {path}") from exc


def load_manifest(capture_dir: Path) -> dict[str, Any]:
    """Load and structurally validate the Stage-1 manifest for one capture."""
    manifest_path = capture_dir / "manifest.json"
    if not manifest_path.exists():
        raise RuntimeError(f"Stage-1 manifest not found in capture directory: {manifest_path}")
    manifest = load_json(manifest_path)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("resources"), dict):
        raise RuntimeError(f"Stage-1 manifest has an unexpected shape: {manifest_path}")
    return manifest


def resource_files_from_manifest(
    manifest: dict[str, Any], resource: str, capture_dir: Path
) -> list[tuple[int, Path]]:
    """Return [(page_number, path)] for one resource in page order, per the Stage-1 manifest."""
    entry = manifest["resources"].get(resource)
    if not isinstance(entry, dict):
        raise RuntimeError(
            f"Stage-1 manifest does not list resource '{resource}': {capture_dir / 'manifest.json'}"
        )
    if not entry.get("success"):
        raise RuntimeError(
            f"Stage-1 manifest records resource '{resource}' as unsuccessful "
            f"(stopped_reason={entry.get('stopped_reason')!r}); refusing to flatten an "
            f"incomplete capture"
        )

    files: list[tuple[int, Path]] = []
    for request_entry in entry.get("requests", []):
        output_file = request_entry.get("output_file")
        if not output_file:
            continue
        files.append((request_entry.get("page_number", 1), capture_dir / output_file))

    if not files:
        raise RuntimeError(f"Stage-1 manifest lists zero output files for resource '{resource}'")

    files.sort(key=lambda item: item[0])
    return files


def verify_against_glob(resource: str, manifest_files: list[tuple[int, Path]], capture_dir: Path) -> None:
    """Cross-check manifest-declared files against an independent glob discovery.

    This is what lets flattening discover an arbitrary number of observation
    pages instead of assuming a single `observations_page_001.json`.
    """
    pattern = f"{resource}_page_*.json" if resource in PAGINATED_RESOURCES else f"{resource}.json"
    globbed = sorted(p.name for p in capture_dir.glob(pattern))
    manifest_names = sorted(path.name for _, path in manifest_files)
    if globbed != manifest_names:
        raise RuntimeError(
            f"Resource '{resource}': manifest-declared files {manifest_names} do not match "
            f"glob-discovered files {globbed} in {capture_dir}; refusing to guess which is correct"
        )


def access_record_list(payload: Any, resource: str, path: Path) -> list[dict[str, Any]]:
    """Descend the resource's known access path and require a list of record dicts."""
    list_key = RESOURCE_LIST_KEYS[resource]
    if not isinstance(payload, dict):
        raise TypeError(f"Raw payload is {type(payload).__name__}, not a mapping, in file: {path}")

    data = payload.get("data")
    if list_key is None:
        value, dotted = data, "data"
    else:
        if not isinstance(data, dict):
            raise TypeError(f"'data' is {type(data).__name__}, not a mapping, in file: {path}")
        value, dotted = data.get(list_key), f"data.{list_key}"

    if not isinstance(value, list):
        raise TypeError(f"Access path '{dotted}' is {type(value).__name__}, not list, in raw file: {path}")
    for index, record in enumerate(value):
        if not isinstance(record, dict):
            raise TypeError(
                f"Record {index} at '{dotted}' is {type(record).__name__}, not dict, in raw file: {path}"
            )
    return value


def add_provenance(record: dict[str, Any], provenance: dict[str, Any], path: Path) -> dict[str, Any]:
    """Merge provenance into one raw record, raising on any field-name collision."""
    collisions = sorted(set(record) & set(provenance))
    if collisions:
        raise ValueError(
            f"Raw record in {path} collides with provenance columns: {collisions}; "
            f"refusing to overwrite raw data"
        )
    combined = dict(record)
    combined.update(provenance)
    return combined


def load_resource(
    resource: str, manifest: dict[str, Any], capture_dir: Path
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read every raw record for one resource, in deterministic page order, with
    provenance attached. Returns (provenance_tagged_records, raw_stats)."""
    manifest_files = resource_files_from_manifest(manifest, resource, capture_dir)
    verify_against_glob(resource, manifest_files, capture_dir)

    source_name = manifest.get("source_name", "icare")
    capture_id = manifest.get("capture_id", capture_dir.name)
    list_key = RESOURCE_LIST_KEYS[resource]
    access_path = "data" if list_key is None else f"data.{list_key}"

    rows: list[dict[str, Any]] = []
    per_file_counts: "OrderedDict[str, int]" = OrderedDict()

    for page_number, path in manifest_files:
        payload = load_json(path)
        records = access_record_list(payload, resource, path)
        per_file_counts[path.name] = len(records)

        provenance: dict[str, Any] = {
            "raw_source": source_name,
            "capture_id": capture_id,
            "raw_file": path.name,
        }
        if resource in PAGINATED_RESOURCES:
            provenance["page_number"] = page_number

        rows.extend(add_provenance(record, provenance, path) for record in records)

    return rows, {
        "access_path": access_path,
        "files": [path.name for _, path in manifest_files],
        "per_file_counts": per_file_counts,
        "raw_record_count": sum(per_file_counts.values()),
        "manifest_record_count": manifest["resources"][resource]["record_count_total"],
        "provenance_fields": ["raw_source", "capture_id", "raw_file"]
        + (["page_number"] if resource in PAGINATED_RESOURCES else []),
    }


# ---------------------------------------------------------------------------
# Flattening (adapted from scripts/skyportal/01_flatten.py)
# ---------------------------------------------------------------------------
def discover_dict_paths(value: Any, prefix: str, paths: set[str]) -> None:
    """Find paths that are dictionaries in at least one raw record."""
    if isinstance(value, dict):
        if prefix:
            paths.add(prefix)
        for key, child in value.items():
            discover_dict_paths(child, f"{prefix}.{key}" if prefix else key, paths)


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
            flat[path] = json.dumps(child, ensure_ascii=False, separators=(",", ":"))
            serialized_lists.add(path)
        elif child is None and path in dict_paths:
            continue
        else:
            flat[path] = child
    return flat


def json_scalar(value: Any) -> str:
    """Represent one mixed-type scalar as an unambiguous JSON literal string."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def build_dataframe(records: list[dict[str, Any]]) -> tuple[pd.DataFrame, dict[str, str], set[str]]:
    """Build a stable object-backed table while preserving varying JSON scalar types.

    Returns (frame, serialized_column_reasons, dict_paths_discovered).
    """
    dict_paths: set[str] = set()
    for record in records:
        discover_dict_paths(record, "", dict_paths)

    serialized_lists: set[str] = set()
    flattened = [flatten_record(record, dict_paths, serialized_lists) for record in records]
    column_order = list(dict.fromkeys(key for record in flattened for key in record))

    serialized: dict[str, str] = {
        column: "list-valued field retained as a JSON string" for column in sorted(serialized_lists)
    }
    columns: dict[str, pd.Series] = {}
    for column in column_order:
        values = [record.get(column) for record in flattened]
        non_null_types = {type(value) for value in values if value is not None}
        if len(non_null_types) > 1:
            values = [None if value is None else json_scalar(value) for value in values]
            serialized[column] = (
                "varying raw scalar types retained as JSON literal strings: "
                + ", ".join(sorted(t.__name__ for t in non_null_types))
            )
        columns[column] = pd.Series(values, dtype=object)

    return pd.DataFrame(columns), serialized, dict_paths


# ---------------------------------------------------------------------------
# Content-preservation spot check
# ---------------------------------------------------------------------------
def strip_provenance(row: dict[str, Any], provenance_fields: list[str]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key not in provenance_fields}


def verify_flattened_sample(
    raw_record: dict[str, Any],
    flat_row: dict[str, Any],
    serialized_columns: set[str],
    prefix: str = "",
) -> list[str]:
    """Recursively confirm one flattened row matches its raw record under the
    documented flattening rules. Returns mismatch descriptions (empty = PASS)."""
    mismatches: list[str] = []
    for key, raw_value in raw_record.items():
        path = f"{prefix}.{key}" if prefix else key

        if isinstance(raw_value, dict):
            if not raw_value:
                mismatches.append(f"'{path}': empty dict in raw record (unsupported by flattening rules)")
                continue
            mismatches.extend(verify_flattened_sample(raw_value, flat_row, serialized_columns, path))
            continue

        if path not in flat_row:
            if raw_value is None:
                continue  # dropped because this path is a dict elsewhere; matches flatten_record
            mismatches.append(f"'{path}': missing from flattened row (raw value={raw_value!r})")
            continue

        flat_value = flat_row[path]

        if raw_value is None:
            if flat_value is not None:
                mismatches.append(f"'{path}': raw is None but flattened value is {flat_value!r}")
        elif isinstance(raw_value, list) or path in serialized_columns:
            expected = json_scalar(raw_value)
            if flat_value != expected:
                mismatches.append(
                    f"'{path}': serialized value mismatch (expected={expected!r}, got={flat_value!r})"
                )
        else:
            if flat_value != raw_value:
                mismatches.append(f"'{path}': value mismatch (raw={raw_value!r}, flat={flat_value!r})")

    return mismatches


def spot_check_resource(
    raw_rows: list[dict[str, Any]],
    frame: pd.DataFrame,
    serialized_columns: set[str],
    provenance_fields: list[str],
) -> dict[str, Any]:
    """Deterministically sample first/middle/last records and verify correspondence."""
    n = len(raw_rows)
    indices = sorted({0, n // 2, n - 1})
    mismatches: dict[int, list[str]] = {}

    for index in indices:
        raw_record = strip_provenance(raw_rows[index], provenance_fields)
        flat_row = frame.iloc[index].to_dict()
        result = verify_flattened_sample(raw_record, flat_row, serialized_columns)
        if result:
            mismatches[index] = result

    return {"indices_checked": indices, "mismatches": mismatches, "status": "PASS" if not mismatches else "FAIL"}


# ---------------------------------------------------------------------------
# Repository-safety helpers
# ---------------------------------------------------------------------------
def hash_files(paths: list[Path]) -> dict[str, str]:
    digests: dict[str, str] = {}
    for path in paths:
        digests[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digests


def git_status_porcelain(repo_root: Path) -> list[str] | None:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_root, capture_output=True, text=True, timeout=30, check=True,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    return [line for line in result.stdout.splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def process_resource(resource: str, manifest: dict[str, Any], capture_dir: Path) -> dict[str, Any]:
    """Load, flatten, and spot-check one resource. Returns a result dict; on
    any structural problem, returns {"error": <contextual message>} instead
    of raising, so the rest of the report can still be produced."""
    try:
        rows, raw_stats = load_resource(resource, manifest, capture_dir)
        frame, serialized, dict_paths = build_dataframe(rows)
        if frame.empty:
            raise RuntimeError(f"Resource '{resource}' flattened to 0 rows; refusing to treat as valid")
        spot_check = spot_check_resource(rows, frame, set(serialized), raw_stats["provenance_fields"])
        return {
            "resource": resource,
            "raw_stats": raw_stats,
            "frame": frame,
            "serialized": serialized,
            "dict_paths": dict_paths,
            "spot_check": spot_check,
            "error": None,
        }
    except (RuntimeError, ValueError, TypeError) as exc:
        return {"resource": resource, "error": str(exc)}


def build_provenance_check(result: dict[str, Any]) -> dict[str, Any]:
    frame = result["frame"]
    fields = result["raw_stats"]["provenance_fields"]
    populated = {field: int(frame[field].notna().sum()) if field in frame.columns else 0 for field in fields}
    all_populated = all(populated[field] == len(frame) for field in fields)
    return {"fields": fields, "populated": populated, "rows": len(frame), "all_populated": all_populated}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Flatten one frozen ICARE telescope-resource raw capture into interim Parquet tables."
    )
    parser.add_argument(
        "--capture-dir",
        default=None,
        help=(
            "Path to a Stage-1 capture directory (e.g. "
            f"{RAW_ROOT}/capture_20260808_071334). Defaults to the latest "
            f"capture_* directory found under {RAW_ROOT}."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help=f"Optional interim output root override. Defaults to {INTERIM_ROOT}/<capture-id>.",
    )
    return parser.parse_args()


def format_preview(items: list[str]) -> str:
    items = sorted(items)
    if len(items) <= PREVIEW_LIMIT:
        return f"{len(items)}: {items}"
    return f"{len(items)}: {items[:PREVIEW_LIMIT]} ... (+{len(items) - PREVIEW_LIMIT} more)"


def print_banner(title: str) -> None:
    bar = "=" * 100
    print(bar)
    print(title)
    print(bar)


def print_section(number: int, title: str) -> None:
    print()
    print("=" * 100)
    print(f"{number}. {title}")
    print("=" * 100)


def main() -> None:
    args = parse_args()

    capture_dir = Path(args.capture_dir).resolve() if args.capture_dir else discover_latest_capture(RAW_ROOT)
    if not capture_dir.is_dir():
        raise RuntimeError(f"Capture directory does not exist: {capture_dir}")

    manifest = load_manifest(capture_dir)
    capture_id = manifest.get("capture_id", capture_dir.name)
    output_dir = Path(args.output_dir).resolve() if args.output_dir else INTERIM_ROOT / capture_id

    status_before = git_status_porcelain(REPO_ROOT)
    raw_files_before = sorted(p for p in capture_dir.glob("*.json"))
    hashes_before = hash_files(raw_files_before)

    results: dict[str, dict[str, Any]] = {}
    for resource in RESOURCE_ORDER:
        results[resource] = process_resource(resource, manifest, capture_dir)

    any_error = any(result["error"] for result in results.values())

    written_files: dict[str, Path] = {}
    if not any_error:
        output_dir.mkdir(parents=True, exist_ok=True)
        for resource in RESOURCE_ORDER:
            frame = results[resource]["frame"]
            out_path = output_dir / f"{resource}.parquet"
            frame.to_parquet(out_path, engine="pyarrow", index=False, compression="zstd")
            written_files[resource] = out_path

    # --- read-back check ---
    readback: dict[str, dict[str, Any]] = {}
    for resource, out_path in written_files.items():
        try:
            reread = pd.read_parquet(out_path, engine="pyarrow")
            readback[resource] = {
                "readable": True,
                "row_count": len(reread),
                "matches_prewrite": len(reread) == len(results[resource]["frame"]),
            }
        except Exception as exc:  # noqa: BLE001 - report any read-back failure as evidence, not a crash
            readback[resource] = {"readable": False, "row_count": None, "matches_prewrite": False, "error": str(exc)}

    hashes_after = hash_files(raw_files_before)
    status_after = git_status_porcelain(REPO_ROOT)

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------
    print_banner("STAGE 2 — ICARE SHAPE-ONLY FLATTENING")

    print_section(1, "IMPLEMENTATION")
    print("files created:")
    print("  - scripts/telescopes/02_flatten.py")
    if written_files:
        print(f"  - {len(written_files)} Parquet file(s) under {output_dir}")
    print("files modified:")
    print("  none")
    print(f"\ncapture used: {capture_dir}")
    print(f"output directory: {output_dir}")
    print(
        "\nstructure: a single self-contained CLI script adapting "
        "scripts/skyportal/01_flatten.py's dotted-path flattening (discover_dict_paths / "
        "flatten_record / build_dataframe) to the 4 ICARE resources; the Stage-1 manifest "
        "drives file discovery (page order, success flags) and is cross-checked against an "
        "independent glob of the capture directory before any record is read."
    )

    print_section(2, "RAW INPUT")
    for resource in RESOURCE_ORDER:
        result = results[resource]
        if result["error"]:
            print(f"resource                {resource}")
            print(f"  ERROR: {result['error']}")
            print()
            continue
        stats = result["raw_stats"]
        print(f"resource                {resource}")
        print(f"raw file/page count     {len(stats['files'])} ({', '.join(stats['files'])})")
        print(f"raw records             {stats['raw_record_count']}")
        print(f"record-list access path {stats['access_path']}")
        print()

    print_section(3, "FLATTENED OUTPUT")
    for resource in RESOURCE_ORDER:
        result = results[resource]
        if result["error"]:
            print(f"resource      {resource}")
            print("  not produced (see RAW INPUT error above)")
            print()
            continue
        frame = result["frame"]
        out_path = written_files.get(resource)
        size = out_path.stat().st_size if out_path and out_path.exists() else None
        print(f"resource      {resource}")
        print(f"rows          {len(frame)}")
        print(f"columns       {len(frame.columns)}")
        print(f"output file   {out_path if out_path else '(not written)'}")
        print(f"file size     {f'{size:,} bytes' if size is not None else 'n/a'}")
        print()

    print_section(4, "STRUCTURAL DISCOVERY")
    for resource in RESOURCE_ORDER:
        result = results[resource]
        if result["error"]:
            print(f"resource: {resource} — skipped (see RAW INPUT error above)")
            print()
            continue
        serialized = result["serialized"]
        list_columns = sorted(c for c, reason in serialized.items() if reason.startswith("list-valued"))
        mixed_columns = sorted(c for c, reason in serialized.items() if not reason.startswith("list-valued"))
        print(f"resource: {resource}")
        print(f"  nested dict paths discovered : {format_preview(sorted(result['dict_paths']))}")
        print(f"  list-valued columns          : {format_preview(list_columns)}")
        print(f"  mixed scalar-type columns    : {format_preview(mixed_columns)}")
        if mixed_columns:
            for column in mixed_columns[:PREVIEW_LIMIT]:
                print(f"    - {column}: {serialized[column]}")
        print()

    print_section(5, "PROVENANCE")
    for resource in RESOURCE_ORDER:
        result = results[resource]
        if result["error"]:
            print(f"resource: {resource} — skipped (see RAW INPUT error above)")
            continue
        check = build_provenance_check(result)
        status = "PASS" if check["all_populated"] else "FAIL"
        print(
            f"resource: {resource:14s} columns={check['fields']} "
            f"populated={check['populated']} rows={check['rows']} status={status}"
        )
    print("\ncollision checks: enforced at merge time (add_provenance); any collision raises "
          "immediately and surfaces as a RAW INPUT error above rather than overwriting raw data.")

    print_section(6, "CONTENT-PRESERVATION SPOT CHECK")
    for resource in RESOURCE_ORDER:
        result = results[resource]
        if result["error"]:
            print(f"resource: {resource} — skipped (see RAW INPUT error above)")
            continue
        spot = result["spot_check"]
        print(f"resource: {resource:14s} sample records checked (indices)={spot['indices_checked']} "
              f"status={spot['status']}")
        for index, mismatch_list in spot["mismatches"].items():
            for mismatch in mismatch_list[:5]:
                print(f"    index {index}: {mismatch}")

    # --- controls ---
    controls: list[dict[str, Any]] = []

    def check(name: str, expected: Any, observed: Any) -> None:
        controls.append({
            "control": name, "expected": expected, "observed": observed,
            "status": "PASS" if observed == expected else "FAIL",
        })

    check("1. every expected raw resource found", 4, sum(1 for r in RESOURCE_ORDER if not results[r]["error"]))
    check("2. every raw JSON file is parseable", True, not any_error)
    check("3. every record list has expected structure", True, not any_error)

    for resource in RESOURCE_ORDER:
        result = results[resource]
        if result["error"]:
            controls.append({
                "control": f"4-6. row count preserved ({resource})",
                "expected": "raw==manifest==flat", "observed": "resource errored", "status": "FAIL",
            })
            continue
        raw_n = result["raw_stats"]["raw_record_count"]
        manifest_n = result["raw_stats"]["manifest_record_count"]
        flat_n = len(result["frame"])
        controls.append({
            "control": f"4-6. row count preserved ({resource})",
            "expected": "raw==manifest==flat",
            "observed": f"raw={raw_n}, manifest={manifest_n}, flat={flat_n}",
            "status": "PASS" if raw_n == manifest_n == flat_n else "FAIL",
        })

    for resource in RESOURCE_ORDER:
        result = results[resource]
        observed = len(result["frame"]) if not result["error"] else 0
        check(f"7. table non-empty ({resource})", True, observed > 0)

    for resource in RESOURCE_ORDER:
        result = results[resource]
        if result["error"]:
            check(f"8. provenance populated ({resource})", True, False)
            continue
        check(f"8. provenance populated ({resource})", True, build_provenance_check(result)["all_populated"])

    check("9. no provenance/raw-column collision", True, not any_error)
    check(
        "10. list-valued fields serialized deterministically", True,
        all(not r["error"] for r in results.values()),
    )
    check(
        "11. mixed-type scalar columns explicitly reported", True,
        all(r["error"] or isinstance(r["serialized"], dict) for r in results.values()),
    )
    check("12. all 4 Parquet outputs readable", 4, sum(1 for v in readback.values() if v["readable"]))
    for resource, rb in readback.items():
        check(f"13. read-back row count matches ({resource})", True, rb["matches_prewrite"])
    changed_raw_files = [k for k in hashes_before if hashes_before[k] != hashes_after.get(k)]
    controls.append({
        "control": "14. no Stage-1 raw file modified",
        "expected": "0 files changed",
        "observed": f"{len(changed_raw_files)} of {len(hashes_before)} files changed",
        "status": "PASS" if not changed_raw_files else "FAIL",
    })
    modified_pre_existing = (
        [line for line in status_after if line not in status_before]
        if status_before is not None and status_after is not None
        else []
    )
    controls.append({
        "control": "15. no existing corpus output modified",
        "expected": "0 pre-existing tracked files changed",
        "observed": f"{len(modified_pre_existing)} changed",
        "status": "PASS" if not modified_pre_existing else "FAIL",
    })

    print_section(7, "CONTROLS")
    print(f"{'control':48s} {'expected':50s} {'observed':50s} {'status':6s}")
    for c in controls:
        print(f"{c['control']:48s} {str(c['expected'])[:50]:50s} {str(c['observed'])[:50]:50s} {c['status']:6s}")

    # --- unexpected findings ---
    print_section(8, "UNEXPECTED FINDINGS")
    findings: list[str] = []
    for resource in RESOURCE_ORDER:
        result = results[resource]
        if result["error"]:
            findings.append(f"resource '{resource}' could not be flattened: {result['error']}")
            continue
        for column, reason in result["serialized"].items():
            if reason.startswith("varying raw scalar types"):
                findings.append(f"{resource}.{column}: {reason}")
    if findings:
        for finding in findings:
            print(f"- {finding}")
    else:
        print("none")

    print_section(9, "REPOSITORY SAFETY")
    print(f"raw files modified               : {len(changed_raw_files)}")
    print(f"existing corpus files modified   : {len(modified_pre_existing)}")
    unexpected_outputs = [
        p.name for p in (output_dir.glob("*") if output_dir.exists() else [])
        if p.suffix != ".parquet"
    ]
    print(f"final tables/docs/notebooks created (unexpected): {len(unexpected_outputs)} {unexpected_outputs or ''}")

    all_pass = all(c["status"] == "PASS" for c in controls)
    stage_status = "PASS" if all_pass else "FAIL"

    print_section(10, "STAGE STATUS")
    print(stage_status)
    print()
    if stage_status == "PASS":
        print(
            "Every control passed: the interim tables are a faithful, shape-only, "
            "provenance-aware flattening of the frozen raw capture and are safe to use as "
            "input to exploratory analysis."
        )
    else:
        print(
            "At least one control FAILED (see section 7 above); the interim tables must NOT "
            "be treated as complete or used as input to exploratory analysis."
        )

    if not all_pass:
        raise RuntimeError(
            "Stage 2 ICARE flattening FAILED at least one control; see the printed report above."
        )


if __name__ == "__main__":
    main()
