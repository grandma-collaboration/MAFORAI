from __future__ import annotations

import unittest

import pandas as pd

from skyportal_corpus.extraction.gcn_event_review import (
    EVENT_REVIEW_COLUMNS,
    build_event_review_table_dataframe,
    comparison_status_for_row,
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


def make_best_claims(source_id: str) -> pd.DataFrame:
    return pd.DataFrame([{"source_id": source_id, "has_gcn_match": True}])


class GcnEventReviewTests(unittest.TestCase):
    def build_review(
        self,
        *,
        selected_sources: list[dict[str, object]],
        claims: list[dict[str, object]],
    ) -> pd.DataFrame:
        baseline = build_skyportal_event_baseline_dataframe(selected_sources)
        return build_event_review_table_dataframe(
            baseline.to_dict(orient="records"),
            make_best_claims(str(selected_sources[0]["id"])),
            pd.DataFrame(claims),
        )

    def test_review_table_schema_matches_expected_output(self) -> None:
        review = self.build_review(
            selected_sources=[
                {
                    "id": "GRB250101A",
                    "groups": ["GRANDMA"],
                }
            ],
            claims=[
                make_claim(
                    source_id="GRB250101A",
                    circular_id="1",
                    claim_type="redshift",
                    normalized_value="2.31",
                    raw_value="z = 2.31",
                    evidence_text="spectroscopic redshift z = 2.31",
                    extraction_rule="redshift_z_equals",
                )
            ],
        )

        self.assertEqual(list(review.columns), EVENT_REVIEW_COLUMNS)
        self.assertNotIn("claim_confidence", review.columns)
        self.assertNotIn("review_priority", review.columns)

    def test_redshift_source_native(self) -> None:
        review = self.build_review(
            selected_sources=[
                {
                    "id": "GRB250102A",
                    "groups": ["GRANDMA"],
                    "redshift": 1.2,
                }
            ],
            claims=[
                make_claim(
                    source_id="GRB250102A",
                    circular_id="1",
                    claim_type="redshift",
                    normalized_value="1.2",
                    raw_value="z = 1.2",
                    evidence_text="spectroscopic redshift z = 1.2",
                    extraction_rule="redshift_z_equals",
                )
            ],
        )

        row = review.iloc[0]
        self.assertEqual(row["field_name"], "redshift")
        self.assertEqual(row["skyportal_value_source"], "native")

    def test_redshift_source_summary_extracted(self) -> None:
        review = self.build_review(
            selected_sources=[
                {
                    "id": "GRB250103A",
                    "groups": ["GRANDMA"],
                    "source_summary": "A spectroscopic redshift z = 2.31 is reported.",
                }
            ],
            claims=[
                make_claim(
                    source_id="GRB250103A",
                    circular_id="1",
                    claim_type="redshift",
                    normalized_value="2.31",
                    raw_value="z = 2.31",
                    evidence_text="spectroscopic redshift z = 2.31",
                    extraction_rule="redshift_z_equals",
                )
            ],
        )

        row = review.iloc[0]
        self.assertEqual(row["skyportal_value_source"], "summary_extracted")

    def test_redshift_source_native_and_summary_extracted(self) -> None:
        review = self.build_review(
            selected_sources=[
                {
                    "id": "GRB250104A",
                    "groups": ["GRANDMA"],
                    "redshift": 2.31,
                    "source_summary": "A spectroscopic redshift z = 2.31 is reported.",
                }
            ],
            claims=[
                make_claim(
                    source_id="GRB250104A",
                    circular_id="1",
                    claim_type="redshift",
                    normalized_value="2.31",
                    raw_value="z = 2.31",
                    evidence_text="spectroscopic redshift z = 2.31",
                    extraction_rule="redshift_z_equals",
                )
            ],
        )

        row = review.iloc[0]
        self.assertEqual(row["skyportal_value_source"], "native+summary_extracted")

    def test_duration_class_source_tag_normalized(self) -> None:
        review = self.build_review(
            selected_sources=[
                {
                    "id": "GRB250105A",
                    "groups": ["GRANDMA"],
                    "tags": ["LongGRB"],
                }
            ],
            claims=[
                make_claim(
                    source_id="GRB250105A",
                    circular_id="1",
                    claim_type="duration_class",
                    normalized_value="long",
                    raw_value="long GRB",
                )
            ],
        )

        row = review.iloc[0]
        self.assertEqual(row["field_name"], "duration_class")
        self.assertEqual(row["skyportal_value_source"], "tag_normalized")

    def test_duration_class_source_summary_and_tag_normalized(self) -> None:
        review = self.build_review(
            selected_sources=[
                {
                    "id": "GRB250106A",
                    "groups": ["GRANDMA"],
                    "tags": ["LongGRB"],
                    "source_summary": "This is a long GRB.",
                }
            ],
            claims=[
                make_claim(
                    source_id="GRB250106A",
                    circular_id="1",
                    claim_type="duration_class",
                    normalized_value="long",
                    raw_value="long GRB",
                )
            ],
        )

        row = review.iloc[0]
        self.assertEqual(
            row["skyportal_value_source"],
            "summary_extracted+tag_normalized",
        )

    def test_counterpart_source_summary_extracted(self) -> None:
        review = self.build_review(
            selected_sources=[
                {
                    "id": "GRB250107A",
                    "groups": ["GRANDMA"],
                    "source_summary": "An optical counterpart was identified.",
                }
            ],
            claims=[
                make_claim(
                    source_id="GRB250107A",
                    circular_id="1",
                    claim_type="counterpart_type",
                    normalized_value="optical",
                    raw_value="optical counterpart",
                )
            ],
        )

        row = review.iloc[0]
        self.assertEqual(row["field_name"], "counterpart")
        self.assertEqual(row["skyportal_value_source"], "summary_extracted")

    def test_counterpart_source_tag_normalized(self) -> None:
        review = self.build_review(
            selected_sources=[
                {
                    "id": "GRB250108A",
                    "groups": ["GRANDMA"],
                    "tags": ["Optical"],
                }
            ],
            claims=[
                make_claim(
                    source_id="GRB250108A",
                    circular_id="1",
                    claim_type="counterpart_type",
                    normalized_value="optical",
                    raw_value="optical counterpart",
                )
            ],
        )

        row = review.iloc[0]
        self.assertEqual(row["skyportal_value_source"], "tag_normalized")

    def test_spectroscopy_source_native(self) -> None:
        review = self.build_review(
            selected_sources=[
                {
                    "id": "GRB250109A",
                    "groups": ["GRANDMA"],
                    "spectrum_exists": True,
                }
            ],
            claims=[
                make_claim(
                    source_id="GRB250109A",
                    circular_id="1",
                    claim_type="spectroscopy_mention",
                    normalized_value="spectroscopy",
                    raw_value="X-shooter",
                    instrument_if_any="VLT/X-shooter",
                )
            ],
        )

        row = review.iloc[0]
        self.assertEqual(row["field_name"], "spectroscopy")
        self.assertEqual(row["skyportal_value_source"], "native")

    def test_spectroscopy_source_summary_extracted(self) -> None:
        review = self.build_review(
            selected_sources=[
                {
                    "id": "GRB250110A",
                    "groups": ["GRANDMA"],
                    "source_summary": "Spectroscopic observations were obtained with X-shooter.",
                }
            ],
            claims=[
                make_claim(
                    source_id="GRB250110A",
                    circular_id="1",
                    claim_type="spectroscopy_mention",
                    normalized_value="spectroscopy",
                    raw_value="X-shooter",
                    instrument_if_any="VLT/X-shooter",
                )
            ],
        )

        row = review.iloc[0]
        self.assertEqual(row["skyportal_value_source"], "summary_extracted")

    def test_host_candidate_source_native(self) -> None:
        review = self.build_review(
            selected_sources=[
                {
                    "id": "GRB250111A",
                    "groups": ["GRANDMA"],
                    "has_host": True,
                }
            ],
            claims=[
                make_claim(
                    source_id="GRB250111A",
                    circular_id="1",
                    claim_type="host_candidate_mention",
                    normalized_value="host_galaxy",
                    raw_value="host galaxy",
                )
            ],
        )

        row = review.iloc[0]
        self.assertEqual(row["field_name"], "host_candidate")
        self.assertEqual(row["skyportal_value_source"], "native")

    def test_host_candidate_source_summary_extracted(self) -> None:
        review = self.build_review(
            selected_sources=[
                {
                    "id": "GRB250112A",
                    "groups": ["GRANDMA"],
                    "source_summary": "A host galaxy is visible close to the transient.",
                }
            ],
            claims=[
                make_claim(
                    source_id="GRB250112A",
                    circular_id="1",
                    claim_type="host_candidate_mention",
                    normalized_value="host_galaxy",
                    raw_value="host galaxy",
                )
            ],
        )

        row = review.iloc[0]
        self.assertEqual(row["skyportal_value_source"], "summary_extracted")

    def test_redshift_difference_becomes_possible_conflict(self) -> None:
        self.assertEqual(
            comparison_status_for_row(
                field_name="redshift",
                skyportal_value=1.0,
                gcn_candidate_value="2.31",
            ),
            "possible_conflict",
        )

    def test_duration_class_overlap_is_same_or_consistent(self) -> None:
        self.assertEqual(
            comparison_status_for_row(
                field_name="duration_class",
                skyportal_value="long;ultralong",
                gcn_candidate_value="long",
            ),
            "same_or_consistent",
        )

    def test_duration_class_difference_is_possible_conflict(self) -> None:
        self.assertEqual(
            comparison_status_for_row(
                field_name="duration_class",
                skyportal_value="short",
                gcn_candidate_value="long",
            ),
            "possible_conflict",
        )

    def test_duration_class_missing_value_is_missing_in_skyportal(self) -> None:
        self.assertEqual(
            comparison_status_for_row(
                field_name="duration_class",
                skyportal_value="",
                gcn_candidate_value="long",
            ),
            "missing_in_skyportal",
        )

    def test_counterpart_subset_is_same_or_consistent(self) -> None:
        self.assertEqual(
            comparison_status_for_row(
                field_name="counterpart",
                skyportal_value="optical;xray",
                gcn_candidate_value="optical",
            ),
            "same_or_consistent",
        )

    def test_counterpart_superset_is_complementary_context(self) -> None:
        self.assertEqual(
            comparison_status_for_row(
                field_name="counterpart",
                skyportal_value="xray",
                gcn_candidate_value="optical;xray",
            ),
            "complementary_context",
        )

    def test_counterpart_no_optical_vs_positive_candidate_is_complementary_context(self) -> None:
        self.assertEqual(
            comparison_status_for_row(
                field_name="counterpart",
                skyportal_value="no_optical",
                gcn_candidate_value="optical",
            ),
            "complementary_context",
        )

    def test_review_table_trigger_time_uses_best_absolute_candidate(self) -> None:
        review = self.build_review(
            selected_sources=[
                {
                    "id": "GRB250113A",
                    "groups": ["GRANDMA"],
                }
            ],
            claims=[
                make_claim(
                    source_id="GRB250113A",
                    circular_id="1",
                    claim_type="trigger_time_t0",
                    normalized_value="09:31:21.198",
                    raw_value="T0=34281.198 s UT (09:31:21.198)",
                    extraction_rule="trigger_t0_explicit",
                    claim_confidence="high",
                ),
                make_claim(
                    source_id="GRB250113A",
                    circular_id="2",
                    claim_type="trigger_time_t0",
                    normalized_value="2026-05-04T09:31:19",
                    raw_value="2026-05-04T09:31:19 UTC",
                    extraction_rule="trigger_iso_timestamp",
                    claim_confidence="high",
                ),
            ],
        )
        trigger_row = review[review["field_name"] == "trigger_time"].iloc[0]

        self.assertEqual(trigger_row["gcn_candidate_value"], "2026-05-04T09:31:19")

    def test_review_table_sorting_prioritizes_status_then_field(self) -> None:
        selected_sources = [
            {
                "id": "GRB250114A",
                "groups": ["GRANDMA"],
                "redshift": 1.0,
            },
            {
                "id": "GRB250115A",
                "groups": ["GRANDMA"],
            },
        ]
        claims = pd.DataFrame(
            [
                make_claim(
                    source_id="GRB250114A",
                    circular_id="2",
                    claim_type="redshift",
                    normalized_value="2.31",
                    raw_value="z = 2.31",
                    evidence_text="spectroscopic redshift z = 2.31",
                    extraction_rule="redshift_z_equals",
                ),
                make_claim(
                    source_id="GRB250115A",
                    circular_id="1",
                    claim_type="trigger_time_t0",
                    normalized_value="2026-05-04T09:31:19",
                    raw_value="2026-05-04T09:31:19 UTC",
                    extraction_rule="trigger_iso_timestamp",
                ),
            ]
        )
        best_claims = pd.DataFrame(
            [
                {"source_id": "GRB250114A", "has_gcn_match": True},
                {"source_id": "GRB250115A", "has_gcn_match": True},
            ]
        )
        baseline = build_skyportal_event_baseline_dataframe(selected_sources)

        review = build_event_review_table_dataframe(
            baseline.to_dict(orient="records"),
            best_claims,
            claims,
        )

        self.assertEqual(review.iloc[0]["comparison_status"], "possible_conflict")
        self.assertEqual(review.iloc[0]["field_name"], "redshift")
        self.assertEqual(review.iloc[1]["comparison_status"], "missing_in_skyportal")
        self.assertEqual(review.iloc[1]["field_name"], "trigger_time")

    def test_review_table_counterpart_uses_union_of_claims(self) -> None:
        review = self.build_review(
            selected_sources=[
                {
                    "id": "GRB250116A",
                    "groups": ["GRANDMA"],
                    "source_summary": "An optical counterpart and X-ray afterglow were reported.",
                }
            ],
            claims=[
                make_claim(
                    source_id="GRB250116A",
                    circular_id="10",
                    claim_type="counterpart_type",
                    normalized_value="optical",
                    raw_value="optical counterpart",
                    evidence_text="The optical counterpart is detected.",
                ),
                make_claim(
                    source_id="GRB250116A",
                    circular_id="11",
                    claim_type="counterpart_type",
                    normalized_value="xray",
                    raw_value="X-ray afterglow",
                    evidence_text="The X-ray afterglow is detected.",
                ),
                make_claim(
                    source_id="GRB250116A",
                    circular_id="12",
                    claim_type="counterpart_type",
                    normalized_value="nir",
                    raw_value="NIR counterpart",
                    evidence_text="The NIR counterpart is detected.",
                ),
            ],
        )
        row = review[review["field_name"] == "counterpart"].iloc[0]

        self.assertEqual(row["gcn_candidate_value"], "optical;xray;nir")
        self.assertEqual(
            row["gcn_candidate_context"],
            "optical counterpart;X-ray afterglow;NIR counterpart",
        )
        self.assertEqual(row["circular_id"], "10 | 11 | 12")
        self.assertIn("optical: The optical counterpart is detected.", row["evidence_text"])
        self.assertIn("xray: The X-ray afterglow is detected.", row["evidence_text"])
        self.assertIn("nir: The NIR counterpart is detected.", row["evidence_text"])

    def test_review_table_counterpart_subset_is_same_or_consistent(self) -> None:
        review = self.build_review(
            selected_sources=[
                {
                    "id": "GRB250117A",
                    "groups": ["GRANDMA"],
                    "source_summary": "An optical counterpart and X-ray afterglow were reported.",
                }
            ],
            claims=[
                make_claim(
                    source_id="GRB250117A",
                    circular_id="10",
                    claim_type="counterpart_type",
                    normalized_value="optical",
                    raw_value="optical counterpart",
                    evidence_text="The optical counterpart is detected.",
                ),
            ],
        )
        row = review[review["field_name"] == "counterpart"].iloc[0]

        self.assertEqual(row["comparison_status"], "same_or_consistent")

    def test_review_table_counterpart_with_only_no_optical_is_complementary(self) -> None:
        review = self.build_review(
            selected_sources=[
                {
                    "id": "GRB250118A",
                    "groups": ["GRANDMA"],
                    "tags": ["NoOptical"],
                }
            ],
            claims=[
                make_claim(
                    source_id="GRB250118A",
                    circular_id="10",
                    claim_type="counterpart_type",
                    normalized_value="optical",
                    raw_value="optical counterpart",
                    evidence_text="The optical counterpart is detected.",
                ),
            ],
        )
        row = review[review["field_name"] == "counterpart"].iloc[0]

        self.assertEqual(row["comparison_status"], "complementary_context")

    def test_review_table_without_counterpart_claim_has_no_counterpart_row(self) -> None:
        review = self.build_review(
            selected_sources=[
                {
                    "id": "GRB250119A",
                    "groups": ["GRANDMA"],
                }
            ],
            claims=[
                make_claim(
                    source_id="GRB250119A",
                    circular_id="10",
                    claim_type="redshift",
                    normalized_value="1.23",
                    raw_value="z = 1.23",
                    evidence_text="spectroscopic redshift z = 1.23",
                    extraction_rule="redshift_z_equals",
                ),
            ],
        )

        self.assertFalse((review["field_name"] == "counterpart").any())


if __name__ == "__main__":
    unittest.main()
