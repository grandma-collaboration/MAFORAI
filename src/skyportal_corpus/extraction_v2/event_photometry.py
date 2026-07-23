from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from skyportal_corpus.canonical.document import CanonicalDocument
from skyportal_corpus.extraction_v2.event_document import (
    EventCanonicalDocument,
    local_to_global,
)
from skyportal_corpus.extraction_v2.photometry_annotations import (
    PhotometricMeasurementAnnotation,
    merge_photometry_measurements,
)
from skyportal_corpus.extraction_v2.photometry_prose import ProsePhotometryExtractor
from skyportal_corpus.extraction_v2.photometry_rows import parse_table_to_measurements
from skyportal_corpus.extraction_v2.photometry_tables import detect_table_blocks


class EventPhotometricMeasurementAnnotation(PhotometricMeasurementAnnotation):
    """Event-level measurement with internal circular provenance.

    ``source_circular_id`` is intentionally absent from the INCEpTION feature
    mapping. It remains available to corpus code and future event aggregation.
    """

    source_circular_id: int


def extract_event_photometry(
    event_doc: EventCanonicalDocument,
    circular_docs: Mapping[int, CanonicalDocument],
    *,
    errors: list[dict[str, Any]] | None = None,
) -> list[EventPhotometricMeasurementAnnotation]:
    """Extract local table/prose photometry and translate it to event offsets."""

    extraction_errors = errors if errors is not None else []
    global_measurements: list[EventPhotometricMeasurementAnnotation] = []
    prose_extractor = ProsePhotometryExtractor()

    for segment in event_doc.segments:
        circular_doc = circular_docs.get(segment.circular_id)
        if circular_doc is None:
            extraction_errors.append(
                {
                    "circular_id": segment.circular_id,
                    "source": None,
                    "message": "Missing CanonicalDocument for event segment",
                }
            )
            continue
        if circular_doc.text_sha256 != segment.local_text_sha256:
            extraction_errors.append(
                {
                    "circular_id": segment.circular_id,
                    "source": None,
                    "message": (
                        "CanonicalDocument sha256 does not match the event segment "
                        "local_text_sha256"
                    ),
                }
            )
            continue

        row_measurements: list[PhotometricMeasurementAnnotation] = []
        for block in detect_table_blocks(circular_doc.rendered_text):
            row_measurements.extend(parse_table_to_measurements(block, circular_doc))
        local_measurements = merge_photometry_measurements(
            row_measurements,
            prose_extractor.extract(circular_doc),
        )

        for measurement in local_measurements:
            global_start = local_to_global(
                event_doc,
                segment.circular_id,
                measurement.span_start,
            )
            global_end = local_to_global(
                event_doc,
                segment.circular_id,
                measurement.span_end,
            )
            event_slice = event_doc.event_rendered_text[global_start:global_end]
            if event_slice != measurement.text:
                extraction_errors.append(
                    {
                        "circular_id": segment.circular_id,
                        "source": _measurement_source(measurement),
                        "local_span_start": measurement.span_start,
                        "local_span_end": measurement.span_end,
                        "global_span_start": global_start,
                        "global_span_end": global_end,
                        "message": (
                            "Translated event span does not match the local "
                            "photometry text"
                        ),
                    }
                )
                continue

            measurement_data = measurement.model_dump()
            measurement_data.update(
                {
                    "span_start": global_start,
                    "span_end": global_end,
                    "text_sha256": event_doc.event_text_sha256,
                    "source_circular_id": segment.circular_id,
                }
            )
            global_measurement = EventPhotometricMeasurementAnnotation.model_validate(
                measurement_data
            )
            if not global_measurement.verify(event_doc.event_rendered_text):
                extraction_errors.append(
                    {
                        "circular_id": segment.circular_id,
                        "source": _measurement_source(measurement),
                        "global_span_start": global_start,
                        "global_span_end": global_end,
                        "message": "Global photometry measurement failed verify()",
                    }
                )
                continue
            global_measurements.append(global_measurement)

    return sorted(
        global_measurements,
        key=lambda measurement: (
            measurement.span_start,
            measurement.span_end,
            measurement.method,
            measurement.rule_id or "",
            measurement.measurement_type,
        ),
    )


def measurement_source(measurement: PhotometricMeasurementAnnotation) -> str:
    """Return the stable report source for a photometry measurement."""

    return _measurement_source(measurement)


def _measurement_source(measurement: PhotometricMeasurementAnnotation) -> str:
    return "table" if measurement.method == "table-parse" else "prose"


__all__ = [
    "EventPhotometricMeasurementAnnotation",
    "extract_event_photometry",
    "measurement_source",
]
