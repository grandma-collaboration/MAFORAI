from __future__ import annotations

import unittest

import pandas as pd

from skyportal_corpus.extraction.gcn_core_claims import (
    build_evidence_text,
    build_event_claim_summary_dataframe,
    extract_claims_from_text,
    normalize_json_safe_record,
)


class GcnCoreClaimsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.association = {
            "source_id": "GRB250129A",
            "circular_id": "39071",
            "year": 2025,
            "created_at_iso": "2025-01-29T07:24:10.847000+00:00",
            "subject": "GRB 250129A: VLT/X-shooter redshift of z = 2.151",
            "raw_file_path": "/tmp/39071.json",
            "best_match_score": 100,
            "best_confidence_level": "high_confidence",
        }

    def test_extract_redshift_with_strong_context(self) -> None:
        claims = extract_claims_from_text(
            self.association,
            "spectroscopic redshift z = 2.31 from VLT/X-shooter",
            source_field="body",
        )
        redshift_claims = [claim for claim in claims if claim["claim_type"] == "redshift"]

        self.assertEqual(len(redshift_claims), 1)
        self.assertEqual(redshift_claims[0]["normalized_value"], "2.31")
        self.assertEqual(redshift_claims[0]["claim_confidence"], "high")

    def test_do_not_extract_redshift_from_z_band_magnitude(self) -> None:
        claims = extract_claims_from_text(
            self.association,
            "The source has mag z = 22.23 AB in the z-band filter.",
            source_field="body",
        )
        redshift_claims = [claim for claim in claims if claim["claim_type"] == "redshift"]
        self.assertEqual(redshift_claims, [])

    def test_extract_non_detection_from_negative_phrase(self) -> None:
        claims = extract_claims_from_text(
            self.association,
            "We do not detect any optical counterpart in our images.",
            source_field="body",
        )
        detection_claims = [claim for claim in claims if claim["claim_type"] == "detection_status"]

        self.assertEqual(len(detection_claims), 1)
        self.assertEqual(detection_claims[0]["normalized_value"], "non_detection")

    def test_extract_simple_t90(self) -> None:
        claims = extract_claims_from_text(
            self.association,
            "T90 = 19 s in the 15-350 keV band.",
            source_field="body",
        )
        t90_claims = [claim for claim in claims if claim["claim_type"] == "duration_t90"]

        self.assertEqual(len(t90_claims), 1)
        self.assertEqual(t90_claims[0]["normalized_value"], "19")
        self.assertEqual(t90_claims[0]["extraction_rule"], "duration_t90_explicit")

    def test_trigger_time_discards_relative_t0_offsets(self) -> None:
        claims = extract_claims_from_text(
            self.association,
            "at a mid-time of t - t0 = 128 s after the trigger.",
            source_field="body",
        )
        trigger_claims = [claim for claim in claims if claim["claim_type"] == "trigger_time_t0"]

        self.assertEqual(trigger_claims, [])

    def test_trigger_time_keeps_iso_and_strips_trailing_text(self) -> None:
        claims = extract_claims_from_text(
            self.association,
            "Refined analysis gives T0 = 2025-02-07T21:47:56(UTC) and lasted for more than 120 s before the observation ended.",
            source_field="body",
        )
        trigger_claims = [claim for claim in claims if claim["claim_type"] == "trigger_time_t0"]

        self.assertEqual(len(trigger_claims), 1)
        self.assertEqual(trigger_claims[0]["normalized_value"], "2025-02-07T21:47:56")

    def test_trigger_time_converts_konus_seconds_of_day_to_clock_time(self) -> None:
        claims = extract_claims_from_text(
            self.association,
            "Konus-Wind triggered at T0=34281.198 s UT (09:31:21.198).",
            source_field="body",
        )
        trigger_claims = [claim for claim in claims if claim["claim_type"] == "trigger_time_t0"]

        self.assertEqual(len(trigger_claims), 1)
        self.assertEqual(trigger_claims[0]["normalized_value"], "09:31:21.198")

    def test_trigger_time_rejects_followup_observation_start(self) -> None:
        claims = extract_claims_from_text(
            self.association,
            "We observed the field of GRB 250129A. The observation began at 2025-01-29T05:14:39 and continued for 30 min.",
            source_field="body",
        )
        trigger_claims = [claim for claim in claims if claim["claim_type"] == "trigger_time_t0"]

        self.assertEqual(trigger_claims, [])

    def test_trigger_time_rejects_observation_time_when_line_only_says_after_trigger(self) -> None:
        claims = extract_claims_from_text(
            self.association,
            "We started observing at 2025-04-24T08:39:07 UTC (1.78h after the trigger).",
            source_field="body",
        )
        trigger_claims = [claim for claim in claims if claim["claim_type"] == "trigger_time_t0"]

        self.assertEqual(trigger_claims, [])

    def test_trigger_time_rejects_followup_starting_on_post_t0(self) -> None:
        claims = extract_claims_from_text(
            self.association,
            "A series of images were obtained starting on 2025-01-30T06:16:34 UT (i.e. 25.5 hours post T0).",
            source_field="body",
        )
        trigger_claims = [claim for claim in claims if claim["claim_type"] == "trigger_time_t0"]

        self.assertEqual(trigger_claims, [])

    def test_trigger_time_keeps_explicit_t0_but_not_later_observation_time(self) -> None:
        claims = extract_claims_from_text(
            self.association,
            (
                "We observed the field of EP240801a (T0 at 2024-08-01T09:06:03) using the telescope. "
                "The observation began at 2024-08-01T16:19:22 and continued for 1200 s."
            ),
            source_field="body",
        )
        trigger_claims = [claim for claim in claims if claim["claim_type"] == "trigger_time_t0"]

        self.assertEqual(len(trigger_claims), 1)
        self.assertEqual(trigger_claims[0]["normalized_value"], "2024-08-01T09:06:03")

    def test_trigger_time_rejects_followup_mjd_started_after_trigger(self) -> None:
        claims = extract_claims_from_text(
            self.association,
            (
                "The first epoch started at 15:28 UT on 11 March 2025 (MJD = 60745.6442), "
                "~13.52 hrs after the EP trigger."
            ),
            source_field="body",
        )
        trigger_claims = [claim for claim in claims if claim["claim_type"] == "trigger_time_t0"]

        self.assertEqual(trigger_claims, [])

    def test_t90_extracts_main_value_when_uncertainty_is_present(self) -> None:
        claims = extract_claims_from_text(
            self.association,
            "The burst duration is T90 = 101 +4/-7 s in the 4-120 keV band.",
            source_field="body",
        )
        t90_claims = [claim for claim in claims if claim["claim_type"] == "duration_t90"]

        self.assertEqual(len(t90_claims), 1)
        self.assertEqual(t90_claims[0]["normalized_value"], "101")

    def test_t90_does_not_capture_start_offset_instead_of_duration(self) -> None:
        claims = extract_claims_from_text(
            self.association,
            "T90 (15-350 keV) is 19.03 +- 1.06 sec, with the T90 starting at T0-20.76 sec due to the slew-delayed T0.",
            source_field="body",
        )
        t90_claims = [claim for claim in claims if claim["claim_type"] == "duration_t90"]

        self.assertEqual(len(t90_claims), 1)
        self.assertEqual(t90_claims[0]["normalized_value"], "19.03")

    def test_extract_simple_upper_limit(self) -> None:
        claims = extract_claims_from_text(
            self.association,
            "The 5-sigma upper limit has been about 18.3mag",
            source_field="body",
        )
        upper_limit_claims = [claim for claim in claims if claim["claim_type"] == "upper_limit_simple"]

        self.assertEqual(len(upper_limit_claims), 1)
        self.assertEqual(upper_limit_claims[0]["normalized_value"], "18.3")
        self.assertEqual(upper_limit_claims[0]["extraction_rule"], "upper_limit_context")

    def test_redshift_method_becomes_spectroscopic_when_spectrum_context_exists(self) -> None:
        claims = extract_claims_from_text(
            self.association,
            (
                "A sequence of three spectra was secured and absorption lines are "
                "detected at a common redshift z = 2.15."
            ),
            source_field="body",
        )
        redshift_claims = [claim for claim in claims if claim["claim_type"] == "redshift"]

        self.assertEqual(len(redshift_claims), 1)
        self.assertEqual(redshift_claims[0]["claim_confidence"], "high")

    def test_removed_false_trigger_detection_rule_is_not_emitted(self) -> None:
        claims = extract_claims_from_text(
            self.association,
            "This was later reported as a false trigger by the team.",
            source_field="body",
        )
        detection_claims = [claim for claim in claims if claim["claim_type"] == "detection_status"]

        self.assertEqual(detection_claims, [])

    def test_build_evidence_text_keeps_a_short_fragment(self) -> None:
        text = "prefix " + ("x" * 300) + " redshift z = 2.31 " + ("y" * 300) + " suffix"
        start = text.index("redshift")
        end = start + len("redshift z = 2.31")
        evidence = build_evidence_text(text, (start, end))

        self.assertLessEqual(len(evidence), 500)
        self.assertIn("redshift z = 2.31", evidence)

    def test_summary_includes_events_without_claims(self) -> None:
        claims = pd.DataFrame(
            [
                {
                    "source_id": "GRB250129A",
                    "circular_id": "39071",
                    "year": 2025,
                    "created_at_iso": "2025-01-29T07:24:10.847000+00:00",
                    "subject": "GRB 250129A",
                    "claim_type": "redshift",
                    "raw_value": "z = 2.31",
                    "normalized_value": "2.31",
                    "instrument_if_any": "VLT/X-shooter",
                    "evidence_text": "spectroscopic redshift z = 2.31",
                    "extraction_rule": "redshift_z_equals",
                    "claim_confidence": "high",
                    "source_field": "body",
                    "raw_file_path": "/tmp/39071.json",
                    "best_match_score": 100,
                    "best_confidence_level": "high_confidence",
                }
            ]
        )
        match_summary = pd.DataFrame(
            [
                {"source_id": "GRB250129A", "status": "matched"},
                {"source_id": "GRB250130A", "status": "matched"},
            ]
        )

        summary = build_event_claim_summary_dataframe(claims, match_summary)

        self.assertEqual(len(summary), 2)
        empty_row = summary[summary["source_id"] == "GRB250130A"].iloc[0]
        self.assertEqual(int(empty_row["n_claims"]), 0)
        self.assertNotIn("status_notes", summary.columns)
        self.assertNotIn("has_event_name", summary.columns)
        self.assertNotIn("has_coordinates", summary.columns)
        self.assertNotIn("has_localization_uncertainty", summary.columns)
        self.assertNotIn("has_followup_encouraged", summary.columns)

    def test_normalize_json_safe_record_replaces_nan_with_null(self) -> None:
        record = normalize_json_safe_record({"source_id": "GRB250129A", "best_t90_seconds": float("nan")})
        self.assertIsNone(record["best_t90_seconds"])


if __name__ == "__main__":
    unittest.main()
