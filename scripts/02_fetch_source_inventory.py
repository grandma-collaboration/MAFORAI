"""
Fetch a raw SkyPortal source inventory.

This script is a thin CLI entrypoint around the shared extraction logic in
`src/skyportal_corpus/extraction/source_inventory.py`.
"""

from __future__ import annotations

import argparse

from skyportal_corpus.core import default_skyportal_config_path
from skyportal_corpus.extraction import run_source_inventory


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch raw paginated source inventory from SkyPortal."
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
        "--profile",
        default=None,
        help="Optional inventory profile name from the shared config, e.g. recent_500.",
    )
    parser.add_argument(
        "--run-label",
        default=None,
        help="Optional semantic label override for the run directory.",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Optional API base URL override. Defaults to the shared config value.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional output directory override. Defaults to the shared config value.",
    )
    parser.add_argument(
        "--num-per-page",
        type=int,
        default=None,
        help="Optional page size override. Defaults to the selected profile or shared config.",
    )
    parser.add_argument(
        "--start-page",
        type=int,
        default=None,
        help="Optional first page override. Defaults to the selected profile or shared config.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help=(
            "Optional page-limit override. Use 0 to continue until the API-reported "
            "total is reached."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="Optional request timeout override in seconds.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=None,
        help="Optional retry-count override per page.",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=None,
        help="Optional delay override between page requests in seconds.",
    )
    parser.add_argument(
        "--query-param",
        action="append",
        default=[],
        help="Additional query parameter as key=value. Can be used multiple times.",
    )

    return parser.parse_args()


def main() -> None:
    run_source_inventory(parse_args())


if __name__ == "__main__":
    main()
