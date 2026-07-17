from __future__ import annotations

import re
from dataclasses import dataclass

from skyportal_corpus.canonical.document import CanonicalDocument
from skyportal_corpus.extraction_v2.annotations import EventEvidenceAnnotation


HOST_CONTEXT_SIGNAL_RE = re.compile(
    r"\b(?:"
    r"host|galax(?:y|ies)|offset|kpc|arcsec\s+separation|"
    r"nearby\s+galax(?:y|ies)"
    r")\b",
    re.IGNORECASE,
)

_NUMBER = r"~?\d+(?:\.\d+)?"
_ANGLE_UNIT = r"(?:arcsec(?:ond)?s?|arcmin(?:ute)?s?)"
_HOST_OR_GALAXY = r"(?:host(?:\s+galaxy)?|galaxy)"
_ESTABLISHED_HOST_RE = re.compile(
    r"\b(?:"
    r"confirmed\s+host(?:\s+galaxy)?|"
    r"the\s+host\s+galaxy\s+(?:is\s+)?(?:at|with)\s+"
    r"(?:(?:a|the)\s+)?"
    r"(?:(?:spectroscopic|photometric)\s+)?"
    r"(?:redshift(?:\s+of)?\s+)?z?\s*[=~]?"
    r")",
    re.IGNORECASE,
)
_HOST_CONTEXT_TERM_RE = re.compile(
    r"\b(?:host|galax(?:y|ies)|association|vicinity)\b",
    re.IGNORECASE,
)
_BARE_GALAXY_REDSHIFT_RE = re.compile(
    r"\bgalax(?:y|ies)\b[^.!?;\n]{0,100}"
    r"(?:\bredshift\b|\bz\s*[=~])",
    re.IGNORECASE,
)
_HOST_RELATION_RE = re.compile(
    r"\b(?:"
    r"host|offset|candidate|association|underlying|vicinity|nearby|"
    r"hosted|resides?|coincident"
    r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class HostContextCandidate:
    span_start: int
    span_end: int
    raw: str
    target: str
    certainty: str
    rule_id: str
    priority: int


@dataclass(frozen=True)
class _HostContextRule:
    rule_id: str
    pattern: re.Pattern[str]
    priority: int
    target: str = "host"
    requires_host_context: bool = False


_RULES = (
    _HostContextRule(
        "host_context.ambiguous",
        re.compile(
            r"(?P<span>\b(?:"
            r"host\s+association\s+(?:(?:is|remains|appears)\s+)?"
            r"(?:not\s+obvious|unclear|ambiguous|uncertain)|"
            r"no\s+obvious\s+host(?:\s+galaxy)?|"
            r"(?:absence|lack)\s+of\s+"
            r"(?:(?:an?|the)\s+)?host\s+galaxy"
            r")\b)",
            re.IGNORECASE,
        ),
        0,
    ),
    _HostContextRule(
        "host_context.candidate",
        re.compile(
            r"(?P<span>\b(?:"
            r"(?:putative|likely|possible|candidate)\s+"
            r"host(?:\s+galaxy)?|"
            r"host\s+candidate"
            r")\b)",
            re.IGNORECASE,
        ),
        1,
    ),
    _HostContextRule(
        "host_context.offset",
        re.compile(
            rf"(?P<span>\boffset\s+from\s+(?:the\s+)?{_HOST_OR_GALAXY}\b)",
            re.IGNORECASE,
        ),
        1,
    ),
    _HostContextRule(
        "host_context.offset",
        re.compile(
            rf"(?P<span>\boffset\s+of\s+{_NUMBER}\s*"
            rf"(?:{_ANGLE_UNIT}|kpc)"
            rf"(?:\s+(?:from|relative\s+to)\s+(?:the\s+)?"
            rf"{_HOST_OR_GALAXY})?)",
            re.IGNORECASE,
        ),
        2,
        requires_host_context=True,
    ),
    _HostContextRule(
        "host_context.offset",
        re.compile(
            rf"(?P<span>\b{_NUMBER}\s*kpc"
            rf"(?:\s+in\s+projection)?\s+from\s+(?:the\s+)?"
            rf"{_HOST_OR_GALAXY}\b)",
            re.IGNORECASE,
        ),
        1,
    ),
    _HostContextRule(
        "host_context.offset",
        re.compile(
            rf"(?P<span>\bseparation\s+of\s+{_NUMBER}\s*{_ANGLE_UNIT}"
            rf"\s+from\s+(?:the\s+)?galaxy\b)",
            re.IGNORECASE,
        ),
        1,
    ),
    _HostContextRule(
        "host_context.offset",
        re.compile(
            rf"(?P<span>\bin\s+the\s+vicinity\s+of\s+(?:a|the)\s+"
            rf"galaxy(?:\s+association)?"
            rf"(?:\s+with\s+{_NUMBER}\s*{_ANGLE_UNIT}\s+separation)?)",
            re.IGNORECASE,
        ),
        1,
    ),
    _HostContextRule(
        "host_context.host",
        re.compile(
            r"(?P<span>\b(?:"
            r"confirmed\s+host(?:\s+galaxy)?|"
            r"host\s+galaxy|host\s+association|underlying\s+galaxy|"
            r"association\s+with\s+(?:the|a)\s+galaxy|"
            r"(?:hosted\s+by|resides?\s+in|coincident\s+with)\s+"
            r"(?:(?:the|an?)\s+)?(?:[\w-]+\s+){0,4}galaxy"
            r")\b)",
            re.IGNORECASE,
        ),
        3,
    ),
    _HostContextRule(
        "host_context.context",
        re.compile(
            r"(?P<span>\bnearby\s+galax(?:y|ies)\b)",
            re.IGNORECASE,
        ),
        4,
        target="nearby_galaxy",
    ),
)


class HostContextExtractor:
    extractor_id = "host-context-v1"
    extractor_version = "0.1"

    def extract(self, doc: CanonicalDocument) -> list[EventEvidenceAnnotation]:
        annotations: list[EventEvidenceAnnotation] = []
        candidates = resolve_host_context_overlaps(
            find_host_context_candidates(doc.rendered_text)
        )
        for candidate in candidates:
            annotation = EventEvidenceAnnotation(
                circular_id=doc.circular_id,
                text_sha256=doc.text_sha256,
                span_start=candidate.span_start,
                span_end=candidate.span_end,
                text=candidate.raw,
                label="HOST_CONTEXT",
                target=candidate.target,
                certainty=candidate.certainty,
                value=None,
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
                    "Host-context annotation failed offset verification: "
                    f"{annotation.span_start}-{annotation.span_end}"
                )
            annotations.append(annotation)
        return annotations


def find_host_context_candidates(text: str) -> list[HostContextCandidate]:
    candidates: list[HostContextCandidate] = []
    for rule in _RULES:
        for match in rule.pattern.finditer(text):
            span_start, span_end = _trim_span(text, *match.span("span"))
            if span_start >= span_end:
                continue
            if rule.requires_host_context and not _has_host_context(
                text,
                span_start,
                span_end,
            ):
                continue
            candidates.append(
                HostContextCandidate(
                    span_start=span_start,
                    span_end=span_end,
                    raw=text[span_start:span_end],
                    target=rule.target,
                    certainty=_certainty(text, span_start, span_end),
                    rule_id=rule.rule_id,
                    priority=rule.priority,
                )
            )
    return sorted(
        candidates,
        key=lambda item: (
            item.span_start,
            item.priority,
            item.span_end,
            item.rule_id,
        ),
    )


def resolve_host_context_overlaps(
    candidates: list[HostContextCandidate],
) -> list[HostContextCandidate]:
    selected: list[HostContextCandidate] = []
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
        if any(_overlaps(candidate, existing) for existing in selected):
            continue
        selected.append(candidate)
    return sorted(
        selected,
        key=lambda item: (item.span_start, item.span_end, item.rule_id),
    )


def is_bare_galaxy_redshift_context(text: str, start: int, end: int) -> bool:
    sentence_start, sentence_end = sentence_bounds(text, start, end)
    sentence = text[sentence_start:sentence_end]
    return bool(
        _BARE_GALAXY_REDSHIFT_RE.search(sentence)
        and not _HOST_RELATION_RE.search(sentence)
    )


def sentence_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    left = start
    while left > 0 and text[left - 1] not in ".!?;\n":
        left -= 1
    right = end
    while right < len(text) and text[right] not in ".!?;\n":
        right += 1
    return left, right


def _certainty(text: str, start: int, end: int) -> str:
    context = text[max(0, start - 30) : min(len(text), end + 80)]
    return "confirmed" if _ESTABLISHED_HOST_RE.search(context) else "unclear"


def _has_host_context(text: str, start: int, end: int) -> bool:
    sentence_start, sentence_end = sentence_bounds(text, start, end)
    return bool(_HOST_CONTEXT_TERM_RE.search(text[sentence_start:sentence_end]))


def _trim_span(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and (text[end - 1].isspace() or text[end - 1] in ",;:"):
        end -= 1
    return start, end


def _overlaps(
    first: HostContextCandidate,
    second: HostContextCandidate,
) -> bool:
    return first.span_start < second.span_end and second.span_start < first.span_end


__all__ = [
    "HOST_CONTEXT_SIGNAL_RE",
    "HostContextCandidate",
    "HostContextExtractor",
    "find_host_context_candidates",
    "is_bare_galaxy_redshift_context",
    "resolve_host_context_overlaps",
    "sentence_bounds",
]
