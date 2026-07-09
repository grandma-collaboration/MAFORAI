from __future__ import annotations

import hashlib
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from skyportal_corpus.canonical.document import render_canonical
from skyportal_corpus.extraction_v2.event_document import (
    SEPARATOR_TEMPLATE,
    build_event_document,
    global_to_circular,
    local_to_global,
)


def test_build_event_document_segments_have_correct_offsets() -> None:
    circulars = [_circular(2, "Second", "Second body."), _circular(1, "First", "First body.")]

    doc = build_event_document("evt", "Test Event", circulars)

    assert doc.n_circulars == 2
    assert [segment.circular_id for segment in doc.segments] == [1, 2]

    first_local = _local_text(circulars[1])
    first_separator = SEPARATOR_TEMPLATE.format(circular_id=1)
    assert doc.segments[0].global_start == len(first_separator)
    assert doc.segments[0].global_end == len(first_separator) + len(first_local)


def test_event_document_preserves_each_canonical_text_slice_and_sha() -> None:
    circulars = [_circular(1, "GRB 260610B", "Body one."), _circular(2, "AT2026owq", "Body two.")]

    doc = build_event_document("2026owq", "GRB 260610B / AT2026owq", circulars)

    by_id = {int(circular["circular_id"]): circular for circular in circulars}
    for segment in doc.segments:
        event_slice = doc.event_rendered_text[segment.global_start : segment.global_end]
        local_text = _local_text(by_id[segment.circular_id])
        assert event_slice == local_text
        assert hashlib.sha256(event_slice.encode("utf-8")).hexdigest() == segment.local_text_sha256


def test_local_to_global_and_global_to_circular_are_exact_inverses() -> None:
    circulars = [_circular(1, "First", "Alpha body."), _circular(2, "Second", "Beta body.")]
    doc = build_event_document("evt", "Test Event", circulars)

    for segment in doc.segments:
        length = segment.global_end - segment.global_start
        for local_offset in [0, 1, length // 2, length - 1]:
            global_offset = local_to_global(doc, segment.circular_id, local_offset)
            assert global_to_circular(doc, global_offset) == (segment.circular_id, local_offset)


def test_build_event_document_is_deterministic() -> None:
    circulars = [_circular(1, "First", "Alpha body."), _circular(2, "Second", "Beta body.")]

    first = build_event_document("evt", "Test Event", circulars)
    second = build_event_document("evt", "Test Event", circulars)

    assert first.event_rendered_text == second.event_rendered_text
    assert first.event_text_sha256 == second.event_text_sha256


def test_global_to_circular_returns_none_for_separator_offsets() -> None:
    circulars = [_circular(1, "First", "Alpha body."), _circular(2, "Second", "Beta body.")]
    doc = build_event_document("evt", "Test Event", circulars)

    assert global_to_circular(doc, 0) is None
    assert global_to_circular(doc, doc.segments[0].global_end) is None


def _circular(circular_id: int, subject: str, body: str) -> dict[str, object]:
    return {
        "circular_id": circular_id,
        "subject": subject,
        "body": body,
        "created_on": f"2026-06-10T00:0{circular_id}:00Z",
        "submitter": "Unit Test",
    }


def _local_text(circular: dict[str, object]) -> str:
    return render_canonical(
        circular_id=int(circular["circular_id"]),
        subject=str(circular["subject"]),
        body=str(circular["body"]),
        created_on=str(circular["created_on"]),
        submitter=str(circular["submitter"]),
    ).rendered_text
