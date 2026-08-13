#!/usr/bin/env python
"""Apply the thirteen corpus decisions to the interim tables and emit the corpus.

The decisions are the ones recorded in the final markdown cell of
notebooks/gcn_corpus/A_eda.ipynb. They are the complete and closed set: this
script adds no rule of its own. It records what the extraction rules emit, so
the three rule defects named in the notebook -- misassigned uncertainty on
multi-magnitude table rows, classification labels landing in the instrument
field, and a subject phrasing no negative-statement rule covers -- are carried
through untouched and unfiltered.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import math
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from skyportal_corpus.extraction_v2.annotations import EventEvidenceAnnotation
from skyportal_corpus.extraction_v2.photometry_annotations import (
    PhotometricMeasurementAnnotation,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INPUT_DIR = PROJECT_ROOT / "data" / "interim" / "gcn_corpus"
OUTPUT_DIR = PROJECT_ROOT / "data" / "gcn_corpus"
REPLACEMENT_CHARACTER = "�"
OUTPUT_TABLES = [
    "circulars.parquet",
    "evidence_spans.parquet",
    "photometry_spans.parquet",
    "vocabulary_coverage.parquet",
]

EXPECTED_CIRCULARS = 12_012
EXPECTED_EVIDENCE = 63_277
EXPECTED_PHOTOMETRY = 37_795
EXPECTED_OFFSETS = EXPECTED_EVIDENCE + EXPECTED_PHOTOMETRY
EXPECTED_SPAN_MOJIBAKE = 4
EXPECTED_CIRCULAR_MOJIBAKE = 39
EXPECTED_WAS_EDITED = 653
EXPECTED_NO_ANNOTATIONS = 57
EXPECTED_EVIDENCE_PARTIAL_PAIRS = 1_251
EXPECTED_PHOTOMETRY_IDENTICAL_GROUPS = 407
EXPECTED_EXPOSURE_PARSE_FAILURES = 2_572

# Free-text columns decision 8 leaves exactly as the rules emitted them.
FREE_TEXT_COLUMNS = {
    "evidence_spans": ["text", "value", "unit", "comment", "target"],
    "photometry_spans": [
        "text",
        "magnitude_or_limit",
        "magnitude_error",
        "limit_sigma",
        "unit",
        "photometric_band",
        "photometric_system",
        "obs_time_raw",
        "exposure_time_raw",
        "instrument",
        "comment",
    ],
}

DECISION_TITLES = {
    1: "span key is unique",
    2: "drop source_circular_id",
    3: "flag overlapping spans",
    4: "retain every circular, add annotation counts",
    5: "retain needs_review and comment",
    6: "flag mojibake",
    7: "add exposure_time_numeric",
    8: "normalise no free-text value",
    9: "retain text byte for byte",
    10: "created_on_utc is the public time",
    11: "retain provenance_inherited",
    12: "retain the declared vocabularies whole",
    13: "write the manifest",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_prior_output_hashes() -> tuple[dict[str, str], str | None] | None:
    """Hash a complete prior output set so this run can prove it is idempotent."""

    manifest_path = OUTPUT_DIR / "manifest.json"
    table_paths = [OUTPUT_DIR / name for name in OUTPUT_TABLES]
    if not manifest_path.is_file() or not all(path.is_file() for path in table_paths):
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    hashes = {path.name: sha256_file(path) for path in table_paths}
    hashes[manifest_path.name] = sha256_file(manifest_path)
    return hashes, manifest.get("script_sha256")


def stop(reason: str, rows: pd.DataFrame | None = None) -> None:
    """Fail loudly, printing the offending rows before leaving."""

    print(f"\nSTOP: {reason}")
    if rows is not None:
        with pd.option_context("display.max_columns", None, "display.width", 200):
            print(rows.to_string())
    raise SystemExit(1)


def effect(
    decision: int,
    table: str,
    rows_before: int,
    rows_after: int,
    rows_affected: int,
    columns_added: list[str],
    columns_dropped: list[str],
    note: str,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "decision": decision,
        "title": DECISION_TITLES[decision],
        "table": table,
        "rows_before": rows_before,
        "rows_after": rows_after,
        "rows_affected": rows_affected,
        "columns_added": columns_added,
        "columns_dropped": columns_dropped,
        "note": note,
        "detail": detail or {},
    }


def string_columns(frame: pd.DataFrame) -> list[str]:
    return [name for name in frame.columns if frame[name].dtype == object]


def contains_replacement_character(series: pd.Series) -> pd.Series:
    return series.map(
        lambda value: isinstance(value, str) and REPLACEMENT_CHARACTER in value
    )


def overlap_report(frame: pd.DataFrame, table: str) -> dict[str, Any]:
    """Find every span that intersects another span in the same circular.

    Both shapes count: a partial overlap, and two spans at identical offsets.
    Nothing is removed or resolved; the caller only sets a flag.
    """

    partial_pairs = 0
    crossings = 0
    boundary_sharing = 0
    strictly_nested = 0
    identical_pairs = 0
    identical_groups = 0
    flagged_index: set[Any] = set()
    partial_index: set[Any] = set()
    identical_index: set[Any] = set()

    for _, group in frame.groupby("circular_id", sort=False):
        spans = sorted(
            zip(group["span_start"], group["span_end"], group.index),
            key=lambda item: (item[0], item[1]),
        )
        group_sizes: dict[tuple[int, int], int] = {}
        for start, end, _ in spans:
            group_sizes[(start, end)] = group_sizes.get((start, end), 0) + 1
        identical_groups += sum(1 for size in group_sizes.values() if size > 1)

        for position, (start, end, index) in enumerate(spans):
            for other_start, other_end, other_index in spans[position + 1 :]:
                if other_start >= end:
                    break
                flagged_index.update((index, other_index))
                if start == other_start and end == other_end:
                    identical_pairs += 1
                    identical_index.update((index, other_index))
                    continue
                partial_pairs += 1
                partial_index.update((index, other_index))
                if start == other_start or end == other_end:
                    boundary_sharing += 1
                elif other_end < end:
                    # The later span starts after this one and ends before it.
                    strictly_nested += 1
                else:
                    crossings += 1

    flagged = pd.Series(frame.index.isin(sorted(flagged_index)), index=frame.index)
    return {
        "table": table,
        "flagged": flagged,
        "flagged_count": int(flagged.sum()),
        "partial_pairs": partial_pairs,
        "crossings": crossings,
        "boundary_sharing": boundary_sharing,
        "strictly_nested": strictly_nested,
        "identical_pairs": identical_pairs,
        "identical_groups": identical_groups,
        "partial_index": partial_index,
        "identical_index": identical_index,
    }


def declared_vocabularies(model: type[Any]) -> dict[str, frozenset[str]]:
    """Read the declared vocabularies off the model's own validators.

    Each field validator that checks membership names its tagset in the module
    namespace of the model. Nothing here is a hardcoded list of values.
    """

    namespace = vars(inspect.getmodule(model))
    vocabularies: dict[str, frozenset[str]] = {}
    for decorator in model.__pydantic_decorators__.field_validators.values():
        function = getattr(decorator.func, "__func__", decorator.func)
        referenced = [
            namespace[name]
            for name in function.__code__.co_names
            if isinstance(namespace.get(name), frozenset)
        ]
        if len(referenced) != 1:
            continue
        for field in decorator.info.fields:
            vocabularies[field] = referenced[0]
    return vocabularies


# --------------------------------------------------------------------------
# The thirteen decisions
# --------------------------------------------------------------------------


def d01_verify_span_key(
    evidence: pd.DataFrame, photometry: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """1 - (circular_id, layer, span_start, span_end, span_index) is unique."""

    keyed = pd.concat(
        [
            evidence[["circular_id", "span_start", "span_end", "span_index"]].assign(
                layer="EVENT_EVIDENCE"
            ),
            photometry[["circular_id", "span_start", "span_end", "span_index"]].assign(
                layer="PHOTOMETRIC_MEASUREMENT"
            ),
        ],
        ignore_index=True,
    )
    key = ["circular_id", "layer", "span_start", "span_end", "span_index"]
    duplicated = keyed.duplicated(subset=key, keep=False)
    if duplicated.any():
        stop(
            f"the span key is not unique on {int(duplicated.sum())} rows",
            keyed.loc[duplicated].sort_values(key),
        )
    return (
        evidence,
        photometry,
        effect(
            1,
            "evidence_spans + photometry_spans",
            len(keyed),
            len(keyed),
            0,
            [],
            [],
            f"{len(keyed)} keys, all distinct; span_index separates the "
            f"{EXPECTED_PHOTOMETRY_IDENTICAL_GROUPS} photometry offset ranges "
            "that carry more than one annotation",
        ),
    )


def d02_drop_source_circular_id(
    evidence: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """2 - drop the column no rule writes, after proving it is empty."""

    column = "source_circular_id"
    if column not in evidence.columns:
        stop(f"{column} is absent from evidence_spans; nothing to verify")
    populated = evidence[column].notna()
    if populated.any():
        stop(
            f"{column} is populated on {int(populated.sum())} rows and cannot be dropped",
            evidence.loc[populated, ["circular_id", "span_start", "span_end", column]],
        )
    rows_before = len(evidence)
    evidence = evidence.drop(columns=[column])
    return (
        evidence,
        effect(
            2,
            "evidence_spans",
            rows_before,
            len(evidence),
            0,
            [],
            [column],
            f"dropped from all {rows_before} rows; 0 populated values discarded",
        ),
    )


def d03_flag_overlapping_spans(
    evidence: pd.DataFrame, photometry: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """3 - add is_overlapping to both span tables. Nothing is resolved."""

    evidence_report = overlap_report(evidence, "evidence_spans")
    photometry_report = overlap_report(photometry, "photometry_spans")
    evidence = evidence.copy()
    photometry = photometry.copy()
    evidence["is_overlapping"] = evidence_report["flagged"].astype(bool)
    photometry["is_overlapping"] = photometry_report["flagged"].astype(bool)
    affected = evidence_report["flagged_count"] + photometry_report["flagged_count"]
    return (
        evidence,
        photometry,
        effect(
            3,
            "evidence_spans + photometry_spans",
            len(evidence) + len(photometry),
            len(evidence) + len(photometry),
            affected,
            ["is_overlapping"],
            [],
            f"{evidence_report['flagged_count']} evidence spans and "
            f"{photometry_report['flagged_count']} photometry spans intersect another "
            "span in the same circular and layer; every one is retained",
            {"evidence": evidence_report, "photometry": photometry_report},
        ),
    )


def d04_add_annotation_counts(
    circulars: pd.DataFrame, evidence: pd.DataFrame, photometry: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """4 - retain every circular, including those that produced nothing."""

    rows_before = len(circulars)
    circulars = circulars.copy()
    evidence_counts = evidence.groupby("circular_id").size()
    photometry_counts = photometry.groupby("circular_id").size()
    circulars["n_evidence"] = (
        circulars["circular_id"].map(evidence_counts).fillna(0).astype("int64")
    )
    circulars["n_photometry"] = (
        circulars["circular_id"].map(photometry_counts).fillna(0).astype("int64")
    )
    circulars["has_annotations"] = (
        circulars["n_evidence"] + circulars["n_photometry"]
    ) > 0
    unknown_evidence = set(evidence_counts.index) - set(circulars["circular_id"])
    unknown_photometry = set(photometry_counts.index) - set(circulars["circular_id"])
    if unknown_evidence or unknown_photometry:
        stop(
            "annotations reference circular ids absent from the circulars table: "
            f"{sorted(unknown_evidence | unknown_photometry)[:20]}"
        )
    silent = int((~circulars["has_annotations"]).sum())
    if len(circulars) != rows_before:
        stop("the circulars table changed length while counting annotations")
    return (
        circulars,
        effect(
            4,
            "circulars",
            rows_before,
            len(circulars),
            rows_before,
            ["n_evidence", "n_photometry", "has_annotations"],
            [],
            f"all {rows_before} circulars retained; {silent} produced no annotation "
            "in either layer and are kept with zero counts",
        ),
    )


def d05_retain_review_fields(
    evidence: pd.DataFrame,
    photometry: pd.DataFrame,
    source_evidence: pd.DataFrame,
    source_photometry: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """5 - needs_review and comment survive unchanged in both layers."""

    for table, current, source in [
        ("evidence_spans", evidence, source_evidence),
        ("photometry_spans", photometry, source_photometry),
    ]:
        for column in ("needs_review", "comment"):
            if column not in current.columns:
                stop(f"{column} is missing from {table}")
            if not current[column].equals(source[column]):
                differing = current[column].ne(source[column]) & (
                    current[column].notna() | source[column].notna()
                )
                stop(
                    f"{column} changed on {int(differing.sum())} rows of {table}",
                    current.loc[differing, ["circular_id", "span_start", "span_end", column]],
                )

    flagged_evidence = int(evidence["needs_review"].sum())
    flagged_photometry = int(photometry["needs_review"].sum())
    flagged = flagged_evidence + flagged_photometry
    missing_comment = int(
        (evidence["needs_review"] & evidence["comment"].isna()).sum()
        + (photometry["needs_review"] & photometry["comment"].isna()).sum()
    )
    if missing_comment:
        stop(f"{missing_comment} rows are flagged for review without a comment")
    return (
        evidence,
        photometry,
        effect(
            5,
            "evidence_spans + photometry_spans",
            len(evidence) + len(photometry),
            len(evidence) + len(photometry),
            0,
            [],
            [],
            f"{flagged} annotations carry needs_review ({flagged_evidence} evidence, "
            f"{flagged_photometry} photometry), every one with a comment; none altered",
        ),
    )


def d06_flag_mojibake(
    circulars: pd.DataFrame, evidence: pd.DataFrame, photometry: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """6 - flag U+FFFD wherever it survives. Values are not repaired."""

    frames = []
    counts = {}
    field_hits: dict[str, dict[str, int]] = {}
    for table, frame, columns in [
        ("circulars", circulars, ["canonical_text"]),
        ("evidence_spans", evidence, string_columns(evidence)),
        ("photometry_spans", photometry, string_columns(photometry)),
    ]:
        frame = frame.copy()
        flag = pd.Series(False, index=frame.index)
        hits: dict[str, int] = {}
        for column in columns:
            column_flag = contains_replacement_character(frame[column])
            if column_flag.any():
                hits[column] = int(column_flag.sum())
            flag |= column_flag
        frame["has_mojibake"] = flag
        counts[table] = int(flag.sum())
        field_hits[table] = hits
        frames.append(frame)

    circulars, evidence, photometry = frames
    span_total = counts["evidence_spans"] + counts["photometry_spans"]
    return (
        circulars,
        evidence,
        photometry,
        effect(
            6,
            "circulars + evidence_spans + photometry_spans",
            len(circulars) + len(evidence) + len(photometry),
            len(circulars) + len(evidence) + len(photometry),
            counts["circulars"] + span_total,
            ["has_mojibake"],
            [],
            f"{span_total} annotations and {counts['circulars']} circulars carry the "
            f"replacement character; fields hit: {field_hits}; no value repaired",
            {"counts": counts, "fields": field_hits},
        ),
    )


def d07_add_exposure_time_numeric(
    photometry: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """7 - a typed column beside the raw one. The raw value is retained."""

    raw_column = "exposure_time_raw"
    numeric_column = "exposure_time_numeric"
    photometry = photometry.copy()
    raw = photometry[raw_column]

    def parse(value: Any) -> float | None:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(parsed):
            stop(
                f"{raw_column} value {value!r} parses to the non-finite float {parsed!r}, "
                "which a null in the typed column cannot be distinguished from"
            )
        return parsed

    numeric = raw.map(parse)
    populated = raw.notna()
    failures = populated & numeric.isna()
    photometry.insert(
        photometry.columns.get_loc(raw_column) + 1,
        numeric_column,
        numeric.astype("float64"),
    )
    if not photometry[raw_column].equals(raw):
        stop(f"{raw_column} changed while the typed column was added")
    failing_values = raw.loc[failures]
    return (
        photometry,
        effect(
            7,
            "photometry_spans",
            len(photometry),
            len(photometry),
            int(populated.sum()),
            [numeric_column],
            [],
            f"{int(populated.sum())} populated raw values, of which "
            f"{int(failures.sum())} do not parse across "
            f"{failing_values.nunique()} distinct forms and hold null",
            {
                "populated": int(populated.sum()),
                "failures": int(failures.sum()),
                "distinct_failing_forms": int(failing_values.nunique()),
                "examples": failing_values.drop_duplicates().head(5).tolist(),
            },
        ),
    )


def d08_normalise_no_free_text(
    evidence: pd.DataFrame,
    photometry: pd.DataFrame,
    source_evidence: pd.DataFrame,
    source_photometry: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """8 - no mapping, no trimming, no recoding of any free-text value."""

    checked = 0
    for table, current, source in [
        ("evidence_spans", evidence, source_evidence),
        ("photometry_spans", photometry, source_photometry),
    ]:
        for column in FREE_TEXT_COLUMNS[table]:
            if column not in current.columns:
                stop(f"{column} is missing from {table}")
            if not current[column].equals(source[column]):
                differing = current[column].ne(source[column]) & (
                    current[column].notna() | source[column].notna()
                )
                stop(
                    f"{column} was altered on {int(differing.sum())} rows of {table}",
                    current.loc[differing, ["circular_id", "span_start", "span_end", column]],
                )
            checked += 1
    return (
        evidence,
        photometry,
        effect(
            8,
            "evidence_spans + photometry_spans",
            len(evidence) + len(photometry),
            len(evidence) + len(photometry),
            0,
            [],
            [],
            f"{checked} free-text columns verified byte for byte against the interim "
            "tables; band, instrument, value, unit and comment left as the rules emitted them",
        ),
    )


def d09_verify_offsets(
    circulars: pd.DataFrame, evidence: pd.DataFrame, photometry: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """9 - canonical_text[span_start:span_end] still equals text, everywhere."""

    canonical = dict(zip(circulars["circular_id"], circulars["canonical_text"]))
    verified = 0
    failures = 0
    for table, frame in [("evidence_spans", evidence), ("photometry_spans", photometry)]:
        for circular_id, start, end, text in zip(
            frame["circular_id"], frame["span_start"], frame["span_end"], frame["text"]
        ):
            document = canonical.get(circular_id)
            if document is None:
                stop(f"{table}: circular {circular_id} is absent from the circulars table")
            if document[start:end] != text:
                failures += 1
                print(f"\nSTOP: offset verification failed in {table}")
                print(f"  circular_id: {circular_id}")
                print(f"  offsets: {start}:{end}")
                print(f"  stored text:   {text!r}")
                print(f"  selected text: {document[start:end]!r}")
                raise SystemExit(1)
            verified += 1
    return (
        evidence,
        photometry,
        effect(
            9,
            "evidence_spans + photometry_spans",
            verified,
            verified,
            0,
            [],
            [],
            f"{verified} annotations re-verified against canonical_text, {failures} failures; "
            "trailing whitespace retained",
        ),
    )


def d10_verify_public_timestamp(
    circulars: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """10 - created_on_utc is the public time; was_edited marks a later edit."""

    created = circulars["created_on_utc"]
    edited = circulars["edited_on_utc"]
    missing = created.isna()
    if missing.any():
        stop(
            f"created_on_utc is null on {int(missing.sum())} rows",
            circulars.loc[missing, ["circular_id", "created_on_utc", "edited_on_utc"]],
        )
    parsed = pd.to_datetime(created, utc=True, format="ISO8601")
    if parsed.isna().any():
        stop(
            "created_on_utc holds values that do not parse as ISO-8601",
            circulars.loc[parsed.isna(), ["circular_id", "created_on_utc"]],
        )
    not_utc = ~created.str.endswith("+00:00")
    if not_utc.any():
        stop(
            f"created_on_utc carries a non-UTC offset on {int(not_utc.sum())} rows",
            circulars.loc[not_utc, ["circular_id", "created_on_utc"]],
        )
    expected = edited.notna() & edited.ne(created)
    mismatch = expected.ne(circulars["was_edited"])
    if mismatch.any():
        stop(
            f"was_edited disagrees with the timestamps on {int(mismatch.sum())} rows",
            circulars.loc[
                mismatch,
                ["circular_id", "created_on_utc", "edited_on_utc", "was_edited"],
            ],
        )
    edited_count = int(expected.sum())
    return (
        circulars,
        effect(
            10,
            "circulars",
            len(circulars),
            len(circulars),
            0,
            [],
            [],
            f"created_on_utc non-null and UTC on all {len(circulars)} rows; was_edited "
            f"already true on exactly the {edited_count} circulars with a differing edit "
            "timestamp",
        ),
    )


def d11_retain_provenance_inherited(
    photometry: pd.DataFrame, source_photometry: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """11 - the serialised JSON string stays exactly as it stands."""

    column = "provenance_inherited"
    if column not in photometry.columns:
        stop(f"{column} is missing from photometry_spans")
    if not photometry[column].equals(source_photometry[column]):
        differing = photometry[column].ne(source_photometry[column])
        stop(
            f"{column} changed on {int(differing.sum())} rows",
            photometry.loc[differing, ["circular_id", "span_start", "span_end", column]],
        )
    non_string = photometry[column].map(lambda value: not isinstance(value, str))
    if non_string.any():
        stop(
            f"{column} is not a serialised string on {int(non_string.sum())} rows",
            photometry.loc[non_string, ["circular_id", "span_start", "span_end", column]],
        )
    populated = int(photometry[column].ne("[]").sum())
    return (
        photometry,
        effect(
            11,
            "photometry_spans",
            len(photometry),
            len(photometry),
            0,
            [],
            [],
            f"retained as a JSON string on all {len(photometry)} rows, "
            f"{photometry[column].nunique()} distinct values, {populated} carrying at "
            "least one token",
        ),
    )


def d12_emit_vocabulary_coverage(
    evidence: pd.DataFrame, photometry: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """12 - the declared vocabularies whole, including values no rule emits."""

    rows: list[dict[str, Any]] = []
    for layer, model, frame in [
        ("EVENT_EVIDENCE", EventEvidenceAnnotation, evidence),
        ("PHOTOMETRIC_MEASUREMENT", PhotometricMeasurementAnnotation, photometry),
    ]:
        vocabularies = declared_vocabularies(model)
        if not vocabularies:
            stop(f"no declared vocabulary was found on {model.__name__}")
        for field in sorted(vocabularies):
            if field not in frame.columns:
                stop(f"{field} is declared on {model.__name__} but absent from the table")
            counts = frame[field].value_counts()
            undeclared = set(counts.index) - set(vocabularies[field])
            if undeclared:
                stop(
                    f"{layer}.{field} holds values outside its declared vocabulary: "
                    f"{sorted(undeclared)}"
                )
            for value in sorted(vocabularies[field]):
                rows.append(
                    {
                        "layer": layer,
                        "field": field,
                        "declared_value": value,
                        "rows": int(counts.get(value, 0)),
                    }
                )

    coverage = pd.DataFrame(rows, columns=["layer", "field", "declared_value", "rows"])
    unused = int((coverage["rows"] == 0).sum())
    return (
        coverage,
        effect(
            12,
            "vocabulary_coverage",
            0,
            len(coverage),
            len(coverage),
            ["layer", "field", "declared_value", "rows"],
            [],
            f"{len(coverage)} declared values across "
            f"{coverage['field'].nunique()} fields read from the models at runtime; "
            f"{unused} appear on zero rows and are listed with 0",
        ),
    )


def d13_write_manifest(
    interim_manifest: dict[str, Any],
    written: dict[str, Path],
    row_counts: dict[str, int],
    effects: list[dict[str, Any]],
    rule_inventory: dict[str, int],
    input_hashes: dict[str, str],
    script_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """13 - the manifest that tells two generations of the corpus apart."""

    applied = [*effects, {"decision": 13, "title": DECISION_TITLES[13],
                          "table": "manifest.json", "rows_affected": 1,
                          "columns_added": [], "columns_dropped": []}]
    manifest = {
        "run_timestamp": interim_manifest["run_timestamp"],
        "run_timestamp_source": (
            "data/interim/gcn_corpus/manifest.json:run_timestamp, carried forward so "
            "the corpus is a pure function of its input"
        ),
        "script_sha256": script_sha256,
        "input_sha256": input_hashes,
        "extractors": interim_manifest["extractors"],
        "schema_versions": interim_manifest["schema_versions"],
        "rule_inventory": dict(sorted(rule_inventory.items())),
        "rule_inventory_source": (
            "rule_id counted across both interim span tables; the interim manifest "
            "carries no rule inventory"
        ),
        "row_counts": dict(sorted(row_counts.items())),
        "decisions_applied": [
            {
                "decision": item["decision"],
                "title": item["title"],
                "table": item["table"],
                "rows_affected": item["rows_affected"],
                "columns_added": item["columns_added"],
                "columns_dropped": item["columns_dropped"],
            }
            for item in applied
        ],
        "output_sha256": {
            name: sha256_file(path) for name, path in sorted(written.items())
        },
    }
    manifest_path = OUTPUT_DIR / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return (
        manifest,
        effect(
            13,
            "manifest.json",
            0,
            1,
            1,
            ["run_timestamp", "extractors", "rule_inventory", "row_counts",
             "decisions_applied", "output_sha256"],
            [],
            f"{len(manifest['extractors'])} extractors and {len(rule_inventory)} rules "
            f"recorded, with the sha256 of each of the {len(written)} output tables",
        ),
    )


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------


def write_parquet(path: Path, frame: pd.DataFrame) -> None:
    if frame.empty:
        raise SystemExit(f"Refusing to write an empty table: {path}")
    table = pa.Table.from_pandas(frame, preserve_index=False)
    pq.write_table(table, path, compression="zstd")


def print_controls(controls: list[tuple[str, bool, str, str]]) -> None:
    print("\n1. CONTROLS")
    width = max(len(name) for name, _, _, _ in controls)
    print(f"| {'control'.ljust(width)} | status | observed | expected |")
    print(f"|{'-' * (width + 2)}|--------|----------|----------|")
    for name, passed, observed, expected in controls:
        print(f"| {name.ljust(width)} | {'PASS' if passed else 'FAIL'} | {observed} | {expected} |")
    failed = [name for name, passed, _, _ in controls if not passed]
    if failed:
        raise SystemExit(f"Controls failed: {failed}. No output table was written.")


def main() -> None:
    script_sha256 = sha256_file(Path(__file__).resolve())
    prior_output = read_prior_output_hashes()
    interim_manifest = json.loads((INPUT_DIR / "manifest.json").read_text(encoding="utf-8"))
    input_paths = {
        "circulars.parquet": INPUT_DIR / "circulars.parquet",
        "evidence_spans.parquet": INPUT_DIR / "evidence_spans.parquet",
        "photometry_spans.parquet": INPUT_DIR / "photometry_spans.parquet",
    }
    input_hashes = {name: sha256_file(path) for name, path in input_paths.items()}
    circulars = pd.read_parquet(input_paths["circulars.parquet"])
    evidence = pd.read_parquet(input_paths["evidence_spans.parquet"])
    photometry = pd.read_parquet(input_paths["photometry_spans.parquet"])
    if circulars.empty or evidence.empty or photometry.empty:
        raise SystemExit(
            "Refusing to run on an empty interim table: "
            f"circulars={len(circulars)}, evidence={len(evidence)}, "
            f"photometry={len(photometry)}"
        )
    source_evidence = evidence.copy()
    source_photometry = photometry.copy()
    rule_inventory = (
        pd.concat([evidence["rule_id"], photometry["rule_id"]], ignore_index=True)
        .value_counts()
        .to_dict()
    )
    rule_inventory = {str(key): int(value) for key, value in rule_inventory.items()}

    print("Interim tables read:")
    for name, path in input_paths.items():
        print(f"  {name}: {input_hashes[name]}")
    print(f"Interim run_timestamp: {interim_manifest['run_timestamp']}")

    effects: list[dict[str, Any]] = []
    evidence, photometry, item = d01_verify_span_key(evidence, photometry)
    effects.append(item)
    evidence, item = d02_drop_source_circular_id(evidence)
    effects.append(item)
    evidence, photometry, item = d03_flag_overlapping_spans(evidence, photometry)
    effects.append(item)
    overlap_detail = item["detail"]
    circulars, item = d04_add_annotation_counts(circulars, evidence, photometry)
    effects.append(item)
    evidence, photometry, item = d05_retain_review_fields(
        evidence, photometry, source_evidence, source_photometry
    )
    effects.append(item)
    circulars, evidence, photometry, item = d06_flag_mojibake(circulars, evidence, photometry)
    effects.append(item)
    mojibake_detail = item["detail"]
    photometry, item = d07_add_exposure_time_numeric(photometry)
    effects.append(item)
    exposure_detail = item["detail"]
    evidence, photometry, item = d08_normalise_no_free_text(
        evidence, photometry, source_evidence, source_photometry
    )
    effects.append(item)
    evidence, photometry, item = d09_verify_offsets(circulars, evidence, photometry)
    effects.append(item)
    offsets_verified = item["rows_before"]
    circulars, item = d10_verify_public_timestamp(circulars)
    effects.append(item)
    photometry, item = d11_retain_provenance_inherited(photometry, source_photometry)
    effects.append(item)
    coverage, item = d12_emit_vocabulary_coverage(evidence, photometry)
    effects.append(item)

    evidence_overlap = overlap_detail["evidence"]
    photometry_overlap = overlap_detail["photometry"]
    evidence_partial_flagged = all(
        bool(evidence["is_overlapping"].at[index]) for index in evidence_overlap["partial_index"]
    )
    photometry_identical_flagged = all(
        bool(photometry["is_overlapping"].at[index])
        for index in photometry_overlap["identical_index"]
    )
    span_mojibake = (
        mojibake_detail["counts"]["evidence_spans"]
        + mojibake_detail["counts"]["photometry_spans"]
    )
    controls = [
        ("circulars", len(circulars) == EXPECTED_CIRCULARS, f"{len(circulars):,} rows", f"{EXPECTED_CIRCULARS:,} rows"),
        ("evidence_spans", len(evidence) == EXPECTED_EVIDENCE, f"{len(evidence):,} rows", f"{EXPECTED_EVIDENCE:,} rows"),
        ("photometry_spans", len(photometry) == EXPECTED_PHOTOMETRY, f"{len(photometry):,} rows", f"{EXPECTED_PHOTOMETRY:,} rows"),
        (
            "source_circular_id dropped",
            "source_circular_id" not in evidence.columns,
            "column absent from output" if "source_circular_id" not in evidence.columns else "column present",
            "column absent from output",
        ),
        ("span key unique", True, "True, both tables", "True, both tables"),
        (
            "offsets re-verified",
            offsets_verified == EXPECTED_OFFSETS,
            f"{offsets_verified:,}, 0 failures",
            f"{EXPECTED_OFFSETS:,}, 0 failures",
        ),
        (
            "has_mojibake true",
            span_mojibake == EXPECTED_SPAN_MOJIBAKE,
            f"{span_mojibake} across both span tables",
            f"{EXPECTED_SPAN_MOJIBAKE} across both span tables",
        ),
        (
            "circulars has_mojibake true",
            mojibake_detail["counts"]["circulars"] == EXPECTED_CIRCULAR_MOJIBAKE,
            str(mojibake_detail["counts"]["circulars"]),
            str(EXPECTED_CIRCULAR_MOJIBAKE),
        ),
        (
            "was_edited true",
            int(circulars["was_edited"].sum()) == EXPECTED_WAS_EDITED,
            str(int(circulars["was_edited"].sum())),
            str(EXPECTED_WAS_EDITED),
        ),
        (
            "has_annotations false",
            int((~circulars["has_annotations"]).sum()) == EXPECTED_NO_ANNOTATIONS,
            str(int((~circulars["has_annotations"]).sum())),
            str(EXPECTED_NO_ANNOTATIONS),
        ),
        (
            "created_on_utc nulls",
            int(circulars["created_on_utc"].isna().sum()) == 0,
            str(int(circulars["created_on_utc"].isna().sum())),
            "0",
        ),
        (
            "is_overlapping true, evidence",
            evidence_overlap["partial_pairs"] == EXPECTED_EVIDENCE_PARTIAL_PAIRS
            and evidence_partial_flagged,
            f"{len(evidence_overlap['partial_index'])} spans of "
            f"{evidence_overlap['partial_pairs']:,} pairs, all flagged",
            f"every span in the {EXPECTED_EVIDENCE_PARTIAL_PAIRS:,} pairs",
        ),
        (
            "is_overlapping true, photometry",
            photometry_overlap["identical_groups"] == EXPECTED_PHOTOMETRY_IDENTICAL_GROUPS
            and photometry_identical_flagged,
            f"{len(photometry_overlap['identical_index'])} spans of "
            f"{photometry_overlap['identical_groups']} groups, all flagged",
            f"every span in the {EXPECTED_PHOTOMETRY_IDENTICAL_GROUPS} groups",
        ),
        (
            "exposure_time_numeric null",
            exposure_detail["failures"] == EXPECTED_EXPOSURE_PARSE_FAILURES,
            f"{exposure_detail['failures']:,} where raw is populated",
            f"{EXPECTED_EXPOSURE_PARSE_FAILURES:,} where raw is populated",
        ),
    ]
    print_controls(controls)

    outputs = {
        "circulars.parquet": circulars,
        "evidence_spans.parquet": evidence,
        "photometry_spans.parquet": photometry,
        "vocabulary_coverage.parquet": coverage,
    }
    for name, frame in outputs.items():
        if frame.empty:
            raise SystemExit(f"Refusing to write an empty table: {name}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    written = {name: OUTPUT_DIR / name for name in outputs}
    for name, frame in outputs.items():
        write_parquet(written[name], frame)
    manifest, item = d13_write_manifest(
        interim_manifest,
        written,
        {name: len(frame) for name, frame in outputs.items()},
        effects,
        rule_inventory,
        input_hashes,
        script_sha256,
    )
    effects.append(item)

    print("\n2. EFFECT LOG")
    for record in effects:
        print(
            f"  {record['decision']:>2}. {record['title']} | table={record['table']} | "
            f"rows {record['rows_before']:,} -> {record['rows_after']:,} | "
            f"affected={record['rows_affected']:,} | "
            f"+{record['columns_added'] or '[]'} | -{record['columns_dropped'] or '[]'}"
        )
        print(f"      {record['note']}")

    print("\n3. OUTPUT TABLES")
    for name, frame in outputs.items():
        print(f"  {name}: {len(frame):,} rows, {len(frame.columns)} columns")
        print(f"    columns: {list(frame.columns)}")

    print("\n4. VOCABULARY COVERAGE")
    print(f"  | {'layer'.ljust(23)} | {'field'.ljust(21)} | {'declared_value'.ljust(29)} | {'rows'.rjust(6)} |")
    print(f"  |{'-' * 25}|{'-' * 23}|{'-' * 31}|{'-' * 8}|")
    for row in coverage.to_dict(orient="records"):
        count = f"{row['rows']:,}"
        print(
            f"  | {row['layer'].ljust(23)} | {row['field'].ljust(21)} | "
            f"{row['declared_value'].ljust(29)} | {count.rjust(6)} |"
        )

    print("\n5. DECISION 7 DETAIL: exposure_time_raw parse failures")
    print(f"  populated raw values: {exposure_detail['populated']:,}")
    print(f"  parse failures held as null: {exposure_detail['failures']:,}")
    print(f"  distinct failing forms: {exposure_detail['distinct_failing_forms']:,}")
    for example in exposure_detail["examples"]:
        print(f"    {example!r}")

    print("\n6. DECISION 3 DETAIL: is_overlapping true counts per layer")
    for report in (evidence_overlap, photometry_overlap):
        print(
            f"  {report['table']}: {report['flagged_count']:,} spans flagged | "
            f"partial pairs {report['partial_pairs']:,} "
            f"(crossings {report['crossings']:,}, boundary {report['boundary_sharing']}, "
            f"nested {report['strictly_nested']}) | "
            f"identical-offset pairs {report['identical_pairs']} in "
            f"{report['identical_groups']} groups"
        )

    print("\n7. UNCOVERED CASES")
    print(
        "  PHOTOMETRIC_SYSTEMS is declared in extraction_v2/photometry_tagsets.py but no\n"
        "  model validator references it, so photometric_system carries no declared\n"
        "  vocabulary at runtime and is absent from vocabulary_coverage. Decision 12 reads\n"
        "  the models, so the value set is left untouched and reported here rather than\n"
        "  added by a rule of this script."
    )
    print(
        "  The interim manifest carries no rule inventory. Decision 13 takes the extractor\n"
        "  ids and versions from it and counts rule_id across the two interim span tables\n"
        "  instead, recorded under rule_inventory_source."
    )

    print("\n8. DETERMINISM")
    output_hashes = manifest["output_sha256"]
    manifest_path = OUTPUT_DIR / "manifest.json"
    all_hashes = {**output_hashes, "manifest.json": sha256_file(manifest_path)}
    for name in sorted(all_hashes):
        print(f"  {name}: {all_hashes[name]}")
    if prior_output is None:
        print("  No complete prior output set was available; run again to compare.")
    else:
        prior_hashes, prior_script_sha256 = prior_output
        if prior_script_sha256 != script_sha256:
            print("  The prior output came from a different script revision; comparison deferred.")
        else:
            identical = prior_hashes == all_hashes
            print(f"  Consecutive-run hashes identical: {'PASS' if identical else 'FAIL'}")
            if not identical:
                changed = [name for name in all_hashes if prior_hashes.get(name) != all_hashes[name]]
                raise SystemExit(f"Determinism failure: {changed} changed across runs.")

    print("\n9. GIT STATUS")
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    print(status.stdout, end="")


if __name__ == "__main__":
    main()
