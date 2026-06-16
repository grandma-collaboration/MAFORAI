#!/usr/bin/env python3

"""Match selected-event search terms against GCN Circulars."""

from __future__ import annotations

import argparse

from skyportal_corpus.extraction import (
    DEFAULT_GCN_CIRCULARS_ROOT_DIR,
    DEFAULT_GCN_EVENT_MATCHING_OUTPUT_DIR,
    DEFAULT_GCN_EVENT_MATCHING_TERMS_PATH,
    DEFAULT_GCN_YEAR_FROM,
    DEFAULT_GCN_YEAR_TO,
    run_gcn_event_match_build,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Match selected-event search terms against GCN Circulars."
    )
    parser.add_argument(
        "--terms-path",
        default=DEFAULT_GCN_EVENT_MATCHING_TERMS_PATH,
        help=(
            "Path to event_search_terms.parquet. "
            f"Default: {DEFAULT_GCN_EVENT_MATCHING_TERMS_PATH}"
        ),
    )
    parser.add_argument(
        "--gcn-root",
        default=DEFAULT_GCN_CIRCULARS_ROOT_DIR,
        help=(
            "Root directory containing yearly GCN circular parquet files. "
            f"Default: {DEFAULT_GCN_CIRCULARS_ROOT_DIR}"
        ),
    )
    parser.add_argument(
        "--year-from",
        type=int,
        default=DEFAULT_GCN_YEAR_FROM,
        help=f"First GCN year to load. Default: {DEFAULT_GCN_YEAR_FROM}",
    )
    parser.add_argument(
        "--year-to",
        type=int,
        default=DEFAULT_GCN_YEAR_TO,
        help=f"Last GCN year to load. Default: {DEFAULT_GCN_YEAR_TO}",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_GCN_EVENT_MATCHING_OUTPUT_DIR,
        help=(
            "Directory where event_gcn_matches outputs will be written. "
            f"Default: {DEFAULT_GCN_EVENT_MATCHING_OUTPUT_DIR}"
        ),
    )
    return parser.parse_args()


def main() -> None:
    run_gcn_event_match_build(parse_args())


if __name__ == "__main__":
    main()
