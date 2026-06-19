from __future__ import annotations

import unittest

import pandas as pd

from skyportal_corpus.extraction.gcn_event_enrichment import (
    build_event_best_claims_dataframe,
    build_event_enrichment_comparison_dataframe,
    count_enrichment_fields,
    compute_enrichment_priority,
)
from skyportal_corpus.extraction.skyportal_event_baseline import (
    build_skyportal_event_baseline_dataframe,
)


def make_claim(
    *,
    source_id: str,
    circular_id: str,
    claim_type: str,
    normalized_value: object = "",
    raw_value: str = "",
    instrument_if_any: str = "",
    evidence_text: str = "",
    extraction_rule: str = "rule",
    claim_confidence: str = "high",
    source_field: str = "body",
) -> dict[str, object]:
    return {
        "source_id": source_id,
        "circular_id": circular_id,
        "year": 2025,
        "created_at_iso": f"2025-01-01T00:00:{circular_id.zfill(2)}+00:00",
        "subject": f"{source_id}: Example",
        "claim_type": claim_type,
        "raw_value": raw_value or str(normalized_value),
        "normalized_value": normalized_value,
        "instrument_if_any": instrument_if_any,
        "evidence_text": evidence_text or f"evidence {claim_type} {circular_id}",
        "extraction_rule": extraction_rule,
        "claim_confidence": claim_confidence,
        "source_field": source_field,
        "raw_file_path": f"/tmp/{circular_id}.json",
        "best_match_score": 100,
        "best_confidence_level": "high_confidence",
    }


class GcnEventEnrichmentTests(unittest.TestCase):
    def test_skyportal_baseline_extracts_summary_claims(self) -> None:
        baseline = build_skyportal_event_baseline_dataframe(
            [
                {
                    "id": "GRB250201A",
                    "gcn_source_type": "grb",
                    "redshift": None,
                    "trigger_time": None,
                    "spectrum_exists": False,
                    "has_host": False,
                    "comment_exists": False,
                    "num_det_global": 3,
                    "classification_labels": [],
                    "tags": [],
                    "source_summary": (
                        "Swift/XRT reports a spectroscopic redshift z = 2.31. "
                        "T0 = 2025-02-01T10:11:12 UT. "
                        "T90 = 34.19 sec. "
                        "This is a short GRB with an optical counterpart. "
                        "Spectroscopic observations were obtained."
                    ),
                }
            ]
        )

        row = baseline.iloc[0]

        self.assertTrue(bool(row["has_source_summary"]))
        self.assertEqual(row["summary_redshift_values"], "2.31")
        self.assertEqual(row["summary_trigger_time_values"], "2025-02-01T10:11:12")
        self.assertEqual(row["summary_t90_values"], "34.19")
        self.assertEqual(row["summary_duration_classes"], "short")
        self.assertEqual(row["summary_counterpart_types"], "optical")
        self.assertTrue(bool(row["summary_has_spectroscopy"]))
        self.assertIn("redshift", row["summary_claim_types_found"])

    def test_skyportal_baseline_normalizes_only_allowed_tag_families(self) -> None:
        baseline = build_skyportal_event_baseline_dataframe(
            [
                {
                    "id": "GRB250202A",
                    "gcn_source_type": "grb",
                    "redshift": None,
                    "trigger_time": None,
                    "spectrum_exists": False,
                    "has_host": False,
                    "comment_exists": False,
                    "num_det_global": 1,
                    "classification_labels": [],
                    "tags": [
                        "LongGRB",
                        "Optical",
                        "NoOptical",
                        "Swift",
                        "Followup",
                        "Supernova",
                        "Review",
                    ],
                    "source_summary": None,
                }
            ]
        )

        row = baseline.iloc[0]

        self.assertEqual(row["tag_temporal_classes"], "long")
        self.assertEqual(row["tag_counterpart_contexts"], "optical;no_optical")
        self.assertEqual(row["tag_instrument_contexts"], "swift")
        self.assertEqual(row["tag_followup_contexts"], "followup")
        self.assertEqual(row["tag_classification_contexts"], "supernova")

    def test_no_optical_only_affects_counterpart_context(self) -> None:
        baseline = build_skyportal_event_baseline_dataframe(
            [
                {
                    "id": "GRB250203A",
                    "gcn_source_type": "grb",
                    "redshift": None,
                    "trigger_time": None,
                    "spectrum_exists": False,
                    "has_host": False,
                    "comment_exists": False,
                    "num_det_global": 1,
                    "classification_labels": [],
                    "tags": ["NoOptical"],
                    "source_summary": None,
                }
            ]
        )

        row = baseline.iloc[0]

        self.assertEqual(row["baseline_counterpart_contexts"], "no_optical")
        self.assertFalse(bool(row["baseline_has_counterpart"]))
        self.assertFalse(bool(row["baseline_has_non_detection"]))

    def test_baseline_union_uses_summary_and_tags(self) -> None:
        baseline = build_skyportal_event_baseline_dataframe(
            [
                {
                    "id": "GRB250204A",
                    "gcn_source_type": "grb",
                    "redshift": None,
                    "trigger_time": None,
                    "spectrum_exists": False,
                    "has_host": False,
                    "comment_exists": True,
                    "num_det_global": 4,
                    "classification_labels": [],
                    "tags": ["ShortGRB", "Optical"],
                    "source_summary": "A spectroscopic redshift z = 1.11 is reported.",
                }
            ]
        )

        row = baseline.iloc[0]

        self.assertTrue(bool(row["baseline_has_redshift"]))
        self.assertTrue(bool(row["baseline_has_duration_class"]))
        self.assertTrue(bool(row["baseline_has_counterpart"]))
        self.assertEqual(row["baseline_redshift_values"], "1.11")
        self.assertEqual(row["baseline_duration_classes"], "short")
        self.assertEqual(row["baseline_counterpart_contexts"], "optical")

    def test_best_redshift_prioritizes_spectroscopic_over_photometric(self) -> None:
        claims = pd.DataFrame(
            [
                make_claim(
                    source_id="GRB250101A",
                    circular_id="1",
                    claim_type="redshift",
                    normalized_value="3.2",
                    evidence_text="photometric redshift z = 3.2",
                    extraction_rule="redshift_z_equals",
                    claim_confidence="high",
                ),
                make_claim(
                    source_id="GRB250101A",
                    circular_id="2",
                    claim_type="redshift",
                    normalized_value="2.1",
                    evidence_text="spectroscopic redshift z = 2.1",
                    extraction_rule="redshift_z_equals",
                    claim_confidence="medium",
                ),
            ]
        )
        match_summary = pd.DataFrame(
            [{"source_id": "GRB250101A", "status": "matched", "n_matched_circulars": 2}]
        )

        best_claims = build_event_best_claims_dataframe(claims, match_summary)

        self.assertEqual(float(best_claims.iloc[0]["best_redshift"]), 2.1)
        self.assertEqual(best_claims.iloc[0]["best_redshift_method"], "spectroscopic")

    def test_best_redshift_prefers_photoz_rule_within_same_method(self) -> None:
        claims = pd.DataFrame(
            [
                make_claim(
                    source_id="GRB250101B",
                    circular_id="1",
                    claim_type="redshift",
                    normalized_value="19.1",
                    evidence_text="The host has g = 21.69, r = 20.15, z = 19.10 and a photo-z = 0.343.",
                    extraction_rule="redshift_z_equals",
                    claim_confidence="medium",
                ),
                make_claim(
                    source_id="GRB250101B",
                    circular_id="1",
                    claim_type="redshift",
                    normalized_value="0.343",
                    evidence_text="The host has g = 21.69, r = 20.15, z = 19.10 and a photo-z = 0.343.",
                    extraction_rule="redshift_photoz",
                    claim_confidence="medium",
                ),
            ]
        )
        match_summary = pd.DataFrame(
            [{"source_id": "GRB250101B", "status": "matched", "n_matched_circulars": 1}]
        )

        best_claims = build_event_best_claims_dataframe(claims, match_summary)

        self.assertEqual(float(best_claims.iloc[0]["best_redshift"]), 0.343)
        self.assertEqual(best_claims.iloc[0]["best_redshift_method"], "photometric")

    def test_best_t90_prefers_high_confidence_claim(self) -> None:
        claims = pd.DataFrame(
            [
                make_claim(
                    source_id="GRB250102A",
                    circular_id="1",
                    claim_type="duration_t90",
                    normalized_value="20",
                    extraction_rule="duration_t90_explicit",
                    claim_confidence="medium",
                ),
                make_claim(
                    source_id="GRB250102A",
                    circular_id="2",
                    claim_type="duration_t90",
                    normalized_value="19",
                    extraction_rule="duration_t90_explicit",
                    claim_confidence="high",
                ),
            ]
        )
        match_summary = pd.DataFrame(
            [{"source_id": "GRB250102A", "status": "matched", "n_matched_circulars": 2}]
        )

        best_claims = build_event_best_claims_dataframe(claims, match_summary)

        self.assertEqual(float(best_claims.iloc[0]["best_t90_seconds"]), 19.0)
        self.assertEqual(best_claims.iloc[0]["best_t90_unit"], "sec")

    def test_best_trigger_time_prefers_full_timestamp_over_less_complete_values(self) -> None:
        claims = pd.DataFrame(
            [
                make_claim(
                    source_id="GRB250106A",
                    circular_id="1",
                    claim_type="trigger_time_t0",
                    normalized_value="09:31:21.198",
                    extraction_rule="trigger_t0_explicit",
                    claim_confidence="high",
                ),
                make_claim(
                    source_id="GRB250106A",
                    circular_id="2",
                    claim_type="trigger_time_t0",
                    normalized_value="2026-05-04T09:31:19",
                    extraction_rule="trigger_iso_timestamp",
                    claim_confidence="high",
                ),
            ]
        )
        match_summary = pd.DataFrame(
            [{"source_id": "GRB250106A", "status": "matched", "n_matched_circulars": 2}]
        )

        best_claims = build_event_best_claims_dataframe(claims, match_summary)

        self.assertEqual(
            best_claims.iloc[0]["best_trigger_time"],
            "2026-05-04T09:31:19",
        )

    def test_instruments_found_are_unique(self) -> None:
        claims = pd.DataFrame(
            [
                make_claim(
                    source_id="GRB250103A",
                    circular_id="1",
                    claim_type="instrument_mention",
                    normalized_value="Swift/XRT",
                ),
                make_claim(
                    source_id="GRB250103A",
                    circular_id="2",
                    claim_type="instrument_mention",
                    normalized_value="Swift/XRT",
                ),
                make_claim(
                    source_id="GRB250103A",
                    circular_id="3",
                    claim_type="instrument_mention",
                    normalized_value="VLT/X-shooter",
                ),
            ]
        )
        match_summary = pd.DataFrame(
            [{"source_id": "GRB250103A", "status": "matched", "n_matched_circulars": 3}]
        )

        best_claims = build_event_best_claims_dataframe(claims, match_summary)

        self.assertEqual(
            best_claims.iloc[0]["instruments_found"],
            "Swift/XRT;VLT/X-shooter",
        )

    def test_detection_flags_capture_detection_and_non_detection(self) -> None:
        claims = pd.DataFrame(
            [
                make_claim(
                    source_id="GRB250104A",
                    circular_id="1",
                    claim_type="detection_status",
                    normalized_value="detected",
                ),
                make_claim(
                    source_id="GRB250104A",
                    circular_id="2",
                    claim_type="detection_status",
                    normalized_value="non_detection",
                ),
            ]
        )
        match_summary = pd.DataFrame(
            [{"source_id": "GRB250104A", "status": "matched", "n_matched_circulars": 2}]
        )

        best_claims = build_event_best_claims_dataframe(claims, match_summary)
        row = best_claims.iloc[0]

        self.assertTrue(bool(row["has_detection"]))
        self.assertTrue(bool(row["has_non_detection"]))
        self.assertNotIn("has_retraction", best_claims.columns)

    def test_comparison_marks_gcn_adds_redshift(self) -> None:
        best_claims = pd.DataFrame(
            [
                {
                    "source_id": "GRB250105A",
                    "has_gcn_match": True,
                    "match_status": "matched",
                    "n_matched_circulars": 2,
                    "n_claims": 5,
                    "n_circulars_with_claims": 2,
                    "best_trigger_time": "",
                    "best_trigger_time_circular_id": "",
                    "best_trigger_time_evidence": "",
                    "best_t90_seconds": None,
                    "best_t90_unit": "",
                    "best_t90_circular_id": "",
                    "best_t90_evidence": "",
                    "best_duration_class": "",
                    "best_duration_class_evidence": "",
                    "best_redshift": 1.23,
                    "best_redshift_method": "spectroscopic",
                    "best_redshift_circular_id": "10",
                    "best_redshift_evidence": "z = 1.23",
                    "has_counterpart": False,
                    "counterpart_types": "",
                    "has_detection": False,
                    "has_non_detection": False,
                    "has_upper_limit": False,
                    "has_spectroscopy": False,
                    "has_host_candidate": False,
                    "instruments_found": "",
                    "classification_flags": "",
                    "claim_types_found": "redshift",
                }
            ]
        )
        payload = [
            {
                "id": "GRB250105A",
                "gcn_source_type": "grb",
                "trigger_time": None,
                "redshift": None,
                "classification_labels": [],
                "spectrum_exists": False,
                "has_host": False,
                "comment_exists": False,
                "num_det_global": 0,
                "tags": [],
                "source_summary": None,
            }
        ]

        baseline = build_skyportal_event_baseline_dataframe(payload)
        comparison = build_event_enrichment_comparison_dataframe(baseline, best_claims)

        self.assertTrue(bool(comparison.iloc[0]["gcn_adds_redshift"]))

    def test_comparison_uses_summary_and_tags_before_marking_gcn_as_new(self) -> None:
        best_claims = pd.DataFrame(
            [
                {
                    "source_id": "GRB250205A",
                    "has_gcn_match": True,
                    "match_status": "matched",
                    "n_matched_circulars": 1,
                    "n_claims": 3,
                    "n_circulars_with_claims": 1,
                    "best_trigger_time": "",
                    "best_trigger_time_circular_id": "",
                    "best_trigger_time_evidence": "",
                    "best_t90_seconds": None,
                    "best_t90_unit": "",
                    "best_t90_circular_id": "",
                    "best_t90_evidence": "",
                    "best_duration_class": "",
                    "best_duration_class_evidence": "",
                    "best_redshift": 2.31,
                    "best_redshift_method": "spectroscopic",
                    "best_redshift_circular_id": "10",
                    "best_redshift_evidence": "z = 2.31",
                    "has_counterpart": True,
                    "counterpart_types": "optical",
                    "has_detection": False,
                    "has_non_detection": False,
                    "has_upper_limit": False,
                    "has_spectroscopy": True,
                    "has_host_candidate": False,
                    "instruments_found": "Swift/XRT",
                    "classification_flags": "",
                    "claim_types_found": "redshift;counterpart_type;spectroscopy_mention",
                }
            ]
        )
        payload = [
            {
                "id": "GRB250205A",
                "gcn_source_type": "grb",
                "trigger_time": None,
                "redshift": None,
                "classification_labels": [],
                "spectrum_exists": False,
                "has_host": False,
                "comment_exists": False,
                "num_det_global": 0,
                "tags": ["Optical"],
                "source_summary": "A spectroscopic redshift z = 2.31 is reported.",
            }
        ]

        baseline = build_skyportal_event_baseline_dataframe(payload)
        comparison = build_event_enrichment_comparison_dataframe(baseline, best_claims)
        row = comparison.iloc[0]

        self.assertFalse(bool(row["gcn_adds_redshift"]))
        self.assertFalse(bool(row["gcn_adds_counterpart"]))

    def test_missing_summary_and_tags_are_handled_as_empty(self) -> None:
        baseline = build_skyportal_event_baseline_dataframe(
            [
                {
                    "id": "GRB250206A",
                    "gcn_source_type": "grb",
                    "redshift": None,
                    "trigger_time": None,
                    "spectrum_exists": False,
                    "has_host": False,
                    "comment_exists": False,
                    "num_det_global": 0,
                    "classification_labels": [],
                    "source_summary": None,
                }
            ]
        )

        row = baseline.iloc[0]

        self.assertFalse(bool(row["has_source_summary"]))
        self.assertEqual(row["summary_claim_types_found"], "")
        self.assertEqual(row["tag_temporal_classes"], "")

    def test_compute_enrichment_priority_uses_expected_rules(self) -> None:
        self.assertEqual(
            compute_enrichment_priority(
                {
                    "has_gcn_match": True,
                    "n_claims": 3,
                    "gcn_adds_redshift": True,
                    "gcn_adds_t90": False,
                    "gcn_adds_counterpart": False,
                    "gcn_adds_spectroscopy": False,
                    "gcn_adds_trigger_time": False,
                    "gcn_adds_host_candidate": False,
                    "gcn_adds_upper_limit": False,
                    "gcn_adds_non_detection": False,
                    "n_enrichment_fields": 1,
                }
            ),
            "high",
        )
        self.assertEqual(
            compute_enrichment_priority(
                {
                    "has_gcn_match": True,
                    "n_claims": 2,
                    "gcn_adds_redshift": False,
                    "gcn_adds_t90": False,
                    "gcn_adds_counterpart": False,
                    "gcn_adds_spectroscopy": False,
                    "gcn_adds_trigger_time": True,
                    "gcn_adds_host_candidate": False,
                    "gcn_adds_upper_limit": False,
                    "gcn_adds_non_detection": False,
                    "n_enrichment_fields": 1,
                }
            ),
            "medium",
        )
        self.assertEqual(
            compute_enrichment_priority(
                {
                    "has_gcn_match": True,
                    "n_claims": 1,
                    "gcn_adds_redshift": False,
                    "gcn_adds_t90": False,
                    "gcn_adds_counterpart": False,
                    "gcn_adds_spectroscopy": False,
                    "gcn_adds_trigger_time": False,
                    "gcn_adds_host_candidate": False,
                    "gcn_adds_upper_limit": False,
                    "gcn_adds_non_detection": False,
                    "gcn_adds_detection": True,
                    "n_enrichment_fields": 1,
                }
            ),
            "low",
        )
        self.assertEqual(
            compute_enrichment_priority(
                {
                    "has_gcn_match": True,
                    "n_claims": 1,
                    "gcn_adds_redshift": False,
                    "gcn_adds_t90": False,
                    "gcn_adds_counterpart": False,
                    "gcn_adds_spectroscopy": False,
                    "gcn_adds_trigger_time": False,
                    "gcn_adds_host_candidate": False,
                    "gcn_adds_upper_limit": False,
                    "gcn_adds_non_detection": False,
                    "gcn_adds_detection": False,
                    "n_enrichment_fields": 0,
                }
            ),
            "none",
        )

    def test_count_enrichment_fields_includes_detection_upper_limit_and_non_detection(self) -> None:
        self.assertEqual(
            count_enrichment_fields(
                {
                    "gcn_adds_redshift": False,
                    "gcn_adds_classification": False,
                    "gcn_adds_spectroscopy": False,
                    "gcn_adds_host_candidate": False,
                    "gcn_adds_t90": False,
                    "gcn_adds_duration_class": False,
                    "gcn_adds_trigger_time": False,
                    "gcn_adds_counterpart": False,
                    "gcn_adds_detection": True,
                    "gcn_adds_non_detection": True,
                    "gcn_adds_upper_limit": True,
                }
            ),
            3,
        )

    def test_comparison_only_keeps_events_with_match(self) -> None:
        best_claims = pd.DataFrame(
            [
                {
                    "source_id": "GRB250106A",
                    "has_gcn_match": True,
                    "match_status": "matched",
                    "n_matched_circulars": 1,
                    "n_claims": 2,
                    "n_circulars_with_claims": 1,
                    "best_trigger_time": "12:34:56",
                    "best_trigger_time_circular_id": "10",
                    "best_trigger_time_evidence": "At 12:34:56 UT",
                    "best_t90_seconds": None,
                    "best_t90_unit": "",
                    "best_t90_circular_id": "",
                    "best_t90_evidence": "",
                    "best_duration_class": "",
                    "best_duration_class_evidence": "",
                    "best_redshift": None,
                    "best_redshift_method": "",
                    "best_redshift_circular_id": "",
                    "best_redshift_evidence": "",
                    "has_counterpart": False,
                    "counterpart_types": "",
                    "has_detection": False,
                    "has_non_detection": False,
                    "has_upper_limit": False,
                    "has_spectroscopy": False,
                    "has_host_candidate": False,
                    "instruments_found": "",
                    "classification_flags": "",
                    "claim_types_found": "trigger_time_t0",
                },
                {
                    "source_id": "EP250106a",
                    "has_gcn_match": False,
                    "match_status": "no_match",
                    "n_matched_circulars": 0,
                    "n_claims": 0,
                    "n_circulars_with_claims": 0,
                    "best_trigger_time": "",
                    "best_trigger_time_circular_id": "",
                    "best_trigger_time_evidence": "",
                    "best_t90_seconds": None,
                    "best_t90_unit": "",
                    "best_t90_circular_id": "",
                    "best_t90_evidence": "",
                    "best_duration_class": "",
                    "best_duration_class_evidence": "",
                    "best_redshift": None,
                    "best_redshift_method": "",
                    "best_redshift_circular_id": "",
                    "best_redshift_evidence": "",
                    "has_counterpart": False,
                    "counterpart_types": "",
                    "has_detection": False,
                    "has_non_detection": False,
                    "has_upper_limit": False,
                    "has_spectroscopy": False,
                    "has_host_candidate": False,
                    "instruments_found": "",
                    "classification_flags": "",
                    "claim_types_found": "",
                },
            ]
        )
        payload = [
            {
                "id": "GRB250106A",
                "gcn_source_type": "grb",
                "trigger_time": None,
                "redshift": None,
                "classification_labels": [],
                "spectrum_exists": False,
                "has_host": False,
                "comment_exists": False,
                "num_det_global": 0,
                "tags": [],
                "source_summary": None,
            },
            {
                "id": "EP250106a",
                "gcn_source_type": "ep",
                "trigger_time": None,
                "redshift": None,
                "classification_labels": [],
                "spectrum_exists": False,
                "has_host": False,
                "comment_exists": False,
                "num_det_global": 0,
                "tags": [],
                "source_summary": None,
            },
        ]

        baseline = build_skyportal_event_baseline_dataframe(payload)
        comparison = build_event_enrichment_comparison_dataframe(baseline, best_claims)

        self.assertEqual(comparison["source_id"].tolist(), ["GRB250106A"])
        self.assertIn("skyportal_has_trigger_time", comparison.columns)
        self.assertIn("gcn_adds_trigger_time", comparison.columns)
        self.assertTrue(bool(comparison.iloc[0]["gcn_adds_trigger_time"]))
        self.assertNotIn("gcn_has_coordinates", comparison.columns)
        self.assertNotIn("review_status", comparison.columns)

    def test_comparison_counts_non_detection_and_upper_limit_as_enrichment_fields(self) -> None:
        best_claims = pd.DataFrame(
            [
                {
                    "source_id": "GRB250107A",
                    "has_gcn_match": True,
                    "match_status": "matched",
                    "n_matched_circulars": 1,
                    "n_claims": 3,
                    "n_circulars_with_claims": 1,
                    "best_trigger_time": "",
                    "best_trigger_time_circular_id": "",
                    "best_trigger_time_evidence": "",
                    "best_t90_seconds": None,
                    "best_t90_unit": "",
                    "best_t90_circular_id": "",
                    "best_t90_evidence": "",
                    "best_duration_class": "",
                    "best_duration_class_evidence": "",
                    "best_redshift": None,
                    "best_redshift_method": "",
                    "best_redshift_circular_id": "",
                    "best_redshift_evidence": "",
                    "has_counterpart": False,
                    "counterpart_types": "",
                    "has_detection": False,
                    "has_non_detection": True,
                    "has_upper_limit": True,
                    "has_spectroscopy": False,
                    "has_host_candidate": False,
                    "instruments_found": "",
                    "classification_flags": "",
                    "claim_types_found": "detection_status;upper_limit_simple",
                }
            ]
        )
        payload = [
            {
                "id": "GRB250107A",
                "gcn_source_type": "grb",
                "aliases": "[]",
                "trigger_time": 12345.0,
                "redshift": None,
                "classification_labels": [],
                "spectrum_exists": False,
                "has_host": False,
                "comment_exists": False,
                "num_det_global": 0,
                "tags": [],
                "source_summary": None,
            }
        ]

        baseline = build_skyportal_event_baseline_dataframe(payload)
        comparison = build_event_enrichment_comparison_dataframe(baseline, best_claims)

        self.assertEqual(int(comparison.iloc[0]["n_enrichment_fields"]), 2)
        self.assertEqual(comparison.iloc[0]["enrichment_priority"], "medium")


if __name__ == "__main__":
    unittest.main()
