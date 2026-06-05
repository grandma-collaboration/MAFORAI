from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from skyportal_corpus.extraction.high_priority_samples import (
    build_bundle_summary_row,
    build_high_priority_sample_contract,
    filter_high_priority_sources,
    write_bundle_summary_csv,
)


class HighPrioritySamplesTests(unittest.TestCase):
    def test_filter_high_priority_sources_keeps_only_high(self) -> None:
        payload = {
            "selected_sources": [
                {"id": "GRB-1", "priority": "high"},
                {"id": "GCN-1", "priority": "medium"},
                {"id": "EP-1", "priority": "high"},
            ]
        }

        kept = filter_high_priority_sources(payload)

        self.assertEqual([item["id"] for item in kept], ["GRB-1", "EP-1"])

    def test_build_high_priority_sample_contract_reports_count(self) -> None:
        payload = build_high_priority_sample_contract(
            selected_sources_path=Path("data/samples/selected_sources_for_bundles.json"),
            bundle_run_dir=Path("data/raw/skyportal/source_bundles/source_bundle_run_example"),
            high_priority_sources=[{"id": "GRB-1"}, {"id": "EP-1"}],
        )

        self.assertEqual(payload["summary"]["n_sources"], 2)
        self.assertEqual(payload["sources"][0]["id"], "GRB-1")

    def test_build_bundle_summary_row_extracts_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_dir = Path(tmpdir)
            (bundle_dir / "source.json").write_text(
                json.dumps(
                    {
                        "data": {
                            "summary": "Example summary",
                            "tns_info": {"name": "TNS"},
                            "followup_requests": [{}, {}],
                        }
                    }
                ),
                encoding="utf-8",
            )
            (bundle_dir / "bundle_manifest.json").write_text(
                json.dumps({"counts": {"endpoint_requests_failed": 1}}),
                encoding="utf-8",
            )
            (bundle_dir / "photometry_flux.json").write_text(
                json.dumps({"data": [{}, {}]}), encoding="utf-8"
            )
            (bundle_dir / "photometry_mag.json").write_text(
                json.dumps({"data": [{}]}), encoding="utf-8"
            )
            (bundle_dir / "comments.json").write_text(
                json.dumps({"data": [{}, {}, {}]}), encoding="utf-8"
            )
            (bundle_dir / "classifications.json").write_text(
                json.dumps({"data": [{}]}), encoding="utf-8"
            )
            (bundle_dir / "spectra.json").write_text(
                json.dumps({"data": {"spectra": [{}, {}]}}), encoding="utf-8"
            )
            (bundle_dir / "annotations.json").write_text(
                json.dumps({"data": []}), encoding="utf-8"
            )
            (bundle_dir / "associated_gcns.json").write_text(
                json.dumps({"data": {"gcns": [{}, {}]}}), encoding="utf-8"
            )
            (bundle_dir / "phot_stat.json").write_text(
                json.dumps({"data": {"obj_id": "GRB-1"}}), encoding="utf-8"
            )

            row = build_bundle_summary_row(
                {
                    "id": "GRB-1",
                    "gcn_source_type": "grb",
                    "priority": "high",
                    "selection_score": 12,
                    "selection_context": {"redshift": 0.5},
                },
                bundle_dir,
            )

            self.assertEqual(row["n_photometry_flux_points"], 2)
            self.assertEqual(row["n_comments"], 3)
            self.assertEqual(row["n_spectra"], 2)
            self.assertEqual(row["n_followup_requests"], 2)
            self.assertTrue(row["has_tns_info"])
            self.assertFalse(row["bundle_complete"])

    def test_write_bundle_summary_csv_writes_header_and_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "summary.csv"
            rows = [
                {"source_id": "GRB-1", "has_comments": True},
                {"source_id": "GRB-2", "has_comments": False},
            ]
            write_bundle_summary_csv(csv_path, rows)

            with csv_path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                loaded = list(reader)

            self.assertEqual(len(loaded), 2)
            self.assertEqual(loaded[0]["source_id"], "GRB-1")


if __name__ == "__main__":
    unittest.main()
