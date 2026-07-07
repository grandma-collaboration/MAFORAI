#!/usr/bin/env python3

"""Build a human-review table for one pilot INCEpTION preannotation event."""

from __future__ import annotations

import argparse

from skyportal_corpus.extraction.gcn_preannotation_candidates import (
    DEFAULT_GCN_PREANNOTATION_CANDIDATES_PARQUET_PATH,
)
from skyportal_corpus.extraction.gcn_preannotation_review import (
    DEFAULT_GCN_PREANNOTATION_PILOT_OUTPUT_DIR,
    DEFAULT_GCN_PREANNOTATION_PILOT_SOURCE_ID,
    run_gcn_pilot_review_table_build,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a human-review table for one pilot INCEpTION preannotation event."
    )
    parser.add_argument(
        "--candidates-path",
        default=DEFAULT_GCN_PREANNOTATION_CANDIDATES_PARQUET_PATH,
        help=(
            "Path to preannotation_candidates.parquet or .csv. "
            f"Default: {DEFAULT_GCN_PREANNOTATION_CANDIDATES_PARQUET_PATH}"
        ),
    )
    parser.add_argument(
        "--source-id",
        default=DEFAULT_GCN_PREANNOTATION_PILOT_SOURCE_ID,
        help=(
            "Pilot event source_id to review. "
            f"Default: {DEFAULT_GCN_PREANNOTATION_PILOT_SOURCE_ID}"
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_GCN_PREANNOTATION_PILOT_OUTPUT_DIR,
        help=(
            "Directory where the pilot review CSV and report will be written. "
            f"Default: {DEFAULT_GCN_PREANNOTATION_PILOT_OUTPUT_DIR}"
        ),
    )
    return parser.parse_args()


def main() -> None:
    run_gcn_pilot_review_table_build(parse_args())


if __name__ == "__main__":
    main()
