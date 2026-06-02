from __future__ import annotations

import sys
import unittest
from argparse import Namespace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from skyportal_corpus.core import (
    load_skyportal_config,
    merge_cli_overrides,
    resolve_inventory_profile,
)


class InventoryProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_skyportal_config()

    def test_expected_profile_exists(self) -> None:
        self.assertIn("recent_500", self.config.inventory.profiles)
        self.assertIn("has_spectrum", self.config.inventory.profiles)

    def test_profile_resolution_applies_defaults_and_template(self) -> None:
        profile = resolve_inventory_profile(self.config, "recent_500")

        self.assertEqual(profile.run_label, "recent_500")
        self.assertEqual(profile.output_dir, "data/raw/skyportal/inventory")
        self.assertEqual(profile.num_per_page, 100)
        self.assertEqual(profile.start_page, 1)
        self.assertEqual(profile.max_pages, 5)
        self.assertEqual(profile.timeout_seconds, 30)
        self.assertEqual(profile.max_retries, 3)
        self.assertAlmostEqual(profile.sleep_seconds, 0.3)
        self.assertEqual(
            profile.query_params,
            {
                "sortBy": "saved_at",
                "sortOrder": "desc",
            },
        )

    def test_cli_overrides_win_over_profile_values(self) -> None:
        base_profile = resolve_inventory_profile(self.config, "has_spectrum")
        overridden = merge_cli_overrides(
            base_profile,
            Namespace(
                run_label="has_spectrum_test",
                output_dir="tmp/inventory_test",
                num_per_page=50,
                start_page=3,
                max_pages=2,
                timeout=15,
                max_retries=5,
                sleep=1.5,
                query_params={"group_ids": "1"},
            ),
        )

        self.assertEqual(overridden.run_label, "has_spectrum_test")
        self.assertEqual(overridden.output_dir, "tmp/inventory_test")
        self.assertEqual(overridden.num_per_page, 50)
        self.assertEqual(overridden.start_page, 3)
        self.assertEqual(overridden.max_pages, 2)
        self.assertEqual(overridden.timeout_seconds, 15)
        self.assertEqual(overridden.max_retries, 5)
        self.assertAlmostEqual(overridden.sleep_seconds, 1.5)
        self.assertEqual(overridden.query_params["group_ids"], "1")
        self.assertEqual(overridden.query_params["hasSpectrum"], "true")

        self.assertEqual(base_profile.max_pages, 0)
        self.assertEqual(base_profile.num_per_page, 100)
        self.assertNotIn("group_ids", base_profile.query_params)


if __name__ == "__main__":
    unittest.main()
