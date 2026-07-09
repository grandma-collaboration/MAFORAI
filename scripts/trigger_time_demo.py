from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from skyportal_corpus.canonical.document import CanonicalDocument, iter_real_circulars, render_canonical  # noqa: E402
from skyportal_corpus.extraction_v2.annotations import EventEvidenceAnnotation  # noqa: E402
from skyportal_corpus.extraction_v2.trigger_time import TriggerTimeExtractor  # noqa: E402


DemoChoice = tuple[dict[str, Any], CanonicalDocument, list[EventEvidenceAnnotation]]


def main() -> int:
    extractor = TriggerTimeExtractor()
    first: DemoChoice | None = None
    chosen: DemoChoice | None = None

    for circular in iter_real_circulars(limit=50):
        doc = render_canonical(**circular)
        annotations = extractor.extract(doc)
        if first is None:
            first = (circular, doc, annotations)
        if annotations:
            chosen = (circular, doc, annotations)
            break

    if chosen is None:
        if first is None:
            print("No circulars found for demo.")
            return 1
        print("No trigger time with context found in the first 50 circulars; using the first one.")
        chosen = first

    circular, doc, annotations = chosen
    created_on = str(circular.get("created_on") or "")
    year = _year_from_created_on(created_on)

    print(f"circular_id: {doc.circular_id}")
    print(f"year: {year}")
    print(f"created_on: {created_on}")
    print(f"subject: {doc.subject}")
    print("annotations:")
    if annotations:
        for annotation in annotations:
            print(
                f"  - label={annotation.label} target={annotation.target} "
                f"certainty={annotation.certainty} value={annotation.value} "
                f"span={annotation.span_start}-{annotation.span_end} text={annotation.text!r} "
                f"rule_id={annotation.rule_id} needs_review={annotation.needs_review} "
                f"comment={annotation.comment!r}"
            )
    else:
        print("  (none)")

    print("rendered_text_marked:")
    print(_mark_spans(doc.rendered_text, annotations))

    print("checks:")
    for annotation in annotations:
        print(f"  {annotation.value} {annotation.span_start}-{annotation.span_end}: {_status(annotation.verify(doc.rendered_text))}")

    return 0


def _mark_spans(rendered_text: str, annotations: list[EventEvidenceAnnotation]) -> str:
    marked = rendered_text
    for annotation in sorted(annotations, key=lambda item: item.span_start, reverse=True):
        marked = marked[: annotation.span_end] + "⟧" + marked[annotation.span_end :]
        marked = marked[: annotation.span_start] + "⟦" + marked[annotation.span_start :]
    return marked


def _year_from_created_on(value: str) -> int | None:
    if len(value) >= 4 and value[:4].isdigit():
        return int(value[:4])
    try:
        timestamp_ms = float(value)
    except ValueError:
        return None
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).year


def _status(ok: bool) -> str:
    return "OK" if ok else "FAIL"


if __name__ == "__main__":
    raise SystemExit(main())
