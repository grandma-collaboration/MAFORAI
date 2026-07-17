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
from skyportal_corpus.extraction_v2.counterpart_association import (
    CounterpartAssociationExtractor,
)


def _extract(
    body: str,
    *,
    circular_id: int = 1,
    subject: str = "Counterpart follow-up",
) -> tuple[CanonicalDocument, list[EventEvidenceAnnotation]]:
    doc = render_canonical(
        circular_id=circular_id,
        subject=subject,
        body=body,
    )
    return doc, CounterpartAssociationExtractor().extract(doc)


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
    certainty: str,
) -> None:
    assert annotation.text == text
    assert annotation.label == "COUNTERPART_ASSOCIATION"
    assert annotation.target == "counterpart"
    assert annotation.certainty == certainty
    assert annotation.value is None
    assert annotation.unit is None
    assert annotation.comment is None
    assert annotation.needs_review is False
    assert annotation.rule_id is not None
    assert annotation.rule_id.startswith("counterpart_association.")
    assert annotation.verify(doc.rendered_text)
    assert doc.rendered_text[annotation.span_start : annotation.span_end] == text


@pytest.mark.parametrize(
    ("body", "expected_text", "certainty"),
    [
        (
            "We report an optical counterpart.",
            "optical counterpart",
            "candidate",
        ),
        (
            "We detected a candidate optical afterglow.",
            "candidate optical afterglow",
            "candidate",
        ),
        (
            "The temporal decay strongly suggest this is the optical counterpart.",
            "strongly suggest this is the optical counterpart",
            "candidate",
        ),
        (
            "This is the spectroscopically confirmed optical counterpart.",
            "spectroscopically confirmed optical counterpart",
            "confirmed",
        ),
    ],
)
def test_association_establishing_phrases_are_captured(
    body: str,
    expected_text: str,
    certainty: str,
) -> None:
    doc, annotations = _extract(body)

    assert len(annotations) == 1
    _assert_annotation(
        doc,
        annotations[0],
        text=expected_text,
        certainty=certainty,
    )


@pytest.mark.parametrize(
    "body",
    [
        "No optical counterpart consistent with the INTEGRAL position was found.",
        "GOTO26fua / AT2026owq",
    ],
)
def test_negative_and_identity_linking_boundaries_are_excluded(body: str) -> None:
    _doc, annotations = _extract(body)

    assert annotations == []


def test_unrelated_without_clause_does_not_gate_a_possible_counterpart() -> None:
    doc, annotations = _extract(
        "The aperture magnitude without template subtraction of the possible "
        "counterpart of EP241202b is reported below."
    )

    assert len(annotations) == 1
    _assert_annotation(
        doc,
        annotations[0],
        text="possible counterpart",
        certainty="candidate",
    )


def test_not_telescope_acronym_in_subject_is_not_a_negation() -> None:
    doc, annotations = _extract(
        "Follow-up observations are reported.",
        subject="EP240618a: NOT optical counterpart candidate",
    )

    assert len(annotations) == 1
    _assert_annotation(
        doc,
        annotations[0],
        text="optical counterpart candidate",
        certainty="candidate",
    )


def test_explicit_detection_with_an_adverb_establishes_the_afterglow_role() -> None:
    doc, annotations = _extract(
        "In grz images taken with the acquisition camera, we clearly detect "
        "the optical afterglow (Gompertz et al., GCN 35805)."
    )

    assert len(annotations) == 1
    _assert_annotation(
        doc,
        annotations[0],
        text="optical afterglow",
        certainty="candidate",
    )


@pytest.mark.parametrize(
    "body",
    [
        "We fit the afterglow model with a broken power law.",
        "The afterglow emission is consistent with synchrotron radiation.",
        "The counterpart was discussed in the previous circular.",
    ],
)
def test_bare_non_associative_mentions_are_not_captured(body: str) -> None:
    _doc, annotations = _extract(body)

    assert annotations == []


def test_real_circular_34681_has_counterpart_association() -> None:
    doc = _render_real_circular(34681)
    annotations = CounterpartAssociationExtractor().extract(doc)

    assert annotations
    assert any(
        annotation.text == "candidate optical counterpart"
        for annotation in annotations
    )
    assert all(annotation.verify(doc.rendered_text) for annotation in annotations)
