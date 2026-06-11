#!/usr/bin/env python3

"""Download the GCN circulars JSON archive into one raw-data run directory."""

from __future__ import annotations

import argparse

from skyportal_corpus.extraction import (
    DEFAULT_GCN_CIRCULARS_ARCHIVE_URL,
    DEFAULT_GCN_CIRCULARS_OUTPUT_DIR,
    run_gcn_circulars_archive_download,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download the GCN circulars JSON archive."
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_GCN_CIRCULARS_ARCHIVE_URL,
        help=(
            "Archive URL to download. "
            f"Default: {DEFAULT_GCN_CIRCULARS_ARCHIVE_URL}"
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_GCN_CIRCULARS_OUTPUT_DIR,
        help=(
            "Base output directory for timestamped runs. "
            f"Default: {DEFAULT_GCN_CIRCULARS_OUTPUT_DIR}"
        ),
    )
    parser.add_argument(
        "--extract",
        action="store_true",
        help="Extract the downloaded .tar.gz archive after download.",
    )
    return parser.parse_args()


def main() -> None:
    run_gcn_circulars_archive_download(parse_args())


if __name__ == "__main__":
    main()
