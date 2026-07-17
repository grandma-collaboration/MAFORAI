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
from skyportal_corpus.extraction_v2.counterpart_association import (  # noqa: E402
    CounterpartAssociationExtractor,
)
from skyportal_corpus.extraction_v2.event_identity import (  # noqa: E402
    EventIdentityExtractor,
)
from skyportal_corpus.extraction_v2.negative_statement import (  # noqa: E402
    NegativeStatementExtractor,
)


OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "gcn"
    / "sweep"
    / "counterpart_boundary_overlap.txt"
)


@dataclass(frozen=True)
class BoundaryOverlap:
    circular_id: int
    counterpart_span: str
    other_label: str
    other_span: str


def main() -> int:
    counterpart_extractor = CounterpartAssociationExtractor()
    identity_extractor = EventIdentityExtractor()
    negative_extractor = NegativeStatementExtractor()
    n_circulars = 0
    n_counterpart = 0
    n_identity = 0
    n_negative = 0
    overlaps: list[BoundaryOverlap] = []

    for circular in iter_real_circulars(limit=100000):
        n_circulars += 1
        doc = _render(circular)
        counterparts = counterpart_extractor.extract(doc)
        identities = identity_extractor.extract(doc)
        negatives = negative_extractor.extract(doc)
        n_counterpart += len(counterparts)
        n_identity += len(identities)
        n_negative += len(negatives)

        for counterpart in counterparts:
            for other in [*identities, *negatives]:
                if not _overlaps(
                    counterpart.span_start,
                    counterpart.span_end,
                    other.span_start,
                    other.span_end,
                ):
                    continue
                overlaps.append(
                    BoundaryOverlap(
                        circular_id=doc.circular_id,
                        counterpart_span=(
                            f"{counterpart.span_start}:{counterpart.span_end} "
                            f"{counterpart.text!r}"
                        ),
                        other_label=other.label,
                        other_span=(
                            f"{other.span_start}:{other.span_end} {other.text!r}"
                        ),
                    )
                )

    report = render_report(
        n_circulars=n_circulars,
        n_counterpart=n_counterpart,
        n_identity=n_identity,
        n_negative=n_negative,
        overlaps=overlaps,
    )
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(report, encoding="utf-8")

    print(f"Wrote boundary audit to {OUTPUT_PATH.relative_to(PROJECT_ROOT)}")
    print(f"Circulars scanned: {n_circulars}")
    print(f"COUNTERPART_ASSOCIATION annotations: {n_counterpart}")
    print(f"EVENT_IDENTITY annotations: {n_identity}")
    print(f"NEGATIVE_STATEMENT annotations: {n_negative}")
    print(f"Boundary overlaps: {len(overlaps)}")
    return 0 if not overlaps else 1


def render_report(
    *,
    n_circulars: int,
    n_counterpart: int,
    n_identity: int,
    n_negative: int,
    overlaps: list[BoundaryOverlap],
) -> str:
    lines = [
        "=" * 100,
        "COUNTERPART_ASSOCIATION BOUNDARY OVERLAP AUDIT",
        "=" * 100,
        f"circulars_scanned: {n_circulars}",
        f"counterpart_association_annotations: {n_counterpart}",
        f"event_identity_annotations: {n_identity}",
        f"negative_statement_annotations: {n_negative}",
        f"boundary_overlaps: {len(overlaps)}",
        "",
        "OVERLAPS",
    ]
    if not overlaps:
        lines.append("  (none)")
    else:
        for item in overlaps:
            lines.extend(
                [
                    f"  circular_id={item.circular_id}",
                    f"    COUNTERPART_ASSOCIATION {item.counterpart_span}",
                    f"    {item.other_label} {item.other_span}",
                ]
            )
    return "\n".join(lines) + "\n"


def _render(circular: dict[str, object]) -> CanonicalDocument:
    return render_canonical(
        circular_id=int(circular["circular_id"]),
        subject=str(circular.get("subject") or ""),
        body=str(circular.get("body") or ""),
        event_id=circular.get("event_id"),  # type: ignore[arg-type]
        created_on=circular.get("created_on"),  # type: ignore[arg-type]
        submitter=circular.get("submitter"),  # type: ignore[arg-type]
    )


def _overlaps(first_start: int, first_end: int, second_start: int, second_end: int) -> bool:
    return first_start < second_end and second_start < first_end


if __name__ == "__main__":
    raise SystemExit(main())
