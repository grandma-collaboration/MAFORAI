#!/usr/bin/env python3

"""Extract core structured claims from already matched GCN circular bodies."""

from __future__ import annotations

import argparse

from skyportal_corpus.extraction import (
    DEFAULT_GCN_EVENT_EXTRACTION_OUTPUT_DIR,
    DEFAULT_GCN_EVENT_MATCHING_ASSOCIATIONS_PATH,
    run_gcn_core_claims_extract,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract core structured claims from already matched GCN circular bodies."
    )
    parser.add_argument(
        "--associations-path",
        default=DEFAULT_GCN_EVENT_MATCHING_ASSOCIATIONS_PATH,
        help=(
            "Path to event_gcn_associations.parquet. "
            f"Default: {DEFAULT_GCN_EVENT_MATCHING_ASSOCIATIONS_PATH}"
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_GCN_EVENT_EXTRACTION_OUTPUT_DIR,
        help=(
            "Directory where core-claim outputs will be written. "
            f"Default: {DEFAULT_GCN_EVENT_EXTRACTION_OUTPUT_DIR}"
        ),
    )
    return parser.parse_args()


def main() -> None:
    run_gcn_core_claims_extract(parse_args())


if __name__ == "__main__":
    main()
