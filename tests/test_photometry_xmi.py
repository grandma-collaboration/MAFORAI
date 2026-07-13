from __future__ import annotations

from pathlib import Path

from cassis import TypeSystem, load_cas_from_xmi, load_typesystem

from skyportal_corpus.canonical.document import render_canonical
from skyportal_corpus.extraction_v2.photometry_annotations import (
    PhotometricMeasurementAnnotation,
)
from skyportal_corpus.extraction_v2.photometry_tagsets import (
    CERTAINTIES,
    MEASUREMENT_TYPES,
    OBS_TIME_REFERENCES,
    OBS_TIME_TYPES,
    PHOTOMETRIC_SYSTEMS,
    TARGETS,
)
from skyportal_corpus.inception_v2.photometry_xmi_export import (
    PHOTOMETRY_FEATURES,
    PHOTOMETRY_TAGSET_DEFAULTS,
    PHOTOMETRY_TYPE,
    export_photometry_xmi,
    photometry_feature_values,
    photometry_roundtrip_check,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TYPESYSTEM_PATH = PROJECT_ROOT / "data" / "inception" / "TypeSystem.xml"


def _fixture_measurements():
    doc = render_canonical(
        circular_id=90001,
        subject="Synthetic photometry",
        created_on="2026-07-13T00:00:00+00:00",
        body="15.5 | 60237.097 | KAO | i | 20.5 +/- 0.1 (AB) | 22.0",
    )
    row_text = "15.5 | 60237.097 | KAO | i | 20.5 +/- 0.1 (AB) | 22.0"
    start = doc.rendered_text.index(row_text)
    common = {
        "circular_id": doc.circular_id,
        "text_sha256": doc.text_sha256,
        "span_start": start,
        "span_end": start + len(row_text),
        "text": row_text,
        "target": "counterpart",
        "certainty": "confirmed",
        "unit": "mag",
        "photometric_band": "i",
        "photometric_system": "AB",
        "obs_time_raw": "60237.097",
        "obs_time_type": "mjd",
        "obs_time_reference": "absolute_time",
        "exposure_time_raw": None,
        "instrument": "KAO",
        "extractor_id": "test-photometry",
        "extractor_version": "0.1",
        "method": "manual",
    }
    measurements = [
        PhotometricMeasurementAnnotation(
            **common,
            measurement_type="detection",
            magnitude_or_limit="20.5",
            magnitude_error="0.1",
            limit_sigma=None,
            comment="This must not be exported because review is false.",
            rule_id="test.detection",
            needs_review=False,
        ),
        PhotometricMeasurementAnnotation(
            **common,
            measurement_type="upper_limit",
            magnitude_or_limit="22.0",
            magnitude_error=None,
            limit_sigma="5",
            comment="Verify whether the limit is independent of the detection.",
            rule_id="test.limit",
            needs_review=True,
        ),
    ]
    return doc, measurements


def test_export_and_roundtrip_preserve_text_duplicate_spans_and_features(tmp_path: Path) -> None:
    doc, measurements = _fixture_measurements()
    out_path = tmp_path / "photometry.xmi"

    export_photometry_xmi(doc, measurements, TYPESYSTEM_PATH, out_path)
    result = photometry_roundtrip_check(
        out_path,
        doc.rendered_text,
        measurements,
        TYPESYSTEM_PATH,
    )

    assert result == {
        "text_matches": True,
        "n_original": 2,
        "n_roundtripped": 2,
        "all_spans_ok": True,
        "all_features_ok": True,
        "discrepancies": [],
    }


def test_comment_semantics_and_free_text_none_values_export_as_empty_strings(
    tmp_path: Path,
) -> None:
    doc, measurements = _fixture_measurements()
    out_path = tmp_path / "comments.xmi"
    export_photometry_xmi(doc, measurements, TYPESYSTEM_PATH, out_path)

    with TYPESYSTEM_PATH.open("rb") as handle:
        typesystem = load_typesystem(handle)
    with out_path.open("rb") as handle:
        cas = load_cas_from_xmi(handle, typesystem=typesystem)
    recovered = sorted(cas.select(PHOTOMETRY_TYPE), key=lambda item: item.measurement_type)

    detection, upper_limit = recovered
    assert detection.measurement_type == "detection"
    assert str(detection.comment or "") == ""
    assert str(detection.exposure_time_raw or "") == ""
    assert str(detection.timezone_raw or "") == ""
    assert upper_limit.measurement_type == "upper_limit"
    assert upper_limit.comment == "Verify whether the limit is independent of the detection."
    assert str(upper_limit.magnitude_error or "") == ""


def test_missing_tagset_values_use_valid_defaults_but_free_text_stays_empty(
    tmp_path: Path,
) -> None:
    doc, measurements = _fixture_measurements()
    missing_values = measurements[0].model_copy(
        update={
            "measurement_type": None,
            "target": None,
            "certainty": None,
            "photometric_system": None,
            "obs_time_raw": None,
            "obs_time_type": None,
            "obs_time_reference": None,
        }
    )
    out_path = tmp_path / "missing-tagset-values.xmi"

    export_photometry_xmi(doc, [missing_values], TYPESYSTEM_PATH, out_path)

    with TYPESYSTEM_PATH.open("rb") as handle:
        typesystem = load_typesystem(handle)
    with out_path.open("rb") as handle:
        cas = load_cas_from_xmi(handle, typesystem=typesystem)
    recovered = list(cas.select(PHOTOMETRY_TYPE))

    assert len(recovered) == 1
    assert recovered[0].measurement_type == "unclear"
    assert recovered[0].target == "unknown"
    assert recovered[0].certainty == "unclear"
    assert recovered[0].obs_time_type == "unclear"
    assert recovered[0].obs_time_reference == "unknown"
    assert recovered[0].photometric_system == "unknown"
    assert str(recovered[0].obs_time_raw or "") == ""
    assert photometry_feature_values(missing_values)["obs_time_raw"] == ""
    assert photometry_roundtrip_check(
        out_path,
        doc.rendered_text,
        [missing_values],
        TYPESYSTEM_PATH,
    )["all_features_ok"] is True


def test_tagset_defaults_are_valid_project_tagset_values() -> None:
    assert PHOTOMETRY_TAGSET_DEFAULTS == {
        "measurement_type": "unclear",
        "target": "unknown",
        "certainty": "unclear",
        "photometric_system": "unknown",
        "obs_time_type": "unclear",
        "obs_time_reference": "unknown",
    }
    assert PHOTOMETRY_TAGSET_DEFAULTS["measurement_type"] in MEASUREMENT_TYPES
    assert PHOTOMETRY_TAGSET_DEFAULTS["target"] in TARGETS
    assert PHOTOMETRY_TAGSET_DEFAULTS["certainty"] in CERTAINTIES
    assert PHOTOMETRY_TAGSET_DEFAULTS["photometric_system"] in PHOTOMETRIC_SYSTEMS
    assert PHOTOMETRY_TAGSET_DEFAULTS["obs_time_type"] in OBS_TIME_TYPES
    assert PHOTOMETRY_TAGSET_DEFAULTS["obs_time_reference"] in OBS_TIME_REFERENCES


def test_missing_typesystem_feature_is_omitted_without_failure(tmp_path: Path) -> None:
    doc, measurements = _fixture_measurements()
    reduced_typesystem_path = tmp_path / "reduced-TypeSystem.xml"
    reduced_typesystem = TypeSystem()
    layer = reduced_typesystem.create_type(PHOTOMETRY_TYPE)
    for feature_name in PHOTOMETRY_FEATURES:
        if feature_name != "limit_sigma":
            reduced_typesystem.create_feature(layer, feature_name, "uima.cas.String")
    reduced_typesystem.to_xml(reduced_typesystem_path)

    out_path = tmp_path / "reduced.xmi"
    export_photometry_xmi(doc, measurements, reduced_typesystem_path, out_path)
    result = photometry_roundtrip_check(
        out_path,
        doc.rendered_text,
        measurements,
        reduced_typesystem_path,
    )

    assert result["all_features_ok"] is True
    assert result["all_spans_ok"] is True
    with reduced_typesystem_path.open("rb") as handle:
        loaded_typesystem = load_typesystem(handle)
    feature_names = {
        feature.name for feature in loaded_typesystem.get_type(PHOTOMETRY_TYPE).features
    }
    assert "limit_sigma" not in feature_names


def test_limit_sigma_roundtrips_when_typesystem_feature_exists(tmp_path: Path) -> None:
    doc, measurements = _fixture_measurements()
    typesystem_path = tmp_path / "limit-sigma-TypeSystem.xml"
    typesystem = TypeSystem()
    layer = typesystem.create_type(PHOTOMETRY_TYPE)
    for feature_name in PHOTOMETRY_FEATURES:
        typesystem.create_feature(layer, feature_name, "uima.cas.String")
    typesystem.to_xml(typesystem_path)

    out_path = tmp_path / "limit-sigma.xmi"
    export_photometry_xmi(doc, measurements, typesystem_path, out_path)
    result = photometry_roundtrip_check(
        out_path,
        doc.rendered_text,
        measurements,
        typesystem_path,
    )

    assert result["all_features_ok"] is True
    with typesystem_path.open("rb") as handle:
        loaded_typesystem = load_typesystem(handle)
    with out_path.open("rb") as handle:
        cas = load_cas_from_xmi(handle, typesystem=loaded_typesystem)
    recovered = {
        item.measurement_type: item for item in cas.select(PHOTOMETRY_TYPE)
    }
    assert str(recovered["detection"].limit_sigma or "") == ""
    assert recovered["upper_limit"].limit_sigma == "5"
