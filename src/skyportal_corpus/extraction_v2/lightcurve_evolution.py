from __future__ import annotations

import re
from dataclasses import dataclass

from skyportal_corpus.canonical.document import CanonicalDocument
from skyportal_corpus.extraction_v2.annotations import EventEvidenceAnnotation


LIGHTCURVE_SIGNAL_RE = re.compile(
    r"\b(?:"
    r"fad(?:e|es|ed|ing)|"
    r"declin(?:e|es|ed|ing)|dimming|steepening|decay(?:ed|ing|s)?|"
    r"ris(?:e|es|en|ing)|fast[- ]rising|"
    r"(?:re[- ]?)?brighten(?:s|ed|ing)?|increase\s+in\s+brightness|"
    r"flatten(?:s|ed|ing)?|plateau|leveled\s+off|"
    r"remain(?:s|ed)?\s+constant|roughly\s+constant|steady|"
    r"variable|variability|fluctuat(?:e|es|ed|ing)|flar(?:e|es|ed|ing)|"
    r"light\s*curve|evolution"
    r")\b",
    re.IGNORECASE,
)

LIGHTCURVE_NEGATIVE_SIGNAL_RE = re.compile(
    r"\b(?:"
    r"(?:there\s+is\s+)?no\s+evidence\s+(?:for|of)\s+"
    r"(?:rapid\s+|significant\s+)?"
    r"(?:"
    r"fading|decline|decay|dimming|steepening|"
    r"rising|brightening|rebrightening|re-brightening|"
    r"flattening|variability|variation|evolution|flaring"
    r")|"
    r"no\s+(?:significant\s+)?"
    r"(?:"
    r"fading|decline|decay|dimming|steepening|"
    r"rising|brightening|rebrightening|re-brightening|"
    r"flattening|variability|variation|evolution|flaring"
    r")|"
    r"(?:the\s+(?:source|afterglow|counterpart|transient)\s+)?"
    r"does\s+not\s+(?:fade|decline|dim|brighten|rise|vary|evolve)"
    r")\b",
    re.IGNORECASE,
)

_CLASSIFICATION_CAUSE_RE = re.compile(
    r"\b(?:"
    r"may\s+be\s+due\s+to|due\s+to|consistent\s+with|attributed\s+to|"
    r"indicative\s+of|suggests?|explained\s+by|caused\s+by|"
    r"interpreted\s+as"
    r")\b",
    re.IGNORECASE,
)
_LIGHTCURVE_CONTEXT_RE = re.compile(
    r"\b(?:"
    r"light\s*curve|source|afterglow|counterpart|transient|candidate|"
    r"flux|brightness|emission|count\s+rate"
    r")\b",
    re.IGNORECASE,
)
_GENERIC_CONTEXT_REQUIRED_RE = re.compile(
    r"^(?:"
    r"flat|steady|roughly\s+constant|remain(?:s|ed)?\s+constant|"
    r"variable|variability|fluctuat(?:e|es|ed|ing)|flar(?:e|es|ed|ing)"
    r")$",
    re.IGNORECASE,
)
_FADE_NEGATION_CUE_RE = re.compile(
    r"\b(?:"
    r"no\s+longer|not|no\s+more|stopped|ceased|isn't|is\s+not|"
    r"wasn't|does\s+not|did\s+not|never"
    r")\b",
    re.IGNORECASE,
)
_FADE_NEGATION_WINDOW = 15
_NORMALIZED_VALUES = {
    "lightcurve_evolution.fade_decline": "fading",
    "lightcurve_evolution.rise_brightening": "rebrightening",
    "lightcurve_evolution.flatten_plateau": "plateau",
    "lightcurve_evolution.variability": "variable",
    "lightcurve_evolution.negative": "no evolution",
}


@dataclass(frozen=True)
class LightcurveEvolutionCandidate:
    span_start: int
    span_end: int
    raw: str
    rule_id: str
    priority: int


@dataclass(frozen=True)
class _LightcurveRule:
    rule_id: str
    pattern: re.Pattern[str]
    priority: int


_RULES = (
    _LightcurveRule(
        "lightcurve_evolution.negative",
        LIGHTCURVE_NEGATIVE_SIGNAL_RE,
        0,
    ),
    _LightcurveRule(
        "lightcurve_evolution.fade_decline",
        re.compile(
            r"\b(?:"
            r"(?:the\s+(?:source|afterglow|counterpart|transient)\s+)?"
            r"continues?\s+to\s+fade|"
            r"rapid\s+decline|"
            r"fad(?:e|es|ed|ing)|declin(?:e|es|ed|ing)|"
            r"dimming|steepening|"
            r"(?:(?:rapid|steep|shallow|continued)\s+)?"
            r"decay(?:s|ed|ing)?"
            r")\b",
            re.IGNORECASE,
        ),
        1,
    ),
    _LightcurveRule(
        "lightcurve_evolution.rise_brightening",
        re.compile(
            r"\b(?:"
            r"(?:(?:optical|X[- ]?ray|radio|NIR|UV)\s+)?"
            r"(?:re[- ]?)?brighten(?:s|ed|ing)?|"
            r"fast[- ]rising|ris(?:e|es|en|ing)|"
            r"increase\s+in\s+brightness"
            r")\b",
            re.IGNORECASE,
        ),
        1,
    ),
    _LightcurveRule(
        "lightcurve_evolution.flatten_plateau",
        re.compile(
            r"\b(?:"
            r"flatten(?:s|ed|ing)"
            r"(?:\s+of\s+(?:the\s+)?light\s*curve)?|flat|"
            r"plateau(?:\s+phase)?|leveled\s+off|"
            r"remain(?:s|ed)?\s+constant|roughly\s+constant|steady"
            r")\b",
            re.IGNORECASE,
        ),
        1,
    ),
    _LightcurveRule(
        "lightcurve_evolution.variability",
        re.compile(
            r"\b(?:"
            r"variable|variability|fluctuat(?:e|es|ed|ing)|"
            r"flar(?:e|es|ed|ing)"
            r")\b",
            re.IGNORECASE,
        ),
        1,
    ),
)


class LightcurveEvolutionExtractor:
    extractor_id = "lightcurve-evolution-v1"
    extractor_version = "0.1"

    def extract(self, doc: CanonicalDocument) -> list[EventEvidenceAnnotation]:
        annotations: list[EventEvidenceAnnotation] = []
        candidates = resolve_lightcurve_evolution_overlaps(
            find_lightcurve_evolution_candidates(doc.rendered_text)
        )
        for candidate in candidates:
            annotation = EventEvidenceAnnotation(
                circular_id=doc.circular_id,
                text_sha256=doc.text_sha256,
                span_start=candidate.span_start,
                span_end=candidate.span_end,
                text=candidate.raw,
                label="LIGHTCURVE_EVOLUTION",
                target="counterpart",
                certainty="confirmed",
                value=_NORMALIZED_VALUES[candidate.rule_id],
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
                    "Light-curve annotation failed offset verification: "
                    f"{annotation.span_start}-{annotation.span_end}"
                )
            annotations.append(annotation)
        return annotations


def find_lightcurve_evolution_candidates(
    text: str,
) -> list[LightcurveEvolutionCandidate]:
    candidates: list[LightcurveEvolutionCandidate] = []
    for rule in _RULES:
        for match in rule.pattern.finditer(text):
            span_start, span_end = _trim_span(text, match.start(), match.end())
            if span_start >= span_end:
                continue
            if is_classification_interpretation_context(text, span_start, span_end):
                continue
            if (
                rule.rule_id == "lightcurve_evolution.fade_decline"
                and is_negated_fade_decline(text, span_start, span_end)
            ):
                continue
            raw = text[span_start:span_end]
            if _requires_lightcurve_context(raw) and not _has_lightcurve_context(
                text,
                span_start,
                span_end,
            ):
                continue
            candidates.append(
                LightcurveEvolutionCandidate(
                    span_start=span_start,
                    span_end=span_end,
                    raw=raw,
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


def resolve_lightcurve_evolution_overlaps(
    candidates: list[LightcurveEvolutionCandidate],
) -> list[LightcurveEvolutionCandidate]:
    selected: list[LightcurveEvolutionCandidate] = []
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


def is_classification_interpretation_context(
    text: str,
    start: int,
    end: int,
) -> bool:
    if LIGHTCURVE_NEGATIVE_SIGNAL_RE.fullmatch(text[start:end].strip()):
        return False
    clause_start, clause_end = clause_bounds(text, start, end)
    return bool(_CLASSIFICATION_CAUSE_RE.search(text[clause_start:clause_end]))


def clause_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    left = start
    while left > 0 and text[left - 1] not in ".,;:!?":
        left -= 1
    right = end
    while right < len(text) and text[right] not in ".,;:!?":
        right += 1
    return left, right


def is_negated_fade_decline(text: str, start: int, end: int) -> bool:
    clause_start, _clause_end = clause_bounds(text, start, end)
    context_start = max(clause_start, start - 40)
    prefix = text[context_start:start]
    for cue in _FADE_NEGATION_CUE_RE.finditer(prefix):
        distance = start - (context_start + cue.end())
        if distance <= _FADE_NEGATION_WINDOW:
            return True
    return False


def _requires_lightcurve_context(raw: str) -> bool:
    return bool(_GENERIC_CONTEXT_REQUIRED_RE.fullmatch(raw.strip()))


def _has_lightcurve_context(text: str, start: int, end: int) -> bool:
    clause_start, clause_end = clause_bounds(text, start, end)
    context_start = max(clause_start, start - 100)
    context_end = min(clause_end, end + 100)
    return bool(_LIGHTCURVE_CONTEXT_RE.search(text[context_start:context_end]))


def _trim_span(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and (text[end - 1].isspace() or text[end - 1] in ",;:"):
        end -= 1
    return start, end


def _spans_overlap(
    first: LightcurveEvolutionCandidate,
    second: LightcurveEvolutionCandidate,
) -> bool:
    return first.span_start < second.span_end and second.span_start < first.span_end


__all__ = [
    "LIGHTCURVE_NEGATIVE_SIGNAL_RE",
    "LIGHTCURVE_SIGNAL_RE",
    "LightcurveEvolutionCandidate",
    "LightcurveEvolutionExtractor",
    "clause_bounds",
    "find_lightcurve_evolution_candidates",
    "is_classification_interpretation_context",
    "is_negated_fade_decline",
    "resolve_lightcurve_evolution_overlaps",
]
