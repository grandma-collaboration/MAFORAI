from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from cassis import Cas, load_typesystem

from skyportal_corpus.extraction_v2.annotations import EventEvidenceAnnotation
from skyportal_corpus.extraction_v2.event_document import EventCanonicalDocument
from skyportal_corpus.extraction_v2.photometry_annotations import (
    PhotometricMeasurementAnnotation,
)
from skyportal_corpus.inception_v2.photometry_xmi_export import (
    PHOTOMETRY_FEATURES,
    PHOTOMETRY_TYPE,
    photometry_feature_values,
    photometry_roundtrip_check,
)
from skyportal_corpus.inception_v2.xmi_export import (
    ASTRO_EVIDENCE_TYPE,
    _add_minimal_segmentation,
)
from skyportal_corpus.inception_v2.xmi_roundtrip import roundtrip_check


EVENT_EVIDENCE_FEATURES = (
    "label",
    "target",
    "certainty",
    "value",
    "unit",
    "comment",
)


def export_event_layers_xmi(
    event_doc: EventCanonicalDocument,
    event_annotations: Sequence[EventEvidenceAnnotation],
    photometry_measurements: Sequence[PhotometricMeasurementAnnotation],
    typesystem_path: str | Path,
    out_path: str | Path,
) -> None:
    """Export EVENT_EVIDENCE and PHOTOMETRIC_MEASUREMENT into one CAS."""

    with Path(typesystem_path).open("rb") as handle:
        typesystem = load_typesystem(handle)

    cas = Cas(typesystem=typesystem)
    cas.sofa_string = event_doc.event_rendered_text
    _add_minimal_segmentation(cas, typesystem, event_doc.event_rendered_text)

    evidence_layer = typesystem.get_type(ASTRO_EVIDENCE_TYPE)
    evidence_features = _available_feature_names(evidence_layer)
    for annotation in event_annotations:
        _verify_span(
            event_doc.event_rendered_text,
            annotation.span_start,
            annotation.span_end,
            annotation.text,
            "EVENT_EVIDENCE",
        )
        values = {
            "label": annotation.label,
            "target": annotation.target,
            "certainty": annotation.certainty,
            "value": annotation.value or "",
            "unit": annotation.unit or "",
            "comment": annotation.comment or "",
        }
        payload = {
            name: values[name]
            for name in EVENT_EVIDENCE_FEATURES
            if name in evidence_features
        }
        cas.add(
            evidence_layer(
                begin=annotation.span_start,
                end=annotation.span_end,
                **payload,
            )
        )

    photometry_layer = typesystem.get_type(PHOTOMETRY_TYPE)
    photometry_features = _available_feature_names(photometry_layer)
    for measurement in photometry_measurements:
        _verify_span(
            event_doc.event_rendered_text,
            measurement.span_start,
            measurement.span_end,
            measurement.text,
            "PHOTOMETRIC_MEASUREMENT",
        )
        # Use the shared mapping so tagset defaults match standalone exports.
        values = photometry_feature_values(measurement)
        payload = {
            name: values[name]
            for name in PHOTOMETRY_FEATURES
            if name in photometry_features
        }
        cas.add(
            photometry_layer(
                begin=measurement.span_start,
                end=measurement.span_end,
                **payload,
            )
        )

    output_file = Path(out_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    cas.to_xmi(output_file)


def event_layers_roundtrip_check(
    xmi_path: str | Path,
    typesystem_path: str | Path,
    event_doc: EventCanonicalDocument,
    event_annotations: Sequence[EventEvidenceAnnotation],
    photometry_measurements: Sequence[PhotometricMeasurementAnnotation],
) -> dict[str, Any]:
    """Verify both event layers independently against the shared sofa text."""

    evidence = roundtrip_check(
        xmi_path,
        typesystem_path,
        event_annotations,
        event_doc.event_rendered_text,
    )
    photometry = photometry_roundtrip_check(
        xmi_path,
        event_doc.event_rendered_text,
        photometry_measurements,
        typesystem_path,
    )
    text_matches = bool(evidence["text_matches"] and photometry["text_matches"])
    return {
        "text_matches": text_matches,
        "event_evidence": evidence,
        "photometry": photometry,
        "all_ok": text_matches and _layer_roundtrip_ok(evidence) and _layer_roundtrip_ok(photometry),
    }


def _layer_roundtrip_ok(result: dict[str, Any]) -> bool:
    return (
        bool(result["text_matches"])
        and bool(result["all_spans_ok"])
        and bool(result["all_features_ok"])
        and int(result["n_original"]) == int(result["n_roundtripped"])
    )


def _available_feature_names(layer: object) -> set[str]:
    return {feature.name for feature in layer.features}  # type: ignore[attr-defined]


def _verify_span(
    text: str,
    span_start: int,
    span_end: int,
    expected: str,
    layer_name: str,
) -> None:
    actual = text[span_start:span_end]
    if actual != expected:
        raise ValueError(
            f"{layer_name} text mismatch at {span_start}-{span_end}: "
            f"{expected!r} != {actual!r}"
        )


__all__ = [
    "EVENT_EVIDENCE_FEATURES",
    "event_layers_roundtrip_check",
    "export_event_layers_xmi",
]
