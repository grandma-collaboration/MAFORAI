from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from skyportal_corpus.extraction_v2.sweep import (  # noqa: E402
    aggregate_by_rule,
    alert_counts_by_year,
    coverage_stats,
    coverage_stats_by_year,
    flag_summary,
    flag_suspicious,
    review_rate,
    run_sweep,
)


OUT_PATH = PROJECT_ROOT / "data" / "interim" / "gcn" / "sweep" / "sweep_report.json"


def main() -> int:
    mode = _parse_mode(sys.argv)
    sweep = run_sweep(
        limit=int(mode["limit"]),
        per_year=_optional_int(mode["per_year"]),
        only_extractors=_optional_str_list(mode["only_extractors"]),
    )
    annotations = list(sweep["annotations"])
    flagged = flag_suspicious(annotations, sweep.get("rendered_text_by_circular_id", {}))
    run_meta = build_run_meta(
        mode=str(mode["label"]),
        n_circulars_processed=int(sweep["n_circulars_processed"]),
        total_annotations=len(annotations),
        total_alerts=len(flagged),
        extractors=str(mode["extractors_label"]),
    )
    aggregates = {
        "coverage": coverage_stats(sweep),
        "review_rate": review_rate(annotations),
        "rule_counts": aggregate_by_rule(annotations),
        "flag_counts": flag_summary(flagged),
        "by_year": {
            "circulars": dict(dict(sweep.get("by_year") or {}).get("circulars") or {}),
            "coverage": coverage_stats_by_year(sweep),
            "alerts": alert_counts_by_year(flagged),
        },
    }

    report = {
        "run_meta": run_meta,
        "mode": mode,
        "summary": {
            "n_circulars_processed": sweep["n_circulars_processed"],
            "n_circulars_with_errors": sweep["n_circulars_with_errors"],
            "n_annotations": len(annotations),
            "extractors": sweep["extractors"],
        },
        "aggregates": aggregates,
        "annotations": annotations,
        "flagged": flagged,
        "gaps": sweep.get("gaps", {}),
        "errors": sweep["errors"],
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(_render_report(mode, sweep, flagged, aggregates))
    print(f"\nJSON: {OUT_PATH.relative_to(PROJECT_ROOT)}")
    return 0


def compute_run_id(
    mode: str,
    n_circulars_processed: int,
    total_annotations: int,
    total_alerts: int,
) -> str:
    payload = f"{mode}|{n_circulars_processed}|{total_annotations}|{total_alerts}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:8]


def build_run_meta(
    mode: str,
    n_circulars_processed: int,
    total_annotations: int,
    total_alerts: int,
    generated_at: str | None = None,
    extractors: str | None = None,
) -> dict[str, Any]:
    generated = generated_at or datetime.now(timezone.utc).isoformat()
    run_meta = {
        "generated_at": generated,
        "mode": mode,
        "n_circulars_processed": n_circulars_processed,
        "total_alerts": total_alerts,
        "run_id": compute_run_id(mode, n_circulars_processed, total_annotations, total_alerts),
    }
    if extractors is not None:
        run_meta["extractors"] = extractors
    return run_meta


def _parse_mode(argv: list[str]) -> dict[str, int | None | str | list[str] | None]:
    kind = "limit"
    limit = 500
    per_year: int | None = None
    only_extractors: list[str] | None = None
    mode_seen = False

    for argument in argv[1:]:
        if argument.startswith("only="):
            raw_value = argument.removeprefix("only=")
            only_extractors = [item.strip() for item in raw_value.split(",") if item.strip()]
            if not only_extractors:
                raise SystemExit("only= requires at least one extractor name")
            continue

        if argument.startswith("per_year="):
            if mode_seen:
                raise SystemExit("Use either a numeric limit or per_year=N, not both")
            raw_value = argument.removeprefix("per_year=")
            try:
                per_year = int(raw_value)
            except ValueError as exc:
                raise SystemExit(f"per_year must be an integer, got: {raw_value!r}") from exc
            if per_year <= 0:
                raise SystemExit(f"per_year must be positive, got: {per_year}")
            kind = "per_year"
            limit = 50
            mode_seen = True
            continue

        if mode_seen:
            raise SystemExit("Use either a numeric limit or per_year=N, not both")
        try:
            limit = int(argument)
        except ValueError as exc:
            raise SystemExit(f"Argument must be an integer, per_year=N, or only=name[,name], got: {argument!r}") from exc
        if limit <= 0:
            raise SystemExit(f"Limit must be positive, got: {limit}")
        kind = "limit"
        per_year = None
        mode_seen = True

    base_label = f"per_year={per_year}" if kind == "per_year" else f"limit={limit}"
    extractors_label = ",".join(only_extractors) if only_extractors else "todos"
    label = f"{base_label} only={extractors_label}" if only_extractors else base_label
    return {
        "kind": kind,
        "limit": limit,
        "per_year": per_year,
        "only_extractors": only_extractors,
        "extractors_label": extractors_label,
        "label": label,
    }


def _render_report(
    mode: dict[str, int | None | str],
    sweep: dict[str, Any],
    flagged: list[dict[str, Any]],
    aggregates: dict[str, Any],
) -> str:
    lines: list[str] = []
    annotations = list(sweep["annotations"])

    lines.append("RESUMEN GLOBAL")
    lines.append(f"  modo: {mode['label']}")
    lines.append(f"  extractores: {mode.get('extractors_label', 'todos')}")
    lines.append(f"  circulars procesados: {sweep['n_circulars_processed']}")
    lines.append(f"  circulars con errores: {sweep['n_circulars_with_errors']}")
    lines.append(f"  anotaciones totales: {len(annotations)}")

    lines.append("")
    lines.append("COBERTURA POR EXTRACTOR")
    lines.append("  extractor        circulars  cobertura")
    for extractor_name, stats in aggregates["coverage"].items():
        lines.append(f"  {extractor_name:<16} {stats['n_circulars']:>9}  {stats['percent']:>7.2f}%")

    lines.append("")
    lines.append("POR AÑO — CIRCULARS")
    lines.append("  año     circulars")
    for year, count in aggregates["by_year"]["circulars"].items():
        lines.append(f"  {year:<7} {count:>9}")

    lines.append("")
    lines.append("POR AÑO — COBERTURA")
    for extractor_name, values_by_year in aggregates["by_year"]["coverage"].items():
        lines.append(f"  {extractor_name}")
        lines.append("    año     anotaciones  circulars_con_una  cobertura")
        for year, stats in values_by_year.items():
            lines.append(
                f"    {year:<7} {stats['n_annotations']:>11}  "
                f"{stats['n_circulars_with_at_least_one']:>17}  {stats['percent']:>7.2f}%"
            )

    lines.append("")
    lines.append("POR AÑO — ALERTAS")
    lines.append("  año     alertas")
    if aggregates["by_year"]["alerts"]:
        for year, count in aggregates["by_year"]["alerts"].items():
            lines.append(f"  {year:<7} {count:>7}")
    else:
        lines.append("  (none)")

    if "event_identity" in dict(sweep.get("extractors") or {}):
        lines.append("")
        lines.append("HUECOS — EVENT_IDENTITY (circulars sin ninguna identidad)")
        identity_gaps = list(dict(sweep.get("gaps") or {}).get("event_identity") or [])
        if identity_gaps:
            for year, gaps in _gaps_by_year(identity_gaps).items():
                lines.append(f"  {year}: {len(gaps)}")
                for gap in gaps[:10]:
                    lines.append(f"    - {gap.get('circular_id')} | {gap.get('subject')}")
        else:
            lines.append("  (none)")

    lines.append("")
    lines.append("TASA DE REVISIÓN")
    lines.append("  extractor        total  needs_review  tasa")
    for extractor_name, stats in aggregates["review_rate"].items():
        lines.append(
            f"  {extractor_name:<16} {stats['total']:>5}  "
            f"{stats['needs_review']:>12}  {stats['percent']:>6.2f}%"
        )

    lines.append("")
    lines.append("DISPAROS POR REGLA")
    if aggregates["rule_counts"]:
        for rule_id, count in aggregates["rule_counts"].items():
            lines.append(f"  {rule_id:<38} {count}")
    else:
        lines.append("  (none)")

    lines.append("")
    lines.append("RESUMEN DE SEÑALES DE ALERTA")
    if aggregates["flag_counts"]:
        for flag, count in aggregates["flag_counts"].items():
            lines.append(f"  {flag:<28} {count}")
    else:
        lines.append("  (none)")

    lines.append("")
    lines.append("MUESTRAS DE ALERTAS")
    if flagged:
        for flag, items in _flagged_by_type(flagged).items():
            lines.append(f"  {flag}")
            for item in items[:5]:
                lines.append(
                    "    - "
                    f"circular_id={item.get('circular_id')} "
                    f"extractor={item.get('extractor')} "
                    f"label={item.get('label')} "
                    f"value={item.get('value')!r} "
                    f"flags={item.get('flags')}"
                )
                lines.append(f"      CONTEXT: {item.get('context_window', '')}")
                lines.append(f"      LINE:    {item.get('source_line', '')}")
    else:
        lines.append("  (none)")

    lines.append("")
    lines.append("EJEMPLOS POSITIVOS")
    flagged_keys = {_annotation_key(item) for item in flagged}
    for extractor_name in sweep["extractors"]:
        clean = [
            annotation
            for annotation in annotations
            if annotation.get("extractor") == extractor_name and _annotation_key(annotation) not in flagged_keys
        ][:3]
        lines.append(f"  {extractor_name}")
        if not clean:
            lines.append("    (none)")
            continue
        for annotation in clean:
            lines.append(
                "    - "
                f"circular_id={annotation.get('circular_id')} "
                f"label={annotation.get('label')} "
                f"value={annotation.get('value')!r} "
                f"text={_clip(str(annotation.get('text') or ''))!r}"
            )

    lines.append("")
    lines.append("ERRORES")
    if sweep["errors"]:
        for error in sweep["errors"]:
            lines.append(
                "  - "
                f"circular_id={error.get('circular_id')} "
                f"extractor={error.get('extractor')} "
                f"message={error.get('message')}"
            )
    else:
        lines.append("  (none)")

    return "\n".join(lines)


def _flagged_by_type(flagged: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_flag: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in flagged:
        for flag in item.get("flags", []):
            by_flag[str(flag)].append(item)
    return dict(sorted(by_flag.items()))


def _gaps_by_year(gaps: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_year: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for gap in gaps:
        by_year[str(gap.get("year") or "unknown")].append(gap)
    return dict(sorted(by_year.items(), key=lambda item: _year_sort_key(item[0])))


def _year_sort_key(year: str) -> tuple[int, str]:
    if year.isdigit():
        return int(year), year
    return 9999, year


def _annotation_key(annotation: dict[str, Any]) -> tuple[Any, Any, Any, Any, Any]:
    return (
        annotation.get("circular_id"),
        annotation.get("extractor"),
        annotation.get("span_start"),
        annotation.get("span_end"),
        annotation.get("rule_id"),
    )


def _clip(text: str, max_chars: int = 100) -> str:
    compact = " ".join(text.split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3] + "..."


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _optional_str_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    return [str(item) for item in value]


if __name__ == "__main__":
    raise SystemExit(main())
