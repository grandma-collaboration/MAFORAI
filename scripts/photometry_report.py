from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from skyportal_corpus.canonical.document import (  # noqa: E402
    iter_real_circulars,
    iter_stratified_circulars,
    render_canonical,
)
from skyportal_corpus.extraction_v2.photometry_rows import (  # noqa: E402
    CLEAR_UNFILTERED_BANDS,
    is_photometry_table,
    parse_table_to_measurements,
)
from skyportal_corpus.extraction_v2.photometry_prose import (  # noqa: E402
    ProsePhotometryExtractor,
    is_optical_circular,
)
from skyportal_corpus.extraction_v2.photometry_tables import detect_table_blocks  # noqa: E402


OUT_PATH = PROJECT_ROOT / "data" / "interim" / "gcn" / "photometry" / "photometry_report.json"
MIN_REPORT_YEAR = 2023
PROSE_TABLE_OVERLAP_COMMENT = (
    "Prose measurement in a circular that also has a photometry table; likely a "
    "summary of the table -- verify whether it is an independent measurement."
)


def main() -> int:
    mode = parse_mode(sys.argv)
    result = collect_photometry_measurements(
        limit=int(mode["limit"]),
        per_year=_optional_int(mode["per_year"]),
        keywords=_optional_str_list(mode["keywords"]),
    )
    aggregates = aggregate_measurements(result["measurements"])
    aggregates["by_year"] = aggregate_by_year(
        result["measurements"],
        result["year_stats"],
    )
    problems = find_measurement_problems(result["measurements"])
    samples = build_samples(
        [item for item in result["measurements"] if item.get("source") == "table"]
    )
    prose_samples = build_prose_samples(result["measurements"])
    run_meta = build_run_meta(
        mode=str(mode["label"]),
        n_circulars_processed=int(result["n_circulars_processed"]),
        total_measurements=len(result["measurements"]),
        total_problems=len(problems),
        years_covered=result["years_covered"],
    )

    report = {
        "run_meta": run_meta,
        "mode": mode,
        "summary": {
            "n_circulars_processed": result["n_circulars_processed"],
            "n_circulars_with_tables": result["n_circulars_with_tables"],
            "n_circulars_with_prose": result["n_circulars_with_prose"],
            "n_measurements": len(result["measurements"]),
            "years_covered": result["years_covered"],
        },
        "aggregates": aggregates,
        "samples": samples,
        "prose_samples": prose_samples,
        "optical_prefilter": result["optical_prefilter"],
        "source_overlaps": result["source_overlaps"],
        "problems": problems,
        "possibly_uncovered": {
            "tables_with_zero_measurements": result["tables_with_zero_measurements"],
            "photometry_like_without_tables": result["photometry_like_without_tables"],
        },
        "measurements": result["measurements"],
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(render_report(mode, report))
    print(f"\nJSON: {OUT_PATH.relative_to(PROJECT_ROOT)}")
    return 0


def parse_mode(argv: list[str]) -> dict[str, int | str | list[str] | None]:
    limit = 300
    per_year: int | None = None
    keywords: list[str] | None = None
    mode_seen = False

    for argument in argv[1:]:
        if argument.startswith("keywords="):
            raw_keywords = argument.removeprefix("keywords=")
            keywords = [item.strip() for item in raw_keywords.split(",") if item.strip()]
            if not keywords:
                raise SystemExit("keywords= requires at least one keyword")
            continue
        if argument.startswith("limit="):
            if mode_seen:
                raise SystemExit("Use either limit=N or per_year=N, not both")
            limit = _parse_positive_int(argument.removeprefix("limit="), name="limit")
            per_year = None
            mode_seen = True
            continue
        if argument.startswith("per_year="):
            if mode_seen:
                raise SystemExit("Use either limit=N or per_year=N, not both")
            per_year = _parse_positive_int(argument.removeprefix("per_year="), name="per_year")
            mode_seen = True
            continue
        if mode_seen:
            raise SystemExit("Use either limit=N or per_year=N, not both")
        limit = _parse_positive_int(argument, name="limit")
        per_year = None
        mode_seen = True

    base_label = f"per_year={per_year}" if per_year is not None else f"limit={limit}"
    keyword_label = ",".join(keywords) if keywords else "all"
    label = f"{base_label} keywords={keyword_label}" if keywords else base_label
    return {"limit": limit, "per_year": per_year, "keywords": keywords, "label": label}


def collect_photometry_measurements(
    limit: int = 300,
    per_year: int | None = None,
    keywords: list[str] | None = None,
) -> dict[str, Any]:
    records = (
        iter_stratified_circulars(per_year=per_year, min_year=MIN_REPORT_YEAR)
        if per_year is not None
        else iter_real_circulars(min_year=MIN_REPORT_YEAR, limit=None)
    )
    measurements: list[dict[str, Any]] = []
    prose_extractor = ProsePhotometryExtractor()
    n_processed = 0
    circulars_with_tables: set[int] = set()
    circulars_with_prose: set[int] = set()
    year_stats: dict[int, dict[str, int]] = defaultdict(
        lambda: {
            "processed": 0,
            "with_tables": 0,
            "with_prose": 0,
            "optical_prefilter_passed": 0,
            "optical_prefilter_discarded": 0,
        }
    )
    tables_with_zero_measurements: list[dict[str, Any]] = []
    photometry_like_without_tables: list[dict[str, Any]] = []

    for circular in records:
        if keywords and not _matches_keywords(circular, keywords):
            continue
        n_processed += 1
        year = circular.get("year") or _year_from_created_on(circular.get("created_on"))
        year_int = int(year) if year is not None else 0
        year_stats[year_int]["processed"] += 1
        doc = _render_circular(circular)
        blocks = detect_table_blocks(doc.rendered_text)
        has_table_measurements = False
        if blocks:
            circulars_with_tables.add(int(circular["circular_id"]))
            year_stats[year_int]["with_tables"] += 1
        elif _suggests_photometry(circular):
            photometry_like_without_tables.append(
                {
                    "circular_id": circular.get("circular_id"),
                    "year": year_int or None,
                    "subject": circular.get("subject", ""),
                    "reason": "subject/body suggests photometry but no table block was detected",
                }
            )
        for block in blocks:
            block_measurements = parse_table_to_measurements(block, doc)
            if block_measurements:
                has_table_measurements = True
            if not block_measurements:
                tables_with_zero_measurements.append(
                    {
                        "circular_id": circular.get("circular_id"),
                        "year": year_int or None,
                        "subject": circular.get("subject", ""),
                        "table_family": block.delimiter_type,
                        "raw_header": block.raw_header or "",
                        "reason": (
                            "is_photometry_table False"
                            if not is_photometry_table(block)
                            else "photometry-like table produced zero row measurements"
                        ),
                    }
                )
            for annotation in block_measurements:
                item = annotation.model_dump()
                item.update(
                    {
                        "source": "table",
                        "year": year_int or None,
                        "subject": circular.get("subject", ""),
                        "table_family": block.delimiter_type,
                        "source_family": classify_source_family(circular, block.context_before),
                        "source_row": annotation.text,
                        "context": _context_excerpt(block.context_before),
                        "verify": annotation.verify(doc.rendered_text),
                        "system_source": system_source(item),
                    }
                )
                measurements.append(item)

        optical_passed = is_optical_circular(doc.rendered_text)
        prefilter_key = "optical_prefilter_passed" if optical_passed else "optical_prefilter_discarded"
        year_stats[year_int][prefilter_key] += 1
        prose_annotations = prose_extractor.extract(doc) if optical_passed else []
        if prose_annotations:
            circular_id = int(circular["circular_id"])
            circulars_with_prose.add(circular_id)
            year_stats[year_int]["with_prose"] += 1
        for annotation in prose_annotations:
            item = annotation.model_dump()
            item.update(
                {
                    "source": "prose",
                    "year": year_int or None,
                    "subject": circular.get("subject", ""),
                    "table_family": None,
                    "source_family": classify_source_family(circular),
                    "source_row": annotation.text,
                    "context": _span_context(
                        doc.rendered_text,
                        annotation.span_start,
                        annotation.span_end,
                    ),
                    "verify": annotation.verify(doc.rendered_text),
                    "system_source": system_source(item),
                }
            )
            if has_table_measurements:
                item = mark_prose_table_overlap(item)
            measurements.append(item)
        if per_year is None and n_processed >= limit:
            break

    source_overlaps = find_source_overlaps(measurements)
    optical_by_year = {
        str(year): {
            "passed": int(values.get("optical_prefilter_passed", 0)),
            "discarded": int(values.get("optical_prefilter_discarded", 0)),
        }
        for year, values in sorted(year_stats.items())
        if year
    }

    return {
        "n_circulars_processed": n_processed,
        "n_circulars_with_tables": len(circulars_with_tables),
        "n_circulars_with_prose": len(circulars_with_prose),
        "year_stats": {str(year): values for year, values in sorted(year_stats.items()) if year},
        "years_covered": [year for year in sorted(year_stats) if year],
        "tables_with_zero_measurements": tables_with_zero_measurements,
        "photometry_like_without_tables": photometry_like_without_tables,
        "optical_prefilter": {
            "passed": sum(values["passed"] for values in optical_by_year.values()),
            "discarded": sum(values["discarded"] for values in optical_by_year.values()),
            "by_year": optical_by_year,
        },
        "source_overlaps": source_overlaps,
        "measurements": measurements,
    }


def aggregate_measurements(measurements: list[dict[str, Any]]) -> dict[str, Any]:
    source = Counter(_value(item.get("source")) for item in measurements)
    measurement_type = Counter(_value(item.get("measurement_type")) for item in measurements)
    table_family = Counter(
        _value(item.get("table_family"))
        for item in measurements
        if item.get("source") == "table"
    )
    photometric_system = Counter(_value(item.get("photometric_system")) for item in measurements)
    system_sources = Counter(system_source(item) for item in measurements)
    obs_time_type = Counter(_value(item.get("obs_time_type")) for item in measurements)
    obs_time_reference = Counter(_value(item.get("obs_time_reference")) for item in measurements)
    bands = Counter(_value(item.get("photometric_band")) for item in measurements if item.get("photometric_band"))
    limit_sigma = Counter()
    for item in measurements:
        if item.get("measurement_type") != "upper_limit":
            continue
        sigma = str(item.get("limit_sigma") or "").strip()
        if sigma == "3":
            limit_sigma["3"] += 1
        elif sigma == "5":
            limit_sigma["5"] += 1
        elif sigma:
            limit_sigma["other"] += 1
        else:
            limit_sigma["without_sigma"] += 1

    review_reasons: Counter[str] = Counter()
    for item in measurements:
        if item.get("needs_review"):
            for reason in _review_reason_parts(item):
                review_reasons[reason] += 1

    prose = [item for item in measurements if item.get("source") == "prose"]
    prose_review_reasons: Counter[str] = Counter()
    for item in prose:
        if item.get("needs_review"):
            prose_review_reasons.update(_review_reason_parts(item))

    return {
        "by_source": dict(sorted(source.items())),
        "by_table_family": dict(sorted(table_family.items())),
        "by_measurement_type": dict(sorted(measurement_type.items())),
        "by_limit_sigma": {
            key: limit_sigma.get(key, 0)
            for key in ("3", "5", "other", "without_sigma")
        },
        "by_photometric_system": dict(sorted(photometric_system.items())),
        "by_system_source": dict(sorted(system_sources.items())),
        "by_obs_time_type": dict(sorted(obs_time_type.items())),
        "by_obs_time_reference": dict(sorted(obs_time_reference.items())),
        "top_bands": dict(bands.most_common(20)),
        "review": {
            "total": sum(1 for item in measurements if item.get("needs_review")),
            "percent": _percent(sum(1 for item in measurements if item.get("needs_review")), len(measurements)),
            "by_reason": dict(review_reasons.most_common()),
        },
        "prose": {
            "total": len(prose),
            "by_measurement_type": dict(
                sorted(Counter(_value(item.get("measurement_type")) for item in prose).items())
            ),
            "by_rule_id": dict(Counter(_value(item.get("rule_id")) for item in prose).most_common()),
            "by_band": dict(
                Counter(_value(item.get("photometric_band")) for item in prose).most_common(20)
            ),
            "by_photometric_system": dict(
                sorted(Counter(_value(item.get("photometric_system")) for item in prose).items())
            ),
            "review": {
                "total": sum(1 for item in prose if item.get("needs_review")),
                "percent": _percent(sum(1 for item in prose if item.get("needs_review")), len(prose)),
                "by_reason": dict(prose_review_reasons.most_common()),
            },
        },
    }


def aggregate_by_year(
    measurements: list[dict[str, Any]],
    year_stats: dict[str, dict[str, int]],
) -> dict[str, Any]:
    """Aggregate the photometry report by year for stratified sweeps."""

    measurement_counts = Counter(str(item.get("year") or "unknown") for item in measurements)
    table_family: dict[str, Counter[str]] = defaultdict(Counter)
    measurement_type: dict[str, Counter[str]] = defaultdict(Counter)
    photometric_system: dict[str, Counter[str]] = defaultdict(Counter)
    source: dict[str, Counter[str]] = defaultdict(Counter)
    review: dict[str, dict[str, float | int]] = {}

    for item in measurements:
        year = str(item.get("year") or "unknown")
        if item.get("source") == "table":
            table_family[year][_value(item.get("table_family"))] += 1
        source[year][_value(item.get("source"))] += 1
        measurement_type[year][_value(item.get("measurement_type"))] += 1
        photometric_system[year][_value(item.get("photometric_system"))] += 1

    all_years = sorted(set(year_stats) | set(measurement_counts), key=lambda value: (value == "unknown", value))
    circulars: dict[str, dict[str, int]] = {}
    for year in all_years:
        stats = year_stats.get(year, {})
        total = measurement_counts.get(year, 0)
        needs_review = sum(
            1 for item in measurements if str(item.get("year") or "unknown") == year and item.get("needs_review")
        )
        circulars[year] = {
            "processed": int(stats.get("processed", 0)),
            "with_tables": int(stats.get("with_tables", 0)),
            "with_prose": int(stats.get("with_prose", 0)),
            "measurements": int(total),
        }
        review[year] = {
            "total": int(total),
            "needs_review": int(needs_review),
            "percent": _percent(needs_review, total),
        }

    return {
        "circulars": circulars,
        "by_table_family": {year: dict(counter) for year, counter in sorted(table_family.items())},
        "by_source": {year: dict(counter) for year, counter in sorted(source.items())},
        "by_measurement_type": {year: dict(counter) for year, counter in sorted(measurement_type.items())},
        "by_photometric_system": {year: dict(counter) for year, counter in sorted(photometric_system.items())},
        "review": review,
    }


def find_measurement_problems(measurements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    problems: list[dict[str, Any]] = []
    for item in measurements:
        flags: list[str] = []
        magnitude = _principal_float(item.get("magnitude_or_limit"))
        if magnitude is not None and not 5 <= magnitude <= 30:
            flags.append("magnitude_out_of_range")
        if item.get("photometric_system") in {None, "", "unknown"} and not _is_clear_unfiltered_band(
            item.get("photometric_band")
        ):
            flags.append("system_unknown")
        if not item.get("obs_time_type"):
            flags.append("time_without_subtype")
        if not item.get("photometric_band"):
            flags.append("band_empty")
        if item.get("verify") is False:
            flags.append("verify_false")
        if flags:
            problems.append(
                {
                    "circular_id": item.get("circular_id"),
                    "source": item.get("source"),
                    "flags": flags,
                    "measurement_type": item.get("measurement_type"),
                    "magnitude_or_limit": item.get("magnitude_or_limit"),
                    "magnitude_error": item.get("magnitude_error"),
                    "photometric_band": item.get("photometric_band"),
                    "photometric_system": item.get("photometric_system"),
                    "obs_time_raw": item.get("obs_time_raw"),
                    "source_row": item.get("source_row") or item.get("text"),
                    "context": item.get("context", ""),
                }
            )
    return problems


def build_samples(measurements: list[dict[str, Any]], max_per_group: int = 5) -> dict[str, dict[str, list[dict[str, Any]]]]:
    samples: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for item in measurements:
        family = str(item.get("source_family") or "OTHER")
        measurement_type = str(item.get("measurement_type") or "unknown")
        bucket = samples[family][measurement_type]
        if len(bucket) >= max_per_group:
            continue
        bucket.append(_sample_item(item))
    return {family: dict(values) for family, values in samples.items()}


def build_prose_samples(
    measurements: list[dict[str, Any]],
    max_per_rule: int = 5,
) -> dict[str, list[dict[str, Any]]]:
    samples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in measurements:
        if item.get("source") != "prose":
            continue
        rule_id = _value(item.get("rule_id"))
        if len(samples[rule_id]) >= max_per_rule:
            continue
        samples[rule_id].append(_sample_item(item))
    return dict(sorted(samples.items()))


def find_source_overlaps(measurements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return circulars with both table and prose measurements."""

    grouped: dict[int, dict[str, Any]] = {}
    for item in measurements:
        circular_id = int(item["circular_id"])
        entry = grouped.setdefault(
            circular_id,
            {
                "circular_id": circular_id,
                "year": item.get("year"),
                "subject": item.get("subject", ""),
                "n_table_measurements": 0,
                "n_prose_measurements": 0,
            },
        )
        if item.get("source") == "table":
            entry["n_table_measurements"] += 1
        elif item.get("source") == "prose":
            entry["n_prose_measurements"] += 1
    return sorted(
        (
            entry
            for entry in grouped.values()
            if entry["n_table_measurements"] and entry["n_prose_measurements"]
        ),
        key=lambda entry: int(entry["circular_id"]),
    )


def mark_prose_table_overlap(item: dict[str, Any]) -> dict[str, Any]:
    """Mark report-level prose that may summarize a table in the same circular."""

    marked = dict(item)
    existing_comment = str(marked.get("comment") or "").strip()
    if PROSE_TABLE_OVERLAP_COMMENT not in existing_comment:
        marked["comment"] = " ".join(
            value for value in (existing_comment, PROSE_TABLE_OVERLAP_COMMENT) if value
        )
    marked["needs_review"] = True
    confidence = marked.get("confidence")
    if isinstance(confidence, (int, float)):
        marked["confidence"] = min(float(confidence), 0.65)
    provenance = list(marked.get("provenance_inherited") or [])
    if "overlap_with_photometry_table" not in provenance:
        provenance.append("overlap_with_photometry_table")
    marked["provenance_inherited"] = provenance
    return marked


def render_report(mode: dict[str, Any], report: dict[str, Any]) -> str:
    summary = report["summary"]
    aggregates = report["aggregates"]
    samples = report["samples"]
    prose_samples = report.get("prose_samples", {})
    problems = report["problems"]
    uncovered = report.get("possibly_uncovered", {})
    optical_prefilter = report.get("optical_prefilter", {})
    source_overlaps = report.get("source_overlaps", [])
    lines: list[str] = []

    lines.append("GLOBAL SUMMARY")
    lines.append(f"  mode: {mode['label']}")
    lines.append(f"  years covered: {', '.join(str(year) for year in summary.get('years_covered', []))}")
    lines.append(f"  circulars processed: {summary['n_circulars_processed']}")
    lines.append(f"  circulars with detected tables: {summary['n_circulars_with_tables']}")
    lines.append(f"  circulars with prose measurements: {summary.get('n_circulars_with_prose', 0)}")
    lines.append(f"  total measurements: {summary['n_measurements']}")

    lines.append("")
    lines.append("BY SOURCE")
    _append_counter(lines, aggregates.get("by_source", {}))

    lines.append("")
    lines.append("MEASUREMENTS BY TABLE FAMILY")
    _append_counter(lines, aggregates["by_table_family"])

    lines.append("")
    lines.append("BY MEASUREMENT TYPE")
    _append_counter(lines, aggregates["by_measurement_type"])

    lines.append("")
    lines.append("BY LIMIT SIGMA")
    _append_counter(lines, aggregates.get("by_limit_sigma", {}))

    lines.append("")
    lines.append("BY PHOTOMETRIC SYSTEM")
    _append_counter(lines, aggregates["by_photometric_system"])
    lines.append("  sources:")
    _append_counter(lines, aggregates["by_system_source"], indent="    ")

    lines.append("")
    lines.append("BY OBSERVATION TIME")
    lines.append("  type:")
    _append_counter(lines, aggregates["by_obs_time_type"], indent="    ")
    lines.append("  reference:")
    _append_counter(lines, aggregates["by_obs_time_reference"], indent="    ")

    lines.append("")
    lines.append("TOP PHOTOMETRIC BANDS")
    _append_counter(lines, aggregates["top_bands"])

    lines.append("")
    lines.append("REVIEW RATE")
    review = aggregates["review"]
    lines.append(f"  needs_review: {review['total']} ({review['percent']:.2f}%)")
    if review["by_reason"]:
        _append_counter(lines, review["by_reason"], indent="  reason ")
    else:
        lines.append("  reason (none)")

    lines.append("")
    lines.append("PROSE PHOTOMETRY")
    prose = aggregates.get("prose", {})
    lines.append(f"  total: {prose.get('total', 0)}")
    lines.append("  by measurement type:")
    _append_counter(lines, prose.get("by_measurement_type", {}), indent="    ")
    lines.append("  by rule_id:")
    _append_counter(lines, prose.get("by_rule_id", {}), indent="    ")
    lines.append("  by band:")
    _append_counter(lines, prose.get("by_band", {}), indent="    ")
    lines.append("  by photometric system:")
    _append_counter(lines, prose.get("by_photometric_system", {}), indent="    ")
    prose_review = prose.get("review", {})
    lines.append(
        f"  review: {prose_review.get('total', 0)}/{prose.get('total', 0)} "
        f"({float(prose_review.get('percent', 0.0)):.2f}%)"
    )
    _append_counter(lines, prose_review.get("by_reason", {}), indent="    reason ")

    lines.append("")
    lines.append("OPTICAL PREFILTER")
    lines.append(f"  passed: {optical_prefilter.get('passed', 0)}")
    lines.append(f"  discarded: {optical_prefilter.get('discarded', 0)}")
    lines.append("  by year:")
    for year, values in optical_prefilter.get("by_year", {}).items():
        lines.append(
            f"    {year}: passed={values.get('passed', 0)} "
            f"discarded={values.get('discarded', 0)}"
        )

    _append_by_year_sections(lines, aggregates.get("by_year", {}))

    lines.append("")
    lines.append("TABLE/PROSE OVERLAP")
    lines.append(f"  circulars with both sources: {len(source_overlaps)}")
    if source_overlaps:
        for item in source_overlaps[:15]:
            lines.append(
                f"  circular_id={item.get('circular_id')} | subject={item.get('subject', '')} | "
                f"table={item.get('n_table_measurements', 0)} | "
                f"prose={item.get('n_prose_measurements', 0)}"
            )
    else:
        lines.append("  (none)")

    lines.append("")
    lines.append("DETAILED SAMPLES")
    if samples:
        for family in sorted(samples):
            lines.append(f"  {family}")
            for measurement_type in sorted(samples[family]):
                lines.append(f"    {measurement_type}")
                for item in samples[family][measurement_type]:
                    lines.extend(_format_sample(item, indent="      "))
    else:
        lines.append("  (none)")

    lines.append("")
    lines.append("PROSE SAMPLES BY RULE")
    if prose_samples:
        for rule_id in sorted(prose_samples):
            lines.append(f"  {rule_id}")
            for item in prose_samples[rule_id]:
                lines.extend(_format_sample(item, indent="    "))
    else:
        lines.append("  (none)")

    lines.append("")
    lines.append("POTENTIALLY UNCOVERED FORMATS")
    tables_with_zero = list(uncovered.get("tables_with_zero_measurements") or [])
    photometry_like = list(uncovered.get("photometry_like_without_tables") or [])
    lines.append("  Tables detected but zero measurements")
    if tables_with_zero:
        for item in tables_with_zero[:15]:
            lines.append(
                f"    circular_id={item.get('circular_id')} year={item.get('year')} "
                f"family={item.get('table_family')} reason={item.get('reason')}"
            )
            lines.append(f"      subject: {item.get('subject', '')}")
            lines.append(f"      raw_header: {item.get('raw_header', '')}")
    else:
        lines.append("    (none)")
    lines.append("  Photometry-like circulars without detected tables")
    if photometry_like:
        for item in photometry_like[:15]:
            lines.append(
                f"    circular_id={item.get('circular_id')} year={item.get('year')} "
                f"reason={item.get('reason')}"
            )
            lines.append(f"      subject: {item.get('subject', '')}")
    else:
        lines.append("    (none)")

    lines.append("")
    lines.append("POSSIBLE PROBLEMS")
    if problems:
        problem_counts = Counter(flag for problem in problems for flag in problem["flags"])
        _append_counter(lines, dict(problem_counts.most_common()))
        for problem in problems[:20]:
            lines.append(
                f"  circular_id={problem['circular_id']} flags={','.join(problem['flags'])} "
                f"mag={problem.get('magnitude_or_limit')} band={problem.get('photometric_band')} "
                f"system={problem.get('photometric_system')}"
            )
            lines.append(f"    SOURCE_ROW: {problem.get('source_row', '')}")
    else:
        lines.append("  (none)")

    return "\n".join(lines)


def build_run_meta(
    mode: str,
    n_circulars_processed: int,
    total_measurements: int,
    total_problems: int,
    years_covered: list[int] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    generated = generated_at or datetime.now(timezone.utc).isoformat()
    return {
        "generated_at": generated,
        "mode": mode,
        "years_covered": years_covered or [],
        "n_circulars_processed": n_circulars_processed,
        "total_measurements": total_measurements,
        "total_problems": total_problems,
        "run_id": compute_run_id(mode, n_circulars_processed, total_measurements, total_problems),
    }


def compute_run_id(
    mode: str,
    n_circulars_processed: int,
    total_measurements: int,
    total_problems: int,
) -> str:
    payload = f"{mode}|{n_circulars_processed}|{total_measurements}|{total_problems}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:8]


def classify_source_family(circular: dict[str, Any], context: str = "") -> str:
    haystack = f"{circular.get('subject', '')}\n{circular.get('body', '')}\n{context}".lower()
    if "uvot" in haystack:
        return "UVOT"
    if "knc" in haystack or "kilonova-catcher" in haystack:
        return "KNC"
    if "master" in haystack:
        return "MASTER"
    if "grandma" in haystack:
        return "GRANDMA"
    return "OTHER"


def system_source(item: dict[str, Any]) -> str:
    provenance = list(item.get("provenance_inherited") or [])
    if "system_from_uvot_convention" in provenance:
        return "uvot_convention"
    for value in provenance:
        if str(value).startswith("photometric_system=context:"):
            return "context"
    system = item.get("photometric_system")
    if system and system != "unknown":
        return "cell"
    return "unknown"


def _format_sample(item: dict[str, Any], indent: str) -> list[str]:
    identity_fields = (
        f"circular_id={item.get('circular_id')} | "
        f"year={item.get('year')} | "
        f"source={item.get('source')} | "
        f"method={item.get('method')} | "
        f"rule_id={item.get('rule_id')} | "
        f"extractor_id={item.get('extractor_id')} | "
        f"extractor_version={item.get('extractor_version')} | "
        f"span={item.get('span_start')}-{item.get('span_end')}"
    )
    measurement_fields = (
        f"measurement_type={item.get('measurement_type')} | "
        f"magnitude_or_limit={item.get('magnitude_or_limit')} | "
        f"magnitude_error={item.get('magnitude_error')} | "
        f"limit_sigma={item.get('limit_sigma')} | "
        f"unit={item.get('unit')} | "
        f"photometric_band={item.get('photometric_band')} | "
        f"photometric_system={item.get('photometric_system')} | "
        f"obs_time_raw={item.get('obs_time_raw')} | "
        f"obs_time_type={item.get('obs_time_type')} | "
        f"obs_time_reference={item.get('obs_time_reference')} | "
        f"exposure_time_raw={item.get('exposure_time_raw')} | "
        f"instrument={item.get('instrument')}"
    )
    review_fields = (
        f"target={item.get('target')} | "
        f"certainty={item.get('certainty')} | "
        f"confidence={item.get('confidence')} | "
        f"needs_review={item.get('needs_review')} | "
        f"comment={item.get('comment')} | "
        f"provenance_inherited={item.get('provenance_inherited')} | "
        f"verify={item.get('verify')}"
    )
    return [
        f"{indent}{identity_fields}",
        f"{indent}{measurement_fields}",
        f"{indent}{review_fields}",
        f"{indent}SOURCE_ROW: {item.get('source_row') or item.get('text') or ''}",
        f"{indent}CONTEXT: {item.get('context', '')}",
    ]


def _sample_item(item: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "circular_id",
        "year",
        "subject",
        "source",
        "method",
        "rule_id",
        "extractor_id",
        "extractor_version",
        "schema_version",
        "text_sha256",
        "span_start",
        "span_end",
        "text",
        "measurement_type",
        "magnitude_or_limit",
        "magnitude_error",
        "limit_sigma",
        "unit",
        "photometric_band",
        "photometric_system",
        "obs_time_raw",
        "obs_time_type",
        "obs_time_reference",
        "exposure_time_raw",
        "instrument",
        "target",
        "certainty",
        "confidence",
        "needs_review",
        "comment",
        "provenance_inherited",
        "verify",
        "system_source",
        "source_family",
        "table_family",
        "source_row",
        "context",
    ]
    return {key: item.get(key) for key in keys}


def _append_counter(lines: list[str], values: dict[str, int], indent: str = "  ") -> None:
    if not values:
        lines.append(f"{indent}(none)")
        return
    for key, value in values.items():
        lines.append(f"{indent}{key}: {value}")


def _append_by_year_sections(lines: list[str], by_year: dict[str, Any]) -> None:
    if not by_year:
        return

    lines.append("")
    lines.append("BY YEAR - CIRCULARS")
    for year, stats in by_year.get("circulars", {}).items():
        lines.append(
            f"  {year}: processed={stats.get('processed', 0)} "
            f"with_tables={stats.get('with_tables', 0)} "
            f"with_prose={stats.get('with_prose', 0)} "
            f"measurements={stats.get('measurements', 0)}"
        )

    lines.append("")
    lines.append("BY YEAR x TABLE FAMILY")
    _append_nested_counter(lines, by_year.get("by_table_family", {}))

    lines.append("")
    lines.append("BY YEAR x SOURCE")
    _append_nested_counter(lines, by_year.get("by_source", {}))

    lines.append("")
    lines.append("BY YEAR x MEASUREMENT TYPE")
    _append_nested_counter(lines, by_year.get("by_measurement_type", {}))

    lines.append("")
    lines.append("BY YEAR x PHOTOMETRIC SYSTEM")
    _append_nested_counter(lines, by_year.get("by_photometric_system", {}))

    lines.append("")
    lines.append("BY YEAR - REVIEW RATE")
    for year, stats in by_year.get("review", {}).items():
        lines.append(
            f"  {year}: needs_review={stats.get('needs_review', 0)}/"
            f"{stats.get('total', 0)} ({float(stats.get('percent', 0.0)):.2f}%)"
        )


def _append_nested_counter(lines: list[str], values: dict[str, dict[str, int]]) -> None:
    if not values:
        lines.append("  (none)")
        return
    for year in sorted(values):
        lines.append(f"  {year}")
        _append_counter(lines, values[year], indent="    ")


def _matches_keywords(circular: dict[str, Any], keywords: list[str]) -> bool:
    haystack = f"{circular.get('subject', '')}\n{circular.get('body', '')}".lower()
    return any(keyword.lower() in haystack for keyword in keywords)


def _suggests_photometry(circular: dict[str, Any]) -> bool:
    haystack = f"{circular.get('subject', '')}\n{circular.get('body', '')}".lower()
    return bool(
        re.search(
            r"\b(?:photometry|photometric|optical|magnitude|upper\s+limit|observations?|"
            r"uvot|grandma|knc|master|goto|ztf|colibri|telescope|observatory)\b",
            haystack,
        )
    )


def _render_circular(circular: dict[str, Any]):
    return render_canonical(
        circular_id=int(circular["circular_id"]),
        subject=str(circular.get("subject", "")),
        body=str(circular.get("body", "")),
        event_id=circular.get("event_id"),
        created_on=circular.get("created_on"),
        submitter=circular.get("submitter"),
    )


def _context_excerpt(context: str, max_chars: int = 300) -> str:
    compact = re.sub(r"\s+", " ", context.strip())
    if len(compact) <= max_chars:
        return compact
    return f"{compact[: max_chars - 3]}..."


def _span_context(text: str, start: int, end: int, radius: int = 100) -> str:
    before = text[max(0, start - radius) : start]
    evidence = text[start:end]
    after = text[end : min(len(text), end + radius)]
    return re.sub(r"\s+", " ", f"{before}⟦{evidence}⟧{after}").strip()


def _review_reason_parts(item: dict[str, Any]) -> list[str]:
    comment = str(item.get("comment") or "needs_review without comment").strip()
    if not comment:
        return ["needs_review without comment"]
    if item.get("source") == "prose":
        return [
            part.strip()
            for part in re.split(r"(?<=\.)\s+(?=[A-Z])", comment)
            if part.strip()
        ]
    if ";" in comment:
        return [part.strip() for part in comment.split(";") if part.strip()]
    return [comment]


def _principal_float(value: object) -> float | None:
    if value is None:
        return None
    match = re.search(r"[+-]?\d+(?:\.\d+)?", str(value))
    if match is None:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _percent(value: int, total: int) -> float:
    if total == 0:
        return 0.0
    return 100 * value / total


def _value(value: object) -> str:
    if value is None or value == "":
        return "unknown"
    return str(value)


def _parse_positive_int(value: str, name: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise SystemExit(f"{name} must be an integer, got: {value!r}") from exc
    if parsed <= 0:
        raise SystemExit(f"{name} must be positive, got: {parsed}")
    return parsed


def _optional_int(value: object) -> int | None:
    return int(value) if value is not None else None


def _optional_str_list(value: object) -> list[str] | None:
    if value is None:
        return None
    return [str(item) for item in value]  # type: ignore[union-attr]


def _year_from_created_on(value: object) -> int | None:
    if value is None:
        return None
    text = str(value)
    if len(text) >= 4 and text[:4].isdigit():
        return int(text[:4])
    return None


def _is_clear_unfiltered_band(value: object) -> bool:
    if value is None:
        return False
    return str(value).strip() in CLEAR_UNFILTERED_BANDS


if __name__ == "__main__":
    raise SystemExit(main())
