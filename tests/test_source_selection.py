from __future__ import annotations

import unittest
from pathlib import Path

from skyportal_corpus.extraction.source_selection import (
    build_gcn_grandma_contract,
    classify_gcn_derived_type,
)


def make_source(
    source_id: str,
    *,
    alias: list[str] | None = None,
    tags: list[str] | None = None,
    redshift: float | None = None,
    t0: float | None = None,
    num_det_global: int = 2,
    comment_exists: bool = False,
    spectrum_exists: bool = False,
    host_id: int | None = None,
    classifications: list[str] | None = None,
    tns_name: str | None = None,
    ra: float | None = None,
    dec: float | None = None,
) -> dict:
    return {
        "id": source_id,
        "alias": alias,
        "redshift": redshift,
        "t0": t0,
        "tns_name": tns_name,
        "ra": ra,
        "dec": dec,
        "comment_exists": comment_exists,
        "spectrum_exists": spectrum_exists,
        "host_id": host_id,
        "summary": f"Summary for {source_id}",
        "groups": [{"id": 3, "name": "GRANDMA"}],
        "photstats": [{"num_det_global": num_det_global}],
        "tags": [{"name": tag} for tag in (tags or [])],
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
            make_source(
                "GCN-1",
                redshift=0.7,
                t0=61200.1,
                num_det_global=12,
                comment_exists=True,
                tags=["LongGRB", "Swift"],
            ),
            make_source(
                "GRB-1",
                redshift=4.5,
                t0=61199.2,
                num_det_global=8,
                comment_exists=True,
                spectrum_exists=True,
                tags=["ShortGRB"],
            ),
            make_source("GW-1", redshift=None, num_det_global=1, comment_exists=False),
            make_source("EP-1", redshift=0.5, num_det_global=9, comment_exists=True, host_id=123),
            make_source("AT2025abc", redshift=0.6, num_det_global=7, comment_exists=True),
        ]
        inventory_runs = [
            {
                "inventory_dir": Path("data/raw/skyportal/inventory/source_inventory_gcn_example"),
                "manifest": {
                    "run_label": "gcn",
                    "profile_name": "gcn",
                },
                "sources": sources,
            }
        ]

        payload = build_gcn_grandma_contract(
            inventory_runs=inventory_runs,
            output_path=Path("data/samples/gcn_grandma_example.json"),
        )

        self.assertEqual(payload["summary"]["input_counts"]["gcn_derived_sources"], 4)
        self.assertEqual(payload["summary"]["input_counts"]["by_type"]["gcn"], 1)
        self.assertEqual(payload["summary"]["input_counts"]["by_type"]["grb"], 1)
        self.assertEqual(payload["summary"]["input_counts"]["by_type"]["gw"], 1)
        self.assertEqual(payload["summary"]["input_counts"]["by_type"]["ep"], 1)
        self.assertEqual(payload["summary"]["input_counts"]["inventory_runs"], 1)
        self.assertEqual(
            [item["id"] for item in payload["sources"]],
            ["EP-1", "GCN-1", "GRB-1", "GW-1"],
        )
        self.assertTrue(payload["sources"][0]["comment_exists"])
        self.assertEqual(payload["sources"][0]["num_det_global"], 9)
        self.assertTrue(payload["sources"][0]["has_host"])
        self.assertEqual(payload["sources"][1]["trigger_time"], 61200.1)
        self.assertTrue(payload["sources"][2]["spectrum_exists"])
        self.assertEqual(payload["sources"][1]["tags"], ["LongGRB", "Swift"])

    def test_gcn_grandma_contract_keeps_alias_prefix_matches(self) -> None:
        inventory_runs = [
            {
                "inventory_dir": Path("data/raw/skyportal/inventory/source_inventory_grandma_base_example"),
                "manifest": {
                    "run_label": "grandma_base",
                    "profile_name": "grandma_base",
                },
                "sources": [
                    make_source(
                        "2026owq",
                        alias=[" GRB 260610B", "SVOM#sb26061001"],
                        tns_name="AT 2026owq",
                        ra=218.159414,
                        dec=27.004935,
                        redshift=1.2,
                        comment_exists=True,
                    ),
                    make_source("AT2025abc"),
                ],
            }
        ]

        payload = build_gcn_grandma_contract(
            inventory_runs=inventory_runs,
            output_path=Path("data/samples/gcn_grandma_example.json"),
        )

        self.assertEqual(payload["summary"]["input_counts"]["gcn_derived_sources"], 1)
        self.assertEqual(payload["sources"][0]["id"], "2026owq")
        self.assertEqual(payload["sources"][0]["gcn_source_type"], "grb")
        self.assertEqual(payload["sources"][0]["aliases"], ["GRB 260610B", "SVOM#sb26061001"])
        self.assertEqual(payload["sources"][0]["tns_name"], "AT 2026owq")
        self.assertEqual(payload["sources"][0]["ra"], 218.159414)
        self.assertEqual(payload["sources"][0]["dec"], 27.004935)

    def test_gcn_grandma_contract_merges_trigger_time_and_spectrum_flag(self) -> None:
        inventory_runs = [
            {
                "inventory_dir": Path("data/raw/skyportal/inventory/source_inventory_gcn_example"),
                "manifest": {
                    "run_label": "gcn",
                    "profile_name": "gcn",
                },
                "sources": [
                    make_source("GCN-1", t0=None, spectrum_exists=False),
                ],
            },
            {
                "inventory_dir": Path("data/raw/skyportal/inventory/source_inventory_grandma_base_example"),
                "manifest": {
                    "run_label": "grandma_base",
                    "profile_name": "grandma_base",
                },
                "sources": [
                    make_source("GCN-1", t0=61205.5, spectrum_exists=True),
                ],
            },
        ]

        payload = build_gcn_grandma_contract(
            inventory_runs=inventory_runs,
            output_path=Path("data/samples/gcn_grandma_example.json"),
        )

        self.assertEqual(payload["sources"][0]["trigger_time"], 61205.5)
        self.assertTrue(payload["sources"][0]["spectrum_exists"])

    def test_gcn_grandma_contract_merges_tags_without_duplicates(self) -> None:
        inventory_runs = [
            {
                "inventory_dir": Path("data/raw/skyportal/inventory/source_inventory_gcn_example"),
                "manifest": {
                    "run_label": "gcn",
                    "profile_name": "gcn",
                },
                "sources": [
                    make_source("GRB-1", tags=["LongGRB", "Swift"]),
                ],
            },
            {
                "inventory_dir": Path("data/raw/skyportal/inventory/source_inventory_grandma_base_example"),
                "manifest": {
                    "run_label": "grandma_base",
                    "profile_name": "grandma_base",
                },
                "sources": [
                    make_source("GRB-1", tags=["Swift", "Optical"]),
                ],
            },
        ]

        payload = build_gcn_grandma_contract(
            inventory_runs=inventory_runs,
            output_path=Path("data/samples/gcn_grandma_example.json"),
        )

        self.assertEqual(
            payload["sources"][0]["tags"],
            ["LongGRB", "Swift", "Optical"],
        )

if __name__ == "__main__":
    unittest.main()
