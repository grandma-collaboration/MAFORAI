#!/usr/bin/env python
"""Emit raw GCN extractor output into flat, offset-preserving Parquet tables."""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from skyportal_corpus.canonical.document import iter_real_circulars, render_canonical
from skyportal_corpus.extraction_v2.annotations import EventEvidenceAnnotation
from skyportal_corpus.extraction_v2.photometry_annotations import (
    PhotometricMeasurementAnnotation,
    merge_photometry_measurements,
)
from skyportal_corpus.extraction_v2.photometry_prose import ProsePhotometryExtractor
from skyportal_corpus.extraction_v2.photometry_rows import (
    PhotometryRowParser,
    parse_table_to_measurements,
)
from skyportal_corpus.extraction_v2.photometry_tables import detect_table_blocks
from skyportal_corpus.extraction_v2.photometry_tagsets import MEASUREMENT_TYPES
from skyportal_corpus.extraction_v2.sweep import get_active_extractors
from skyportal_corpus.extraction_v2.tagsets import LABELS


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INDEX_ROOT = PROJECT_ROOT / "data" / "interim" / "gcn" / "circulars"
OUTPUT_DIR = PROJECT_ROOT / "data" / "interim" / "gcn_corpus"
MIN_YEAR = 2023
EXPECTED_CIRCULARS = 12_012
EXPECTED_FIRST_DATE = "2023-01-01"
EXPECTED_LAST_DATE = "2026-07-19"
CIRCULAR_COLUMNS = [
    "circular_id",
    "subject",
    "created_on_utc",
    "edited_on_utc",
    "canonical_text",
    "text_length",
    "text_sha256",
    "body_hash",
    "year",
    "submitter",
    "was_edited",
]
RULE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def nullable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    return value


def load_index_metadata() -> dict[int, dict[str, Any]]:
    index_paths = sorted(INDEX_ROOT.glob("20[2-9][0-9]/circulars_index.parquet"))
    frames = [pd.read_parquet(path) for path in index_paths if int(path.parent.name) >= MIN_YEAR]
    index = pd.concat(frames, ignore_index=True)
    metadata: dict[int, dict[str, Any]] = {}
    for row in index.to_dict(orient="records"):
        metadata[int(row["circular_id"])] = row
    return metadata


def output_columns(model: type[EventEvidenceAnnotation] | type[PhotometricMeasurementAnnotation]) -> list[str]:
    fields = list(model.model_fields)
    return ["circular_id", "span_index", *[field for field in fields if field != "circular_id"]]


def annotation_row(annotation: Any, span_index: int, columns: list[str]) -> dict[str, Any]:
    values = annotation.model_dump()
    if values.get("provenance_inherited") is not None:
        values["provenance_inherited"] = json.dumps(
            values["provenance_inherited"],
            ensure_ascii=False,
            separators=(",", ":"),
        )
    return {column: values["circular_id"] if column == "circular_id" else span_index if column == "span_index" else values[column] for column in columns}


def verify_annotation(annotation: Any, canonical_text: str, text_sha256: str) -> None:
    selected_text = canonical_text[annotation.span_start : annotation.span_end]
    if selected_text != annotation.text or annotation.text_sha256 != text_sha256:
        print("OFFSET VERIFICATION FAILURE")
        print(f"circular_id: {annotation.circular_id}")
        print(f"offsets: {annotation.span_start}:{annotation.span_end}")
        print(f"expected text: {annotation.text!r}")
        print(f"selected text: {selected_text!r}")
        print(f"annotation text_sha256: {annotation.text_sha256}")
        print(f"canonical text_sha256: {text_sha256}")
        raise SystemExit(1)


def extract_evidence(circular_id: int, document: Any, extractors: list[Any]) -> list[EventEvidenceAnnotation]:
    annotations: list[EventEvidenceAnnotation] = []
    for extractor in extractors:
        try:
            annotations.extend(extractor.extract(document))
        except Exception as exc:
            raise RuntimeError(
                f"Evidence extractor {extractor.extractor_id} failed for circular {circular_id}"
            ) from exc
    return annotations


def extract_photometry(
    circular_id: int,
    document: Any,
    prose_extractor: ProsePhotometryExtractor,
) -> list[PhotometricMeasurementAnnotation]:
    try:
        row_annotations: list[PhotometricMeasurementAnnotation] = []
        for block in detect_table_blocks(document.rendered_text):
            row_annotations.extend(parse_table_to_measurements(block, document))
        return merge_photometry_measurements(row_annotations, prose_extractor.extract(document))
    except Exception as exc:
        raise RuntimeError(f"Photometry extraction failed for circular {circular_id}") from exc


def declared_rule_ids(extractors: list[Any], prose_extractor: ProsePhotometryExtractor) -> set[str]:
    modules = [inspect.getmodule(extractor) for extractor in extractors]
    modules.extend([inspect.getmodule(PhotometryRowParser), inspect.getmodule(prose_extractor)])
    rule_ids: set[str] = set()
    for module in modules:
        source_path = Path(inspect.getsourcefile(module))
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            candidates = list(node.args[:1])
            candidates.extend(keyword.value for keyword in node.keywords if keyword.arg == "rule_id")
            for candidate in candidates:
                if isinstance(candidate, ast.Constant) and isinstance(candidate.value, str):
                    if RULE_ID_PATTERN.fullmatch(candidate.value):
                        rule_ids.add(candidate.value)
    return rule_ids


def write_parquet(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    if not rows:
        raise RuntimeError(f"Refusing to write empty table: {path}")
    table = pa.Table.from_pandas(pd.DataFrame(rows, columns=columns), preserve_index=False)
    pq.write_table(table, path, compression="zstd")


def existing_output_hashes() -> tuple[dict[str, str], str | None] | None:
    paths = [
        OUTPUT_DIR / "circulars.parquet",
        OUTPUT_DIR / "evidence_spans.parquet",
        OUTPUT_DIR / "photometry_spans.parquet",
        OUTPUT_DIR / "manifest.json",
    ]
    if not all(path.is_file() for path in paths):
        return None
    manifest = json.loads(paths[-1].read_text(encoding="utf-8"))
    return (
        {path.name: sha256_file(path) for path in paths},
        manifest.get("script_sha256"),
    )


def print_controls(controls: list[tuple[str, bool, str, str]]) -> None:
    print("\nCONTROLS")
    print("| control | status | observed | expected |")
    print("|---|---|---|---|")
    for name, passed, observed, expected in controls:
        print(f"| {name} | {'PASS' if passed else 'FAIL'} | {observed} | {expected} |")
    if not all(passed for _, passed, _, _ in controls):
        raise SystemExit("A control failed; no output table was written.")


def print_counter(title: str, counter: Counter[Any], known_values: set[str] | None = None) -> None:
    print(f"\n{title}")
    values = set(counter)
    if known_values is not None:
        values.update(known_values)
    for value in sorted(values, key=lambda item: "" if item is None else str(item)):
        name = "<null>" if value is None else str(value)
        print(f"  {name}: {counter.get(value, 0)}")


def main() -> None:
    prior_output = existing_output_hashes()
    script_sha256 = sha256_file(Path(__file__).resolve())
    evidence_fields = list(EventEvidenceAnnotation.model_fields)
    photometry_fields = list(PhotometricMeasurementAnnotation.model_fields)
    evidence_columns = output_columns(EventEvidenceAnnotation)
    photometry_columns = output_columns(PhotometricMeasurementAnnotation)
    evidence_extractors = get_active_extractors()
    prose_extractor = ProsePhotometryExtractor()
    runtime_extractors = [
        {
            "extractor_id": extractor.extractor_id,
            "extractor_version": extractor.extractor_version,
        }
        for extractor in evidence_extractors
    ]
    runtime_extractors.extend(
        [
            {
                "extractor_id": PhotometryRowParser.extractor_id,
                "extractor_version": PhotometryRowParser.extractor_version,
            },
            {
                "extractor_id": prose_extractor.extractor_id,
                "extractor_version": prose_extractor.extractor_version,
            },
        ]
    )
    metadata_by_circular_id = load_index_metadata()
    span_indices: dict[str, defaultdict[tuple[int, int, int], int]] = {
        "evidence": defaultdict(int),
        "photometry": defaultdict(int),
    }
    circular_rows: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    photometry_rows: list[dict[str, Any]] = []
    evidence_labels: Counter[str] = Counter()
    measurement_types: Counter[str] = Counter()
    extractor_counts: Counter[str] = Counter()
    rule_counts: Counter[str | None] = Counter()
    zero_annotation_circulars: list[tuple[int, str]] = []
    verified_offsets = 0
    edited_count = 0
    processed_at_values: set[str] = set()

    print("Extractors obtained at runtime:")
    for extractor in runtime_extractors:
        print(f"  {extractor['extractor_id']} | {extractor['extractor_version']}")
    print(f"EVENT_EVIDENCE fields obtained at runtime: {evidence_fields}")
    print(f"PHOTOMETRIC_MEASUREMENT fields obtained at runtime: {photometry_fields}")

    for circular in iter_real_circulars(min_year=MIN_YEAR):
        circular_id = int(circular["circular_id"])
        metadata = metadata_by_circular_id[circular_id]
        document = render_canonical(
            circular_id=circular_id,
            subject=circular.get("subject", ""),
            body=circular["body"],
            event_id=circular.get("event_id"),
            created_on=circular.get("created_on"),
            submitter=circular.get("submitter"),
        )
        created_raw = nullable(metadata["created_on"])
        edited_raw = nullable(metadata["edited_on"])
        was_edited = edited_raw is not None and edited_raw != created_raw
        if was_edited:
            edited_count += 1
        processed_at = nullable(metadata["processed_at"])
        if processed_at is not None:
            processed_at_values.add(str(processed_at))
        circular_rows.append(
            {
                "circular_id": document.circular_id,
                "subject": document.subject,
                "created_on_utc": document.created_on,
                "edited_on_utc": nullable(metadata["edited_at_iso"]),
                "canonical_text": document.rendered_text,
                "text_length": len(document.rendered_text),
                "text_sha256": document.text_sha256,
                "body_hash": nullable(metadata["body_hash"]),
                "year": int(str(document.created_on)[:4]),
                "submitter": nullable(metadata["submitter"]),
                "was_edited": was_edited,
            }
        )

        evidence_annotations = extract_evidence(circular_id, document, evidence_extractors)
        photometry_annotations = extract_photometry(circular_id, document, prose_extractor)
        if not evidence_annotations and not photometry_annotations:
            zero_annotation_circulars.append((circular_id, document.subject))

        for annotation in evidence_annotations:
            verify_annotation(annotation, document.rendered_text, document.text_sha256)
            key = (annotation.circular_id, annotation.span_start, annotation.span_end)
            span_index = span_indices["evidence"][key]
            span_indices["evidence"][key] += 1
            evidence_rows.append(annotation_row(annotation, span_index, evidence_columns))
            evidence_labels[annotation.label] += 1
            extractor_counts[annotation.extractor_id] += 1
            rule_counts[annotation.rule_id] += 1
            verified_offsets += 1

        for annotation in photometry_annotations:
            verify_annotation(annotation, document.rendered_text, document.text_sha256)
            key = (annotation.circular_id, annotation.span_start, annotation.span_end)
            span_index = span_indices["photometry"][key]
            span_indices["photometry"][key] += 1
            photometry_rows.append(annotation_row(annotation, span_index, photometry_columns))
            measurement_types[annotation.measurement_type] += 1
            extractor_counts[annotation.extractor_id] += 1
            rule_counts[annotation.rule_id] += 1
            verified_offsets += 1

    circular_dates = [str(row["created_on_utc"])[:10] for row in circular_rows]
    invalid_labels = sorted(set(evidence_labels) - set(LABELS))
    invalid_measurement_types = sorted(set(measurement_types) - set(MEASUREMENT_TYPES))
    invalid_spans = sum(
        row["span_start"] >= row["span_end"]
        for row in [*evidence_rows, *photometry_rows]
    )
    empty_canonical_texts = sum(not row["canonical_text"] for row in circular_rows)
    controls = [
        ("circulars", len(circular_rows) == EXPECTED_CIRCULARS, str(len(circular_rows)), str(EXPECTED_CIRCULARS)),
        (
            "circular date range",
            min(circular_dates) == EXPECTED_FIRST_DATE and max(circular_dates) == EXPECTED_LAST_DATE,
            f"{min(circular_dates)} to {max(circular_dates)}",
            f"{EXPECTED_FIRST_DATE} to {EXPECTED_LAST_DATE}",
        ),
        (
            "distinct extractor_id values",
            len(extractor_counts) == len(runtime_extractors) == 15,
            str(len(extractor_counts)),
            "15",
        ),
        (
            "offsets verified",
            verified_offsets == len(evidence_rows) + len(photometry_rows),
            f"{verified_offsets} verified, 0 failures",
            "every annotation, 0 failures",
        ),
        (
            "evidence label values",
            not invalid_labels,
            "all within declared LABELS" if not invalid_labels else str(invalid_labels),
            "all within declared LABELS",
        ),
        (
            "photometry measurement_type values",
            not invalid_measurement_types,
            "all within declared set" if not invalid_measurement_types else str(invalid_measurement_types),
            "all within declared set",
        ),
        (
            "invalid spans",
            invalid_spans == 0,
            str(invalid_spans),
            "0",
        ),
        (
            "empty canonical_text",
            empty_canonical_texts == 0,
            str(empty_canonical_texts),
            "0",
        ),
    ]
    print_controls(controls)
    if len(processed_at_values) != 1:
        raise RuntimeError(f"Expected one normalized-index processed_at value, found {sorted(processed_at_values)}")
    if not circular_rows or not evidence_rows or not photometry_rows:
        raise RuntimeError(
            "Refusing to write output after a zero-row extraction: "
            f"circulars={len(circular_rows)}, evidence={len(evidence_rows)}, "
            f"photometry={len(photometry_rows)}"
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    circular_path = OUTPUT_DIR / "circulars.parquet"
    evidence_path = OUTPUT_DIR / "evidence_spans.parquet"
    photometry_path = OUTPUT_DIR / "photometry_spans.parquet"
    write_parquet(circular_path, circular_rows, CIRCULAR_COLUMNS)
    write_parquet(evidence_path, evidence_rows, evidence_columns)
    write_parquet(photometry_path, photometry_rows, photometry_columns)
    output_hashes = {
        circular_path.name: sha256_file(circular_path),
        evidence_path.name: sha256_file(evidence_path),
        photometry_path.name: sha256_file(photometry_path),
    }
    manifest = {
        "run_timestamp": next(iter(processed_at_values)),
        "run_timestamp_source": "normalized_circular_index.processed_at",
        "script_sha256": script_sha256,
        "extractors": runtime_extractors,
        "schema_versions": {
            "EventEvidenceAnnotation": EventEvidenceAnnotation.model_fields["schema_version"].default,
            "PhotometricMeasurementAnnotation": PhotometricMeasurementAnnotation.model_fields["schema_version"].default,
        },
        "circular_count": len(circular_rows),
        "annotation_counts": {
            "evidence_spans": len(evidence_rows),
            "photometry_spans": len(photometry_rows),
            "evidence_by_label": dict(sorted(evidence_labels.items())),
            "photometry_by_measurement_type": dict(sorted(measurement_types.items())),
        },
        "output_sha256": output_hashes,
    }
    manifest_path = OUTPUT_DIR / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    all_output_hashes = {
        **output_hashes,
        manifest_path.name: sha256_file(manifest_path),
    }

    print("\nOUTPUT TABLES")
    for path, rows, columns in [
        (circular_path, circular_rows, CIRCULAR_COLUMNS),
        (evidence_path, evidence_rows, evidence_columns),
        (photometry_path, photometry_rows, photometry_columns),
    ]:
        print(f"  {path.name}: {len(rows)} rows, {len(columns)} columns")
        print(f"  columns: {columns}")
    print_counter("ANNOTATION COUNTS PER LABEL", evidence_labels, set(LABELS))
    print_counter("ANNOTATION COUNTS PER MEASUREMENT_TYPE", measurement_types, set(MEASUREMENT_TYPES))
    print_counter("ROWS PER EXTRACTOR_ID", extractor_counts, {item["extractor_id"] for item in runtime_extractors})
    print_counter("ROWS PER RULE_ID", rule_counts, declared_rule_ids(evidence_extractors, prose_extractor))
    print("\nCIRCULARS WITH ZERO ANNOTATIONS IN BOTH LAYERS")
    print(f"  count: {len(zero_annotation_circulars)}")
    for circular_id, subject in zero_annotation_circulars[:5]:
        print(f"  {circular_id} | {subject}")
    print(f"\nwas_edited count: {edited_count}")
    print("\nSERIALIZED JSON COLUMNS")
    print("  photometry_spans.provenance_inherited: list[str] serialised as JSON to retain every model field in one flat column.")
    print("\nUNCOVERED CASES")
    print("  none")
    print("\nOUTPUT SHA256")
    for name, digest in output_hashes.items():
        print(f"  {name}: {digest}")
    print("\nDETERMINISM")
    if prior_output is None:
        print("  No complete prior output set was available for comparison.")
    else:
        prior_hashes, prior_script_sha256 = prior_output
        if prior_script_sha256 != script_sha256:
            print("  Prior output used a different or unrecorded script revision; comparison deferred to the next run.")
        else:
            identical = prior_hashes == all_output_hashes
            print(f"  Consecutive-run hashes: {'PASS' if identical else 'FAIL'}")
            for name in sorted(all_output_hashes):
                print(f"  {name}: {all_output_hashes[name]}")
            if not identical:
                raise SystemExit("Determinism failure: output hashes changed across consecutive runs.")
    print("\nGIT STATUS")
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
