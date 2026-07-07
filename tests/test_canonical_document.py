from __future__ import annotations

import hashlib
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from skyportal_corpus.canonical.document import _strip_illegal_xml_chars, render_canonical


def test_canonical_document_invariants() -> None:
    document = render_canonical(
        circular_id=42,
        event_id="S250101abc",
        subject="Synthetic\r\nCircular\rSubject",
        created_on="2026-01-02T03:04:05Z",
        submitter="Unit Test",
        body="First line\r\nSecond\x07 line\rThird line with enough text for extraction.",
    )

    for segment in document.segments:
        assert document.rendered_text[segment.start : segment.end] == segment.text

    body_segment = next(segment for segment in document.segments if segment.name == "body")
    body_start = document.rendered_text.index("\n\n") + 2
    assert body_segment.start == body_start
    assert body_segment.text == document.rendered_text[body_start:]

    recalculated_sha256 = hashlib.sha256(document.rendered_text.encode("utf-8")).hexdigest()
    assert recalculated_sha256 == document.text_sha256

    assert document.rendered_text == _strip_illegal_xml_chars(document.rendered_text)


def test_render_canonical_is_deterministic() -> None:
    kwargs = {
        "circular_id": 7,
        "event_id": "S250102abc",
        "subject": "Same subject",
        "created_on": "2026-02-03T04:05:06Z",
        "submitter": "Same Submitter",
        "body": "Same body\nwith stable content.",
    }

    first = render_canonical(**kwargs)
    second = render_canonical(**kwargs)

    assert first.rendered_text == second.rendered_text
    assert first.text_sha256 == second.text_sha256


def test_newlines_are_normalized_to_lf() -> None:
    document = render_canonical(
        circular_id=8,
        subject="A\r\nB\rC",
        body="D\r\nE\rF",
    )

    assert "\r" not in document.rendered_text
    assert "SUBJECT: A\nB\nC\n" in document.rendered_text
    assert document.rendered_text.endswith("D\nE\nF")


def test_illegal_xml_control_character_is_removed() -> None:
    document = render_canonical(
        circular_id=9,
        subject="Subject",
        body="Body before bell\x07 body after bell",
    )

    assert "\x07" not in document.rendered_text
    assert "Body before bell body after bell" in document.rendered_text
