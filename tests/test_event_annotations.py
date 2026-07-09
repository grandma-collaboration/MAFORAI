from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from skyportal_corpus.canonical.document import CanonicalDocument, render_canonical
from skyportal_corpus.extraction_v2.event_annotations import extract_event_annotations
from skyportal_corpus.extraction_v2.event_document import build_event_document


def test_event_annotations_translate_local_offsets_and_keep_provenance() -> None:
    circulars = _circulars()
    event_doc = build_event_document("evt", "GRB 260610B", circulars)
    circular_docs = _canonical_documents(circulars)
    errors: list[dict[str, object]] = []

    annotations = extract_event_annotations(
        event_doc,
        circular_docs,
        errors=errors,
    )

    assert annotations
    assert errors == []
    assert all(annotation.verify(event_doc.event_rendered_text) for annotation in annotations)
    assert all(
        event_doc.event_rendered_text[annotation.span_start : annotation.span_end]
        == annotation.text
        for annotation in annotations
    )
    assert all(annotation.text_sha256 == event_doc.event_text_sha256 for annotation in annotations)

    first_annotations = [annotation for annotation in annotations if annotation.circular_id == 1]
    second_annotations = [annotation for annotation in annotations if annotation.circular_id == 2]
    assert first_annotations
    assert second_annotations
    assert min(annotation.span_start for annotation in second_annotations) > min(
        annotation.span_start for annotation in first_annotations
    )
    assert all(annotation.source_circular_id == 1 for annotation in first_annotations)
    assert all(annotation.source_circular_id == 2 for annotation in second_annotations)
    assert all(
        bool(annotation.comment) == annotation.needs_review
        for annotation in annotations
    )


def test_global_annotations_match_expected_local_to_global_positions() -> None:
    circulars = _circulars()
    event_doc = build_event_document("evt", "GRB 260610B", circulars)
    circular_docs = _canonical_documents(circulars)

    annotations = extract_event_annotations(event_doc, circular_docs)

    second_identity = next(
        annotation
        for annotation in annotations
        if annotation.circular_id == 2 and annotation.label == "EVENT_IDENTITY"
    )
    local_start = circular_docs[2].rendered_text.index(second_identity.text)
    second_segment = next(
        segment for segment in event_doc.segments if segment.circular_id == 2
    )
    assert second_identity.span_start == second_segment.global_start + local_start
    assert second_identity.span_end == second_identity.span_start + len(second_identity.text)


def _circulars() -> list[dict[str, object]]:
    return [
        {
            "circular_id": 1,
            "subject": "GRB 260610B: Swift detection",
            "body": (
                "At 21:04:43 UT, the Swift Burst Alert Telescope (BAT) triggered "
                "and located GRB 260610B."
            ),
            "created_on": "2026-06-10T23:50:00Z",
            "submitter": "First Author",
        },
        {
            "circular_id": 2,
            "subject": "GRB 260610B: host redshift",
            "body": "The host galaxy is at z=0.474.",
            "created_on": "2026-06-11T01:00:00Z",
            "submitter": "Second Author",
        },
    ]


def _canonical_documents(
    circulars: list[dict[str, object]],
) -> dict[int, CanonicalDocument]:
    documents: dict[int, CanonicalDocument] = {}
    for circular in circulars:
        document = render_canonical(
            circular_id=int(circular["circular_id"]),
            subject=str(circular["subject"]),
            body=str(circular["body"]),
            created_on=str(circular["created_on"]),
            submitter=str(circular["submitter"]),
        )
        documents[document.circular_id] = document
    return documents
