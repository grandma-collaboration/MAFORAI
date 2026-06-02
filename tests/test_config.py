from __future__ import annotations

import unittest

from skyportal_corpus.core import default_skyportal_config_path, load_skyportal_config


class SkyPortalConfigTests(unittest.TestCase):
    def test_default_config_path_exists(self) -> None:
        self.assertTrue(default_skyportal_config_path().exists())

    def test_yaml_loads_into_structured_config(self) -> None:
        config = load_skyportal_config()

        self.assertEqual(config.version, 1)
        self.assertEqual(
            config.source_path,
            default_skyportal_config_path().resolve(),
        )
        self.assertEqual(
            config.skyportal.base_url,
            "https://skyportal-icare.ijclab.in2p3.fr/api",
        )
        self.assertEqual(
            config.skyportal.auth.token_env_var,
            "SKYPORTAL_API_TOKEN",
        )
        self.assertEqual(
            config.paths.inventory,
            "data/raw/skyportal/inventory",
        )
        self.assertEqual(
            config.paths.endpoint_audit,
            "data/raw/skyportal/endpoint_audit",
        )


if __name__ == "__main__":
    unittest.main()
