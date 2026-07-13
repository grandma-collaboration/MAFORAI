from __future__ import annotations

import pytest

from skyportal_corpus.extraction_v2.photometry_annotations import (
    PhotometricMeasurementAnnotation,
)


def _annotation_for_span(rendered_text: str, snippet: str, **overrides: object) -> PhotometricMeasurementAnnotation:
    start = rendered_text.index(snippet)
    data = {
        "circular_id": 1,
        "text_sha256": "sha",
        "span_start": start,
        "span_end": start + len(snippet),
        "text": snippet,
        "measurement_type": "detection",
        "target": "counterpart",
        "certainty": "confirmed",
        "magnitude_or_limit": "19.29",
        "unit": "mag",
        "photometric_band": "R",
        "photometric_system": "Vega",
        "obs_time_raw": "2024-10-25T04:04:36",
        "obs_time_type": "utc_datetime",
        "obs_time_reference": "absolute_time",
        "exposure_time_raw": "300 s",
        "instrument": "GOTO",
        "comment": None,
        "provenance_inherited": ["system", "sigma"],
        "extractor_id": "photometry-test",
        "extractor_version": "0.1",
        "method": "synthetic",
        "rule_id": "test.photometry",
    }
    data.update(overrides)
    return PhotometricMeasurementAnnotation(**data)


def test_valid_detection_annotation() -> None:
    text = "The source was detected at R = 19.29 mag."
    annotation = _annotation_for_span(text, "R = 19.29 mag")

    assert annotation.measurement_type == "detection"
    assert annotation.magnitude_or_limit == "19.29"
    assert annotation.unit == "mag"
    assert annotation.photometric_band == "R"
    assert annotation.photometric_system == "Vega"
    assert annotation.obs_time_type == "utc_datetime"
    assert annotation.obs_time_reference == "absolute_time"
    assert annotation.verify(text)


def test_valid_upper_limit_annotation() -> None:
    text = "No source is detected down to >18.5 mag."
    annotation = _annotation_for_span(
        text,
        ">18.5 mag",
        measurement_type="upper_limit",
        magnitude_or_limit="18.5",
        limit_sigma="5",
        photometric_band=None,
        photometric_system="AB",
    )

    assert annotation.measurement_type == "upper_limit"
    assert annotation.magnitude_or_limit == "18.5"
    assert annotation.limit_sigma == "5"
    assert annotation.verify(text)


def test_detection_cannot_carry_limit_sigma() -> None:
    text = "The source was detected at R = 19.29 mag."

    with pytest.raises(ValueError, match="limit_sigma"):
        _annotation_for_span(text, "R = 19.29 mag", limit_sigma="3")


def test_invalid_measurement_type_raises() -> None:
    text = "The source was detected at R = 19.29 mag."

    with pytest.raises(ValueError, match="measurement_type"):
        _annotation_for_span(text, "R = 19.29 mag", measurement_type="foo")


def test_verify_true_and_false_for_span_text() -> None:
    text = "The source was detected at R = 19.29 mag."
    annotation = _annotation_for_span(text, "R = 19.29 mag")

    assert annotation.verify(text)
    assert not annotation.verify(text.replace("19.29", "19.30"))


def test_construction_is_deterministic() -> None:
    text = "The source was detected at R = 19.29 mag."

    first = _annotation_for_span(text, "R = 19.29 mag")
    second = _annotation_for_span(text, "R = 19.29 mag")

    assert first == second
    assert first.model_dump() == second.model_dump()
