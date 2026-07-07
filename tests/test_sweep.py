from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from scripts.alerts_report import sync_status  # noqa: E402
from scripts.sweep_report import build_run_meta, compute_run_id  # noqa: E402
import skyportal_corpus.canonical.document as canonical_document  # noqa: E402
from skyportal_corpus.canonical.document import CanonicalDocument  # noqa: E402
from skyportal_corpus.extraction_v2.event_identity import EventIdentityExtractor  # noqa: E402
from skyportal_corpus.extraction_v2.sweep import (  # noqa: E402
    aggregate_by_rule,
    alert_counts_by_year,
    coverage_stats,
    coverage_stats_by_year,
    flag_summary,
    flag_suspicious,
    get_active_extractors,
    review_rate,
    run_sweep,
)


def _synthetic_body() -> str:
    return "This synthetic circular body is intentionally long enough for loader filtering. " * 4


def test_iter_stratified_circulars_samples_uniformly_by_year(monkeypatch: pytest.MonkeyPatch) -> None:
    records = [
        {
            "circular_id": year * 100 + index,
            "subject": f"Report {year}-{index}",
            "body": _synthetic_body(),
            "created_on": f"{year}-01-{index + 1:02d}T00:00:00+00:00",
            "year": year,
        }
        for year, total in ((2023, 10), (2024, 6), (2025, 2))
        for index in range(total)
    ]

    def fake_records(min_year: int, limit: int | None, include_year: bool) -> list[dict[str, object]]:
        selected: list[dict[str, object]] = []
        for record in records:
            if int(record["year"]) < min_year:
                continue
            item = dict(record)
            if not include_year:
                item.pop("year")
            selected.append(item)
            if limit is not None and len(selected) >= limit:
                break
        return selected

    monkeypatch.setattr(canonical_document, "_iter_real_circular_records", fake_records)

    first = list(canonical_document.iter_stratified_circulars(per_year=3, min_year=2023))
    second = list(canonical_document.iter_stratified_circulars(per_year=3, min_year=2023))

    assert first == second
    assert [item["year"] for item in first].count(2023) == 3
    assert [item["year"] for item in first].count(2024) == 3
    assert [item["year"] for item in first].count(2025) == 2
    assert [item["circular_id"] for item in first if item["year"] == 2023] == [202301, 202305, 202308]


def test_run_sweep_per_year_records_year_aggregates() -> None:
    circulars = [
        {
            "circular_id": year * 100 + index,
            "year": year,
            "created_on": f"{year}-02-{index + 1:02d}T00:00:00+00:00",
            "subject": f"Instrument report {year}-{index}",
            "body": "Swift/BAT triggered and located the burst.",
        }
        for year, total in ((2023, 4), (2024, 1))
        for index in range(total)
    ]

    sweep = run_sweep(limit=10, per_year=2, circulars=circulars)

    assert sweep["n_circulars_processed"] == 3
    assert sweep["by_year"]["circulars"] == {"2023": 2, "2024": 1}
    assert sweep["by_year"]["extractors"]["trigger_instrument"]["2023"] == {
        "n_annotations": 2,
        "n_circulars_with_at_least_one": 2,
    }
    assert sweep["by_year"]["extractors"]["trigger_instrument"]["2024"] == {
        "n_annotations": 1,
        "n_circulars_with_at_least_one": 1,
    }
    assert all(annotation["year"] in {2023, 2024} for annotation in sweep["annotations"])
    assert coverage_stats_by_year(sweep)["trigger_instrument"] == {
        "2023": {"n_annotations": 2, "n_circulars_with_at_least_one": 2, "percent": 100.0},
        "2024": {"n_annotations": 1, "n_circulars_with_at_least_one": 1, "percent": 100.0},
    }


def test_run_sweep_counts_synthetic_circulars() -> None:
    circulars = [
        {
            "circular_id": 1,
            "subject": "GRB 240625A",
            "body": (
                "At 02:16:38 UT on 1 Jan 2023, the Fermi GBM triggered and located the burst. "
                "The on-ground location is RA = 206.3, Dec = -21.9, "
                "with a statistical uncertainty of 2.8 degrees."
            ),
        },
        {
            "circular_id": 2,
            "subject": "Plain follow-up report",
            "body": "No recognized event name, trigger time, or coordinates appear here.",
        },
    ]

    sweep = run_sweep(limit=10, circulars=circulars)

    assert sweep["n_circulars_processed"] == 2
    assert sweep["n_circulars_with_errors"] == 0
    assert sweep["errors"] == []
    assert sweep["extractors"]["event_identity"] == {
        "n_annotations": 1,
        "n_circulars_with_at_least_one": 1,
    }
    assert sweep["extractors"]["trigger_time"] == {
        "n_annotations": 1,
        "n_circulars_with_at_least_one": 1,
    }
    assert sweep["extractors"]["localization"] == {
        "n_annotations": 2,
        "n_circulars_with_at_least_one": 1,
    }
    assert sweep["extractors"]["trigger_instrument"] == {
        "n_annotations": 1,
        "n_circulars_with_at_least_one": 1,
    }
    assert len(sweep["annotations"]) == 5


def test_run_sweep_records_event_identity_gaps_with_subject() -> None:
    sweep = run_sweep(
        limit=10,
        circulars=[
            {
                "circular_id": 60,
                "year": 2024,
                "subject": "GRB 240625A",
                "body": "This circular has a standard event identity.",
            },
            {
                "circular_id": 61,
                "year": 2024,
                "subject": "Unusual transient naming format",
                "body": "This circular has no known event identity pattern.",
            },
        ],
    )

    assert sweep["gaps"]["event_identity"] == [
        {
            "circular_id": 61,
            "year": 2024,
            "subject": "Unusual transient naming format",
        }
    ]


def test_get_active_extractors_includes_five_extractors() -> None:
    extractor_ids = [extractor.extractor_id for extractor in get_active_extractors()]

    assert extractor_ids == [
        "event-identity-v1",
        "trigger-time-v1",
        "localization-v1",
        "trigger-instrument-v1",
        "redshift-v1",
    ]


def test_run_sweep_only_redshift_runs_single_extractor() -> None:
    sweep = run_sweep(
        limit=10,
        only_extractors=["redshift"],
        circulars=[
            {
                "circular_id": 49,
                "subject": "GRB 240625A redshift",
                "body": "We measure z = 1.2 for the event.",
            }
        ],
    )

    assert set(sweep["extractors"]) == {"redshift"}
    assert sweep["extractors"]["redshift"] == {
        "n_annotations": 1,
        "n_circulars_with_at_least_one": 1,
    }
    assert len(sweep["annotations"]) == 1
    assert sweep["annotations"][0]["extractor"] == "redshift"
    assert sweep["annotations"][0]["label"] == "REDSHIFT_EVENT"
    assert sweep["gaps"]["event_identity"] == []


def test_run_sweep_extracts_trigger_instrument_from_synthetic_circular() -> None:
    sweep = run_sweep(
        limit=1,
        circulars=[
            {
                "circular_id": 50,
                "subject": "Swift trigger report",
                "body": "At 21:04:43 UT, Swift/BAT triggered and located GRB 230116D.",
            }
        ],
    )

    trigger_instruments = [
        annotation
        for annotation in sweep["annotations"]
        if annotation.get("label") == "TRIGGER_INSTRUMENT"
    ]

    assert sweep["extractors"]["trigger_instrument"] == {
        "n_annotations": 1,
        "n_circulars_with_at_least_one": 1,
    }
    assert len(trigger_instruments) == 1
    assert trigger_instruments[0]["value"] == "Swift/BAT"
    assert trigger_instruments[0]["text"] == "Swift/BAT"


def test_flag_suspicious_marks_long_spans_and_bad_coordinates() -> None:
    suspicious = flag_suspicious(
        [
            {
                "circular_id": 10,
                "extractor": "event_identity",
                "label": "EVENT_IDENTITY",
                "value": "GRB 240625A",
                "text": "x" * 121,
                "needs_review": False,
            },
            {
                "circular_id": 11,
                "extractor": "localization",
                "label": "LOCALIZATION",
                "value": "RA=999, Dec=0",
                "text": "RA = 999, Dec = 0",
                "needs_review": False,
            },
        ]
    )

    by_id = {item["circular_id"]: item for item in suspicious}
    assert "span_too_long" in by_id[10]["flags"]
    assert "localization_out_of_range" in by_id[11]["flags"]


def test_flag_suspicious_adds_context_only_for_flagged_annotations() -> None:
    rendered_text = "GRB starts at the first character\nThe second line is nearby."
    flagged = flag_suspicious(
        [
            {
                "circular_id": 12,
                "extractor": "event_identity",
                "label": "EVENT_IDENTITY",
                "value": "GRB 240625A",
                "text": "GRB",
                "span_start": 0,
                "span_end": 3,
                "rule_id": "event_identity.grb",
                "needs_review": True,
            }
        ],
        {"12": rendered_text},
    )

    assert len(flagged) == 1
    assert flagged[0]["context_window"].startswith("⟦GRB⟧ starts at the first character")
    assert " ⏎ " in flagged[0]["context_window"]
    assert flagged[0]["source_line"] == "GRB starts at the first character"


def test_run_sweep_keeps_healthy_annotations_without_context_fields() -> None:
    sweep = run_sweep(
        limit=1,
        circulars=[
            {
                "circular_id": 13,
                "subject": "GRB 240625A",
                "body": "This synthetic body has no additional suspicious evidence.",
            }
        ],
    )

    assert sweep["annotations"]
    assert all("context_window" not in annotation for annotation in sweep["annotations"])
    assert all("source_line" not in annotation for annotation in sweep["annotations"])
    assert flag_suspicious(sweep["annotations"], sweep["rendered_text_by_circular_id"]) == []


def test_run_sweep_records_extractor_errors_and_continues() -> None:
    class BrokenExtractor:
        extractor_id = "broken"

        def extract(self, doc: CanonicalDocument) -> list[object]:
            if doc.circular_id == 20:
                raise RuntimeError("synthetic extractor failure")
            return []

    circulars = [
        {"circular_id": 20, "subject": "GRB 240625A", "body": "First body."},
        {"circular_id": 21, "subject": "GRB 240626A", "body": "Second body."},
    ]

    sweep = run_sweep(
        limit=10,
        circulars=circulars,
        extractors={"event_identity": EventIdentityExtractor(), "broken": BrokenExtractor()},
    )

    assert sweep["n_circulars_processed"] == 2
    assert sweep["n_circulars_with_errors"] == 1
    assert sweep["extractors"]["event_identity"]["n_annotations"] == 2
    assert sweep["extractors"]["broken"]["n_annotations"] == 0
    assert len(sweep["errors"]) == 1
    assert sweep["errors"][0]["circular_id"] == 20
    assert sweep["errors"][0]["extractor"] == "broken"
    assert "synthetic extractor failure" in sweep["errors"][0]["message"]


def test_aggregation_helpers_count_rules_flags_review_and_coverage() -> None:
    annotations = [
        {
            "extractor": "event_identity",
            "rule_id": "event_identity.grb",
            "needs_review": False,
        },
        {
            "extractor": "event_identity",
            "rule_id": "event_identity.grb",
            "needs_review": True,
        },
        {
            "extractor": "trigger_time",
            "rule_id": "trigger_time.clock_on_date",
            "needs_review": True,
        },
    ]
    flagged = [
        {"year": 2023, "flags": ["needs_review_true", "span_too_long"]},
        {"year": 2024, "flags": ["needs_review_true"]},
    ]
    sweep_result = {
        "n_circulars_processed": 10,
        "extractors": {
            "event_identity": {"n_circulars_with_at_least_one": 3},
            "trigger_time": {"n_circulars_with_at_least_one": 2},
        },
    }

    assert aggregate_by_rule(annotations) == {
        "event_identity.grb": 2,
        "trigger_time.clock_on_date": 1,
    }
    assert flag_summary(flagged) == {"needs_review_true": 2, "span_too_long": 1}
    assert alert_counts_by_year(flagged) == {"2023": 1, "2024": 1}
    assert review_rate(annotations) == {
        "event_identity": {"total": 2, "needs_review": 1, "percent": 50.0},
        "trigger_time": {"total": 1, "needs_review": 1, "percent": 100.0},
    }
    assert coverage_stats(sweep_result) == {
        "event_identity": {"n_circulars": 3, "percent": 30.0},
        "trigger_time": {"n_circulars": 2, "percent": 20.0},
    }


def test_flag_suspicious_marks_review_and_weird_formats() -> None:
    suspicious = flag_suspicious(
        [
            {
                "circular_id": 30,
                "extractor": "event_identity",
                "label": "EVENT_IDENTITY",
                "value": "NOT_AN_EVENT",
                "text": "NOT_AN_EVENT",
                "needs_review": True,
            },
            {
                "circular_id": 31,
                "extractor": "trigger_time",
                "label": "TRIGGER_TIME",
                "value": "yesterday morning",
                "text": "yesterday morning",
                "needs_review": False,
            },
        ]
    )

    by_id = {item["circular_id"]: item for item in suspicious}
    assert set(by_id[30]["flags"]) == {"identity_value_weird", "needs_review_true"}
    assert by_id[31]["flags"] == ["trigger_value_not_iso"]


@pytest.mark.parametrize(
    "value",
    [
        "ZTF23aaarlti",
        "AT 2023bic",
        "GRB 230101A",
        "GRB 230101.09",
        "EP 240315a",
        "EP 260225.148",
        "EP-WXT 01709176712",
        "EP-WXT 20240219aa",
        "EP-FXT 01709177837",
        "IceCube-230101A",
        "GW230529",
        "S231113a",
    ],
)
def test_flag_suspicious_accepts_canonical_event_identity_values(value: str) -> None:
    assert (
        flag_suspicious(
            [
                {
                    "circular_id": 33,
                    "extractor": "event_identity",
                    "label": "EVENT_IDENTITY",
                    "value": value,
                    "text": value,
                    "needs_review": False,
                }
            ]
        )
        == []
    )


@pytest.mark.parametrize("value", ["GRB 23", "XYZ 999"])
def test_flag_suspicious_rejects_malformed_event_identity_values(value: str) -> None:
    suspicious = flag_suspicious(
        [
            {
                "circular_id": 34,
                "extractor": "event_identity",
                "label": "EVENT_IDENTITY",
                "value": value,
                "text": value,
                "needs_review": False,
            }
        ]
    )

    assert suspicious[0]["flags"] == ["identity_value_weird"]


def test_flag_suspicious_rejects_out_of_range_clock_value() -> None:
    suspicious = flag_suspicious(
        [
            {
                "circular_id": 32,
                "extractor": "trigger_time",
                "label": "TRIGGER_TIME",
                "value": "49:52:20.5",
                "text": "49:52:20.5",
                "needs_review": False,
            }
        ]
    )

    assert suspicious[0]["flags"] == ["trigger_value_not_iso"]


@pytest.mark.parametrize(
    "value",
    ["2023-01-01T02:16:38", "MJD 59945.1", "02:16:38", "02:16:38 UT"],
)
def test_flag_suspicious_accepts_expected_trigger_value_formats(value: str) -> None:
    assert (
        flag_suspicious(
            [
                {
                    "circular_id": 40,
                    "extractor": "trigger_time",
                    "label": "TRIGGER_TIME",
                    "value": value,
                    "text": value,
                    "needs_review": False,
                }
            ]
        )
        == []
    )


def test_sweep_report_run_id_is_deterministic() -> None:
    first = compute_run_id(
        mode="per_year=100",
        n_circulars_processed=400,
        total_annotations=1200,
        total_alerts=226,
    )
    second = compute_run_id(
        mode="per_year=100",
        n_circulars_processed=400,
        total_annotations=1200,
        total_alerts=226,
    )
    different = compute_run_id(
        mode="per_year=100",
        n_circulars_processed=400,
        total_annotations=1200,
        total_alerts=202,
    )

    assert first == second
    assert len(first) == 8
    assert first != different

    filtered = compute_run_id(
        mode="per_year=100 only=redshift",
        n_circulars_processed=400,
        total_annotations=1200,
        total_alerts=226,
    )

    assert filtered != first


def test_alerts_report_sync_status_detects_mismatch() -> None:
    flagged = [{"circular_id": 1}, {"circular_id": 2}]
    run_meta = build_run_meta(
        mode="per_year=100",
        n_circulars_processed=10,
        total_annotations=20,
        total_alerts=2,
        generated_at="2026-07-06T00:00:00+00:00",
    )

    assert "SINCRONIZADO ✓" in sync_status(run_meta, flagged)

    stale_meta = dict(run_meta)
    stale_meta["total_alerts"] = 3

    assert (
        "DESINCRONIZADO: el JSON tiene 3 alertas pero se leyeron 2"
        in sync_status(stale_meta, flagged)
    )
