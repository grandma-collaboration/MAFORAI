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
from skyportal_corpus.extraction_v2.host_context import (  # noqa: E402
    HOST_CONTEXT_SIGNAL_RE,
    HostContextExtractor,
    is_bare_galaxy_redshift_context,
)


OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "gcn"
    / "sweep"
    / "host_context_audit.txt"
)
YEARS = (2023, 2024, 2025, 2026)
PER_YEAR = 4
MIN_SIGNALS = 2
SAMPLE_LIMIT_PER_RULE = 15
SAMPLE_RULE_ORDER = (
    "host_context.ambiguous",
    "host_context.candidate",
    "host_context.offset",
    "host_context.host",
    "host_context.context",
)


def main() -> int:
    selected = select_audit_circulars(iter_real_circulars(limit=100000))
    capture_samples = collect_capture_samples(
        iter_real_circulars(min_year=2023, limit=100000)
    )
    report = render_audit(selected, capture_samples)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(report, encoding="utf-8")

    counts: dict[int, int] = defaultdict(int)
    for circular, _doc, _score in selected:
        counts[_circular_year(circular)] += 1
    print(f"Wrote host-context audit to {OUTPUT_PATH.relative_to(PROJECT_ROOT)}")
    print(f"Selected circulars: {len(selected)}")
    for year in YEARS:
        print(f"  {year}: {counts[year]}")
    return 0


def select_audit_circulars(
    circulars: Iterable[Mapping[str, Any]],
) -> list[tuple[dict[str, Any], CanonicalDocument, int]]:
    by_year: dict[int, list[tuple[dict[str, Any], CanonicalDocument, int]]] = (
        defaultdict(list)
    )
    for source in circulars:
        circular = dict(source)
        year = _circular_year(circular)
        if year not in YEARS:
            continue
        doc = _render(circular)
        score = len(HOST_CONTEXT_SIGNAL_RE.findall(doc.rendered_text))
        if score >= MIN_SIGNALS:
            by_year[year].append((circular, doc, score))

    selected: list[tuple[dict[str, Any], CanonicalDocument, int]] = []
    for year in YEARS:
        ranked = sorted(
            by_year.get(year, []),
            key=lambda item: (-item[2], item[1].circular_id),
        )
        selected.extend(ranked[:PER_YEAR])
    return sorted(
        selected,
        key=lambda item: (
            _circular_year(item[0]),
            -item[2],
            item[1].circular_id,
        ),
    )


def collect_capture_samples(
    circulars: Iterable[Mapping[str, Any]],
) -> dict[str, list[EventEvidenceAnnotation]]:
    extractor = HostContextExtractor()
    samples: dict[str, list[EventEvidenceAnnotation]] = defaultdict(list)
    for circular in circulars:
        doc = _render(circular)
        for annotation in extractor.extract(doc):
            samples[str(annotation.rule_id or "unknown")].append(annotation)
    return {
        rule_id: sorted(
            annotations,
            key=lambda annotation: (
                -len(annotation.text),
                annotation.circular_id,
                annotation.span_start,
            ),
        )[:SAMPLE_LIMIT_PER_RULE]
        for rule_id, annotations in samples.items()
    }


def render_audit(
    selected: list[tuple[dict[str, Any], CanonicalDocument, int]],
    capture_samples: dict[str, list[EventEvidenceAnnotation]],
) -> str:
    extractor = HostContextExtractor()
    lines = [
        "=" * 100,
        "HOST_CONTEXT DEEP AUDIT",
        f"Selection: up to {PER_YEAR} circulars with at least {MIN_SIGNALS} "
        "host-context signal hits per year",
        "=" * 100,
    ]
    lines.extend(_render_capture_samples(capture_samples))
    for circular, doc, score in selected:
        annotations = extractor.extract(doc)
        lines.extend(_render_circular(circular, doc, score, annotations))
    return "\n".join(lines).rstrip() + "\n"


def _render_capture_samples(
    capture_samples: dict[str, list[EventEvidenceAnnotation]],
) -> list[str]:
    remaining_rules = sorted(set(capture_samples) - set(SAMPLE_RULE_ORDER))
    lines = ["", "CAPTURE SAMPLE BY RULE", "-" * 100]
    for rule_id in [*SAMPLE_RULE_ORDER, *remaining_rules]:
        samples = capture_samples.get(rule_id, [])
        lines.append(f"{rule_id} ({len(samples)} shown)")
        if not samples:
            lines.append("  (none)")
            continue
        for annotation in samples:
            lines.append(
                f"  - circular_id={annotation.circular_id} "
                f"target={annotation.target} certainty={annotation.certainty} "
                f"SRC={annotation.text!r}"
            )
    return lines


def _render_circular(
    circular: dict[str, Any],
    doc: CanonicalDocument,
    score: int,
    annotations: list[EventEvidenceAnnotation],
) -> list[str]:
    lines = [
        "",
        "=" * 100,
        f"CIRCULAR {doc.circular_id} | {doc.subject}",
        f"year={_circular_year(circular)} | signal_matches={score} | "
        f"extracted={len(annotations)}",
        "=" * 100,
    ]
    if annotations:
        for annotation in annotations:
            lines.extend(
                [
                    f"  [{annotation.label}] target={annotation.target} "
                    f"certainty={annotation.certainty} "
                    f"review={annotation.needs_review} rule={annotation.rule_id}",
                    f"      SRC: {annotation.text!r}",
                    f"      verify: "
                    f"{'OK' if annotation.verify(doc.rendered_text) else 'FAIL'}",
                ]
            )
    else:
        lines.append("  (no HOST_CONTEXT annotations)")

    lines.extend(["", "  --- lines containing host-context signals ---"])
    lines.extend(_signal_lines(doc.rendered_text, annotations))
    lines.extend(
        ["", f"  --- FULL TEXT ({len(doc.rendered_text)} chars) ---", doc.rendered_text]
    )
    return lines


def _signal_lines(
    text: str,
    annotations: list[EventEvidenceAnnotation],
) -> list[str]:
    rendered: list[str] = []
    offset = 0
    for raw_line in text.splitlines(keepends=True):
        line = raw_line.rstrip("\r\n")
        line_end = offset + len(raw_line)
        matches = list(HOST_CONTEXT_SIGNAL_RE.finditer(line))
        if matches:
            covered = any(
                annotation.span_start < line_end and offset < annotation.span_end
                for annotation in annotations
            )
            prefix = "OK          " if covered else ">> UNCOVERED"
            reason = "" if covered else f" {_uncovered_reason(text, offset, matches)}"
            signals = ", ".join(repr(match.group(0)) for match in matches)
            rendered.append(f"   {prefix}{reason} [{signals}]: {line}")
        offset = line_end
    return rendered or ["   (none)"]


def _uncovered_reason(text: str, line_offset: int, matches: list[Any]) -> str:
    if any(
        is_bare_galaxy_redshift_context(
            text,
            line_offset + match.start(),
            line_offset + match.end(),
        )
        for match in matches
    ):
        return "(defer: REDSHIFT_CONTEXT)"
    return "(gap: review)"


def _render(circular: Mapping[str, Any]) -> CanonicalDocument:
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
    return int(created_on[:4]) if created_on[:4].isdigit() else 0


if __name__ == "__main__":
    raise SystemExit(main())
