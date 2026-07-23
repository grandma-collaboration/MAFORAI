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
from skyportal_corpus.extraction_v2.classification_interpretation import (
    ClassificationInterpretationExtractor,
)


def _extract(
    body: str,
    *,
    circular_id: int = 1,
    subject: str = "Event classification",
) -> tuple[CanonicalDocument, list[EventEvidenceAnnotation]]:
    doc = render_canonical(
        circular_id=circular_id,
        subject=subject,
        body=body,
    )
    return doc, ClassificationInterpretationExtractor().extract(doc)


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
    value: str,
    certainty: str = "tentative",
    rule_id: str | None = None,
) -> None:
    assert annotation.text == text
    assert annotation.label == "CLASSIFICATION_INTERPRETATION"
    assert annotation.target == "event"
    assert annotation.certainty == certainty
    assert annotation.value == value
    assert annotation.unit is None
    assert annotation.comment is None
    assert annotation.needs_review is False
    if rule_id is None:
        assert annotation.rule_id is not None
        assert annotation.rule_id.startswith("classification_interpretation.")
    else:
        assert annotation.rule_id == rule_id
    assert annotation.verify(doc.rendered_text)
    assert doc.rendered_text[annotation.span_start : annotation.span_end] == text


@pytest.mark.parametrize(
    ("body", "expected_text", "expected_value", "rule_id"),
    [
        (
            "The evidence favors a likely long GRB.",
            "likely long GRB",
            "long GRB",
            "classification_interpretation.qualified_class",
        ),
        (
            "The event belongs to the Type II GRB population.",
            "Type II GRB",
            "Type II GRB",
            "classification_interpretation.type_grb",
        ),
        (
            "The excess may represent a possible supernova.",
            "possible supernova",
            "supernova",
            "classification_interpretation.qualified_class",
        ),
        (
            "This rebrightening may be due to late jet activity.",
            "This rebrightening may be due to late jet activity",
            "late jet activity",
            "classification_interpretation.physical_cause",
        ),
    ],
)
def test_real_classification_and_interpretation_phrasings_are_captured(
    body: str,
    expected_text: str,
    expected_value: str,
    rule_id: str,
) -> None:
    doc, annotations = _extract(body)

    assert len(annotations) == 1
    _assert_annotation(
        doc,
        annotations[0],
        text=expected_text,
        value=expected_value,
        rule_id=rule_id,
    )


def test_firm_classification_marker_sets_confirmed_certainty() -> None:
    doc, annotations = _extract(
        "The transient was spectroscopically classified as a Type Ic supernova."
    )

    assert len(annotations) == 1
    _assert_annotation(
        doc,
        annotations[0],
        text="spectroscopically classified as a Type Ic supernova",
        value="supernova",
        certainty="confirmed",
    )


@pytest.mark.parametrize(
    "body",
    [
        "The source is consistent with the Swift-XRT position.",
        "The light curve shows a rebrightening.",
    ],
)
def test_descriptors_positions_and_observed_evolution_are_excluded(
    body: str,
) -> None:
    _doc, annotations = _extract(body)

    assert annotations == []


@pytest.mark.parametrize(
    ("body", "expected_text", "expected_value"),
    [
        (
            "We suggest that SN 2025ulz is a type II supernova "
            "(of unconfirmed subtype at this point).",
            "We suggest that SN 2025ulz is a type II supernova",
            "supernova",
        ),
        (
            "The observations make a kilonova the most likely interpretation.",
            "make a kilonova the most likely interpretation",
            "kilonova",
        ),
        (
            "The spectrum is consistent with those of very young supernovae "
            "that demonstrate flash-ionisation features.",
            "is consistent with those of very young supernovae",
            "supernova",
        ),
        (
            "This would be consistent with Huang et al. (GCN 44075) "
            "interpretaiton of the EP260321a as shock breakout signature.",
            "interpretaiton of the EP260321a as shock breakout signature",
            "shock breakout",
        ),
        (
            "The source exhibits a brightness similar to that of an "
            "AT2017gfo-like kilonova.",
            "AT2017gfo-like kilonova",
            "kilonova",
        ),
        (
            "The LOT optical lightcurve could be explained by shock cooling "
            "and a rise from a supernovae.",
            "could be explained by shock cooling and a rise from a supernovae",
            "shock cooling",
        ),
    ],
)
def test_real_interpretation_structures_are_captured(
    body: str,
    expected_text: str,
    expected_value: str,
) -> None:
    doc, annotations = _extract(body)

    assert len(annotations) == 1
    _assert_annotation(
        doc,
        annotations[0],
        text=expected_text,
        value=expected_value,
        certainty="tentative",
        rule_id="classification_interpretation.interpretation",
    )


@pytest.mark.parametrize(
    ("body", "expected_text", "certainty", "expected_value"),
    [
        (
            "The long-duration GRB 230114A was detected by Fermi/GBM.",
            "long-duration GRB",
            "confirmed",
            "long GRB",
        ),
        (
            "The long GRB 240205B was observed by Konus-Wind.",
            "long GRB",
            "confirmed",
            "long GRB",
        ),
        (
            "The analysis showed the detection of a short-duration "
            "GRB 240123C.",
            "short-duration GRB",
            "confirmed",
            "short GRB",
        ),
        (
            "The subject describes a short hard GRB detected by IBAS.",
            "short hard GRB",
            "confirmed",
            "short GRB",
        ),
        (
            "This burst has a typical brightness, duration, and hardness "
            "of a long GRB.",
            "long GRB",
            "tentative",
            "long GRB",
        ),
    ],
)
def test_real_grb_class_statements_are_captured(
    body: str,
    expected_text: str,
    certainty: str,
    expected_value: str,
) -> None:
    doc, annotations = _extract(body)

    assert len(annotations) == 1
    _assert_annotation(
        doc,
        annotations[0],
        text=expected_text,
        value=expected_value,
        certainty=certainty,
        rule_id="classification_interpretation.grb_class",
    )


@pytest.mark.parametrize(
    "body",
    [
        "The Fermi GBM on-ground location is consistent with the "
        "Swift/BAT-GUANO position.",
        "Our upper limits are consistent with Perez-Garcia et al. "
        "(GCN 43364).",
        "GRB 230209A, tentatively classified as GRB 230209A, is in fact "
        "not a GRB.",
        "These sources have been ruled out as kilonovae candidates.",
        "We obtained spectroscopy to explore the nature of EP260321a.",
        "Further observations are needed to determine the nature of this "
        "transient.",
    ],
)
def test_consistency_retraction_and_nature_call_boundaries_are_excluded(
    body: str,
) -> None:
    _doc, annotations = _extract(body)

    assert annotations == []


def test_observed_evolution_and_physical_cause_are_separated() -> None:
    doc, annotations = _extract(
        "We observe a rebrightening. "
        "This rebrightening may be due to late jet activity."
    )

    assert len(annotations) == 1
    _assert_annotation(
        doc,
        annotations[0],
        text="This rebrightening may be due to late jet activity",
        value="late jet activity",
    )


def test_physical_class_after_presence_phrase_is_captured() -> None:
    doc, annotations = _extract(
        "The observations are consistent with the presence of a kilonova."
    )

    assert len(annotations) == 1
    _assert_annotation(
        doc,
        annotations[0],
        text="are consistent with the presence of a kilonova",
        value="kilonova",
    )


@pytest.mark.parametrize(
    "body",
    [
        (
            "this excess is too bright to be powered by the emergence of "
            "a typical GRB-supernova signal."
        ),
        "inconsistent with expectations for an emerging supernova.",
    ],
)
def test_real_physical_class_exclusions_are_captured(body: str) -> None:
    doc, annotations = _extract(body)

    assert len(annotations) == 1
    annotation = annotations[0]
    _assert_annotation(
        doc,
        annotation,
        text=body.rstrip("."),
        value="not a supernova",
        certainty="rejected",
        rule_id="classification_interpretation.class_exclusion",
    )


def test_negated_physical_consistency_is_not_a_positive_interpretation() -> None:
    _doc, annotations = _extract(
        "The blue color is not consistent with a kilonova spectrum."
    )

    assert annotations == []


def test_real_circular_35037_has_physical_interpretation() -> None:
    doc = _render_real_circular(35037)
    annotations = ClassificationInterpretationExtractor().extract(doc)

    assert annotations
    assert any(
        "may be due to a magnetar giant flare" in annotation.text
        for annotation in annotations
    )
    assert all(annotation.verify(doc.rendered_text) for annotation in annotations)
