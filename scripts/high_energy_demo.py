from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from skyportal_corpus.canonical.document import CanonicalDocument, iter_real_circulars, render_canonical  # noqa: E402
from skyportal_corpus.extraction_v2.annotations import EventEvidenceAnnotation  # noqa: E402
from skyportal_corpus.extraction_v2.high_energy import HighEnergyPropertyExtractor  # noqa: E402


DemoChoice = tuple[dict[str, Any], CanonicalDocument, list[EventEvidenceAnnotation]]


def main() -> int:
    chosen = _find_demo(HighEnergyPropertyExtractor())
    if chosen is None:
        print("No real circular with a high-energy property was found in the search window.")
        return 1
    circular, doc, annotations = chosen
    _print_demo(circular, doc, annotations)
    return 0


def _find_demo(extractor: HighEnergyPropertyExtractor) -> DemoChoice | None:
    for circular in iter_real_circulars(limit=2000):
        doc = render_canonical(**circular)
        annotations = extractor.extract(doc)
        if annotations:
            return circular, doc, annotations
    return None


def _print_demo(
    circular: dict[str, Any],
    doc: CanonicalDocument,
    annotations: list[EventEvidenceAnnotation],
) -> None:
    print(f"circular_id: {doc.circular_id}")
    print(f"created_on: {circular.get('created_on')}")
    print(f"subject: {doc.subject}")
    print("annotations:")
    for annotation in annotations:
        print(
            f"  - label={annotation.label} target={annotation.target} "
            f"certainty={annotation.certainty} value={annotation.value!r} unit={annotation.unit!r} "
            f"span={annotation.span_start}-{annotation.span_end} rule_id={annotation.rule_id} "
            f"needs_review={annotation.needs_review} comment={annotation.comment!r} "
            f"verify={'OK' if annotation.verify(doc.rendered_text) else 'FAIL'}"
        )
        print(f"    text={annotation.text!r}")
    print("rendered_text_marked:")
    print(_mark_spans(doc.rendered_text, annotations))


def _mark_spans(text: str, annotations: list[EventEvidenceAnnotation]) -> str:
    marked = text
    for annotation in sorted(annotations, key=lambda item: item.span_start, reverse=True):
        marked = marked[: annotation.span_end] + "]]" + marked[annotation.span_end :]
        marked = marked[: annotation.span_start] + "[[" + marked[annotation.span_start :]
    return marked


if __name__ == "__main__":
    raise SystemExit(main())
