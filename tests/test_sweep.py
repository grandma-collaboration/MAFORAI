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
from scripts.sweep_report import (  # noqa: E402
    _distributed_gap_examples,
    build_run_meta,
    compute_run_id,
)
import skyportal_corpus.canonical.document as canonical_document  # noqa: E402
from skyportal_corpus.canonical.document import CanonicalDocument  # noqa: E402
from skyportal_corpus.extraction_v2.event_identity import EventIdentityExtractor  # noqa: E402
from skyportal_corpus.extraction_v2.sweep import (  # noqa: E402
    DIMENSIONLESS_RULES,
    aggregate_by_rule,
    alert_counts_by_year,
    coverage_stats,
    coverage_stats_by_year,
    flag_summary,
    flag_suspicious,
    get_active_extractors,
    review_rate,
    run_sweep,
    samples_by_rule,
)


def _synthetic_body() -> str:
    return "This synthetic circular body is intentionally long enough for loader filtering. " * 4


def _scientific_annotation(
    circular_id: int,
    extractor: str,
    label: str,
    value: str,
    unit: str,
    rule_id: str,
) -> dict[str, object]:
    return {
        "circular_id": circular_id,
        "year": 2026,
        "extractor": extractor,
        "label": label,
        "value": value,
        "unit": unit,
        "text": value,
        "span_start": 0,
        "span_end": len(value),
        "rule_id": rule_id,
        "needs_review": False,
    }


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


def test_get_active_extractors_includes_thirteen_extractors() -> None:
    extractor_ids = [extractor.extractor_id for extractor in get_active_extractors()]

    assert extractor_ids == [
        "event-identity-v1",
        "trigger-time-v1",
        "localization-v1",
        "trigger-instrument-v1",
        "redshift-v1",
        "duration-v1",
        "high-energy-v1",
        "negative-statement-v1",
        "lightcurve-evolution-v1",
        "counterpart-association-v1",
        "classification-interpretation-v1",
        "host-context-v1",
        "spectroscopy-v1",
    ]


def test_run_sweep_filters_duration_and_high_energy_extractors() -> None:
    sweep = run_sweep(
        limit=10,
        only_extractors=["duration", "high_energy"],
        circulars=[
            {
                "circular_id": 48,
                "subject": "GRB duration and spectrum",
                "body": (
                    "The burst has a T90 of 2.4 +/- 0.4 s. "
                    "The power law index is -1.50 +/- 0.01."
                ),
            }
        ],
    )

    assert set(sweep["extractors"]) == {"duration", "high_energy"}
    assert {annotation["label"] for annotation in sweep["annotations"]} == {
        "T90",
        "HIGH_ENERGY_PROPERTY",
    }


def test_run_sweep_records_duration_and_high_energy_signal_gaps() -> None:
    sweep = run_sweep(
        limit=10,
        only_extractors=["duration", "high_energy"],
        circulars=[
            {
                "circular_id": 70,
                "year": 2023,
                "subject": "Unconstrained duration",
                "body": "The T90 could not be constrained from the available data.",
            },
            {
                "circular_id": 71,
                "year": 2024,
                "subject": "Spectral analysis",
                "body": "The photon index could not be constrained by this fit.",
            },
            {
                "circular_id": 72,
                "year": 2025,
                "subject": "Measured duration and fluence",
                "body": "The T90 is 2.0 s and the fluence is 1.2E-06 erg/cm^2.",
            },
        ],
    )

    assert sweep["gaps"]["duration"] == [
        {
            "circular_id": 70,
            "year": 2023,
            "subject": "Unconstrained duration",
            "signal": "T90",
            "source_line": "The T90 could not be constrained from the available data.",
        }
    ]
    assert sweep["gaps"]["high_energy"] == [
        {
            "circular_id": 71,
            "year": 2024,
            "subject": "Spectral analysis",
            "signal": "photon index",
            "source_line": "The photon index could not be constrained by this fit.",
        }
    ]


def test_run_sweep_filters_and_records_negative_statement_gaps() -> None:
    sweep = run_sweep(
        limit=10,
        only_extractors=["negative_statement"],
        circulars=[
            {
                "circular_id": 73,
                "year": 2024,
                "subject": "Supernova constraint",
                "body": "We find no evidence for a supernova.",
            },
            {
                "circular_id": 74,
                "year": 2025,
                "subject": "Uncovered non-detection",
                "body": "The counterpart was not detected.",
            },
            {
                "circular_id": 75,
                "year": 2026,
                "subject": "Photometric non-detection",
                "body": "There is no optical counterpart in our i-band images.",
            },
        ],
    )

    assert set(sweep["extractors"]) == {"negative_statement"}
    assert sweep["extractors"]["negative_statement"] == {
        "n_annotations": 1,
        "n_circulars_with_at_least_one": 1,
    }
    assert len(sweep["annotations"]) == 1
    assert sweep["annotations"][0]["label"] == "NEGATIVE_STATEMENT"
    assert sweep["annotations"][0]["target"] is None
    assert sweep["gaps"]["negative_statement"] == [
        {
            "circular_id": 74,
            "year": 2025,
            "subject": "Uncovered non-detection",
            "signal": "not detected",
            "source_line": "The counterpart was not detected.",
        },
        {
            "circular_id": 75,
            "year": 2026,
            "subject": "Photometric non-detection",
            "signal": "no optical counterpart",
            "source_line": "There is no optical counterpart in our i-band images.",
        },
    ]


def test_run_sweep_filters_and_records_lightcurve_evolution_gaps() -> None:
    sweep = run_sweep(
        limit=10,
        only_extractors=["lightcurve_evolution"],
        circulars=[
            {
                "circular_id": 76,
                "year": 2024,
                "subject": "Observed optical evolution",
                "body": "The source continues to fade.",
            },
            {
                "circular_id": 77,
                "year": 2025,
                "subject": "Unconstrained light curve",
                "body": "The light curve could not be characterized.",
            },
        ],
    )

    assert set(sweep["extractors"]) == {"lightcurve_evolution"}
    assert sweep["extractors"]["lightcurve_evolution"] == {
        "n_annotations": 1,
        "n_circulars_with_at_least_one": 1,
    }
    assert sweep["annotations"][0]["label"] == "LIGHTCURVE_EVOLUTION"
    assert sweep["annotations"][0]["target"] == "counterpart"
    assert sweep["gaps"]["lightcurve_evolution"] == [
        {
            "circular_id": 77,
            "year": 2025,
            "subject": "Unconstrained light curve",
            "signal": "light curve",
            "source_line": "The light curve could not be characterized.",
        }
    ]


def test_run_sweep_filters_and_records_counterpart_association_gaps() -> None:
    sweep = run_sweep(
        limit=10,
        only_extractors=["counterpart_association"],
        circulars=[
            {
                "circular_id": 78,
                "year": 2024,
                "subject": "Optical association",
                "body": "We identify one candidate optical counterpart.",
            },
            {
                "circular_id": 79,
                "year": 2025,
                "subject": "Generic candidate discussion",
                "body": "The candidate was discussed without an association claim.",
            },
        ],
    )

    assert set(sweep["extractors"]) == {"counterpart_association"}
    assert sweep["extractors"]["counterpart_association"] == {
        "n_annotations": 1,
        "n_circulars_with_at_least_one": 1,
    }
    assert sweep["annotations"][0]["label"] == "COUNTERPART_ASSOCIATION"
    assert sweep["annotations"][0]["target"] == "counterpart"
    assert sweep["gaps"]["counterpart_association"] == [
        {
            "circular_id": 79,
            "year": 2025,
            "subject": "Generic candidate discussion",
            "signal": "candidate",
            "source_line": "The candidate was discussed without an association claim.",
        }
    ]


def test_run_sweep_filters_and_records_classification_interpretation_gaps() -> None:
    sweep = run_sweep(
        limit=10,
        only_extractors=["classification_interpretation"],
        circulars=[
            {
                "circular_id": 80,
                "year": 2024,
                "subject": "Physical interpretation",
                "body": "This rebrightening may be due to late jet activity.",
            },
            {
                "circular_id": 81,
                "year": 2025,
                "subject": "Unresolved classification",
                "body": "A supernova interpretation remains under discussion.",
            },
        ],
    )

    assert set(sweep["extractors"]) == {"classification_interpretation"}
    assert sweep["extractors"]["classification_interpretation"] == {
        "n_annotations": 1,
        "n_circulars_with_at_least_one": 1,
    }
    assert sweep["annotations"][0]["label"] == "CLASSIFICATION_INTERPRETATION"
    assert sweep["annotations"][0]["target"] == "event"
    assert sweep["gaps"]["classification_interpretation"] == [
        {
            "circular_id": 81,
            "year": 2025,
            "subject": "Unresolved classification",
            "signal": "supernova",
            "source_line": "A supernova interpretation remains under discussion.",
        }
    ]


def test_run_sweep_filters_and_records_host_context_gaps() -> None:
    sweep = run_sweep(
        limit=10,
        only_extractors=["host_context"],
        circulars=[
            {
                "circular_id": 82,
                "year": 2025,
                "subject": "Context report",
                "body": "The host association is not obvious.",
            },
            {
                "circular_id": 83,
                "year": 2026,
                "subject": "Galaxy redshift",
                "body": "A galaxy redshift of z=0.42 is reported.",
            },
        ],
    )

    assert set(sweep["extractors"]) == {"host_context"}
    assert sweep["extractors"]["host_context"] == {
        "n_annotations": 1,
        "n_circulars_with_at_least_one": 1,
    }
    assert sweep["annotations"][0]["label"] == "HOST_CONTEXT"
    assert sweep["annotations"][0]["target"] == "host"
    assert sweep["gaps"]["host_context"] == [
        {
            "circular_id": 83,
            "year": 2026,
            "subject": "Galaxy redshift",
            "signal": "galaxy",
            "source_line": "A galaxy redshift of z=0.42 is reported.",
        }
    ]


def test_run_sweep_filters_and_records_spectroscopy_gaps() -> None:
    sweep = run_sweep(
        limit=10,
        only_extractors=["spectroscopy"],
        circulars=[
            {
                "circular_id": 84,
                "year": 2025,
                "subject": "Follow-up result",
                "body": "We obtained spectroscopy with ALFOSC.",
            },
            {
                "circular_id": 85,
                "year": 2026,
                "subject": "Follow-up request",
                "body": "Further spectroscopic observations are encouraged.",
            },
        ],
    )

    assert set(sweep["extractors"]) == {"spectroscopy"}
    assert sweep["extractors"]["spectroscopy"] == {
        "n_annotations": 1,
        "n_circulars_with_at_least_one": 1,
    }
    assert sweep["annotations"][0]["label"] == "SPECTROSCOPY"
    assert sweep["annotations"][0]["target"] == "counterpart"
    assert sweep["gaps"]["spectroscopy"] == [
        {
            "circular_id": 85,
            "year": 2026,
            "subject": "Follow-up request",
            "signal": "spectroscop",
            "source_line": "Further spectroscopic observations are encouraged.",
        }
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


def test_flag_suspicious_validates_duration_and_high_energy_ranges_and_units() -> None:
    annotations = [
        _scientific_annotation(80, "duration", "T90", "0.5", "ms", "duration.t90_explicit"),
        _scientific_annotation(81, "duration", "T90", "5", "", "duration.t90_explicit"),
        _scientific_annotation(82, "high_energy", "HIGH_ENERGY_PROPERTY", "Epeak = 200", "MeV", "high_energy.epeak"),
        _scientific_annotation(83, "high_energy", "HIGH_ENERGY_PROPERTY", "fluence = 1E-10", "erg/cm^2", "high_energy.fluence"),
        _scientific_annotation(84, "high_energy", "HIGH_ENERGY_PROPERTY", "alpha = 6", "", "high_energy.alpha"),
        _scientific_annotation(85, "high_energy", "HIGH_ENERGY_PROPERTY", "Eiso = 1E44", "erg", "high_energy.eiso"),
        _scientific_annotation(86, "high_energy", "HIGH_ENERGY_PROPERTY", "peak flux = 4", "", "high_energy.peak_flux"),
        _scientific_annotation(87, "high_energy", "HIGH_ENERGY_PROPERTY", "beta = -2.3", "", "high_energy.beta"),
        _scientific_annotation(
            88,
            "high_energy",
            "HIGH_ENERGY_PROPERTY",
            "photon index = 1.7",
            "",
            "high_energy.photon_index",
        ),
        _scientific_annotation(
            89,
            "high_energy",
            "HIGH_ENERGY_PROPERTY",
            "Epeak = 200",
            "",
            "high_energy.epeak",
        ),
    ]
    rendered = {str(annotation["circular_id"]): str(annotation["text"]) for annotation in annotations}

    flagged = flag_suspicious(annotations, rendered)
    by_id = {item["circular_id"]: item for item in flagged}

    assert by_id[80]["flags"] == ["duration_out_of_range"]
    assert by_id[81]["flags"] == ["missing_unit"]
    assert by_id[82]["flags"] == ["high_energy_implausible"]
    assert by_id[83]["flags"] == ["high_energy_implausible"]
    assert by_id[84]["flags"] == ["high_energy_implausible"]
    assert by_id[85]["flags"] == ["high_energy_implausible"]
    assert by_id[86]["flags"] == ["missing_unit"]
    assert 87 not in by_id
    assert 88 not in by_id
    assert by_id[89]["flags"] == ["missing_unit"]
    assert by_id[82]["unit"] == "MeV"
    assert by_id[82]["source_line"] == "Epeak = 200"
    assert by_id[82]["circular_id"] == 82
    assert by_id[82]["rule_id"] == "high_energy.epeak"
    assert by_id[82]["value"] == "Epeak = 200"
    assert "⟦Epeak = 200⟧" in by_id[82]["context_window"]


def test_dimensionless_rules_cover_all_supported_spectral_indices() -> None:
    assert DIMENSIONLESS_RULES == frozenset(
        {
            "high_energy.powerlaw_index",
            "high_energy.photon_index",
            "high_energy.spectral_index",
            "high_energy.alpha",
            "high_energy.beta",
        }
    )


def test_samples_by_rule_include_source_text_line_and_context() -> None:
    rendered_text = "Before the fit. The T90 is 2.0 s in the detector. After the fit."
    source_text = "T90 is 2.0 s"
    start = rendered_text.index(source_text)
    annotation = {
        "circular_id": 90,
        "year": 2026,
        "extractor": "duration",
        "label": "T90",
        "value": "2.0",
        "unit": "s",
        "comment": "15-150 keV",
        "text": source_text,
        "span_start": start,
        "span_end": start + len(source_text),
        "rule_id": "duration.t90_explicit",
    }

    samples = samples_by_rule([annotation], {"90": rendered_text}, max_per_rule=1)

    assert list(samples) == ["duration.t90_explicit"]
    sample = samples["duration.t90_explicit"][0]
    assert sample["text"] == source_text
    assert sample["source_line"] == rendered_text
    assert "⟦T90 is 2.0 s⟧" in sample["context_window"]


def test_gap_examples_are_distributed_across_years() -> None:
    gaps = [
        {"circular_id": year * 100 + index, "year": year}
        for year in (2023, 2024, 2025)
        for index in range(4)
    ]

    examples = _distributed_gap_examples(gaps, max_items=6)

    assert [item["year"] for item in examples] == [2023, 2024, 2025, 2023, 2024, 2025]


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
    ("value", "unit"),
    [
        ("2023-01-01T02:16:38", None),
        ("59945.1", "mjd"),
        ("02:16:38", None),
        ("02:16:38 UT", None),
    ],
)
def test_flag_suspicious_accepts_expected_trigger_value_formats(
    value: str,
    unit: str | None,
) -> None:
    assert (
        flag_suspicious(
            [
                {
                    "circular_id": 40,
                    "extractor": "trigger_time",
                    "label": "TRIGGER_TIME",
                    "value": value,
                    "unit": unit,
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

    assert "SYNCHRONIZED ✓" in sync_status(run_meta, flagged)

    stale_meta = dict(run_meta)
    stale_meta["total_alerts"] = 3

    assert (
        "OUT OF SYNC: the JSON declares 3 alerts but 2 were read"
        in sync_status(stale_meta, flagged)
    )
