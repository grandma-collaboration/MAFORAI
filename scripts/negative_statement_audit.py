from __future__ import annotations

import sys
from collections import defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


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
    NEGATIVE_SIGNAL_RE,
    NegativeStatementExtractor,
    negative_statement_deferral_reason,
)


OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "gcn"
    / "sweep"
    / "negative_statement_audit.txt"
)
YEARS = (2023, 2024, 2025, 2026)
PER_YEAR = 4
MIN_SIGNALS = 2
ANCHORS = frozenset({42311, 35064, 33208})


def main() -> int:
    selected = select_audit_circulars(iter_real_circulars(limit=100000))
    report = render_audit(selected)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(report, encoding="utf-8")

    counts: dict[int, int] = defaultdict(int)
    for circular, _doc, _score in selected:
        counts[_circular_year(circular)] += 1
    print(f"Wrote negative-statement audit to {OUTPUT_PATH.relative_to(PROJECT_ROOT)}")
    print(f"Selected circulars: {len(selected)}")
    for year in YEARS:
        print(f"  {year}: {counts[year]}")
    return 0


def select_audit_circulars(
    circulars: Iterable[Mapping[str, Any]],
) -> list[tuple[dict[str, Any], CanonicalDocument, int]]:
    by_year: dict[int, list[tuple[dict[str, Any], CanonicalDocument, int]]] = defaultdict(list)
    anchors: dict[int, tuple[dict[str, Any], CanonicalDocument, int]] = {}
    for source in circulars:
        circular = dict(source)
        year = _circular_year(circular)
        if year not in YEARS:
            continue
        doc = _render(circular)
        score = len(NEGATIVE_SIGNAL_RE.findall(doc.rendered_text))
        if doc.circular_id in ANCHORS:
            anchors[doc.circular_id] = (circular, doc, score)
        if score >= MIN_SIGNALS:
            by_year[year].append((circular, doc, score))

    selected_by_id: dict[int, tuple[dict[str, Any], CanonicalDocument, int]] = {}
    for year in YEARS:
        ranked = sorted(
            by_year.get(year, []),
            key=lambda item: (-item[2], int(item[0]["circular_id"])),
        )
        for item in ranked[:PER_YEAR]:
            selected_by_id[item[1].circular_id] = item
    selected_by_id.update(anchors)
    return sorted(
        selected_by_id.values(),
        key=lambda item: (_circular_year(item[0]), item[1].circular_id),
    )


def render_audit(
    selected: list[tuple[dict[str, Any], CanonicalDocument, int]],
) -> str:
    extractor = NegativeStatementExtractor()
    lines = [
        "=" * 100,
        "NEGATIVE_STATEMENT DEEP AUDIT",
        f"Selection: up to {PER_YEAR} circulars with at least {MIN_SIGNALS} "
        "negative-signal hits per year",
        "=" * 100,
    ]
    for circular, doc, score in selected:
        annotations = extractor.extract(doc)
        lines.extend(_render_circular(circular, doc, score, annotations))
    return "\n".join(lines).rstrip() + "\n"


def _render_circular(
    circular: dict[str, Any],
    doc: CanonicalDocument,
    score: int,
    annotations: list[EventEvidenceAnnotation],
) -> list[str]:
    lines = [
        "",
        "=" * 100,
        f"CIRCULAR {doc.circular_id}"
        f"{' [ANCHOR]' if doc.circular_id in ANCHORS else ''} | {doc.subject}",
        f"year={_circular_year(circular)} | signal_matches={score} | "
        f"extracted={len(annotations)}",
        "=" * 100,
    ]
    if annotations:
        for annotation in annotations:
            lines.extend(
                [
                    f"  [{annotation.label}] certainty={annotation.certainty} "
                    f"review={annotation.needs_review} rule={annotation.rule_id}",
                    f"      SRC: {annotation.text!r}",
                    f"      verify: "
                    f"{'OK' if annotation.verify(doc.rendered_text) else 'FAIL'}",
                ]
            )
    else:
        lines.append("  (no NEGATIVE_STATEMENT annotations)")

    lines.extend(["", "  --- lines containing negative signal words ---"])
    lines.extend(_signal_lines(doc.rendered_text, annotations))
    lines.extend(["", f"  --- FULL TEXT ({len(doc.rendered_text)} chars) ---", doc.rendered_text])
    return lines


def _signal_lines(
    text: str,
    annotations: list[EventEvidenceAnnotation],
) -> list[str]:
    rendered: list[str] = []
    offset = 0
    for raw_line in text.splitlines(keepends=True):
        line = raw_line.rstrip("\r\n")
        line_matches = list(NEGATIVE_SIGNAL_RE.finditer(line))
        if line_matches:
            match_coverage = [
                any(
                    annotation.span_start < offset + match.end()
                    and offset + match.start() < annotation.span_end
                    for annotation in annotations
                )
                for match in line_matches
            ]
            covered = all(match_coverage)
            prefix = "OK          " if covered else ">> UNCOVERED"
            signals = ", ".join(repr(match.group(0)) for match in line_matches)
            reason = (
                ""
                if covered
                else f" {_uncovered_reason(text, offset, line_matches, match_coverage)}"
            )
            rendered.append(f"   {prefix}{reason} [{signals}]: {line}")
        offset += len(raw_line)
    return rendered or ["   (none)"]


def _uncovered_reason(
    text: str,
    line_offset: int,
    matches: list[Any],
    coverage: list[bool],
) -> str:
    deferrals = [
        negative_statement_deferral_reason(
            text,
            line_offset + match.start(),
            line_offset + match.end(),
        )
        for match, is_covered in zip(matches, coverage)
        if not is_covered
    ]
    if "LIGHTCURVE_EVOLUTION" in deferrals:
        return "(defer: LIGHTCURVE_EVOLUTION)"
    if "PHOTOMETRY" in deferrals:
        return "(defer: PHOTOMETRY)"
    return "(gap: review)"


def _render(circular: dict[str, Any]) -> CanonicalDocument:
    return render_canonical(
        circular_id=int(circular["circular_id"]),
        subject=str(circular.get("subject") or ""),
        body=str(circular.get("body") or ""),
        event_id=circular.get("event_id"),
        created_on=circular.get("created_on"),
        submitter=circular.get("submitter"),
    )


def _circular_year(circular: Mapping[str, Any]) -> int:
    explicit = circular.get("year")
    if explicit is not None and str(explicit).isdigit():
        return int(explicit)
    created_on = str(circular.get("created_on") or "")
    return int(created_on[:4]) if len(created_on) >= 4 and created_on[:4].isdigit() else 0


if __name__ == "__main__":
    raise SystemExit(main())
