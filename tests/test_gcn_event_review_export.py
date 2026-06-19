from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from skyportal_corpus.extraction.gcn_event_review_export import (
    REVIEW_HIGH_COLUMNS,
    build_astronomer_review_dataframe,
    build_legend_dataframe,
    write_astronomer_review_workbook,
)


def make_review_row(
    *,
    source_id: str,
    field_name: str,
    comparison_status: str,
    circular_id: str = "",
) -> dict[str, object]:
    return {
        "source_id": source_id,
        "groups": "GRANDMA",
        "field_name": field_name,
        "skyportal_value": "sky",
        "skyportal_value_source": "native",
        "gcn_candidate_value": "gcn",
        "gcn_candidate_context": "context",
        "comparison_status": comparison_status,
        "circular_id": circular_id,
        "evidence_text": "evidence",
        "astronomer_decision": "pending",
        "validated_value": "",
        "astronomer_notes": "",
    }


class GcnEventReviewExportTests(unittest.TestCase):
    def test_same_or_consistent_rows_are_excluded(self) -> None:
        dataframe = pd.DataFrame(
            [
                make_review_row(
                    source_id="A",
                    field_name="redshift",
                    comparison_status="same_or_consistent",
                    circular_id="1",
                ),
                make_review_row(
                    source_id="B",
                    field_name="redshift",
                    comparison_status="missing_in_skyportal",
                    circular_id="2",
                ),
            ]
        )

        exported = build_astronomer_review_dataframe(dataframe)

        self.assertEqual(len(exported), 1)
        self.assertTrue((exported["comparison_status"] != "same_or_consistent").all())

    def test_editorial_filters_keep_only_requested_status_field_pairs(self) -> None:
        dataframe = pd.DataFrame(
            [
                make_review_row(
                    source_id="A",
                    field_name="t90",
                    comparison_status="complementary_context",
                    circular_id="1",
                ),
                make_review_row(
                    source_id="B",
                    field_name="counterpart",
                    comparison_status="complementary_context",
                    circular_id="2",
                ),
                make_review_row(
                    source_id="C",
                    field_name="trigger_time",
                    comparison_status="complementary_context",
                    circular_id="3",
                ),
                make_review_row(
                    source_id="D",
                    field_name="counterpart",
                    comparison_status="gcn_only_context_flag",
                    circular_id="4",
                ),
                make_review_row(
                    source_id="E",
                    field_name="host_candidate",
                    comparison_status="gcn_only_context_flag",
                    circular_id="5",
                ),
                make_review_row(
                    source_id="F",
                    field_name="spectroscopy",
                    comparison_status="gcn_only_context_flag",
                    circular_id="6",
                ),
            ]
        )

        exported = build_astronomer_review_dataframe(dataframe)

        self.assertEqual(
            exported[["comparison_status", "field_name"]].to_dict(orient="records"),
            [
                {"comparison_status": "complementary_context", "field_name": "t90"},
                {"comparison_status": "complementary_context", "field_name": "counterpart"},
                {"comparison_status": "gcn_only_context_flag", "field_name": "counterpart"},
                {"comparison_status": "gcn_only_context_flag", "field_name": "host_candidate"},
            ],
        )

    def test_exported_dataframe_has_expected_columns(self) -> None:
        dataframe = pd.DataFrame(
            [
                make_review_row(
                    source_id="A",
                    field_name="missing",
                    comparison_status="missing_in_skyportal",
                    circular_id="1",
                )
            ]
        )
        dataframe.loc[0, "field_name"] = "redshift"

        exported = build_astronomer_review_dataframe(dataframe)

        self.assertEqual(list(exported.columns), REVIEW_HIGH_COLUMNS)
        self.assertIn("skyportal_value_source", exported.columns)

    def test_export_keeps_skyportal_value_source_values(self) -> None:
        dataframe = pd.DataFrame(
            [
                make_review_row(
                    source_id="A",
                    field_name="redshift",
                    comparison_status="missing_in_skyportal",
                    circular_id="1",
                )
            ]
        )
        dataframe.loc[0, "skyportal_value_source"] = "summary_extracted+tag_normalized"

        exported = build_astronomer_review_dataframe(dataframe)

        self.assertEqual(
            exported.iloc[0]["skyportal_value_source"],
            "summary_extracted+tag_normalized",
        )

    def test_export_order_respects_status_and_field_priority(self) -> None:
        dataframe = pd.DataFrame(
            [
                make_review_row(
                    source_id="B",
                    field_name="counterpart",
                    comparison_status="gcn_only_context_flag",
                    circular_id="9",
                ),
                make_review_row(
                    source_id="A",
                    field_name="counterpart",
                    comparison_status="complementary_context",
                    circular_id="8",
                ),
                make_review_row(
                    source_id="A",
                    field_name="trigger_time",
                    comparison_status="missing_in_skyportal",
                    circular_id="7",
                ),
                make_review_row(
                    source_id="A",
                    field_name="redshift",
                    comparison_status="possible_conflict",
                    circular_id="6",
                ),
                make_review_row(
                    source_id="A",
                    field_name="t90",
                    comparison_status="missing_in_skyportal",
                    circular_id="5",
                ),
            ]
        )

        exported = build_astronomer_review_dataframe(dataframe)

        self.assertEqual(
            exported[["comparison_status", "field_name", "source_id"]].to_dict(orient="records"),
            [
                {
                    "comparison_status": "possible_conflict",
                    "field_name": "redshift",
                    "source_id": "A",
                },
                {
                    "comparison_status": "missing_in_skyportal",
                    "field_name": "trigger_time",
                    "source_id": "A",
                },
                {
                    "comparison_status": "missing_in_skyportal",
                    "field_name": "t90",
                    "source_id": "A",
                },
                {
                    "comparison_status": "complementary_context",
                    "field_name": "counterpart",
                    "source_id": "A",
                },
                {
                    "comparison_status": "gcn_only_context_flag",
                    "field_name": "counterpart",
                    "source_id": "B",
                },
            ],
        )

    def test_workbook_contains_review_and_legend_sheets(self) -> None:
        review_dataframe = pd.DataFrame(
            [
                make_review_row(
                    source_id="A",
                    field_name="counterpart",
                    comparison_status="gcn_only_context_flag",
                    circular_id="1",
                )
            ]
        )
        review_high = build_astronomer_review_dataframe(review_dataframe)
        legend = build_legend_dataframe()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "review.xlsx"
            write_astronomer_review_workbook(review_high, legend, output_path)

            loaded_review = pd.read_excel(output_path, sheet_name="review_high")
            loaded_legend = pd.read_excel(output_path, sheet_name="legend")

        self.assertEqual(list(loaded_review.columns), REVIEW_HIGH_COLUMNS)
        legend_text = " ".join(loaded_legend.iloc[:, 0].astype(str).tolist()).lower()
        self.assertIn("afterglow", legend_text)
        self.assertIn("counterpart", legend_text)
