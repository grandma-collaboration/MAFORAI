#!/usr/bin/env python3

"""Build the compact SkyPortal-side baseline used before GCN comparison."""

from __future__ import annotations

import argparse

from skyportal_corpus.extraction import (
    DEFAULT_GCN_GRANDMA_OUTPUT,
    DEFAULT_SKYPORTAL_EVENT_BASELINE_OUTPUT_DIR,
    run_skyportal_event_baseline_build,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the compact SkyPortal-side baseline used before GCN comparison."
    )
    parser.add_argument(
        "--selected-sources",
        default=DEFAULT_GCN_GRANDMA_OUTPUT,
        help=(
            "Path to the canonical SkyPortal event universe. "
            f"Default: {DEFAULT_GCN_GRANDMA_OUTPUT}"
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_SKYPORTAL_EVENT_BASELINE_OUTPUT_DIR,
        help=(
            "Directory where skyportal_event_baseline outputs will be written. "
            f"Default: {DEFAULT_SKYPORTAL_EVENT_BASELINE_OUTPUT_DIR}"
        ),
    )
    return parser.parse_args()


def main() -> None:
    run_skyportal_event_baseline_build(parse_args())


if __name__ == "__main__":
    main()
