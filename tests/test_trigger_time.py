from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from skyportal_corpus.canonical.document import render_canonical
from skyportal_corpus.extraction_v2.trigger_time import TriggerTimeExtractor


def test_trigger_time_with_trigger_context() -> None:
    doc = render_canonical(
        circular_id=1,
        subject="GRB trigger report",
        body="At 02:16:38 UT on 1 Jan 2023, the Fermi GBM triggered and located the burst.",
    )

    annotations = TriggerTimeExtractor().extract(doc)

    assert len(annotations) == 1
    annotation = annotations[0]
    assert annotation.label == "TRIGGER_TIME"
    assert annotation.target == "event"
    assert annotation.certainty == "confirmed"
    assert annotation.text == doc.rendered_text[annotation.span_start : annotation.span_end]
    assert annotation.text == "02:16:38 UT on 1 Jan 2023"
    assert annotation.value == "2023-01-01T02:16:38"
    assert annotation.needs_review is False
    assert annotation.verify(doc.rendered_text)


def test_trigger_time_clock_on_date_des_overlaps_ut_clock() -> None:
    doc = render_canonical(
        circular_id=6,
        subject="GRB trigger report",
        body="At 02:16:38 UT on 1 Jan 2023, the Fermi GBM triggered and located the burst.",
    )

    annotations = TriggerTimeExtractor().extract(doc)

    assert len(annotations) == 1
    assert annotations[0].rule_id == "trigger_time.clock_on_date"
    assert annotations[0].text == "02:16:38 UT on 1 Jan 2023"


def test_trigger_time_t0_explicit_counts_as_context() -> None:
    doc = render_canonical(
        circular_id=2,
        subject="T0 report",
        body="T0 = 2023-05-10T14:22:00 UTC",
    )

    annotations = TriggerTimeExtractor().extract(doc)

    assert len(annotations) == 1
    annotation = annotations[0]
    assert annotation.rule_id == "trigger_time.t0_explicit"
    assert annotation.text == "T0 = 2023-05-10T14:22:00"
    assert annotation.value == "2023-05-10T14:22:00"
    assert annotation.verify(doc.rendered_text)


def test_trigger_time_agile_wrapped_date_and_clock_normalizes_to_iso() -> None:
    doc = render_canonical(
        circular_id=29,
        subject="AGILE trigger report",
        body="The AGILE Mini-CALorimeter detected a burst at T0 = 2023-01-04\n06:03:15.00 +/- 0.01 s (UTC).",
    )

    annotations = TriggerTimeExtractor().extract(doc)

    assert len(annotations) == 1
    annotation = annotations[0]
    assert annotation.text == "2023-01-04\n06:03:15.00"
    assert annotation.value == "2023-01-04T06:03:15.00"
    assert annotation.needs_review is False
    assert annotation.verify(doc.rendered_text)


def test_trigger_time_without_trigger_context_is_ignored() -> None:
    doc = render_canonical(
        circular_id=3,
        subject="Observation report",
        body="We observed the field at 05:30:00 UT with GOTO.",
    )

    assert TriggerTimeExtractor().extract(doc) == []


def test_trigger_number_is_not_trigger_time_even_with_context() -> None:
    doc = render_canonical(
        circular_id=7,
        subject="Trigger report",
        body="The GBM trigger 694232203.998664 / 230101095 identified the burst.",
    )

    assert TriggerTimeExtractor().extract(doc) == []


def test_trigger_time_rejects_declination_sexagesimal_coordinate() -> None:
    doc = render_canonical(
        circular_id=8,
        subject="Coordinate report",
        body="The trigger data includes a coordinate Dec. = +49:52:20.5 for the optical transient.",
    )

    assert TriggerTimeExtractor().extract(doc) == []


def test_trigger_time_rejects_ra_sexagesimal_coordinate_even_with_trigger_context() -> None:
    doc = render_canonical(
        circular_id=9,
        subject="Coordinate report",
        body="The trigger data includes a coordinate R.A. = 06:34:28.2 for the optical transient.",
    )

    assert TriggerTimeExtractor().extract(doc) == []


def test_trigger_time_rejects_master_observation_start_after_trigger_time() -> None:
    doc = render_canonical(
        circular_id=10,
        subject="MASTER observation report",
        body=(
            "errorbox 33 sec after notice time and 72 sec after trigger time at "
            "2023-01-01 02:17:51 UT, with upper limit up to 18.8 mag"
        ),
    )

    assert TriggerTimeExtractor().extract(doc) == []


def test_trigger_time_rejects_swift_xrt_observation_start() -> None:
    doc = render_canonical(
        circular_id=11,
        subject="Swift XRT report",
        body=(
            "The XRT began observing the field at 21:06:54.1 UT, "
            "130.9 seconds after the BAT trigger"
        ),
    )

    assert TriggerTimeExtractor().extract(doc) == []


def test_trigger_time_rejects_observation_window_with_relative_mid_time() -> None:
    doc = render_canonical(
        circular_id=12,
        subject="Observation window report",
        body=(
            "exposures were obtained in the Rc band from 28 March 2023 18:51:01 UT "
            "to 28 March 2023 20:13:46 UT (mid time ~4.5h after trigger)"
        ),
    )

    assert TriggerTimeExtractor().extract(doc) == []


def test_trigger_time_rejects_maxi_scan_times_with_t0_offsets() -> None:
    doc = render_canonical(
        circular_id=13,
        subject="MAXI scan report",
        body=(
            "The scan time of the five consecutive scans were 17:31:49 (t0+6463s), "
            "19:04:40 (t0+12034s)"
        ),
    )

    assert TriggerTimeExtractor().extract(doc) == []


def test_trigger_time_rejects_started_observation_with_adjacent_date() -> None:
    doc = render_canonical(
        circular_id=23,
        subject="Observation report",
        body=(
            "We started the observation at 21:39:00 UT on 2023-01-16, i.e., "
            "34.28 min after the Swift/BAT trigger"
        ),
    )

    assert TriggerTimeExtractor().extract(doc) == []


def test_trigger_time_rejects_started_observations_with_relative_suffix() -> None:
    doc = render_canonical(
        circular_id=24,
        subject="Observation report",
        body=(
            "We started observations at 23:22:37.597 UT, i.e., "
            "1.57 hrs after the Swift/BAT trigger"
        ),
    )

    assert TriggerTimeExtractor().extract(doc) == []


def test_trigger_time_rejects_starting_on_observation_with_after_trigger_suffix() -> None:
    doc = render_canonical(
        circular_id=25,
        subject="Observation report",
        body="observed the GRB location starting on Feb. 5, 10:30:47 UT (~ 56 s after trigger)",
    )

    assert TriggerTimeExtractor().extract(doc) == []


def test_trigger_time_rejects_we_observed_burst_with_later_after_trigger_suffix() -> None:
    doc = render_canonical(
        circular_id=26,
        subject="Observation report",
        body=(
            "We observed the burst with the telescope on 14:02:03 UT, "
            "Feb. 5th, 2023, about 3.5 hours after the Swift trigger"
        ),
    )

    assert TriggerTimeExtractor().extract(doc) == []


def test_trigger_time_keeps_swift_bat_trigger_time_as_single_annotation() -> None:
    doc = render_canonical(
        circular_id=14,
        subject="Swift BAT trigger report",
        body="At 21:04:43 UT, the Swift Burst Alert Telescope (BAT) triggered and located GRB 230116D",
    )

    annotations = TriggerTimeExtractor().extract(doc)

    assert len(annotations) == 1
    assert annotations[0].text == "21:04:43 UT"
    assert annotations[0].value == "21:04:43 UT"
    assert annotations[0].needs_review is True
    assert annotations[0].confidence == 0.5
    assert annotations[0].comment
    assert annotations[0].verify(doc.rendered_text)


def test_trigger_time_keeps_noise_event_trigger_time() -> None:
    doc = render_canonical(
        circular_id=27,
        subject="Swift BAT trigger report",
        body="At 00:27:49 UT, the Swift BAT was triggered on a noise event.",
    )

    annotations = TriggerTimeExtractor().extract(doc)

    assert len(annotations) == 1
    assert annotations[0].text == "00:27:49 UT"
    assert annotations[0].needs_review is True
    assert annotations[0].verify(doc.rendered_text)


def test_trigger_time_date_before_clock_normalizes_to_iso() -> None:
    doc = render_canonical(
        circular_id=17,
        subject="Swift BAT trigger report",
        body="on 2023-01-16 at 21:04:43 UT the BAT triggered and located GRB 230116D",
    )

    annotations = TriggerTimeExtractor().extract(doc)

    assert len(annotations) == 1
    assert annotations[0].text == "on 2023-01-16 at 21:04:43 UT"
    assert annotations[0].value == "2023-01-16T21:04:43"
    assert annotations[0].needs_review is False
    assert annotations[0].verify(doc.rendered_text)


def test_trigger_time_calet_clock_on_month_day_date_normalizes_to_iso() -> None:
    doc = render_canonical(
        circular_id=28,
        subject="CALET trigger report",
        body="The CALET team triggered the CGBM at 21:44:25.20 UTC on February 4, 2023.",
    )

    annotations = TriggerTimeExtractor().extract(doc)

    assert len(annotations) == 1
    assert annotations[0].text == "21:44:25.20 UTC on February 4, 2023"
    assert annotations[0].value == "2023-02-04T21:44:25.20"
    assert annotations[0].needs_review is False
    assert annotations[0].verify(doc.rendered_text)


def test_trigger_time_prose_date_before_clock_normalizes_to_iso() -> None:
    doc = render_canonical(
        circular_id=18,
        subject="Swift BAT trigger report",
        body="on 16 January 2023 at 21:04:43 UT the BAT triggered and located GRB 230116D",
    )

    annotations = TriggerTimeExtractor().extract(doc)

    assert len(annotations) == 1
    assert annotations[0].value == "2023-01-16T21:04:43"
    assert annotations[0].needs_review is False
    assert annotations[0].verify(doc.rendered_text)


def test_trigger_time_date_after_clock_normalizes_to_iso() -> None:
    doc = render_canonical(
        circular_id=19,
        subject="Swift BAT trigger report",
        body="the BAT triggered at 21:04:43 UT on 16 Jan 2023 and located GRB 230116D",
    )

    annotations = TriggerTimeExtractor().extract(doc)

    assert len(annotations) == 1
    assert annotations[0].text == "21:04:43 UT on 16 Jan 2023"
    assert annotations[0].value == "2023-01-16T21:04:43"
    assert annotations[0].needs_review is False
    assert annotations[0].verify(doc.rendered_text)


def test_trigger_time_iso_date_after_clock_normalizes_to_iso() -> None:
    doc = render_canonical(
        circular_id=20,
        subject="Swift BAT trigger report",
        body="the BAT triggered at 21:04:43 UT on 2023-01-16 and located GRB 230116D",
    )

    annotations = TriggerTimeExtractor().extract(doc)

    assert len(annotations) == 1
    assert annotations[0].value == "2023-01-16T21:04:43"
    assert annotations[0].needs_review is False
    assert annotations[0].verify(doc.rendered_text)


def test_trigger_time_comma_date_before_clock_normalizes_to_iso() -> None:
    doc = render_canonical(
        circular_id=21,
        subject="Swift BAT trigger report",
        body="2023-01-16, 21:04:43 UT: Swift BAT triggered and located GRB 230116D",
    )

    annotations = TriggerTimeExtractor().extract(doc)

    assert len(annotations) == 1
    assert annotations[0].text == "2023-01-16, 21:04:43 UT"
    assert annotations[0].value == "2023-01-16T21:04:43"
    assert annotations[0].needs_review is False
    assert annotations[0].verify(doc.rendered_text)


def test_trigger_time_date_on_previous_line_does_not_get_combined() -> None:
    doc = render_canonical(
        circular_id=22,
        subject="Swift BAT trigger report",
        body="The trigger date was 2023-01-16.\nAt 21:04:43 UT, the Swift BAT triggered GRB 230116D",
    )

    annotations = TriggerTimeExtractor().extract(doc)

    assert len(annotations) == 1
    assert annotations[0].text == "21:04:43 UT"
    assert annotations[0].value == "21:04:43 UT"
    assert annotations[0].needs_review is True
    assert annotations[0].comment
    assert annotations[0].verify(doc.rendered_text)


def test_trigger_time_sentence_boundary_does_not_combine_date_and_clock() -> None:
    doc = render_canonical(
        circular_id=30,
        subject="Sentence boundary trigger report",
        body="The event was on 2023-01-04. At 06:03:15 UT the burst triggered.",
    )

    annotations = TriggerTimeExtractor().extract(doc)

    assert len(annotations) == 1
    assert annotations[0].text == "06:03:15 UT"
    assert annotations[0].value == "06:03:15 UT"
    assert annotations[0].needs_review is True
    assert annotations[0].verify(doc.rendered_text)


def test_trigger_time_blank_line_does_not_combine_date_and_clock() -> None:
    doc = render_canonical(
        circular_id=31,
        subject="Paragraph boundary trigger report",
        body="T0 = 2023-01-04\n\n06:03:15 UT triggered the detector.",
    )

    annotations = TriggerTimeExtractor().extract(doc)

    assert len(annotations) == 1
    assert annotations[0].text == "06:03:15 UT"
    assert annotations[0].value == "06:03:15 UT"
    assert annotations[0].needs_review is True
    assert annotations[0].verify(doc.rendered_text)


def test_trigger_time_konus_wind_keeps_parenthesized_clock_without_date() -> None:
    doc = render_canonical(
        circular_id=32,
        subject="Konus-Wind trigger report",
        body="The burst triggered Konus-Wind at T0=56645.615 s UT (15:44:05.615).",
    )

    annotations = TriggerTimeExtractor().extract(doc)

    assert len(annotations) == 1
    assert annotations[0].text == "15:44:05.615"
    assert annotations[0].value == "15:44:05.615"
    assert annotations[0].needs_review is True
    assert annotations[0].verify(doc.rendered_text)


def test_trigger_time_keeps_multi_instrument_trigger_times_needing_review() -> None:
    doc = render_canonical(
        circular_id=15,
        subject="ARIES multi-instrument trigger report",
        body=(
            "GRB 230328B was triggered by Swift-BAT at 14:54:48 UT "
            "and Fermi-GBM at 14:54:47.43 UT"
        ),
    )

    annotations = TriggerTimeExtractor().extract(doc)

    assert len(annotations) == 2
    assert {annotation.text for annotation in annotations} == {"14:54:48 UT", "14:54:47.43 UT"}
    assert all(annotation.needs_review is True for annotation in annotations)
    assert all(annotation.verify(doc.rendered_text) for annotation in annotations)


def test_trigger_time_keeps_earlier_than_trigger_time_iso() -> None:
    doc = render_canonical(
        circular_id=16,
        subject="Fermi trigger time report",
        body="25 s earlier than the Fermi GBM trigger time at 2023-03-07T15:44:06",
    )

    annotations = TriggerTimeExtractor().extract(doc)

    assert len(annotations) == 1
    assert annotations[0].text == "2023-03-07T15:44:06"
    assert annotations[0].needs_review is False
    assert annotations[0].verify(doc.rendered_text)


def test_trigger_time_header_date_is_excluded() -> None:
    doc = render_canonical(
        circular_id=4,
        subject="Trigger time report",
        created_on="2023-05-10T14:22:00 UTC",
        body="The body mentions trigger context but no body time.",
    )

    assert TriggerTimeExtractor().extract(doc) == []


def test_trigger_time_multiple_candidates_need_review() -> None:
    doc = render_canonical(
        circular_id=5,
        subject="Multiple trigger report",
        body=(
            "The GBM trigger time was 01:02:03 UT. "
            "A second trigger was reported at 04:05:06 UT."
        ),
    )

    annotations = TriggerTimeExtractor().extract(doc)

    assert len(annotations) == 2
    for annotation in annotations:
        assert annotation.needs_review is True
        assert annotation.comment == (
            "Multiple times have trigger context; the annotator must choose the correct one."
        )
        assert annotation.verify(doc.rendered_text)


def test_is_observation_context_detects_negative_observation_gates() -> None:
    from skyportal_corpus.extraction_v2.trigger_time import is_observation_context

    started = "The XRT started the observation at 21:39:00 UT after setup."
    started_span = started.index("21:39:00")
    assert is_observation_context(started, started_span, started_span + len("21:39:00 UT"))

    relative_after = "The XRT began at 21:06:54.1 UT, 130.9 seconds after the BAT trigger."
    relative_span = relative_after.index("21:06:54.1")
    assert is_observation_context(
        relative_after,
        relative_span,
        relative_span + len("21:06:54.1 UT"),
    )

    t0_offset = "The scan time was 17:31:49 (t0+6463s)."
    t0_span = t0_offset.index("17:31:49")
    assert is_observation_context(t0_offset, t0_span, t0_span + len("17:31:49"))

    trigger = "At 21:04:43 UT, the Swift BAT triggered and located the burst."
    trigger_span = trigger.index("21:04:43")
    assert not is_observation_context(trigger, trigger_span, trigger_span + len("21:04:43 UT"))


def test_has_trigger_context_detects_positive_trigger_gates() -> None:
    from skyportal_corpus.extraction_v2.trigger_time import has_trigger_context

    triggered = "At 21:04:43 UT, the Swift BAT triggered and located the burst."
    triggered_span = triggered.index("21:04:43")
    assert has_trigger_context(triggered, triggered_span, triggered_span + len("21:04:43 UT"))

    t0 = "The detector reported T0 = 2023-01-04\n06:03:15.00 UTC."
    t0_span = t0.index("06:03:15.00")
    assert has_trigger_context(t0, t0_span, t0_span + len("06:03:15.00"))

    observation = "We observed the field at 05:30:00 UT with GOTO."
    observation_span = observation.index("05:30:00")
    assert not has_trigger_context(observation, observation_span, observation_span + len("05:30:00 UT"))


def test_find_adjacent_date_respects_wrapping_sentence_and_paragraph_boundaries() -> None:
    from skyportal_corpus.extraction_v2.trigger_time import find_adjacent_date

    wrapped = "T0 = 2023-01-04\n06:03:15.00 UTC"
    wrapped_span = wrapped.index("06:03:15.00")
    wrapped_date = find_adjacent_date(wrapped, wrapped_span, wrapped_span + len("06:03:15.00"))
    assert wrapped_date is not None
    assert wrapped_date.text == "2023-01-04"

    sentence = "The event was on 2023-01-04. At 06:03:15 UT the burst triggered."
    sentence_span = sentence.index("06:03:15")
    assert find_adjacent_date(sentence, sentence_span, sentence_span + len("06:03:15 UT")) is None

    paragraph = "T0 = 2023-01-04\n\n06:03:15 UT triggered the detector."
    paragraph_span = paragraph.index("06:03:15")
    assert find_adjacent_date(paragraph, paragraph_span, paragraph_span + len("06:03:15 UT")) is None

    no_date = "At 21:04:43 UT, the Swift BAT triggered."
    no_date_span = no_date.index("21:04:43")
    assert find_adjacent_date(no_date, no_date_span, no_date_span + len("21:04:43 UT")) is None


def test_normalize_to_iso_combines_date_match_or_returns_raw_time() -> None:
    from skyportal_corpus.extraction_v2.trigger_time import DateMatch, normalize_to_iso

    date = DateMatch(span_start=0, span_end=len("1 Jan 2023"), text="1 Jan 2023")
    assert normalize_to_iso("02:16:38 UT", date) == "2023-01-01T02:16:38"
    assert normalize_to_iso("21:04:43 UT", None) == "21:04:43 UT"


def test_resolve_overlaps_keeps_longest_candidate() -> None:
    from skyportal_corpus.extraction_v2.trigger_time import TimeCandidate, resolve_overlaps

    short = TimeCandidate(
        span_start=10,
        span_end=21,
        time_start=10,
        time_end=21,
        raw_time="02:16:38 UT",
        rule_id="trigger_time.clock",
        priority=4,
    )
    long = TimeCandidate(
        span_start=10,
        span_end=35,
        time_start=10,
        time_end=21,
        raw_time="02:16:38 UT",
        rule_id="trigger_time.clock_on_date",
        priority=3,
    )

    assert resolve_overlaps([short, long]) == [long]
