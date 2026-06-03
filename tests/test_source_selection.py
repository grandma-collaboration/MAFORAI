from __future__ import annotations

import unittest
from pathlib import Path

from skyportal_corpus.extraction.source_selection import (
    assign_priority,
    build_selection_contract,
    classify_source_family,
)


def make_source(
    source_id: str,
    *,
    redshift: float | None = None,
    num_det_global: int = 2,
    comment_exists: bool = False,
) -> dict:
    return {
        "id": source_id,
        "redshift": redshift,
        "comment_exists": comment_exists,
        "summary": f"Summary for {source_id}",
        "groups": [{"id": 3, "name": "GRANDMA"}],
        "photstats": [{"num_det_global": num_det_global}],
    }


class SourceSelectionTests(unittest.TestCase):
    def test_source_family_classification(self) -> None:
        self.assertEqual(classify_source_family("GCN-260515_190819"), "grb_like")
        self.assertEqual(classify_source_family("GRB250221A"), "grb_like")
        self.assertEqual(classify_source_family("EP250702a"), "ep")
        self.assertEqual(classify_source_family("AT2025xyz"), "non_grb")

    def test_priority_assignment_matches_rules(self) -> None:
        self.assertEqual(assign_priority(0.8, False, 2), "high")
        self.assertEqual(assign_priority(4.2, True, 10), "high")
        self.assertEqual(assign_priority(1.8, False, 2), "medium")
        self.assertEqual(assign_priority(None, True, 5), "medium")
        self.assertEqual(assign_priority(None, False, 2), "low")

    def test_selection_contract_applies_targets_and_excludes_ep(self) -> None:
        sources = [
            make_source("GCN-1", redshift=0.7, num_det_global=12, comment_exists=True),
            make_source("GRB-1", redshift=4.5, num_det_global=8, comment_exists=True),
            make_source("GCN-2", redshift=1.5, num_det_global=6, comment_exists=True),
            make_source("AT2025abc", redshift=0.6, num_det_global=7, comment_exists=True),
            make_source("ZTF25abc", redshift=None, num_det_global=5, comment_exists=True),
            make_source("SN2025abc", redshift=None, num_det_global=2, comment_exists=False),
            make_source("EP250702a", redshift=0.5, num_det_global=9, comment_exists=True),
        ]
        manifest = {
            "run_label": "grandma_followup_det2_base",
            "profile_name": "has_followup",
        }

        payload = build_selection_contract(
            inventory_dir=Path("data/raw/skyportal/inventory/example"),
            output_path=Path("data/samples/example.json"),
            manifest=manifest,
            sources=sources,
            target_grb_like=2,
            target_non_grb=2,
        )

        self.assertEqual(payload["summary"]["selected_counts"]["grb_like"], 2)
        self.assertEqual(payload["summary"]["selected_counts"]["non_grb"], 2)
        self.assertEqual(payload["summary"]["input_counts"]["excluded_ep_candidates"], 1)
        self.assertEqual(
            [item["id"] for item in payload["selected"]["grb_like"]],
            ["GCN-1", "GRB-1"],
        )
        self.assertEqual(
            [item["id"] for item in payload["selected"]["non_grb"]],
            ["AT2025abc", "ZTF25abc"],
        )
        self.assertFalse(
            any(item["id"].startswith("EP") for item in payload["selected"]["non_grb"])
        )


if __name__ == "__main__":
    unittest.main()
