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
from skyportal_corpus.extraction_v2.spectroscopy import SpectroscopyExtractor


def _extract(
    body: str,
    *,
    circular_id: int = 1,
    subject: str = "Spectroscopic follow-up",
) -> tuple[CanonicalDocument, list[EventEvidenceAnnotation]]:
    doc = render_canonical(
        circular_id=circular_id,
        subject=subject,
        body=body,
    )
    return doc, SpectroscopyExtractor().extract(doc)


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
    target: str = "counterpart",
) -> None:
    assert annotation.text == text
    assert annotation.label == "SPECTROSCOPY"
    assert annotation.target == target
    assert annotation.certainty == "confirmed"
    assert annotation.value is None
    assert annotation.unit is None
    assert annotation.comment is None
    assert annotation.needs_review is False
    assert annotation.rule_id is not None
    assert annotation.rule_id.startswith("spectroscopy.")
    assert annotation.verify(doc.rendered_text)
    assert doc.rendered_text[annotation.span_start : annotation.span_end] == text


@pytest.mark.parametrize(
    ("body", "expected_text"),
    [
        (
            "We obtained spectroscopy with ALFOSC.",
            "We obtained spectroscopy with ALFOSC",
        ),
        (
            "We identify Mg II and Ca II absorption features.",
            "Mg II and Ca II absorption features",
        ),
        ("The spectrum shows an [O II] emission line.", "[O II] emission line"),
        (
            "The spectrum shows a P-Cygni profile of the H-alpha line.",
            "P-Cygni profile of the H-alpha line",
        ),
    ],
)
def test_real_spectroscopy_phrasings_are_captured(
    body: str,
    expected_text: str,
) -> None:
    doc, annotations = _extract(body)

    matching = [
        annotation
        for annotation in annotations
        if annotation.text == expected_text
    ]
    assert len(matching) == 1
    _assert_annotation(doc, matching[0], text=expected_text)


@pytest.mark.parametrize(
    "body",
    [
        "The time-averaged WXT 0.5-4 keV spectrum was fitted.",
        "The average WXT 0.5 - 4 keV spectrum was fitted.",
        "The average FXT 0.5-10 keV spectrum was fitted.",
        "The prompt gamma-ray spectrum was fitted with a cutoff power law.",
    ],
)
def test_high_energy_spectra_are_excluded(body: str) -> None:
    _doc, annotations = _extract(body)

    assert annotations == []


@pytest.mark.parametrize(
    ("body", "expected_text"),
    [
        (
            "The optical spectrum obtained with X-shooter is featureless.",
            "The optical spectrum",
        ),
        (
            "The spectrum shows H-alpha and H-beta emission lines.",
            "The spectrum",
        ),
        (
            "The spectrum covers 3500-9000 Angstroms.",
            "The spectrum",
        ),
    ],
)
def test_optical_spectrum_rule_requires_optical_context(
    body: str,
    expected_text: str,
) -> None:
    doc, annotations = _extract(body)
    matching = [
        annotation
        for annotation in annotations
        if annotation.rule_id == "spectroscopy.spectrum"
    ]

    assert len(matching) == 1
    _assert_annotation(doc, matching[0], text=expected_text)


def test_optical_spectrograph_observation_stays_counterpart_when_gbm_is_cited() -> None:
    doc, annotations = _extract(
        "We observed the field of GRB 241228B triggered by Fermi/GBM "
        "using the X-shooter spectrograph."
    )

    assert len(annotations) == 1
    _assert_annotation(
        doc,
        annotations[0],
        text=(
            "We observed the field of GRB 241228B triggered by Fermi/GBM "
            "using the X-shooter spectrograph"
        ),
        target="counterpart",
    )


@pytest.mark.parametrize(
    "body",
    [
        "The redshift is z=0.473.",
        "The transient is a type II supernova.",
        "Further spectroscopic observations are encouraged.",
    ],
)
def test_redshift_classification_and_followup_only_phrases_are_excluded(
    body: str,
) -> None:
    _doc, annotations = _extract(body)

    assert annotations == []


def test_real_circular_44914_has_observation_and_absorption_features() -> None:
    doc = _render_real_circular(44914)
    annotations = SpectroscopyExtractor().extract(doc)
    by_text = {annotation.text: annotation for annotation in annotations}

    for expected_text in (
        "We obtained spectroscopy with ALFOSC",
        "Mg II and Ca II absorption features",
    ):
        assert expected_text in by_text
        _assert_annotation(doc, by_text[expected_text], text=expected_text)


def test_real_circular_45004_captures_each_named_doublet_feature() -> None:
    doc = _render_real_circular(45004)
    annotations = SpectroscopyExtractor().extract(doc)
    features = [
        annotation
        for annotation in annotations
        if annotation.rule_id == "spectroscopy.features"
    ]
    by_text = {annotation.text: annotation for annotation in features}

    for expected_text in (
        "Ca II doublet in absorption",
        "[O II] doublet in emission",
    ):
        assert expected_text in by_text
        _assert_annotation(doc, by_text[expected_text], text=expected_text)

    assert all(annotation.verify(doc.rendered_text) for annotation in features)


def test_real_circular_41532_has_p_cygni_profile() -> None:
    doc = _render_real_circular(41532)
    annotations = SpectroscopyExtractor().extract(doc)
    matching = [
        annotation
        for annotation in annotations
        if annotation.text == "P-Cygni profile of the H-alpha line"
    ]

    assert len(matching) == 1
    _assert_annotation(
        doc,
        matching[0],
        text="P-Cygni profile of the H-alpha line",
    )
