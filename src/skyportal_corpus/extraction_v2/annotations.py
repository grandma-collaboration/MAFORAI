from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from skyportal_corpus.extraction_v2.tagsets import CERTAINTIES, LABELS, TARGETS


# These labels use comment for compact scientific context (for example, the
# instrument or energy band) even when no review is required. All other labels
# retain the pipeline-wide contract that comment is exclusively a review note.
INFORMATIVE_COMMENT_LABELS = frozenset({"T90", "DURATION_GENERAL", "HIGH_ENERGY_PROPERTY"})


class EventEvidenceAnnotation(BaseModel):
    model_config = ConfigDict(frozen=True)

    circular_id: int
    source_circular_id: int | None = None
    text_sha256: str
    span_start: int
    span_end: int
    text: str
    label: str
    target: str | None = None
    certainty: str
    value: str | None = None
    unit: str | None = None
    comment: str | None = None
    extractor_id: str
    extractor_version: str
    method: str
    rule_id: str | None = None
    confidence: float = 1.0
    needs_review: bool = False
    schema_version: str = Field(default="0.1")

    @field_validator("label")
    @classmethod
    def _validate_label(cls, value: str) -> str:
        if value not in LABELS:
            raise ValueError(f"Invalid EVENT_EVIDENCE label: {value!r}")
        return value

    @field_validator("target")
    @classmethod
    def _validate_target(cls, value: str | None) -> str | None:
        if value is not None and value not in TARGETS:
            raise ValueError(f"Invalid EVENT_EVIDENCE target: {value!r}")
        return value

    @field_validator("certainty")
    @classmethod
    def _validate_certainty(cls, value: str) -> str:
        if value not in CERTAINTIES:
            raise ValueError(f"Invalid EVENT_EVIDENCE certainty: {value!r}")
        return value

    @field_validator("comment", mode="before")
    @classmethod
    def _normalize_comment(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("span_start")
    @classmethod
    def _validate_span_start(cls, value: int) -> int:
        if value < 0:
            raise ValueError("span_start must be >= 0")
        return value

    @model_validator(mode="after")
    def _validate_span(self) -> EventEvidenceAnnotation:
        if self.span_end <= self.span_start:
            raise ValueError("span_end must be > span_start")
        if len(self.text) != self.span_end - self.span_start:
            raise ValueError("text length must match span_end - span_start")
        if self.needs_review and self.comment is None:
            raise ValueError("comment is required when needs_review=True")
        if (
            not self.needs_review
            and self.comment is not None
            and self.label not in INFORMATIVE_COMMENT_LABELS
        ):
            raise ValueError("comment must be empty when needs_review=False")
        return self

    def verify(self, rendered_text: str) -> bool:
        return (
            0 <= self.span_start < self.span_end <= len(rendered_text)
            and rendered_text[self.span_start : self.span_end] == self.text
        )
