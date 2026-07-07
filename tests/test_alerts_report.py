from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.alerts_report import (  # noqa: E402
    filter_by_rule_id,
    generate_alerts_report,
    group_counts,
)


def test_alerts_report_groups_and_counts() -> None:
    flagged = _flagged_fixture()

    counts = group_counts(flagged)

    assert counts == [
        {
            "flag": "needs_review_true",
            "extractor": "event_identity",
            "rule_id": "event_identity.grb_dayfraction",
            "count": 2,
        },
        {
            "flag": "span_too_long",
            "extractor": "localization",
            "rule_id": "localization.error_radius",
            "count": 1,
        },
    ]


def test_alerts_report_rule_filter() -> None:
    filtered = filter_by_rule_id(_flagged_fixture(), "event_identity.grb_dayfraction")

    assert len(filtered) == 2
    assert {item["rule_id"] for item in filtered} == {"event_identity.grb_dayfraction"}


def test_alerts_report_writes_file_with_context(tmp_path: Path) -> None:
    input_path = tmp_path / "sweep_report.json"
    input_path.write_text(json.dumps({"flagged": _flagged_fixture()}), encoding="utf-8")

    out_path, summary = generate_alerts_report(
        input_path=input_path,
        out_dir=tmp_path,
        rule_id_filter=None,
    )

    text = out_path.read_text(encoding="utf-8")
    assert out_path == tmp_path / "alerts_report.txt"
    assert "total de alertas: 3" in summary
    assert "### needs_review_true / event_identity / event_identity.grb_dayfraction  (2 alertas)" in text
    assert "CONTEXT: before ⟦GRB230101.09⟧ after" in text
    assert "LINE:    line with GRB230101.09" in text


def test_alerts_report_writes_filtered_file(tmp_path: Path) -> None:
    input_path = tmp_path / "sweep_report.json"
    input_path.write_text(json.dumps({"flagged": _flagged_fixture()}), encoding="utf-8")

    out_path, summary = generate_alerts_report(
        input_path=input_path,
        out_dir=tmp_path,
        rule_id_filter="event_identity.grb_dayfraction",
    )

    text = out_path.read_text(encoding="utf-8")
    assert out_path == tmp_path / "alerts_report_event_identity.grb_dayfraction.txt"
    assert "total de alertas: 2" in summary
    assert "event_identity.grb_dayfraction" in text
    assert "localization.error_radius" not in text
    assert "very long localization text" not in text


def _flagged_fixture() -> list[dict[str, object]]:
    return [
        {
            "circular_id": 1,
            "extractor": "event_identity",
            "rule_id": "event_identity.grb_dayfraction",
            "label": "EVENT_IDENTITY",
            "value": "GRB 230101.09",
            "span_start": 10,
            "flags": ["needs_review_true"],
            "context_window": "before ⟦GRB230101.09⟧ after",
            "source_line": "line with GRB230101.09",
        },
        {
            "circular_id": 2,
            "extractor": "event_identity",
            "rule_id": "event_identity.grb_dayfraction",
            "label": "EVENT_IDENTITY",
            "value": "GRB 230110.65",
            "span_start": 20,
            "flags": ["needs_review_true"],
            "context_window": "before ⟦GRB230110.65⟧ after",
            "source_line": "line with GRB230110.65",
        },
        {
            "circular_id": 3,
            "extractor": "localization",
            "rule_id": "localization.error_radius",
            "label": "LOCALIZATION",
            "value": "very long localization text",
            "span_start": 30,
            "flags": ["span_too_long"],
            "context_window": "before ⟦very long localization text⟧ after",
            "source_line": "line with localization",
        },
    ]
