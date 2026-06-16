#!/usr/bin/env python3

"""Build deduplicated event-circular associations and the review summary."""

from __future__ import annotations

import argparse

from skyportal_corpus.extraction import (
    DEFAULT_GCN_EVENT_MATCHING_MATCHES_PATH,
    DEFAULT_GCN_EVENT_MATCHING_OUTPUT_DIR,
    DEFAULT_GCN_EVENT_MATCHING_TERMS_PATH,
    run_gcn_event_match_summary_build,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build deduplicated event-circular associations and the review summary."
    )
    parser.add_argument(
        "--matches-path",
        default=DEFAULT_GCN_EVENT_MATCHING_MATCHES_PATH,
        help=(
            "Path to event_gcn_matches.parquet. "
            f"Default: {DEFAULT_GCN_EVENT_MATCHING_MATCHES_PATH}"
        ),
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
        "--output-dir",
        default=DEFAULT_GCN_EVENT_MATCHING_OUTPUT_DIR,
        help=(
            "Directory where associations and summary outputs will be written. "
            f"Default: {DEFAULT_GCN_EVENT_MATCHING_OUTPUT_DIR}"
        ),
    )
    return parser.parse_args()


def main() -> None:
    run_gcn_event_match_summary_build(parse_args())


if __name__ == "__main__":
    main()
