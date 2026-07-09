from __future__ import annotations

import re
from dataclasses import dataclass

from skyportal_corpus.canonical.document import CanonicalDocument
from skyportal_corpus.extraction_v2.annotations import EventEvidenceAnnotation


EVENT_IDENTITY_REVIEW_COMMENT = (
    "Event name absent from the subject; verify whether it is an alias of the main "
    "event or a referenced/comparison event."
)
GRB_DAYFRACTION_REVIEW_COMMENT = (
    "Day-fraction format (MASTER/Fermi); it may correspond to a GRB with an official "
    "letter suffix. Verify the mapping to the canonical event."
)
EP_WXT_TRIGGER_REVIEW_COMMENT = (
    "EP-WXT trigger identifier; the annotator must verify the mapping to the canonical "
    "event/source."
)
EP_FXT_TRIGGER_REVIEW_COMMENT = (
    "EP-FXT trigger identifier; the annotator must verify the mapping to the canonical "
    "event/source."
)
EP_DAYFRACTION_REVIEW_COMMENT = (
    "EP day-fraction format; verify the mapping to the canonical event."
)

GRB_DAYFRACTION_RULE_ID = "event_identity.grb_dayfraction"
EP_WXT_TRIGGER_RULE_ID = "event_identity.ep_wxt_trigger"
EP_FXT_TRIGGER_RULE_ID = "event_identity.ep_fxt_trigger"
EP_DAYFRACTION_RULE_ID = "event_identity.ep_dayfraction"
ALWAYS_REVIEW_RULE_IDS = frozenset(
    {
        GRB_DAYFRACTION_RULE_ID,
        EP_WXT_TRIGGER_RULE_ID,
        EP_FXT_TRIGGER_RULE_ID,
        EP_DAYFRACTION_RULE_ID,
    }
)
TABLE_FILTER_RULE_IDS = frozenset({"event_identity.at_sn", "event_identity.ztf"})
_CANONICAL_IDENTITY_PATTERNS = (
    re.compile(r"^GRB \d{6}(?:[A-Z]|\.\d+)?$"),
    re.compile(r"^EP \d{6}(?:[a-z]|\.\d+)$"),
    re.compile(r"^EP-WXT \d{8,}[a-z]{0,4}$"),
    re.compile(r"^EP-FXT \d{8,}[a-z]{0,4}$"),
    re.compile(r"^(?:AT|SN) \d{4}[a-z]{1,4}$"),
    re.compile(r"^ZTF\d{2}[a-z]{7}$"),
    re.compile(r"^IceCube-\d{6}[A-Z]?$"),
    re.compile(r"^GW\d{6}(?:_\d{6})?$"),
    re.compile(r"^S\d{6}[a-z]{1,3}$"),
)


def is_canonical_identity(value: str) -> bool:
    return any(pattern.fullmatch(value) for pattern in _CANONICAL_IDENTITY_PATTERNS)


@dataclass(frozen=True)
class _Rule:
    rule_id: str
    pattern: re.Pattern[str]
    priority: int


@dataclass(frozen=True)
class _Candidate:
    rule: _Rule
    start: int
    end: int
    text: str
    value: str


class EventIdentityExtractor:
    extractor_id = "event-identity-v1"
    extractor_version = "0.1"

    _rules = (
        _Rule(GRB_DAYFRACTION_RULE_ID, re.compile(r"\bGRB\s?\d{6}\.\d+\b", re.IGNORECASE), 0),
        _Rule(EP_WXT_TRIGGER_RULE_ID, re.compile(r"\b(?:EP[\s/\-]?WXT(?:\s+trigger)?[\s:/\-]*\d{8,}|EPW\d{8}[A-Za-z]{1,4})\b", re.IGNORECASE), 1),
        _Rule(EP_FXT_TRIGGER_RULE_ID, re.compile(r"\b(?:EP[\s/\-]?FXT(?:\s+trigger)?[\s:/\-]*\d{8,}|EPF\d{8}[A-Za-z]{1,4})\b", re.IGNORECASE), 2),
        _Rule(EP_DAYFRACTION_RULE_ID, re.compile(r"\bEP\s?\d{6}\.\d+\b", re.IGNORECASE), 3),
        _Rule("event_identity.grb", re.compile(r"\bGRB\s?\d{6}[A-Za-z]?\b", re.IGNORECASE), 4),
        _Rule("event_identity.ep", re.compile(r"\bEP\s?\d{6}[a-z]\b", re.IGNORECASE), 5),
        _Rule("event_identity.at_sn", re.compile(r"\b(AT|SN)\s?2\d{3}[a-z]{2,4}\b", re.IGNORECASE), 6),
        _Rule("event_identity.ztf", re.compile(r"\bZTF\d{2}[a-z]{7}\b", re.IGNORECASE), 7),
        _Rule("event_identity.icecube", re.compile(r"\bIceCube[- ]?\d{6}[A-Z]\b", re.IGNORECASE), 8),
        _Rule("event_identity.gw", re.compile(r"\bGW\d{6}(_\d{6})?\b", re.IGNORECASE), 9),
        _Rule("event_identity.sname", re.compile(r"\bS\d{6}[a-z]{1,3}\b", re.IGNORECASE), 10),
    )

    def extract(self, doc: CanonicalDocument) -> list[EventEvidenceAnnotation]:
        header_text = _header_text(doc)
        header_values = {
            candidate.value
            for candidate in _selected_candidates(header_text, self._rules)
            if candidate.rule.rule_id not in ALWAYS_REVIEW_RULE_IDS
        }

        annotations: list[EventEvidenceAnnotation] = []
        for candidate in _selected_candidates(doc.rendered_text, self._rules):
            is_always_review = candidate.rule.rule_id in ALWAYS_REVIEW_RULE_IDS
            is_in_header = candidate.value in header_values
            needs_review = True if is_always_review else not is_in_header
            annotations.append(
                EventEvidenceAnnotation(
                    circular_id=doc.circular_id,
                    text_sha256=doc.text_sha256,
                    span_start=candidate.start,
                    span_end=candidate.end,
                    text=candidate.text,
                    label="EVENT_IDENTITY",
                    target="event",
                    certainty="confirmed",
                    value=candidate.value,
                    extractor_id=self.extractor_id,
                    extractor_version=self.extractor_version,
                    method="regex",
                    rule_id=candidate.rule.rule_id,
                    confidence=0.5 if needs_review else 1.0,
                    needs_review=needs_review,
                    comment=_review_comment(candidate.rule.rule_id, needs_review),
                )
            )

        annotations.sort(key=lambda annotation: (annotation.span_start, annotation.span_end, annotation.rule_id or ""))
        for annotation in annotations:
            if not annotation.verify(doc.rendered_text):
                raise ValueError(
                    f"Annotation failed offset verification: {annotation.rule_id} "
                    f"{annotation.span_start}-{annotation.span_end}"
                )
        return annotations


def _header_text(doc: CanonicalDocument) -> str:
    for segment in doc.segments:
        if segment.name == "header":
            return segment.text
    return ""


def _selected_candidates(text: str, rules: tuple[_Rule, ...]) -> list[_Candidate]:
    candidates: list[_Candidate] = []
    for rule in rules:
        for match in rule.pattern.finditer(text):
            # Catalog-style circulars often list AT/SN/ZTF transients in table rows.
            # Those rows are listed objects, not the circular-level event identity.
            # Keep this filter limited to AT/SN/ZTF to avoid suppressing GRB/EP/GW
            # identities that may appear near numeric values in normal prose.
            if rule.rule_id in TABLE_FILTER_RULE_IDS and is_in_table_row(text, match.start(), match.end()):
                continue
            candidates.append(
                _Candidate(
                    rule=rule,
                    start=match.start(),
                    end=match.end(),
                    text=text[match.start() : match.end()],
                    value=_normalize_event_identity(match.group(0), rule.rule_id),
                )
            )
    return _select_non_overlapping(candidates)


def is_in_table_row(text: str, span_start: int, span_end: int) -> bool:
    del span_end
    line_start = text.rfind("\n", 0, span_start) + 1
    line_end = text.find("\n", span_start)
    if line_end == -1:
        line_end = len(text)
    line = text[line_start:line_end]
    stripped = line.strip()
    if not stripped:
        return False

    # Strong table-row signals: pipe-delimited rows, many numeric columns, or a
    # short leading row token followed by several numeric fields. This is a
    # conservative heuristic for catalog/photometry rows in GCN circulars.
    if line.count("|") >= 2:
        return True

    numeric_fields = re.findall(
        r"(?<![A-Za-z])[-+]?(?:\d+\.\d+|\d+)(?:[eE][-+]?\d+)?(?![A-Za-z])",
        line,
    )
    if len(numeric_fields) < 3:
        return False

    columnish_separators = bool(re.search(r"\d\s{2,}[-+]?\d", line)) or "|" in line
    fields = [field for field in re.split(r"\s{2,}|\|", stripped) if field.strip()]
    starts_like_data_row = bool(re.match(r"^\|?\s*[A-Za-z0-9_.+-]{1,20}(?:\s{2,}|\s*\|)", line))
    return columnish_separators or (starts_like_data_row and len(fields) >= 4)


def _select_non_overlapping(candidates: list[_Candidate]) -> list[_Candidate]:
    selected: list[_Candidate] = []
    for candidate in sorted(
        candidates,
        key=lambda item: (-(item.end - item.start), item.rule.priority, item.start, item.end),
    ):
        if any(_overlaps(candidate, existing) for existing in selected):
            continue
        selected.append(candidate)
    return sorted(selected, key=lambda item: (item.start, item.end, item.rule.rule_id))


def _overlaps(left: _Candidate, right: _Candidate) -> bool:
    return left.start < right.end and right.start < left.end


def _review_comment(rule_id: str, needs_review: bool) -> str | None:
    if not needs_review:
        return None
    if rule_id == GRB_DAYFRACTION_RULE_ID:
        return GRB_DAYFRACTION_REVIEW_COMMENT
    if rule_id == EP_WXT_TRIGGER_RULE_ID:
        return EP_WXT_TRIGGER_REVIEW_COMMENT
    if rule_id == EP_FXT_TRIGGER_RULE_ID:
        return EP_FXT_TRIGGER_REVIEW_COMMENT
    if rule_id == EP_DAYFRACTION_RULE_ID:
        return EP_DAYFRACTION_REVIEW_COMMENT
    return EVENT_IDENTITY_REVIEW_COMMENT


def _normalize_event_identity(value: str, rule_id: str) -> str:
    if rule_id == GRB_DAYFRACTION_RULE_ID:
        compact = re.sub(r"\s+", "", value.strip()).upper()
        return f"GRB {compact[len('GRB'):]}"
    if rule_id == EP_DAYFRACTION_RULE_ID:
        compact = re.sub(r"\s+", "", value.strip()).upper()
        return f"EP {compact[len('EP'):]}"
    if rule_id == EP_WXT_TRIGGER_RULE_ID:
        return _normalize_ep_instrument_identifier(value, "WXT")
    if rule_id == EP_FXT_TRIGGER_RULE_ID:
        return _normalize_ep_instrument_identifier(value, "FXT")

    normalizers = {
        "event_identity.grb": _normalize_grb,
        "event_identity.ep": _normalize_ep,
        "event_identity.at_sn": _normalize_at_sn,
        "event_identity.ztf": _normalize_ztf,
        "event_identity.icecube": _normalize_icecube,
        "event_identity.gw": _normalize_gw,
        "event_identity.sname": _normalize_sname,
    }
    normalizer = normalizers.get(rule_id)
    return normalizer(value) if normalizer is not None else value.strip()


def _normalize_ep_instrument_identifier(value: str, instrument: str) -> str:
    match = re.search(r"(?P<identifier>\d{8,}[A-Za-z]{0,4})\b", value, re.IGNORECASE)
    if match is None:
        return value.strip()
    identifier = match.group("identifier")
    normalized_identifier = identifier[:8] + identifier[8:].lower()
    return f"EP-{instrument} {normalized_identifier}"


def _normalize_grb(value: str) -> str:
    match = re.fullmatch(r"\s*GRB\s?(?P<digits>\d{6})(?P<suffix>[A-Za-z]?)\s*", value, re.IGNORECASE)
    if match is None:
        return value.strip()
    return f"GRB {match.group('digits')}{match.group('suffix').upper()}"


def _normalize_ep(value: str) -> str:
    match = re.fullmatch(r"\s*EP\s?(?P<digits>\d{6})(?P<suffix>[A-Za-z])\s*", value, re.IGNORECASE)
    if match is None:
        return value.strip()
    return f"EP {match.group('digits')}{match.group('suffix').lower()}"


def _normalize_at_sn(value: str) -> str:
    match = re.fullmatch(
        r"\s*(?P<prefix>AT|SN)\s?(?P<year>2\d{3})(?P<suffix>[A-Za-z]{2,4})\s*",
        value,
        re.IGNORECASE,
    )
    if match is None:
        return value.strip()
    return f"{match.group('prefix').upper()} {match.group('year')}{match.group('suffix').lower()}"


def _normalize_ztf(value: str) -> str:
    match = re.fullmatch(r"\s*ZTF(?P<year>\d{2})(?P<suffix>[A-Za-z]{7})\s*", value, re.IGNORECASE)
    if match is None:
        return value.strip()
    return f"ZTF{match.group('year')}{match.group('suffix').lower()}"


def _normalize_icecube(value: str) -> str:
    match = re.fullmatch(r"\s*IceCube[- ]?(?P<digits>\d{6})(?P<suffix>[A-Za-z])\s*", value, re.IGNORECASE)
    if match is None:
        return value.strip()
    return f"IceCube-{match.group('digits')}{match.group('suffix').upper()}"


def _normalize_gw(value: str) -> str:
    compact = re.sub(r"\s+", "", value.strip()).upper()
    return compact


def _normalize_sname(value: str) -> str:
    match = re.fullmatch(r"\s*S(?P<digits>\d{6})(?P<suffix>[A-Za-z]{1,3})\s*", value, re.IGNORECASE)
    if match is None:
        return value.strip()
    return f"S{match.group('digits')}{match.group('suffix').lower()}"
