from __future__ import annotations

import unittest

from skyportal_corpus.extraction.source_bundles import (
    BUNDLE_ENDPOINTS,
    filter_selected_sources,
    sanitize_source_id,
)


class SourceBundlesTests(unittest.TestCase):
    def test_filter_selected_sources_keeps_only_requested_priority(self) -> None:
        payload = {
            "selected_sources": [
                {"id": "GRB-1", "priority": "high"},
                {"id": "GCN-1", "priority": "medium"},
                {"id": "EP-1", "priority": "high"},
            ]
        }

        kept = filter_selected_sources(payload, priority="high")

        self.assertEqual([item["id"] for item in kept], ["GRB-1", "EP-1"])

    def test_sanitize_source_id_only_replaces_path_separators(self) -> None:
        self.assertEqual(sanitize_source_id("GRB-250424_065229"), "GRB-250424_065229")
        self.assertEqual(sanitize_source_id("GW/250101A"), "GW_250101A")

    def test_bundle_endpoints_match_current_recipe(self) -> None:
        endpoint_names = [endpoint["name"] for endpoint in BUNDLE_ENDPOINTS]
        self.assertEqual(
            endpoint_names,
            [
                "source",
                "photometry_flux",
                "photometry_mag",
                "phot_stat",
                "comments",
                "classifications",
                "spectra",
                "annotations",
                "associated_gcns",
                "position",
                "offsets",
                "color_mag",
            ],
        )


if __name__ == "__main__":
    unittest.main()
