"""Fetch per-source SkyPortal bundles from the current selected source list."""

from __future__ import annotations

import argparse

from skyportal_corpus.core import default_skyportal_config_path
from skyportal_corpus.extraction import run_source_bundles


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch per-source SkyPortal bundles from the selected source list."
    )
    parser.add_argument(
        "--config",
        default=str(default_skyportal_config_path()),
        help=(
            "Path to the shared SkyPortal YAML config. "
            f"Default: {default_skyportal_config_path()}"
        ),
    )
    parser.add_argument(
        "--selected-sources-path",
        default=None,
        help="Optional path to the selected_sources_for_bundles JSON file.",
    )
    parser.add_argument(
        "--priority",
        choices=("high", "medium", "low"),
        default="high",
        help="Priority bucket to fetch. Default: high.",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Optional API base URL override. Defaults to the shared config value.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional output directory override. Defaults to data/raw/skyportal/source_bundles/.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Request timeout in seconds for each endpoint call.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Retry count for each endpoint call.",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.2,
        help="Delay in seconds between source bundles.",
    )
    return parser.parse_args()


def main() -> None:
    run_source_bundles(parse_args())


if __name__ == "__main__":
    main()
