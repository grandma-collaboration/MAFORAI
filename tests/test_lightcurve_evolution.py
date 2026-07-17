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
from skyportal_corpus.extraction_v2.lightcurve_evolution import (
    LightcurveEvolutionExtractor,
)


def _extract(
    body: str,
    *,
    circular_id: int = 1,
    subject: str = "Light-curve follow-up",
) -> tuple[CanonicalDocument, list[EventEvidenceAnnotation]]:
    doc = render_canonical(
        circular_id=circular_id,
        subject=subject,
        body=body,
    )
    return doc, LightcurveEvolutionExtractor().extract(doc)


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
    rule_id: str,
) -> None:
    assert annotation.text == text
    assert annotation.label == "LIGHTCURVE_EVOLUTION"
    assert annotation.target == "counterpart"
    assert annotation.certainty == "confirmed"
    assert annotation.value is None
    assert annotation.unit is None
    assert annotation.comment is None
    assert annotation.needs_review is False
    assert annotation.rule_id == rule_id
    assert annotation.verify(doc.rendered_text)
    assert doc.rendered_text[annotation.span_start : annotation.span_end] == text


@pytest.mark.parametrize(
    ("body", "expected_text", "rule_id"),
    [
        (
            "The observations show optical rebrightening.",
            "optical rebrightening",
            "lightcurve_evolution.rise_brightening",
        ),
        (
            "We measure a flattening of the light curve.",
            "flattening of the light curve",
            "lightcurve_evolution.flatten_plateau",
        ),
        (
            "The source continues to fade.",
            "The source continues to fade",
            "lightcurve_evolution.fade_decline",
        ),
        (
            "The afterglow entered a plateau phase.",
            "plateau phase",
            "lightcurve_evolution.flatten_plateau",
        ),
        (
            "The flux shows a rapid decline.",
            "rapid decline",
            "lightcurve_evolution.fade_decline",
        ),
        (
            "There is no evidence for fading.",
            "There is no evidence for fading",
            "lightcurve_evolution.negative",
        ),
    ],
)
def test_real_lightcurve_phrasings_are_captured(
    body: str,
    expected_text: str,
    rule_id: str,
) -> None:
    doc, annotations = _extract(body)

    assert len(annotations) == 1
    _assert_annotation(
        doc,
        annotations[0],
        text=expected_text,
        rule_id=rule_id,
    )


@pytest.mark.parametrize(
    "body",
    [
        "This rebrightening may be due to late jet activity.",
        "This rebrightening\nmay be due to late jet activity.",
    ],
)
def test_physical_cause_clause_is_deferred_to_classification(body: str) -> None:
    _doc, annotations = _extract(body)

    assert annotations == []


def test_observed_rebrightening_survives_separate_cause_clause() -> None:
    doc, annotations = _extract(
        "We observe a rebrightening. "
        "This rebrightening may be due to late jet activity."
    )

    assert len(annotations) == 1
    _assert_annotation(
        doc,
        annotations[0],
        text="rebrightening",
        rule_id="lightcurve_evolution.rise_brightening",
    )


def test_negated_fading_is_not_emitted_as_positive_fade_decline() -> None:
    doc, annotations = _extract(
        "The lightcurve evolution of AT 2026owq is no longer fading; "
        "instead, the transient appears to be flattening."
    )

    assert not any(
        annotation.rule_id == "lightcurve_evolution.fade_decline"
        for annotation in annotations
    )
    flattening = [
        annotation
        for annotation in annotations
        if annotation.rule_id == "lightcurve_evolution.flatten_plateau"
    ]
    assert len(flattening) == 1
    _assert_annotation(
        doc,
        flattening[0],
        text="flattening",
        rule_id="lightcurve_evolution.flatten_plateau",
    )


def test_non_negated_fading_and_decline_remain_captured() -> None:
    doc, annotations = _extract(
        "The candidate continues to fade. The light curve shows a rapid decline."
    )

    fade_decline = [
        annotation
        for annotation in annotations
        if annotation.rule_id == "lightcurve_evolution.fade_decline"
    ]
    assert [annotation.text for annotation in fade_decline] == [
        "continues to fade",
        "rapid decline",
    ]
    assert all(annotation.verify(doc.rendered_text) for annotation in fade_decline)


@pytest.mark.parametrize(
    "body",
    [
        "The g-band is consistent with no evolution.",
        "Our observations suggest there is no significant evolution.",
    ],
)
def test_negative_flat_behavior_is_not_treated_as_a_physical_cause(
    body: str,
) -> None:
    doc, annotations = _extract(body)

    assert len(annotations) == 1
    assert annotations[0].rule_id == "lightcurve_evolution.negative"
    assert annotations[0].verify(doc.rendered_text)


def test_generic_variability_requires_lightcurve_context() -> None:
    doc, annotations = _extract("The counterpart is variable.")

    assert len(annotations) == 1
    _assert_annotation(
        doc,
        annotations[0],
        text="variable",
        rule_id="lightcurve_evolution.variability",
    )

    _doc, unrelated = _extract("The comparison object is a variable star.")
    assert unrelated == []


def test_real_circular_42311_now_has_lightcurve_annotations() -> None:
    doc = _render_real_circular(42311)
    annotations = LightcurveEvolutionExtractor().extract(doc)

    assert annotations
    assert any(
        annotation.text == "There is no evidence for fading"
        for annotation in annotations
    )
    assert all(annotation.verify(doc.rendered_text) for annotation in annotations)
