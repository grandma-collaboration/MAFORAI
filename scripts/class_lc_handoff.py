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
    PHYSICAL_CAUSE_RE,
    ClassificationInterpretationExtractor,
    is_negated_physical_cause_context,
)
from skyportal_corpus.extraction_v2.lightcurve_evolution import (  # noqa: E402
    LightcurveEvolutionExtractor,
)


OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "gcn"
    / "sweep"
    / "class_lc_handoff.txt"
)


@dataclass(frozen=True)
class HandoffGap:
    circular_id: int
    span_start: int
    span_end: int
    text: str


@dataclass(frozen=True)
class DoubleAnnotation:
    circular_id: int
    classification_span: str
    lightcurve_span: str


def main() -> int:
    classification_extractor = ClassificationInterpretationExtractor()
    lightcurve_extractor = LightcurveEvolutionExtractor()
    n_circulars = 0
    n_formerly_deferred = 0
    n_captured_here = 0
    handoff_gaps: list[HandoffGap] = []
    doubles: list[DoubleAnnotation] = []

    for circular in iter_real_circulars(limit=100000):
        n_circulars += 1
        doc = _render(circular)
        classifications = classification_extractor.extract(doc)
        lightcurves = lightcurve_extractor.extract(doc)

        for match in PHYSICAL_CAUSE_RE.finditer(doc.rendered_text):
            if is_negated_physical_cause_context(
                doc.rendered_text,
                match.start(),
            ):
                continue
            n_formerly_deferred += 1
            if any(
                annotation.span_start < match.end()
                and match.start() < annotation.span_end
                for annotation in classifications
            ):
                n_captured_here += 1
            else:
                handoff_gaps.append(
                    HandoffGap(
                        circular_id=doc.circular_id,
                        span_start=match.start(),
                        span_end=match.end(),
                        text=match.group(0),
                    )
                )

        for classification in classifications:
            for lightcurve in lightcurves:
                if not _overlaps(
                    classification.span_start,
                    classification.span_end,
                    lightcurve.span_start,
                    lightcurve.span_end,
                ):
                    continue
                doubles.append(
                    DoubleAnnotation(
                        circular_id=doc.circular_id,
                        classification_span=(
                            f"{classification.span_start}:"
                            f"{classification.span_end} "
                            f"{classification.text!r}"
                        ),
                        lightcurve_span=(
                            f"{lightcurve.span_start}:{lightcurve.span_end} "
                            f"{lightcurve.text!r}"
                        ),
                    )
                )

    report = render_report(
        n_circulars=n_circulars,
        n_formerly_deferred=n_formerly_deferred,
        n_captured_here=n_captured_here,
        handoff_gaps=handoff_gaps,
        doubles=doubles,
    )
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(report, encoding="utf-8")

    print(f"Wrote handoff audit to {OUTPUT_PATH.relative_to(PROJECT_ROOT)}")
    print(f"Circulars scanned: {n_circulars}")
    print(f"Formerly deferred physical-cause clauses: {n_formerly_deferred}")
    print(f"Captured by CLASSIFICATION_INTERPRETATION: {n_captured_here}")
    print(f"Handoff gaps: {len(handoff_gaps)}")
    print(f"Double-annotated spans: {len(doubles)}")
    return 0 if not handoff_gaps and not doubles else 1


def render_report(
    *,
    n_circulars: int,
    n_formerly_deferred: int,
    n_captured_here: int,
    handoff_gaps: list[HandoffGap],
    doubles: list[DoubleAnnotation],
) -> str:
    lines = [
        "=" * 100,
        "CLASSIFICATION_INTERPRETATION / LIGHTCURVE_EVOLUTION HANDOFF AUDIT",
        "=" * 100,
        f"circulars_scanned: {n_circulars}",
        f"formerly_deferred_physical_causes: {n_formerly_deferred}",
        f"captured_by_classification_interpretation: {n_captured_here}",
        f"handoff_gaps: {len(handoff_gaps)}",
        f"double_annotated_spans: {len(doubles)}",
        "",
        "HANDOFF GAPS",
    ]
    if not handoff_gaps:
        lines.append("  (none)")
    else:
        for gap in handoff_gaps:
            lines.append(
                f"  circular_id={gap.circular_id} "
                f"span={gap.span_start}:{gap.span_end} text={gap.text!r}"
            )

    lines.extend(["", "DOUBLE-ANNOTATED SPANS"])
    if not doubles:
        lines.append("  (none)")
    else:
        for item in doubles:
            lines.extend(
                [
                    f"  circular_id={item.circular_id}",
                    f"    CLASSIFICATION_INTERPRETATION "
                    f"{item.classification_span}",
                    f"    LIGHTCURVE_EVOLUTION {item.lightcurve_span}",
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


def _overlaps(
    first_start: int,
    first_end: int,
    second_start: int,
    second_end: int,
) -> bool:
    return first_start < second_end and second_start < first_end


if __name__ == "__main__":
    raise SystemExit(main())
