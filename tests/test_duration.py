from __future__ import annotations

import pytest

from skyportal_corpus.canonical.document import render_canonical
from skyportal_corpus.extraction_v2.duration import (
    DurationExtractor,
    assemble_instrument_band_comment,
)


def _extract(body: str, subject: str = "GRB duration report"):
    doc = render_canonical(circular_id=1, subject=subject, body=body)
    annotations = DurationExtractor().extract(doc)
    assert all(annotation.verify(doc.rendered_text) for annotation in annotations)
    return annotations


def test_t90_duration_parenthetical_with_approximation_and_band() -> None:
    annotations = _extract("The burst has a duration (T90) of about 62 s (50-300 keV).")

    assert len(annotations) == 1
    annotation = annotations[0]
    assert annotation.label == "T90"
    assert annotation.value == "about 62"
    assert annotation.unit == "s"
    assert annotation.certainty == "tentative"
    assert annotation.needs_review is False
    assert annotation.comment is not None
    assert "50-300 keV" in annotation.comment


def test_t90_with_symmetric_error() -> None:
    annotations = _extract(
        "SVOM/GRM reports a T90 of 65.0 +/-8.0 s in the 15-5000 keV band."
    )

    assert len(annotations) == 1
    annotation = annotations[0]
    assert annotation.label == "T90"
    assert annotation.value == "65.0 +/- 8.0"
    assert annotation.unit == "s"
    assert annotation.certainty == "confirmed"
    assert annotation.comment is not None
    assert "SVOM/GRM" in annotation.comment
    assert "15-5000 keV" in annotation.comment


def test_paired_t90_and_t50_produce_distinct_labels() -> None:
    annotations = _extract(
        "The T90 and T50 durations measured by the SGM data are "
        "0.28 +/- 0.03 sec and 0.23 +/- 0.04 sec."
    )

    assert [(annotation.label, annotation.value) for annotation in annotations] == [
        ("T90", "0.28 +/- 0.03"),
        ("DURATION_GENERAL", "0.23 +/- 0.04"),
    ]
    assert annotations[0].comment == "SGM"
    assert annotations[1].comment == "T50, SGM"


def test_t90_with_asymmetric_error() -> None:
    annotations = _extract(
        "This burst mainly consists of a single pulse with a duration (T90) "
        "of 2.4 +0.4/-0.4 s."
    )

    assert len(annotations) == 1
    assert annotations[0].label == "T90"
    assert annotations[0].value == "2.4 +0.4/-0.4"


def test_t90_with_parenthesized_asymmetric_error() -> None:
    annotations = _extract("Using cumulative rates, we measure a T90 of 81 (+12, -27) s.")

    assert len(annotations) == 1
    assert annotations[0].value == "81 (+12, -27)"
    assert annotations[0].unit == "s"
    assert annotations[0].needs_review is False


def test_general_duration_without_t90() -> None:
    annotations = _extract(
        "The BAT light curve showed a single-peak structure with a duration of about 30 sec."
    )

    assert len(annotations) == 1
    assert annotations[0].label == "DURATION_GENERAL"
    assert annotations[0].value == "about 30"
    assert annotations[0].certainty == "tentative"


@pytest.mark.parametrize(
    ("body", "expected_value", "expected_band"),
    [
        (
            "T90 (15-350 keV) is 0.62 +- 0.05 sec (estimated error including systematics).",
            "0.62 +/- 0.05",
            "15-350 keV",
        ),
        (
            "The T90 (50-300 keV) is 31.00 + - 6.32 sec.",
            "31.00 +/- 6.32",
            "50-300 keV",
        ),
        (
            "The T90 in the 10-1000 keV band was measured to be 4.2 +/- 0.3 s.",
            "4.2 +/- 0.3",
            "10-1000 keV",
        ),
    ],
)
def test_t90_allows_band_and_verb_before_value(
    body: str,
    expected_value: str,
    expected_band: str,
) -> None:
    annotations = _extract(body)

    assert len(annotations) == 1
    annotation = annotations[0]
    assert annotation.label == "T90"
    assert annotation.value == expected_value
    assert annotation.unit in {"s", "sec"}
    assert annotation.comment is not None
    assert expected_band in annotation.comment


def test_t90_direct_value_is_not_rejected_by_nearby_relative_time() -> None:
    annotations = _extract(
        "The tail lasts until 100 seconds after the trigger. "
        "T90 (15-350 keV) is 72.86 +- 19.39 sec."
    )

    assert len(annotations) == 1
    assert annotations[0].label == "T90"
    assert annotations[0].value == "72.86 +/- 19.39"


def test_t90_without_connector() -> None:
    annotations = _extract("The light curve has a single pulse with a T90 ~ 0.1s.")

    assert len(annotations) == 1
    assert annotations[0].label == "T90"
    assert annotations[0].value == "~ 0.1"
    assert annotations[0].unit == "s"


@pytest.mark.parametrize(
    ("body", "expected_value", "expected_unit"),
    [
        ("The event lasted about 1400 seconds.", "about 1400", "seconds"),
        ("The burst lasted for 200 seconds.", "200", "seconds"),
        ("The prompt emission was lasting approximately 3 minutes.", "approximately 3", "minutes"),
    ],
)
def test_lasted_event_duration_variants(
    body: str,
    expected_value: str,
    expected_unit: str,
) -> None:
    annotations = _extract(body)

    assert len(annotations) == 1
    assert annotations[0].label == "DURATION_GENERAL"
    assert annotations[0].value == expected_value
    assert annotations[0].unit == expected_unit


@pytest.mark.parametrize(
    "body",
    [
        "The long-duration GRB was detected by Fermi/GBM.",
        "This is a short-duration burst candidate.",
    ],
)
def test_adjectival_duration_classification_is_not_a_measurement(body: str) -> None:
    assert _extract(body) == []


@pytest.mark.parametrize(
    "body",
    [
        "We obtained 4x90s exposures of the field.",
        "The exposure time of 600 s was used.",
        "The observations lasted 2 hours.",
        "The source was detected 130.9 seconds after the BAT trigger.",
    ],
)
def test_non_event_durations_are_rejected(body: str) -> None:
    assert _extract(body) == []


@pytest.mark.parametrize(
    ("instrument", "band", "expected"),
    [
        ("Fermi/GBM", "50-300 keV", "Fermi/GBM, 50-300 keV"),
        ("Konus-Wind", None, "Konus-Wind"),
        (None, "15-150 keV", "15-150 keV"),
        (None, None, None),
    ],
)
def test_shared_instrument_band_comment_format(
    instrument: str | None,
    band: str | None,
    expected: str | None,
) -> None:
    assert assemble_instrument_band_comment(instrument, band) == expected


def test_fermi_t90_comment_remains_exact() -> None:
    annotations = _extract(
        "The GBM light curve consists of multiple peaks with a duration (T90)\n"
        "of about 24.8 s (50-300 keV).",
        subject="GRB 240527B: Fermi GBM Observation",
    )

    assert len(annotations) == 1
    assert annotations[0].value == "about 24.8"
    assert annotations[0].comment == "Fermi/GBM, 50-300 keV"


def test_konus_general_duration_uses_reporting_instrument() -> None:
    annotations = _extract(
        "The burst light curve shows a single FRED-like pulse which starts at "
        "~T0-0.256 s and has a duration of ~10 s.",
        subject="Konus-Wind detection of GRB 230818A",
    )

    assert len(annotations) == 1
    assert annotations[0].label == "DURATION_GENERAL"
    assert annotations[0].value == "~ 10"
    assert annotations[0].comment == "Konus-Wind"


def test_reporting_instrument_wins_over_neighboring_episode_instrument() -> None:
    annotations = _extract(
        "The burst light curve shows two separated multipeaked emission episodes. "
        "The first episode starts at ~T0-14.1 s and has a total duration of ~150 s, "
        "the second (detected by Swift-BAT) starts at ~T0+344 s and lasts up to "
        "~T0+520 s.",
        subject="Konus-Wind detection of GRB 240529A",
    )

    assert len(annotations) == 1
    assert annotations[0].value == "~ 150"
    assert annotations[0].comment == "Konus-Wind"


@pytest.mark.parametrize(
    ("subject", "body", "expected_value"),
    [
        (
            "Konus-Wind detection of GRB 231215A",
            "The burst light curve has a duration of ~25 s.",
            "~ 25",
        ),
        (
            "Konus-Wind detection of GRB 230309A",
            "The burst light curve has a duration of ~68.9 s.",
            "~ 68.9",
        ),
        (
            "Konus-Wind detection of GRB 230818A",
            "The burst light curve has a duration of ~10 s.",
            "~ 10",
        ),
        (
            "Konus-Wind detection of GRB 240809A",
            "The burst light curve has a duration of ~36.9 s.",
            "~ 36.9",
        ),
        (
            "Konus-Wind detection of GRB 250215A / EP250215a",
            "The burst light curve has a duration of ~22 s.",
            "~ 22",
        ),
        (
            "Konus-Wind detection of GRB 251118A",
            "The burst light curve has a duration of about 25.8 s.",
            "about 25.8",
        ),
        (
            "Konus-Wind detection of GRB 250226A",
            "The burst light curve has a duration of ~32 s.",
            "~ 32",
        ),
        (
            "Konus-Wind detection of GRB 260601B/EP260601a",
            "The burst light curve has a duration of ~230 s.",
            "~ 230",
        ),
        (
            "Konus-Wind detection of GRB 260511B",
            "The duration of the burst is ~43.4 s.",
            "~ 43.4",
        ),
    ],
)
def test_konus_duration_reporting_instrument_regressions(
    subject: str,
    body: str,
    expected_value: str,
) -> None:
    annotations = _extract(body, subject=subject)

    assert len(annotations) == 1
    assert annotations[0].value == expected_value
    assert annotations[0].comment == "Konus-Wind"


@pytest.mark.parametrize(
    ("subject", "body", "expected_value"),
    [
        (
            "GRB 240527B: Fermi GBM Observation",
            "The GBM light curve consists of multiple peaks with a duration (T90) "
            "of about 24.8 s (50-300 keV).",
            "about 24.8",
        ),
        (
            "GRB 260207B: Fermi GBM Detection of a Short Burst with Extended Emission",
            "The GBM light curve consists of multiple episodes with a duration (T90) "
            "of about 56 s (50-300 keV).",
            "about 56",
        ),
    ],
)
def test_fermi_t90_reporting_instrument_regressions(
    subject: str,
    body: str,
    expected_value: str,
) -> None:
    annotations = _extract(body, subject=subject)

    assert len(annotations) == 1
    assert annotations[0].value == expected_value
    assert annotations[0].comment == "Fermi/GBM, 50-300 keV"


def test_same_clause_measurement_instrument_overrides_reporter() -> None:
    annotations = _extract(
        "The T90 as measured by Swift-BAT is 8 s.",
        subject="Konus-Wind report on a joint GRB detection",
    )

    assert len(annotations) == 1
    assert annotations[0].comment == "Swift/BAT"
