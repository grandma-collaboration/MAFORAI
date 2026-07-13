from __future__ import annotations

from scripts.photometry_report import (
    aggregate_measurements,
    aggregate_by_year,
    build_run_meta,
    find_measurement_problems,
    find_source_overlaps,
    mark_prose_table_overlap,
)


def _measurement(**overrides):
    base = {
        "circular_id": 1,
        "measurement_type": "detection",
        "magnitude_or_limit": "19.2",
        "magnitude_error": None,
        "limit_sigma": None,
        "unit": "mag",
        "photometric_band": "R",
        "photometric_system": "AB",
        "obs_time_raw": "60426.477894",
        "obs_time_type": "mjd",
        "obs_time_reference": "absolute_time",
        "exposure_time_raw": "10x180s",
        "instrument": "KNC",
        "needs_review": False,
        "comment": None,
        "provenance_inherited": ["photometric_system=context:AB"],
        "source": "table",
        "method": "table-parse",
        "rule_id": "photometry_row.pipe",
        "table_family": "pipe",
        "source_row": "3.58 | 60426.477894 | KNC | 10x180s | R | 19.2",
        "verify": True,
    }
    base.update(overrides)
    return base


def test_aggregate_measurements_counts_core_dimensions() -> None:
    measurements = [
        _measurement(),
        _measurement(
            measurement_type="upper_limit",
            magnitude_or_limit="20.4",
            limit_sigma="3",
            photometric_band="white",
            photometric_system="Vega",
            obs_time_raw="168",
            obs_time_type="relative_to_trigger",
            obs_time_reference="trigger_time_t0",
            table_family="whitespace",
            provenance_inherited=["system_from_uvot_convention"],
        ),
        _measurement(
            magnitude_or_limit="18.9",
            photometric_band="Rc",
            photometric_system="Vega",
            provenance_inherited=[],
        ),
    ]

    aggregates = aggregate_measurements(measurements)

    assert aggregates["by_measurement_type"] == {"detection": 2, "upper_limit": 1}
    assert aggregates["by_limit_sigma"] == {
        "3": 1,
        "5": 0,
        "other": 0,
        "without_sigma": 0,
    }
    assert aggregates["by_source"] == {"table": 3}
    assert aggregates["by_photometric_system"] == {"AB": 1, "Vega": 2}
    assert aggregates["by_system_source"] == {"cell": 1, "context": 1, "uvot_convention": 1}
    assert aggregates["by_obs_time_type"] == {"mjd": 2, "relative_to_trigger": 1}
    assert aggregates["by_obs_time_reference"] == {"absolute_time": 2, "trigger_time_t0": 1}
    assert aggregates["by_table_family"] == {"pipe": 2, "whitespace": 1}
    assert aggregates["top_bands"]["R"] == 1
    assert aggregates["top_bands"]["white"] == 1
    assert aggregates["review"]["total"] == 0


def test_limit_sigma_aggregation_separates_common_other_and_missing_values() -> None:
    measurements = [
        _measurement(measurement_type="upper_limit", limit_sigma="3"),
        _measurement(measurement_type="upper_limit", limit_sigma="5"),
        _measurement(measurement_type="upper_limit", limit_sigma="4"),
        _measurement(measurement_type="upper_limit", limit_sigma=None),
        _measurement(measurement_type="detection", limit_sigma=None),
    ]

    assert aggregate_measurements(measurements)["by_limit_sigma"] == {
        "3": 1,
        "5": 1,
        "other": 1,
        "without_sigma": 1,
    }


def test_find_measurement_problems_detects_out_of_range_magnitude() -> None:
    measurements = [
        _measurement(magnitude_or_limit="99.9", needs_review=True, comment="magnitude outside expected optical range"),
        _measurement(photometric_system="unknown", provenance_inherited=[]),
        _measurement(photometric_band="C", photometric_system="unknown", provenance_inherited=[]),
        _measurement(photometric_band=None),
    ]

    problems = find_measurement_problems(measurements)

    flags = [flag for problem in problems for flag in problem["flags"]]
    assert "magnitude_out_of_range" in flags
    assert "system_unknown" in flags
    assert "band_empty" in flags
    assert not any(
        problem["photometric_band"] == "C" and "system_unknown" in problem["flags"]
        for problem in problems
    )
    assert any(
        problem["photometric_band"] == "R" and "system_unknown" in problem["flags"]
        for problem in problems
    )
    assert problems[0]["source_row"]


def test_run_meta_hash_is_deterministic_for_same_inputs() -> None:
    first = build_run_meta(
        mode="limit=300",
        n_circulars_processed=300,
        total_measurements=12,
        total_problems=1,
        generated_at="2026-01-01T00:00:00+00:00",
    )
    second = build_run_meta(
        mode="limit=300",
        n_circulars_processed=300,
        total_measurements=12,
        total_problems=1,
        generated_at="2026-01-02T00:00:00+00:00",
    )

    assert first["run_id"] == second["run_id"]


def test_aggregate_by_year_counts_core_dimensions() -> None:
    measurements = [
        _measurement(year=2023, table_family="pipe", measurement_type="upper_limit", photometric_system="unknown"),
        _measurement(year=2023, table_family="pipe", measurement_type="detection", photometric_system="AB", needs_review=True, comment="review"),
        _measurement(year=2024, table_family="whitespace", measurement_type="upper_limit", photometric_system="Vega"),
    ]
    year_stats = {
        "2023": {"processed": 2, "with_tables": 1},
        "2024": {"processed": 1, "with_tables": 1},
    }

    by_year = aggregate_by_year(measurements, year_stats)

    assert by_year["circulars"]["2023"] == {
        "processed": 2,
        "with_tables": 1,
        "with_prose": 0,
        "measurements": 2,
    }
    assert by_year["circulars"]["2024"] == {
        "processed": 1,
        "with_tables": 1,
        "with_prose": 0,
        "measurements": 1,
    }
    assert by_year["by_table_family"]["2023"] == {"pipe": 2}
    assert by_year["by_table_family"]["2024"] == {"whitespace": 1}
    assert by_year["by_measurement_type"]["2023"] == {"upper_limit": 1, "detection": 1}
    assert by_year["by_photometric_system"]["2024"] == {"Vega": 1}
    assert by_year["by_source"]["2023"] == {"table": 2}
    assert by_year["review"]["2023"]["needs_review"] == 1
    assert by_year["review"]["2024"]["percent"] == 0


def test_run_meta_records_years_covered() -> None:
    meta = build_run_meta(
        mode="per_year=200",
        n_circulars_processed=400,
        total_measurements=10,
        total_problems=2,
        years_covered=[2023, 2024],
        generated_at="2026-01-01T00:00:00+00:00",
    )

    assert meta["years_covered"] == [2023, 2024]


def test_report_separates_table_and_prose_and_detects_overlap() -> None:
    measurements = [
        _measurement(circular_id=10, subject="GRB optical photometry"),
        _measurement(
            circular_id=10,
            subject="GRB optical photometry",
            source="prose",
            method="prose",
            rule_id="photometry_prose.prose_band_eq",
            table_family=None,
            source_row="R = 19.2 +/- 0.1",
            text="R = 19.2 +/- 0.1",
            needs_review=True,
            comment="Photometric system is unknown; verify AB or Vega.",
        ),
        _measurement(circular_id=11, subject="Table only"),
    ]

    aggregates = aggregate_measurements(measurements)
    overlaps = find_source_overlaps(measurements)

    assert aggregates["by_source"] == {"prose": 1, "table": 2}
    assert aggregates["prose"]["total"] == 1
    assert aggregates["prose"]["by_rule_id"] == {
        "photometry_prose.prose_band_eq": 1
    }
    assert aggregates["prose"]["review"]["total"] == 1
    assert overlaps == [
        {
            "circular_id": 10,
            "year": None,
            "subject": "GRB optical photometry",
            "n_table_measurements": 1,
            "n_prose_measurements": 1,
        }
    ]


def test_prose_measurement_is_marked_when_same_circular_has_table() -> None:
    original = _measurement(
        source="prose",
        method="prose",
        rule_id="photometry_prose.prose_limit_upto",
        needs_review=False,
        comment=None,
        confidence=0.9,
        provenance_inherited=[],
    )

    marked = mark_prose_table_overlap(original)

    assert marked["needs_review"] is True
    assert "likely a summary of the table" in marked["comment"]
    assert marked["confidence"] == 0.65
    assert "overlap_with_photometry_table" in marked["provenance_inherited"]
    assert original["needs_review"] is False
