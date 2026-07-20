#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from skyportal_corpus.extraction_v2.event_registry import (  # noqa: E402
    DEFAULT_EVENT_REGISTRY_PATH,
    DEFAULT_EVENT_SOURCES_PATH,
    DEFAULT_EVENT_TERMS_PATH,
    build_event_registry_rows,
    load_event_sources,
    load_event_term_rows,
    suffixless_only_rows,
    write_event_registry,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the deduplicated SkyPortal event registry.")
    parser.add_argument("--sources", default=str(DEFAULT_EVENT_SOURCES_PATH))
    parser.add_argument("--terms", default=str(DEFAULT_EVENT_TERMS_PATH))
    parser.add_argument("--output", default=str(DEFAULT_EVENT_REGISTRY_PATH))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sources = load_event_sources(PROJECT_ROOT / args.sources)
    term_rows = load_event_term_rows(PROJECT_ROOT / args.terms)
    registry_rows, duplicate_groups = build_event_registry_rows(sources, term_rows)
    output_path = write_event_registry(registry_rows, PROJECT_ROOT / args.output)
    suffixless = suffixless_only_rows(registry_rows)
    rows_with_dropped_terms = [
        row for row in registry_rows if str(row.get("dropped_terms") or "").strip()
    ]

    print(f"input_events: {len(sources)}")
    print(f"duplicate_groups: {len(duplicate_groups)}")
    for group in duplicate_groups:
        print(
            "duplicate: "
            f"members={','.join(group['members'])} "
            f"canonical={group['canonical_source_id']}"
        )
    print(f"registry_events: {len(registry_rows)}")
    print(f"events_with_dropped_terms: {len(rows_with_dropped_terms)}")
    for row in rows_with_dropped_terms:
        print(
            f"dropped_terms: {row['source_id']} | kept={row['terms']} | "
            f"dropped={row['dropped_terms']}"
        )
    print(f"suffixless_only_events: {len(suffixless)}")
    print("suffixless_only_first_20:")
    for row in suffixless[:20]:
        print(
            f"{row['source_id']} | {row['gcn_source_type']} | {row['terms']}"
        )
    print(f"registry_path: {output_path}")


if __name__ == "__main__":
    main()
