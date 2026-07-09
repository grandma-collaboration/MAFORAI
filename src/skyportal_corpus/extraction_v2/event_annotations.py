from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from skyportal_corpus.canonical.document import CanonicalDocument
from skyportal_corpus.extraction_v2.annotations import EventEvidenceAnnotation
from skyportal_corpus.extraction_v2.event_document import (
    EventCanonicalDocument,
    local_to_global,
)
from skyportal_corpus.extraction_v2.sweep import get_active_extractors


def extract_event_annotations(
    event_doc: EventCanonicalDocument,
    circular_docs: Mapping[int, CanonicalDocument],
    *,
    errors: list[dict[str, Any]] | None = None,
) -> list[EventEvidenceAnnotation]:
    """Run active extractors locally and translate verified spans to event offsets."""
    extraction_errors = errors if errors is not None else []
    global_annotations: list[EventEvidenceAnnotation] = []
    extractors = get_active_extractors()

    for segment in event_doc.segments:
        circular_doc = circular_docs.get(segment.circular_id)
        if circular_doc is None:
            extraction_errors.append(
                {
                    "circular_id": segment.circular_id,
                    "extractor_id": None,
                    "message": "Missing CanonicalDocument for event segment",
                }
            )
            continue
        if circular_doc.text_sha256 != segment.local_text_sha256:
            extraction_errors.append(
                {
                    "circular_id": segment.circular_id,
                    "extractor_id": None,
                    "message": (
                        "CanonicalDocument sha256 does not match the event segment "
                        "local_text_sha256"
                    ),
                }
            )
            continue

        for extractor in extractors:
            for annotation in extractor.extract(circular_doc):
                global_start = local_to_global(
                    event_doc,
                    segment.circular_id,
                    annotation.span_start,
                )
                global_end = local_to_global(
                    event_doc,
                    segment.circular_id,
                    annotation.span_end,
                )
                event_slice = event_doc.event_rendered_text[global_start:global_end]
                if event_slice != annotation.text:
                    extraction_errors.append(
                        {
                            "circular_id": segment.circular_id,
                            "extractor_id": annotation.extractor_id,
                            "local_span_start": annotation.span_start,
                            "local_span_end": annotation.span_end,
                            "global_span_start": global_start,
                            "global_span_end": global_end,
                            "message": (
                                "Translated event span does not match the local "
                                "annotation text"
                            ),
                        }
                    )
                    continue

                annotation_data = annotation.model_dump()
                annotation_data.update(
                    {
                        "span_start": global_start,
                        "span_end": global_end,
                        "text_sha256": event_doc.event_text_sha256,
                        "source_circular_id": segment.circular_id,
                    }
                )
                global_annotation = EventEvidenceAnnotation.model_validate(annotation_data)
                if not global_annotation.verify(event_doc.event_rendered_text):
                    extraction_errors.append(
                        {
                            "circular_id": segment.circular_id,
                            "extractor_id": annotation.extractor_id,
                            "global_span_start": global_start,
                            "global_span_end": global_end,
                            "message": "Global annotation failed verify()",
                        }
                    )
                    continue
                global_annotations.append(global_annotation)

    return sorted(
        global_annotations,
        key=lambda annotation: (
            annotation.span_start,
            annotation.span_end,
            annotation.extractor_id,
            annotation.rule_id or "",
        ),
    )
