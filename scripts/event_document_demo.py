from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from skyportal_corpus.canonical.document import iter_real_circulars, render_canonical
from skyportal_corpus.extraction_v2.event_document import (
    build_event_document,
    global_to_circular,
    local_to_global,
)
from skyportal_corpus.extraction_v2.event_grouping import group_event_circulars


SOURCE_ID = "2026owq"
TITLE = "GRB 260610B / AT2026owq"
ALIASES = ["GRB 260610B", "AT2026owq", "2026owq"]
MIN_CIRCULAR_ID = 44880
MAX_CIRCULAR_ID = 45050


def main() -> None:
    candidates = _candidate_circulars()
    grouped = group_event_circulars(
        source_id=SOURCE_ID,
        title=TITLE,
        aliases=ALIASES,
        circulars=candidates,
    )
    included_ids = {int(item["circular_id"]) for item in grouped["included"]}
    included_circulars = [
        circular for circular in candidates if int(circular["circular_id"]) in included_ids
    ]

    doc = build_event_document(
        source_id=SOURCE_ID,
        title=TITLE,
        circulars_in_order=included_circulars,
    )

    print("SUMMARY")
    print(f"source_id: {doc.source_id}")
    print(f"title: {doc.title}")
    print(f"n_circulars: {doc.n_circulars}")
    print(f"event_text_sha256: {doc.event_text_sha256}")
    print(f"event_text_length: {len(doc.event_rendered_text)}")

    print("\nSEGMENTS")
    print("circular_id | global_start | global_end | subject")
    for segment in doc.segments:
        print(
            f"{segment.circular_id} | {segment.global_start} | "
            f"{segment.global_end} | {segment.subject}"
        )

    print("\nCHECKS")
    local_sha_ok = _verify_local_sha(doc, included_circulars)
    inverse_ok = _verify_inverse_offsets(doc)
    count_ok = doc.n_circulars == len(included_circulars) == grouped["n_included"] == 28
    print(f"segment_sha256_survives: {'OK' if local_sha_ok else 'FAIL'}")
    print(f"local_global_inverse_offsets: {'OK' if inverse_ok else 'FAIL'}")
    print(f"segment_count_is_28: {'OK' if count_ok else 'FAIL'}")

    print("\nFIRST 800 CHARACTERS")
    print(doc.event_rendered_text[:800])


def _candidate_circulars() -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for circular in iter_real_circulars(min_year=2026):
        circular_id = int(circular["circular_id"])
        if MIN_CIRCULAR_ID <= circular_id <= MAX_CIRCULAR_ID:
            candidates.append(circular)
    return sorted(candidates, key=lambda item: (str(item.get("created_on") or ""), int(item["circular_id"])))


def _verify_local_sha(doc: Any, circulars: list[dict[str, Any]]) -> bool:
    circular_by_id = {int(circular["circular_id"]): circular for circular in circulars}
    for segment in doc.segments:
        circular = circular_by_id[segment.circular_id]
        local_doc = render_canonical(
            circular_id=int(circular["circular_id"]),
            subject=str(circular.get("subject") or ""),
            body=str(circular.get("body") or ""),
            event_id=_optional_str(circular.get("event_id")),
            created_on=_optional_str(circular.get("created_on")),
            submitter=_optional_str(circular.get("submitter")),
        )
        event_slice = doc.event_rendered_text[segment.global_start : segment.global_end]
        if event_slice != local_doc.rendered_text:
            return False
        if hashlib.sha256(event_slice.encode("utf-8")).hexdigest() != segment.local_text_sha256:
            return False
    return True


def _verify_inverse_offsets(doc: Any) -> bool:
    for segment in doc.segments:
        length = segment.global_end - segment.global_start
        offsets = sorted({0, min(5, length - 1), length // 2, length - 1})
        for local_offset in offsets:
            global_offset = local_to_global(doc, segment.circular_id, local_offset)
            if global_to_circular(doc, global_offset) != (segment.circular_id, local_offset):
                return False
    return True


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


if __name__ == "__main__":
    main()
