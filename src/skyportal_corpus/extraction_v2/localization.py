from __future__ import annotations

import re
from dataclasses import dataclass

from skyportal_corpus.canonical.document import CanonicalDocument
from skyportal_corpus.extraction_v2.annotations import EventEvidenceAnnotation


_RA_LABEL = r"(?:R\.?\s*A\.?)"
_DEC_LABEL = r"(?:Dec\.?|Decl\.?|Declination)"
_RA_SEXAGESIMAL = (
    r"[+\-]?\d{1,2}\s*(?::\s*\d{1,2}\s*(?::\s*\d{1,2}(?:\.\d+)?)?"
    r"|h\s*\d{1,2}\s*m\s*(?:\d{1,2}(?:\.\d+)?\s*s?)?)"
)
_DEC_SEXAGESIMAL = (
    r"[+\-]?\d{1,2}\s*(?::\s*\d{1,2}\s*(?::\s*\d{1,2}(?:\.\d+)?)?"
    r"|d\s*\d{1,2}\s*m\s*(?:\d{1,2}(?:\.\d+)?\s*s?)?)"
)

_COUNTERPART_CONTEXT_RE = re.compile(
    r"\b(counterpart|afterglow|optical transient|OT)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class _Rule:
    rule_id: str
    pattern: re.Pattern[str]


@dataclass(frozen=True)
class _Candidate:
    rule_id: str
    start: int
    end: int
    text: str
    value: str
    unit: str
    comment: str | None
    target: str


class LocalizationExtractor:
    extractor_id = "localization-v1"
    extractor_version = "0.1"

    _decimal_rule = _Rule(
        "localization.radec_decimal",
        re.compile(
            rf"\b{_RA_LABEL}\s*[=:]\s*"
            rf"(?P<ra>[+\-]?\d{{1,3}}(?:\.\d+)?)(?:\s*(?P<ra_unit>degrees|deg|d))?\s*"
            rf"(?:,|\s)\s*{_DEC_LABEL}\s*[=:]\s*"
            rf"(?P<dec>[+\-]?\d{{1,2}}(?:\.\d+)?)(?:\s*(?P<dec_unit>degrees|deg|d))?",
            re.IGNORECASE,
        ),
    )
    _sexagesimal_rule = _Rule(
        "localization.radec_sexagesimal",
        re.compile(
            rf"\b{_RA_LABEL}\s*[=:]\s*(?P<ra>{_RA_SEXAGESIMAL})\s*(?:,|\s)\s*"
            rf"{_DEC_LABEL}\s*[=:]\s*(?P<dec>{_DEC_SEXAGESIMAL})",
            re.IGNORECASE,
        ),
    )
    _error_radius_rule = _Rule(
        "localization.error_radius",
        re.compile(
            r"\b(?P<context>error radius|uncertainty|positional uncertainty|error circle)\b"
            r"[^.\n]{0,40}?(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>degrees|deg|arcmin|arcsec|')",
            re.IGNORECASE,
        ),
    )

    def extract(self, doc: CanonicalDocument) -> list[EventEvidenceAnnotation]:
        accepted_decimal_spans: list[tuple[int, int]] = []
        candidates: list[_Candidate] = []

        for match in self._decimal_rule.pattern.finditer(doc.rendered_text):
            accepted_decimal_spans.append((match.start(), match.end()))
            candidates.append(
                _Candidate(
                    rule_id=self._decimal_rule.rule_id,
                    start=match.start(),
                    end=match.end(),
                    text=doc.rendered_text[match.start() : match.end()],
                    value=_position_value(match),
                    unit=_position_unit(match),
                    comment=None,
                    target=_target_from_context(doc.rendered_text, match.start(), match.end()),
                )
            )

        for match in self._sexagesimal_rule.pattern.finditer(doc.rendered_text):
            # GCN Circulars often repeat the same point in decimal and sexagesimal form nearby.
            # If a sexagesimal pair is within +/-120 chars of an accepted decimal pair, keep only decimal.
            if _near_decimal_position(match.start(), match.end(), accepted_decimal_spans):
                continue
            candidates.append(
                _Candidate(
                    rule_id=self._sexagesimal_rule.rule_id,
                    start=match.start(),
                    end=match.end(),
                    text=doc.rendered_text[match.start() : match.end()],
                    value=_position_value(match),
                    unit="",
                    comment=None,
                    target=_target_from_context(doc.rendered_text, match.start(), match.end()),
                )
            )

        for match in self._error_radius_rule.pattern.finditer(doc.rendered_text):
            candidates.append(
                _Candidate(
                    rule_id=self._error_radius_rule.rule_id,
                    start=match.start(),
                    end=match.end(),
                    text=doc.rendered_text[match.start() : match.end()],
                    value=match.group("value"),
                    unit=_normalize_unit(match.group("unit")),
                    comment="positional uncertainty",
                    target=_target_from_context(doc.rendered_text, match.start(), match.end()),
                )
            )

        annotations = [
            EventEvidenceAnnotation(
                circular_id=doc.circular_id,
                text_sha256=doc.text_sha256,
                span_start=candidate.start,
                span_end=candidate.end,
                text=candidate.text,
                label="LOCALIZATION",
                target=candidate.target,
                certainty="confirmed",
                value=candidate.value,
                unit=candidate.unit,
                comment=candidate.comment,
                extractor_id=self.extractor_id,
                extractor_version=self.extractor_version,
                method="regex",
                rule_id=candidate.rule_id,
            )
            for candidate in sorted(candidates, key=lambda item: (item.start, item.end, item.rule_id))
        ]

        for annotation in annotations:
            if not annotation.verify(doc.rendered_text):
                raise ValueError(
                    f"Annotation failed offset verification: {annotation.rule_id} "
                    f"{annotation.span_start}-{annotation.span_end}"
                )
        return annotations


def _position_value(match: re.Match[str]) -> str:
    return f"RA={match.group('ra')}, Dec={match.group('dec')}"


def _position_unit(match: re.Match[str]) -> str:
    ra_unit = match.groupdict().get("ra_unit")
    dec_unit = match.groupdict().get("dec_unit")
    if _normalize_unit(ra_unit or "") == "deg" or _normalize_unit(dec_unit or "") == "deg":
        return "deg"
    return ""


def _normalize_unit(unit: str) -> str:
    normalized = unit.lower()
    if normalized in {"deg", "degrees", "d"}:
        return "deg"
    if normalized == "'":
        return "arcmin"
    return normalized


def _near_decimal_position(start: int, end: int, decimal_spans: list[tuple[int, int]]) -> bool:
    return any(start <= decimal_end + 120 and end >= decimal_start - 120 for decimal_start, decimal_end in decimal_spans)


def _target_from_context(rendered_text: str, start: int, end: int) -> str:
    window = rendered_text[max(0, start - 80) : min(len(rendered_text), end + 80)]
    if _COUNTERPART_CONTEXT_RE.search(window):
        return "counterpart"
    return "event"
