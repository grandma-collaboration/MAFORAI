"""Export the current high-priority source set into compact shared sample files."""

from __future__ import annotations

import argparse

from skyportal_corpus.extraction import run_high_priority_sample_export


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export the current high-priority source set into compact shared sample files."
    )
    parser.add_argument(
        "--bundle-run-dir",
        required=True,
        help="Path to one source_bundle_run_<timestamp> directory.",
    )
    parser.add_argument(
        "--selected-sources-path",
        default=None,
        help="Optional path to selected_sources_for_bundles.json.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional output directory. Defaults to data/samples/.",
    )
    return parser.parse_args()


def main() -> None:
    run_high_priority_sample_export(parse_args())


if __name__ == "__main__":
    main()
