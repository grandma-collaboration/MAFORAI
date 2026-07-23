from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from skyportal_corpus.extraction_v2.photometry_tagsets import (
    CERTAINTIES,
    INSTRUMENT_PROVENANCES,
    MEASUREMENT_TYPES,
    OBS_TIME_REFERENCES,
    OBS_TIME_TYPES,
    TARGETS,
)


class PhotometricMeasurementAnnotation(BaseModel):
    """Offset-anchored annotation for the PHOTOMETRIC_MEASUREMENT layer.

    The real INCEpTION feature names are defined by
    webanno.custom.PHOTOMETRIC_MEASUREMENT in data/inception/TypeSystem.xml. If
    the internal model contains a field absent from a particular TypeSystem
    revision, the photometry exporter omits that field without changing the
    annotation model.
    """

    model_config = ConfigDict(frozen=True)

    circular_id: int
    text_sha256: str
    span_start: int
    span_end: int
    text: str
    measurement_type: str
    target: str
    certainty: str
    magnitude_or_limit: str | None = None
    magnitude_error: str | None = None
    limit_sigma: str | None = None
    unit: str | None = None
    photometric_band: str | None = None
    photometric_system: str | None = None
    obs_time_raw: str | None = None
    obs_time_type: str | None = None
    obs_time_reference: str | None = None
    exposure_time_raw: str | None = None
    instrument: str | None = None
    instrument_provenance: str | None = None
    comment: str | None = None
    provenance_inherited: list[str] = Field(default_factory=list)
    extractor_id: str
    extractor_version: str
    method: str
    rule_id: str | None = None
    confidence: float = 1.0
    needs_review: bool = False
    schema_version: str = Field(default="0.1")

    @field_validator("measurement_type")
    @classmethod
    def _validate_measurement_type(cls, value: str) -> str:
        if value not in MEASUREMENT_TYPES:
            raise ValueError(f"Invalid PHOTOMETRIC_MEASUREMENT measurement_type: {value!r}")
        return value

    @field_validator("target")
    @classmethod
    def _validate_target(cls, value: str) -> str:
        if value not in TARGETS:
            raise ValueError(f"Invalid PHOTOMETRIC_MEASUREMENT target: {value!r}")
        return value

    @field_validator("certainty")
    @classmethod
    def _validate_certainty(cls, value: str) -> str:
        if value not in CERTAINTIES:
            raise ValueError(f"Invalid PHOTOMETRIC_MEASUREMENT certainty: {value!r}")
        return value

    @field_validator("obs_time_type")
    @classmethod
    def _validate_obs_time_type(cls, value: str | None) -> str | None:
        if value is not None and value not in OBS_TIME_TYPES:
            raise ValueError(f"Invalid PHOTOMETRIC_MEASUREMENT obs_time_type: {value!r}")
        return value

    @field_validator("obs_time_reference")
    @classmethod
    def _validate_obs_time_reference(cls, value: str | None) -> str | None:
        if value is not None and value not in OBS_TIME_REFERENCES:
            raise ValueError(f"Invalid PHOTOMETRIC_MEASUREMENT obs_time_reference: {value!r}")
        return value

    @field_validator("instrument_provenance")
    @classmethod
    def _validate_instrument_provenance(cls, value: str | None) -> str | None:
        if value is not None and value not in INSTRUMENT_PROVENANCES:
            raise ValueError(f"Invalid PHOTOMETRIC_MEASUREMENT instrument_provenance: {value!r}")
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
    def _validate_span(self) -> PhotometricMeasurementAnnotation:
        if self.span_end <= self.span_start:
            raise ValueError("span_end must be > span_start")
        if len(self.text) != self.span_end - self.span_start:
            raise ValueError("text length must match span_end - span_start")
        if self.limit_sigma is not None and self.measurement_type != "upper_limit":
            raise ValueError("limit_sigma is only valid for upper_limit measurements")
        return self

    def verify(self, rendered_text: str) -> bool:
        return (
            0 <= self.span_start < self.span_end <= len(rendered_text)
            and rendered_text[self.span_start : self.span_end] == self.text
        )


def photometry_measurement_key(
    annotation: PhotometricMeasurementAnnotation,
) -> tuple[object, ...]:
    """Return the complete stable identity of one parsed measurement."""

    return (
        "PHOTOMETRIC_MEASUREMENT",
        annotation.rule_id,
        annotation.span_start,
        annotation.span_end,
        annotation.text,
        annotation.measurement_type,
        annotation.target,
        annotation.certainty,
        annotation.magnitude_or_limit,
        annotation.magnitude_error,
        annotation.limit_sigma,
        annotation.unit,
        annotation.photometric_band,
        annotation.photometric_system,
        annotation.obs_time_raw,
        annotation.obs_time_type,
        annotation.obs_time_reference,
        annotation.exposure_time_raw,
        annotation.instrument,
        annotation.instrument_provenance,
        annotation.comment,
        tuple(annotation.provenance_inherited),
        annotation.extractor_id,
        annotation.extractor_version,
        annotation.method,
        annotation.confidence,
        annotation.needs_review,
    )


def deduplicate_photometry_measurements(
    annotations: Sequence[PhotometricMeasurementAnnotation],
) -> list[PhotometricMeasurementAnnotation]:
    """Keep the first occurrence of each identical parsed measurement."""

    seen: set[tuple[object, ...]] = set()
    unique: list[PhotometricMeasurementAnnotation] = []
    for annotation in annotations:
        key = photometry_measurement_key(annotation)
        if key in seen:
            continue
        seen.add(key)
        unique.append(annotation)
    return unique


def suppress_prose_overlapping_rows(
    row_annotations: Sequence[PhotometricMeasurementAnnotation],
    prose_annotations: Sequence[PhotometricMeasurementAnnotation],
) -> list[PhotometricMeasurementAnnotation]:
    """Suppress prose measurements whose spans overlap parsed table rows."""

    row_spans = tuple(
        (annotation.span_start, annotation.span_end)
        for annotation in row_annotations
    )
    return [
        annotation
        for annotation in prose_annotations
        if not any(
            annotation.span_start < row_end and row_start < annotation.span_end
            for row_start, row_end in row_spans
        )
    ]


def merge_photometry_measurements(
    row_annotations: Sequence[PhotometricMeasurementAnnotation],
    prose_annotations: Sequence[PhotometricMeasurementAnnotation],
) -> list[PhotometricMeasurementAnnotation]:
    """Merge row and prose output with row precedence and final deduplication."""

    surviving_prose = suppress_prose_overlapping_rows(
        row_annotations,
        prose_annotations,
    )
    return deduplicate_photometry_measurements(
        [*row_annotations, *surviving_prose]
    )
