from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any, Protocol

from skyportal_corpus.canonical.document import (
    CanonicalDocument,
    iter_real_circulars,
    iter_stratified_circulars,
    render_canonical,
)
from skyportal_corpus.extraction_v2.annotations import EventEvidenceAnnotation
from skyportal_corpus.extraction_v2.event_identity import EventIdentityExtractor, is_canonical_identity
from skyportal_corpus.extraction_v2.localization import LocalizationExtractor
from skyportal_corpus.extraction_v2.redshift import RedshiftExtractor
from skyportal_corpus.extraction_v2.trigger_instrument import TriggerInstrumentExtractor
from skyportal_corpus.extraction_v2.trigger_time import TriggerTimeExtractor


class _Extractor(Protocol):
    extractor_id: str

    def extract(self, doc: CanonicalDocument) -> list[EventEvidenceAnnotation]:
        ...


def run_sweep(
    limit: int = 50,
    per_year: int | None = None,
    circulars: Iterable[Mapping[str, Any]] | None = None,
    extractors: Mapping[str, _Extractor] | None = None,
    only_extractors: list[str] | None = None,
) -> dict[str, Any]:
    extractor_map = _filter_extractor_map(dict(extractors or _active_extractor_map()), only_extractors)
    stats = {
        name: {"n_annotations": 0, "n_circulars_with_at_least_one": 0}
        for name in extractor_map
    }
    annotations: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    circulars_with_errors: set[int | str] = set()
    rendered_text_by_circular_id: dict[str, str] = {}
    circulars_by_year: Counter[str] = Counter()
    extractor_stats_by_year: dict[str, dict[str, dict[str, int]]] = {name: {} for name in extractor_map}
    event_identity_gaps: list[dict[str, Any]] = []
    processed = 0

    circular_iterable = _circular_iterable(limit=limit, per_year=per_year, circulars=circulars)
    for circular in circular_iterable:
        processed += 1
        circular_id = _safe_circular_id(circular)
        year = _safe_year(circular)
        year_key = _year_key(year)
        circulars_by_year[year_key] += 1
        try:
            doc = render_canonical(**_render_canonical_kwargs(circular))
        except Exception as exc:
            errors.append(
                {
                    "circular_id": circular_id,
                    "year": year,
                    "extractor": "render_canonical",
                    "message": str(exc),
                }
            )
            circulars_with_errors.add(circular_id)
            continue

        rendered_text_by_circular_id[str(doc.circular_id)] = doc.rendered_text
        for extractor_name, extractor in extractor_map.items():
            try:
                extracted = extractor.extract(doc)
            except Exception as exc:
                errors.append({"circular_id": circular_id, "year": year, "extractor": extractor_name, "message": str(exc)})
                circulars_with_errors.add(circular_id)
                continue

            if extracted:
                stats[extractor_name]["n_circulars_with_at_least_one"] += 1
                _year_extractor_stats(extractor_stats_by_year, extractor_name, year_key)[
                    "n_circulars_with_at_least_one"
                ] += 1
            elif extractor_name == "event_identity":
                event_identity_gaps.append(
                    {
                        "circular_id": doc.circular_id,
                        "year": year,
                        "subject": doc.subject,
                    }
                )
            stats[extractor_name]["n_annotations"] += len(extracted)
            _year_extractor_stats(extractor_stats_by_year, extractor_name, year_key)["n_annotations"] += len(extracted)
            for annotation in extracted:
                annotation_dict = annotation.model_dump()
                annotation_dict["extractor"] = extractor_name
                annotation_dict["year"] = year
                annotations.append(annotation_dict)

    return {
        "n_circulars_processed": processed,
        "n_circulars_with_errors": len(circulars_with_errors),
        "extractors": stats,
        "by_year": {
            "circulars": dict(sorted(circulars_by_year.items(), key=lambda item: _year_sort_key(item[0]))),
            "extractors": _sorted_extractor_stats_by_year(extractor_stats_by_year),
        },
        "annotations": annotations,
        "errors": errors,
        "gaps": {"event_identity": event_identity_gaps},
        "rendered_text_by_circular_id": rendered_text_by_circular_id,
        "mode": {"limit": limit, "per_year": per_year, "only_extractors": list(extractor_map)},
    }


def flag_suspicious(
    annotations: list[Mapping[str, Any]],
    rendered_text_by_circular_id: Mapping[str, str] | Mapping[int, str] | None = None,
) -> list[dict[str, Any]]:
    suspicious: list[dict[str, Any]] = []
    for annotation in annotations:
        flags: list[str] = []
        text = str(annotation.get("text") or "")
        label = str(annotation.get("label") or "")
        value = str(annotation.get("value") or "")

        if len(text) > 120:
            flags.append("span_too_long")
        if label == "EVENT_IDENTITY" and not _looks_like_event_identity(value):
            flags.append("identity_value_weird")
        if label == "TRIGGER_TIME" and not _looks_like_trigger_value(value):
            flags.append("trigger_value_not_iso")
        if label == "LOCALIZATION" and _localization_out_of_range(value):
            flags.append("localization_out_of_range")
        if bool(annotation.get("needs_review")):
            flags.append("needs_review_true")

        if flags:
            flagged = {
                "circular_id": annotation.get("circular_id"),
                "year": annotation.get("year"),
                "extractor": annotation.get("extractor"),
                "label": label,
                "value": value,
                "text": text,
                "span_start": annotation.get("span_start"),
                "span_end": annotation.get("span_end"),
                "rule_id": annotation.get("rule_id"),
                "flags": flags,
            }
            if rendered_text_by_circular_id is not None:
                _attach_context(flagged, annotation, rendered_text_by_circular_id)
            suspicious.append(flagged)
    return suspicious


def aggregate_by_rule(annotations: list[Mapping[str, Any]]) -> dict[str, int]:
    counts = Counter(str(annotation.get("rule_id") or "unknown") for annotation in annotations)
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def flag_summary(flagged: list[Mapping[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for item in flagged:
        for flag in item.get("flags", []):
            counts[str(flag)] += 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def review_rate(annotations: list[Mapping[str, Any]]) -> dict[str, dict[str, float | int]]:
    totals: dict[str, dict[str, int]] = {}
    for annotation in annotations:
        extractor = str(annotation.get("extractor") or "unknown")
        totals.setdefault(extractor, {"total": 0, "needs_review": 0})
        totals[extractor]["total"] += 1
        if bool(annotation.get("needs_review")):
            totals[extractor]["needs_review"] += 1

    return {
        extractor: {
            "total": values["total"],
            "needs_review": values["needs_review"],
            "percent": round((values["needs_review"] / values["total"]) * 100, 2) if values["total"] else 0.0,
        }
        for extractor, values in sorted(totals.items())
    }


def coverage_stats(sweep_result: Mapping[str, Any]) -> dict[str, dict[str, float | int]]:
    processed = int(sweep_result.get("n_circulars_processed") or 0)
    stats: dict[str, dict[str, float | int]] = {}
    for extractor, values in dict(sweep_result.get("extractors") or {}).items():
        n_circulars = int(dict(values).get("n_circulars_with_at_least_one") or 0)
        stats[str(extractor)] = {
            "n_circulars": n_circulars,
            "percent": round((n_circulars / processed) * 100, 2) if processed else 0.0,
        }
    return stats


def coverage_stats_by_year(sweep_result: Mapping[str, Any]) -> dict[str, dict[str, dict[str, float | int]]]:
    processed_by_year = {
        str(year): int(count)
        for year, count in dict(dict(sweep_result.get("by_year") or {}).get("circulars") or {}).items()
    }
    extractor_years = dict(dict(sweep_result.get("by_year") or {}).get("extractors") or {})
    stats: dict[str, dict[str, dict[str, float | int]]] = {}

    for extractor in dict(sweep_result.get("extractors") or {}):
        stats[str(extractor)] = {}
        values_by_year = dict(extractor_years.get(extractor) or {})
        for year, processed in sorted(processed_by_year.items(), key=lambda item: _year_sort_key(item[0])):
            values = dict(values_by_year.get(year) or {})
            n_annotations = int(values.get("n_annotations") or 0)
            n_circulars = int(values.get("n_circulars_with_at_least_one") or 0)
            stats[str(extractor)][year] = {
                "n_annotations": n_annotations,
                "n_circulars_with_at_least_one": n_circulars,
                "percent": round((n_circulars / processed) * 100, 2) if processed else 0.0,
            }
    return stats


def alert_counts_by_year(flagged: list[Mapping[str, Any]]) -> dict[str, int]:
    counts = Counter(_year_key(item.get("year")) for item in flagged)
    return dict(sorted(counts.items(), key=lambda item: _year_sort_key(item[0])))


def get_active_extractors() -> list[_Extractor]:
    # Fuente única de extractores activos. Para agregar uno nuevo al barrido, añadelo aquí.
    return [
        EventIdentityExtractor(),
        TriggerTimeExtractor(),
        LocalizationExtractor(),
        TriggerInstrumentExtractor(),
        RedshiftExtractor(),
    ]


def _active_extractor_map() -> Mapping[str, _Extractor]:
    return {_extractor_name(extractor): extractor for extractor in get_active_extractors()}


def _extractor_name(extractor: _Extractor) -> str:
    raw_name = extractor.extractor_id
    if raw_name.endswith("-v1"):
        raw_name = raw_name[: -len("-v1")]
    return raw_name.replace("-", "_")


def _filter_extractor_map(
    extractor_map: dict[str, _Extractor],
    only_extractors: list[str] | None,
) -> dict[str, _Extractor]:
    if only_extractors is None:
        return extractor_map

    requested = [_normalize_extractor_selector(item) for item in only_extractors if item.strip()]
    if not requested:
        return extractor_map

    selected: dict[str, _Extractor] = {}
    unmatched = set(requested)
    for short_name, extractor in extractor_map.items():
        aliases = {
            short_name,
            extractor.extractor_id,
            _extractor_name(extractor),
        }
        alias_keys = {_normalize_extractor_selector(alias) for alias in aliases}
        if unmatched & alias_keys:
            selected[short_name] = extractor
            unmatched -= alias_keys

    if unmatched:
        available = ", ".join(sorted(extractor_map))
        unknown = ", ".join(sorted(unmatched))
        raise ValueError(f"Unknown extractor filter(s): {unknown}. Available: {available}")
    return selected


def _normalize_extractor_selector(value: str) -> str:
    return value.strip().replace("-", "_")


def _limit_circulars(circulars: Iterable[Mapping[str, Any]], limit: int) -> Iterable[Mapping[str, Any]]:
    for index, circular in enumerate(circulars):
        if index >= limit:
            break
        yield circular


def _circular_iterable(
    limit: int,
    per_year: int | None,
    circulars: Iterable[Mapping[str, Any]] | None,
) -> Iterable[Mapping[str, Any]]:
    if circulars is None:
        if per_year is not None:
            return iter_stratified_circulars(per_year=per_year)
        return iter_real_circulars(limit=limit)

    if per_year is not None:
        return _stratify_inline_circulars(circulars, per_year=per_year)
    return _limit_circulars(circulars, limit)


def _stratify_inline_circulars(
    circulars: Iterable[Mapping[str, Any]],
    per_year: int,
) -> Iterable[Mapping[str, Any]]:
    if per_year <= 0:
        raise ValueError("per_year must be positive")

    grouped: dict[int, list[dict[str, Any]]] = {}
    for circular in circulars:
        year = _safe_year(circular)
        if year is None:
            continue
        record = dict(circular)
        record["year"] = year
        grouped.setdefault(year, []).append(record)

    for year in sorted(grouped):
        records = sorted(grouped[year], key=_inline_circular_sort_key)
        yield from _uniform_sample(records, per_year)


def _safe_circular_id(circular: Mapping[str, Any]) -> int | str:
    value = circular.get("circular_id")
    if isinstance(value, int):
        return value
    return str(value or "unknown")


def _safe_year(circular: Mapping[str, Any]) -> int | None:
    value = circular.get("year")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r"\d{4}", value.strip()):
        return int(value)

    created_on = str(circular.get("created_on") or "")
    if len(created_on) >= 4 and created_on[:4].isdigit():
        return int(created_on[:4])
    try:
        timestamp_ms = float(created_on)
    except ValueError:
        return None
    return _year_from_epoch_ms(timestamp_ms)


def _year_from_epoch_ms(timestamp_ms: float) -> int | None:
    try:
        from datetime import datetime, timezone

        return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).year
    except (OSError, OverflowError, ValueError):
        return None


def _year_key(year: Any) -> str:
    if isinstance(year, int):
        return str(year)
    if isinstance(year, str) and year:
        return year
    return "unknown"


def _year_sort_key(year: str) -> tuple[int, str]:
    if re.fullmatch(r"\d{4}", year):
        return int(year), year
    return 9999, year


def _render_canonical_kwargs(circular: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {"circular_id", "subject", "body", "event_id", "created_on", "submitter"}
    return {key: value for key, value in dict(circular).items() if key in allowed}


def _year_extractor_stats(
    stats: dict[str, dict[str, dict[str, int]]],
    extractor_name: str,
    year: str,
) -> dict[str, int]:
    return stats.setdefault(extractor_name, {}).setdefault(
        year,
        {"n_annotations": 0, "n_circulars_with_at_least_one": 0},
    )


def _sorted_extractor_stats_by_year(
    stats: dict[str, dict[str, dict[str, int]]],
) -> dict[str, dict[str, dict[str, int]]]:
    return {
        extractor: dict(sorted(values.items(), key=lambda item: _year_sort_key(item[0])))
        for extractor, values in sorted(stats.items())
    }


def _inline_circular_sort_key(circular: Mapping[str, Any]) -> tuple[str, int]:
    created_on = str(circular.get("created_on") or "")
    circular_id = circular.get("circular_id")
    try:
        circular_int = int(circular_id)
    except (TypeError, ValueError):
        circular_int = 0
    return created_on, circular_int


def _uniform_sample(records: list[dict[str, Any]], per_year: int) -> list[dict[str, Any]]:
    total = len(records)
    if total <= per_year:
        return records

    stride = total / per_year
    selected_indices = [min(total - 1, int((index + 0.5) * stride)) for index in range(per_year)]
    return [records[index] for index in selected_indices]


def _looks_like_event_identity(value: str) -> bool:
    return is_canonical_identity(value)


def _looks_like_trigger_value(value: str) -> bool:
    if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", value):
        return True
    if re.match(r"^MJD\s+\d{5}(?:\.\d+)?$", value):
        return True

    clock_match = re.match(
        r"^(?P<hour>\d{1,2}):(?P<minute>\d{2})(?::(?P<second>\d{2}(?:\.\d+)?))?(?:\s?(?:UT|UTC))?$",
        value,
    )
    if clock_match is None:
        return False

    hour = int(clock_match.group("hour"))
    minute = int(clock_match.group("minute"))
    second = float(clock_match.group("second") or "0")
    return 0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second < 60


def _localization_out_of_range(value: str) -> bool:
    match = re.search(r"RA=([+\-]?\d+(?:\.\d+)?),\s*Dec=([+\-]?\d+(?:\.\d+)?)", value)
    if match is None:
        return False
    try:
        ra = float(match.group(1))
        dec = float(match.group(2))
    except ValueError:
        return False
    return not (0 <= ra <= 360 and -90 <= dec <= 90)


def _attach_context(
    flagged: dict[str, Any],
    annotation: Mapping[str, Any],
    rendered_text_by_circular_id: Mapping[str, str] | Mapping[int, str],
) -> None:
    rendered_text = _rendered_text_for_annotation(annotation, rendered_text_by_circular_id)
    if rendered_text is None:
        return

    try:
        start = int(annotation.get("span_start"))
        end = int(annotation.get("span_end"))
    except (TypeError, ValueError):
        return
    if not (0 <= start < end <= len(rendered_text)):
        return

    flagged["context_window"] = _context_window(rendered_text, start, end)
    flagged["source_line"] = _source_line(rendered_text, start)


def _rendered_text_for_annotation(
    annotation: Mapping[str, Any],
    rendered_text_by_circular_id: Mapping[str, str] | Mapping[int, str],
) -> str | None:
    circular_id = annotation.get("circular_id")
    if circular_id in rendered_text_by_circular_id:
        return rendered_text_by_circular_id[circular_id]  # type: ignore[index]
    return rendered_text_by_circular_id.get(str(circular_id))  # type: ignore[arg-type]


def _context_window(rendered_text: str, start: int, end: int, radius: int = 120) -> str:
    window_start = max(0, start - radius)
    window_end = min(len(rendered_text), end + radius)
    marked = (
        f"{rendered_text[window_start:start]}"
        f"⟦{rendered_text[start:end]}⟧"
        f"{rendered_text[end:window_end]}"
    )
    return _display_text(marked)


def _source_line(rendered_text: str, start: int) -> str:
    line_start = rendered_text.rfind("\n", 0, start) + 1
    line_end = rendered_text.find("\n", start)
    if line_end == -1:
        line_end = len(rendered_text)
    return _display_text(rendered_text[line_start:line_end])


def _display_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ⏎ ")
