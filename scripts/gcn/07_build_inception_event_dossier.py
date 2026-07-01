#!/usr/bin/env python3

"""Build one blind plain-text INCEpTION pilot dossier for a matched event."""

from __future__ import annotations

import argparse

from skyportal_corpus.extraction import (
    DEFAULT_GCN_EVENT_MATCHING_ASSOCIATIONS_PATH,
    DEFAULT_GCN_EVENT_MATCHING_SELECTED_SOURCES_PATH,
    DEFAULT_GCN_INCEPTION_CIRCULARS_ROOT,
    DEFAULT_GCN_INCEPTION_DOSSIERS_OUTPUT_DIR,
    run_gcn_inception_event_dossier_build,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build one blind plain-text INCEpTION pilot dossier for a matched event."
    )
    parser.add_argument(
        "--source-id",
        required=True,
        help="Matched event source_id, e.g. 2026owq",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="Optional dossier title. Default: built from aliases and source_id",
    )
    parser.add_argument(
        "--associations-path",
        default=DEFAULT_GCN_EVENT_MATCHING_ASSOCIATIONS_PATH,
        help=(
            "Path to event_gcn_associations.parquet or .csv. "
            f"Default: {DEFAULT_GCN_EVENT_MATCHING_ASSOCIATIONS_PATH}"
        ),
    )
    parser.add_argument(
        "--selected-sources-path",
        default=DEFAULT_GCN_EVENT_MATCHING_SELECTED_SOURCES_PATH,
        help=(
            "Path to the compact SkyPortal event universe JSON. "
            f"Default: {DEFAULT_GCN_EVENT_MATCHING_SELECTED_SOURCES_PATH}"
        ),
    )
    parser.add_argument(
        "--gcn-root",
        default=DEFAULT_GCN_INCEPTION_CIRCULARS_ROOT,
        help=(
            "Root directory of the year-partitioned GCN indexes, used as fallback for circular bodies. "
            f"Default: {DEFAULT_GCN_INCEPTION_CIRCULARS_ROOT}"
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_GCN_INCEPTION_DOSSIERS_OUTPUT_DIR,
        help=(
            "Directory where the dossier and manifest will be written. "
            f"Default: {DEFAULT_GCN_INCEPTION_DOSSIERS_OUTPUT_DIR}"
        ),
    )
    parser.add_argument(
        "--include-low-confidence",
        action="store_true",
        help=(
            "Compatibility flag. The current dossier already includes all matched Circulars, including low-confidence associations."
        ),
    )
    return parser.parse_args()


def main() -> None:
    run_gcn_inception_event_dossier_build(parse_args())


if __name__ == "__main__":
    main()
