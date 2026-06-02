"""
Audit the availability of SkyPortal API endpoints.

This script is a thin CLI entrypoint around the shared audit logic in
`src/skyportal_corpus/extraction/endpoint_audit.py`.
"""

from __future__ import annotations

import argparse

from skyportal_corpus.core import default_skyportal_config_path
from skyportal_corpus.extraction import run_endpoint_audit


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit availability of SkyPortal API endpoints."
    )
    parser.add_argument(
        "--config",
        default=str(default_skyportal_config_path()),
        help=(
            "Path to the shared SkyPortal YAML config. "
            f"Default: {default_skyportal_config_path()}"
        ),
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Optional API base URL override. Defaults to the shared config value.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional output directory override. Defaults to the shared config value.",
    )
    parser.add_argument(
        "--run-label",
        default=None,
        help="Optional semantic label for the run, e.g. initial, full, source_level.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="Optional request timeout override in seconds.",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=None,
        help="Optional delay override between requests in seconds.",
    )
    parser.add_argument(
        "--category",
        default=None,
        help="Audit only one endpoint category, e.g. inventory, photometry, classifications.",
    )
    parser.add_argument("--source-id", default=None, help="Example SkyPortal source ID.")
    parser.add_argument("--candidate-id", default=None, help="Example candidate ID.")
    parser.add_argument(
        "--resource-type",
        default=None,
        help="Resource type for comments/annotations. Defaults to the shared config value.",
    )
    parser.add_argument(
        "--resource-id",
        default=None,
        help="Resource ID for comments/annotations. Defaults to source ID if omitted.",
    )
    parser.add_argument("--photometry-id", default=None)
    parser.add_argument("--photometric-series-id", default=None)
    parser.add_argument("--spectrum-id", default=None)
    parser.add_argument("--classification-id", default=None)
    parser.add_argument("--taxonomy-id", default=None)
    parser.add_argument("--comment-id", default=None)
    parser.add_argument("--annotation-id", default=None)
    parser.add_argument("--catalog-name", default=None)
    parser.add_argument("--catalog-id", default=None)
    parser.add_argument("--dateobs", default=None, help="Example GCN dateobs.")
    parser.add_argument("--gcnevent-id", default=None)
    parser.add_argument("--notice-id", default=None)
    parser.add_argument("--localization-name", default=None)
    parser.add_argument("--localization-id", default=None)
    parser.add_argument("--followup-request-id", default=None)
    parser.add_argument("--photometry-request-id", default=None)
    parser.add_argument("--observation-plan-request-id", default=None)
    parser.add_argument("--thumbnail-id", default=None)
    parser.add_argument("--analysis-service-id", default=None)
    parser.add_argument("--analysis-resource-type", default=None)
    parser.add_argument("--analysis-id", default=None)
    parser.add_argument("--group-id", default=None)
    parser.add_argument("--instrument-id", default=None)
    parser.add_argument("--telescope-id", default=None)
    parser.add_argument("--filter-id", default=None)

    return parser.parse_args()


def main() -> None:
    run_endpoint_audit(parse_args())


if __name__ == "__main__":
    main()
