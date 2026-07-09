from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import sys
from collections.abc import Iterator, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


MIN_YEAR = 2023  # Lower this value to include older circulars.


class Segment(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    start: int
    end: int
    text: str

    @model_validator(mode="after")
    def _validate_span(self) -> Segment:
        if self.start < 0:
            raise ValueError("segment start must be non-negative")
        if self.end < self.start:
            raise ValueError("segment end must be greater than or equal to start")
        if len(self.text) != self.end - self.start:
            raise ValueError("segment text length must match end - start")
        return self


class CanonicalDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    circular_id: int
    event_id: str | None
    subject: str
    created_on: str | None
    rendered_text: str
    text_sha256: str
    segments: list[Segment]
    schema_version: str = Field(default="0.1")

    @model_validator(mode="after")
    def _validate_segments(self) -> CanonicalDocument:
        for segment in self.segments:
            if self.rendered_text[segment.start : segment.end] != segment.text:
                raise ValueError(f"segment {segment.name!r} does not match rendered_text slice")
        expected_sha256 = hashlib.sha256(self.rendered_text.encode("utf-8")).hexdigest()
        if self.text_sha256 != expected_sha256:
            raise ValueError("text_sha256 does not match rendered_text")
        return self


def _normalize_newlines(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def _strip_illegal_xml_chars(s: str) -> str:
    return "".join(ch for ch in s if ch in {"\t", "\n"} or ord(ch) >= 0x20)


def _clean_text(value: str) -> str:
    return _strip_illegal_xml_chars(_normalize_newlines(value))


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    return _clean_text(str(value))


def render_canonical(
    circular_id: int,
    subject: str,
    body: str,
    event_id: str | None = None,
    created_on: str | None = None,
    submitter: str | None = None,
) -> CanonicalDocument:
    subject_text = _clean_text(str(subject))
    body_text = _clean_text(str(body))
    created_on_text = _clean_optional_text(created_on)
    submitter_text = _clean_optional_text(submitter)
    event_id_text = _clean_optional_text(event_id)

    header_text = (
        f"SUBJECT: {subject_text}\n"
        f"DATE: {created_on_text or ''}\n"
        f"FROM: {submitter_text or ''}\n\n"
    )
    rendered_text = f"{header_text}{body_text}"

    # Do not transform rendered_text after this point; every offset targets this exact string.
    body_start = len(header_text)
    segments = [
        Segment(name="header", start=0, end=body_start, text=rendered_text[:body_start]),
        Segment(name="body", start=body_start, end=len(rendered_text), text=rendered_text[body_start:]),
    ]
    text_sha256 = hashlib.sha256(rendered_text.encode("utf-8")).hexdigest()

    return CanonicalDocument(
        circular_id=int(circular_id),
        event_id=event_id_text,
        subject=subject_text,
        created_on=created_on_text,
        rendered_text=rendered_text,
        text_sha256=text_sha256,
        segments=segments,
    )


def iter_real_circulars(
    min_year: int = MIN_YEAR,
    limit: int | None = None,
) -> Iterator[dict[str, Any]]:
    for circular in _iter_real_circular_records(min_year=min_year, limit=limit, include_year=False):
        yield circular


def iter_stratified_circulars(
    per_year: int,
    min_year: int = MIN_YEAR,
) -> Iterator[dict[str, Any]]:
    if per_year <= 0:
        raise ValueError("per_year must be positive")

    grouped: dict[int, list[dict[str, Any]]] = {}
    for circular in _iter_real_circular_records(min_year=min_year, limit=None, include_year=True):
        year = int(circular["year"])
        grouped.setdefault(year, []).append(circular)

    for year in sorted(grouped):
        records = sorted(grouped[year], key=_circular_sort_key)
        yield from _uniform_sample(records, per_year)


def _iter_real_circular_records(
    min_year: int = MIN_YEAR,
    limit: int | None = None,
    include_year: bool = False,
) -> Iterator[dict[str, Any]]:
    project_root = Path(__file__).resolve().parents[3]
    index_root = project_root / "data" / "interim" / "gcn" / "circulars"
    raw_root = project_root / "data" / "raw" / "gcn" / "circulars"
    yielded = 0
    seen_circular_ids: set[int] = set()

    if index_root.exists():
        index_paths = _index_paths(index_root, min_year=min_year)
        if not index_paths:
            print(f"No CSV/Parquet circular index files for year >= {min_year} under: {index_root}")
        for path in index_paths:
            index_year = _year_from_index_path(path)
            for row in _iter_index_rows(path):
                circular = _normalize_circular_record(
                    row,
                    project_root=project_root,
                    index_year=index_year,
                    min_year=min_year,
                    include_year=include_year,
                )
                if circular is not None:
                    circular_id = circular["circular_id"]
                    if circular_id in seen_circular_ids:
                        continue
                    seen_circular_ids.add(circular_id)
                    yield circular
                    yielded += 1
                    if limit is not None and yielded >= limit:
                        return
        if yielded:
            return
        print(f"No circular with year >= {min_year} and body >= 200 chars found in: {index_root}")
    else:
        print(f"Missing circulars index directory: {index_root}")

    if raw_root.exists():
        raw_paths = sorted(raw_root.rglob("*.json"))
        if not raw_paths:
            print(f"No raw JSON circular files found under: {raw_root}")
        for path in raw_paths:
            for record in _iter_json_records(path):
                circular = _normalize_circular_record(
                    record,
                    project_root=project_root,
                    index_year=None,
                    min_year=min_year,
                    include_year=include_year,
                )
                if circular is not None:
                    circular_id = circular["circular_id"]
                    if circular_id in seen_circular_ids:
                        continue
                    seen_circular_ids.add(circular_id)
                    yield circular
                    yielded += 1
                    if limit is not None and yielded >= limit:
                        return
        print(f"No circular with year >= {min_year} and body >= 200 chars found in: {raw_root}")
    else:
        print(f"Missing raw circulars directory: {raw_root}")

    if yielded == 0:
        print("Missing data: circular_id, created date/year, or body >= 200 chars")


def load_one_real_circular(min_year: int = MIN_YEAR) -> dict[str, Any]:
    for circular in iter_real_circulars(min_year=min_year, limit=1):
        return circular
    raise FileNotFoundError(
        f"No real circular with year >= {min_year} and non-empty body >= 200 chars was found"
    )


def _index_paths(root: Path, min_year: int) -> list[Path]:
    selected: dict[tuple[int | None, str], Path] = {}
    for path in sorted(root.rglob("*.csv")) + sorted(root.rglob("*.parquet")):
        year = _year_from_index_path(path)
        if year is not None and year < min_year:
            continue
        key = (year, path.with_suffix("").name)
        if key not in selected:
            selected[key] = path
    return sorted(selected.values(), key=lambda path: (_year_from_index_path(path) or 0, str(path)))


def _iter_index_rows(path: Path) -> Iterator[Mapping[str, Any]]:
    if path.suffix == ".csv":
        csv.field_size_limit(sys.maxsize)
        with path.open("r", encoding="utf-8", newline="") as handle:
            yield from csv.DictReader(handle)
        return

    if path.suffix == ".parquet":
        try:
            import pandas as pd  # type: ignore[import-not-found]
        except ImportError:
            print(f"Cannot read Parquet without pandas installed: {path}")
            return
        try:
            frame = pd.read_parquet(path)
        except Exception as exc:  # pragma: no cover - depends on optional parquet engine.
            print(f"Could not read Parquet file {path}: {exc}")
            return
        for record in frame.to_dict(orient="records"):
            yield record


def _iter_json_records(path: Path) -> Iterator[Mapping[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Could not read JSON circular file {path}: {exc}")
        return

    if isinstance(payload, Mapping):
        yield payload
    elif isinstance(payload, list):
        for item in payload:
            if isinstance(item, Mapping):
                yield item


def _normalize_circular_record(
    record: Mapping[str, Any],
    project_root: Path,
    index_year: int | None = None,
    min_year: int = MIN_YEAR,
    include_year: bool = False,
) -> dict[str, Any] | None:
    enriched_record = _enrich_record_with_raw_body(record, project_root)
    record_year = _record_year(enriched_record, index_year=index_year)
    if record_year is None or record_year < min_year:
        return None

    body = _first_present(enriched_record, ("body", "Body", "text", "message", "content"))
    if body is None:
        return None
    body_text = str(body)
    if len(body_text.strip()) < 200:
        return None

    subject = _first_present(enriched_record, ("subject", "Subject", "title", "Title")) or ""
    circular_id = _first_present(enriched_record, ("circular_id", "circularId"))
    if circular_id is None:
        return None

    normalized_circular_id = _coerce_int(circular_id)
    if normalized_circular_id is None:
        return None

    result: dict[str, Any] = {
        "circular_id": normalized_circular_id,
        "subject": str(subject),
        "body": body_text,
    }
    if include_year:
        result["year"] = record_year

    created_at_iso = _first_present(enriched_record, ("created_at_iso", "createdAtIso", "createdAtISO"))
    created_epoch = _first_present(enriched_record, ("createdOn", "created_on"))
    if created_at_iso is not None:
        result["created_on"] = str(created_at_iso)
    elif created_epoch is not None:
        result["created_on"] = str(created_epoch)

    optional_keys = {
        "event_id": ("event_id", "eventId", "graceid", "grace_id", "source_id"),
        "submitter": ("submitter", "Submitter", "from", "sender"),
    }
    for output_key, input_keys in optional_keys.items():
        value = _first_present(enriched_record, input_keys)
        if value is not None:
            result[output_key] = str(value)

    return result


def _uniform_sample(records: list[dict[str, Any]], per_year: int) -> list[dict[str, Any]]:
    total = len(records)
    if total <= per_year:
        return records

    stride = total / per_year
    selected_indices = [min(total - 1, int((index + 0.5) * stride)) for index in range(per_year)]
    return [records[index] for index in selected_indices]


def _circular_sort_key(circular: Mapping[str, Any]) -> tuple[str, int]:
    created_on = str(circular.get("created_on") or "")
    circular_id = _coerce_int(circular.get("circular_id")) or 0
    return _created_on_sort_key(created_on), circular_id


def _created_on_sort_key(value: str) -> str:
    if len(value) >= 4 and value[:4].isdigit():
        return value

    year = _year_from_epoch_ms(value)
    if year is not None:
        try:
            timestamp_ms = float(value)
        except (TypeError, ValueError):
            return f"{year:04d}"
        return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat()

    return ""


def _enrich_record_with_raw_body(record: Mapping[str, Any], project_root: Path) -> dict[str, Any]:
    enriched_record = dict(record)
    body = _first_present(enriched_record, ("body", "Body", "text", "message", "content"))
    if body is not None and len(str(body).strip()) >= 200:
        return enriched_record

    raw_file_path = _first_present(enriched_record, ("raw_file_path", "rawFilePath"))
    if raw_file_path is None:
        return enriched_record

    raw_path = Path(str(raw_file_path))
    if not raw_path.is_absolute():
        raw_path = project_root / raw_path
    if not raw_path.exists():
        return enriched_record

    raw_record = next(_iter_json_records(raw_path), None)
    if raw_record is None:
        return enriched_record

    for key, value in raw_record.items():
        if key not in enriched_record or _is_missing(enriched_record[key]):
            enriched_record[key] = value

    raw_body = _first_present(raw_record, ("body", "Body", "text", "message", "content"))
    if raw_body is not None:
        enriched_record["body"] = raw_body
    return enriched_record


def _first_present(record: Mapping[str, Any], keys: tuple[str, ...]) -> Any | None:
    for key in keys:
        if key not in record:
            continue
        value = record[key]
        if _is_missing(value):
            continue
        return value
    return None


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str) and value.strip().lower() in {"", "nan", "none", "null"}:
        return True
    return False


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return None
        return int(value)
    text = str(value).strip()
    if re.fullmatch(r"\d+", text):
        return int(text)
    if re.fullmatch(r"\d+\.0+", text):
        return int(float(text))
    return None


def _record_year(record: Mapping[str, Any], index_year: int | None = None) -> int | None:
    created_at_iso = _first_present(record, ("created_at_iso", "createdAtIso", "createdAtISO"))
    if created_at_iso is not None:
        year = _year_from_iso(str(created_at_iso))
        if year is not None:
            return year

    created_epoch = _first_present(record, ("createdOn", "created_on"))
    if created_epoch is not None:
        year = _year_from_epoch_ms(created_epoch)
        if year is not None:
            return year

    return index_year


def _year_from_iso(value: str) -> int | None:
    if len(value) < 4 or not value[:4].isdigit():
        return None
    return int(value[:4])


def _year_from_epoch_ms(value: Any) -> int | None:
    try:
        timestamp_ms = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(timestamp_ms):
        return None
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).year


def _year_from_index_path(path: Path) -> int | None:
    for part in reversed(path.parts):
        if re.fullmatch(r"\d{4}", part):
            return int(part)
    return None
