from __future__ import annotations

import sys
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
from skyportal_corpus.extraction_v2.negative_statement import (  # noqa: E402
    NegativeStatementExtractor,
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
    / "negstmt_photometry_overlap.txt"
)


def main() -> int:
    negative_extractor = NegativeStatementExtractor()
    prose_extractor = ProsePhotometryExtractor()
    n_circulars = 0
    n_negative = 0
    n_photometric_limits = 0
    overlaps: list[tuple[int, str, str]] = []

    for circular in iter_real_circulars(limit=100000):
        n_circulars += 1
        doc = _render(circular)
        negative_annotations = negative_extractor.extract(doc)
        photometry = _extract_photometry(doc, prose_extractor)
        limits = [
            measurement
            for measurement in photometry
            if measurement.measurement_type in {"non_detection", "upper_limit"}
        ]
        n_negative += len(negative_annotations)
        n_photometric_limits += len(limits)
        for negative in negative_annotations:
            for measurement in limits:
                if _overlaps(
                    negative.span_start,
                    negative.span_end,
                    measurement.span_start,
                    measurement.span_end,
                ):
                    overlaps.append(
                        (
                            doc.circular_id,
                            (
                                f"NEGATIVE_STATEMENT "
                                f"{negative.span_start}:{negative.span_end} "
                                f"{negative.text!r}"
                            ),
                            (
                                f"PHOTOMETRIC_MEASUREMENT[{measurement.measurement_type}] "
                                f"{measurement.span_start}:{measurement.span_end} "
                                f"{measurement.text!r}"
                            ),
                        )
                    )

    report = _render_report(
        n_circulars=n_circulars,
        n_negative=n_negative,
        n_photometric_limits=n_photometric_limits,
        overlaps=overlaps,
    )
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(report, encoding="utf-8")
    print(f"Wrote overlap audit to {OUTPUT_PATH.relative_to(PROJECT_ROOT)}")
    print(f"Circulars scanned: {n_circulars}")
    print(f"NEGATIVE_STATEMENT annotations: {n_negative}")
    print(f"Photometric non-detections/upper limits: {n_photometric_limits}")
    print(f"Overlaps: {len(overlaps)}")
    return 0 if not overlaps else 1


def _extract_photometry(
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


def _render_report(
    *,
    n_circulars: int,
    n_negative: int,
    n_photometric_limits: int,
    overlaps: list[tuple[int, str, str]],
) -> str:
    lines = [
        "=" * 100,
        "NEGATIVE_STATEMENT / PHOTOMETRIC_MEASUREMENT OVERLAP AUDIT",
        "=" * 100,
        f"circulars_scanned: {n_circulars}",
        f"negative_statement_annotations: {n_negative}",
        f"photometric_non_detections_or_upper_limits: {n_photometric_limits}",
        f"overlaps: {len(overlaps)}",
        "",
        "OVERLAPS",
    ]
    if not overlaps:
        lines.append("  (none)")
    else:
        for circular_id, negative, photometry in overlaps:
            lines.extend(
                [
                    f"  circular_id={circular_id}",
                    f"    {negative}",
                    f"    {photometry}",
                ]
            )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
