from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = PROJECT_ROOT / "data" / "interim" / "gcn" / "sweep" / "sweep_report.json"
OUT_DIR = PROJECT_ROOT / "data" / "interim" / "gcn" / "sweep"

GroupKey = tuple[str, str, str]


def main() -> int:
    args = _parse_args(sys.argv)
    try:
        out_path, summary = generate_alerts_report(
            input_path=INPUT_PATH,
            out_dir=OUT_DIR,
            rule_id_filter=args["rule_id_filter"],
            check_freshness=bool(args["check_freshness"]),
        )
    except FileNotFoundError:
        print(
            "data/interim/gcn/sweep/sweep_report.json does not exist. "
            "Run this first: .venv/bin/python scripts/sweep_report.py 500"
        )
        return 1

    print(summary)
    print(f"\nFull report: {out_path.relative_to(PROJECT_ROOT)}")
    return 0


def generate_alerts_report(
    input_path: Path,
    out_dir: Path,
    rule_id_filter: str | None = None,
    check_freshness: bool = False,
) -> tuple[Path, str]:
    if not input_path.exists():
        raise FileNotFoundError(input_path)

    data = json.loads(input_path.read_text(encoding="utf-8"))
    flagged_all = list(data.get("flagged", []))
    run_meta = dict(data.get("run_meta") or {})
    flagged = flagged_all
    if rule_id_filter:
        flagged = filter_by_rule_id(flagged_all, rule_id_filter)

    counts = group_counts(flagged)
    out_path = output_path(out_dir, rule_id_filter)
    sync_message = sync_status(run_meta, flagged_all)
    freshness_message = freshness_status(run_meta) if check_freshness else None
    report_text = render_full_report(
        flagged,
        counts,
        input_path,
        rule_id_filter,
        run_meta=run_meta,
        sync_message=sync_message,
        freshness_message=freshness_message,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report_text, encoding="utf-8")

    summary = render_summary(
        flagged,
        counts,
        rule_id_filter,
        run_meta=run_meta,
        sync_message=sync_message,
        freshness_message=freshness_message,
    )
    return out_path, summary


def _parse_args(argv: list[str]) -> dict[str, str | bool | None]:
    check_freshness = False
    rule_id_filter: str | None = None
    for argument in argv[1:]:
        if argument == "--check-freshness":
            check_freshness = True
            continue
        if rule_id_filter is None:
            rule_id_filter = argument
            continue
        raise SystemExit("Usage: .venv/bin/python scripts/alerts_report.py [rule_id] [--check-freshness]")
    return {"rule_id_filter": rule_id_filter, "check_freshness": check_freshness}


def filter_by_rule_id(flagged: list[dict[str, Any]], rule_id: str) -> list[dict[str, Any]]:
    return [item for item in flagged if str(item.get("rule_id") or "unknown") == rule_id]


def group_counts(flagged: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups = group_alerts(flagged)
    rows = [
        {
            "flag": flag,
            "extractor": extractor,
            "rule_id": rule_id,
            "count": len(items),
        }
        for (flag, extractor, rule_id), items in groups.items()
    ]
    return sorted(rows, key=lambda row: (-int(row["count"]), str(row["flag"]), str(row["extractor"]), str(row["rule_id"])))


def group_alerts(flagged: list[dict[str, Any]]) -> dict[GroupKey, list[dict[str, Any]]]:
    groups: dict[GroupKey, list[dict[str, Any]]] = defaultdict(list)
    for item in flagged:
        extractor = str(item.get("extractor") or "unknown")
        rule_id = str(item.get("rule_id") or "unknown")
        for flag in item.get("flags", []):
            groups[(str(flag), extractor, rule_id)].append(item)
    return dict(sorted(groups.items(), key=lambda entry: entry[0]))


def render_summary(
    flagged: list[dict[str, Any]],
    counts: list[dict[str, Any]],
    rule_id_filter: str | None = None,
    run_meta: dict[str, Any] | None = None,
    sync_message: str | None = None,
    freshness_message: str | None = None,
) -> str:
    lines: list[str] = []
    lines.extend(render_run_meta(run_meta or {}, sync_message, freshness_message))
    lines.append("")
    lines.append("FULL ALERT SUMMARY")
    lines.append(f"  total alerts: {len(flagged)}")
    if rule_id_filter:
        lines.append(f"  rule_id filter: {rule_id_filter}")
    lines.append("")
    lines.append("flag_type                    extractor        rule_id                                count")
    if not counts:
        lines.append("(none)")
    for row in counts:
        lines.append(
            f"{row['flag']:<28} "
            f"{row['extractor']:<16} "
            f"{row['rule_id']:<38} "
            f"{row['count']}"
        )
    return "\n".join(lines)


def render_full_report(
    flagged: list[dict[str, Any]],
    counts: list[dict[str, Any]],
    input_path: Path,
    rule_id_filter: str | None = None,
    run_meta: dict[str, Any] | None = None,
    sync_message: str | None = None,
    freshness_message: str | None = None,
) -> str:
    lines: list[str] = []
    lines.append("FULL SWEEP ALERTS")
    lines.append(f"Source: {input_path}")
    if rule_id_filter:
        lines.append(f"Rule_id filter: {rule_id_filter}")
    lines.append("")
    lines.append(
        render_summary(
            flagged,
            counts,
            rule_id_filter,
            run_meta=run_meta,
            sync_message=sync_message,
            freshness_message=freshness_message,
        )
    )
    lines.append("")
    lines.append("DETAILS")

    groups = group_alerts(flagged)
    if not groups:
        lines.append("(none)")
        return "\n".join(lines) + "\n"

    for (flag, extractor, rule_id), items in groups.items():
        lines.append("")
        lines.append(f"### {flag} / {extractor} / {rule_id}  ({len(items)} alerts)")
        for item in sorted(items, key=_alert_sort_key):
            lines.append(
                f"circular_id={item.get('circular_id')} | "
                f"extractor={item.get('extractor')} | "
                f"rule_id={item.get('rule_id')} | "
                f"label={item.get('label')} | "
                f"value={item.get('value')!r}"
            )
            lines.append(f"CONTEXT: {item.get('context_window', '')}")
            lines.append(f"LINE:    {item.get('source_line', '')}")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_run_meta(
    run_meta: dict[str, Any],
    sync_message: str | None = None,
    freshness_message: str | None = None,
) -> list[str]:
    lines = ["RUN_META"]
    if not run_meta:
        lines.append("  (unavailable)")
        lines.append(f"  {sync_message or 'OUT OF SYNC: run_meta is missing from the JSON.'}")
        return lines
    lines.append(f"  generated_at: {run_meta.get('generated_at', '')}")
    lines.append(f"  mode: {run_meta.get('mode', '')}")
    if "extractors" in run_meta:
        lines.append(f"  extractors: {run_meta.get('extractors', '')}")
    lines.append(f"  n_circulars: {run_meta.get('n_circulars_processed', '')}")
    lines.append(f"  total_alerts: {run_meta.get('total_alerts', '')}")
    lines.append(f"  run_id: {run_meta.get('run_id', '')}")
    lines.append(f"  {sync_message or ''}".rstrip())
    if freshness_message:
        lines.append(f"  {freshness_message}")
    return lines


def sync_status(run_meta: dict[str, Any], flagged: list[dict[str, Any]]) -> str:
    if not run_meta:
        return (
            "OUT OF SYNC: run_meta is missing from the JSON. "
            "Run sweep_report.py and then alerts_report.py IN THAT ORDER."
        )
    try:
        expected = int(run_meta.get("total_alerts"))
    except (TypeError, ValueError):
        return (
            "OUT OF SYNC: run_meta.total_alerts is invalid. "
            "Run sweep_report.py and then alerts_report.py IN THAT ORDER."
        )
    actual = len(flagged)
    generated_at = str(run_meta.get("generated_at") or "")
    run_id = str(run_meta.get("run_id") or "")
    if expected == actual:
        return f"SYNCHRONIZED ✓ (run_id={run_id}, generated_at={generated_at})"
    return (
        f"OUT OF SYNC: the JSON declares {expected} alerts but {actual} were read. "
        "Run sweep_report.py and then alerts_report.py IN THAT ORDER."
    )


def freshness_status(
    run_meta: dict[str, Any],
    max_age_hours: int = 6,
    now: datetime | None = None,
) -> str | None:
    generated_at = run_meta.get("generated_at")
    if not generated_at:
        return "WARNING: generated_at is missing; freshness cannot be checked."
    try:
        parsed = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00"))
    except ValueError:
        return "WARNING: generated_at is not a valid ISO timestamp."
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    if current - parsed > timedelta(hours=max_age_hours):
        return "WARNING: the JSON may belong to an earlier run."
    return None


def output_path(out_dir: Path, rule_id_filter: str | None = None) -> Path:
    if not rule_id_filter:
        return out_dir / "alerts_report.txt"
    safe_rule_id = re.sub(r"[^A-Za-z0-9._-]+", "_", rule_id_filter)
    return out_dir / f"alerts_report_{safe_rule_id}.txt"


def _alert_sort_key(item: dict[str, Any]) -> tuple[int, int, str]:
    circular_id = _safe_int(item.get("circular_id"))
    span_start = _safe_int(item.get("span_start"))
    value = str(item.get("value") or "")
    return (circular_id, span_start, value)


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
