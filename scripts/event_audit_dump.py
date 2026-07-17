from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from event_xmi_export import (  # noqa: E402
    ALIASES,
    SOURCE_ID,
    TITLE,
    _candidate_circulars,
    _canonical_documents,
)
from skyportal_corpus.canonical.document import CanonicalDocument  # noqa: E402
from skyportal_corpus.extraction_v2.annotations import EventEvidenceAnnotation  # noqa: E402
from skyportal_corpus.extraction_v2.event_annotations import extract_event_annotations  # noqa: E402
from skyportal_corpus.extraction_v2.event_document import (  # noqa: E402
    CircularSegment,
    EventCanonicalDocument,
    build_event_document,
)
from skyportal_corpus.extraction_v2.event_grouping import group_event_circulars  # noqa: E402
from skyportal_corpus.extraction_v2.event_photometry import (  # noqa: E402
    EventPhotometricMeasurementAnnotation,
    extract_event_photometry,
)


OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "gcn"
    / "sweep"
    / "event_2026owq_audit.txt"
)


def main() -> int:
    event_doc, circular_docs, evidence, photometry, translation_errors = _build_event()
    report = render_audit(
        event_doc,
        circular_docs,
        evidence,
        photometry,
        translation_errors,
    )
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(report, encoding="utf-8")
    print(f"Wrote event audit to {OUTPUT_PATH.relative_to(PROJECT_ROOT)}")
    print(f"Total lines: {report.count(chr(10))}")
    return 0


def _build_event() -> tuple[
    EventCanonicalDocument,
    dict[int, CanonicalDocument],
    list[EventEvidenceAnnotation],
    list[EventPhotometricMeasurementAnnotation],
    list[dict[str, Any]],
]:
    candidates = _candidate_circulars()
    grouped = group_event_circulars(
        source_id=SOURCE_ID,
        title=TITLE,
        aliases=ALIASES,
        circulars=candidates,
    )
    included_ids = {int(item["circular_id"]) for item in grouped["included"]}
    included_circulars = [
        circular
        for circular in candidates
        if int(circular["circular_id"]) in included_ids
    ]
    event_doc = build_event_document(
        source_id=SOURCE_ID,
        title=TITLE,
        circulars_in_order=included_circulars,
    )
    circular_docs = _canonical_documents(included_circulars)

    evidence_errors: list[dict[str, Any]] = []
    evidence = extract_event_annotations(
        event_doc,
        circular_docs,
        errors=evidence_errors,
    )
    photometry_errors: list[dict[str, Any]] = []
    photometry = extract_event_photometry(
        event_doc,
        circular_docs,
        errors=photometry_errors,
    )
    translation_errors = [
        {"layer": "EVENT_EVIDENCE", **error}
        for error in evidence_errors
    ] + [
        {"layer": "PHOTOMETRIC_MEASUREMENT", **error}
        for error in photometry_errors
    ]
    return event_doc, circular_docs, evidence, photometry, translation_errors


def render_audit(
    event_doc: EventCanonicalDocument,
    circular_docs: dict[int, CanonicalDocument],
    evidence: list[EventEvidenceAnnotation],
    photometry: list[EventPhotometricMeasurementAnnotation],
    translation_errors: list[dict[str, Any]],
) -> str:
    evidence_by_circular: dict[int, list[EventEvidenceAnnotation]] = defaultdict(list)
    for annotation in evidence:
        circular_id = annotation.source_circular_id or annotation.circular_id
        evidence_by_circular[circular_id].append(annotation)

    photometry_by_circular: dict[int, list[EventPhotometricMeasurementAnnotation]] = defaultdict(list)
    for measurement in photometry:
        photometry_by_circular[measurement.source_circular_id].append(measurement)

    lines = [
        "HEADER",
        "======",
        f"source_id: {event_doc.source_id}",
        f"title: {event_doc.title}",
        f"n_circulars: {event_doc.n_circulars}",
        f"event_text_length: {len(event_doc.event_rendered_text)}",
        f"event_text_sha256: {event_doc.event_text_sha256}",
        f"n_event_evidence: {len(evidence)}",
        f"n_photometry: {len(photometry)}",
        f"n_needs_review_event_evidence: {sum(item.needs_review for item in evidence)}",
    ]
    verify_failures: list[str] = []

    for segment in event_doc.segments:
        circular_doc = circular_docs[segment.circular_id]
        circular_evidence = sorted(
            evidence_by_circular.get(segment.circular_id, []),
            key=lambda item: (
                item.span_start - segment.global_start,
                item.span_end - segment.global_start,
                item.extractor_id,
                item.rule_id or "",
            ),
        )
        circular_photometry = sorted(
            photometry_by_circular.get(segment.circular_id, []),
            key=lambda item: (
                item.span_start - segment.global_start,
                item.span_end - segment.global_start,
                item.method,
                item.rule_id or "",
            ),
        )
        lines.extend(
            _render_circular(
                segment,
                circular_doc,
                circular_evidence,
                circular_photometry,
                verify_failures,
            )
        )

    lines.extend(
        _render_summary(
            evidence,
            verify_failures,
            translation_errors,
        )
    )
    return "\n".join(lines).rstrip() + "\n"


def _render_circular(
    segment: CircularSegment,
    circular_doc: CanonicalDocument,
    evidence: list[EventEvidenceAnnotation],
    photometry: list[EventPhotometricMeasurementAnnotation],
    verify_failures: list[str],
) -> list[str]:
    lines = [
        "",
        (
            f"==== CIRCULAR {segment.circular_id} | "
            f"{segment.created_on or ''} | {segment.subject} ===="
        ),
        f"local_text_length: {len(circular_doc.rendered_text)}",
        f"n_event_evidence: {len(evidence)}",
        f"n_photometry: {len(photometry)}",
        "--- EVENT_EVIDENCE (sorted by local span_start) ---",
    ]

    if not evidence:
        lines.append("  (none)")
    for annotation in evidence:
        local_start, local_end = _local_span(segment, annotation.span_start, annotation.span_end)
        verified = _local_verify(circular_doc.rendered_text, local_start, local_end, annotation.text)
        lines.extend(
            [
                (
                    f"  [{annotation.label}] target={_display(annotation.target)} "
                    f"certainty={annotation.certainty} needs_review={annotation.needs_review}"
                ),
                (
                    f"               rule_id={_display(annotation.rule_id)} "
                    f"extractor_id={annotation.extractor_id}"
                ),
            ]
        )
        _append_quoted(lines, "    SRC: ", annotation.text, "         ")
        _append_context(lines, circular_doc.rendered_text, local_start, local_end)
        lines.append(f"    verify: {'OK' if verified else 'FAIL'}")
        if not verified:
            verify_failures.append(
                f"circular_id={segment.circular_id} layer=EVENT_EVIDENCE "
                f"label={annotation.label} global_span={annotation.span_start}-{annotation.span_end}"
            )

    lines.append("--- PHOTOMETRIC_MEASUREMENT (sorted by local span_start) ---")
    if not photometry:
        lines.append("  (none)")
    for measurement in photometry:
        local_start, local_end = _local_span(segment, measurement.span_start, measurement.span_end)
        verified = _local_verify(
            circular_doc.rendered_text,
            local_start,
            local_end,
            measurement.text,
        )
        lines.extend(
            [
                (
                    f"  [PHOTOMETRY] type={measurement.measurement_type} "
                    f"band={_display(measurement.photometric_band)} "
                    f"system={_display(measurement.photometric_system)}"
                ),
                (
                    f"               value/limit={_display(measurement.magnitude_or_limit)} "
                    f"limit_sigma={_display(measurement.limit_sigma)} "
                    f"needs_review={measurement.needs_review}"
                ),
            ]
        )
        _append_quoted(lines, "    SRC: ", measurement.text, "         ")
        _append_context(lines, circular_doc.rendered_text, local_start, local_end)
        lines.append(f"    verify: {'OK' if verified else 'FAIL'}")
        if not verified:
            verify_failures.append(
                f"circular_id={segment.circular_id} layer=PHOTOMETRIC_MEASUREMENT "
                f"type={measurement.measurement_type} "
                f"global_span={measurement.span_start}-{measurement.span_end}"
            )
    return lines


def _render_summary(
    evidence: list[EventEvidenceAnnotation],
    verify_failures: list[str],
    translation_errors: list[dict[str, Any]],
) -> list[str]:
    label_counts = Counter(item.label for item in evidence)
    rule_counts = Counter(item.rule_id or "None" for item in evidence)
    certainty_counts = Counter(item.certainty for item in evidence)
    needs_review = sorted(
        (item for item in evidence if item.needs_review),
        key=lambda item: (
            item.source_circular_id or item.circular_id,
            item.span_start,
            item.span_end,
            item.label,
        ),
    )

    lines = ["", "SUMMARY", "=======", "COUNTS BY LABEL"]
    lines.extend(f"{label}: {count}" for label, count in sorted(label_counts.items()))
    lines.extend(["", "COUNTS BY RULE_ID"])
    lines.extend(f"{rule_id}: {count}" for rule_id, count in sorted(rule_counts.items()))
    lines.extend(["", "COUNTS BY CERTAINTY"])
    lines.extend(
        f"{certainty}: {count}"
        for certainty, count in sorted(certainty_counts.items())
    )
    lines.extend(["", "NEEDS_REVIEW=True EVENT_EVIDENCE"])
    if not needs_review:
        lines.append("(none)")
    for annotation in needs_review:
        circular_id = annotation.source_circular_id or annotation.circular_id
        lines.append(f"circular_id={circular_id} label={annotation.label}")
        _append_quoted(lines, "  SRC: ", annotation.text, "       ")

    lines.extend(["", "VERIFY FAILURES"])
    lines.extend(verify_failures or ["(none)"])
    lines.extend(["", "TRANSLATION ERRORS"])
    if translation_errors:
        lines.extend(str(error) for error in translation_errors)
    else:
        lines.append("(none)")
    return lines


def _local_span(
    segment: CircularSegment,
    global_start: int,
    global_end: int,
) -> tuple[int, int]:
    return (
        global_start - segment.global_start,
        global_end - segment.global_start,
    )


def _local_verify(
    local_text: str,
    local_start: int,
    local_end: int,
    expected_text: str,
) -> bool:
    return (
        0 <= local_start < local_end <= len(local_text)
        and local_text[local_start:local_end] == expected_text
    )


def _append_context(
    lines: list[str],
    local_text: str,
    local_start: int,
    local_end: int,
) -> None:
    if not (0 <= local_start < local_end <= len(local_text)):
        lines.append("    CONTEXT: (span outside local canonical text)")
        return
    line_start = local_text.rfind("\n", 0, local_start) + 1
    last_span_character = local_end - 1
    line_end = local_text.find("\n", last_span_character)
    if line_end == -1:
        line_end = len(local_text)
    marked = (
        local_text[line_start:local_start]
        + "<<"
        + local_text[local_start:local_end]
        + ">>"
        + local_text[local_end:line_end]
    )
    _append_multiline(lines, "    CONTEXT: ", marked, "             ")


def _append_quoted(
    lines: list[str],
    prefix: str,
    value: str,
    continuation: str,
) -> None:
    parts = value.split("\n")
    if len(parts) == 1:
        lines.append(f"{prefix}'{value}'")
        return
    lines.append(f"{prefix}'{parts[0]}")
    lines.extend(f"{continuation}{part}" for part in parts[1:-1])
    lines.append(f"{continuation}{parts[-1]}'")


def _append_multiline(
    lines: list[str],
    prefix: str,
    value: str,
    continuation: str,
) -> None:
    parts = value.split("\n")
    lines.append(f"{prefix}{parts[0]}")
    lines.extend(f"{continuation}{part}" for part in parts[1:])


def _display(value: object) -> str:
    return "None" if value is None or value == "" else str(value)


if __name__ == "__main__":
    raise SystemExit(main())
