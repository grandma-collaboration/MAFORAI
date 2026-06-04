from __future__ import annotations

import unittest
from pathlib import Path

from skyportal_corpus.extraction.source_selection import (
    assign_gcn_bundle_priority,
    build_gcn_bundle_selection_contract,
    build_gcn_grandma_contract,
    classify_gcn_derived_type,
)


def make_source(
    source_id: str,
    *,
    redshift: float | None = None,
    num_det_global: int = 2,
    comment_exists: bool = False,
    host_id: int | None = None,
    classifications: list[str] | None = None,
) -> dict:
    return {
        "id": source_id,
        "redshift": redshift,
        "comment_exists": comment_exists,
        "host_id": host_id,
        "summary": f"Summary for {source_id}",
        "groups": [{"id": 3, "name": "GRANDMA"}],
        "photstats": [{"num_det_global": num_det_global}],
        "classifications": [
            {"classification": label} for label in (classifications or [])
        ],
    }


class SourceSelectionTests(unittest.TestCase):
    def test_gcn_derived_subtype_classification(self) -> None:
        self.assertEqual(classify_gcn_derived_type("GCN-260515_190819"), "gcn")
        self.assertEqual(classify_gcn_derived_type("GRB250221A"), "grb")
        self.assertEqual(classify_gcn_derived_type("GW250101A"), "gw")
        self.assertEqual(classify_gcn_derived_type("EP250702a"), "ep")
        self.assertEqual(classify_gcn_derived_type("AT2025xyz"), "other")

    def test_gcn_grandma_contract_keeps_all_gcn_derived_subtypes(self) -> None:
        sources = [
            make_source("GCN-1", redshift=0.7, num_det_global=12, comment_exists=True),
            make_source("GRB-1", redshift=4.5, num_det_global=8, comment_exists=True),
            make_source("GW-1", redshift=None, num_det_global=1, comment_exists=False),
            make_source("EP-1", redshift=0.5, num_det_global=9, comment_exists=True, host_id=123),
            make_source("AT2025abc", redshift=0.6, num_det_global=7, comment_exists=True),
        ]
        manifest = {
            "run_label": "grandma_base",
            "profile_name": "grandma_base",
        }

        payload = build_gcn_grandma_contract(
            inventory_dir=Path("data/raw/skyportal/inventory/example"),
            output_path=Path("data/samples/gcn_grandma_example.json"),
            manifest=manifest,
            sources=sources,
        )

        self.assertEqual(payload["summary"]["input_counts"]["gcn_derived_sources"], 4)
        self.assertEqual(payload["summary"]["input_counts"]["by_type"]["gcn"], 1)
        self.assertEqual(payload["summary"]["input_counts"]["by_type"]["grb"], 1)
        self.assertEqual(payload["summary"]["input_counts"]["by_type"]["gw"], 1)
        self.assertEqual(payload["summary"]["input_counts"]["by_type"]["ep"], 1)
        self.assertEqual(
            [item["id"] for item in payload["sources"]],
            ["EP-1", "GCN-1", "GRB-1", "GW-1"],
        )
        self.assertTrue(payload["sources"][0]["comment_exists"])
        self.assertEqual(payload["sources"][0]["num_det_global"], 9)
        self.assertTrue(payload["sources"][0]["has_host"])

    def test_gcn_priority_assignment_matches_current_rules(self) -> None:
        priority, score = assign_gcn_bundle_priority(
            {
                "redshift": 0.8,
                "comment_exists": False,
                "num_det_global": 2,
                "classification_labels": [],
            }
        )
        self.assertEqual(priority, "high")
        self.assertGreater(score, 0)

        priority, _ = assign_gcn_bundle_priority(
            {
                "redshift": 1.8,
                "comment_exists": False,
                "num_det_global": 2,
                "classification_labels": [],
            }
        )
        self.assertEqual(priority, "medium")

        priority, _ = assign_gcn_bundle_priority(
            {
                "redshift": None,
                "comment_exists": False,
                "num_det_global": 0,
                "classification_labels": [],
            }
        )
        self.assertEqual(priority, "low")

    def test_selected_sources_contract_keeps_all_gcn_subtypes_in_one_pool(self) -> None:
        base_payload = {
            "gcn_grandma_run": {
                "inventory_run_label": "grandma_base",
            },
            "sources": [
                {
                    "id": "GCN-1",
                    "gcn_source_type": "gcn",
                    "redshift": 0.8,
                    "comment_exists": True,
                    "num_det_global": 12,
                    "has_host": False,
                    "groups": ["GRANDMA"],
                    "classification_labels": ["GRB"],
                    "source_summary": "Summary 1",
                },
                {
                    "id": "EP-1",
                    "gcn_source_type": "ep",
                    "redshift": None,
                    "comment_exists": True,
                    "num_det_global": 8,
                    "has_host": False,
                    "groups": ["GRANDMA"],
                    "classification_labels": ["GO GRANDMA"],
                    "source_summary": "Summary 2",
                },
                {
                    "id": "GW-1",
                    "gcn_source_type": "gw",
                    "redshift": None,
                    "comment_exists": False,
                    "num_det_global": 0,
                    "has_host": False,
                    "groups": ["GRANDMA"],
                    "classification_labels": [],
                    "source_summary": "Summary 3",
                },
            ],
        }

        payload = build_gcn_bundle_selection_contract(
            gcn_grandma_path=Path("data/samples/gcn_grandma_example.json"),
            output_path=Path("data/samples/selected_sources_for_bundles.json"),
            payload=base_payload,
        )

        self.assertEqual(payload["summary"]["input_counts"]["gcn_derived_sources"], 3)
        self.assertEqual(payload["summary"]["input_counts"]["by_type"]["gcn"], 1)
        self.assertEqual(payload["summary"]["input_counts"]["by_type"]["ep"], 1)
        self.assertEqual(payload["summary"]["input_counts"]["by_type"]["gw"], 1)
        self.assertEqual(payload["summary"]["priority_counts"]["high"], 1)
        self.assertEqual(payload["summary"]["priority_counts"]["medium"], 1)
        self.assertEqual(payload["summary"]["priority_counts"]["low"], 1)
        self.assertEqual(
            [item["id"] for item in payload["selected_sources"]],
            ["GCN-1", "EP-1", "GW-1"],
        )


if __name__ == "__main__":
    unittest.main()
