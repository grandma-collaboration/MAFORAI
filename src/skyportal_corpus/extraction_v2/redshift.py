from __future__ import annotations

import re
from dataclasses import dataclass

from skyportal_corpus.canonical.document import CanonicalDocument
from skyportal_corpus.extraction_v2.annotations import EventEvidenceAnnotation
from skyportal_corpus.extraction_v2.event_identity import is_in_table_row


AMBIGUOUS_REDSHIFT_COMMENT = (
    "Redshift sin atribución explícita a evento o contexto; verificar si pertenece "
    "al evento/afterglow/host o a una galaxia de contexto."
)
CITED_GCN_REDSHIFT_COMMENT = "Redshift del evento citado de otra circular (referencia GCN)."
CONTEXT_REDSHIFT_COMMENT = "Clasificado como redshift de contexto/intervening; verificar que no sea el redshift del evento."

_REDSHIFT_VALUE_RE = re.compile(r"\d+\.\d+")
_TENTATIVE_RE = re.compile(r"\b(possible|likely|candidate)\b|~", re.IGNORECASE)
_HOST_CANDIDATE_RE = re.compile(
    r"\bif\s+[^.\n]{0,80}\bis\s+associated\s+with\s+this\s+galaxy\b",
    re.IGNORECASE,
)
_TENTATIVE_EVENT_ASSOCIATION_RE = re.compile(
    r"\b(candidate\s+afterglow|propose[^.\n]{0,120}afterglow)\b",
    re.IGNORECASE,
)
_REJECTED_RE = re.compile(r"\b(not the redshift of|not associated)\b", re.IGNORECASE)
_CONTEXT_SIGNAL_RE = re.compile(
    r"\b("
    r"nearby\s+galax(?:y|ies)|foreground|in\s+the\s+field|intervening|unrelated|"
    r"a\s+galaxy\s+at|field\s+galaxy|cluster\s+at|not\s+the\s+redshift\s+of|not\s+associated|"
    r"matched\s+with\s+galaxies\s+in\s+the\s+range|galaxies\s+in\s+the\s+range"
    r")\b",
    re.IGNORECASE,
)
_DIRECT_CONTEXT_RE = re.compile(
    r"\b("
    r"not\s+the\s+redshift\s+of|not\s+associated|"
    r"foreground[^.\n]{0,80}(?:\bz\s*[=~≈]|\d+\.\d+)|"
    r"intervening[^.\n]{0,80}(?:\bz\s*[=~≈]|\d+\.\d+)|"
    r"unrelated[^.\n]{0,80}(?:\bz\s*[=~≈]|\d+\.\d+)|"
    r"a\s+galaxy\s+at\s+(?:\bz\s*[=~≈]\s*)?\d+\.\d+|"
    r"field\s+galaxy[^.\n]{0,80}(?:\bz\s*[=~≈]|\d+\.\d+)|"
    r"cluster\s+at\s+(?:\bz\s*[=~≈]\s*)?\d+\.\d+|"
    r"nearby[^.\n]{0,80}(?:\bz\s*[=~≈]\s*\d+\.\d+|\d+\.\d+)[^.\n]{0,80}galax(?:y|ies)|"
    r"(?:matched\s+with\s+)?galaxies\s+in\s+the\s+range[^.\n]{0,80}\d+\.\d+\s*<\s*z\s*<\s*\d+\.\d+"
    r")\b",
    re.IGNORECASE,
)
_ABSOLUTE_MAG_CONTEXT_RE = re.compile(
    r"(?:\bM_?z?\s*[><~=][^.\n]{0,120}\bat\s+[^.\n]{0,40}redshift|"
    r"\babsolute\s+magnitude[^.\n]{0,120}\bat\s+redshift)",
    re.IGNORECASE,
)
_EVENT_SIGNAL_RE = re.compile(
    r"\b("
    r"afterglow|counterpart|optical\s+transient|host\s+environment|host\s+galaxy|host\s+of|"
    r"of\s+the\s+GRB|of\s+the\s+burst|of\s+the\s+event|of\s+GRB|of\s+EP"
    r")\b",
    re.IGNORECASE,
)
_EVENT_ANCHOR_PHRASES = (
    "redshift of the burst",
    "redshift of the grb",
    "redshift for this event",
    "redshift of this event",
    "redshift of the event",
    "this is the redshift",
    "is the redshift of",
    "we suggest to be the redshift",
    "suggest to be the redshift",
    "at the redshift of",
    "at the redshift z",
    "at this redshift",
    "lies at this redshift",
    "lies at a redshift",
    "host environment",
    "host galaxy",
    "host of",
)
_CONFIRM_EVENT_ANCHOR_PHRASES = (
    "confirm the redshift measurement",
    "confirming the redshift measurement",
)
_GCN_CITED_REDSHIFT_RE = re.compile(
    r"\b(?:assuming|adopting)\s+the\s+redshift[^\n]{0,160}\bGCN\b|"
    r"\bat\s+the\s+redshift\s+z\s*[=~≈]\s*\d+\.\d+[^\n]{0,160}\bGCN\b",
    re.IGNORECASE,
)
_EVENT_NAME_RE = re.compile(
    r"\b("
    r"GRB\s?\d{6}[A-Za-z]?|EP\s?\d{6}[a-z]|AT\s?2\d{3}[a-z]{2,4}|"
    r"SN\s?2\d{3}[a-z]{2,4}|ZTF\d{2}[a-z]{7}|GW\d{6}(?:_\d{6})?|"
    r"IceCube[- ]?\d{6}[A-Z]|S\d{6}[a-z]{1,3}"
    r")\b",
    re.IGNORECASE,
)
_COUNTERPART_TARGET_RE = re.compile(r"\b(afterglow|counterpart|optical\s+transient)\b", re.IGNORECASE)
_HOST_TARGET_RE = re.compile(r"\b(host\s+environment|host\s+galaxy|host\s+of)\b", re.IGNORECASE)
_BAND_SUFFIX_RE = re.compile(r"^\s*(mag|bands?|filters?|-band)\b", re.IGNORECASE)
_BAND_LIST_RE = re.compile(r"\b[ugrizy]\s*,\s*[ugrizy]\s*,\s*[ugrizy]\s*,\s*z\s+(?:bands?|filters?)\b", re.IGNORECASE)


@dataclass(frozen=True)
class _Rule:
    rule_id: str
    pattern: re.Pattern[str]
    priority: int
    kind: str


@dataclass(frozen=True)
class RedshiftCandidate:
    raw: str
    value: str
    span_start: int
    span_end: int
    kind: str
    rule_id: str


_RULES = (
    _Rule(
        "redshift.z_equals",
        re.compile(r"\bz\s*[=~≈]\s*(?P<value>\d+\.\d+)(?:\s*\+/-\s*\d+\.\d+)?", re.IGNORECASE),
        0,
        "single",
    ),
    _Rule(
        "redshift.z_spec",
        re.compile(r"\bz_?(?:spec|phot|abs|em)\s*[=~]\s*(?P<value>\d+\.\d+)", re.IGNORECASE),
        1,
        "single",
    ),
    _Rule(
        "redshift.redshift_word",
        re.compile(
            r"\bredshift\s+(?:of|at|is|=|~)?\s*(?:z\s*[=~≈]\s*)?(?P<value>\d+\.\d+)",
            re.IGNORECASE,
        ),
        2,
        "single",
    ),
    _Rule(
        "redshift.z_range",
        re.compile(r"(?P<low>\d+\.\d+)\s*<\s*z\s*<\s*(?P<high>\d+\.\d+)", re.IGNORECASE),
        3,
        "range",
    ),
)


class RedshiftExtractor:
    extractor_id = "redshift-v1"
    extractor_version = "0.1"

    def extract(self, doc: CanonicalDocument) -> list[EventEvidenceAnnotation]:
        accepted = resolve_overlaps(find_redshift_candidates(doc.rendered_text))
        classified: list[tuple[RedshiftCandidate, str, str]] = []
        for candidate in accepted:
            attribution, reason = classify_attribution(
                doc.rendered_text,
                candidate.span_start,
                candidate.span_end,
            )
            classified.append((candidate, attribution, reason))

        explicit_event_values = {
            candidate.value
            for candidate, attribution, reason in classified
            if attribution == "EVENT" and reason in {"explicit_event", "event_gcn_reference"}
        }
        context_values = {
            candidate.value
            for candidate, attribution, _reason in classified
            if attribution == "CONTEXT"
        }

        annotations: list[EventEvidenceAnnotation] = []
        for candidate, attribution, reason in classified:
            if (
                attribution == "EVENT"
                and reason == "ambiguous"
                and candidate.value in explicit_event_values
                and candidate.value not in context_values
            ):
                # Same circular, same redshift value, and another occurrence has explicit event attribution.
                # Never apply this if any same-value occurrence was classified as CONTEXT.
                reason = "explicit_event"
            target = assign_target(doc.rendered_text, candidate.span_start, candidate.span_end, attribution)
            needs_review = attribution == "CONTEXT" or (
                attribution == "EVENT" and reason in {"ambiguous", "mixed_signals"}
            )
            certainty = (
                "confirmed"
                if reason == "event_gcn_reference"
                else _certainty(doc.rendered_text, candidate.span_start, candidate.span_end)
            )
            annotation = EventEvidenceAnnotation(
                circular_id=doc.circular_id,
                text_sha256=doc.text_sha256,
                span_start=candidate.span_start,
                span_end=candidate.span_end,
                text=candidate.raw,
                label="REDSHIFT_EVENT" if attribution == "EVENT" else "REDSHIFT_CONTEXT",
                target=target,
                certainty=certainty,
                value=candidate.value,
                unit="",
                comment=_comment_for_reason(attribution, reason, needs_review),
                extractor_id=self.extractor_id,
                extractor_version=self.extractor_version,
                method="regex",
                rule_id=candidate.rule_id,
                confidence=0.5 if needs_review else 1.0,
                needs_review=needs_review,
            )
            annotations.append(annotation)

        annotations.sort(key=lambda item: (item.span_start, item.span_end, item.rule_id or ""))
        for annotation in annotations:
            if not annotation.verify(doc.rendered_text):
                raise ValueError(
                    f"Annotation failed offset verification: {annotation.rule_id} "
                    f"{annotation.span_start}-{annotation.span_end}"
                )
        return annotations


def find_redshift_candidates(text: str) -> list[RedshiftCandidate]:
    candidates: list[RedshiftCandidate] = []
    for rule in _RULES:
        for match in rule.pattern.finditer(text):
            if is_in_table_row(text, match.start(), match.end()):
                continue
            raw = text[match.start() : match.end()]
            value = _candidate_value(match, rule)
            # Anti-band-z gate: z is also a photometric band. Reject magnitudes,
            # filters, table-like rows, and implausible redshifts outside [0, 12].
            if _looks_like_photometric_z_band(text, match.start(), match.end(), value):
                continue
            candidates.append(
                RedshiftCandidate(
                    raw=raw,
                    value=value,
                    span_start=match.start(),
                    span_end=match.end(),
                    kind=rule.kind,
                    rule_id=rule.rule_id,
                )
            )
    return candidates


def classify_attribution(text: str, span_start: int, span_end: int) -> tuple[str, str]:
    window = _window(text, span_start, span_end, 120)
    wide_window = _window(text, span_start, span_end, 250)
    sentence_context = _sentence_and_next_context(text, span_start, span_end)
    broad_context = f"{wide_window}\n{sentence_context}"
    has_event = bool(_EVENT_SIGNAL_RE.search(window) or _EVENT_NAME_RE.search(window))
    has_event_anchor = _has_event_anchor(sentence_context) or _event_name_at_redshift_same_sentence(sentence_context)
    has_confirm_anchor = _has_confirm_event_anchor(broad_context)
    has_gcn_reference = bool(_GCN_CITED_REDSHIFT_RE.search(broad_context))

    if _has_negated_context_for_span(text, span_start, span_end):
        return "CONTEXT", "explicit_context"
    if _TENTATIVE_EVENT_ASSOCIATION_RE.search(broad_context) and not has_event_anchor:
        return "EVENT", "ambiguous"
    if has_event_anchor:
        return "EVENT", "explicit_event"
    if _has_direct_context_for_span(text, span_start, span_end):
        return "CONTEXT", "explicit_context"
    if has_confirm_anchor:
        return "EVENT", "explicit_event"
    if has_gcn_reference:
        return "EVENT", "event_gcn_reference"
    if has_event:
        return "EVENT", "explicit_event"
    if _TENTATIVE_EVENT_ASSOCIATION_RE.search(broad_context) and not has_event_anchor:
        return "EVENT", "ambiguous"
    return "EVENT", "ambiguous"


def assign_target(text: str, span_start: int, span_end: int, attribution: str) -> str:
    if attribution == "CONTEXT":
        return "nearby_galaxy"
    window = _window(text, span_start, span_end, 120)
    if _COUNTERPART_TARGET_RE.search(window):
        return "counterpart"
    if _HOST_TARGET_RE.search(window):
        return "host"
    return "event"


def resolve_overlaps(candidates: list[RedshiftCandidate]) -> list[RedshiftCandidate]:
    by_rule_priority = {rule.rule_id: rule.priority for rule in _RULES}
    selected: list[RedshiftCandidate] = []
    for candidate in sorted(
        candidates,
        key=lambda item: (
            -(item.span_end - item.span_start),
            by_rule_priority.get(item.rule_id, 999),
            item.span_start,
            item.span_end,
        ),
    ):
        if any(_overlaps(candidate, existing) for existing in selected):
            continue
        selected.append(candidate)
    return sorted(selected, key=lambda item: (item.span_start, item.span_end, item.rule_id))


def _candidate_value(match: re.Match[str], rule: _Rule) -> str:
    if rule.kind == "range":
        return f"{match.group('low')}-{match.group('high')}"
    return match.group("value")


def _looks_like_photometric_z_band(text: str, span_start: int, span_end: int, value: str) -> bool:
    values = [float(item) for item in _REDSHIFT_VALUE_RE.findall(value)]
    if not values or any(item < 0 or item > 12 for item in values):
        return True
    suffix = text[span_end : min(len(text), span_end + 12)]
    if _BAND_SUFFIX_RE.search(suffix):
        return True
    local = text[max(0, span_start - 40) : min(len(text), span_end + 40)]
    return bool(_BAND_LIST_RE.search(local))


def _certainty(text: str, span_start: int, span_end: int) -> str:
    window = _window(text, span_start, span_end, 160)
    if _REJECTED_RE.search(window):
        return "rejected"
    if _TENTATIVE_RE.search(window) or _HOST_CANDIDATE_RE.search(_window(text, span_start, span_end, 250)):
        return "tentative"
    return "confirmed"


def _comment_for_reason(attribution: str, reason: str, needs_review: bool) -> str | None:
    if attribution == "CONTEXT":
        return CONTEXT_REDSHIFT_COMMENT
    if reason == "event_gcn_reference":
        return CITED_GCN_REDSHIFT_COMMENT
    if needs_review:
        return AMBIGUOUS_REDSHIFT_COMMENT
    return None


def _has_negated_context_for_span(text: str, start: int, end: int) -> bool:
    around = _normalize_for_matching(_window(text, start, end, 140))
    return any(
        phrase in around
        for phrase in (
            "not the redshift of",
            "not associated",
            "not related",
            "unrelated to the grb",
        )
    )


def _has_direct_context_for_span(text: str, start: int, end: int) -> bool:
    sentence_context = _sentence_context(text, start, end)
    normalized_sentence = _normalize_for_matching(sentence_context)
    before = _normalize_for_matching(text[max(0, start - 120) : start])
    after = _normalize_for_matching(text[end : min(len(text), end + 120)])
    around = f"{before} <z> {after}"

    if _ABSOLUTE_MAG_CONTEXT_RE.search(sentence_context):
        return True
    if "matched with galaxies in the range" in normalized_sentence or "galaxies in the range" in normalized_sentence:
        return True
    for marker in ("intervening", "foreground"):
        if marker in before and len(before.rsplit(marker, 1)[1]) <= 140:
            return True
        if marker in after and len(after.split(marker, 1)[0]) <= 70:
            return True
    if re.search(r"(intervening|foreground)(?:\s+\w+){0,10}\s+(?:at\s+)?$", before):
        return True
    if re.search(r"(intervening|foreground)(?:\s+\w+){0,10}\s+(?:at\s+)?<z>", around):
        return True
    if re.search(r"<z>(?:\s+\w+){0,10}\s+(intervening|foreground)", around):
        return True
    if re.search(r"(?:^|\s)(?:a\s+)?(?:nearby\s+|field\s+|catalogued\s+)?galax(?:y|ies)\s+(?:is\s+)?(?:at|with)$", before):
        return True
    if re.search(r"(?:^|\s)(?:a\s+)?(?:nearby\s+|field\s+|catalogued\s+)?galax(?:y|ies)\s+(?:is\s+)?(?:at|with)\s+(?:a\s+)?(?:photometric\s+|spectroscopic\s+)?(?:redshift\s+(?:of\s+)?)?$", before):
        return True
    if re.search(r"(?:cluster|field\s+galaxy)\s+at\s+$", before):
        return True
    if "nearby" in before.split()[-8:] and re.search(r"^.*galax(?:y|ies)\b", after):
        return True
    return False


def _window(text: str, start: int, end: int, radius: int) -> str:
    return text[max(0, start - radius) : min(len(text), end + radius)]


def _sentence_and_next_context(text: str, start: int, end: int) -> str:
    sentence_start = _previous_sentence_boundary(text, start)
    first_end = _next_sentence_boundary(text, end)
    second_end = _next_sentence_boundary(text, first_end)
    return text[sentence_start:second_end]


def _sentence_context(text: str, start: int, end: int) -> str:
    sentence_start = _previous_sentence_boundary(text, start)
    sentence_end = _next_sentence_boundary(text, end)
    return text[sentence_start:sentence_end]


def _previous_sentence_boundary(text: str, start: int) -> int:
    previous = -1
    for pattern in (". ", ".\n", "? ", "?\n", "! ", "!\n", "\n\n"):
        index = text.rfind(pattern, 0, start)
        if index > previous:
            previous = index + len(pattern)
    return max(0, previous)


def _next_sentence_boundary(text: str, start: int) -> int:
    candidates = [
        index + len(pattern)
        for pattern in (". ", ".\n", "? ", "?\n", "! ", "!\n", "\n\n")
        if (index := text.find(pattern, start)) != -1
    ]
    return min(candidates) if candidates else len(text)


def _event_name_at_redshift_same_sentence(sentence_context: str) -> bool:
    normalized = _normalize_for_matching(sentence_context)
    if not _EVENT_NAME_RE.search(sentence_context):
        return False
    return any(
        phrase in normalized
        for phrase in (
            "at the redshift",
            "at this redshift",
            "lies at this redshift",
            "lies at a redshift",
        )
    )


def _has_event_anchor(text: str) -> bool:
    normalized = _normalize_for_matching(text)
    return any(phrase in normalized for phrase in _EVENT_ANCHOR_PHRASES)


def _has_confirm_event_anchor(text: str) -> bool:
    normalized = _normalize_for_matching(text)
    return any(phrase in normalized for phrase in _CONFIRM_EVENT_ANCHOR_PHRASES)


def _normalize_for_matching(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _overlaps(left: RedshiftCandidate, right: RedshiftCandidate) -> bool:
    return left.span_start < right.span_end and right.span_start < left.span_end
