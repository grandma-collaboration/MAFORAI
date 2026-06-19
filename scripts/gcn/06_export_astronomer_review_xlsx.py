#!/usr/bin/env python3

"""Export the curated astronomer-facing review workbook."""

from __future__ import annotations

import argparse

from skyportal_corpus.extraction import (
    DEFAULT_GCN_ASTRONOMER_REVIEW_XLSX_PATH,
    DEFAULT_GCN_EVENT_REVIEW_CSV_PATH,
    run_gcn_astronomer_review_xlsx_export,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export the curated astronomer-facing review workbook."
    )
    parser.add_argument(
        "--review-table-path",
        default=DEFAULT_GCN_EVENT_REVIEW_CSV_PATH,
        help=(
            "Path to gcn_event_review_table.csv. "
            f"Default: {DEFAULT_GCN_EVENT_REVIEW_CSV_PATH}"
        ),
    )
    parser.add_argument(
        "--output-path",
        default=DEFAULT_GCN_ASTRONOMER_REVIEW_XLSX_PATH,
        help=(
            "Path where the astronomer workbook will be written. "
            f"Default: {DEFAULT_GCN_ASTRONOMER_REVIEW_XLSX_PATH}"
        ),
    )
    return parser.parse_args()


def main() -> None:
    run_gcn_astronomer_review_xlsx_export(parse_args())


if __name__ == "__main__":
    main()
