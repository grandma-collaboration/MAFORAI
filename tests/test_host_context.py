from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from skyportal_corpus.canonical.document import (
    CanonicalDocument,
    iter_real_circulars,
    render_canonical,
)
from skyportal_corpus.extraction_v2.annotations import EventEvidenceAnnotation
from skyportal_corpus.extraction_v2.host_context import HostContextExtractor


def _extract(
    body: str,
    *,
    circular_id: int = 1,
    subject: str = "Host context",
) -> tuple[CanonicalDocument, list[EventEvidenceAnnotation]]:
    doc = render_canonical(
        circular_id=circular_id,
        subject=subject,
        body=body,
    )
    return doc, HostContextExtractor().extract(doc)


def _render_real_circular(circular_id: int) -> CanonicalDocument:
    circular = next(
        item
        for item in iter_real_circulars(limit=100000)
        if int(item["circular_id"]) == circular_id
    )
    return _render_mapping(circular)


def _render_mapping(circular: Mapping[str, Any]) -> CanonicalDocument:
    return render_canonical(
        circular_id=int(circular["circular_id"]),
        subject=str(circular.get("subject") or ""),
        body=str(circular.get("body") or ""),
        event_id=circular.get("event_id"),
        created_on=circular.get("created_on"),
        submitter=circular.get("submitter"),
    )


def _assert_annotation(
    doc: CanonicalDocument,
    annotation: EventEvidenceAnnotation,
    *,
    text: str,
    target: str = "host",
    certainty: str = "unclear",
) -> None:
    assert annotation.text == text
    assert annotation.label == "HOST_CONTEXT"
    assert annotation.target == target
    assert annotation.certainty == certainty
    assert annotation.value is None
    assert annotation.unit is None
    assert annotation.comment is None
    assert annotation.needs_review is False
    assert annotation.rule_id is not None
    assert annotation.rule_id.startswith("host_context.")
    assert annotation.verify(doc.rendered_text)
    assert doc.rendered_text[annotation.span_start : annotation.span_end] == text


@pytest.mark.parametrize(
    ("body", "expected_text", "target"),
    [
        (
            "The host association is not obvious.",
            "host association is not obvious",
            "host",
        ),
        ("This object is a host candidate.", "host candidate", "host"),
        (
            "The transient is offset from the host galaxy.",
            "offset from the host galaxy",
            "host",
        ),
        (
            "It is in the vicinity of a galaxy association with "
            "~1.7 arcsec separation.",
            "in the vicinity of a galaxy association with "
            "~1.7 arcsec separation",
            "host",
        ),
        (
            "The absence of a host galaxy remains notable.",
            "absence of a host galaxy",
            "host",
        ),
        (
            "Several nearby galaxies are visible in the field.",
            "nearby galaxies",
            "nearby_galaxy",
        ),
    ],
)
def test_real_host_context_phrasings_are_captured(
    body: str,
    expected_text: str,
    target: str,
) -> None:
    doc, annotations = _extract(body)

    assert len(annotations) == 1
    _assert_annotation(
        doc,
        annotations[0],
        text=expected_text,
        target=target,
    )


def test_explicitly_established_host_is_confirmed_without_capturing_redshift() -> None:
    doc, annotations = _extract(
        "The host galaxy at z=0.473 shows strong nebular emission."
    )

    assert len(annotations) == 1
    _assert_annotation(
        doc,
        annotations[0],
        text="host galaxy",
        certainty="confirmed",
    )
    assert "z=0.473" not in annotations[0].text


@pytest.mark.parametrize(
    "body",
    [
        "A galaxy at z=0.473 is visible.",
        "We measure a redshift of z=0.473.",
    ],
)
def test_pure_redshift_values_are_not_host_context(body: str) -> None:
    _doc, annotations = _extract(body)

    assert annotations == []


def test_real_circular_44910_has_ambiguous_host_context() -> None:
    doc = _render_real_circular(44910)
    annotations = HostContextExtractor().extract(doc)

    matching = [
        annotation
        for annotation in annotations
        if annotation.text == "host association is not obvious"
    ]
    assert len(matching) == 1
    _assert_annotation(
        doc,
        matching[0],
        text="host association is not obvious",
    )


def test_real_circular_36371_has_galaxy_separation_context() -> None:
    doc = _render_real_circular(36371)
    annotations = HostContextExtractor().extract(doc)

    matching = [
        annotation
        for annotation in annotations
        if annotation.text
        == "in the vicinity of a galaxy association with ~1.7 arcsec separation"
    ]
    assert len(matching) == 1
    _assert_annotation(
        doc,
        matching[0],
        text=(
            "in the vicinity of a galaxy association with "
            "~1.7 arcsec separation"
        ),
    )
