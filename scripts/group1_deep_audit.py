from __future__ import annotations

import re
import sys
from collections import defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from skyportal_corpus.canonical.document import CanonicalDocument, iter_real_circulars, render_canonical  # noqa: E402
from skyportal_corpus.extraction_v2.annotations import EventEvidenceAnnotation  # noqa: E402
from skyportal_corpus.extraction_v2.duration import DurationExtractor  # noqa: E402
from skyportal_corpus.extraction_v2.high_energy import HighEnergyPropertyExtractor  # noqa: E402


OUTPUT_PATH = PROJECT_ROOT / "data" / "interim" / "gcn" / "sweep" / "group1_audit.txt"
YEARS = (2023, 2024, 2025, 2026)
PER_YEAR = 3
MIN_SIGNALS = 4
ANCHORS = frozenset({34511, 36553, 36584, 38104})

_SIGNAL_RE = re.compile(
    r"(?:"
    r"\bT90\b|\bT50\b|\bburst\s+duration\b|\bduration\b|\blasted\b|\blasting\b|"
    r"\bfluence\b|\bpower[- ]law\s+index\b|\bphoton\s+index\b|"
    r"\bspectral\s+index\b|\bBand\s+function\b|\balpha\s*=|\bbeta\s*(?:=|<)|"
    r"\bEp(?=\s|=|<)|\bEpeak\b|\bpeak\s+flux\b|\bpeak\s+energy\s+flux\b|"
    r"\bpeak\s+photon\s+flux\b|\bEiso\b|\bE_iso\b|\bisotropic\s+energy\b|"
    r"\bisotropic\s+equivalent\b|\bLiso\b|\bL_iso\b|\bcutoff\s+energy\b|"
    r"\bpeak\s+energy\b"
    r")",
    re.IGNORECASE,
)


def main() -> int:
    selected = select_audit_circulars(iter_real_circulars(limit=100000))
    selected_ids = {int(circular["circular_id"]) for circular, _, _ in selected}
    missing_anchors = ANCHORS - selected_ids
    if missing_anchors:
        raise ValueError(f"Missing audit anchors: {sorted(missing_anchors)}")
    report = render_audit(selected)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(report, encoding="utf-8")

    counts = defaultdict(int)
    for circular, _, _ in selected:
        counts[_circular_year(circular)] += 1
    print(f"Wrote deep audit to {OUTPUT_PATH.relative_to(PROJECT_ROOT)}")
    print(f"Selected circulars: {len(selected)}")
    print(f"Anchors: {sorted(ANCHORS)}")
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
        score = len(_SIGNAL_RE.findall(doc.rendered_text))
        circular_id = int(circular["circular_id"])
        if circular_id in ANCHORS:
            anchors[circular_id] = (circular, doc, score)
        if score >= MIN_SIGNALS:
            by_year[year].append((circular, doc, score))

    selected_by_id: dict[int, tuple[dict[str, Any], CanonicalDocument, int]] = {}
    for year in YEARS:
        ranked = sorted(
            by_year.get(year, []),
            key=lambda item: (-item[2], int(item[0]["circular_id"])),
        )
        for item in ranked[:PER_YEAR]:
            selected_by_id[int(item[0]["circular_id"])] = item
    selected_by_id.update(anchors)
    return sorted(
        selected_by_id.values(),
        key=lambda item: (
            _circular_year(item[0]),
            0 if int(item[0]["circular_id"]) in ANCHORS else 1,
            -item[2],
            int(item[0]["circular_id"]),
        ),
    )


def render_audit(
    selected: list[tuple[dict[str, Any], CanonicalDocument, int]],
) -> str:
    duration_extractor = DurationExtractor()
    high_energy_extractor = HighEnergyPropertyExtractor()
    lines = [
        "=" * 100,
        "GROUP 1 DEEP AUDIT: DURATION AND HIGH-ENERGY EXTRACTION",
        f"Selection: top {PER_YEAR} signal-rich circulars per year plus fixed anchors",
        "=" * 100,
    ]

    for circular, doc, score in selected:
        annotations = sorted(
            duration_extractor.extract(doc) + high_energy_extractor.extract(doc),
            key=lambda item: (item.span_start, item.span_end, item.rule_id),
        )
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
        f"CIRCULAR {doc.circular_id}{' [ANCHOR]' if doc.circular_id in ANCHORS else ''} "
        f"| {doc.subject}",
        f"year={_circular_year(circular)} | signal_matches={score} | "
        f"extracted={len(annotations)}",
        "=" * 100,
    ]
    for annotation in annotations:
        lines.extend(
            [
                f"  [{annotation.label}] value={annotation.value!r} unit={annotation.unit!r} "
                f"certainty={annotation.certainty} review={annotation.needs_review} "
                f"rule={annotation.rule_id}",
                f"      comment: {annotation.comment}",
                f"      SRC: {annotation.text!r}",
                f"      verify: {'OK' if annotation.verify(doc.rendered_text) else 'FAIL'}",
            ]
        )

    lines.extend(["", "  --- lines containing high-energy/duration signal words ---"])
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
        line_end = offset + len(raw_line)
        if _SIGNAL_RE.search(line):
            covered = any(
                annotation.span_start < line_end and offset < annotation.span_end
                for annotation in annotations
            )
            prefix = "OK          " if covered else ">> UNCOVERED"
            rendered.append(f"   {prefix}: {line}")
        offset = line_end
    return rendered or ["   (none)"]


def _render(circular: dict[str, Any]) -> CanonicalDocument:
    return render_canonical(
        circular_id=int(circular["circular_id"]),
        subject=str(circular.get("subject") or ""),
        body=str(circular.get("body") or ""),
        event_id=circular.get("event_id"),
        created_on=circular.get("created_on"),
        submitter=circular.get("submitter"),
    )


def _circular_year(circular: dict[str, Any]) -> int:
    explicit = circular.get("year")
    if explicit is not None and str(explicit).isdigit():
        return int(explicit)
    created_on = str(circular.get("created_on") or "")
    return int(created_on[:4]) if len(created_on) >= 4 and created_on[:4].isdigit() else 0


if __name__ == "__main__":
    raise SystemExit(main())
