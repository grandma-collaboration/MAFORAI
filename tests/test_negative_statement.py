from __future__ import annotations

import pytest

from skyportal_corpus.canonical.document import CanonicalDocument, render_canonical
from skyportal_corpus.extraction_v2.annotations import EventEvidenceAnnotation
from skyportal_corpus.extraction_v2.negative_statement import (
    NegativeStatementExtractor,
)


def _extract(
    body: str,
    *,
    circular_id: int = 1,
    subject: str = "Scientific follow-up report",
) -> tuple[CanonicalDocument, list[EventEvidenceAnnotation]]:
    doc = render_canonical(
        circular_id=circular_id,
        subject=subject,
        body=body,
    )
    annotations = NegativeStatementExtractor().extract(doc)
    return doc, annotations


def _assert_annotation(
    doc: CanonicalDocument,
    annotation: EventEvidenceAnnotation,
    *,
    text: str,
    certainty: str,
    rule_id: str,
) -> None:
    assert annotation.text == text
    assert annotation.label == "NEGATIVE_STATEMENT"
    assert annotation.certainty == certainty
    assert annotation.rule_id == rule_id
    assert annotation.target is None
    assert annotation.value is None
    assert annotation.unit is None
    assert annotation.verify(doc.rendered_text)
    assert doc.rendered_text[annotation.span_start : annotation.span_end] == text


@pytest.mark.parametrize(
    ("body", "expected_text", "rule_id"),
    [
        ("The event is not a GRB.", "not a GRB", "negative_statement.not_grb"),
        (
            "GRB 250101A is a false trigger.",
            "GRB 250101A is a false trigger",
            "negative_statement.false_trigger",
        ),
        (
            "This circular is a retraction of GCN 44900.",
            "retraction of GCN 44900",
            "negative_statement.retraction",
        ),
        (
            "The transient is not associated with the host galaxy.",
            "not associated with the host galaxy",
            "negative_statement.not_associated",
        ),
        (
            "The localization rules out the association.",
            "rules out the association",
            "negative_statement.rules_out",
        ),
    ],
)
def test_rejections_are_emitted_with_rejected_certainty(
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
        certainty="rejected",
        rule_id=rule_id,
    )
    assert annotations[0].comment is None
    assert annotations[0].needs_review is False


@pytest.mark.parametrize(
    ("body", "expected_text", "rule_id"),
    [
        (
            "We find no evidence for a supernova.",
            "no evidence for a supernova",
            "negative_statement.no_evidence",
        ),
        (
            "We find no evidence for a jet break.",
            "no evidence for a jet break",
            "negative_statement.no_evidence",
        ),
        (
            "The spectrum shows no significant excess.",
            "no significant excess",
            "negative_statement.no_significant",
        ),
    ],
)
def test_negative_findings_are_emitted_with_confirmed_certainty(
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
        certainty="confirmed",
        rule_id=rule_id,
    )
    assert annotations[0].comment is None
    assert annotations[0].needs_review is False


@pytest.mark.parametrize(
    "behavior",
    [
        "fading",
        "brightening",
        "rising",
        "dimming",
        "rebrightening",
        "variability",
        "variation",
        "decay",
        "decline",
        "evolution",
        "flaring",
    ],
)
def test_lightcurve_behavior_negatives_are_deferred(behavior: str) -> None:
    _doc, annotations = _extract(f"There is no evidence for {behavior}.")

    assert annotations == []


def test_real_circular_42311_fading_claims_yield_zero_annotations() -> None:
    body = "\n".join(
        [
            "Source 2: There is no evidence for fading.",
            "Source 3: There is no evidence for fading.",
            "Source 4: There is no evidence for fading.",
            "Source 5: There is no evidence for fading.",
            "Source 6: There is no evidence for fading.",
            "Source 7: There is no evidence for fading.",
            "Source 8: There is no evidence for fading.",
            "Source 9: There is no evidence for fading.",
        ]
    )
    _doc, annotations = _extract(
        body,
        circular_id=42311,
        subject="sb25101602: Swift-XRT counterpart detection",
    )

    assert annotations == []


@pytest.mark.parametrize(
    "body",
    [
        (
            "We find no evidence of the source prior to the GRB in GOTO "
            "observations down to a 5-sigma depth of >20.8 AB mag."
        ),
        (
            "We find no evidence for pre-GRB emission in the ZTF observations "
            "or the ATLAS forced photometry server."
        ),
        "X2 is not detected, with a 3 sigma detection limit > 21.54 mag (AB).",
        "VLA-4 and VLA-5 are not detected in our images.",
        "We observed the field for one hour, and have not detected any afterglow.",
        "An upper limit of R = 19.0 with no detection of the afterglow.",
        (
            "No optical counterpart consistent with the position "
            "(GCN Circ. 12345) is detected down to r > 21.5 mag."
        ),
    ],
)
def test_optical_ir_radio_photometric_negatives_are_excluded(body: str) -> None:
    _doc, annotations = _extract(body)

    assert annotations == []


def test_photometric_context_gates_rejection_rules_too() -> None:
    _doc, annotations = _extract(
        "The source has r = 24.5 mag and is unrelated to the X-ray transient."
    )

    assert annotations == []


@pytest.mark.parametrize(
    ("body", "expected_text"),
    [
        (
            "No optical counterpart consistent with the INTEGRAL position is "
            "detected in the initial UVOT exposures.",
            "No optical counterpart consistent with the INTEGRAL position",
        ),
        (
            "The prompt search found no counterpart candidates.",
            "no counterpart candidates",
        ),
        (
            "No confirmed counterpart is found in the XRT or UVOT data within "
            "the BAT error circle.",
            "No confirmed counterpart is found",
        ),
    ],
)
def test_counterpart_absence_claims_are_confirmed(
    body: str,
    expected_text: str,
) -> None:
    doc, annotations = _extract(body)

    assert len(annotations) == 1
    _assert_annotation(
        doc,
        annotations[0],
        text=expected_text,
        certainty="confirmed",
        rule_id="negative_statement.no_counterpart",
    )
    assert annotations[0].needs_review is False
    assert annotations[0].comment is None


def test_xray_catalog_counterpart_absence_is_retained_for_review() -> None:
    doc, annotations = _extract(
        "There is no counterpart in the 3MAXI 7-year catalog with the "
        "sensitivity of 0.6e-11 erg/s/cm2 in 4-10 keV."
    )

    assert len(annotations) == 1
    annotation = annotations[0]
    _assert_annotation(
        doc,
        annotation,
        text="no counterpart in the 3MAXI 7-year catalog",
        certainty="confirmed",
        rule_id="negative_statement.no_counterpart",
    )
    assert annotation.needs_review is True
    assert annotation.comment == (
        "Counterpart absence is based on a catalog sensitivity; verify the "
        "catalog scope and completeness."
    )


@pytest.mark.parametrize(
    "body",
    [
        "GRB 250309B and IceCube-250309A are unrelated.",
        "Potential Magellan candidates from GCN 36263 are unrelated.",
    ],
)
def test_clause_final_unrelated_is_a_rejection(body: str) -> None:
    doc, annotations = _extract(body)

    assert len(annotations) == 1
    _assert_annotation(
        doc,
        annotations[0],
        text="are unrelated",
        certainty="rejected",
        rule_id="negative_statement.unrelated",
    )


def test_unlikely_counterpart_is_a_soft_rejection() -> None:
    doc, annotations = _extract(
        "Their status as catalogued objects makes them unlikely to be the "
        "X-ray counterpart."
    )

    assert len(annotations) == 1
    _assert_annotation(
        doc,
        annotations[0],
        text="unlikely to be the X-ray counterpart",
        certainty="rejected",
        rule_id="negative_statement.unlikely",
    )


def test_disfavored_association_is_a_soft_rejection() -> None:
    doc, annotations = _extract("The proposed association is disfavored.")

    assert len(annotations) == 1
    _assert_annotation(
        doc,
        annotations[0],
        text="disfavored",
        certainty="rejected",
        rule_id="negative_statement.unlikely",
    )


def test_unlikely_association_after_redshift_sentence_is_not_gated() -> None:
    doc, annotations = _extract(
        "The host galaxy has strong emission lines at z = 0.0658. "
        "We conclude that AT2024hdo is unlikely to be associated with S240422ed."
    )

    assert len(annotations) == 1
    _assert_annotation(
        doc,
        annotations[0],
        text="unlikely to be associated with S240422ed",
        certainty="rejected",
        rule_id="negative_statement.unlikely",
    )


def test_xray_flux_context_is_not_treated_as_photometry() -> None:
    doc, annotations = _extract(
        "There was no significant X-ray signal down to a catalog sensitivity "
        "of 1.8e-12 erg/s/cm2 in 0.6-10 keV."
    )

    assert len(annotations) == 1
    _assert_annotation(
        doc,
        annotations[0],
        text="no significant X-ray signal",
        certainty="confirmed",
        rule_id="negative_statement.no_significant",
    )


@pytest.mark.parametrize(
    ("body", "expected_text", "certainty", "rule_id"),
    [
        (
            "Swift Trigger 1434591 is not a GRB.",
            "not a GRB",
            "rejected",
            "negative_statement.not_grb",
        ),
        (
            "This candidate is a false trigger.",
            "a false trigger",
            "rejected",
            "negative_statement.false_trigger",
        ),
        (
            "The trigger is not a real astrophysical event.",
            "not a real astrophysical event",
            "rejected",
            "negative_statement.not_real",
        ),
        (
            "This is a retraction of GCN 44900.",
            "retraction of GCN 44900",
            "rejected",
            "negative_statement.retraction",
        ),
        (
            "The candidate was retracted.",
            "retracted",
            "rejected",
            "negative_statement.retraction",
        ),
        (
            "Retraction.",
            "Retraction",
            "rejected",
            "negative_statement.retraction",
        ),
        (
            "The candidates are unrelated to S240422ed.",
            "unrelated to S240422ed",
            "rejected",
            "negative_statement.unrelated",
        ),
        (
            "The two candidates can be ruled out.",
            "ruled out",
            "rejected",
            "negative_statement.rules_out",
        ),
        (
            "No significant excess emission was detected from the region.",
            "No significant excess emission",
            "confirmed",
            "negative_statement.no_significant",
        ),
        (
            "There was no significant signal.",
            "no significant signal",
            "confirmed",
            "negative_statement.no_significant",
        ),
        (
            "There was no significant X-ray signal.",
            "no significant X-ray signal",
            "confirmed",
            "negative_statement.no_significant",
        ),
        (
            "No significant activity has been reported.",
            "No significant activity",
            "confirmed",
            "negative_statement.no_significant",
        ),
        (
            "Preliminary analysis indicates no significant (>5sigma) new "
            "excess emission (>100 MeV).",
            "no significant (>5sigma) new excess emission (>100 MeV)",
            "confirmed",
            "negative_statement.no_significant",
        ),
        (
            "The association is not confirmed.",
            "not confirmed",
            "confirmed",
            "negative_statement.not_confirmed",
        ),
    ],
)
def test_v1_confirmed_captures_do_not_regress(
    body: str,
    expected_text: str,
    certainty: str,
    rule_id: str,
) -> None:
    doc, annotations = _extract(body)

    assert len(annotations) == 1
    _assert_annotation(
        doc,
        annotations[0],
        text=expected_text,
        certainty=certainty,
        rule_id=rule_id,
    )


def test_bare_not_detected_remains_uncovered() -> None:
    _doc, annotations = _extract("The counterpart was not detected.")

    assert annotations == []


def test_methodological_rule_out_is_not_a_rejection() -> None:
    _doc, annotations = _extract(
        "We searched archival photometry to rule out unrelated transients."
    )

    assert annotations == []


def test_not_a_real_source_is_a_rejection() -> None:
    doc, annotations = _extract("The candidate is not a real source.")

    assert len(annotations) == 1
    _assert_annotation(
        doc,
        annotations[0],
        text="not a real source",
        certainty="rejected",
        rule_id="negative_statement.not_real",
    )


def test_terminal_ruled_out_is_captured_but_uncertainty_is_not_inverted() -> None:
    ruled_out_doc, ruled_out = _extract("The two candidates can be ruled out.")
    _uncertain_doc, uncertain = _extract("The candidate cannot be ruled out.")

    assert len(ruled_out) == 1
    _assert_annotation(
        ruled_out_doc,
        ruled_out[0],
        text="ruled out",
        certainty="rejected",
        rule_id="negative_statement.rules_out",
    )
    assert uncertain == []


def test_no_annotation_carries_a_lightcurve_value() -> None:
    doc, annotations = _extract(
        "There is no evidence for fading. There is no evidence for a supernova. "
        "The source is not a GRB."
    )

    assert {annotation.text for annotation in annotations} == {
        "no evidence for a supernova",
        "not a GRB",
    }
    assert all(annotation.value is None for annotation in annotations)
    assert all(annotation.verify(doc.rendered_text) for annotation in annotations)
