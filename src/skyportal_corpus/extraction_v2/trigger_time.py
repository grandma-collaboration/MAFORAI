from __future__ import annotations

import re
from dataclasses import dataclass

from skyportal_corpus.canonical.document import CanonicalDocument
from skyportal_corpus.extraction_v2.annotations import EventEvidenceAnnotation


TRIGGER_TIME_REVIEW_COMMENT = (
    "Multiple times have trigger context; the annotator must choose the correct one."
)
TRIGGER_TIME_MISSING_DATE_REVIEW_COMMENT = (
    "Trigger time without an adjacent date in the text; the annotator must complete "
    "the date (for example, from the event name or context)."
)

_TRIGGER_CONTEXT_RE = re.compile(
    r"\b(?:trigger(?:ed)?|T0|burst onset|onset of|GBM trigger|BAT trigger)\b"
    r"|\bdetected\b.{0,80}\bat\b",
    re.IGNORECASE | re.DOTALL,
)
_COORDINATE_PREFIX_RE = re.compile(
    r"(?:R\.?\s*A\.?|RA|Dec\.?|DEC|Decl)\s*[=:]?\s*[+\-]?\s*$",
    re.IGNORECASE,
)
_AFTER_TRIGGER_PREFIX_RE = re.compile(
    r"(\d+(\.\d+)?\s*(s|sec|seconds|min|minutes|min\.|h|hr|hrs|hours)\s+)?"
    r"after\s+(the\s+)?[\w\-/ ]{0,25}trigger(\s+time)?\s+at\s+"
    r"(\d{4}-\d{2}-\d{2}\s+)?$",
    re.IGNORECASE,
)
_OBSERVATION_PREFIX_RE = re.compile(
    r"\b("
    r"began observing|started observing|started observations|started the observation|"
    r"observations started|we started|started on|we observed|we observed the burst|"
    r"observed the|observation was done|exposures were obtained|carried out from|"
    r"scanned|starting at|starting on"
    r")\b",
    re.IGNORECASE,
)
_RELATIVE_AFTER_SUFFIX_RE = re.compile(
    r"\(\s*t0\s*\+"
    r"|(?:i\.e\.,\s*)?(?:about\s*)?(?:~\s*)?"
    r"\d+(\.\d+)?\s*(s|sec|seconds|min|minutes|min\.|h|hr|hrs|hours)\s+"
    r"after\s+(?:the\s+)?(?:[\w\-/]+\s+){0,4}?trigger",
    re.IGNORECASE,
)
_ISO_DATE_RE = r"\d{4}-\d{2}-\d{2}"
_DAY_MONTH_DATE_RE = r"\d{1,2}\s+[A-Z][a-z]{2,9}\.?\s+\d{4}"
_MONTH_DAY_DATE_RE = r"[A-Z][a-z]{2,9}\.?\s+\d{1,2}(?:st|nd|rd|th)?,\s+\d{4}"
_DATE_RE = rf"(?:{_ISO_DATE_RE}|{_DAY_MONTH_DATE_RE}|{_MONTH_DAY_DATE_RE})"
_DATE_TIME_CONNECTOR_RE = r"(?:(?:\s+|,\s*)|\bon\b|\bat\b)*"

_MONTHS = {
    "jan": "01",
    "january": "01",
    "feb": "02",
    "february": "02",
    "mar": "03",
    "march": "03",
    "apr": "04",
    "april": "04",
    "may": "05",
    "jun": "06",
    "june": "06",
    "jul": "07",
    "july": "07",
    "aug": "08",
    "august": "08",
    "sep": "09",
    "sept": "09",
    "september": "09",
    "oct": "10",
    "october": "10",
    "nov": "11",
    "november": "11",
    "dec": "12",
    "december": "12",
}


@dataclass(frozen=True)
class _Rule:
    rule_id: str
    pattern: re.Pattern[str]
    priority: int


@dataclass(frozen=True)
class DateMatch:
    span_start: int
    span_end: int
    text: str


@dataclass(frozen=True)
class TimeCandidate:
    span_start: int
    span_end: int
    time_start: int
    time_end: int
    raw_time: str
    rule_id: str
    priority: int


class TriggerTimeExtractor:
    extractor_id = "trigger-time-v1"
    extractor_version = "0.1"

    _rules = (
        _Rule(
            "trigger_time.t0_explicit",
            re.compile(
                r"\bT0\s*[=:]\s*\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?",
                re.IGNORECASE,
            ),
            0,
        ),
        _Rule(
            "trigger_time.iso",
            re.compile(
                r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(\s?(UTC|UT|Z))?\b",
                re.IGNORECASE,
            ),
            1,
        ),
        _Rule(
            "trigger_time.date_before_clock",
            re.compile(
                r"\b(?:on\s+)?"
                rf"{_DATE_RE}"
                rf"{_DATE_TIME_CONNECTOR_RE}"
                r"\d{1,2}:\d{2}:\d{2}(?:\.\d+)?\s?(?:UTC|UT)?\b",
                re.IGNORECASE,
            ),
            2,
        ),
        _Rule(
            "trigger_time.clock_on_date",
            re.compile(
                r"\b\d{1,2}:\d{2}:\d{2}(\.\d+)?\s?(UTC|UT)?"
                rf"{_DATE_TIME_CONNECTOR_RE}{_DATE_RE}\b",
                re.IGNORECASE,
            ),
            3,
        ),
        _Rule(
            "trigger_time.clock",
            re.compile(r"\b\d{1,2}:\d{2}:\d{2}(\.\d+)?\s?(UTC|UT)?\b", re.IGNORECASE),
            4,
        ),
        _Rule("trigger_time.mjd", re.compile(r"\bMJD\s?\d{5}(\.\d+)?\b", re.IGNORECASE), 5),
    )

    def extract(self, doc: CanonicalDocument) -> list[EventEvidenceAnnotation]:
        accepted: list[tuple[TimeCandidate, DateMatch | None, str]] = []
        for candidate in resolve_overlaps(find_time_candidates(doc.rendered_text)):
            if _is_in_header(doc, candidate.span_start, candidate.span_end):
                continue
            if is_observation_context(doc.rendered_text, candidate.span_start, candidate.span_end):
                continue
            if not has_trigger_context(doc.rendered_text, candidate.span_start, candidate.span_end):
                continue

            date_match = find_adjacent_date(doc.rendered_text, candidate.time_start, candidate.time_end)
            value = normalize_to_iso(candidate.raw_time, date_match)
            accepted.append((candidate, date_match, value))

        has_multiple_candidates = len(accepted) > 1
        annotations = [
            EventEvidenceAnnotation(
                circular_id=doc.circular_id,
                text_sha256=doc.text_sha256,
                span_start=candidate.span_start,
                span_end=candidate.span_end,
                text=doc.rendered_text[candidate.span_start : candidate.span_end],
                label="TRIGGER_TIME",
                target="event",
                certainty="confirmed",
                value=value,
                extractor_id=self.extractor_id,
                extractor_version=self.extractor_version,
                method="regex",
                rule_id=candidate.rule_id,
                confidence=0.5 if date_match is None else 1.0,
                needs_review=has_multiple_candidates or date_match is None,
                comment=_review_comment(date_match, has_multiple_candidates),
            )
            for candidate, date_match, value in accepted
        ]

        for annotation in annotations:
            if not annotation.verify(doc.rendered_text):
                raise ValueError(
                    f"Annotation failed offset verification: {annotation.rule_id} "
                    f"{annotation.span_start}-{annotation.span_end}"
                )
        return annotations


def find_time_candidates(text: str) -> list[TimeCandidate]:
    candidates: list[TimeCandidate] = []
    for rule in TriggerTimeExtractor._rules:
        for match in rule.pattern.finditer(text):
            raw = match.group(0)
            if rule.rule_id in {"trigger_time.date_before_clock", "trigger_time.clock_on_date"} and not _has_valid_date_time_connector(raw):
                continue
            if not _has_valid_clock_range(rule.rule_id, raw):
                continue

            time_span = _time_span(match, rule.rule_id)
            if time_span is None:
                continue
            time_start, time_end = time_span
            candidates.append(
                TimeCandidate(
                    span_start=match.start(),
                    span_end=match.end(),
                    time_start=time_start,
                    time_end=time_end,
                    raw_time=text[time_start:time_end],
                    rule_id=rule.rule_id,
                    priority=rule.priority,
                )
            )
    return candidates


def is_observation_context(text: str, span_start: int, span_end: int) -> bool:
    if _has_coordinate_prefix(text, span_start):
        return True

    previous_45 = text[max(0, span_start - 45) : span_start]
    if _AFTER_TRIGGER_PREFIX_RE.search(previous_45):
        return True

    previous_120 = text[max(0, span_start - 120) : span_start]
    if _OBSERVATION_PREFIX_RE.search(previous_120):
        return True

    next_80 = text[span_end : min(len(text), span_end + 80)]
    return bool(_RELATIVE_AFTER_SUFFIX_RE.search(next_80))


def has_trigger_context(text: str, span_start: int, span_end: int) -> bool:
    window_start = max(0, span_start - 80)
    window_end = min(len(text), span_end + 80)
    return bool(_TRIGGER_CONTEXT_RE.search(text[window_start:window_end]))


def find_adjacent_date(text: str, time_span_start: int, time_span_end: int) -> DateMatch | None:
    if _is_mjd_text(text[time_span_start:time_span_end]):
        return DateMatch(time_span_start, time_span_end, text[time_span_start:time_span_end])

    before_window_start = max(0, time_span_start - 80)
    before = text[before_window_start:time_span_start]
    before_matches = [
        (before_window_start + match.start(), before_window_start + match.end())
        for match in _date_matches(before)
    ]
    for date_start, date_end in sorted(before_matches, key=lambda item: item[1], reverse=True):
        if _is_contiguous_date_time_connector(text[date_end:time_span_start]):
            return DateMatch(date_start, date_end, text[date_start:date_end])

    after_window_end = min(len(text), time_span_end + 80)
    after = text[time_span_end:after_window_end]
    after_matches = [
        (time_span_end + match.start(), time_span_end + match.end())
        for match in _date_matches(after)
    ]
    for date_start, date_end in sorted(after_matches, key=lambda item: item[0]):
        if _is_contiguous_date_time_connector(text[time_span_end:date_start]):
            return DateMatch(date_start, date_end, text[date_start:date_end])

    return None


def normalize_to_iso(raw_time: str, date_match: DateMatch | None) -> str:
    if _is_mjd_text(raw_time):
        match = re.search(r"\bMJD\s?(\d{5}(\.\d+)?)\b", raw_time, re.IGNORECASE)
        return f"MJD {match.group(1)}" if match else raw_time.strip()

    if date_match is None:
        return raw_time.strip()

    try:
        date_parts = _date_parts(date_match.text)
        if date_parts is None:
            return raw_time.strip()
        time_match = _clock_match(raw_time)
        if time_match is None:
            return raw_time.strip()
        year, month, day = date_parts
        hour, minute, second = time_match.group("time").split(":", 2)
        return f"{year}-{month}-{day}T{int(hour):02d}:{minute}:{second}"
    except (TypeError, ValueError):
        return raw_time.strip()


def resolve_overlaps(candidates: list[TimeCandidate]) -> list[TimeCandidate]:
    selected: list[TimeCandidate] = []
    for candidate in sorted(
        candidates,
        key=lambda item: (-(item.span_end - item.span_start), item.priority, item.span_start, item.span_end),
    ):
        if any(_overlaps(candidate, existing) for existing in selected):
            continue
        selected.append(candidate)
    return sorted(selected, key=lambda item: (item.span_start, item.span_end, item.rule_id))


def _is_in_header(doc: CanonicalDocument, start: int, end: int) -> bool:
    for segment in doc.segments:
        if segment.name == "header":
            return start < segment.end and end > segment.start
    return False


def _has_valid_clock_range(rule_id: str, text: str) -> bool:
    if rule_id == "trigger_time.mjd":
        return True

    match = re.search(
        r"(?P<hour>\d{1,2}):(?P<minute>\d{2})(?::(?P<second>\d{2}(?:\.\d+)?))?",
        text,
    )
    if match is None:
        return False

    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    second = float(match.group("second") or "0")
    return 0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second < 60


def _has_coordinate_prefix(rendered_text: str, start: int) -> bool:
    previous_text = rendered_text[max(0, start - 15) : start]
    return bool(_COORDINATE_PREFIX_RE.search(previous_text))


def _overlaps(left: TimeCandidate, right: TimeCandidate) -> bool:
    return left.span_start < right.span_end and right.span_start < left.span_end


def _time_span(match: re.Match[str], rule_id: str) -> tuple[int, int] | None:
    if rule_id == "trigger_time.mjd":
        return match.start(), match.end()

    clock_match = _clock_match(match.group(0))
    if clock_match is None:
        return None
    return match.start() + clock_match.start(), match.start() + clock_match.end()


def _clock_match(text: str) -> re.Match[str] | None:
    return re.search(
        r"(?P<time>\d{1,2}:\d{2}:\d{2}(?:\.\d+)?)(?:\s?(?:UTC|UT))?",
        text,
        re.IGNORECASE,
    )


def _date_matches(text: str) -> list[re.Match[str]]:
    return [
        match
        for pattern in (
            r"\d{4}-\d{2}-\d{2}",
            r"\d{1,2}\s+[A-Z][a-z]{2,9}\.?\s+\d{4}",
            r"[A-Z][a-z]{2,9}\.?\s+\d{1,2}(?:st|nd|rd|th)?,\s+\d{4}",
        )
        for match in re.finditer(pattern, text, re.IGNORECASE)
    ]


def _is_mjd_text(text: str) -> bool:
    return bool(re.fullmatch(r"\s*MJD\s?\d{5}(?:\.\d+)?\s*", text, re.IGNORECASE))


def _has_valid_date_time_connector(text: str) -> bool:
    if "\n" in text and re.search(r"\n[ \t]*\n", text):
        return False

    date_span = _date_span(text)
    time_match = re.search(r"\d{1,2}:\d{2}:\d{2}(?:\.\d+)?(?:\s?(?:UTC|UT))?", text, re.IGNORECASE)
    if date_span is None or time_match is None:
        return True

    if date_span[1] <= time_match.start():
        between = text[date_span[1] : time_match.start()]
    elif time_match.end() <= date_span[0]:
        between = text[time_match.end() : date_span[0]]
    else:
        return True

    return _is_contiguous_date_time_connector(between)


def _is_contiguous_date_time_connector(text: str) -> bool:
    if text == "T":
        return True
    if re.search(r"\n[ \t]*\n", text):
        return False
    if re.search(r"\.\s", text):
        return False
    return bool(re.fullmatch(_DATE_TIME_CONNECTOR_RE, text, re.IGNORECASE))


def _review_comment(date_match: DateMatch | None, has_multiple_candidates: bool) -> str | None:
    if has_multiple_candidates:
        return TRIGGER_TIME_REVIEW_COMMENT
    if date_match is None:
        return TRIGGER_TIME_MISSING_DATE_REVIEW_COMMENT
    return None


def _date_parts(text: str) -> tuple[str, str, str] | None:
    iso_date = re.search(r"(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})", text)
    if iso_date is not None:
        return iso_date.group("year"), iso_date.group("month"), iso_date.group("day")

    day_month_date = re.search(
        r"(?P<day>\d{1,2})\s+(?P<month>[A-Z][a-z]{2,9})\.?\s+(?P<year>\d{4})",
        text,
        re.IGNORECASE,
    )
    if day_month_date is not None:
        month = _MONTHS.get(day_month_date.group("month").lower().rstrip("."))
        if month is None:
            return None
        return day_month_date.group("year"), month, f"{int(day_month_date.group('day')):02d}"

    month_day_date = re.search(
        r"(?P<month>[A-Z][a-z]{2,9})\.?\s+"
        r"(?P<day>\d{1,2})(?:st|nd|rd|th)?,\s+(?P<year>\d{4})",
        text,
        re.IGNORECASE,
    )
    if month_day_date is None:
        return None

    month = _MONTHS.get(month_day_date.group("month").lower().rstrip("."))
    if month is None:
        return None
    return month_day_date.group("year"), month, f"{int(month_day_date.group('day')):02d}"


def _date_span(text: str) -> tuple[int, int] | None:
    for pattern in (
        r"\d{4}-\d{2}-\d{2}",
        r"\d{1,2}\s+[A-Z][a-z]{2,9}\.?\s+\d{4}",
        r"[A-Z][a-z]{2,9}\.?\s+\d{1,2}(?:st|nd|rd|th)?,\s+\d{4}",
    ):
        match = re.search(pattern, text, re.IGNORECASE)
        if match is not None:
            return match.start(), match.end()
    return None
