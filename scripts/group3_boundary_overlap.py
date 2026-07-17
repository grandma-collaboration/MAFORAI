from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from skyportal_corpus.canonical.document import (  # noqa: E402
    CanonicalDocument,
    iter_real_circulars,
    render_canonical,
)
from skyportal_corpus.extraction_v2.classification_interpretation import (  # noqa: E402
    ClassificationInterpretationExtractor,
)
from skyportal_corpus.extraction_v2.host_context import (  # noqa: E402
    HostContextExtractor,
)
from skyportal_corpus.extraction_v2.redshift import RedshiftExtractor  # noqa: E402
from skyportal_corpus.extraction_v2.spectroscopy import (  # noqa: E402
    SpectroscopyExtractor,
)


OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "gcn"
    / "sweep"
    / "group3_boundary_overlap.txt"
)
MAX_DISPLAY = 50


@dataclass(frozen=True)
class BoundaryOverlap:
    circular_id: int
    boundary: str
    first_span: str
    second_span: str


def main() -> int:
    host_extractor = HostContextExtractor()
    spectroscopy_extractor = SpectroscopyExtractor()
    redshift_extractor = RedshiftExtractor()
    classification_extractor = ClassificationInterpretationExtractor()
    counts = {
        "circulars": 0,
        "host_context": 0,
        "spectroscopy": 0,
        "redshift_event": 0,
        "redshift_context": 0,
        "classification_interpretation": 0,
    }
    overlaps: list[BoundaryOverlap] = []

    for circular in iter_real_circulars(limit=100000):
        counts["circulars"] += 1
        doc = _render(circular)
        hosts = host_extractor.extract(doc)
        spectroscopy = spectroscopy_extractor.extract(doc)
        redshifts = redshift_extractor.extract(doc)
        classifications = classification_extractor.extract(doc)
        redshift_events = [
            annotation
            for annotation in redshifts
            if annotation.label == "REDSHIFT_EVENT"
        ]
        redshift_contexts = [
            annotation
            for annotation in redshifts
            if annotation.label == "REDSHIFT_CONTEXT"
        ]

        counts["host_context"] += len(hosts)
        counts["spectroscopy"] += len(spectroscopy)
        counts["redshift_event"] += len(redshift_events)
        counts["redshift_context"] += len(redshift_contexts)
        counts["classification_interpretation"] += len(classifications)

        overlaps.extend(
            _find_overlaps(
                doc.circular_id,
                "HOST_CONTEXT & REDSHIFT_CONTEXT",
                hosts,
                redshift_contexts,
            )
        )
        overlaps.extend(
            _find_overlaps(
                doc.circular_id,
                "SPECTROSCOPY & REDSHIFT_EVENT",
                spectroscopy,
                redshift_events,
            )
        )
        overlaps.extend(
            _find_overlaps(
                doc.circular_id,
                "SPECTROSCOPY & CLASSIFICATION_INTERPRETATION",
                spectroscopy,
                classifications,
            )
        )

    report = render_report(counts, overlaps)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(report, encoding="utf-8")

    print(f"Wrote group-3 boundary audit to {OUTPUT_PATH.relative_to(PROJECT_ROOT)}")
    print(f"Circulars scanned: {counts['circulars']}")
    print(f"HOST_CONTEXT annotations: {counts['host_context']}")
    print(f"SPECTROSCOPY annotations: {counts['spectroscopy']}")
    print(f"REDSHIFT_EVENT annotations: {counts['redshift_event']}")
    print(f"REDSHIFT_CONTEXT annotations: {counts['redshift_context']}")
    print(
        "CLASSIFICATION_INTERPRETATION annotations: "
        f"{counts['classification_interpretation']}"
    )
    print(f"Boundary overlaps: {len(overlaps)}")
    return 0 if not overlaps else 1


def render_report(
    counts: dict[str, int],
    overlaps: list[BoundaryOverlap],
) -> str:
    by_boundary = {
        boundary: [
            overlap for overlap in overlaps if overlap.boundary == boundary
        ]
        for boundary in (
            "HOST_CONTEXT & REDSHIFT_CONTEXT",
            "SPECTROSCOPY & REDSHIFT_EVENT",
            "SPECTROSCOPY & CLASSIFICATION_INTERPRETATION",
        )
    }
    lines = [
        "=" * 100,
        "GROUP 3 BOUNDARY OVERLAP AUDIT",
        "=" * 100,
        f"circulars_scanned: {counts['circulars']}",
        f"host_context_annotations: {counts['host_context']}",
        f"spectroscopy_annotations: {counts['spectroscopy']}",
        f"redshift_event_annotations: {counts['redshift_event']}",
        f"redshift_context_annotations: {counts['redshift_context']}",
        "classification_interpretation_annotations: "
        f"{counts['classification_interpretation']}",
        f"boundary_overlaps: {len(overlaps)}",
    ]
    for boundary, items in by_boundary.items():
        lines.extend(["", f"{boundary}: {len(items)}"])
        if not items:
            lines.append("  (none)")
            continue
        for item in items[:MAX_DISPLAY]:
            lines.extend(
                [
                    f"  circular_id={item.circular_id}",
                    f"    first:  {item.first_span}",
                    f"    second: {item.second_span}",
                ]
            )
    return "\n".join(lines) + "\n"


def _find_overlaps(
    circular_id: int,
    boundary: str,
    first_annotations: list[object],
    second_annotations: list[object],
) -> list[BoundaryOverlap]:
    overlaps: list[BoundaryOverlap] = []
    for first in first_annotations:
        first_start = int(getattr(first, "span_start"))
        first_end = int(getattr(first, "span_end"))
        for second in second_annotations:
            second_start = int(getattr(second, "span_start"))
            second_end = int(getattr(second, "span_end"))
            if not _overlaps(first_start, first_end, second_start, second_end):
                continue
            overlaps.append(
                BoundaryOverlap(
                    circular_id=circular_id,
                    boundary=boundary,
                    first_span=(
                        f"{first_start}:{first_end} "
                        f"{getattr(first, 'text')!r}"
                    ),
                    second_span=(
                        f"{second_start}:{second_end} "
                        f"{getattr(second, 'text')!r}"
                    ),
                )
            )
    return overlaps


def _render(circular: dict[str, object]) -> CanonicalDocument:
    return render_canonical(
        circular_id=int(circular["circular_id"]),
        subject=str(circular.get("subject") or ""),
        body=str(circular.get("body") or ""),
        event_id=circular.get("event_id"),  # type: ignore[arg-type]
        created_on=circular.get("created_on"),  # type: ignore[arg-type]
        submitter=circular.get("submitter"),  # type: ignore[arg-type]
    )


def _overlaps(
    first_start: int,
    first_end: int,
    second_start: int,
    second_end: int,
) -> bool:
    return first_start < second_end and second_start < first_end


if __name__ == "__main__":
    raise SystemExit(main())
