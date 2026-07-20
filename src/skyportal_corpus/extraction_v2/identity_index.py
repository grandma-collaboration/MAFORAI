from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from skyportal_corpus.canonical.document import iter_real_circulars, render_canonical
from skyportal_corpus.extraction_v2.annotations import EventEvidenceAnnotation
from skyportal_corpus.extraction_v2.event_grouping import _body_text, _is_in_header
from skyportal_corpus.extraction_v2.event_identity import EventIdentityExtractor


DEFAULT_IDENTITY_INDEX_DIR = Path("data/interim/gcn/event_matching/identity_index")
DEFAULT_IDENTITY_INDEX_PATH = DEFAULT_IDENTITY_INDEX_DIR / "identity_index.parquet"
DEFAULT_IDENTITY_INDEX_META_PATH = DEFAULT_IDENTITY_INDEX_DIR / "index_meta.json"
IDENTITY_FIELDS = (
    "value",
    "text",
    "span_start",
    "span_end",
    "rule_id",
    "needs_review",
)
IDENTITY_STRUCT = pa.struct(
    [
        pa.field("value", pa.string(), nullable=True),
        pa.field("text", pa.string(), nullable=False),
        pa.field("span_start", pa.int64(), nullable=False),
        pa.field("span_end", pa.int64(), nullable=False),
        pa.field("rule_id", pa.string(), nullable=True),
        pa.field("needs_review", pa.bool_(), nullable=False),
    ]
)
IDENTITY_INDEX_SCHEMA = pa.schema(
    [
        pa.field("circular_id", pa.int64(), nullable=False),
        pa.field("subject", pa.string(), nullable=False),
        pa.field("created_on", pa.string(), nullable=True),
        pa.field("body_text", pa.string(), nullable=False),
        pa.field("subject_identities", pa.list_(IDENTITY_STRUCT), nullable=False),
        pa.field("body_identities", pa.list_(IDENTITY_STRUCT), nullable=False),
    ]
)


def build_identity_index_records(
    circulars: Iterable[Mapping[str, Any]],
    *,
    extractor: EventIdentityExtractor | None = None,
) -> list[dict[str, Any]]:
    """Extract reusable identity records from normalized Circular mappings."""
    identity_extractor = extractor or EventIdentityExtractor()
    records: list[dict[str, Any]] = []
    for circular in circulars:
        document = render_canonical(
            circular_id=int(circular["circular_id"]),
            subject=str(circular.get("subject") or ""),
            body=str(circular.get("body") or ""),
            event_id=_optional_text(circular.get("event_id")),
            created_on=_optional_text(circular.get("created_on")),
            submitter=_optional_text(circular.get("submitter")),
        )
        annotations = identity_extractor.extract(document)
        subject_annotations = [
            annotation
            for annotation in annotations
            if _is_in_header(document, annotation) and not annotation.needs_review
        ]
        body_annotations = [
            annotation for annotation in annotations if annotation not in subject_annotations
        ]
        records.append(
            {
                "circular_id": document.circular_id,
                "subject": document.subject,
                "created_on": document.created_on,
                "body_text": _body_text(document),
                "subject_identities": [
                    identity_entry(annotation) for annotation in subject_annotations
                ],
                "body_identities": [
                    identity_entry(annotation) for annotation in body_annotations
                ],
            }
        )
    return records


def identity_entry(annotation: EventEvidenceAnnotation) -> dict[str, Any]:
    """Serialize the exact fields consumed and reported by circular_matches_event()."""
    return {
        "value": annotation.value,
        "text": annotation.text,
        "span_start": annotation.span_start,
        "span_end": annotation.span_end,
        "rule_id": annotation.rule_id,
        "needs_review": annotation.needs_review,
    }


def write_identity_index(records: Iterable[Mapping[str, Any]], path: str | Path) -> Path:
    """Write identity index rows using a stable nested Arrow schema."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [dict(record) for record in records]
    table = pa.Table.from_pylist(rows, schema=IDENTITY_INDEX_SCHEMA)
    pq.write_table(table, output_path, compression="zstd")
    return output_path


def read_identity_index(path: str | Path) -> list[dict[str, Any]]:
    """Read identity index rows as plain Python mappings."""
    table = pq.read_table(Path(path), schema=IDENTITY_INDEX_SCHEMA)
    return [dict(record) for record in table.to_pylist()]


def build_identity_index(
    *,
    min_year: int = 2023,
    index_path: str | Path = DEFAULT_IDENTITY_INDEX_PATH,
    meta_path: str | Path = DEFAULT_IDENTITY_INDEX_META_PATH,
) -> dict[str, Any]:
    """Build the full reusable identity index and staleness metadata."""
    extractor = EventIdentityExtractor()
    started = perf_counter()
    records = build_identity_index_records(
        iter_real_circulars(min_year=min_year),
        extractor=extractor,
    )
    output_path = write_identity_index(records, index_path)
    elapsed = perf_counter() - started
    annotation_count = sum(
        len(record["subject_identities"]) + len(record["body_identities"])
        for record in records
    )
    metadata = {
        "schema_version": "0.1",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "min_year": min_year,
        "n_circulars": len(records),
        "n_identity_annotations": annotation_count,
        "build_seconds": elapsed,
        "extractor_id": extractor.extractor_id,
        "extractor_version": extractor.extractor_version,
        "index_path": str(output_path),
        "index_size_bytes": output_path.stat().st_size,
        "index_sha256": _sha256(output_path),
    }
    metadata_path = Path(meta_path)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return metadata


def load_identity_index_meta(path: str | Path) -> dict[str, Any]:
    """Load and validate basic index staleness metadata."""
    metadata = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return metadata


def validate_identity_index_meta(
    metadata: Mapping[str, Any],
    *,
    min_year: int | None = None,
) -> None:
    """Reject an index built for another corpus scope or extractor version."""
    extractor = EventIdentityExtractor()
    if metadata.get("extractor_id") != extractor.extractor_id:
        raise ValueError("Identity index extractor_id is stale")
    if metadata.get("extractor_version") != extractor.extractor_version:
        raise ValueError("Identity index extractor_version is stale")
    if min_year is not None and int(metadata.get("min_year", -1)) != min_year:
        raise ValueError(
            f"Identity index min_year={metadata.get('min_year')} does not match {min_year}"
        )


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "DEFAULT_IDENTITY_INDEX_DIR",
    "DEFAULT_IDENTITY_INDEX_META_PATH",
    "DEFAULT_IDENTITY_INDEX_PATH",
    "IDENTITY_FIELDS",
    "IDENTITY_INDEX_SCHEMA",
    "build_identity_index",
    "build_identity_index_records",
    "identity_entry",
    "load_identity_index_meta",
    "read_identity_index",
    "validate_identity_index_meta",
    "write_identity_index",
]
