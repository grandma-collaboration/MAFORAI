#!/usr/bin/env python3

"""Build auditable INCEpTION preannotation candidates from existing GCN claims."""

from __future__ import annotations

import argparse

from skyportal_corpus.extraction import (
    DEFAULT_GCN_EVENT_MATCHING_SELECTED_SOURCES_PATH,
    DEFAULT_GCN_INCEPTION_CIRCULARS_ROOT,
    DEFAULT_GCN_INCEPTION_DOSSIERS_OUTPUT_DIR,
    DEFAULT_GCN_PREANNOTATIONS_OUTPUT_DIR,
    run_gcn_preannotation_candidates_build,
)
from skyportal_corpus.extraction.gcn_preannotation_candidates import (
    select_default_claims_path,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build auditable INCEpTION preannotation candidates from existing GCN claims."
    )
    parser.add_argument(
        "--claims-path",
        default=select_default_claims_path(),
        help=(
            "Path to gcn_core_claims.parquet or .csv. "
            f"Default: {select_default_claims_path()}"
        ),
    )
    parser.add_argument(
        "--dossiers-dir",
        default=DEFAULT_GCN_INCEPTION_DOSSIERS_OUTPUT_DIR,
        help=(
            "Directory containing the plain-text INCEpTION dossiers. "
            f"Default: {DEFAULT_GCN_INCEPTION_DOSSIERS_OUTPUT_DIR}"
        ),
    )
    parser.add_argument(
        "--selected-sources-path",
        default=DEFAULT_GCN_EVENT_MATCHING_SELECTED_SOURCES_PATH,
        help=(
            "Path to the compact SkyPortal event universe JSON, used to recover event names. "
            f"Default: {DEFAULT_GCN_EVENT_MATCHING_SELECTED_SOURCES_PATH}"
        ),
    )
    parser.add_argument(
        "--gcn-root",
        default=DEFAULT_GCN_INCEPTION_CIRCULARS_ROOT,
        help=(
            "Root directory of the year-partitioned GCN indexes, used as a fallback for circular bodies. "
            f"Default: {DEFAULT_GCN_INCEPTION_CIRCULARS_ROOT}"
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_GCN_PREANNOTATIONS_OUTPUT_DIR,
        help=(
            "Directory where the preannotation candidates and report will be written. "
            f"Default: {DEFAULT_GCN_PREANNOTATIONS_OUTPUT_DIR}"
        ),
    )
    parser.add_argument(
        "--source-id",
        action="append",
        default=None,
        help=(
            "Optional source_id filter within the available INCEpTION dossiers. "
            "Can be repeated."
        ),
    )
    parser.add_argument(
        "--document-name",
        action="append",
        default=None,
        help=(
            "Optional dossier filename or stem filter within the available INCEpTION dossiers. "
            "Can be repeated."
        ),
    )
    return parser.parse_args()


def main() -> None:
    run_gcn_preannotation_candidates_build(parse_args())


if __name__ == "__main__":
    main()
