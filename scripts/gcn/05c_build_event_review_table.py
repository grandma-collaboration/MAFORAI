#!/usr/bin/env python3

"""Build the final event-level review table for astronomer validation."""

from __future__ import annotations

import argparse

from skyportal_corpus.extraction import (
    DEFAULT_GCN_CORE_CLAIMS_PATH,
    DEFAULT_GCN_EVENT_BEST_CLAIMS_PATH,
    DEFAULT_GCN_EVENT_REVIEW_OUTPUT_DIR,
    DEFAULT_SKYPORTAL_EVENT_BASELINE_PARQUET_PATH,
    run_gcn_event_review_table_build,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the final event-level review table for astronomer validation."
    )
    parser.add_argument(
        "--skyportal-baseline-path",
        default=DEFAULT_SKYPORTAL_EVENT_BASELINE_PARQUET_PATH,
        help=(
            "Path to the prebuilt SkyPortal baseline. "
            f"Default: {DEFAULT_SKYPORTAL_EVENT_BASELINE_PARQUET_PATH}"
        ),
    )
    parser.add_argument(
        "--best-claims-path",
        default=DEFAULT_GCN_EVENT_BEST_CLAIMS_PATH,
        help=(
            "Path to gcn_event_best_claims.parquet. "
            f"Default: {DEFAULT_GCN_EVENT_BEST_CLAIMS_PATH}"
        ),
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
        "--output-dir",
        default=DEFAULT_GCN_EVENT_REVIEW_OUTPUT_DIR,
        help=(
            "Directory where the review table will be written. "
            f"Default: {DEFAULT_GCN_EVENT_REVIEW_OUTPUT_DIR}"
        ),
    )
    return parser.parse_args()


def main() -> None:
    run_gcn_event_review_table_build(parse_args())


if __name__ == "__main__":
    main()
