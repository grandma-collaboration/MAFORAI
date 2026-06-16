#!/usr/bin/env python3

"""Compare GCN enrichment candidates against selected SkyPortal metadata."""

from __future__ import annotations

import argparse

from skyportal_corpus.extraction import (
    DEFAULT_GCN_EVENT_BEST_CLAIMS_PATH,
    DEFAULT_GCN_EVENT_ENRICHMENT_OUTPUT_DIR,
    DEFAULT_GCN_EVENT_ENRICHMENT_INPUT_PATH,
    run_gcn_event_enrichment_comparison,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare GCN enrichment candidates against selected SkyPortal metadata."
    )
    parser.add_argument(
        "--selected-sources",
        default=DEFAULT_GCN_EVENT_ENRICHMENT_INPUT_PATH,
        help=(
            "Path to the SkyPortal event base used for comparison. "
            "Defaults to data/samples/gcn_grandma.json. "
            f"Default: {DEFAULT_GCN_EVENT_ENRICHMENT_INPUT_PATH}"
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
        "--output-dir",
        default=DEFAULT_GCN_EVENT_ENRICHMENT_OUTPUT_DIR,
        help=(
            "Directory where the GCN-vs-SkyPortal comparison outputs will be written. "
            f"Default: {DEFAULT_GCN_EVENT_ENRICHMENT_OUTPUT_DIR}"
        ),
    )
    return parser.parse_args()


def main() -> None:
    run_gcn_event_enrichment_comparison(parse_args())


if __name__ == "__main__":
    main()
