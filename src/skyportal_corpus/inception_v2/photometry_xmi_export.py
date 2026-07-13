from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from cassis import Cas, load_cas_from_xmi, load_typesystem

from skyportal_corpus.canonical.document import CanonicalDocument
from skyportal_corpus.extraction_v2.photometry_annotations import (
    PhotometricMeasurementAnnotation,
)
from skyportal_corpus.inception_v2.xmi_export import _add_minimal_segmentation


PHOTOMETRY_TYPE = "webanno.custom.PHOTOMETRIC_MEASUREMENT"
PHOTOMETRY_FEATURES = (
    "measurement_type",
    "target",
    "certainty",
    "magnitude_or_limit",
    "magnitude_error",
    "limit_sigma",
    "unit",
    "photometric_band",
    "photometric_system",
    "obs_time_raw",
    "obs_time_type",
    "obs_time_reference",
    "exposure_time_raw",
    "timezone_raw",
    "instrument",
    "comment",
)

# INCEpTION rejects an empty string when a feature is constrained by a tagset.
# Free-text features keep using an empty string when the internal value is None.
PHOTOMETRY_TAGSET_DEFAULTS = {
    "measurement_type": "unclear",
    "target": "unknown",
    "certainty": "unclear",
    "photometric_system": "unknown",
    "obs_time_type": "unclear",
    "obs_time_reference": "unknown",
}


def export_photometry_xmi(
    doc: CanonicalDocument,
    measurements: Sequence[PhotometricMeasurementAnnotation],
    typesystem_path: str | Path,
    out_path: str | Path,
) -> None:
    """Export offset-anchored photometry measurements to an INCEpTION CAS XMI."""

    typesystem_file = Path(typesystem_path)
    with typesystem_file.open("rb") as handle:
        typesystem = load_typesystem(handle)

    cas = Cas(typesystem=typesystem)
    cas.sofa_string = doc.rendered_text
    _add_minimal_segmentation(cas, typesystem, doc.rendered_text)

    layer = typesystem.get_type(PHOTOMETRY_TYPE)
    available_features = _available_feature_names(layer)
    for measurement in measurements:
        expected_text = doc.rendered_text[measurement.span_start : measurement.span_end]
        if expected_text != measurement.text:
            raise ValueError(
                f"Measurement text mismatch at {measurement.span_start}-{measurement.span_end}: "
                f"{measurement.text!r} != {expected_text!r}"
            )
        values = photometry_feature_values(measurement)
        payload = {
            feature_name: values[feature_name]
            for feature_name in PHOTOMETRY_FEATURES
            if feature_name in available_features
        }
        cas.add(
            layer(
                begin=measurement.span_start,
                end=measurement.span_end,
                **payload,
            )
        )

    output_file = Path(out_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    cas.to_xmi(output_file)


def photometry_roundtrip_check(
    xmi_path: str | Path,
    original_text: str,
    original_measurements: Sequence[PhotometricMeasurementAnnotation],
    typesystem_path: str | Path = "data/inception/TypeSystem.xml",
) -> dict[str, Any]:
    """Reload a photometry XMI and compare text, spans, and exported features."""

    with Path(typesystem_path).open("rb") as handle:
        typesystem = load_typesystem(handle)
    with Path(xmi_path).open("rb") as handle:
        cas = load_cas_from_xmi(handle, typesystem=typesystem)

    layer = typesystem.get_type(PHOTOMETRY_TYPE)
    exported_features = tuple(
        feature_name
        for feature_name in PHOTOMETRY_FEATURES
        if feature_name in _available_feature_names(layer)
    )
    roundtripped = list(cas.select(PHOTOMETRY_TYPE))
    discrepancies: list[str] = []
    text_matches = cas.sofa_string == original_text

    original_span_counts = Counter(
        (measurement.span_start, measurement.span_end) for measurement in original_measurements
    )
    roundtripped_span_counts = Counter(
        (int(measurement.begin), int(measurement.end)) for measurement in roundtripped
    )
    all_spans_ok = original_span_counts == roundtripped_span_counts
    if not all_spans_ok:
        discrepancies.append(
            "Span multiplicities differ: "
            f"original={dict(original_span_counts)}, roundtripped={dict(roundtripped_span_counts)}"
        )

    original_texts_by_span: dict[tuple[int, int], set[str]] = {}
    for measurement in original_measurements:
        original_texts_by_span.setdefault(
            (measurement.span_start, measurement.span_end), set()
        ).add(measurement.text)
    for measurement in roundtripped:
        span = (int(measurement.begin), int(measurement.end))
        span_text = cas.sofa_string[span[0] : span[1]]
        if span_text not in original_texts_by_span.get(span, set()):
            all_spans_ok = False
            discrepancies.append(f"Span text mismatch for {span[0]}-{span[1]}: {span_text!r}")

    original_signatures = Counter(
        _original_signature(measurement, exported_features)
        for measurement in original_measurements
    )
    roundtripped_signatures = Counter(
        _roundtripped_signature(measurement, exported_features)
        for measurement in roundtripped
    )
    all_features_ok = original_signatures == roundtripped_signatures
    if not all_features_ok:
        for signature, count in (original_signatures - roundtripped_signatures).items():
            discrepancies.append(f"Missing roundtripped annotation x{count}: {signature!r}")
        for signature, count in (roundtripped_signatures - original_signatures).items():
            discrepancies.append(f"Unexpected roundtripped annotation x{count}: {signature!r}")

    return {
        "text_matches": text_matches,
        "n_original": len(original_measurements),
        "n_roundtripped": len(roundtripped),
        "all_spans_ok": all_spans_ok,
        "all_features_ok": all_features_ok,
        "discrepancies": discrepancies,
    }


def photometry_feature_values(
    measurement: PhotometricMeasurementAnnotation,
) -> dict[str, str]:
    """Return the exact string values written to INCEpTION features.

    Missing tagset-backed features receive a valid tagset value. Missing free-text
    features remain empty strings so absence is not confused with observed data.
    """

    values = {
        feature_name: str(getattr(measurement, feature_name, None) or "")
        for feature_name in PHOTOMETRY_FEATURES
    }
    for feature_name, default in PHOTOMETRY_TAGSET_DEFAULTS.items():
        if not values[feature_name]:
            values[feature_name] = default
    values["comment"] = str(measurement.comment or "") if measurement.needs_review else ""
    return values


def get_photometry_typesystem_features(
    typesystem_path: str | Path,
) -> tuple[tuple[str, str], ...]:
    """Return direct feature names and range types defined on the photometry layer."""

    with Path(typesystem_path).open("rb") as handle:
        typesystem = load_typesystem(handle)
    layer = typesystem.get_type(PHOTOMETRY_TYPE)
    return tuple((feature.name, feature.rangeType.name) for feature in layer.features)


def _available_feature_names(layer: object) -> set[str]:
    return {feature.name for feature in layer.features}  # type: ignore[attr-defined]


def _original_signature(
    measurement: PhotometricMeasurementAnnotation,
    feature_names: tuple[str, ...],
) -> tuple[int, int, tuple[tuple[str, str], ...]]:
    values = photometry_feature_values(measurement)
    return (
        measurement.span_start,
        measurement.span_end,
        tuple((feature_name, values[feature_name]) for feature_name in feature_names),
    )


def _roundtripped_signature(
    measurement: object,
    feature_names: tuple[str, ...],
) -> tuple[int, int, tuple[tuple[str, str], ...]]:
    return (
        int(measurement.begin),  # type: ignore[attr-defined]
        int(measurement.end),  # type: ignore[attr-defined]
        tuple(
            (feature_name, str(getattr(measurement, feature_name, "") or ""))
            for feature_name in feature_names
        ),
    )


__all__ = [
    "PHOTOMETRY_FEATURES",
    "PHOTOMETRY_TAGSET_DEFAULTS",
    "PHOTOMETRY_TYPE",
    "export_photometry_xmi",
    "get_photometry_typesystem_features",
    "photometry_feature_values",
    "photometry_roundtrip_check",
]
