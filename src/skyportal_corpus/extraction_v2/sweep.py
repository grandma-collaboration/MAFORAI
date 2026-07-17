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
from skyportal_corpus.extraction_v2.classification_interpretation import (
    CLASSIFICATION_SIGNAL_RE,
    ClassificationInterpretationExtractor,
)
from skyportal_corpus.extraction_v2.counterpart_association import (
    COUNTERPART_SIGNAL_RE,
    CounterpartAssociationExtractor,
)
from skyportal_corpus.extraction_v2.duration import DurationExtractor
from skyportal_corpus.extraction_v2.event_identity import EventIdentityExtractor, is_canonical_identity
from skyportal_corpus.extraction_v2.high_energy import HighEnergyPropertyExtractor
from skyportal_corpus.extraction_v2.host_context import (
    HOST_CONTEXT_SIGNAL_RE,
    HostContextExtractor,
)
from skyportal_corpus.extraction_v2.lightcurve_evolution import (
    LIGHTCURVE_SIGNAL_RE,
    LightcurveEvolutionExtractor,
)
from skyportal_corpus.extraction_v2.localization import LocalizationExtractor
from skyportal_corpus.extraction_v2.negative_statement import (
    NEGATIVE_SIGNAL_RE,
    NegativeStatementExtractor,
)
from skyportal_corpus.extraction_v2.redshift import RedshiftExtractor
from skyportal_corpus.extraction_v2.spectroscopy import (
    SPECTROSCOPY_SIGNAL_RE,
    SpectroscopyExtractor,
)
from skyportal_corpus.extraction_v2.trigger_instrument import TriggerInstrumentExtractor
from skyportal_corpus.extraction_v2.trigger_time import TriggerTimeExtractor


_DURATION_GAP_SIGNAL_RE = re.compile(
    r"\b(?:T90|T50|burst\s+duration|duration|lasted)\b",
    re.IGNORECASE,
)
_HIGH_ENERGY_GAP_SIGNAL_RE = re.compile(
    r"\b(?:"
    r"fluence|E[_ ]?peak|peak\s+flux|power[- ]law\s+index|photon\s+index|"
    r"E[_ ]?iso|cutoff\s+energy|Band\s+function|spectral\s+index"
    r")\b",
    re.IGNORECASE,
)
_PRIMARY_NUMBER_RE = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)")
_SCIENTIFIC_EXPONENT_RE = re.compile(
    r"(?:"
    r"[Ee]\s*(?P<direct>[+-]?\d+)|"
    r"[xX*×]\s*10\s*(?:\^\s*)?\(?\s*(?P<times_ten>[+-]?\d+)\s*\)?|"
    r"\*\s*[Ee]\s*(?P<star_e>[+-]?\d+)"
    r")",
)
DIMENSIONLESS_RULES = frozenset(
    {
        "high_energy.powerlaw_index",
        "high_energy.photon_index",
        "high_energy.spectral_index",
        "high_energy.alpha",
        "high_energy.beta",
    }
)


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
    duration_gaps: list[dict[str, Any]] = []
    high_energy_gaps: list[dict[str, Any]] = []
    negative_statement_gaps: list[dict[str, Any]] = []
    lightcurve_evolution_gaps: list[dict[str, Any]] = []
    counterpart_association_gaps: list[dict[str, Any]] = []
    classification_interpretation_gaps: list[dict[str, Any]] = []
    host_context_gaps: list[dict[str, Any]] = []
    spectroscopy_gaps: list[dict[str, Any]] = []
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
            elif extractor_name == "duration":
                gap = _signal_gap(doc, year, _DURATION_GAP_SIGNAL_RE)
                if gap is not None:
                    duration_gaps.append(gap)
            elif extractor_name == "high_energy":
                gap = _signal_gap(doc, year, _HIGH_ENERGY_GAP_SIGNAL_RE)
                if gap is not None:
                    high_energy_gaps.append(gap)
            elif extractor_name == "negative_statement":
                gap = _signal_gap(doc, year, NEGATIVE_SIGNAL_RE)
                if gap is not None:
                    negative_statement_gaps.append(gap)
            elif extractor_name == "lightcurve_evolution":
                gap = _signal_gap(doc, year, LIGHTCURVE_SIGNAL_RE)
                if gap is not None:
                    lightcurve_evolution_gaps.append(gap)
            elif extractor_name == "counterpart_association":
                gap = _signal_gap(doc, year, COUNTERPART_SIGNAL_RE)
                if gap is not None:
                    counterpart_association_gaps.append(gap)
            elif extractor_name == "classification_interpretation":
                gap = _signal_gap(doc, year, CLASSIFICATION_SIGNAL_RE)
                if gap is not None:
                    classification_interpretation_gaps.append(gap)
            elif extractor_name == "host_context":
                gap = _signal_gap(doc, year, HOST_CONTEXT_SIGNAL_RE)
                if gap is not None:
                    host_context_gaps.append(gap)
            elif extractor_name == "spectroscopy":
                gap = _signal_gap(doc, year, SPECTROSCOPY_SIGNAL_RE)
                if gap is not None:
                    spectroscopy_gaps.append(gap)
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
        "gaps": {
            "event_identity": event_identity_gaps,
            "duration": duration_gaps,
            "high_energy": high_energy_gaps,
            "negative_statement": negative_statement_gaps,
            "lightcurve_evolution": lightcurve_evolution_gaps,
            "counterpart_association": counterpart_association_gaps,
            "classification_interpretation": classification_interpretation_gaps,
            "host_context": host_context_gaps,
            "spectroscopy": spectroscopy_gaps,
        },
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
        flags.extend(_scientific_anomaly_flags(annotation))
        if bool(annotation.get("needs_review")):
            flags.append("needs_review_true")

        if flags:
            flagged = {
                "circular_id": annotation.get("circular_id"),
                "year": annotation.get("year"),
                "extractor": annotation.get("extractor"),
                "label": label,
                "value": value,
                "unit": annotation.get("unit"),
                "comment": annotation.get("comment"),
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


def samples_by_rule(
    annotations: list[Mapping[str, Any]],
    rendered_text_by_circular_id: Mapping[str, str] | Mapping[int, str],
    max_per_rule: int = 5,
) -> dict[str, list[dict[str, Any]]]:
    """Return deterministic duration/high-energy examples with source context."""

    samples: dict[str, list[dict[str, Any]]] = {}
    ordered = sorted(
        annotations,
        key=lambda annotation: (
            str(annotation.get("rule_id") or "unknown"),
            _safe_int(annotation.get("circular_id")),
            _safe_int(annotation.get("span_start")),
        ),
    )
    for annotation in ordered:
        extractor = str(annotation.get("extractor") or "")
        if extractor not in {"duration", "high_energy"}:
            continue
        rule_id = str(annotation.get("rule_id") or "unknown")
        rule_samples = samples.setdefault(rule_id, [])
        if len(rule_samples) >= max_per_rule:
            continue
        rendered_text = _rendered_text_for_annotation(annotation, rendered_text_by_circular_id)
        if rendered_text is None:
            continue
        try:
            start = int(annotation.get("span_start"))
            end = int(annotation.get("span_end"))
        except (TypeError, ValueError):
            continue
        if not (0 <= start < end <= len(rendered_text)):
            continue
        rule_samples.append(
            {
                "circular_id": annotation.get("circular_id"),
                "year": annotation.get("year"),
                "extractor": extractor,
                "label": annotation.get("label"),
                "value": annotation.get("value"),
                "unit": annotation.get("unit"),
                "comment": annotation.get("comment"),
                "text": annotation.get("text"),
                "source_line": _source_line(rendered_text, start),
                "context_window": _context_window(rendered_text, start, end, radius=80),
            }
        )
    return dict(sorted(samples.items()))


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
    # Single source of truth for active extractors. Add new sweep extractors here.
    return [
        EventIdentityExtractor(),
        TriggerTimeExtractor(),
        LocalizationExtractor(),
        TriggerInstrumentExtractor(),
        RedshiftExtractor(),
        DurationExtractor(),
        HighEnergyPropertyExtractor(),
        NegativeStatementExtractor(),
        LightcurveEvolutionExtractor(),
        CounterpartAssociationExtractor(),
        ClassificationInterpretationExtractor(),
        HostContextExtractor(),
        SpectroscopyExtractor(),
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


def _signal_gap(
    doc: CanonicalDocument,
    year: int | None,
    pattern: re.Pattern[str],
) -> dict[str, Any] | None:
    search_ranges = [
        (segment.start, segment.end)
        for segment in doc.segments
        if segment.name == "body"
    ]
    search_ranges.append((0, len(doc.rendered_text)))
    for range_start, range_end in search_ranges:
        match = pattern.search(doc.rendered_text, range_start, range_end)
        if match is None:
            continue
        return {
            "circular_id": doc.circular_id,
            "year": year,
            "subject": doc.subject,
            "signal": match.group(0),
            "source_line": _source_line(doc.rendered_text, match.start()),
        }
    return None


def _scientific_anomaly_flags(annotation: Mapping[str, Any]) -> list[str]:
    extractor = str(annotation.get("extractor") or "")
    value = str(annotation.get("value") or "")
    unit = str(annotation.get("unit") or "").strip()
    rule_id = str(annotation.get("rule_id") or "")
    flags: list[str] = []

    if extractor == "duration":
        seconds = _duration_seconds(value, unit)
        if seconds is not None and not 0.001 <= seconds <= 10000:
            flags.append("duration_out_of_range")
        if not unit:
            flags.append("missing_unit")
        return flags

    if extractor != "high_energy":
        return flags

    primary_value = _primary_scientific_value(value)
    if primary_value is not None and _high_energy_value_out_of_range(
        primary_value,
        unit,
        rule_id,
    ):
        flags.append("high_energy_implausible")
    if not unit and rule_id not in DIMENSIONLESS_RULES:
        flags.append("missing_unit")
    return flags


def _duration_seconds(value: str, unit: str) -> float | None:
    numeric = _primary_scientific_value(value)
    if numeric is None or not unit:
        return None
    normalized_unit = unit.lower().strip().rstrip(".")
    if normalized_unit in {"ms", "msec", "millisecond", "milliseconds"}:
        return numeric / 1000
    if normalized_unit in {"s", "sec", "secs", "second", "seconds"}:
        return numeric
    return None


def _high_energy_value_out_of_range(value: float, unit: str, rule_id: str) -> bool:
    if rule_id == "high_energy.epeak":
        value_kev = _energy_to_kev(value, unit)
        return value_kev is not None and not 1 <= value_kev <= 100000
    if rule_id == "high_energy.fluence":
        return not 1e-9 <= abs(value) <= 1e-2
    if rule_id in DIMENSIONLESS_RULES:
        return not -10 <= value <= 5
    if rule_id == "high_energy.eiso":
        return not 1e45 <= abs(value) <= 1e56
    return False


def _energy_to_kev(value: float, unit: str) -> float | None:
    normalized_unit = unit.lower().strip()
    if normalized_unit == "kev":
        return value
    if normalized_unit == "mev":
        return value * 1000
    if normalized_unit == "gev":
        return value * 1_000_000
    return None


def _primary_scientific_value(value: str) -> float | None:
    payload = value.split("=", 1)[1] if "=" in value else value
    number_match = _PRIMARY_NUMBER_RE.search(payload)
    if number_match is None:
        return None
    try:
        numeric = float(number_match.group(0))
    except ValueError:
        return None

    exponent_match = _SCIENTIFIC_EXPONENT_RE.search(payload, number_match.end())
    if exponent_match is None:
        return numeric
    exponent_raw = next(
        (
            exponent_match.group(name)
            for name in ("direct", "times_ten", "star_e")
            if exponent_match.group(name) is not None
        ),
        None,
    )
    if exponent_raw is None:
        return numeric
    try:
        return numeric * (10.0 ** int(exponent_raw))
    except OverflowError:
        return float("inf") if numeric >= 0 else float("-inf")


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


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
