"""
Create the initial selection contract for source-bundle candidates.

This script is a thin CLI entrypoint around the shared selection scaffolding in
`src/skyportal_corpus/extraction/source_selection.py`.
"""

from __future__ import annotations

import argparse

from skyportal_corpus.extraction import run_source_selection


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create the initial JSON contract for source-bundle selection."
    )
    parser.add_argument(
        "--inventory-dir",
        required=True,
        help="Path to one saved inventory run directory containing manifest.json.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional output JSON path. Defaults to data/samples/.",
    )
    parser.add_argument(
        "--target-grb-like",
        type=int,
        default=20,
        help="Target number of GRB-like sources to keep in the later selection step.",
    )
    parser.add_argument(
        "--target-non-grb",
        type=int,
        default=10,
        help="Target number of non-GRB sources to keep in the later selection step.",
    )

    return parser.parse_args()


def main() -> None:
    run_source_selection(parse_args())


if __name__ == "__main__":
    main()
