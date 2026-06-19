#!/usr/bin/env python3

"""Build conservative event search terms from the selected SkyPortal events."""

from __future__ import annotations

import argparse

from skyportal_corpus.extraction import (
    DEFAULT_GCN_EVENT_INPUT_PATH,
    DEFAULT_GCN_EVENT_MATCHING_OUTPUT_DIR,
    run_gcn_event_search_terms_build,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build conservative event search terms from selected SkyPortal events."
    )
    parser.add_argument(
        "--selected-sources",
        default=DEFAULT_GCN_EVENT_INPUT_PATH,
        help=(
            "Path to the event-universe input used for matching. "
            "Defaults to data/interim/skyportal/gcn_grandma.json. "
            f"Default: {DEFAULT_GCN_EVENT_INPUT_PATH}"
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_GCN_EVENT_MATCHING_OUTPUT_DIR,
        help=(
            "Directory where event_search_terms outputs will be written. "
            f"Default: {DEFAULT_GCN_EVENT_MATCHING_OUTPUT_DIR}"
        ),
    )
    return parser.parse_args()


def main() -> None:
    run_gcn_event_search_terms_build(parse_args())


if __name__ == "__main__":
    main()
