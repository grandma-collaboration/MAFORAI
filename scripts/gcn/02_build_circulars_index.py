"""Build a normalized tabular index from extracted GCN circular JSON files."""

from __future__ import annotations

import argparse

from skyportal_corpus.extraction import (
    DEFAULT_CIRCULARS_INDEX_OUTPUT_DIR,
    DEFAULT_CIRCULARS_INPUT_DIR,
    run_gcn_circulars_index_build,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a normalized index from extracted GCN circular JSON files."
    )
    parser.add_argument(
        "--input-dir",
        default=DEFAULT_CIRCULARS_INPUT_DIR,
        help=(
            "Directory containing extracted GCN circular JSON files. "
            f"Default: {DEFAULT_CIRCULARS_INPUT_DIR}"
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_CIRCULARS_INDEX_OUTPUT_DIR,
        help=(
            "Directory where the normalized index outputs will be written. "
            f"Default: {DEFAULT_CIRCULARS_INDEX_OUTPUT_DIR}"
        ),
    )
    return parser.parse_args()


def main() -> None:
    run_gcn_circulars_index_build(parse_args())


if __name__ == "__main__":
    main()
