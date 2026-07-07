from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from skyportal_corpus.canonical.document import render_canonical  # noqa: E402
from skyportal_corpus.extraction_v2.redshift import RedshiftExtractor  # noqa: E402


def _extract(body: str):
    doc = render_canonical(circular_id=1, subject="Redshift test", body=body)
    annotations = RedshiftExtractor().extract(doc)
    for annotation in annotations:
        assert annotation.verify(doc.rendered_text)
        assert annotation.text == doc.rendered_text[annotation.span_start : annotation.span_end]
    return doc, annotations


def test_redshift_event_afterglow_targets_counterpart() -> None:
    _, annotations = _extract(
        "implying a redshift of z=0.887, and thus confirming AT "
        "2023qxj as the optical afterglow of GRB 230827B"
    )

    assert len(annotations) == 1
    annotation = annotations[0]
    assert annotation.label == "REDSHIFT_EVENT"
    assert annotation.target == "counterpart"
    assert annotation.value == "0.887"
    assert annotation.needs_review is False
    assert annotation.certainty == "confirmed"


def test_redshift_event_host_targets_host() -> None:
    _, annotations = _extract("The host galaxy is at z=0.474.")

    assert len(annotations) == 1
    assert annotations[0].label == "REDSHIFT_EVENT"
    assert annotations[0].target == "host"
    assert annotations[0].value == "0.474"


def test_redshift_context_nearby_galaxies() -> None:
    _, annotations = _extract("There are nearby z ~ 0.1 galaxies in the field.")

    assert len(annotations) == 1
    assert annotations[0].label == "REDSHIFT_CONTEXT"
    assert annotations[0].target == "nearby_galaxy"
    assert annotations[0].needs_review is True
    assert annotations[0].comment == "Clasificado como redshift de contexto/intervening; verificar que no sea el redshift del evento."


def test_redshift_context_foreground_intervening() -> None:
    _, annotations = _extract("We identify an intervening/foreground galaxy at z=0.5.")

    assert len(annotations) == 1
    assert annotations[0].label == "REDSHIFT_CONTEXT"
    assert annotations[0].target == "nearby_galaxy"
    assert annotations[0].value == "0.5"
    assert annotations[0].needs_review is True


def test_redshift_ambiguous_defaults_to_event_with_review() -> None:
    _, annotations = _extract("We measure z = 1.2.")

    assert len(annotations) == 1
    assert annotations[0].label == "REDSHIFT_EVENT"
    assert annotations[0].target == "event"
    assert annotations[0].needs_review is True
    assert annotations[0].comment


def test_redshift_does_not_capture_z_band_magnitudes_or_filters() -> None:
    for body in [
        "The photometry gives z = 21.3 mag.",
        "We observed in the g, r, i, z bands.",
        "The z-band limit of 22.0 mag is reported.",
    ]:
        _, annotations = _extract(body)
        assert annotations == []


def test_redshift_range_preserves_range_value() -> None:
    _, annotations = _extract("The source is consistent with 0.1 < z < 0.3.")

    assert len(annotations) == 1
    assert annotations[0].value == "0.1-0.3"
    assert annotations[0].rule_id == "redshift.z_range"


def test_redshift_tentative_certainty() -> None:
    _, annotations = _extract("We find a possible redshift of z~0.9.")

    assert len(annotations) == 1
    assert annotations[0].certainty == "tentative"


def test_redshift_rejected_context_not_event() -> None:
    _, annotations = _extract(
        "This is not the redshift of the GRB, but a foreground system at z=0.2."
    )

    assert len(annotations) == 1
    assert annotations[0].label == "REDSHIFT_CONTEXT"
    assert annotations[0].target == "nearby_galaxy"
    assert annotations[0].certainty == "rejected"
    assert annotations[0].needs_review is True


def test_redshift_does_not_emit_spurious_table_row_values() -> None:
    _, annotations = _extract(
        "| src | AT2025x | 0.887 | 20.1 |\n"
        "| src | z = 0.887 | 20.1 |"
    )

    assert annotations == []


def test_redshift_event_anchor_after_number_removes_review() -> None:
    _, annotations = _extract(
        "We infer a common redshift of z = 4.01 from the absorption system. "
        "We conclude this is the redshift of the burst."
    )

    assert len(annotations) == 1
    assert annotations[0].label == "REDSHIFT_EVENT"
    assert annotations[0].target == "event"
    assert annotations[0].needs_review is False


def test_redshift_event_anchor_for_this_event_removes_review() -> None:
    _, annotations = _extract("The measured z = 2.28 is likely the redshift for this event.")

    assert len(annotations) == 1
    assert annotations[0].label == "REDSHIFT_EVENT"
    assert annotations[0].needs_review is False


def test_redshift_event_anchor_for_this_event_with_extra_words_removes_review() -> None:
    _, annotations = _extract("We therefore conclude that z = 2.28 is likely the redshift for this event.")

    assert len(annotations) == 1
    assert annotations[0].label == "REDSHIFT_EVENT"
    assert annotations[0].needs_review is False


def test_redshift_at_the_redshift_of_z_removes_review() -> None:
    _, annotations = _extract("The transient is indeed at the redshift of z = 0.153, confirming the association.")

    assert len(annotations) == 1
    assert annotations[0].label == "REDSHIFT_EVENT"
    assert annotations[0].needs_review is False


def test_redshift_same_value_in_document_inherits_explicit_event_attribution() -> None:
    _, annotations = _extract(
        "We identify several lines at a redshift of z=2.28. "
        "We therefore conclude that z = 2.28 is likely the redshift for this event."
    )

    assert len(annotations) == 2
    assert {annotation.value for annotation in annotations} == {"2.28"}
    assert all(annotation.label == "REDSHIFT_EVENT" for annotation in annotations)
    assert all(annotation.needs_review is False for annotation in annotations)


def test_redshift_host_environment_targets_host_without_review() -> None:
    _, annotations = _extract("The host environment at z=2.006 detected by the GTC shows strong absorption.")

    assert len(annotations) == 1
    assert annotations[0].label == "REDSHIFT_EVENT"
    assert annotations[0].target == "host"
    assert annotations[0].needs_review is False


def test_redshift_host_environment_in_same_sentence_removes_review_for_consistent_redshift() -> None:
    _, annotations = _extract(
        "The host environment at z=2.006 detected by the GTC is visible in our data, "
        "with FeII lines observed at a consistent redshift of z=2.007."
    )

    assert len(annotations) == 2
    assert all(annotation.label == "REDSHIFT_EVENT" for annotation in annotations)
    assert all(annotation.needs_review is False for annotation in annotations)


def test_redshift_event_name_lies_at_this_redshift_removes_review() -> None:
    _, annotations = _extract(
        "The spectra imply a common redshift z = 1.535 from several lines. "
        "EP260302a likely lies at this redshift."
    )

    assert len(annotations) == 1
    assert annotations[0].label == "REDSHIFT_EVENT"
    assert annotations[0].needs_review is False


def test_redshift_gcn_citation_is_event_without_review() -> None:
    _, annotations = _extract("Assuming the redshift z=2.42 (Malesani et al., GCN 34485), we derive Eiso.")

    assert len(annotations) == 1
    assert annotations[0].label == "REDSHIFT_EVENT"
    assert annotations[0].certainty == "confirmed"
    assert annotations[0].needs_review is False
    assert annotations[0].comment
    assert "GCN" in annotations[0].comment


def test_redshift_galaxy_range_is_context() -> None:
    _, annotations = _extract("The skymap was matched with galaxies in the range 0.10 < z < 0.17.")

    assert len(annotations) == 1
    assert annotations[0].label == "REDSHIFT_CONTEXT"
    assert annotations[0].target == "nearby_galaxy"
    assert annotations[0].needs_review is True


def test_redshift_absolute_magnitude_reference_is_context() -> None:
    _, annotations = _extract("The non-detection corresponds to M_z > -12 at redshift z = 0.018.")

    assert len(annotations) == 1
    assert annotations[0].label == "REDSHIFT_CONTEXT"
    assert annotations[0].target == "nearby_galaxy"
    assert annotations[0].needs_review is True


def test_redshift_candidate_host_stays_event_review_tentative() -> None:
    _, annotations = _extract(
        "The galaxy SDSS J09 is at z = 0.0343. "
        "If EP260321 is associated with this galaxy, the luminosity is low."
    )

    assert len(annotations) == 1
    assert annotations[0].label == "REDSHIFT_EVENT"
    assert annotations[0].needs_review is True
    assert annotations[0].certainty == "tentative"


def test_redshift_photometric_catalogued_galaxy_candidate_afterglow_stays_review() -> None:
    _, annotations = _extract(
        "The transient is spatially coincident with the catalogued galaxy PSO J162 "
        "with a photometric redshift of 0.63 +/- 0.19 in the PS1-STRM catalogue. "
        "Due to the galaxy association, rapid decay, and lack of detection in archival "
        "pre-event imaging, we propose this source as the optical afterglow."
    )

    assert len(annotations) == 1
    assert annotations[0].label == "REDSHIFT_EVENT"
    assert annotations[0].needs_review is True


def test_redshift_candidate_afterglow_photometric_redshift_stays_review() -> None:
    _, annotations = _extract(
        "This source is consistent with a faint extended object visible in the Legacy Survey "
        "with a reported photometric redshift 1.12 +/- 0.18, and photometry suggests "
        "it has brightened. We consider this a candidate afterglow for GRB 250225B."
    )

    assert len(annotations) == 1
    assert annotations[0].label == "REDSHIFT_EVENT"
    assert annotations[0].needs_review is True


def test_redshift_event_anchor_wins_over_intervening_elsewhere() -> None:
    _, annotations = _extract(
        "From absorption lines we infer a common redshift of z = 5.178. "
        "We conclude this is the redshift of the burst. "
        "Additional intervening systems are visible at lower redshift."
    )

    assert len(annotations) == 1
    assert annotations[0].label == "REDSHIFT_EVENT"
    assert annotations[0].target == "event"
    assert annotations[0].value == "5.178"
    assert annotations[0].needs_review is False


def test_redshift_grb_event_and_local_intervening_system() -> None:
    _, annotations = _extract(
        "We infer a common redshift of 2.006 from the host environment, "
        "which we suggest to be the redshift of GRB 260511B. "
        "Multiple intervening systems are also detected, including a strong system at z = 1.437."
    )

    by_value = {annotation.value: annotation for annotation in annotations}
    assert set(by_value) == {"2.006", "1.437"}
    assert by_value["2.006"].label == "REDSHIFT_EVENT"
    assert by_value["2.006"].needs_review is False
    assert by_value["1.437"].label == "REDSHIFT_CONTEXT"
    assert by_value["1.437"].needs_review is True


def test_redshift_event_measurement_and_intervening_redshift() -> None:
    _, annotations = _extract(
        "We identify absorption lines C IV and Si II at a common redshift of z = 2.42. "
        "We confirm the redshift measurement of the GRB. "
        "We also identified Si IV and Al II lines at a common redshift of 2.38 "
        "which might be an intervening system."
    )

    by_value = {annotation.value: annotation for annotation in annotations}
    assert set(by_value) == {"2.42", "2.38"}
    assert by_value["2.42"].label == "REDSHIFT_EVENT"
    assert by_value["2.42"].needs_review is False
    assert by_value["2.38"].label == "REDSHIFT_CONTEXT"
    assert by_value["2.38"].needs_review is True


def test_redshift_burst_and_multiple_intervening_systems() -> None:
    _, annotations = _extract(
        "From several lines we infer a common redshift of z = 2.674. "
        "We conclude this is the redshift of the burst. "
        "We also detect intervening systems at z = 2.000 and z = 1.824."
    )

    by_value = {annotation.value: annotation for annotation in annotations}
    assert set(by_value) == {"2.674", "2.000", "1.824"}
    assert by_value["2.674"].label == "REDSHIFT_EVENT"
    assert by_value["2.674"].needs_review is False
    for value in ("2.000", "1.824"):
        assert by_value[value].label == "REDSHIFT_CONTEXT"
        assert by_value[value].needs_review is True


def test_redshift_legitimate_context_galaxy_requires_review() -> None:
    _, annotations = _extract("The nearest object is a galaxy at z = 0.524.")

    assert len(annotations) == 1
    assert annotations[0].label == "REDSHIFT_CONTEXT"
    assert annotations[0].target == "nearby_galaxy"
    assert annotations[0].needs_review is True


def test_redshift_unrelated_galaxy_context_requires_review() -> None:
    _, annotations = _extract("A galaxy at redshift of z=0.416 is likely unrelated to the GRB.")

    assert len(annotations) == 1
    assert annotations[0].label == "REDSHIFT_CONTEXT"
    assert annotations[0].needs_review is True
