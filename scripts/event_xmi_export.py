from __future__ import annotations

import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast


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
from skyportal_corpus.inception_v2.xmi_export import (
    MISSING_TYPESYSTEM_MESSAGE,
    TYPESYSTEM_PATH,
    export_document_to_xmi,
)
from skyportal_corpus.inception_v2.xmi_roundtrip import roundtrip_check


SOURCE_ID = "2026owq"
TITLE = "GRB 260610B / AT2026owq"
ALIASES = ["GRB 260610B", "AT2026owq", "2026owq"]
MIN_CIRCULAR_ID = 44880
MAX_CIRCULAR_ID = 45050
XMI_PATH = PROJECT_ROOT / "data/inception/out/event_2026owq.xmi"
MANIFEST_PATH = PROJECT_ROOT / "data/inception/out/event_2026owq_manifest.txt"


@dataclass(frozen=True)
class _EventTextAdapter:
    rendered_text: str


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
    extraction_errors: list[dict[str, Any]] = []
    annotations = extract_event_annotations(
        event_doc,
        circular_docs,
        errors=extraction_errors,
    )

    # The existing exporter uses only rendered_text from its document argument.
    # This typed adapter lets it write the immutable event text without duplicating
    # any CAS, segmentation, feature, or validation logic.
    export_document_to_xmi(
        cast(CanonicalDocument, _EventTextAdapter(event_doc.event_rendered_text)),
        annotations,
        typesystem_path,
        XMI_PATH,
    )
    roundtrip = roundtrip_check(
        XMI_PATH,
        typesystem_path,
        annotations,
        event_doc.event_rendered_text,
    )
    roundtrip_ok = (
        bool(roundtrip["text_matches"])
        and bool(roundtrip["all_spans_ok"])
        and bool(roundtrip["all_features_ok"])
        and int(roundtrip["n_original"]) == int(roundtrip["n_roundtripped"])
    )

    extractor_counts = Counter(_extractor_short_name(item.extractor_id) for item in annotations)
    circular_counts = Counter(item.circular_id for item in annotations)
    label_counts = Counter(item.label for item in annotations)
    needs_review_count = sum(item.needs_review for item in annotations)
    comment_count = sum(bool(item.comment) for item in annotations)
    clean_comment_invariant = all(
        bool(item.comment) == item.needs_review for item in annotations
    )

    _write_manifest(
        event_doc,
        annotations,
        extractor_counts,
        circular_counts,
        label_counts,
    )
    _print_summary(
        event_doc,
        annotations,
        extractor_counts,
        circular_counts,
        needs_review_count,
        comment_count,
        clean_comment_invariant,
        extraction_errors,
        roundtrip,
        roundtrip_ok,
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
    extractor_counts: Counter[str],
    circular_counts: Counter[int],
    label_counts: Counter[str],
) -> None:
    labels_by_circular: dict[int, Counter[str]] = {}
    for annotation in annotations:
        labels_by_circular.setdefault(annotation.circular_id, Counter())[annotation.label] += 1

    lines = [
        "EVENT XMI MANIFEST",
        "==================",
        f"source_id: {event_doc.source_id}",
        f"title: {event_doc.title}",
        f"n_circulars: {event_doc.n_circulars}",
        f"event_text_sha256: {event_doc.event_text_sha256}",
        f"event_text_length: {len(event_doc.event_rendered_text)}",
        f"n_annotations: {len(annotations)}",
        f"xmi_path: {XMI_PATH}",
        "",
        "ANNOTATIONS BY EXTRACTOR",
        "extractor | count",
    ]
    lines.extend(
        f"{extractor} | {count}"
        for extractor, count in sorted(extractor_counts.items())
    )
    lines.extend(["", "ANNOTATIONS BY TYPE", "label | count"])
    lines.extend(f"{label} | {count}" for label, count in sorted(label_counts.items()))
    lines.extend(
        [
            "",
            "CIRCULARS",
            "circular_id | created_on | subject | n_annotations | annotations_by_type",
        ]
    )
    for segment in event_doc.segments:
        label_summary = ", ".join(
            f"{label}={count}"
            for label, count in sorted(labels_by_circular.get(segment.circular_id, {}).items())
        )
        lines.append(
            f"{segment.circular_id} | {segment.created_on or ''} | {segment.subject} | "
            f"{circular_counts.get(segment.circular_id, 0)} | {label_summary or 'none'}"
        )

    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _print_summary(
    event_doc: EventCanonicalDocument,
    annotations: list[EventEvidenceAnnotation],
    extractor_counts: Counter[str],
    circular_counts: Counter[int],
    needs_review_count: int,
    comment_count: int,
    clean_comment_invariant: bool,
    extraction_errors: list[dict[str, Any]],
    roundtrip: dict[str, Any],
    roundtrip_ok: bool,
) -> None:
    print("EVENT SUMMARY")
    print(f"source_id: {event_doc.source_id}")
    print(f"title: {event_doc.title}")
    print(f"n_circulars: {event_doc.n_circulars}")
    print(f"event_text_length: {len(event_doc.event_rendered_text)}")
    print(f"total_annotations: {len(annotations)}")
    print(f"needs_review: {needs_review_count}")
    print(f"annotations_with_comment: {comment_count}")
    print(
        "comments_only_when_needs_review: "
        f"{'OK' if clean_comment_invariant else 'FAIL'}"
    )
    print(f"broken_global_offsets: {len(extraction_errors)}")

    print("\nANNOTATIONS BY EXTRACTOR")
    print("extractor | count")
    for extractor, count in sorted(extractor_counts.items()):
        print(f"{extractor} | {count}")

    print("\nANNOTATIONS BY CIRCULAR")
    print("circular_id | count")
    for segment in event_doc.segments:
        print(f"{segment.circular_id} | {circular_counts.get(segment.circular_id, 0)}")

    print("\nROUND-TRIP")
    print(f"text_matches: {roundtrip['text_matches']}")
    print(f"all_spans_ok: {roundtrip['all_spans_ok']}")
    print(f"all_features_ok: {roundtrip['all_features_ok']}")
    print(f"n_original: {roundtrip['n_original']}")
    print(f"n_roundtripped: {roundtrip['n_roundtripped']}")
    print(f"discrepancies: {roundtrip['discrepancies']}")
    print(f"FINAL: {'OK' if roundtrip_ok else 'FAIL'}")
    print(f"XMI: {XMI_PATH}")
    print(f"MANIFEST: {MANIFEST_PATH}")

    if extraction_errors:
        print("\nTRANSLATION ERRORS")
        for error in extraction_errors:
            print(error)


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
