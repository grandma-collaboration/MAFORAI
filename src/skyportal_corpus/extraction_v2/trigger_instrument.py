from __future__ import annotations

import re
from dataclasses import dataclass

from skyportal_corpus.canonical.document import CanonicalDocument
from skyportal_corpus.extraction_v2.annotations import EventEvidenceAnnotation
from skyportal_corpus.extraction_v2.instruments_vocab import iter_instrument_matches, rule_id_for_instrument


TRIGGER_INSTRUMENT_REVIEW_COMMENT = (
    "Múltiples instrumentos con contexto de trigger; el anotador debe confirmar el primario."
)

_TRIGGER_ACTION_RE = re.compile(
    r"\b(?:was\s+triggered|triggered|was\s+detected\s+by|detected|trigger)\b",
    re.IGNORECASE,
)
# "located" is a trigger verb only in active event-localization phrases.
# Passive spatial/catalog phrases such as "are located within" are references, not trigger evidence.
_ACTIVE_LOCATED_RE = re.compile(
    r"\b(?:triggered\s+and\s+located|located\s+(?:the\s+)?(?:GRB|burst|event|[A-Z]{1,4}\s?\d))\b",
    re.IGNORECASE,
)
_FOLLOWUP_CONTEXT_RE = re.compile(
    r"\b(?:"
    r"observed|began observing|started observing|followed up|took|exposure|"
    r"imaging|reported photometry|pointed to|monitoring"
    r")\b",
    re.IGNORECASE,
)
_NON_TRIGGER_REFERENCE_SUFFIX_RE = re.compile(
    r"^\s{0,20}(?:boresight|catalog|catalogue|collaboration|detection\s*:)",
    re.IGNORECASE,
)
_DATA_REFERENCE_SUFFIX_RE = re.compile(r"^[\s-]{0,6}\bdata\b", re.IGNORECASE)


@dataclass(frozen=True)
class InstrumentCandidate:
    canonical: str
    span_start: int
    span_end: int
    rule_id: str


class TriggerInstrumentExtractor:
    extractor_id = "trigger-instrument-v1"
    extractor_version = "0.1"

    def extract(self, doc: CanonicalDocument) -> list[EventEvidenceAnnotation]:
        accepted: list[InstrumentCandidate] = []
        seen_canonical: set[str] = set()

        for candidate in find_instrument_candidates(doc.rendered_text):
            if is_non_trigger_reference(doc.rendered_text, candidate.span_start, candidate.span_end):
                continue
            if is_followup_context(doc.rendered_text, candidate.span_start, candidate.span_end):
                continue
            if not is_trigger_verb_context(doc.rendered_text, candidate.span_start, candidate.span_end):
                continue
            # A circular often names the same trigger instrument several times.
            # Keep the first trigger-context mention per canonical instrument to avoid duplicate evidence.
            if candidate.canonical in seen_canonical:
                continue
            seen_canonical.add(candidate.canonical)
            accepted.append(candidate)

        has_multiple_instruments = len({candidate.canonical for candidate in accepted}) > 1
        annotations = [
            EventEvidenceAnnotation(
                circular_id=doc.circular_id,
                text_sha256=doc.text_sha256,
                span_start=candidate.span_start,
                span_end=candidate.span_end,
                text=doc.rendered_text[candidate.span_start : candidate.span_end],
                label="TRIGGER_INSTRUMENT",
                target="instrument",
                certainty="confirmed",
                value=candidate.canonical,
                extractor_id=self.extractor_id,
                extractor_version=self.extractor_version,
                method="regex",
                rule_id=candidate.rule_id,
                confidence=0.5 if has_multiple_instruments else 1.0,
                needs_review=has_multiple_instruments,
                comment=TRIGGER_INSTRUMENT_REVIEW_COMMENT if has_multiple_instruments else None,
            )
            for candidate in accepted
        ]

        for annotation in annotations:
            if not annotation.verify(doc.rendered_text):
                raise ValueError(
                    f"Annotation failed offset verification: {annotation.rule_id} "
                    f"{annotation.span_start}-{annotation.span_end}"
                )
        return annotations


def find_instrument_candidates(text: str) -> list[InstrumentCandidate]:
    return [
        InstrumentCandidate(
            canonical=canonical,
            span_start=start,
            span_end=end,
            rule_id=rule_id_for_instrument(canonical),
        )
        for canonical, start, end in iter_instrument_matches(text)
    ]


def is_trigger_verb_context(text: str, span_start: int, span_end: int) -> bool:
    context = _sentence_limited_context(text, span_start, span_end, radius=60)
    return bool(_TRIGGER_ACTION_RE.search(context) or _ACTIVE_LOCATED_RE.search(context))


def is_followup_context(text: str, span_start: int, span_end: int) -> bool:
    return bool(_FOLLOWUP_CONTEXT_RE.search(_sentence_limited_context(text, span_start, span_end, radius=60)))


def is_non_trigger_reference(text: str, span_start: int, span_end: int) -> bool:
    suffix = text[span_end : min(len(text), span_end + 32)]
    if _NON_TRIGGER_REFERENCE_SUFFIX_RE.search(suffix):
        return True

    # Keep this data gate short and LAT-specific: "LAT data" is an analysis/reference mention,
    # but "GBM trigger data" should remain valid because "trigger" identifies the instrument.
    short_suffix = text[span_end : min(len(text), span_end + 12)]
    matched_text = text[span_start:span_end]
    return _is_lat_match(matched_text) and bool(_DATA_REFERENCE_SUFFIX_RE.search(short_suffix))


def _is_lat_match(text: str) -> bool:
    return bool(re.fullmatch(r"(?:Fermi[\s\-/]+)?LAT", text, re.IGNORECASE))


def _sentence_limited_context(text: str, span_start: int, span_end: int, radius: int) -> str:
    window_start = max(0, span_start - radius)
    window_end = min(len(text), span_end + radius)
    context = text[window_start:window_end]
    local_start = span_start - window_start
    local_end = span_end - window_start

    left_boundary = max(context.rfind(".", 0, local_start), context.rfind("\n", 0, local_start))
    if left_boundary != -1:
        context = context[left_boundary + 1 :]
        local_end -= left_boundary + 1

    right_period = context.find(".", local_end)
    right_newline = context.find("\n", local_end)
    right_boundaries = [boundary for boundary in (right_period, right_newline) if boundary != -1]
    if right_boundaries:
        context = context[: min(right_boundaries)]

    return context
