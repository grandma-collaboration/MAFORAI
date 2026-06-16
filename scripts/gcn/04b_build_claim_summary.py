#!/usr/bin/env python3

"""Build an event-level review summary from extracted GCN body claims."""

from __future__ import annotations

import argparse

from skyportal_corpus.extraction import (
    DEFAULT_GCN_CORE_CLAIMS_PATH,
    DEFAULT_GCN_EVENT_EXTRACTION_OUTPUT_DIR,
    DEFAULT_GCN_EVENT_MATCHING_SUMMARY_PATH,
    run_gcn_claim_summary_build,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build an event-level review summary from extracted GCN body claims."
    )
    parser.add_argument(
        "--claims-path",
        default=DEFAULT_GCN_CORE_CLAIMS_PATH,
        help=(
            "Path to gcn_core_claims.parquet. "
            f"Default: {DEFAULT_GCN_CORE_CLAIMS_PATH}"
        ),
    )
    parser.add_argument(
        "--match-summary-path",
        default=DEFAULT_GCN_EVENT_MATCHING_SUMMARY_PATH,
        help=(
            "Path to event_gcn_match_summary.csv from Step A. "
            f"Default: {DEFAULT_GCN_EVENT_MATCHING_SUMMARY_PATH}"
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_GCN_EVENT_EXTRACTION_OUTPUT_DIR,
        help=(
            "Directory where event_gcn_claim_summary.csv will be written. "
            f"Default: {DEFAULT_GCN_EVENT_EXTRACTION_OUTPUT_DIR}"
        ),
    )
    return parser.parse_args()


def main() -> None:
    run_gcn_claim_summary_build(parse_args())


if __name__ == "__main__":
    main()
