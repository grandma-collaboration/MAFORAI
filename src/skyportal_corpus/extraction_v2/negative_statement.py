from __future__ import annotations

import re
from dataclasses import dataclass

from skyportal_corpus.canonical.document import CanonicalDocument
from skyportal_corpus.extraction_v2.annotations import EventEvidenceAnnotation


NEGATIVE_SIGNAL_RE = re.compile(
    r"\b(?:"
    r"not\s+detected|no\s+detection|no\s+evidence|not\s+associated|unrelated|"
    r"not\s+a\s+GRB|false\s+trigger|retraction|retracted|"
    r"no\s+(?:confirmed\s+)?"
    r"(?:(?:optical|X[- ]?ray|radio|NIR|UV|gamma[- ]?ray)\s+)?"
    r"counterpart(?:\s+candidates?)?|"
    r"rules\s+out|ruled\s+out|not\s+consistent\s+with|no\s+significant|"
    r"not\s+confirmed|cannot\s+confirm|no\s+signature|spurious|"
    r"not\s+(?:a\s+)?real|"
    r"disfavou?red|disfavou?rs|unlikely\s+to\s+be"
    r")\b",
    re.IGNORECASE,
)

_OBJECT_WORD = r"[^\s,:;.!?\n]+"
_OBJECT_STOP = (
    r"(?:because|based|given|although|however|but|and|while|which|that|"
    r"is|was|were|has|have|in|within|at|between|from|with|during|prior|down|"
    r"using|provided|reported|taken|over|after|before|since)"
)
_CLAUSE_OBJECT = (
    rf"{_OBJECT_WORD}"
    rf"(?:[ \t]+(?!{_OBJECT_STOP}\b){_OBJECT_WORD}){{0,7}}"
)
_COUNTERPART_OBJECT_WORD = r"[^\s,:;.!?()\n]+"
_COUNTERPART_CLAUSE_OBJECT = (
    rf"{_COUNTERPART_OBJECT_WORD}"
    rf"(?:[ \t]+(?!{_OBJECT_STOP}\b){_COUNTERPART_OBJECT_WORD}){{0,7}}"
)

_LIGHTCURVE_BEHAVIOR_RE = re.compile(
    r"\b(?:"
    r"fad(?:e|ed|es|ing)|"
    r"(?:re[- ]?)?brighten(?:ed|ing|s)?|"
    r"ris(?:e|en|es|ing)|"
    r"dimm(?:ed|ing|s)?|"
    r"variab(?:ility|le)|variation|varying|"
    r"decay(?:ed|ing|s)?|declin(?:e|ed|es|ing)|"
    r"evolution|evolv(?:e|ed|es|ing)|"
    r"flar(?:e|ed|es|ing)"
    r")\b",
    re.IGNORECASE,
)
_EXPLICIT_PHOTOMETRIC_BAND_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?:u|B|V|R|I|g|r|i|z|y|J|H|K|Kp|L|F\d{3,4}W|SDSS[- ]?[ugrizy])"
    r"\s*[- ]?(?:band|filter)\b"
)
_BARE_PHOTOMETRIC_BAND_RE = re.compile(
    r"(?:\b(?:in|through|using|with)\s+(?:the\s+)?"
    r"(?:u|B|V|R|I|g|r|i|z|y|J|H|K|Kp|L|F\d{3,4}W)"
    r"(?=\s|[,.;)]|$)|"
    r"(?<![A-Za-z0-9])"
    r"(?:u|B|V|R|I|g|r|i|z|y|J|H|K|Kp|L|F\d{3,4}W)"
    r"(?![A-Za-z0-9])(?=\s*[=<>]))"
)
_PHOTOMETRIC_MAGNITUDE_RE = re.compile(
    r"\b(?:"
    r"mag(?:nitude)?s?|limiting\s+magnitude|deeper\s+than|"
    r"(?:\d+(?:\.\d+)?[\s-]*sigma\s+)?(?:detection\s+limit|depth)|"
    r"AB\s+mag(?:nitude)?s?|Vega"
    r")\b|"
    r"\bm_[ugrizyUBVRIJHK]\b",
    re.IGNORECASE,
)
_PHOTOMETRIC_FLUX_RE = re.compile(
    r"\b(?:uJy|microJy|mJy|Jy)\b|[µμ]Jy",
    re.IGNORECASE,
)
_IMAGING_RE = re.compile(
    r"\bforced\s+photometry\b|"
    r"\b(?:our|archival|stacked|individual|difference)\s+images?\b|"
    r"\b(?:imaged|imaging)\b|"
    r"\bobserved\s+(?:the\s+)?field\b[^.!?]{0,160}"
    r"\b(?:did\s+not|have\s+not|has\s+not|failed\s+to)\s+detect(?:ed|ing)?\b",
    re.IGNORECASE,
)
_CATALOG_SENSITIVITY_RE = re.compile(
    r"\b(?:catalog|catalogue)\b[^.!?]{0,160}\bsensitiv(?:ity|ities)\b",
    re.IGNORECASE,
)
_NO_COUNTERPART_REVIEW_COMMENT = (
    "Counterpart absence is based on a catalog sensitivity; verify the "
    "catalog scope and completeness."
)
_SENTENCE_ABBREVIATION_RE = re.compile(
    r"\b(?:Circ|Dr|Mr|Mrs|Ms|Prof|Fig|Ref|No|e\.g|i\.e)\.$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class NegativeStatementCandidate:
    span_start: int
    span_end: int
    raw: str
    certainty: str
    rule_id: str
    priority: int
    needs_review: bool = False
    comment: str | None = None


@dataclass(frozen=True)
class _NegativeRule:
    rule_id: str
    certainty: str
    pattern: re.Pattern[str]
    priority: int


_RULES = (
    _NegativeRule(
        "negative_statement.retraction",
        "rejected",
        re.compile(
            r"\bretraction(?:[ \t]+of[ \t]+"
            r"(?:GCN(?:[ \t]+Circular)?[ \t]*#?[ \t]*\d+|"
            rf"{_CLAUSE_OBJECT}))?|\b(?:we[ \t]+)?retracted\b",
            re.IGNORECASE,
        ),
        0,
    ),
    _NegativeRule(
        "negative_statement.not_grb",
        "rejected",
        re.compile(r"\bnot[ \t]+(?:a[ \t]+)?GRB\b", re.IGNORECASE),
        0,
    ),
    _NegativeRule(
        "negative_statement.false_trigger",
        "rejected",
        re.compile(
            r"\b(?:GRB[ \t]+\d{6}[A-Z]?[ \t]+(?:is|was)[ \t]+)?"
            r"(?:a[ \t]+)?false[ \t]+trigger\b",
            re.IGNORECASE,
        ),
        0,
    ),
    _NegativeRule(
        "negative_statement.not_associated",
        "rejected",
        re.compile(
            rf"\bnot[ \t]+associated[ \t]+with[ \t]+{_CLAUSE_OBJECT}",
            re.IGNORECASE,
        ),
        1,
    ),
    _NegativeRule(
        "negative_statement.unrelated",
        "rejected",
        re.compile(
            rf"\bunrelated[ \t]+to[ \t]+{_CLAUSE_OBJECT}|"
            r"\b(?:is|are|was|were)[ \t]+unrelated\b"
            r"(?=[ \t]*(?:[.,;:!?]|$))",
            re.IGNORECASE,
        ),
        1,
    ),
    _NegativeRule(
        "negative_statement.unlikely",
        "rejected",
        re.compile(
            r"\bunlikely\s+to\s+be\s+"
            r"(?:(?:the|an?)\s+)?"
            r"(?:(?:optical|X[- ]?ray|radio|NIR|UV|gamma[- ]?ray)\s+)?"
            r"(?:"
            r"counterpart|afterglow|"
            r"associated(?:\s+with\s+" + _CLAUSE_OBJECT + r")?|"
            r"related\s+to\s+" + _CLAUSE_OBJECT +
            r")|"
            r"\bdisfavou?r(?:ed|s)"
            r"(?:\s+(?:the\s+)?"
            r"(?:association|connection|identification|classification))?",
            re.IGNORECASE,
        ),
        1,
    ),
    _NegativeRule(
        "negative_statement.rules_out",
        "rejected",
        re.compile(
            rf"\brules[ \t]+out[ \t]+{_CLAUSE_OBJECT}|"
            rf"(?<!cannot[ \t]be[ \t])(?<!not[ \t]be[ \t])"
            rf"\bruled[ \t]+out(?:[ \t]+{_CLAUSE_OBJECT})?",
            re.IGNORECASE,
        ),
        1,
    ),
    _NegativeRule(
        "negative_statement.identity_rejection",
        "rejected",
        re.compile(
            r"\bnot[ \t]+(?:the[ \t]+|an?[ \t]+)?(?:afterglow|counterpart)\b",
            re.IGNORECASE,
        ),
        1,
    ),
    _NegativeRule(
        "negative_statement.not_consistent",
        "rejected",
        re.compile(
            rf"\bnot[ \t]+consistent[ \t]+with[ \t]+{_CLAUSE_OBJECT}",
            re.IGNORECASE,
        ),
        1,
    ),
    _NegativeRule(
        "negative_statement.not_real",
        "rejected",
        re.compile(
            r"\bnot[ \t]+(?:a[ \t]+)?real"
            r"(?:[ \t]+(?:astrophysical[ \t]+)?"
            r"(?:source|event|signal|trigger|detection|counterpart))?\b",
            re.IGNORECASE,
        ),
        1,
    ),
    _NegativeRule(
        "negative_statement.spurious",
        "rejected",
        re.compile(
            r"\b(?:spurious[ \t]+(?:trigger|detection|signal|source|event)|"
            r"(?:trigger|detection|signal|source|event)[ \t]+"
            r"(?:is|was)[ \t]+spurious)\b",
            re.IGNORECASE,
        ),
        1,
    ),
    _NegativeRule(
        "negative_statement.cannot_confirm",
        "rejected",
        re.compile(
            r"\bcannot[ \t]+confirm[ \t]+(?:the[ \t]+)?"
            r"(?:association|classification|identification)\b",
            re.IGNORECASE,
        ),
        1,
    ),
    _NegativeRule(
        "negative_statement.no_counterpart",
        "confirmed",
        re.compile(
            r"\bno[ \t]+(?:confirmed[ \t]+)?"
            r"(?:(?:optical|X[- ]?ray|radio|NIR|near[- ]infrared|UV|"
            r"ultraviolet|gamma[- ]?ray)[ \t]+)?"
            r"counterpart(?:[ \t]+candidates?)?"
            rf"(?:[ \t]+consistent[ \t]+with[ \t]+{_COUNTERPART_CLAUSE_OBJECT})?"
            rf"(?:[ \t]+in[ \t]+{_COUNTERPART_CLAUSE_OBJECT})?"
            r"(?:[ \t]+(?:is|was)[ \t]+(?:found|identified))?",
            re.IGNORECASE,
        ),
        2,
    ),
    _NegativeRule(
        "negative_statement.no_evidence",
        "confirmed",
        re.compile(
            rf"\bno[ \t]+evidence[ \t]+(?:for|of)[ \t]+{_CLAUSE_OBJECT}",
            re.IGNORECASE,
        ),
        2,
    ),
    _NegativeRule(
        "negative_statement.no_signature",
        "confirmed",
        re.compile(
            rf"\bno[ \t]+(?:clear[ \t]+)?signature[ \t]+of[ \t]+{_CLAUSE_OBJECT}",
            re.IGNORECASE,
        ),
        2,
    ),
    _NegativeRule(
        "negative_statement.no_significant",
        "confirmed",
        re.compile(rf"\bno[ \t]+significant[ \t]+{_CLAUSE_OBJECT}", re.IGNORECASE),
        2,
    ),
    _NegativeRule(
        "negative_statement.absent_phenomenon",
        "confirmed",
        re.compile(
            r"\bno[ \t]+(?:clear[ \t]+)?(?:jet[ \t]+break|supernova|kilonova)\b|"
            r"\bno[ \t]+host(?:[ \t]+galaxy)?[ \t]+"
            r"(?:(?:was|is)[ \t]+)?detected\b",
            re.IGNORECASE,
        ),
        2,
    ),
    _NegativeRule(
        "negative_statement.not_confirmed",
        "confirmed",
        re.compile(r"\bnot[ \t]+confirmed\b", re.IGNORECASE),
        2,
    ),
)


class NegativeStatementExtractor:
    extractor_id = "negative-statement-v1"
    extractor_version = "0.1"

    def extract(self, doc: CanonicalDocument) -> list[EventEvidenceAnnotation]:
        annotations: list[EventEvidenceAnnotation] = []
        candidates = resolve_negative_statement_overlaps(
            find_negative_statement_candidates(doc.rendered_text)
        )
        for candidate in candidates:
            annotation = EventEvidenceAnnotation(
                circular_id=doc.circular_id,
                text_sha256=doc.text_sha256,
                span_start=candidate.span_start,
                span_end=candidate.span_end,
                text=candidate.raw,
                label="NEGATIVE_STATEMENT",
                target=None,
                certainty=candidate.certainty,
                value=None,
                unit=None,
                comment=candidate.comment,
                extractor_id=self.extractor_id,
                extractor_version=self.extractor_version,
                method="regex",
                rule_id=candidate.rule_id,
                confidence=0.6 if candidate.needs_review else 1.0,
                needs_review=candidate.needs_review,
            )
            if not annotation.verify(doc.rendered_text):
                raise ValueError(
                    "Negative-statement annotation failed offset verification: "
                    f"{annotation.span_start}-{annotation.span_end}"
                )
            annotations.append(annotation)
        return annotations


def find_negative_statement_candidates(text: str) -> list[NegativeStatementCandidate]:
    candidates: list[NegativeStatementCandidate] = []
    for rule in _RULES:
        for match in rule.pattern.finditer(text):
            span_start, span_end = _trim_span(text, match.start(), match.end())
            if span_start >= span_end:
                continue
            if negative_statement_deferral_reason(text, span_start, span_end) is not None:
                continue
            needs_review, comment = _candidate_review_fields(
                text,
                span_start,
                span_end,
                rule.rule_id,
            )
            candidates.append(
                NegativeStatementCandidate(
                    span_start=span_start,
                    span_end=span_end,
                    raw=text[span_start:span_end],
                    certainty=rule.certainty,
                    rule_id=rule.rule_id,
                    priority=rule.priority,
                    needs_review=needs_review,
                    comment=comment,
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


def resolve_negative_statement_overlaps(
    candidates: list[NegativeStatementCandidate],
) -> list[NegativeStatementCandidate]:
    selected: list[NegativeStatementCandidate] = []
    for candidate in sorted(
        candidates,
        key=lambda item: (
            item.priority,
            item.span_end - item.span_start,
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


def is_photometric_negative_context(text: str, start: int, end: int) -> bool:
    sentence_start, sentence_end = sentence_bounds(text, start, end)
    sentence = text[sentence_start:sentence_end]
    return bool(
        _EXPLICIT_PHOTOMETRIC_BAND_RE.search(sentence)
        or _BARE_PHOTOMETRIC_BAND_RE.search(sentence)
        or _PHOTOMETRIC_MAGNITUDE_RE.search(sentence)
        or _PHOTOMETRIC_FLUX_RE.search(sentence)
        or _IMAGING_RE.search(sentence)
    )


def is_lightcurve_behavior_negative(text: str, start: int, end: int) -> bool:
    sentence_start, sentence_end = sentence_bounds(text, start, end)
    clause_start = max(sentence_start, start)
    clause_end = min(sentence_end, max(end, start + 120))
    clause = text[clause_start:clause_end]
    boundary = re.search(r"[,;]|\b(?:and|but|while|although)\b", clause, re.IGNORECASE)
    if boundary is not None:
        clause = clause[: boundary.start()]
    return bool(_LIGHTCURVE_BEHAVIOR_RE.search(clause))


def negative_statement_deferral_reason(
    text: str,
    start: int,
    end: int,
) -> str | None:
    if is_lightcurve_behavior_negative(text, start, end):
        return "LIGHTCURVE_EVOLUTION"
    if is_photometric_negative_context(text, start, end):
        return "PHOTOMETRY"
    return None


def sentence_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    boundaries = [
        boundary
        for boundary in re.finditer(r"[.!?](?=\s|$)", text)
        if not _is_abbreviation_period(text, boundary)
    ]
    sentence_start = 0
    sentence_end = len(text)
    for boundary in boundaries:
        if boundary.end() <= start:
            sentence_start = boundary.end()
        elif boundary.start() >= end:
            sentence_end = boundary.end()
            break
    return sentence_start, sentence_end


def _is_abbreviation_period(text: str, boundary: re.Match[str]) -> bool:
    if boundary.group(0) != ".":
        return False
    prefix = text[max(0, boundary.start() - 12) : boundary.end()]
    if _SENTENCE_ABBREVIATION_RE.search(prefix):
        return True
    if not re.search(r"\bet\s+al\.$", prefix, re.IGNORECASE):
        return False
    suffix = text[boundary.end() :].lstrip()
    return bool(suffix and (suffix[0].isdigit() or suffix[0] in "(["))


def _candidate_review_fields(
    text: str,
    start: int,
    end: int,
    rule_id: str,
) -> tuple[bool, str | None]:
    if rule_id != "negative_statement.no_counterpart":
        return False, None
    sentence_start, sentence_end = sentence_bounds(text, start, end)
    sentence = text[sentence_start:sentence_end]
    if _CATALOG_SENSITIVITY_RE.search(sentence):
        return True, _NO_COUNTERPART_REVIEW_COMMENT
    return False, None


def _trim_span(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and (text[end - 1].isspace() or text[end - 1] in ",;:"):
        end -= 1
    return start, end


def _spans_overlap(
    first: NegativeStatementCandidate,
    second: NegativeStatementCandidate,
) -> bool:
    return first.span_start < second.span_end and second.span_start < first.span_end


__all__ = [
    "NEGATIVE_SIGNAL_RE",
    "NegativeStatementCandidate",
    "NegativeStatementExtractor",
    "find_negative_statement_candidates",
    "is_lightcurve_behavior_negative",
    "is_photometric_negative_context",
    "negative_statement_deferral_reason",
    "resolve_negative_statement_overlaps",
    "sentence_bounds",
]
