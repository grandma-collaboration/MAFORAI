from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from skyportal_corpus.canonical.document import CanonicalDocument, render_canonical


SEPARATOR_TEMPLATE = "\n\n===== CIRCULAR {circular_id} =====\n\n"


class CircularSegment(BaseModel):
    model_config = ConfigDict(frozen=True)

    circular_id: int
    global_start: int
    global_end: int
    local_text_sha256: str
    subject: str
    created_on: str | None

    @model_validator(mode="after")
    def _validate_span(self) -> CircularSegment:
        if self.global_start < 0:
            raise ValueError("global_start must be non-negative")
        if self.global_end <= self.global_start:
            raise ValueError("global_end must be greater than global_start")
        if len(self.local_text_sha256) != 64:
            raise ValueError("local_text_sha256 must be a hex sha256 string")
        return self


class EventCanonicalDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_id: str
    title: str
    event_rendered_text: str
    event_text_sha256: str
    segments: list[CircularSegment]
    n_circulars: int
    schema_version: str = Field(default="0.1")

    @model_validator(mode="after")
    def _validate_document(self) -> EventCanonicalDocument:
        expected_sha256 = hashlib.sha256(self.event_rendered_text.encode("utf-8")).hexdigest()
        if self.event_text_sha256 != expected_sha256:
            raise ValueError("event_text_sha256 does not match event_rendered_text")
        if self.n_circulars != len(self.segments):
            raise ValueError("n_circulars must match the number of segments")
        previous_end = -1
        for segment in self.segments:
            if segment.global_start < previous_end:
                raise ValueError("segments must be sorted and non-overlapping")
            if segment.global_end > len(self.event_rendered_text):
                raise ValueError("segment extends beyond event_rendered_text")
            previous_end = segment.global_end
        return self


def build_event_document(
    source_id: str,
    title: str,
    circulars_in_order: Iterable[Mapping[str, Any]],
) -> EventCanonicalDocument:
    rendered_parts: list[str] = []
    segments: list[CircularSegment] = []
    current_offset = 0

    for circular in sorted(circulars_in_order, key=_circular_sort_key):
        local_doc = _render_local_canonical(circular)
        separator = SEPARATOR_TEMPLATE.format(circular_id=local_doc.circular_id)
        rendered_parts.append(separator)
        current_offset += len(separator)

        global_start = current_offset
        rendered_parts.append(local_doc.rendered_text)
        current_offset += len(local_doc.rendered_text)
        global_end = current_offset

        segments.append(
            CircularSegment(
                circular_id=local_doc.circular_id,
                global_start=global_start,
                global_end=global_end,
                local_text_sha256=local_doc.text_sha256,
                subject=local_doc.subject,
                created_on=local_doc.created_on,
            )
        )

    event_rendered_text = "".join(rendered_parts)
    event_text_sha256 = hashlib.sha256(event_rendered_text.encode("utf-8")).hexdigest()
    return EventCanonicalDocument(
        source_id=source_id,
        title=title,
        event_rendered_text=event_rendered_text,
        event_text_sha256=event_text_sha256,
        segments=segments,
        n_circulars=len(segments),
    )


def local_to_global(doc: EventCanonicalDocument, circular_id: int, local_offset: int) -> int:
    segment = _segment_for_circular(doc, circular_id)
    segment_length = segment.global_end - segment.global_start
    if local_offset < 0 or local_offset > segment_length:
        raise ValueError(
            f"local_offset {local_offset} is outside circular {circular_id} "
            f"canonical text length {segment_length}"
        )
    return segment.global_start + local_offset


def global_to_circular(doc: EventCanonicalDocument, global_offset: int) -> tuple[int, int] | None:
    if global_offset < 0 or global_offset > len(doc.event_rendered_text):
        raise ValueError(
            f"global_offset {global_offset} is outside event text length {len(doc.event_rendered_text)}"
        )
    for segment in doc.segments:
        if segment.global_start <= global_offset < segment.global_end:
            return segment.circular_id, global_offset - segment.global_start
    return None


def _segment_for_circular(doc: EventCanonicalDocument, circular_id: int) -> CircularSegment:
    for segment in doc.segments:
        if segment.circular_id == circular_id:
            return segment
    raise KeyError(f"circular_id {circular_id} is not present in event document")


def _render_local_canonical(circular: Mapping[str, Any]) -> CanonicalDocument:
    return render_canonical(
        circular_id=int(circular["circular_id"]),
        subject=str(circular.get("subject") or ""),
        body=str(circular.get("body") or ""),
        event_id=_optional_str(circular.get("event_id")),
        created_on=_optional_str(circular.get("created_on")),
        submitter=_optional_str(circular.get("submitter")),
    )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _circular_sort_key(circular: Mapping[str, Any]) -> tuple[str, int]:
    return str(circular.get("created_on") or ""), int(circular["circular_id"])
