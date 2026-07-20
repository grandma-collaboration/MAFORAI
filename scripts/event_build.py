#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from skyportal_corpus.canonical.document import CanonicalDocument, render_canonical  # noqa: E402
from skyportal_corpus.extraction_v2.annotations import EventEvidenceAnnotation  # noqa: E402
from skyportal_corpus.extraction_v2.event_annotations import extract_event_annotations  # noqa: E402
from skyportal_corpus.extraction_v2.event_document import (  # noqa: E402
    EventCanonicalDocument,
    build_event_document,
)
from skyportal_corpus.extraction_v2.event_photometry import (  # noqa: E402
    EventPhotometricMeasurementAnnotation,
    extract_event_photometry,
    measurement_source,
)
from skyportal_corpus.extraction_v2.event_registry import DEFAULT_EVENT_REGISTRY_PATH  # noqa: E402
from skyportal_corpus.extraction_v2.event_selection import select_event_candidates  # noqa: E402
from skyportal_corpus.extraction_v2.identity_index import (  # noqa: E402
    DEFAULT_IDENTITY_INDEX_META_PATH,
    DEFAULT_IDENTITY_INDEX_PATH,
    load_identity_index_meta,
    validate_identity_index_meta,
)
from skyportal_corpus.inception_v2.event_xmi_export import (  # noqa: E402
    event_layers_roundtrip_check,
    export_event_layers_xmi,
)
from skyportal_corpus.inception_v2.xmi_export import (  # noqa: E402
    MISSING_TYPESYSTEM_MESSAGE,
    TYPESYSTEM_PATH,
)


DEFAULT_SELECTION_DIR = Path("data/interim/gcn/event_matching/selections")
DEFAULT_XMI_ROOT = Path("data/inception/out")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build one event dossier from the identity index.")
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--title", default=None)
    parser.add_argument("--no-xmi", action="store_true")
    parser.add_argument("--min-year", type=int, default=2023)
    parser.add_argument("--registry-path", default=str(DEFAULT_EVENT_REGISTRY_PATH))
    parser.add_argument("--index-path", default=str(DEFAULT_IDENTITY_INDEX_PATH))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    registry_path = PROJECT_ROOT / args.registry_path
    index_path = PROJECT_ROOT / args.index_path
    metadata = load_identity_index_meta(
        index_path.with_name(DEFAULT_IDENTITY_INDEX_META_PATH.name)
    )
    validate_identity_index_meta(metadata, min_year=args.min_year)

    selection = select_event_candidates(
        args.source_id,
        registry_path=registry_path,
        index_path=index_path,
    )
    if args.title:
        selection["title"] = args.title
    report_path = write_selection_report(selection)
    print_selection_summary(selection, report_path)
    if args.no_xmi:
        return 0

    typesystem_path = PROJECT_ROOT / TYPESYSTEM_PATH
    if not typesystem_path.exists():
        print(MISSING_TYPESYSTEM_MESSAGE)
        return 1
    return build_event_xmi(selection, typesystem_path)


def write_selection_report(selection: dict[str, Any]) -> Path:
    """Write the complete per-event selection audit."""
    safe_id = safe_source_id(str(selection["source_id"]))
    output_path = PROJECT_ROOT / DEFAULT_SELECTION_DIR / f"selection_{safe_id}.txt"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "EVENT CIRCULAR SELECTION",
        "========================",
        f"source_id: {selection['source_id']}",
        f"title: {selection['title']}",
        f"terms_used: {' | '.join(selection['terms'])}",
        f"merged_source_ids: {' | '.join(selection['merged_source_ids'])}",
        f"trigger_time: {_optional_display(selection['trigger_time'])}",
        f"min_year: {selection['min_year']}",
        f"n_scanned: {selection['n_scanned']}",
        f"n_included: {selection['n_included']}",
        f"n_excluded: {selection['n_excluded']}",
        f"flags: {';'.join(selection['flags'])}",
        "",
        "INCLUDED",
        "circular_id | created_on | delta_days | subject | reason | evidence",
    ]
    lines.extend(_selection_line(item) for item in selection["included"])
    lines.extend(
        [
            "",
            "EXCLUDED_CONFLICT",
            "circular_id | created_on | delta_days | subject | reason | evidence",
        ]
    )
    lines.extend(_selection_line(item) for item in selection["excluded_conflicts"])
    lines.extend(
        [
            "",
            "BODY_ONLY - IDENTITY ANNOTATION",
            "circular_id | created_on | delta_days | subject | reason | evidence",
        ]
    )
    lines.extend(_selection_line(item) for item in selection["body_only_identity"])
    lines.extend(
        [
            "",
            "BODY_ONLY - BODY NAME MATCH",
            "circular_id | created_on | delta_days | subject | reason | evidence",
        ]
    )
    lines.extend(_selection_line(item) for item in selection["body_only_name"])
    lines.extend(
        [
            "",
            "FAR_IN_TIME",
            "circular_id | created_on | delta_days | subject | reason | evidence",
        ]
    )
    lines.extend(_selection_line(item) for item in selection["far_in_time"])
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def print_selection_summary(selection: dict[str, Any], report_path: Path) -> None:
    """Print concise selection metrics for CLI and dry-run use."""
    print("EVENT SELECTION")
    for key in (
        "source_id",
        "gcn_source_type",
        "title",
        "min_year",
        "n_scanned",
        "n_included",
        "n_excluded",
    ):
        print(f"{key}: {selection[key]}")
    print(f"n_body_only: {len(selection['body_only'])}")
    print(f"n_body_name_match: {len(selection['body_only_name'])}")
    print(f"n_conflict_excluded: {len(selection['excluded_conflicts'])}")
    print(f"n_far_in_time: {len(selection['far_in_time'])}")
    print(f"flags: {';'.join(selection['flags'])}")
    print(f"selection_report: {report_path}")


def build_event_xmi(selection: dict[str, Any], typesystem_path: Path) -> int:
    """Extract both event layers, export XMI, verify round-trip, and write a manifest."""
    source_id = str(selection["source_id"])
    safe_id = safe_source_id(source_id)
    output_dir = PROJECT_ROOT / DEFAULT_XMI_ROOT / safe_id
    xmi_path = output_dir / f"event_{safe_id}.xmi"
    manifest_path = output_dir / f"event_{safe_id}_manifest.txt"
    circulars = list(selection["included_records"])
    event_doc = build_event_document(
        source_id=source_id,
        title=str(selection["title"]),
        circulars_in_order=circulars,
    )
    circular_docs = canonical_documents(circulars)
    evidence_errors: list[dict[str, Any]] = []
    annotations = extract_event_annotations(event_doc, circular_docs, errors=evidence_errors)
    photometry_errors: list[dict[str, Any]] = []
    measurements = extract_event_photometry(
        event_doc,
        circular_docs,
        errors=photometry_errors,
    )
    export_event_layers_xmi(
        event_doc,
        annotations,
        measurements,
        typesystem_path,
        xmi_path,
    )
    roundtrip = event_layers_roundtrip_check(
        xmi_path,
        typesystem_path,
        event_doc,
        annotations,
        measurements,
    )
    write_event_manifest(
        manifest_path,
        xmi_path,
        event_doc,
        annotations,
        measurements,
    )
    print_event_result(
        event_doc,
        annotations,
        measurements,
        evidence_errors,
        photometry_errors,
        roundtrip,
        xmi_path,
        manifest_path,
    )
    return 0 if roundtrip["all_ok"] and not evidence_errors and not photometry_errors else 1


def canonical_documents(circulars: list[dict[str, Any]]) -> dict[int, CanonicalDocument]:
    """Render the selected local documents exactly as the event builder does."""
    result: dict[int, CanonicalDocument] = {}
    for circular in circulars:
        document = render_canonical(
            circular_id=int(circular["circular_id"]),
            subject=str(circular.get("subject") or ""),
            body=str(circular.get("body") or ""),
            event_id=_optional_text(circular.get("event_id")),
            created_on=_optional_text(circular.get("created_on")),
            submitter=_optional_text(circular.get("submitter")),
        )
        result[document.circular_id] = document
    return result


def write_event_manifest(
    path: Path,
    xmi_path: Path,
    event_doc: EventCanonicalDocument,
    annotations: list[EventEvidenceAnnotation],
    measurements: list[EventPhotometricMeasurementAnnotation],
) -> None:
    """Write event counts and selected Circular IDs beside the XMI."""
    extractor_counts = Counter(extractor_short_name(item.extractor_id) for item in annotations)
    label_counts = Counter(item.label for item in annotations)
    measurement_counts = Counter(item.measurement_type for item in measurements)
    lines = [
        "EVENT XMI MANIFEST",
        "==================",
        f"source_id: {event_doc.source_id}",
        f"title: {event_doc.title}",
        f"n_circulars: {event_doc.n_circulars}",
        f"event_text_sha256: {event_doc.event_text_sha256}",
        f"event_text_length: {len(event_doc.event_rendered_text)}",
        f"n_event_evidence: {len(annotations)}",
        f"n_photometric_measurements: {len(measurements)}",
        f"xmi_path: {xmi_path}",
        "",
        "EVENT_EVIDENCE BY EXTRACTOR",
        "extractor | count",
    ]
    lines.extend(f"{name} | {count}" for name, count in sorted(extractor_counts.items()))
    lines.extend(["", "EVENT_EVIDENCE BY LABEL", "label | count"])
    lines.extend(f"{name} | {count}" for name, count in sorted(label_counts.items()))
    lines.extend(["", "PHOTOMETRY BY TYPE", "measurement_type | count"])
    lines.extend(f"{name} | {count}" for name, count in sorted(measurement_counts.items()))
    lines.extend(["", "CIRCULARS", "circular_id | created_on | subject"])
    lines.extend(
        f"{segment.circular_id} | {segment.created_on or ''} | {segment.subject}"
        for segment in event_doc.segments
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def print_event_result(
    event_doc: EventCanonicalDocument,
    annotations: list[EventEvidenceAnnotation],
    measurements: list[EventPhotometricMeasurementAnnotation],
    evidence_errors: list[dict[str, Any]],
    photometry_errors: list[dict[str, Any]],
    roundtrip: dict[str, Any],
    xmi_path: Path,
    manifest_path: Path,
) -> None:
    """Print the round-trip verdict and extractor counts."""
    evidence = roundtrip["event_evidence"]
    photometry = roundtrip["photometry"]
    print("\nEVENT XMI")
    print(f"n_circulars: {event_doc.n_circulars}")
    print(f"broken_global_offsets_event_evidence: {len(evidence_errors)}")
    print(f"broken_global_offsets_photometry: {len(photometry_errors)}")
    print(f"text_matches: {roundtrip['text_matches']}")
    print(f"all_spans_ok: {evidence['all_spans_ok']}")
    print(f"all_features_ok: {evidence['all_features_ok']}")
    print(f"n_original: {evidence['n_original']}")
    print(f"n_roundtripped: {evidence['n_roundtripped']}")
    print(f"discrepancies: {evidence['discrepancies']}")
    print(f"photometry_all_spans_ok: {photometry['all_spans_ok']}")
    print(f"photometry_all_features_ok: {photometry['all_features_ok']}")
    print(f"FINAL: {'OK' if roundtrip['all_ok'] else 'FAIL'}")
    print("EVENT_EVIDENCE BY EXTRACTOR")
    for name, count in sorted(
        Counter(extractor_short_name(item.extractor_id) for item in annotations).items()
    ):
        print(f"{name} | {count}")
    print(f"event_evidence_total: {len(annotations)}")
    print(f"photometry_total: {len(measurements)}")
    print(f"xmi_path: {xmi_path}")
    print(f"manifest_path: {manifest_path}")
    if evidence_errors or photometry_errors:
        print("TRANSLATION ERRORS")
        for error in evidence_errors:
            print(json.dumps({"layer": "event_evidence", **error}, sort_keys=True))
        for error in photometry_errors:
            print(json.dumps({"layer": "photometry", **error}, sort_keys=True))


def safe_source_id(source_id: str) -> str:
    """Return a filesystem-safe deterministic source identifier."""
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", source_id).strip("._")
    if not safe:
        raise ValueError("source_id has no filesystem-safe characters")
    return safe


def extractor_short_name(extractor_id: str) -> str:
    return extractor_id.removesuffix("-v1").replace("-", "_")


def _selection_line(item: dict[str, Any]) -> str:
    return (
        f"{item['circular_id']} | {item.get('created_on') or ''} | "
        f"{_delta_display(item.get('delta_days'))} | {item.get('subject') or ''} | "
        f"{item.get('reason') or ''} | "
        f"{json.dumps(item.get('evidence') or {}, ensure_ascii=False, sort_keys=True)}"
    )


def _delta_display(value: Any) -> str:
    return "" if value is None else f"{float(value):.6f}"


def _optional_display(value: Any) -> str:
    return "" if value is None else str(value)


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


if __name__ == "__main__":
    raise SystemExit(main())
