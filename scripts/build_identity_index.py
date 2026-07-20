#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from skyportal_corpus.extraction_v2.identity_index import (  # noqa: E402
    DEFAULT_IDENTITY_INDEX_META_PATH,
    DEFAULT_IDENTITY_INDEX_PATH,
    build_identity_index,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the reusable GCN identity index.")
    parser.add_argument("--min-year", type=int, default=2023)
    parser.add_argument("--index-path", default=str(DEFAULT_IDENTITY_INDEX_PATH))
    parser.add_argument("--meta-path", default=str(DEFAULT_IDENTITY_INDEX_META_PATH))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    metadata = build_identity_index(
        min_year=args.min_year,
        index_path=PROJECT_ROOT / args.index_path,
        meta_path=PROJECT_ROOT / args.meta_path,
    )
    for key in (
        "min_year",
        "n_circulars",
        "n_identity_annotations",
        "build_seconds",
        "index_size_bytes",
        "extractor_id",
        "extractor_version",
        "index_path",
        "index_sha256",
    ):
        print(f"{key}: {metadata[key]}")
    print(f"meta_path: {PROJECT_ROOT / args.meta_path}")


if __name__ == "__main__":
    main()
