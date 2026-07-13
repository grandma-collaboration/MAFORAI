from __future__ import annotations

import pytest

from skyportal_corpus.canonical.document import render_canonical
from skyportal_corpus.extraction_v2.photometry_prose import (
    ProsePhotometryExtractor,
    is_optical_circular,
)


def _extract(body: str):
    doc = render_canonical(circular_id=1, subject="Optical follow-up", body=body)
    annotations = ProsePhotometryExtractor().extract(doc)
    assert all(annotation.verify(doc.rendered_text) for annotation in annotations)
    return doc, annotations


def test_brightness_detection_from_38780() -> None:
    _doc, annotations = _extract(
        "The optical afterglow is clearly detected in our stacked image with the "
        "brightness of R = 21.86 +/- 0.06, calibrated against nearby PS1 stars."
    )

    assert len(annotations) == 1
    annotation = annotations[0]
    assert annotation.measurement_type == "detection"
    assert annotation.magnitude_or_limit == "21.86"
    assert annotation.magnitude_error == "0.06"
    assert annotation.photometric_band == "R"


def test_preliminary_isolated_detection_from_39777() -> None:
    _doc, annotations = _extract(
        "The preliminary magnitude derived for the source is :\n\n"
        "r = 23.5 +/- 0.4 mag (AB)"
    )

    assert len(annotations) == 1
    annotation = annotations[0]
    assert annotation.measurement_type == "detection"
    assert annotation.magnitude_or_limit == "23.5"
    assert annotation.magnitude_error == "0.4"
    assert annotation.photometric_band == "r"
    assert annotation.photometric_system == "AB"
    assert annotation.certainty == "tentative"


def test_limiting_ab_magnitude_from_42115() -> None:
    _doc, annotations = _extract(
        "Optical imaging reaches to a 3-sigma limiting AB magnitude of L > 19.65 mag."
    )

    assert len(annotations) == 1
    annotation = annotations[0]
    assert annotation.measurement_type == "upper_limit"
    assert annotation.magnitude_or_limit == "19.65"
    assert annotation.photometric_band == "L"
    assert annotation.photometric_system == "AB"
    assert annotation.limit_sigma == "3"


def test_limit_sigma_can_come_from_preceding_sentence_clause() -> None:
    _doc, annotations = _extract(
        "Optical observations were obtained on 2025-03-18T21:33:00 UT down to "
        "the following 3-sigma limit:\n\nr > 22.3 mag (AB)"
    )

    assert len(annotations) == 1
    annotation = annotations[0]
    assert annotation.measurement_type == "upper_limit"
    assert annotation.magnitude_or_limit == "22.3"
    assert annotation.limit_sigma == "3"
    assert annotation.photometric_system == "AB"


def test_sigma_depth_limit_is_measurement_but_average_search_depth_is_not() -> None:
    _doc, limit_annotations = _extract(
        "We find no evidence of the optical source on 2025-03-18T21:33:00 UT, "
        "down to a 5-sigma depth of >20.8 AB mag."
    )
    _doc, average_annotations = _extract(
        "Optical observations used 141 images taken with an average 5-sigma "
        "depth of 20.2 mag."
    )

    assert len(limit_annotations) == 1
    assert limit_annotations[0].measurement_type == "upper_limit"
    assert limit_annotations[0].magnitude_or_limit == "20.8"
    assert limit_annotations[0].limit_sigma == "5"
    assert limit_annotations[0].photometric_system == "AB"
    assert average_annotations == []


def test_up_to_limit_from_36988() -> None:
    _doc, annotations = _extract(
        "We have not detected any clearly visible optical sources, up to 19.5th magnitude."
    )

    assert len(annotations) == 1
    assert annotations[0].measurement_type == "upper_limit"
    assert annotations[0].magnitude_or_limit == "19.5"


def test_catalog_completeness_is_not_a_measurement() -> None:
    _doc, annotations = _extract(
        "Optical catalog inspection was performed. The list of sources is typically "
        "complete to about 18 mag."
    )
    assert annotations == []


def test_calibration_statement_is_not_a_measurement() -> None:
    _doc, annotations = _extract(
        "Optical photometry was calibrated. Magnitudes were estimated with the Gaia DR2 cat."
    )
    assert annotations == []


def test_non_optical_xrt_and_gecam_prefilter() -> None:
    xrt = "Swift-XRT reports a Count-rate: 0.0107 ct s^-1 in the 0.3-10 keV range."
    gecam = "GECAM reports a T90 of 38 s and fluence of 2e-6 erg/cm^2."

    assert not is_optical_circular(xrt)
    assert not is_optical_circular(gecam)
    assert ProsePhotometryExtractor().extract(
        render_canonical(circular_id=2, subject="Swift-XRT analysis", body=xrt)
    ) == []
    assert ProsePhotometryExtractor().extract(
        render_canonical(circular_id=3, subject="GECAM analysis", body=gecam)
    ) == []


def test_companion_fields_can_be_distributed_across_paragraphs() -> None:
    _doc, annotations = _extract(
        "Optical observations in the Rc band started at 21:33 UT on 2025-03-18.\n"
        "We obtained 4x90s exposures with GOTO.\n\n"
        "The images were reduced using standard procedures.\n\n"
        "The optical transient was detected with a magnitude of 19.2 +/- 0.1 in Rc (AB)."
    )

    assert len(annotations) == 1
    annotation = annotations[0]
    assert annotation.obs_time_raw == "started at 21:33 UT on 2025-03-18"
    assert annotation.obs_time_type == "utc_datetime"
    assert annotation.obs_time_reference == "absolute_time"
    assert annotation.exposure_time_raw == "4x90s exposures"
    assert annotation.photometric_band == "Rc"
    assert annotation.photometric_system == "AB"
    assert annotation.target == "counterpart"
    assert annotation.verify(_doc.rendered_text)


def test_citation_is_kept_but_marked_for_review() -> None:
    _doc, annotations = _extract(
        "Optical follow-up notes the upper limit of 21 mag reported by Lipunov et al., GCN 12345."
    )
    assert len(annotations) == 1
    assert annotations[0].needs_review
    assert "cited from another GCN" in (annotations[0].comment or "")


def test_coordinate_and_redshift_expressions_are_not_magnitudes() -> None:
    _doc, annotations = _extract(
        "Optical follow-up of the trigger at 13h 46m, +42d 46m, R=5.62) errorbox. "
        "The galactic latitude b = 71 deg., longitude l = 90 deg. A nearby galaxy "
        "at z=0.065 may be associated with the event."
    )
    assert annotations == []


def test_citation_of_coordinate_does_not_mark_magnitude_ownership() -> None:
    _doc, annotations = _extract(
        "At 454 seconds after the burst, the optical transient had Ic=17.1+/-0.2 "
        "at the coordinate reported by Agui Fernandez et al. GCN 34251. The "
        "magnitude is in the AB system."
    )
    assert len(annotations) == 1
    assert "cited from another GCN" not in (annotations[0].comment or "")


@pytest.mark.parametrize(
    "expression",
    (
        "z = 0.0658",
        "z = 1.763",
        "z = 2.36",
        "z < 3",
        "z = 0.18 +/- 0.01",
        "z=0.374",
        "z < 2.06",
    ),
)
def test_redshift_expressions_are_not_z_band_magnitudes(expression: str) -> None:
    _doc, annotations = _extract(
        f"Optical spectroscopy of the host galaxy gives a redshift {expression}."
    )
    assert annotations == []


@pytest.mark.parametrize(
    ("expression", "measurement_type", "magnitude"),
    (
        ("z > 22.5 mag", "upper_limit", "22.5"),
        ("z = 21.3 mag", "detection", "21.3"),
    ),
)
def test_explicit_z_band_magnitudes_remain_valid(
    expression: str,
    measurement_type: str,
    magnitude: str,
) -> None:
    _doc, annotations = _extract(
        f"Optical imaging on 2025-03-18T21:33:00 UT measured {expression} (AB)."
    )
    assert len(annotations) == 1
    assert annotations[0].measurement_type == measurement_type
    assert annotations[0].magnitude_or_limit == magnitude
    assert annotations[0].photometric_band == "z"


@pytest.mark.parametrize(
    "expression",
    ("r > 0.3 mag", "r = 0.97 +/- 0.05", "r < 1"),
)
def test_color_like_values_below_magnitude_range_are_discarded(expression: str) -> None:
    _doc, annotations = _extract(f"Optical color analysis reports {expression}.")
    assert annotations == []


def test_valid_r_band_magnitude_remains_detected() -> None:
    _doc, annotations = _extract(
        "Optical imaging on 2025-03-18T21:33:00 UT gives r = 21.86 +/- 0.06 mag (AB)."
    )
    assert len(annotations) == 1
    assert annotations[0].magnitude_or_limit == "21.86"


def test_observation_time_wins_over_trigger_time_without_false_ambiguity() -> None:
    _doc, annotations = _extract(
        "At 02:16:38 UT, the burst triggered the high-energy monitor.\n\n"
        "We observed the optical field on January 2, 15:20:13--18:06:55 UT "
        "(t_mid - T0 = 1.1394 days).\n\n"
        "The optical afterglow was detected with the brightness of "
        "R = 21.86 +/- 0.06 mag (AB)."
    )

    assert len(annotations) == 1
    annotation = annotations[0]
    assert annotation.obs_time_raw == "on January 2, 15:20:13--18:06:55 UT"
    assert annotation.obs_time_type == "utc_datetime"
    assert "Multiple observation times" not in (annotation.comment or "")
    assert not annotation.needs_review


def test_goto_measurement_is_not_marked_as_cited_by_unrelated_gcn_text() -> None:
    _doc, annotations = _extract(
        "A previous localization was discussed in GCN 41000. A GOTO frame obtained "
        "4.36 min before the trigger shows no source to a 3-sigma limit of "
        "L >18.8 mag (AB)."
    )

    assert len(annotations) == 1
    annotation = annotations[0]
    assert annotation.magnitude_or_limit == "18.8"
    assert annotation.instrument == "GOTO"
    assert "cited from another GCN" not in (annotation.comment or "")


def test_instrument_matching_distinguishes_not_telescope_from_lowercase_word() -> None:
    _doc, lowercase_annotations = _extract(
        "The optical source was not detected on 2025-03-18T21:33:00 UT to "
        "R > 20.1 mag (AB)."
    )
    _doc, telescope_annotations = _extract(
        "The NOT observed on 2025-03-18T21:33:00 UT and measured "
        "R = 20.1 +/- 0.1 mag (AB)."
    )

    assert lowercase_annotations[0].instrument is None
    assert telescope_annotations[0].instrument == "NOT"


def test_ddoti_w_band_detection_with_system_in_preceding_phrase() -> None:
    _doc, annotations = _extract(
        "We detect the candidate optical afterglow with a preliminary AB magnitude of:\n\n"
        "w = 18.82 +/- 0.04"
    )

    assert len(annotations) == 1
    annotation = annotations[0]
    assert annotation.measurement_type == "detection"
    assert annotation.magnitude_or_limit == "18.82"
    assert annotation.magnitude_error == "0.04"
    assert annotation.photometric_band == "w"
    assert annotation.photometric_system == "AB"
    assert annotation.certainty == "tentative"


def test_atlas_enumerated_limits_and_detections_are_all_captured() -> None:
    _doc, annotations = _extract(
        "ATLAS observed the optical transient four times with the wide w-band filter. "
        "The first and second exposures returned 5-sigma upper limits of >20.20 and "
        ">20.35 AB mag, respectively. The third and fourth exposures detected the "
        "transient, with magnitudes of w = 16.26+/-0.02 and w = 16.29+/-0.02 AB mag, "
        "respectively."
    )

    assert len(annotations) == 4
    assert [annotation.measurement_type for annotation in annotations] == [
        "upper_limit",
        "upper_limit",
        "detection",
        "detection",
    ]
    assert [annotation.magnitude_or_limit for annotation in annotations] == [
        "20.20",
        "20.35",
        "16.26",
        "16.29",
    ]
    assert [annotation.magnitude_error for annotation in annotations] == [None, None, "0.02", "0.02"]
    assert [annotation.limit_sigma for annotation in annotations] == ["5", "5", None, None]
    assert all(annotation.photometric_band == "w" for annotation in annotations)
    assert all(annotation.photometric_system == "AB" for annotation in annotations)
