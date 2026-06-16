from __future__ import annotations

import unittest

import pandas as pd

from skyportal_corpus.extraction.gcn_event_review import (
    build_event_review_table_dataframe,
    comparison_status_for_row,
    review_priority_for_row,
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


class GcnEventReviewTests(unittest.TestCase):
    def test_redshift_row_is_created_as_missing_in_skyportal(self) -> None:
        selected_sources = [
            {
                "id": "GRB250101A",
                "groups": ["GRANDMA"],
                "redshift": None,
                "trigger_time": None,
                "spectrum_exists": False,
                "has_host": False,
            }
        ]
        best_claims = pd.DataFrame(
            [
                {
                    "source_id": "GRB250101A",
                    "has_gcn_match": True,
                }
            ]
        )
        claims = pd.DataFrame(
            [
                make_claim(
                    source_id="GRB250101A",
                    circular_id="1",
                    claim_type="redshift",
                    normalized_value="2.31",
                    raw_value="z = 2.31",
                    evidence_text="spectroscopic redshift z = 2.31",
                    extraction_rule="redshift_z_equals",
                    claim_confidence="high",
                )
            ]
        )

        review = build_event_review_table_dataframe(selected_sources, best_claims, claims)

        redshift_row = review[review["field_name"] == "redshift"].iloc[0]
        self.assertEqual(redshift_row["source_id"], "GRB250101A")
        self.assertEqual(redshift_row["groups"], "GRANDMA")
        self.assertEqual(redshift_row["skyportal_value"], "")
        self.assertEqual(redshift_row["gcn_candidate_value"], "2.31")
        self.assertEqual(redshift_row["gcn_candidate_context"], "spectroscopic")
        self.assertEqual(redshift_row["comparison_status"], "missing_in_skyportal")
        self.assertEqual(redshift_row["review_priority"], "high")
        self.assertEqual(redshift_row["astronomer_decision"], "pending")

    def test_spectroscopy_row_becomes_gcn_only_context_flag(self) -> None:
        selected_sources = [
            {
                "id": "GRB250102A",
                "groups": ["GRANDMA", "GRANDMA/Kilonova-Catcher"],
                "redshift": None,
                "trigger_time": None,
                "spectrum_exists": False,
                "has_host": False,
            }
        ]
        best_claims = pd.DataFrame(
            [
                {
                    "source_id": "GRB250102A",
                    "has_gcn_match": True,
                }
            ]
        )
        claims = pd.DataFrame(
            [
                make_claim(
                    source_id="GRB250102A",
                    circular_id="2",
                    claim_type="spectroscopy_mention",
                    normalized_value="spectroscopy",
                    raw_value="X-shooter",
                    instrument_if_any="VLT/X-shooter",
                    evidence_text="GRB 250102A: VLT/X-shooter spectrum",
                    extraction_rule="spectroscopy_instrument",
                    claim_confidence="medium",
                )
            ]
        )

        review = build_event_review_table_dataframe(selected_sources, best_claims, claims)

        spectroscopy_row = review[review["field_name"] == "spectroscopy"].iloc[0]
        self.assertEqual(
            spectroscopy_row["groups"],
            "GRANDMA | GRANDMA/Kilonova-Catcher",
        )
        self.assertEqual(spectroscopy_row["skyportal_value"], "false")
        self.assertEqual(spectroscopy_row["gcn_candidate_value"], "true")
        self.assertEqual(spectroscopy_row["gcn_candidate_context"], "VLT/X-shooter")
        self.assertEqual(spectroscopy_row["comparison_status"], "gcn_only_context_flag")
        self.assertEqual(spectroscopy_row["review_priority"], "medium")

    def test_redshift_difference_becomes_possible_conflict(self) -> None:
        self.assertEqual(
            comparison_status_for_row(
                field_name="redshift",
                skyportal_value=1.0,
                gcn_candidate_value="2.31",
            ),
            "possible_conflict",
        )
        self.assertEqual(
            review_priority_for_row("redshift", "possible_conflict"),
            "high",
        )

    def test_review_table_trigger_time_uses_best_absolute_candidate(self) -> None:
        selected_sources = [
            {
                "id": "GRB250106A",
                "groups": ["GRANDMA"],
                "redshift": None,
                "trigger_time": None,
                "spectrum_exists": False,
                "has_host": False,
            }
        ]
        best_claims = pd.DataFrame(
            [
                {
                    "source_id": "GRB250106A",
                    "has_gcn_match": True,
                }
            ]
        )
        claims = pd.DataFrame(
            [
                make_claim(
                    source_id="GRB250106A",
                    circular_id="1",
                    claim_type="trigger_time_t0",
                    normalized_value="09:31:21.198",
                    raw_value="T0=34281.198 s UT (09:31:21.198)",
                    extraction_rule="trigger_t0_explicit",
                    claim_confidence="high",
                ),
                make_claim(
                    source_id="GRB250106A",
                    circular_id="2",
                    claim_type="trigger_time_t0",
                    normalized_value="2026-05-04T09:31:19",
                    raw_value="2026-05-04T09:31:19 UTC",
                    extraction_rule="trigger_iso_timestamp",
                    claim_confidence="high",
                ),
            ]
        )

        review = build_event_review_table_dataframe(selected_sources, best_claims, claims)
        trigger_row = review[review["field_name"] == "trigger_time"].iloc[0]

        self.assertEqual(trigger_row["gcn_candidate_value"], "2026-05-04T09:31:19")


if __name__ == "__main__":
    unittest.main()
