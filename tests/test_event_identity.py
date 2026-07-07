from __future__ import annotations

import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from skyportal_corpus.canonical.document import render_canonical
from skyportal_corpus.extraction_v2.annotations import EventEvidenceAnnotation
from skyportal_corpus.extraction_v2.event_identity import EventIdentityExtractor


def test_event_identity_positive_subject_and_body_only() -> None:
    doc = render_canonical(
        circular_id=1,
        subject="GRB 240625A",
        body="We report a comparison source EP240315a in the field.",
    )

    annotations = EventIdentityExtractor().extract(doc)

    assert len(annotations) == 2
    for annotation in annotations:
        assert annotation.target == "event"
        assert annotation.certainty == "confirmed"
        assert annotation.text == doc.rendered_text[annotation.span_start : annotation.span_end]
        assert annotation.verify(doc.rendered_text)

    by_value = {annotation.value: annotation for annotation in annotations}
    assert by_value["GRB 240625A"].needs_review is False
    assert by_value["GRB 240625A"].confidence == 1.0

    ep_annotation = by_value["EP 240315a"]
    assert ep_annotation.text == "EP240315a"
    assert ep_annotation.needs_review is True
    assert ep_annotation.confidence == 0.5
    assert ep_annotation.comment


@pytest.mark.parametrize(
    ("raw_value", "expected_value"),
    [
        ("GRB230101.09", "GRB 230101.09"),
        ("GRB230110.65", "GRB 230110.65"),
    ],
)
def test_event_identity_grb_dayfraction_preserves_fraction(raw_value: str, expected_value: str) -> None:
    doc = render_canonical(
        circular_id=7,
        subject="Fermi trigger report",
        body=f"Fermi {raw_value} was observed by MASTER.",
    )

    annotations = EventIdentityExtractor().extract(doc)

    assert len(annotations) == 1
    annotation = annotations[0]
    assert annotation.text == raw_value
    assert annotation.value == expected_value
    assert annotation.rule_id == "event_identity.grb_dayfraction"
    assert annotation.needs_review is True
    assert annotation.confidence == 0.5
    assert annotation.comment == (
        "Formato de fracción de día (MASTER/Fermi); puede corresponder a un GRB "
        "con letra oficial. Verificar el mapeo al evento canónico."
    )
    assert annotation.verify(doc.rendered_text)


def test_event_identity_grb_dayfraction_does_not_emit_truncated_grb() -> None:
    doc = render_canonical(
        circular_id=8,
        subject="Fermi trigger report",
        body="Fermi GRB230101.09 was observed by MASTER.",
    )

    annotations = EventIdentityExtractor().extract(doc)

    assert [annotation.value for annotation in annotations] == ["GRB 230101.09"]
    assert "GRB 230101" not in {annotation.value for annotation in annotations}


def test_event_identity_grb_with_letter_still_uses_normal_grb_rule() -> None:
    doc = render_canonical(
        circular_id=9,
        subject="GRB 230101A",
        body="This circular reports the event.",
    )

    annotations = EventIdentityExtractor().extract(doc)

    assert len(annotations) == 1
    assert annotations[0].value == "GRB 230101A"
    assert annotations[0].rule_id == "event_identity.grb"
    assert annotations[0].needs_review is False


def test_event_identity_ep_wxt_trigger_phrase_requires_review() -> None:
    doc = render_canonical(
        circular_id=11,
        subject="EP trigger report",
        body="The EP-WXT trigger 01709176712 is likely a flaring star.",
    )

    annotations = EventIdentityExtractor().extract(doc)

    assert len(annotations) == 1
    annotation = annotations[0]
    assert annotation.text == "EP-WXT trigger 01709176712"
    assert annotation.value == "EP-WXT 01709176712"
    assert annotation.rule_id == "event_identity.ep_wxt_trigger"
    assert annotation.needs_review is True
    assert annotation.confidence == 0.5
    assert annotation.comment == (
        "Identificador de trigger EP-WXT; el anotador debe verificar el mapeo al evento/fuente canónica."
    )
    assert annotation.verify(doc.rendered_text)


def test_event_identity_ep_wxt_compact_trigger_requires_review() -> None:
    doc = render_canonical(
        circular_id=12,
        subject="EP follow-up report",
        body="EP/WXT01709201159: GOTO optical follow-up.",
    )

    annotations = EventIdentityExtractor().extract(doc)

    assert len(annotations) == 1
    assert annotations[0].text == "EP/WXT01709201159"
    assert annotations[0].value == "EP-WXT 01709201159"
    assert annotations[0].rule_id == "event_identity.ep_wxt_trigger"
    assert annotations[0].needs_review is True
    assert annotations[0].verify(doc.rendered_text)


def test_event_identity_ep_dayfraction_requires_review() -> None:
    doc = render_canonical(
        circular_id=13,
        subject="EP report",
        body="EP 260225.148: COLIBRI Confirmation of flaring star.",
    )

    annotations = EventIdentityExtractor().extract(doc)

    assert len(annotations) == 1
    assert annotations[0].text == "EP 260225.148"
    assert annotations[0].value == "EP 260225.148"
    assert annotations[0].rule_id == "event_identity.ep_dayfraction"
    assert annotations[0].needs_review is True
    assert annotations[0].comment == "Formato de fracción de día de EP; verificar mapeo al evento canónico."
    assert annotations[0].verify(doc.rendered_text)


def test_event_identity_epw_transient_uses_ep_wxt_rule_without_truncation() -> None:
    doc = render_canonical(
        circular_id=14,
        subject="EP transient report",
        body="Transient EPW20240219aa: GECKO optical upper limits.",
    )

    annotations = EventIdentityExtractor().extract(doc)

    assert len(annotations) == 1
    assert annotations[0].text == "EPW20240219aa"
    assert annotations[0].value == "EP-WXT 20240219aa"
    assert annotations[0].rule_id == "event_identity.ep_wxt_trigger"
    assert annotations[0].needs_review is True
    assert "EP 202402" not in {annotation.value for annotation in annotations}
    assert annotations[0].verify(doc.rendered_text)


@pytest.mark.parametrize(
    ("subject", "expected_value", "expected_rule_id"),
    [
        ("AT2023bic", "AT 2023bic", "event_identity.at_sn"),
        ("ZTF23aaarlti", "ZTF23aaarlti", "event_identity.ztf"),
        ("GRB230101A", "GRB 230101A", "event_identity.grb"),
        ("EP240315a", "EP 240315a", "event_identity.ep"),
    ],
)
def test_event_identity_normalizes_value_by_family(
    subject: str,
    expected_value: str,
    expected_rule_id: str,
) -> None:
    doc = render_canonical(
        circular_id=10,
        subject=subject,
        body="This circular reports an event identity.",
    )

    annotations = EventIdentityExtractor().extract(doc)

    assert len(annotations) == 1
    assert annotations[0].text == subject
    assert annotations[0].value == expected_value
    assert annotations[0].rule_id == expected_rule_id
    assert annotations[0].verify(doc.rendered_text)


def test_event_identity_suppresses_at_sn_inside_candidate_table_row() -> None:
    doc = render_canonical(
        circular_id=15,
        subject="Candidate table",
        body="| SN_LIKE | 2290036 | AT2025gek | 145.199481 | 10.828527 | 20.77 | 0.04 |",
    )

    assert EventIdentityExtractor().extract(doc) == []


def test_event_identity_suppresses_at_and_ztf_inside_photometry_table_row() -> None:
    doc = render_canonical(
        circular_id=16,
        subject="Photometry table",
        body="| ZTF23abnoapt | AT2023wue | 102.9 | +48.07 | g | 17.98 |",
    )

    assert EventIdentityExtractor().extract(doc) == []


def test_event_identity_keeps_legitimate_at_alias_in_prose() -> None:
    doc = render_canonical(
        circular_id=17,
        subject="Optical afterglow confirmation",
        body="We report confirming AT 2023qxj as the optical afterglow of GRB 230827B.",
    )

    annotations = EventIdentityExtractor().extract(doc)
    values = {annotation.value for annotation in annotations}

    assert values == {"AT 2023qxj", "GRB 230827B"}
    assert all(annotation.verify(doc.rendered_text) for annotation in annotations)


def test_event_identity_keeps_sn_comparison_in_prose() -> None:
    doc = render_canonical(
        circular_id=18,
        subject="Spectroscopic comparison",
        body="The spectrum is a good match to the spectrum of GRB-SN 2006aj.",
    )

    annotations = EventIdentityExtractor().extract(doc)

    assert [annotation.value for annotation in annotations] == ["SN 2006aj"]
    assert annotations[0].text == "SN 2006aj"
    assert annotations[0].verify(doc.rendered_text)


def test_event_identity_does_not_apply_table_filter_to_grb() -> None:
    doc = render_canonical(
        circular_id=19,
        subject="Numeric GRB line",
        body="| trigger | 145.199481 | 10.828527 | 20.77 | GRB 230827B |",
    )

    annotations = EventIdentityExtractor().extract(doc)

    assert [annotation.value for annotation in annotations] == ["GRB 230827B"]
    assert annotations[0].verify(doc.rendered_text)


def test_event_identity_negative_without_names() -> None:
    doc = render_canonical(
        circular_id=2,
        subject="Optical follow-up report",
        body="No recognized event identity appears in this synthetic circular.",
    )

    assert EventIdentityExtractor().extract(doc) == []


def test_event_identity_does_not_match_gcn_reference_number() -> None:
    doc = render_canonical(
        circular_id=3,
        subject="Follow-up report",
        body="The result was already reported in GCN 12345 and GCN Circular 12346.",
    )

    assert EventIdentityExtractor().extract(doc) == []


def test_event_evidence_target_tagset_rejects_other_event() -> None:
    with pytest.raises(ValueError, match="other_event"):
        EventEvidenceAnnotation(
            circular_id=4,
            text_sha256="abc",
            span_start=0,
            span_end=4,
            text="test",
            label="EVENT_IDENTITY",
            target="other_event",
            certainty="confirmed",
            extractor_id="test",
            extractor_version="0.1",
            method="unit",
        )


def test_event_evidence_certainty_tagset() -> None:
    with pytest.raises(ValueError, match="foo"):
        EventEvidenceAnnotation(
            circular_id=5,
            text_sha256="abc",
            span_start=0,
            span_end=4,
            text="test",
            label="EVENT_IDENTITY",
            target="event",
            certainty="foo",
            extractor_id="test",
            extractor_version="0.1",
            method="unit",
        )

    annotation = EventEvidenceAnnotation(
        circular_id=6,
        text_sha256="abc",
        span_start=0,
        span_end=4,
        text="test",
        label="EVENT_IDENTITY",
        target="event",
        certainty="candidate",
        extractor_id="test",
        extractor_version="0.1",
        method="unit",
    )

    assert annotation.certainty == "candidate"
