from __future__ import annotations

import unittest

import pandas as pd

from skyportal_corpus.extraction.gcn_event_matching import (
    build_conservative_variants,
    build_event_gcn_associations_dataframe,
    build_event_gcn_match_summary_dataframe,
    build_event_search_terms_dataframe,
    confidence_level_from_score,
    filter_match_summary_to_matched,
    normalize_search_term,
)


class GcnEventMatchingTests(unittest.TestCase):
    def test_normalize_search_term_compacts_grb_and_ep(self) -> None:
        self.assertEqual(normalize_search_term("GRB 250424A"), "GRB250424A")
        self.assertEqual(normalize_search_term("EP 250704a"), "EP250704A")

    def test_build_conservative_variants_for_grb_and_ep(self) -> None:
        grb_variants = build_conservative_variants("GRB250424A")
        ep_variants = build_conservative_variants("EP 250704a")

        self.assertEqual(grb_variants[0]["search_term"], "GRB 250424A")
        self.assertEqual(grb_variants[0]["variant_type"], "spaced_variant")
        self.assertEqual(ep_variants[0]["search_term"], "EP250704a")
        self.assertEqual(ep_variants[0]["variant_type"], "compact_variant")

    def test_confidence_level_from_score_uses_expected_buckets(self) -> None:
        self.assertEqual(confidence_level_from_score(100), "high_confidence")
        self.assertEqual(confidence_level_from_score(80), "high_confidence")
        self.assertEqual(confidence_level_from_score(60), "medium_confidence")
        self.assertEqual(confidence_level_from_score(40), "low_confidence")

    def test_build_event_gcn_associations_keeps_best_score(self) -> None:
        matches = pd.DataFrame(
            [
                {
                    "source_id": "GRB250424A",
                    "search_term": "GRB 250424A",
                    "search_term_normalized": "GRB250424A",
                    "variant_type": "original",
                    "origin_field": "alias",
                    "origin_value": "GRB 250424A",
                    "matched_field": "body",
                    "match_type": "original_term",
                    "match_score": 75,
                    "confidence_level": "medium_confidence",
                    "circular_id": "40224",
                    "gcn_event_id": "GRB 250424A",
                    "subject": "GRB 250424A: Example",
                    "created_at_iso": "2025-04-24T07:00:00+00:00",
                    "raw_file_path": "/tmp/40224.json",
                    "year": 2025,
                    "evidence_text": "body evidence",
                },
                {
                    "source_id": "GRB250424A",
                    "search_term": "GRB250424A",
                    "search_term_normalized": "GRB250424A",
                    "variant_type": "compact_variant",
                    "origin_field": "alias",
                    "origin_value": "GRB 250424A",
                    "matched_field": "subject",
                    "match_type": "generated_variant",
                    "match_score": 80,
                    "confidence_level": "high_confidence",
                    "circular_id": "40224",
                    "gcn_event_id": "GRB 250424A",
                    "subject": "GRB250424A: Example",
                    "created_at_iso": "2025-04-24T07:00:00+00:00",
                    "raw_file_path": "/tmp/40224.json",
                    "year": 2025,
                    "evidence_text": "subject evidence",
                },
            ]
        )

        associations = build_event_gcn_associations_dataframe(matches)

        self.assertEqual(len(associations), 1)
        self.assertEqual(int(associations.iloc[0]["best_match_score"]), 80)
        self.assertEqual(associations.iloc[0]["best_matched_field"], "subject")
        self.assertIn("GRB 250424A", associations.iloc[0]["matched_terms"])
        self.assertIn("GRB250424A", associations.iloc[0]["matched_terms"])

    def test_match_summary_orders_matched_before_no_match(self) -> None:
        terms = pd.DataFrame(
            [
                {"source_id": "EP250101a", "search_term": "EP250101a"},
                {"source_id": "GRB250101A", "search_term": "GRB250101A"},
            ]
        )
        matches = pd.DataFrame(
            [
                {
                    "source_id": "GRB250101A",
                    "search_term": "GRB250101A",
                    "search_term_normalized": "GRB250101A",
                    "variant_type": "original",
                    "origin_field": "id",
                    "origin_value": "GRB250101A",
                    "matched_field": "subject",
                    "match_type": "original_term",
                    "match_score": 100,
                    "confidence_level": "high_confidence",
                    "circular_id": "40001",
                    "gcn_event_id": "GRB 250101A",
                    "subject": "GRB 250101A: Example",
                    "created_at_iso": "2025-01-01T00:00:00+00:00",
                    "raw_file_path": "/tmp/40001.json",
                    "year": 2025,
                    "evidence_text": "subject evidence",
                }
            ]
        )

        summary = build_event_gcn_match_summary_dataframe(terms, matches)

        self.assertEqual(summary.iloc[0]["source_id"], "GRB250101A")
        self.assertEqual(summary.iloc[0]["status"], "matched")
        self.assertEqual(summary.iloc[1]["source_id"], "EP250101a")
        self.assertEqual(summary.iloc[1]["status"], "no_match")
        self.assertEqual(summary.iloc[1]["best_confidence_level"], "")

    def test_filter_match_summary_to_matched_keeps_only_matched_rows(self) -> None:
        summary = pd.DataFrame(
            [
                {"source_id": "GRB250101A", "status": "matched"},
                {"source_id": "EP250101a", "status": "medium_match"},
                {"source_id": "GCN-250101_000001", "status": "weak_match"},
                {"source_id": "GW250101a", "status": "no_match"},
            ]
        )

        filtered = filter_match_summary_to_matched(summary)

        self.assertEqual(filtered["source_id"].tolist(), ["GRB250101A", "EP250101a", "GCN-250101_000001"])
        self.assertNotIn("no_match", filtered["status"].tolist())

    def test_search_terms_build_uses_top_level_aliases_and_groups(self) -> None:
        dataframe = build_event_search_terms_dataframe(
            [
                {
                    "source_id": "GRB250101A",
                    "gcn_source_type": "grb",
                    "aliases": ["GRB 250101A"],
                    "groups": ["GRANDMA", "GRANDMA/Kilonova-Catcher"],
                }
            ]
        )

        self.assertIn("GRB250101A", dataframe["search_term"].tolist())
        self.assertIn("GRB 250101A", dataframe["search_term"].tolist())
        self.assertEqual(
            dataframe.iloc[0]["groups"],
            "GRANDMA | GRANDMA/Kilonova-Catcher",
        )


if __name__ == "__main__":
    unittest.main()
