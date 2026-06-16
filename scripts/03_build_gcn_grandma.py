"""Build the enriched GCN-derived base list from several saved inventories."""

from __future__ import annotations

import argparse

from skyportal_corpus.extraction import run_gcn_grandma_build


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the enriched GCN-derived base list from several saved inventories."
    )
    parser.add_argument(
        "--inventory-dir",
        action="append",
        required=True,
        help="Path to one saved inventory run directory containing manifest.json. Repeat this flag for gcn, grb, ep, and grandma_base.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional output JSON path. Defaults to data/samples/gcn_grandma.json.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_gcn_grandma_build(
        inventory_dirs=args.inventory_dir,
        output=args.output,
    )


if __name__ == "__main__":
    main()
