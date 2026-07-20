"""Build a normalized tabular index from extracted GCN circular JSON files."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from skyportal_corpus.extraction import (
    DEFAULT_CIRCULARS_INDEX_OUTPUT_DIR,
    run_gcn_circulars_index_build,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ARCHIVE_JSON_ROOT = PROJECT_ROOT / "data/raw/gcn/circulars/archive_json"
ARCHIVE_RUN_PATTERN = re.compile(r"\d{8}_\d{6}")


def resolve_latest_circulars_input_dir(
    archive_root: Path = ARCHIVE_JSON_ROOT,
) -> Path:
    """Return the extracted archive directory from the latest timestamped run."""
    candidates: list[Path] = []
    if archive_root.is_dir():
        candidates = sorted(
            run_dir / "extracted" / "archive.json"
            for run_dir in archive_root.iterdir()
            if run_dir.is_dir()
            and ARCHIVE_RUN_PATTERN.fullmatch(run_dir.name)
            and (run_dir / "extracted" / "archive.json").is_dir()
        )
    if not candidates:
        raise FileNotFoundError(
            "No extracted GCN Circular archive found under "
            f"{archive_root}. Run scripts/gcn/01_download_circulars_archive.py first "
            "or pass --input-dir explicitly."
        )
    return candidates[-1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a normalized index from extracted GCN circular JSON files."
    )
    parser.add_argument(
        "--input-dir",
        default=None,
        help=(
            "Directory containing extracted GCN circular JSON files. "
            "Default: the latest timestamped archive under "
            "data/raw/gcn/circulars/archive_json/."
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
    args = parser.parse_args()
    if args.input_dir is None:
        try:
            args.input_dir = str(resolve_latest_circulars_input_dir())
        except FileNotFoundError as exc:
            parser.error(str(exc))
    return args


def main() -> None:
    run_gcn_circulars_index_build(parse_args())


if __name__ == "__main__":
    main()
