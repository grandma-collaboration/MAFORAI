"""Build the final selected-sources file from the GCN-derived GRANDMA base list."""

from __future__ import annotations

import argparse

from skyportal_corpus.extraction import run_selected_sources_build


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the final selected-sources file from the GCN-derived GRANDMA base list."
    )
    parser.add_argument(
        "--gcn-grandma-path",
        default=None,
        help="Optional path to a gcn_grandma JSON file. Defaults to data/samples/gcn_grandma_grandma_base.json.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional output JSON path. Defaults to data/samples/selected_sources_for_bundles.json.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_selected_sources_build(
        gcn_grandma_path=args.gcn_grandma_path,
        output=args.output,
    )


if __name__ == "__main__":
    main()
