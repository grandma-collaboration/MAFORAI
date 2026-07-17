from __future__ import annotations

import re
from dataclasses import dataclass

from skyportal_corpus.canonical.document import CanonicalDocument
from skyportal_corpus.extraction_v2.annotations import EventEvidenceAnnotation
from skyportal_corpus.extraction_v2.instruments_vocab import iter_instrument_matches


_NUMBER = r"(?:\d+(?:\.\d+)?|\.\d+)"
_PLUS_MINUS = r"(?:\+/-|±|\+\s*-)"
_ERROR = (
    rf"(?:\s*{_PLUS_MINUS}\s*{_NUMBER}|"
    rf"\s*[+-]\s*{_NUMBER}\s*/\s*[+-]\s*{_NUMBER}|"
    rf"\s*[\(（]\s*[+-]?\s*{_NUMBER}\s*,\s*[+-]?\s*{_NUMBER}\s*[\)）]|"
    rf"\s*\(\s*[+-]?\s*{_NUMBER}\s*\)\s*\(\s*[+-]?\s*{_NUMBER}\s*\)|"
    rf"\s*[+-]\s*{_NUMBER})?"
)
_VALUE = rf"{_NUMBER}{_ERROR}"
_UNIT = r"(?:milliseconds?|msecs?|msec|ms|seconds?|secs?|sec|s|minutes?|mins?|min)"
_APPROX = r"(?:about|approximately|approx\.?|around|at\s+least|~)"

_T90_T50_PAIR_RE = re.compile(
    rf"\bT90\s+and\s+T50\s+durations?\b[^.\n]{{0,100}}?\b(?:are|were)\s*"
    rf"(?P<t90>{_VALUE})\s*(?P<t90_unit>{_UNIT})\s+and\s+"
    rf"(?P<t50>{_VALUE})\s*(?P<t50_unit>{_UNIT})\b",
    re.IGNORECASE,
)
_T90_EXPLICIT_RE = re.compile(
    rf"\b(?P<prefix>T90(?:[-\s]+value)?(?:\s+duration)?|duration\s*\(\s*T90\s*\))"
    rf"(?:[^\n.!?]{{0,40}}?\b(?:is|was|are|were|of|measured\s+to\s+be)\b\s*|"
    rf"\s*(?:=|:)\s*)?\s*"
    rf"(?P<approx>{_APPROX})?\s*"
    rf"(?P<value>{_VALUE})(?:\s*(?P<unit>{_UNIT})\b)?",
    re.IGNORECASE,
)
_T50_EXPLICIT_RE = re.compile(
    rf"\bT50(?:\s+duration)?\s*(?:of|is|=|:)?\s*(?P<approx>{_APPROX})?\s*"
    rf"(?P<value>{_VALUE})(?:\s*(?P<unit>{_UNIT})\b)?",
    re.IGNORECASE,
)
_GENERAL_DURATION_RE = re.compile(
    rf"\bduration(?:\s*\([^)]{{1,20}}\))?"
    rf"(?:\s+of|[^\n.!?]{{0,60}}?\b(?:is|was)\b"
    rf"(?:\s+estimated[^\n.!?]{{0,30}}?\bto\s+be)?)\s*"
    rf"(?P<approx>{_APPROX})?\s*(?P<value>{_VALUE})\s*(?P<unit>{_UNIT})\b",
    re.IGNORECASE,
)
_LASTED_DURATION_RE = re.compile(
    rf"\b(?:lasted|lasting)\s*(?:for\s+)?(?P<approx>{_APPROX})?\s*"
    rf"(?P<value>{_VALUE})\s*(?P<unit>{_UNIT})\b",
    re.IGNORECASE,
)
_EVENT_DURATION_SUFFIX_RE = re.compile(
    rf"\b(?:burst|event|pulse|emission|episode)\b[^\n.!?]{{0,55}}?"
    rf"(?P<approx>{_APPROX})?\s*(?P<value>{_VALUE})\s*(?P<unit>{_UNIT})\s*"
    rf"(?:in\s+)?duration\b",
    re.IGNORECASE,
)

_ENERGY_BAND_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*[-–]\s*\d+(?:\.\d+)?\s*(?:keV|MeV|GeV)\b",
    re.IGNORECASE,
)
_TENTATIVE_RE = re.compile(
    r"\b(?:about|approximately|approx\.?|around|at\s+least|estimated|preliminary)\b|~",
    re.IGNORECASE,
)
_EXPOSURE_RE = re.compile(
    r"\b(?:exposure(?:\s+time)?|integration(?:\s+time)?)\b|"
    r"\b\d+\s*[xX*]\s*\d+(?:\.\d+)?\s*(?:ms|s|sec|seconds?)\b",
    re.IGNORECASE,
)
_OBSERVATION_LASTED_RE = re.compile(
    r"\b(?:observations?|exposures?|images?)\b[^.!?\n]{0,40}\b(?:lasted|lasting)\b",
    re.IGNORECASE,
)
_RELATIVE_TIME_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:ms|s|sec|seconds?|min|hours?|hr)\s+after\s+"
    r"(?:the\s+)?(?:BAT\s+|GBM\s+)?trigger\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DurationCandidate:
    span_start: int
    span_end: int
    raw: str
    value: str
    unit: str | None
    label: str
    rule_id: str
    priority: int
    is_t50: bool = False


def assemble_instrument_band_comment(
    instrument: str | None,
    band: str | None,
) -> str | None:
    """Assemble the shared scientific-context comment without empty fields."""

    parts = [part for part in (instrument, band) if part]
    return ", ".join(dict.fromkeys(parts)) or None


def resolve_measurement_instrument(
    text: str,
    start: int,
    end: int,
) -> str | None:
    """Resolve the reporter, allowing only a governing same-clause override."""

    reporting_instrument = _reporting_instrument(text, start, end)
    clause_start, clause_end = _instrument_clause_bounds(text, start, end)
    clause = text[clause_start:clause_end]
    clause_matches = iter_instrument_matches(clause)

    if reporting_instrument is not None:
        for instrument, local_start, local_end in clause_matches:
            if instrument == reporting_instrument:
                continue
            absolute_start = clause_start + local_start
            absolute_end = clause_start + local_end
            if _instrument_governs_value(
                text,
                clause_start,
                clause_end,
                absolute_start,
                absolute_end,
                start,
                end,
            ):
                return instrument
        return reporting_instrument

    governing = [
        (instrument, local_start, local_end)
        for instrument, local_start, local_end in clause_matches
        if _instrument_governs_value(
            text,
            clause_start,
            clause_end,
            clause_start + local_start,
            clause_start + local_end,
            start,
            end,
        )
    ]
    if governing:
        return _nearest_instrument_match(governing, start - clause_start, end - clause_start)
    return None


class DurationExtractor:
    extractor_id = "duration-v1"
    extractor_version = "0.1"

    def extract(self, doc: CanonicalDocument) -> list[EventEvidenceAnnotation]:
        annotations: list[EventEvidenceAnnotation] = []
        for candidate in resolve_duration_overlaps(find_duration_candidates(doc.rendered_text)):
            needs_review = candidate.unit is None
            context_comment = _scientific_context(
                doc.rendered_text,
                candidate.span_start,
                candidate.span_end,
                label=candidate.label,
                is_t50=candidate.is_t50,
            )
            review_comment = (
                "Duration unit not identified; verify the reported event duration."
                if needs_review
                else None
            )
            comment = _join_comment(review_comment, context_comment)
            certainty = (
                "tentative"
                if _TENTATIVE_RE.search(candidate.value)
                else "confirmed"
            )
            annotation = EventEvidenceAnnotation(
                circular_id=doc.circular_id,
                text_sha256=doc.text_sha256,
                span_start=candidate.span_start,
                span_end=candidate.span_end,
                text=candidate.raw,
                label=candidate.label,
                target="event",
                certainty=certainty,
                value=candidate.value,
                unit=candidate.unit or "",
                comment=comment,
                extractor_id=self.extractor_id,
                extractor_version=self.extractor_version,
                method="regex",
                rule_id=candidate.rule_id,
                confidence=0.5 if needs_review else 1.0,
                needs_review=needs_review,
            )
            if not annotation.verify(doc.rendered_text):
                raise ValueError(
                    f"Duration annotation failed offset verification: {annotation.rule_id} "
                    f"{annotation.span_start}-{annotation.span_end}"
                )
            annotations.append(annotation)
        return annotations


def find_duration_candidates(text: str) -> list[DurationCandidate]:
    """Find event-duration expressions before annotation construction.

    T90 wins only when it is explicitly attached to the value or appears within
    the same sentence and 60 characters. T50 remains DURATION_GENERAL. Dedicated
    paired handling prevents the two values in a ``T90 and T50`` sentence from
    inheriting the same label.
    """

    candidates: list[DurationCandidate] = []

    for match in _T90_T50_PAIR_RE.finditer(text):
        candidates.append(
            _pair_candidate(text, match, "t90", "t90_unit", "T90", False, 0)
        )
        candidates.append(
            _pair_candidate(
                text,
                match,
                "t50",
                "t50_unit",
                "DURATION_GENERAL",
                True,
                0,
            )
        )

    for match in _T90_EXPLICIT_RE.finditer(text):
        candidate = _candidate_from_match(
            text,
            match,
            label="T90",
            rule_id="duration.t90_explicit",
            priority=1,
        )
        candidates.append(candidate)

    for match in _T50_EXPLICIT_RE.finditer(text):
        candidate = _candidate_from_match(
            text,
            match,
            label="DURATION_GENERAL",
            rule_id="duration.t50_explicit",
            priority=1,
            is_t50=True,
        )
        candidates.append(candidate)

    for pattern in (
        _GENERAL_DURATION_RE,
        _LASTED_DURATION_RE,
        _EVENT_DURATION_SUFFIX_RE,
    ):
        for match in pattern.finditer(text):
            if _is_negative_duration_context(text, match.start(), match.end()):
                continue
            label, is_t50 = _duration_label_from_boundary(text, match.start(), match.end())
            rule_id = "duration.t90_nearby" if label == "T90" else "duration.duration_general"
            candidates.append(
                _candidate_from_match(
                    text,
                    match,
                    label=label,
                    rule_id=rule_id,
                    priority=2,
                    is_t50=is_t50,
                )
            )

    return sorted(candidates, key=lambda item: (item.span_start, item.priority, item.span_end))


def resolve_duration_overlaps(candidates: list[DurationCandidate]) -> list[DurationCandidate]:
    accepted: list[DurationCandidate] = []
    for candidate in sorted(
        candidates,
        key=lambda item: (item.priority, item.span_start, -(item.span_end - item.span_start)),
    ):
        if any(
            candidate.span_start < current.span_end and current.span_start < candidate.span_end
            for current in accepted
        ):
            continue
        accepted.append(candidate)
    return sorted(accepted, key=lambda item: (item.span_start, item.span_end, item.rule_id))


def _pair_candidate(
    text: str,
    match: re.Match[str],
    value_group: str,
    unit_group: str,
    label: str,
    is_t50: bool,
    priority: int,
) -> DurationCandidate:
    start = match.start(value_group)
    end = match.end(unit_group)
    return DurationCandidate(
        span_start=start,
        span_end=end,
        raw=text[start:end],
        value=_normalize_duration_value(match.group(value_group), None),
        unit=match.group(unit_group),
        label=label,
        rule_id="duration.t90_t50_pair_t50" if is_t50 else "duration.t90_t50_pair_t90",
        priority=priority,
        is_t50=is_t50,
    )


def _candidate_from_match(
    text: str,
    match: re.Match[str],
    label: str,
    rule_id: str,
    priority: int,
    is_t50: bool = False,
) -> DurationCandidate:
    unit = match.groupdict().get("unit")
    return DurationCandidate(
        span_start=match.start(),
        span_end=match.end(),
        raw=text[match.start() : match.end()],
        value=_normalize_duration_value(
            match.group("value"),
            match.groupdict().get("approx"),
        ),
        unit=unit,
        label=label,
        rule_id=rule_id,
        priority=priority,
        is_t50=is_t50,
    )


def _normalize_duration_value(value: str, approximate: str | None) -> str:
    normalized = value.replace("±", "+/-").replace("（", "(").replace("）", ")")
    normalized = re.sub(r"\s*\+\s*-\s*", " +/- ", normalized)
    normalized = re.sub(r"\s*\+/-\s*", " +/- ", normalized)
    normalized = re.sub(
        rf"\+\s*({_NUMBER})\s*/\s*-\s*({_NUMBER})",
        lambda match: f"+{match.group(1)}/-{match.group(2)}",
        normalized,
    )
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if approximate:
        prefix = approximate.strip()
        normalized = f"{prefix} {normalized}"
    return normalized


def _duration_label_from_boundary(text: str, start: int, end: int) -> tuple[str, bool]:
    sentence_start, sentence_end = _sentence_bounds(text, start, end)
    sentence = text[sentence_start:sentence_end]
    relative_start = start - sentence_start
    relative_end = end - sentence_start
    tokens = [
        (token.group(0).upper(), token.start(), token.end())
        for token in re.finditer(r"\bT(?:90|50)\b", sentence, re.IGNORECASE)
        if _distance_to_span(token.start(), token.end(), relative_start, relative_end) <= 60
    ]
    if not tokens:
        return "DURATION_GENERAL", False
    nearest = min(
        tokens,
        key=lambda token: _distance_to_span(token[1], token[2], relative_start, relative_end),
    )
    if nearest[0] == "T50":
        return "DURATION_GENERAL", True
    return "T90", False


def _is_negative_duration_context(text: str, start: int, end: int) -> bool:
    local = text[max(0, start - 70) : min(len(text), end + 70)]
    preceding = text[max(0, start - 60) : start]
    sentence_start, sentence_end = _sentence_bounds(text, start, end)
    sentence = text[sentence_start:sentence_end]
    if _EXPOSURE_RE.search(local):
        return True
    if _OBSERVATION_LASTED_RE.search(sentence):
        return True
    if re.search(
        r"\b(?:observations?|exposures?|images?|filters?)\b[^.!?\n]{0,45}$",
        preceding,
        re.IGNORECASE,
    ):
        return True
    if _RELATIVE_TIME_RE.search(local):
        return True
    return False


def _scientific_context(
    text: str,
    start: int,
    end: int,
    label: str,
    is_t50: bool,
) -> str | None:
    sentence_start, sentence_end = _sentence_bounds(text, start, end)
    window_start = max(0, sentence_start - 80)
    window_end = min(len(text), sentence_end + 80)
    sentence = text[sentence_start:sentence_end]
    window = text[window_start:window_end]
    instrument = resolve_measurement_instrument(text, start, end)
    if instrument is None and re.search(r"\bSGM\b", window):
        instrument = "SGM"

    if label == "T90" or is_t50:
        energy_band = _nearest_match(
            _ENERGY_BAND_RE,
            sentence,
            start - sentence_start,
            end - sentence_start,
        )
        if energy_band is None:
            energy_band = _nearest_match(
                _ENERGY_BAND_RE,
                window,
                start - window_start,
                end - window_start,
            )
    else:
        clause_start = max(sentence_start, start - 40)
        clause_end = min(sentence_end, end + 60)
        clause = text[clause_start:clause_end]
        energy_band = _nearest_match(
            _ENERGY_BAND_RE,
            clause,
            start - clause_start,
            end - clause_start,
        )

    band = (
        re.sub(r"\s+", " ", energy_band.group(0)).strip()
        if energy_band is not None
        else None
    )
    context = assemble_instrument_band_comment(instrument, band)
    if not is_t50:
        return context
    return ", ".join(part for part in ("T50", context) if part)


def _sentence_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    boundaries = [
        match
        for match in re.finditer(r"(?<!\d)[.!?](?!\d)", text)
    ]
    left = max((match.end() for match in boundaries if match.end() <= start), default=0)
    right = min((match.end() for match in boundaries if match.start() >= end), default=len(text))
    return left, right


def _nearest_instrument_match(
    matches: list[tuple[str, int, int]],
    start: int,
    end: int,
) -> str:
    center = (start + end) / 2
    return min(matches, key=lambda item: abs(((item[1] + item[2]) / 2) - center))[0]


def _reporting_instrument(text: str, start: int, end: int) -> str | None:
    subject_line = text.split("\n", 1)[0]
    subject_matches = iter_instrument_matches(subject_line)
    if subject_matches:
        return subject_matches[0][0]

    intro = text[: min(len(text), 1200)]
    intro_matches = iter_instrument_matches(intro)
    reporting_cues = list(
        re.finditer(
            r"\b(?:on\s+behalf\s+of|team\s*,?\s+reports?|reports?\s+on\s+behalf|"
            r"as\s+observed\s+by)\b",
            intro,
            re.IGNORECASE,
        )
    )
    if intro_matches and reporting_cues:
        return min(
            intro_matches,
            key=lambda item: min(
                abs(((item[1] + item[2]) / 2) - ((cue.start() + cue.end()) / 2))
                for cue in reporting_cues
            ),
        )[0]
    return None


def _instrument_clause_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    sentence_boundaries = list(re.finditer(r"\.(?!\d)|[!?]", text))
    sentence_start = max(
        (match.end() for match in sentence_boundaries if match.end() <= start),
        default=0,
    )
    sentence_end = min(
        (match.start() for match in sentence_boundaries if match.start() >= end),
        default=len(text),
    )
    left_delimiters = list(re.finditer(r"[,;]", text[sentence_start:start]))
    clause_start = (
        sentence_start + left_delimiters[-1].end()
        if left_delimiters
        else sentence_start
    )
    right_delimiter = re.search(r"[,;]", text[end:sentence_end])
    clause_end = (
        end + right_delimiter.start()
        if right_delimiter is not None
        else sentence_end
    )
    return clause_start, clause_end


def _instrument_governs_value(
    text: str,
    clause_start: int,
    clause_end: int,
    instrument_start: int,
    instrument_end: int,
    value_start: int,
    value_end: int,
) -> bool:
    if instrument_start < value_end and value_start < instrument_end:
        return True

    prefix = text[max(clause_start, instrument_start - 50) : instrument_start]
    suffix = text[instrument_end : min(clause_end, instrument_end + 80)]
    if re.search(
        r"(?:as\s+)?(?:measured|reported|detected|observed|derived|calculated|"
        r"estimated)\s+(?:by|with|using)\s*(?:the\s+)?$",
        prefix,
        re.IGNORECASE,
    ):
        return True
    return bool(
        re.match(
            r"\s*(?:team\s+)?(?:reports?|measures?|finds?|obtains?|detects?|"
            r"observes?|gives?|light\s+curve\b|spectrum\b|T90\b|T50\b|"
            r"duration\b|fluence\b|flux\b|"
            r"E[ _-]?peak\b|E[ _-]?iso\b|alpha\b|beta\b)",
            suffix,
            re.IGNORECASE,
        )
    )


def _nearest_match(
    pattern: re.Pattern[str],
    fragment: str,
    start: int,
    end: int,
) -> re.Match[str] | None:
    matches = list(pattern.finditer(fragment))
    if not matches:
        return None
    center = (start + end) / 2
    return min(matches, key=lambda match: abs(((match.start() + match.end()) / 2) - center))


def _distance_to_span(token_start: int, token_end: int, span_start: int, span_end: int) -> int:
    if token_end < span_start:
        return span_start - token_end
    if span_end < token_start:
        return token_start - span_end
    return 0


def _join_comment(*parts: str | None) -> str | None:
    values = [part for part in parts if part]
    return "; ".join(values) or None
