from __future__ import annotations

import re
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
from skyportal_corpus.extraction_v2.annotations import (  # noqa: E402
    EventEvidenceAnnotation,
)
from skyportal_corpus.extraction_v2.negative_statement import (  # noqa: E402
    NegativeStatementExtractor,
    is_photometric_negative_context,
    sentence_bounds,
)
from skyportal_corpus.extraction_v2.photometry_annotations import (  # noqa: E402
    PhotometricMeasurementAnnotation,
)
from skyportal_corpus.extraction_v2.photometry_prose import (  # noqa: E402
    ProsePhotometryExtractor,
)
from skyportal_corpus.extraction_v2.photometry_rows import (  # noqa: E402
    parse_table_to_measurements,
)
from skyportal_corpus.extraction_v2.photometry_tables import (  # noqa: E402
    detect_table_blocks,
)


OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "gcn"
    / "sweep"
    / "negstmt_between_layer_gaps.txt"
)
_PHOTOMETRIC_NEGATIVE_SIGNAL_RE = re.compile(
    r"\b(?:"
    r"not\s+detected|no\s+detection|no\s+evidence|"
    r"no\s+(?:confirmed\s+)?"
    r"(?:(?:optical|X[- ]?ray|radio|NIR|UV|gamma[- ]?ray)\s+)?"
    r"counterpart(?:\s+candidates?)?"
    r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DeferredPhotometricNegative:
    sentence_start: int
    sentence_end: int
    sentence: str
    signals: tuple[str, ...]


@dataclass(frozen=True)
class BetweenLayerGap:
    circular_id: int
    subject: str
    sentence_start: int
    sentence_end: int
    sentence: str
    signals: tuple[str, ...]


def main() -> int:
    negative_extractor = NegativeStatementExtractor()
    prose_extractor = ProsePhotometryExtractor()
    n_circulars = 0
    n_deferred_sentences = 0
    n_deferred_circulars = 0
    n_owned_circulars = 0
    gaps: list[BetweenLayerGap] = []

    for circular in iter_real_circulars(limit=100000):
        n_circulars += 1
        doc = _render(circular)
        negative_annotations = negative_extractor.extract(doc)
        deferred = find_deferred_photometric_negatives(
            doc.rendered_text,
            negative_annotations,
        )
        if not deferred:
            continue

        n_deferred_circulars += 1
        n_deferred_sentences += len(deferred)
        photometric_limits = [
            measurement
            for measurement in extract_photometry(doc, prose_extractor)
            if measurement.measurement_type in {"non_detection", "upper_limit"}
        ]
        if photometric_limits:
            n_owned_circulars += 1
            continue

        for item in deferred:
            gaps.append(
                BetweenLayerGap(
                    circular_id=doc.circular_id,
                    subject=doc.subject,
                    sentence_start=item.sentence_start,
                    sentence_end=item.sentence_end,
                    sentence=item.sentence,
                    signals=item.signals,
                )
            )

    gaps.sort(
        key=lambda item: (
            item.circular_id,
            item.sentence_start,
            item.sentence_end,
        )
    )
    report = render_report(
        n_circulars=n_circulars,
        n_deferred_sentences=n_deferred_sentences,
        n_deferred_circulars=n_deferred_circulars,
        n_owned_circulars=n_owned_circulars,
        gaps=gaps,
    )
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(report, encoding="utf-8")

    offending_ids = sorted({gap.circular_id for gap in gaps})
    print(f"Wrote between-layer audit to {OUTPUT_PATH.relative_to(PROJECT_ROOT)}")
    print(f"Circulars scanned: {n_circulars}")
    print(f"Deferred photometric-negative sentences: {n_deferred_sentences}")
    print(f"Deferred photometric-negative circulars: {n_deferred_circulars}")
    print(f"Circulars owned by photometry: {n_owned_circulars}")
    print(f"Between-layer gap circulars: {len(offending_ids)}")
    if offending_ids:
        print("First offending circulars:")
        for circular_id in offending_ids[:10]:
            first = next(gap for gap in gaps if gap.circular_id == circular_id)
            print(f"  {circular_id}: {first.subject}")
    else:
        print("First offending circulars: (none)")
    return 0


def find_deferred_photometric_negatives(
    text: str,
    negative_annotations: list[EventEvidenceAnnotation],
) -> list[DeferredPhotometricNegative]:
    by_sentence: dict[tuple[int, int], list[str]] = {}
    for match in _PHOTOMETRIC_NEGATIVE_SIGNAL_RE.finditer(text):
        if not is_photometric_negative_context(text, match.start(), match.end()):
            continue
        if any(
            annotation.span_start < match.end()
            and match.start() < annotation.span_end
            for annotation in negative_annotations
        ):
            continue
        bounds = sentence_bounds(text, match.start(), match.end())
        by_sentence.setdefault(bounds, []).append(match.group(0))

    return [
        DeferredPhotometricNegative(
            sentence_start=start,
            sentence_end=end,
            sentence=text[start:end].strip(),
            signals=tuple(signals),
        )
        for (start, end), signals in sorted(by_sentence.items())
    ]


def extract_photometry(
    doc: CanonicalDocument,
    prose_extractor: ProsePhotometryExtractor,
) -> list[PhotometricMeasurementAnnotation]:
    measurements = [
        measurement
        for block in detect_table_blocks(doc.rendered_text)
        for measurement in parse_table_to_measurements(block, doc)
    ]
    measurements.extend(prose_extractor.extract(doc))
    return sorted(
        measurements,
        key=lambda item: (
            item.span_start,
            item.span_end,
            item.measurement_type,
            item.rule_id or "",
        ),
    )


def render_report(
    *,
    n_circulars: int,
    n_deferred_sentences: int,
    n_deferred_circulars: int,
    n_owned_circulars: int,
    gaps: list[BetweenLayerGap],
) -> str:
    offending_ids = sorted({gap.circular_id for gap in gaps})
    lines = [
        "=" * 100,
        "NEGATIVE_STATEMENT / PHOTOMETRY BETWEEN-LAYER GAP AUDIT",
        "=" * 100,
        f"circulars_scanned: {n_circulars}",
        f"deferred_photometric_negative_sentences: {n_deferred_sentences}",
        f"deferred_photometric_negative_circulars: {n_deferred_circulars}",
        f"circulars_with_photometric_limit: {n_owned_circulars}",
        f"between_layer_gap_circulars: {len(offending_ids)}",
        f"between_layer_gap_sentences: {len(gaps)}",
        "",
        "OFFENDERS",
    ]
    if not gaps:
        lines.append("  (none)")
    else:
        for gap in gaps:
            lines.extend(
                [
                    f"  circular_id={gap.circular_id} subject={gap.subject}",
                    f"    offsets={gap.sentence_start}:{gap.sentence_end}",
                    f"    signals={list(gap.signals)!r}",
                    f"    SENTENCE: {gap.sentence}",
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


if __name__ == "__main__":
    raise SystemExit(main())
