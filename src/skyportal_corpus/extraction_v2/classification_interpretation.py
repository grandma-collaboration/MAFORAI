from __future__ import annotations

import re
from dataclasses import dataclass

from skyportal_corpus.canonical.document import CanonicalDocument
from skyportal_corpus.extraction_v2.annotations import EventEvidenceAnnotation


CLASSIFICATION_SIGNAL_RE = re.compile(
    r"\b(?:"
    r"(?:ultra[- ]long|long(?:\s+soft)?|short(?:\s+hard)?)\s+GRB|"
    r"(?:long|short)[- ]duration\s+GRB|(?:long|short)\s+burst|"
    r"Type\s+(?:I|II)\b|"
    r"supernova|kilonova|jet|shock|magnetar|collapsar|merger|"
    r"classified|identified|interpreted|interpretation|"
    r"consistent\s+with|due\s+to|explained\s+by|TDE|"
    r"tidal\s+disruption|blazar|AGN\s+flare"
    r")\b",
    re.IGNORECASE,
)

_GRB_CLASS = (
    r"(?:"
    r"short\s+GRB\s+with\s+extended\s+emission|"
    r"(?:ultra[- ]long|long|short)\s+GRB|"
    r"Type\s+(?:I|II)\s+GRBs?"
    r")"
)
_SUPERNOVA_CLASS = (
    r"(?:"
    r"(?:Type\s+(?:Ia|Ib|Ic|II|IIb|IIn)\s+)?"
    r"supernova(?:[- ]like)?"
    r"(?:\s+(?:component|origin|scenario|interpretation|signature))?"
    r")"
)
_KILONOVA_CLASS = (
    r"kilonova(?:[- ]like)?"
    r"(?:\s+(?:component|origin|scenario|interpretation|signature|spectrum))?"
)
_PHYSICAL_PHENOMENON = (
    r"(?:"
    rf"{_GRB_CLASS}|"
    rf"{_SUPERNOVA_CLASS}|"
    rf"{_KILONOVA_CLASS}|"
    r"TDE|tidal\s+disruption\s+event|"
    r"magnetar(?:\s+giant\s+flare)?|"
    r"collapsar|"
    r"(?:reverse|forward|external|internal|refreshed)\s+shock|"
    r"shock\s+breakout|"
    r"jet\s+break|"
    r"(?:late\s+|off[- ]axis\s+)?jet\s+activity|"
    r"energy\s+(?:injection|re[- ]injection)|"
    r"central\s+engine\s+activity|"
    r"(?:nearby\s+|compact[- ]object\s+|neutron[- ]star\s+)?merger|"
    r"synchrotron(?:\s+emission)?"
    r")"
)
_OBJECT_PREFIX = (
    r"(?:"
    r"the\s+presence\s+of\s+(?:(?:an?|the)\s+)?|"
    r"(?:(?:an?|the)\s+)?"
    r"(?:(?:possible|likely|probable|candidate|potential)\s+)?"
    r")"
)
_PHYSICAL_OBJECT = rf"{_OBJECT_PREFIX}{_PHYSICAL_PHENOMENON}"
_PHYSICAL_OBJECT_LIST = (
    rf"{_PHYSICAL_OBJECT}"
    rf"(?:\s+(?:or|and)\s+(?:to\s+)?{_PHYSICAL_OBJECT})?"
)
_CAUSE_CONNECTOR = (
    r"(?:"
    r"due\s+to|"
    r"attributed\s+to|"
    r"interpreted\s+as|"
    r"indicative\s+of|"
    r"consistent\s+with|"
    r"explained\s+by|"
    r"caused\s+by"
    r")"
)
_CAUSE_LEAD = (
    r"(?:(?:may|might|could|can)\s+be\s+|"
    r"(?:appears?|seems?)\s+(?:to\s+be\s+)?|"
    r"(?:is|was|are|were)\s+)?"
)
_CAUSE_SUBJECT = (
    r"(?:this|the|such)\s+"
    r"(?:rebrightening|brightening|flattening|plateau|decline|decay|"
    r"feature|emission|excess|signal|activity|behavior|behaviour|"
    r"event|burst|trigger|transient)"
)

PHYSICAL_CAUSE_RE = re.compile(
    rf"\b{_CAUSE_LEAD}{_CAUSE_CONNECTOR}\s+{_PHYSICAL_OBJECT_LIST}",
    re.IGNORECASE,
)

_FIRM_MARKER_RE = re.compile(
    r"\b(?:"
    r"spectroscopically\s+confirmed\s+as|"
    r"spectroscopically\s+classified\s+as|"
    r"classified\s+as|"
    r"confirmed\s+as|"
    r"firmly\s+established\s+as|"
    r"(?:spectroscopically\s+)?identified\s+as"
    r")\b",
    re.IGNORECASE,
)
_NEGATED_CLAIM_PREFIX_RE = re.compile(
    r"\b(?:not|never|unlikely)\s+(?:to\s+be\s+)?$",
    re.IGNORECASE,
)
_OBSERVED_EVOLUTION_RE = re.compile(
    r"\b(?:"
    r"light\s*curve\s+(?:shows?|exhibits?|has)|"
    r"rebrighten(?:ing|ed)?|brighten(?:ing|ed)?|"
    r"fad(?:e|es|ed|ing)|declin(?:e|es|ed|ing)|"
    r"flatten(?:ing|ed)?|plateau|rising|dimming"
    r")\b",
    re.IGNORECASE,
)
_GRB_EVENT_NAME = r"\d{6}[A-Za-z]?"
_GRB_CLASS_TERM = (
    r"(?:"
    r"(?:long|short)[- ]duration\s+GRB|"
    r"ultra[- ]long\s+GRB|"
    r"long\s+soft\s+GRB|"
    r"short\s+hard\s+GRB|"
    r"long\s+GRB|"
    r"short\s+GRB"
    r")"
)
_BURST_CLASS_TERM = r"(?:long|short)\s+burst"
_GRB_HEDGE_RE = re.compile(
    r"\b(?:"
    r"likely|possible|probable|tentative(?:ly)?|apparently|"
    r"could\s+be|may\s+be|might\s+be|"
    r"typical\b[^.!?;\n]{0,100}\bof"
    r")\b",
    re.IGNORECASE,
)
_SN_SUBTYPE = (
    r"(?:Ia|Ib|Ic(?:-BL)?|II(?:b|n|P|L)?|IIn|Ic-BL)"
)
_INTERPRETATION_SUPERNOVA = (
    r"(?:"
    rf"(?:very\s+young|young|broad[- ]lined|Type\s+{_SN_SUBTYPE})\s+"
    r"supernovae?|"
    rf"supernovae?(?:\s+(?:Type\s+)?{_SN_SUBTYPE})?|"
    rf"SNe?(?:\s+{_SN_SUBTYPE})?"
    r")"
)
_INTERPRETATION_CLASS = (
    r"(?:"
    rf"{_INTERPRETATION_SUPERNOVA}|"
    r"kilonovae?|"
    r"TDE|"
    r"tidal\s+disruption(?:\s+(?:event|flare))?|"
    r"GRB\s+afterglow|"
    r"magnetar(?:\s+giant\s+flare)?|"
    r"compact\s+binary\s+merger|"
    r"blazar(?:\s+flare)?|"
    r"AGN\s+flare|"
    r"shock\s+breakout(?:\s+(?:signature|scenario|emission))?|"
    r"shock\s+cooling|"
    r"(?:reverse|forward)\s+shock|"
    r"jet\s+break|"
    r"collapsar"
    r")"
)
_INTERPRETATION_OBJECT = (
    r"(?:(?:an?|the)\s+)?"
    r"(?:(?:possible|likely|probable|candidate|potential)\s+)?"
    rf"{_INTERPRETATION_CLASS}"
)
_SUGGEST_SUBJECT = r"[^.!?;\n]{1,100}?"
_CLASS_LIKE = (
    r"(?:"
    r"(?:supernova|SN|kilonova|TDE|GRB[- ]afterglow)[- ]like|"
    r"(?:AT\d{4}[a-z]{3,5}|SN\s*\d{4}[A-Za-z]+)[- ]like"
    r"(?:\s+(?:supernovae?|kilonova))?"
    r")"
)
_REJECTED_PREFIX_RE = re.compile(
    r"(?:"
    r"\bruled\s+out\s+as\s+|"
    r"\brules\s+out\s+|"
    r"\bno\s+(?:evidence\s+(?:for|of)\s+)?|"
    r"\bnot\s+(?:(?:an?|the)\s+)?|"
    r"\bunlikely\s+to\s+be\s+|"
    r"\bcannot\s+be\s+|"
    r"\bcannot\s+(?:confirm|establish)\s+"
    r"(?:(?:the\s+)?presence\s+of\s+)?|"
    r"\bwithout\s+(?:an?\s+|the\s+)?|"
    r"\bdisfavou?red\s+as\s+"
    r")$",
    re.IGNORECASE,
)
_RETRACTION_CONTEXT_RE = re.compile(
    r"\b(?:"
    r"is\s+in\s+fact\s+not|"
    r"was\s+in\s+fact\s+not|"
    r"not\s+(?:an?\s+)?GRB|"
    r"retraction|retracted"
    r")\b",
    re.IGNORECASE,
)
_CALL_FOR_CLASSIFICATION_RE = re.compile(
    r"\b(?:"
    r"explore|determine|establish|clarify|investigate"
    r")\s+(?:the\s+)?nature\s+of\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ClassificationInterpretationCandidate:
    span_start: int
    span_end: int
    raw: str
    certainty: str
    rule_id: str
    priority: int


@dataclass(frozen=True)
class _ClassificationRule:
    rule_id: str
    pattern: re.Pattern[str]
    priority: int
    span_group: str = "span"


_RULES = (
    _ClassificationRule(
        "classification_interpretation.firm_classification",
        re.compile(
            rf"(?P<span>\b(?:"
            rf"spectroscopically\s+confirmed\s+as|"
            rf"spectroscopically\s+classified\s+as|"
            rf"classified\s+as|"
            rf"confirmed\s+as|"
            rf"firmly\s+established\s+as"
            rf")\s+{_PHYSICAL_OBJECT})",
            re.IGNORECASE,
        ),
        0,
    ),
    _ClassificationRule(
        "classification_interpretation.physical_cause",
        re.compile(
            rf"(?P<span>\b{_CAUSE_SUBJECT}\s+"
            rf"{_CAUSE_LEAD}{_CAUSE_CONNECTOR}\s+"
            rf"{_PHYSICAL_OBJECT_LIST})",
            re.IGNORECASE,
        ),
        0,
    ),
    _ClassificationRule(
        "classification_interpretation.physical_cause",
        PHYSICAL_CAUSE_RE,
        1,
        span_group="span",
    ),
    _ClassificationRule(
        "classification_interpretation.qualified_class",
        re.compile(
            rf"(?P<span>\b(?:likely|possible|probable|potential)\s+"
            rf"(?:an?\s+)?{_PHYSICAL_PHENOMENON})",
            re.IGNORECASE,
        ),
        1,
    ),
    _ClassificationRule(
        "classification_interpretation.type_grb",
        re.compile(
            r"(?P<span>\bType\s+(?:I|II)\s+GRBs?\b)",
            re.IGNORECASE,
        ),
        1,
    ),
    _ClassificationRule(
        "classification_interpretation.extended_emission",
        re.compile(
            r"(?P<span>\bshort\s+GRB\s+with\s+extended\s+emission\b)",
            re.IGNORECASE,
        ),
        1,
    ),
    _ClassificationRule(
        "classification_interpretation.claim",
        re.compile(
            rf"\b(?:this|the)\s+(?:event|burst|source|trigger|transient)\s+"
            rf"(?:is|was|appears\s+to\s+be|seems\s+to\s+be)\s+"
            rf"{_OBJECT_PREFIX}(?P<span>{_PHYSICAL_PHENOMENON})",
            re.IGNORECASE,
        ),
        2,
    ),
    _ClassificationRule(
        "classification_interpretation.this_is",
        re.compile(
            rf"\bthis\s+is\s+{_OBJECT_PREFIX}"
            rf"(?P<span>{_PHYSICAL_PHENOMENON})",
            re.IGNORECASE,
        ),
        2,
    ),
    _ClassificationRule(
        "classification_interpretation.inferred_phenomenon",
        re.compile(
            rf"\b(?:we\s+(?:identify|infer|find|favor)|"
            rf"the\s+(?:data|spectrum|observations)\s+"
            rf"(?:show|suggest|indicate))\s+"
            rf"{_OBJECT_PREFIX}(?P<span>{_PHYSICAL_PHENOMENON})",
            re.IGNORECASE,
        ),
        2,
    ),
    _ClassificationRule(
        "classification_interpretation.interpretation",
        re.compile(
            rf"(?P<span>\b(?:we\s+)?(?:suggest|propose)\s+"
            rf"(?:that\s+)?{_SUGGEST_SUBJECT}\s+"
            rf"(?:is|could\s+be|may\s+be|might\s+be|"
            rf"appears?\s+to\s+be|seems?\s+to\s+be)\s+"
            rf"{_INTERPRETATION_OBJECT})",
            re.IGNORECASE,
        ),
        3,
    ),
    _ClassificationRule(
        "classification_interpretation.interpretation",
        re.compile(
            rf"(?P<span>\b(?:"
            rf"(?:spectroscopically\s+)?identified\s+as|"
            rf"interpret(?:ed)?\s+as"
            rf")\s+{_INTERPRETATION_OBJECT})",
            re.IGNORECASE,
        ),
        3,
    ),
    _ClassificationRule(
        "classification_interpretation.interpretation",
        re.compile(
            rf"(?P<span>\binterpret(?:ation|aiton)\s+of\s+"
            rf"[^.!?;\n]{{1,100}}?\s+as\s+{_INTERPRETATION_OBJECT})",
            re.IGNORECASE,
        ),
        3,
    ),
    _ClassificationRule(
        "classification_interpretation.interpretation",
        re.compile(
            rf"(?P<span>\b(?:make|makes|making)\s+"
            rf"{_INTERPRETATION_OBJECT}\s+the\s+most\s+likely\s+"
            rf"interpretation)",
            re.IGNORECASE,
        ),
        3,
    ),
    _ClassificationRule(
        "classification_interpretation.interpretation",
        re.compile(
            rf"(?P<span>\b{_INTERPRETATION_OBJECT}\s+"
            rf"(?:is\s+)?the\s+most\s+likely\s+interpretation)",
            re.IGNORECASE,
        ),
        3,
    ),
    _ClassificationRule(
        "classification_interpretation.interpretation",
        re.compile(
            rf"(?P<span>\bthe\s+most\s+likely\s+interpretation"
            rf"[^.!?;\n]{{0,40}}?(?:is|would\s+be|:)\s+"
            rf"{_INTERPRETATION_OBJECT})",
            re.IGNORECASE,
        ),
        3,
    ),
    _ClassificationRule(
        "classification_interpretation.interpretation",
        re.compile(
            rf"(?P<span>\b(?:is|are|was|were|appears?|seems?)?\s*"
            rf"consistent\s+with\s+(?:those\s+of\s+)?"
            rf"{_INTERPRETATION_OBJECT})",
            re.IGNORECASE,
        ),
        3,
    ),
    _ClassificationRule(
        "classification_interpretation.interpretation",
        re.compile(
            rf"(?P<span>\b(?:"
            rf"(?:could|may|might|can)\s+be|"
            rf"(?:is|are|was|were)"
            rf")\s+explained\s+by\s+{_INTERPRETATION_OBJECT}"
            rf"(?:\s+and\s+(?:a\s+)?rise\s+from\s+"
            rf"(?:(?:an?|the)\s+)?supernovae?)?)",
            re.IGNORECASE,
        ),
        3,
    ),
    _ClassificationRule(
        "classification_interpretation.interpretation",
        re.compile(
            rf"\b(?:similar\s+to\s+(?:that\s+of\s+)?(?:an?\s+)?)"
            rf"(?P<span>{_CLASS_LIKE})",
            re.IGNORECASE,
        ),
        3,
    ),
    _ClassificationRule(
        "classification_interpretation.interpretation",
        re.compile(
            rf"(?P<span>\b(?:supernova|SN|kilonova|TDE|"
            rf"GRB[- ]afterglow)[- ]like\b)",
            re.IGNORECASE,
        ),
        4,
    ),
    _ClassificationRule(
        "classification_interpretation.interpretation",
        re.compile(
            rf"(?P<span>\b(?:"
            rf"shock\s+breakout(?:\s+(?:signature|scenario|emission))?|"
            rf"shock\s+cooling|"
            rf"(?:reverse|forward)\s+shock|"
            rf"jet\s+break|"
            rf"magnetar\s+giant\s+flare|"
            rf"collapsar"
            rf")\b)",
            re.IGNORECASE,
        ),
        4,
    ),
    _ClassificationRule(
        "classification_interpretation.grb_class",
        re.compile(
            rf"(?P<span>\b{_GRB_CLASS_TERM}\s+{_GRB_EVENT_NAME}\b)",
            re.IGNORECASE,
        ),
        3,
    ),
    _ClassificationRule(
        "classification_interpretation.grb_class",
        re.compile(
            rf"(?P<span>\b(?:ultra[- ]long\s+GRB|"
            rf"long\s+soft\s+GRB|short\s+hard\s+GRB)\b)",
            re.IGNORECASE,
        ),
        3,
    ),
    _ClassificationRule(
        "classification_interpretation.grb_class",
        re.compile(
            rf"\b(?:this|the)\s+(?:event|burst|trigger|source)\s+"
            rf"(?:is|was|appears?\s+to\s+be|seems?\s+to\s+be)\s+"
            rf"(?:an?\s+)?(?P<span>{_GRB_CLASS_TERM}|"
            rf"{_BURST_CLASS_TERM})\b",
            re.IGNORECASE,
        ),
        3,
    ),
    _ClassificationRule(
        "classification_interpretation.grb_class",
        re.compile(
            rf"\btypical\b[^.!?;\n]{{0,100}}\bof\s+(?:an?\s+)?"
            rf"(?P<span>{_GRB_CLASS_TERM}|{_BURST_CLASS_TERM})\b",
            re.IGNORECASE,
        ),
        3,
    ),
    _ClassificationRule(
        "classification_interpretation.grb_class",
        re.compile(
            rf"\b(?:likely|possible|probable|tentative(?:ly)?)\s+"
            rf"(?:an?\s+)?(?P<span>GRB|{_GRB_CLASS_TERM}|"
            rf"{_BURST_CLASS_TERM})\b",
            re.IGNORECASE,
        ),
        3,
    ),
)


class ClassificationInterpretationExtractor:
    extractor_id = "classification-interpretation-v1"
    extractor_version = "0.1"

    def extract(self, doc: CanonicalDocument) -> list[EventEvidenceAnnotation]:
        annotations: list[EventEvidenceAnnotation] = []
        candidates = resolve_classification_interpretation_overlaps(
            find_classification_interpretation_candidates(doc.rendered_text)
        )
        for candidate in candidates:
            annotation = EventEvidenceAnnotation(
                circular_id=doc.circular_id,
                text_sha256=doc.text_sha256,
                span_start=candidate.span_start,
                span_end=candidate.span_end,
                text=candidate.raw,
                label="CLASSIFICATION_INTERPRETATION",
                target="event",
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
                    "Classification-interpretation annotation failed offset "
                    f"verification: {annotation.span_start}-{annotation.span_end}"
                )
            annotations.append(annotation)
        return annotations


def find_classification_interpretation_candidates(
    text: str,
) -> list[ClassificationInterpretationCandidate]:
    candidates: list[ClassificationInterpretationCandidate] = []
    for rule in _RULES:
        for match in rule.pattern.finditer(text):
            if rule.pattern is PHYSICAL_CAUSE_RE:
                span_start, span_end = match.span(0)
            else:
                span_start, span_end = match.span(rule.span_group)
            span_start, span_end = _trim_span(text, span_start, span_end)
            if span_start >= span_end:
                continue
            raw = text[span_start:span_end]
            if (
                _is_negated_claim(text, span_start)
                or is_rejected_classification_context(
                    text,
                    span_start,
                    span_end,
                )
                or _is_classification_call_context(
                    text,
                    span_start,
                    span_end,
                )
                or _is_nonassertive_flare_candidate(
                    text,
                    span_start,
                    raw,
                    rule.rule_id,
                )
            ):
                continue
            candidates.append(
                ClassificationInterpretationCandidate(
                    span_start=span_start,
                    span_end=span_end,
                    raw=raw,
                    certainty=_candidate_certainty(
                        text,
                        span_start,
                        span_end,
                        raw,
                        rule.rule_id,
                    ),
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


def resolve_classification_interpretation_overlaps(
    candidates: list[ClassificationInterpretationCandidate],
) -> list[ClassificationInterpretationCandidate]:
    selected: list[ClassificationInterpretationCandidate] = []
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


def classification_interpretation_deferral_reason(
    text: str,
    start: int,
    end: int,
) -> str | None:
    clause_start, clause_end = clause_bounds(text, start, end)
    clause = text[clause_start:clause_end]
    if is_rejected_classification_context(text, start, end):
        return "NEGATIVE_STATEMENT"
    if _OBSERVED_EVOLUTION_RE.search(clause) and not PHYSICAL_CAUSE_RE.search(
        clause
    ):
        return "LIGHTCURVE_EVOLUTION"
    return None


def is_negated_physical_cause_context(text: str, start: int) -> bool:
    return _is_negated_claim(text, start)


def is_rejected_classification_context(
    text: str,
    start: int,
    end: int,
) -> bool:
    sentence_start, sentence_end = sentence_bounds(text, start, end)
    prefix = text[max(sentence_start, start - 100):start]
    sentence = text[sentence_start:sentence_end]
    suffix = text[end:sentence_end]
    if _REJECTED_PREFIX_RE.search(prefix):
        return True
    return bool(
        re.search(r"\btentative(?:ly)?\s+classified\s+as\b", sentence, re.IGNORECASE)
        and _RETRACTION_CONTEXT_RE.search(suffix)
    )


def clause_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    left = start
    while left > 0 and text[left - 1] not in ".,;:!?\n":
        left -= 1
    right = end
    while right < len(text) and text[right] not in ".,;:!?\n":
        right += 1
    return left, right


def sentence_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    left = start
    while left > 0 and text[left - 1] not in ".!?\n":
        left -= 1
    right = end
    while right < len(text) and text[right] not in ".!?\n":
        right += 1
    return left, right


def _certainty(raw: str) -> str:
    return "confirmed" if _FIRM_MARKER_RE.search(raw) else "tentative"


def _candidate_certainty(
    text: str,
    start: int,
    end: int,
    raw: str,
    rule_id: str,
) -> str:
    if rule_id != "classification_interpretation.grb_class":
        return _certainty(raw)
    sentence_start, _sentence_end = sentence_bounds(text, start, end)
    context = text[max(sentence_start, start - 120):end]
    return "tentative" if _GRB_HEDGE_RE.search(context) else "confirmed"


def _is_negated_claim(text: str, start: int) -> bool:
    prefix_start = max(0, start - 30)
    return bool(_NEGATED_CLAIM_PREFIX_RE.search(text[prefix_start:start]))


def _is_classification_call_context(
    text: str,
    start: int,
    end: int,
) -> bool:
    sentence_start, sentence_end = sentence_bounds(text, start, end)
    return bool(
        _CALL_FOR_CLASSIFICATION_RE.search(text[sentence_start:sentence_end])
    )


def _is_nonassertive_flare_candidate(
    text: str,
    start: int,
    raw: str,
    rule_id: str,
) -> bool:
    if (
        rule_id != "classification_interpretation.interpretation"
        or raw.lower() != "magnetar giant flare"
    ):
        return False
    prefix = text[max(0, start - 30):start]
    return bool(re.search(r"\bcandidate\s+$", prefix, re.IGNORECASE))


def _trim_span(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and (
        text[end - 1].isspace() or text[end - 1] in ",;:"
    ):
        end -= 1
    return start, end


def _spans_overlap(
    first: ClassificationInterpretationCandidate,
    second: ClassificationInterpretationCandidate,
) -> bool:
    return first.span_start < second.span_end and second.span_start < first.span_end


__all__ = [
    "CLASSIFICATION_SIGNAL_RE",
    "PHYSICAL_CAUSE_RE",
    "ClassificationInterpretationCandidate",
    "ClassificationInterpretationExtractor",
    "classification_interpretation_deferral_reason",
    "clause_bounds",
    "find_classification_interpretation_candidates",
    "is_negated_physical_cause_context",
    "is_rejected_classification_context",
    "resolve_classification_interpretation_overlaps",
    "sentence_bounds",
]
