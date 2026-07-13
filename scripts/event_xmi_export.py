from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from skyportal_corpus.canonical.document import (
    CanonicalDocument,
    iter_real_circulars,
    render_canonical,
)
from skyportal_corpus.extraction_v2.annotations import EventEvidenceAnnotation
from skyportal_corpus.extraction_v2.event_annotations import extract_event_annotations
from skyportal_corpus.extraction_v2.event_document import (
    EventCanonicalDocument,
    build_event_document,
)
from skyportal_corpus.extraction_v2.event_grouping import group_event_circulars
from skyportal_corpus.extraction_v2.event_photometry import (
    EventPhotometricMeasurementAnnotation,
    extract_event_photometry,
    measurement_source,
)
from skyportal_corpus.inception_v2.event_xmi_export import (
    event_layers_roundtrip_check,
    export_event_layers_xmi,
)
from skyportal_corpus.inception_v2.xmi_export import (
    MISSING_TYPESYSTEM_MESSAGE,
    TYPESYSTEM_PATH,
)


SOURCE_ID = "2026owq"
TITLE = "GRB 260610B / AT2026owq"
ALIASES = ["GRB 260610B", "AT2026owq", "2026owq"]
MIN_CIRCULAR_ID = 44880
MAX_CIRCULAR_ID = 45050
XMI_PATH = PROJECT_ROOT / "data/inception/out/event_2026owq.xmi"
MANIFEST_PATH = PROJECT_ROOT / "data/inception/out/event_2026owq_manifest.txt"


def main() -> None:
    typesystem_path = PROJECT_ROOT / TYPESYSTEM_PATH
    if not typesystem_path.exists():
        print(MISSING_TYPESYSTEM_MESSAGE)
        return

    candidates = _candidate_circulars()
    grouped = group_event_circulars(
        source_id=SOURCE_ID,
        title=TITLE,
        aliases=ALIASES,
        circulars=candidates,
    )
    included_ids = {int(item["circular_id"]) for item in grouped["included"]}
    included_circulars = [
        circular for circular in candidates if int(circular["circular_id"]) in included_ids
    ]
    event_doc = build_event_document(
        source_id=SOURCE_ID,
        title=TITLE,
        circulars_in_order=included_circulars,
    )
    circular_docs = _canonical_documents(included_circulars)
    evidence_errors: list[dict[str, Any]] = []
    annotations = extract_event_annotations(
        event_doc,
        circular_docs,
        errors=evidence_errors,
    )
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
        XMI_PATH,
    )
    roundtrip = event_layers_roundtrip_check(
        XMI_PATH,
        typesystem_path,
        event_doc,
        annotations,
        measurements,
    )

    extractor_counts = Counter(_extractor_short_name(item.extractor_id) for item in annotations)
    evidence_circular_counts = Counter(item.source_circular_id for item in annotations)
    label_counts = Counter(item.label for item in annotations)
    measurement_type_counts = Counter(item.measurement_type for item in measurements)
    measurement_source_counts = Counter(measurement_source(item) for item in measurements)
    measurement_band_counts = Counter(item.photometric_band or "unknown" for item in measurements)
    measurement_system_counts = Counter(item.photometric_system or "unknown" for item in measurements)
    photometry_circular_counts = Counter(item.source_circular_id for item in measurements)

    _write_manifest(
        event_doc,
        annotations,
        measurements,
        extractor_counts,
        evidence_circular_counts,
        photometry_circular_counts,
        label_counts,
        measurement_type_counts,
        measurement_source_counts,
    )
    _print_summary(
        event_doc,
        annotations,
        measurements,
        extractor_counts,
        evidence_circular_counts,
        photometry_circular_counts,
        measurement_type_counts,
        measurement_source_counts,
        measurement_band_counts,
        measurement_system_counts,
        evidence_errors,
        photometry_errors,
        roundtrip,
    )


def _candidate_circulars() -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for circular in iter_real_circulars(min_year=2026):
        circular_id = int(circular["circular_id"])
        if MIN_CIRCULAR_ID <= circular_id <= MAX_CIRCULAR_ID:
            candidates.append(circular)
    return sorted(
        candidates,
        key=lambda item: (str(item.get("created_on") or ""), int(item["circular_id"])),
    )


def _canonical_documents(
    circulars: list[dict[str, Any]],
) -> dict[int, CanonicalDocument]:
    documents: dict[int, CanonicalDocument] = {}
    for circular in circulars:
        document = render_canonical(
            circular_id=int(circular["circular_id"]),
            subject=str(circular.get("subject") or ""),
            body=str(circular.get("body") or ""),
            event_id=_optional_str(circular.get("event_id")),
            created_on=_optional_str(circular.get("created_on")),
            submitter=_optional_str(circular.get("submitter")),
        )
        documents[document.circular_id] = document
    return documents


def _write_manifest(
    event_doc: EventCanonicalDocument,
    annotations: list[EventEvidenceAnnotation],
    measurements: list[EventPhotometricMeasurementAnnotation],
    extractor_counts: Counter[str],
    evidence_circular_counts: Counter[int | None],
    photometry_circular_counts: Counter[int],
    label_counts: Counter[str],
    measurement_type_counts: Counter[str],
    measurement_source_counts: Counter[str],
) -> None:
    labels_by_circular: dict[int, Counter[str]] = {}
    for annotation in annotations:
        source_id = annotation.source_circular_id or annotation.circular_id
        labels_by_circular.setdefault(source_id, Counter())[annotation.label] += 1
    photometry_by_circular: dict[int, Counter[str]] = {}
    for measurement in measurements:
        photometry_by_circular.setdefault(
            measurement.source_circular_id,
            Counter(),
        )[measurement.measurement_type] += 1

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
        f"xmi_path: {XMI_PATH}",
        "",
        "EVENT_EVIDENCE BY EXTRACTOR",
        "extractor | count",
    ]
    lines.extend(
        f"{extractor} | {count}"
        for extractor, count in sorted(extractor_counts.items())
    )
    lines.extend(["", "EVENT_EVIDENCE BY LABEL", "label | count"])
    lines.extend(f"{label} | {count}" for label, count in sorted(label_counts.items()))
    lines.extend(["", "PHOTOMETRY BY TYPE", "measurement_type | count"])
    lines.extend(
        f"{measurement_type} | {count}"
        for measurement_type, count in sorted(measurement_type_counts.items())
    )
    lines.extend(["", "PHOTOMETRY BY SOURCE", "source | count"])
    lines.extend(
        f"{source} | {count}"
        for source, count in sorted(measurement_source_counts.items())
    )
    lines.extend(
        [
            "",
            "CIRCULARS",
            "circular_id | created_on | subject | n_event_evidence | "
            "event_labels | n_photometry | photometry_types",
        ]
    )
    for segment in event_doc.segments:
        label_summary = ", ".join(
            f"{label}={count}"
            for label, count in sorted(labels_by_circular.get(segment.circular_id, {}).items())
        )
        photometry_summary = ", ".join(
            f"{measurement_type}={count}"
            for measurement_type, count in sorted(
                photometry_by_circular.get(segment.circular_id, {}).items()
            )
        )
        lines.append(
            f"{segment.circular_id} | {segment.created_on or ''} | {segment.subject} | "
            f"{evidence_circular_counts.get(segment.circular_id, 0)} | "
            f"{label_summary or 'none'} | "
            f"{photometry_circular_counts.get(segment.circular_id, 0)} | "
            f"{photometry_summary or 'none'}"
        )

    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _print_summary(
    event_doc: EventCanonicalDocument,
    annotations: list[EventEvidenceAnnotation],
    measurements: list[EventPhotometricMeasurementAnnotation],
    extractor_counts: Counter[str],
    evidence_circular_counts: Counter[int | None],
    photometry_circular_counts: Counter[int],
    measurement_type_counts: Counter[str],
    measurement_source_counts: Counter[str],
    measurement_band_counts: Counter[str],
    measurement_system_counts: Counter[str],
    evidence_errors: list[dict[str, Any]],
    photometry_errors: list[dict[str, Any]],
    roundtrip: dict[str, Any],
) -> None:
    print("EVENT SUMMARY")
    print(f"source_id: {event_doc.source_id}")
    print(f"title: {event_doc.title}")
    print(f"n_circulars: {event_doc.n_circulars}")
    print(f"event_text_length: {len(event_doc.event_rendered_text)}")
    print(f"broken_global_offsets_event_evidence: {len(evidence_errors)}")
    print(f"broken_global_offsets_photometry: {len(photometry_errors)}")

    print("\nEVENT_EVIDENCE")
    print(f"total: {len(annotations)}")
    print(f"needs_review: {sum(item.needs_review for item in annotations)}")
    print("by extractor:")
    print("extractor | count")
    for extractor, count in sorted(extractor_counts.items()):
        print(f"{extractor} | {count}")

    print("\nPHOTOMETRIC_MEASUREMENT")
    print(f"total: {len(measurements)}")
    print(f"needs_review: {sum(item.needs_review for item in measurements)}")
    print(f"with_limit_sigma: {sum(bool(item.limit_sigma) for item in measurements)}")
    print("by type:")
    for measurement_type, count in sorted(measurement_type_counts.items()):
        print(f"{measurement_type} | {count}")
    print("by source:")
    for source, count in sorted(measurement_source_counts.items()):
        print(f"{source} | {count}")
    print("top bands:")
    for band, count in measurement_band_counts.most_common(10):
        print(f"{band} | {count}")
    print("by system:")
    for system, count in sorted(measurement_system_counts.items()):
        print(f"{system} | {count}")

    print("\nBY CIRCULAR")
    print("circular_id | event_evidence | photometry")
    for segment in event_doc.segments:
        print(
            f"{segment.circular_id} | "
            f"{evidence_circular_counts.get(segment.circular_id, 0)} | "
            f"{photometry_circular_counts.get(segment.circular_id, 0)}"
        )

    print("\nROUND-TRIP")
    print(f"text_matches: {roundtrip['text_matches']}")
    for layer_name in ("event_evidence", "photometry"):
        layer = roundtrip[layer_name]
        print(f"{layer_name}:")
        print(f"  all_spans_ok: {layer['all_spans_ok']}")
        print(f"  all_features_ok: {layer['all_features_ok']}")
        print(f"  n_original: {layer['n_original']}")
        print(f"  n_roundtripped: {layer['n_roundtripped']}")
        print(f"  discrepancies: {layer['discrepancies']}")
    print(f"FINAL: {'OK' if roundtrip['all_ok'] else 'FAIL'}")
    print(f"XMI: {XMI_PATH}")
    print(f"MANIFEST: {MANIFEST_PATH}")

    if evidence_errors or photometry_errors:
        print("\nTRANSLATION ERRORS")
        for error in evidence_errors:
            print({"layer": "event_evidence", **error})
        for error in photometry_errors:
            print({"layer": "photometry", **error})


def _extractor_short_name(extractor_id: str) -> str:
    name = extractor_id.removesuffix("-v1")
    return name.replace("-", "_")


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


if __name__ == "__main__":
    main()
