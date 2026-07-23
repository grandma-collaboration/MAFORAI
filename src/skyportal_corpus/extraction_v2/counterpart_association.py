from __future__ import annotations

import re
from dataclasses import dataclass

from skyportal_corpus.canonical.document import CanonicalDocument
from skyportal_corpus.extraction_v2.annotations import EventEvidenceAnnotation


COUNTERPART_SIGNAL_RE = re.compile(
    r"\b(?:counterpart|afterglow|associated\s+with|"
    r"identif(?:y|ies|ied|ication)|candidate)\b",
    re.IGNORECASE,
)

_MODALITY = (
    r"(?:optical|X[- ]?ray|radio|NIR|near[- ]infrared|UV|ultraviolet)"
)
_ROLE = r"(?:counterpart|afterglow)"
_QUALIFIER = r"(?:candidate|tentative|possible|likely|probable|potential)"
_EVENT_NAME = (
    r"(?:"
    r"GRB\s*\d{6}[A-Za-z]?|"
    r"EP(?:-WXT|-FXT)?\s*[A-Za-z0-9.]+|"
    r"(?:AT|SN)\s*2\d{3}[a-z]{2,4}|"
    r"ZTF\d{2}[a-z]{7}|"
    r"GOTO[A-Za-z0-9]+|"
    r"IceCube[- ]?\d{6}[A-Z]?"
    r")"
)
_ALIAS_LINK_RE = re.compile(
    rf"^\s*{_EVENT_NAME}\s*(?:/|=)\s*{_EVENT_NAME}\s*[.,;:]?\s*$",
    re.IGNORECASE,
)
_NEGATED_PREFIX_RE = re.compile(
    r"(?:"
    r"\bno\s+(?:(?:clear|credible|confirmed|significant|new|uncataloged)\s+)?|"
    r"\bwithout\s+(?:(?:detecting|finding|identifying)\s+)?"
    r"(?:(?:an?|the|any)\s+)?|"
    r"\bnot\s+(?:(?:an?|the|any)\s+)?|"
    r"\b(?:do|does|did|have|has|had|can|could|was|were|is|are)\s+not\b"
    r"(?:\s+[A-Za-z-]+){0,5}\s+|"
    r"\bcannot\b(?:\s+[A-Za-z-]+){0,5}\s+|"
    r"\bcan't\b(?:\s+[A-Za-z-]+){0,5}\s+|"
    r"\bunable\s+to\b(?:\s+[A-Za-z-]+){0,5}\s+|"
    r"\bfailed\s+to\b(?:\s+[A-Za-z-]+){0,5}\s+|"
    r"\bunlikely\s+to\s+be\s+(?:(?:an?|the)\s+)?"
    r")$",
    re.IGNORECASE,
)
_NEGATED_SUFFIX_RE = re.compile(
    r"^\s*(?:"
    r"(?:is|was|are|were|has|have)\s+not\b|"
    r"cannot\b|can't\b|is\s+unlikely\b"
    r")",
    re.IGNORECASE,
)
_CONFIRMED_RE = re.compile(
    r"\b(?:"
    r"spectroscopically\s+confirmed|confirmed|unambiguously|"
    r"firmly\s+associated|we\s+confirm|confirming"
    r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CounterpartAssociationCandidate:
    span_start: int
    span_end: int
    raw: str
    certainty: str
    rule_id: str
    priority: int


@dataclass(frozen=True)
class _CounterpartRule:
    rule_id: str
    pattern: re.Pattern[str]
    priority: int
    span_group: str = "span"


_RULES = (
    _CounterpartRule(
        "counterpart_association.identify",
        re.compile(
            rf"\bwe\s+"
            rf"(?:(?:clearly|marginally|tentatively|unambiguously)\s+)?"
            rf"(?:identify|identified|propose|proposed|report|reported|"
            rf"detect|detected|confirm|confirmed)\s+"
            rf"(?:one\s+|an?\s+|the\s+)?"
            rf"(?P<span>(?:{_QUALIFIER}\s+|"
            rf"spectroscopically\s+confirmed\s+|confirmed\s+)?"
            rf"(?:{_MODALITY}\s+)?{_ROLE}\b)",
            re.IGNORECASE,
        ),
        0,
    ),
    _CounterpartRule(
        "counterpart_association.identify_as",
        re.compile(
            rf"\b(?:we\s+)?"
            rf"(?:identify|identified|propose|proposed|report|reported|"
            rf"detect|detected|confirm|confirmed|confirming)\b"
            rf"[^.!?;\n]{{0,100}}?"
            rf"(?P<span>\bas\s+(?:the|an?)\s+"
            rf"(?:{_QUALIFIER}\s+|spectroscopically\s+confirmed\s+|"
            rf"confirmed\s+)?"
            rf"(?:{_MODALITY}\s+)?{_ROLE}\b)",
            re.IGNORECASE,
        ),
        0,
    ),
    _CounterpartRule(
        "counterpart_association.suggest",
        re.compile(
            rf"(?P<span>\b(?:we\s+)?strongly\s+suggest(?:s|ed)?\s+"
            rf"(?:that\s+)?this\s+is\s+(?:the|an?)\s+"
            rf"(?:{_MODALITY}\s+)?{_ROLE}\b)",
            re.IGNORECASE,
        ),
        0,
    ),
    _CounterpartRule(
        "counterpart_association.confirmed_role",
        re.compile(
            rf"(?P<span>\b(?:"
            rf"spectroscopically\s+confirmed|confirmed|"
            rf"unambiguously\s+(?:identified\s+as\s+)?"
            rf")\s+(?:{_MODALITY}\s+)?{_ROLE}\b)",
            re.IGNORECASE,
        ),
        0,
    ),
    _CounterpartRule(
        "counterpart_association.candidate_role",
        re.compile(
            rf"(?P<span>\b(?:"
            rf"{_QUALIFIER}\s+(?:{_MODALITY}\s+)?{_ROLE}|"
            rf"(?:{_MODALITY}\s+)?{_ROLE}\s+(?:candidate|candidates)"
            rf")\b)",
            re.IGNORECASE,
        ),
        1,
    ),
    _CounterpartRule(
        "counterpart_association.likely_role",
        re.compile(
            rf"(?P<span>\b(?:likely|possible|probable|potential)\s+"
            rf"(?:the\s+|an?\s+)?(?:{_MODALITY}\s+)?{_ROLE}\b)",
            re.IGNORECASE,
        ),
        1,
    ),
    _CounterpartRule(
        "counterpart_association.role_relation",
        re.compile(
            rf"(?P<span>\b(?:the\s+)?(?:{_MODALITY}\s+)?"
            rf"{_ROLE}\s+(?:of|to)\b)",
            re.IGNORECASE,
        ),
        2,
    ),
    _CounterpartRule(
        "counterpart_association.modality_counterpart",
        re.compile(
            rf"(?P<span>\b{_MODALITY}\s+counterpart\b)",
            re.IGNORECASE,
        ),
        3,
    ),
)


class CounterpartAssociationExtractor:
    extractor_id = "counterpart-association-v1"
    extractor_version = "0.1"

    def extract(self, doc: CanonicalDocument) -> list[EventEvidenceAnnotation]:
        annotations: list[EventEvidenceAnnotation] = []
        candidates = resolve_counterpart_association_overlaps(
            find_counterpart_association_candidates(doc.rendered_text)
        )
        for candidate in candidates:
            annotation = EventEvidenceAnnotation(
                circular_id=doc.circular_id,
                text_sha256=doc.text_sha256,
                span_start=candidate.span_start,
                span_end=candidate.span_end,
                text=candidate.raw,
                label="COUNTERPART_ASSOCIATION",
                target="counterpart",
                certainty=candidate.certainty,
                value=normalized_counterpart_value(candidate.raw),
                unit=None,
                comment=None,
                extractor_id=self.extractor_id,
                extractor_version=self.extractor_version,
                method="regex",
                rule_id=candidate.rule_id,
                confidence=1.0,
                needs_review=False,
            )
            if not annotation.verify(doc.rendered_text):
                raise ValueError(
                    "Counterpart-association annotation failed offset verification: "
                    f"{annotation.span_start}-{annotation.span_end}"
                )
            annotations.append(annotation)
        return annotations


def find_counterpart_association_candidates(
    text: str,
) -> list[CounterpartAssociationCandidate]:
    candidates: list[CounterpartAssociationCandidate] = []
    for rule in _RULES:
        for match in rule.pattern.finditer(text):
            span_start, span_end = match.span(rule.span_group)
            span_start, span_end = _trim_span(text, span_start, span_end)
            if span_start >= span_end:
                continue
            if counterpart_association_deferral_reason(
                text,
                span_start,
                span_end,
            ) is not None:
                continue
            raw = text[span_start:span_end]
            candidates.append(
                CounterpartAssociationCandidate(
                    span_start=span_start,
                    span_end=span_end,
                    raw=raw,
                    certainty=_certainty(match.group(0)),
                    rule_id=rule.rule_id,
                    priority=rule.priority,
                )
            )
    return sorted(
        candidates,
        key=lambda candidate: (
            candidate.span_start,
            candidate.priority,
            candidate.span_end,
            candidate.rule_id,
        ),
    )


def resolve_counterpart_association_overlaps(
    candidates: list[CounterpartAssociationCandidate],
) -> list[CounterpartAssociationCandidate]:
    selected: list[CounterpartAssociationCandidate] = []
    for candidate in sorted(
        candidates,
        key=lambda item: (
            item.priority,
            -(item.span_end - item.span_start),
            item.span_start,
            item.span_end,
            item.rule_id,
        ),
    ):
        if any(_spans_overlap(candidate, existing) for existing in selected):
            continue
        selected.append(candidate)
    return sorted(
        selected,
        key=lambda item: (item.span_start, item.span_end, item.rule_id),
    )


def is_negated_counterpart_context(text: str, start: int, end: int) -> bool:
    clause_start, clause_end = clause_bounds(text, start, end)
    prefix = text[clause_start:start]
    suffix = text[end:clause_end]
    if _is_not_telescope_subject(text, start, prefix):
        return False
    return bool(
        _NEGATED_PREFIX_RE.search(prefix)
        or _NEGATED_SUFFIX_RE.search(suffix)
    )


def is_event_identity_linking_context(text: str, start: int, end: int) -> bool:
    clause_start, clause_end = clause_bounds(text, start, end)
    return bool(_ALIAS_LINK_RE.fullmatch(text[clause_start:clause_end]))


def counterpart_association_deferral_reason(
    text: str,
    start: int,
    end: int,
) -> str | None:
    if is_negated_counterpart_context(text, start, end):
        return "NEGATIVE_STATEMENT"
    if is_event_identity_linking_context(text, start, end):
        return "EVENT_IDENTITY"
    return None


def clause_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    left = start
    while left > 0 and text[left - 1] not in ".,;:!?\n":
        left -= 1
    right = end
    while right < len(text) and text[right] not in ".,;:!?\n":
        right += 1
    return left, right


def _certainty(raw: str) -> str:
    return "confirmed" if _CONFIRMED_RE.search(raw) else "candidate"


def normalized_counterpart_value(raw: str) -> str:
    role = "afterglow" if re.search(r"\bafterglow\b", raw, re.IGNORECASE) else "counterpart"
    modality_patterns = (
        ("optical", r"\boptical\b"),
        ("X-ray", r"\bX[- ]?ray\b"),
        ("radio", r"\bradio\b"),
        ("NIR", r"\b(?:NIR|near[- ]infrared)\b"),
        ("UV", r"\b(?:UV|ultraviolet)\b"),
    )
    for modality, pattern in modality_patterns:
        if re.search(pattern, raw, re.IGNORECASE):
            return f"{modality} {role}"
    return role


def _is_not_telescope_subject(text: str, start: int, prefix: str) -> bool:
    line_start = text.rfind("\n", 0, start) + 1
    line_prefix = text[line_start:start]
    return (
        prefix.strip() == "NOT"
        and line_prefix.startswith("SUBJECT:")
        and re.search(r"\bNOT\s*$", line_prefix) is not None
    )


def _trim_span(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and (text[end - 1].isspace() or text[end - 1] in ",;:"):
        end -= 1
    return start, end


def _spans_overlap(
    first: CounterpartAssociationCandidate,
    second: CounterpartAssociationCandidate,
) -> bool:
    return first.span_start < second.span_end and second.span_start < first.span_end


__all__ = [
    "COUNTERPART_SIGNAL_RE",
    "CounterpartAssociationCandidate",
    "CounterpartAssociationExtractor",
    "clause_bounds",
    "counterpart_association_deferral_reason",
    "find_counterpart_association_candidates",
    "is_event_identity_linking_context",
    "is_negated_counterpart_context",
    "normalized_counterpart_value",
    "resolve_counterpart_association_overlaps",
]
