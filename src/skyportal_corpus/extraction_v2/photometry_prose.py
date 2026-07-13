from __future__ import annotations

import re
from dataclasses import dataclass

from skyportal_corpus.canonical.document import CanonicalDocument
from skyportal_corpus.extraction_v2.photometry_annotations import (
    PhotometricMeasurementAnnotation,
)
from skyportal_corpus.extraction_v2.photometry_tables import FILTER_VALUES


_BAND_VALUES = tuple(sorted(FILTER_VALUES | {"VT_B", "VT_R", "o"}, key=len, reverse=True))
_BAND_PATTERN = "|".join(re.escape(value) for value in _BAND_VALUES)
_NUMBER = r"\d{1,2}(?:\.\d+)?"
_ERROR = r"\d+(?:\.\d+)?"
_SYSTEM = r"\(\s*(?:AB|Vega)(?:\s+mag)?\s*\)"
_ENUMERATED_LIMIT_RE = re.compile(
    rf"\b(?P<sigma>{_ERROR})[\s-]*sigma\s+upper\s+limits?\s+of\s+"
    rf"(?P<values>[<>]\s*~?\s*{_NUMBER}(?:\s*(?:,|and)\s*"
    rf"[<>]\s*~?\s*{_NUMBER})+)\s*(?P<system>AB|Vega)?\s*mag\b",
    re.IGNORECASE,
)
_ENUMERATED_LIMIT_VALUE_RE = re.compile(rf"[<>]\s*~?\s*(?P<mag>{_NUMBER})")


@dataclass(frozen=True)
class ProseMagnitudeCandidate:
    span_start: int
    span_end: int
    raw: str
    rule_id: str
    measurement_type: str
    magnitude_or_limit: str
    magnitude_error: str | None = None
    limit_sigma: str | None = None
    photometric_band: str | None = None
    photometric_system: str | None = None
    cited_from_other_gcn: bool = False


@dataclass(frozen=True)
class CompanionFields:
    photometric_band: str | None
    photometric_system: str
    obs_time_raw: str | None
    obs_time_type: str | None
    obs_time_reference: str | None
    exposure_time_raw: str | None
    instrument: str | None
    ambiguous_time: bool
    ambiguous_exposure: bool


@dataclass(frozen=True)
class _Pattern:
    rule_id: str
    regex: re.Pattern[str]
    measurement_type: str


@dataclass(frozen=True)
class _FieldMatch:
    start: int
    end: int
    raw: str
    kind: str


_PATTERNS = (
    _Pattern(
        "photometry_prose.prose_sigma_depth",
        re.compile(
            rf"\bdown\s+to\s+(?:a\s+)?(?P<sigma>{_ERROR})[\s-]*sigma\s+"
            rf"depth\s+of\s*[<>]\s*~?\s*(?P<mag>{_NUMBER})\s*"
            rf"(?P<system_word>AB|Vega)?\s*mag\b",
            re.IGNORECASE,
        ),
        "upper_limit",
    ),
    _Pattern(
        "photometry_prose.prose_brightness",
        re.compile(
            rf"\b(?:with\s+the\s+)?brightness\s+of\s+"
            rf"(?P<band>{_BAND_PATTERN})\s*=\s*~?\s*(?P<mag>{_NUMBER})"
            rf"(?:\s*(?:\+/-|±)\s*(?P<err>{_ERROR}))?\s*(?:mag(?:nitudes?)?)?"
            rf"\s*(?P<system>{_SYSTEM})?",
            re.IGNORECASE,
        ),
        "detection",
    ),
    _Pattern(
        "photometry_prose.prose_limit_gt",
        re.compile(
            rf"(?:\b(?:to\s+(?:a\s+)?\d+(?:\.\d+)?-sigma\s+)?"
            rf"(?:limiting\s+)?(?:AB|Vega)?\s*magnitude\s+of\s+)?"
            rf"\b(?P<band>{_BAND_PATTERN})\s*[<>]\s*~?\s*(?P<mag>{_NUMBER})"
            rf"\s*(?:mag(?:nitudes?)?)?\s*(?P<system>{_SYSTEM})?",
            re.IGNORECASE,
        ),
        "upper_limit",
    ),
    _Pattern(
        "photometry_prose.prose_limit_upto",
        re.compile(
            rf"\b(?P<limit_phrase>up\s+to|down\s+to|upper\s+limit\s+(?:of|up\s+to))"
            rf"\s*~?\s*(?P<mag>{_NUMBER})\s*(?:th)?\s*(?:mag|magnitude)\b",
            re.IGNORECASE,
        ),
        "upper_limit",
    ),
    _Pattern(
        "photometry_prose.prose_magnitude_of",
        re.compile(
            rf"\b(?:preliminary\s+)?magnitude\s+of\s+"
            rf"(?:(?P<band_before>{_BAND_PATTERN})\s*=\s*)?"
            rf"(?P<mag>{_NUMBER})(?:\s*(?:\+/-|±)\s*(?P<err>{_ERROR}))?"
            rf"\s*(?:mag(?:nitudes?)?)?(?:\s+in\s+(?:the\s+)?(?P<band_after>{_BAND_PATTERN})(?:\s+band)?)?"
            rf"\s*(?P<system>{_SYSTEM})?",
            re.IGNORECASE,
        ),
        "detection",
    ),
    _Pattern(
        "photometry_prose.prose_band_eq",
        re.compile(
            rf"(?<![\w/])(?:m[_\s]?)?(?P<band>{_BAND_PATTERN})\s*=\s*~?\s*"
            rf"(?P<mag>{_NUMBER})(?:\s*(?:\+/-|±)\s*(?P<err>{_ERROR}))?"
            rf"\s*(?:mag(?:nitudes?)?)?\s*(?P<system>{_SYSTEM})?",
            re.IGNORECASE,
        ),
        "detection",
    ),
)

_OPTICAL_WORD_RE = re.compile(
    r"\b(?:optical|photometr(?:y|ic)|magnitudes?|afterglow\s+(?:was\s+)?detected)\b",
    re.IGNORECASE,
)
_OPTICAL_TELESCOPE_RE = re.compile(
    r"\b(?:UVOT|GOTO|MASTER|GRANDMA|KNC|GTC|VLT|Gemini|Keck|NOT|LCOGT|"
    r"Liverpool Telescope|Xinglong|TRAPPIST|REM|TAROT|COLIBRI|SVOM/VT)\b",
    re.IGNORECASE,
)
_EXPLICIT_BAND_RE = re.compile(
    rf"(?<!\w)(?:{_BAND_PATTERN})(?:\s*[- ]?band|\s*[=<>])|"
    rf"\b(?:band|filter)\s+(?:{_BAND_PATTERN})\b|"
    rf"\bin\s+(?:the\s+)?(?:{_BAND_PATTERN})\s+(?:band|filter)\b",
    re.IGNORECASE,
)
_NON_OPTICAL_RE = re.compile(
    r"count\s*rate|ct\s*s\^?-?1|erg\s*/?\s*cm|\bkeV\b|\bMeV\b|\bGeV\b|"
    r"\bT90\b|\bfluence\b|flux\s+density|\b[um]?Jy\b|\bneutrino",
    re.IGNORECASE,
)

_CATALOG_GATE_RE = re.compile(
    r"complete\s+to|completeness|typically\s+complete|list\s+of\s+sources|"
    r"catalog(?:ue)?\s+is\s+complete",
    re.IGNORECASE,
)
_CALIBRATION_GATE_RE = re.compile(
    r"calibrated\s+(?:against|using)|calibration\s+was\s+performed|"
    r"reference\s+stars|comparison\s+stars|PS1\s+stars|PanSTARRS\s+catalog|"
    r"ATLAS-REFCAT2|Gaia\s+DR2\s+cat|2MASS\s+stars|USNO|SDSS\s+catalogue",
    re.IGNORECASE,
)
_EXTINCTION_RE = re.compile(
    r"E\s*\(\s*B\s*-\s*V\s*\)|extinction\s+of|corrected\s+for[^.\n]{0,30}extinction",
    re.IGNORECASE,
)
_NON_PHOTOMETRIC_UNIT_RE = re.compile(
    r"\b(?:keV|MeV|GeV|erg|ct\s*/?\s*s|uJy|mJy|Jy)\b",
    re.IGNORECASE,
)
_PROSE_LIMIT_SIGMA_RE = re.compile(
    r"\b(?P<sigma>\d+(?:\.\d+)?)[\s-]*sigma\b[^.!?]{0,60}"
    r"\b(?:upper\s+)?(?:limit(?:ing)?|depth)\b",
    re.IGNORECASE,
)
_SEARCH_DEPTH_RE = re.compile(
    r"\b(?:average\s+\d+(?:\.\d+)?[\s-]*sigma\s+depth|depth\s+of\s+the\s+search|"
    r"images?\s+were\s+taken[^.!?]{0,100}\bdepth)\b",
    re.IGNORECASE,
)
_COORDINATE_CONTEXT_RE = re.compile(
    r"galactic\s+latitude[^.\n]{0,30}\bb\s*=|"
    r"galactic\s+longitude[^.\n]{0,30}\bl\s*=|"
    r"\b[bl]\s*=\s*[+-]?\d+(?:\.\d+)?\s*deg|"
    r"\bR\s*=\s*\d+(?:\.\d+)?\s*\)\s*errorbox",
    re.IGNORECASE,
)
_REDSHIFT_CONTEXT_RE = re.compile(
    r"\b(?:redshift|spectrum|emission\s+lines?|absorption|host\s+galaxy\s+at|"
    r"galaxy\s+at)\b",
    re.IGNORECASE,
)
_DIRECT_CITATION_SUFFIX_RE = re.compile(
    r"^\s*[,;]?\s*(?:as\s+)?(?:reported|published|cited)\s+(?:by\s+)?"
    r"[^.\n]{0,80}(?:\bGCN\b|\bet\s+al\.)",
    re.IGNORECASE,
)
_DIRECT_CITATION_PREFIX_RE = re.compile(
    r"(?:reported|published|cited)\s+(?:by\s+)?[^.\n]{0,60}"
    r"(?:\bGCN\b|\bet\s+al\.)[^.\n]{0,40}$",
    re.IGNORECASE,
)
_TENTATIVE_RE = re.compile(r"\b(?:preliminary|marginally\s+detected|possible)\b|~", re.IGNORECASE)
_COUNTERPART_RE = re.compile(
    r"\b(?:afterglow|counterpart|optical\s+transient|transient|\bOT\b)\b",
    re.IGNORECASE,
)
_OBSERVATION_TIME_CONTEXT_RE = re.compile(
    r"observations?\s+(?:started|began)|we\s+observed|t_?mid\s*-\s*T0\s*=|"
    r"exposures?[^.\n]{0,50}starting\s+at|images?[^.\n]{0,50}\bat\b",
    re.IGNORECASE,
)
_TRIGGER_TIME_BEFORE_RE = re.compile(
    r"(?:trigger(?:ed)?|burst\s+onset|\bT0)\s*(?:time\s*)?(?:at|=)?\s*$",
    re.IGNORECASE,
)
_TRIGGER_TIME_AFTER_RE = re.compile(
    r"^\s*[,;]?\s*(?:the\s+)?[^.\n]{0,45}\b(?:triggered|burst\s+onset)\b",
    re.IGNORECASE,
)

_TIME_PATTERNS = (
    (
        "relative_to_trigger",
        re.compile(
            r"\(?\s*t_?mid\s*-\s*T0\s*=\s*\d+(?:\.\d+)?\s*"
            r"(?:s|sec(?:onds?)?|min(?:utes?)?|h|hr|hours?|days?)\s*\)?",
            re.IGNORECASE,
        ),
    ),
    (
        "relative_to_trigger",
        re.compile(
            r"\b\d+(?:\.\d+)?\s*(?:s|sec(?:onds?)?|min(?:utes?)?|h|hr|hours?|days?)"
            r"\s+after\s+(?:the\s+)?(?:GRB\s+)?trigger\b",
            re.IGNORECASE,
        ),
    ),
    (
        "utc_datetime",
        re.compile(
            r"\bstart(?:ed|ing)\s+at\s+\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?\s*(?:UT|UTC)?"
            r"\s+on\s+\d{4}-\d{2}-\d{2}\b",
            re.IGNORECASE,
        ),
    ),
    (
        "utc_datetime",
        re.compile(
            r"\bon\s+(?:January|February|March|April|May|June|July|August|September|"
            r"October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
            r"\s+\d{1,2},?\s+\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?"
            r"(?:--\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?)?\s*(?:UT|UTC)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "utc_datetime",
        re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?\s*(?:UT|UTC)?\b"),
    ),
    (
        "utc_datetime",
        re.compile(r"\bat\s+\d{1,2}:\d{2}:\d{2}(?:\.\d+)?\s*(?:UT|UTC)\b", re.IGNORECASE),
    ),
)

_EXPOSURE_PATTERNS = (
    re.compile(r"\b\d+\s*[xX*]\s*\d+(?:\.\d+)?\s*(?:s|sec(?:onds?)?)\s*(?:exposures?)?\b", re.IGNORECASE),
    re.compile(
        r"\b\d+\s+exposures?\s+of\s+\d+(?:\.\d+)?\s*s\s+and\s+"
        r"\d+\s+exposures?\s+of\s+\d+(?:\.\d+)?\s*s\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b\d+\s+images?\s+of\s+\d+(?:\.\d+)?\s*sec(?:onds?)?\s+each\b", re.IGNORECASE),
    re.compile(r"\b\d+\s+exposures?\s+of\s+\d+(?:\.\d+)?\s*s\b", re.IGNORECASE),
)

_INSTRUMENT_PATTERNS = (
    re.compile(r"\bSwift/?UVOT\b", re.IGNORECASE),
    re.compile(r"\bUVOT\b", re.IGNORECASE),
    re.compile(r"\b(?:GOTO|MASTER|GRANDMA|KNC|GTC|VLT|Gemini|Keck|LCOGT|"
               r"Liverpool Telescope|Xinglong|TRAPPIST|REM|TAROT|COLIBRI|SVOM/VT)\b", re.IGNORECASE),
    re.compile(r"\bNOT\b"),
)


def is_optical_circular(text: str) -> bool:
    """Return whether a circular has credible optical/NIR content.

    High-energy, radio, and neutrino circulars frequently contain numbers that
    resemble magnitudes. They are rejected when no positive optical signal is
    present. Explicit optical vocabulary, telescope names, or a band used in a
    photometric construction is required; isolated one-letter tokens do not count.
    """

    has_optical_signal = bool(
        _OPTICAL_WORD_RE.search(text)
        or _OPTICAL_TELESCOPE_RE.search(text)
        or _EXPLICIT_BAND_RE.search(text)
    )
    if not has_optical_signal and _NON_OPTICAL_RE.search(text):
        return False
    return has_optical_signal


def find_prose_magnitudes(text: str) -> list[ProseMagnitudeCandidate]:
    candidates = _find_enumerated_upper_limits(text)
    for pattern in _PATTERNS:
        for match in pattern.regex.finditer(text):
            if _should_discard_candidate(text, match.start(), match.end()):
                continue
            band = match.groupdict().get("band") or match.groupdict().get("band_before") or match.groupdict().get("band_after")
            magnitude = match.group("mag")
            # Unlike table parsing, prose expressions outside the optical range
            # are discarded. In prose they are overwhelmingly colors, redshifts,
            # or unrelated scalar parameters rather than malformed magnitudes.
            if not 5 <= float(magnitude) <= 30:
                continue
            if _is_non_photometric_band_expression(
                text,
                match.start(),
                match.end(),
                band,
                magnitude,
            ):
                continue
            system_raw = match.groupdict().get("system") or match.groupdict().get("system_word")
            limit_sigma = (
                match.groupdict().get("sigma")
                or _find_prose_limit_sigma(text, match.start(), match.end())
                if pattern.measurement_type == "upper_limit"
                else None
            )
            candidates.append(
                ProseMagnitudeCandidate(
                    span_start=match.start(),
                    span_end=match.end(),
                    raw=text[match.start() : match.end()],
                    rule_id=pattern.rule_id,
                    measurement_type=pattern.measurement_type,
                    magnitude_or_limit=magnitude,
                    magnitude_error=match.groupdict().get("err"),
                    limit_sigma=limit_sigma,
                    photometric_band=_canonical_band(band),
                    photometric_system=_parse_system(system_raw),
                    cited_from_other_gcn=_is_cited_measurement(text, match.start(), match.end()),
                )
            )
    return _resolve_candidate_overlaps(candidates)


def _find_enumerated_upper_limits(text: str) -> list[ProseMagnitudeCandidate]:
    """Expand ``>X and >Y`` upper-limit prose into one annotation per value."""

    candidates: list[ProseMagnitudeCandidate] = []
    for phrase_match in _ENUMERATED_LIMIT_RE.finditer(text):
        values_start = phrase_match.start("values")
        values_text = phrase_match.group("values")
        for value_match in _ENUMERATED_LIMIT_VALUE_RE.finditer(values_text):
            start = values_start + value_match.start()
            end = values_start + value_match.end()
            if _should_discard_candidate(text, start, end):
                continue
            magnitude = value_match.group("mag")
            if not 5 <= float(magnitude) <= 30:
                continue
            candidates.append(
                ProseMagnitudeCandidate(
                    span_start=start,
                    span_end=end,
                    raw=text[start:end],
                    rule_id="photometry_prose.prose_enumerated_limits",
                    measurement_type="upper_limit",
                    magnitude_or_limit=magnitude,
                    magnitude_error=None,
                    limit_sigma=phrase_match.group("sigma"),
                    photometric_band=None,
                    photometric_system=_parse_system(phrase_match.group("system")),
                    cited_from_other_gcn=_is_cited_measurement(text, start, end),
                )
            )
    return candidates


def find_companion_fields(
    text: str,
    mag_span: tuple[int, int] | ProseMagnitudeCandidate,
) -> dict[str, object]:
    if isinstance(mag_span, ProseMagnitudeCandidate):
        start, end = mag_span.span_start, mag_span.span_end
        own_band = mag_span.photometric_band
        own_system = mag_span.photometric_system
    else:
        start, end = mag_span
        own_band = None
        own_system = None

    band = own_band or _nearest_band(text, start, end)
    system = own_system or _nearest_system(text, start, end) or "unknown"
    times = _find_time_fields(text)
    exposures = _find_exposure_fields(text)
    primary_time, ambiguous_time = _select_observation_time(text, times, start, end)
    primary_exposure = _nearest_field(exposures, start, end)

    return {
        "photometric_band": band,
        "photometric_system": system,
        "obs_time_raw": primary_time.raw if primary_time else None,
        "obs_time_type": primary_time.kind if primary_time else None,
        "obs_time_reference": _time_reference(primary_time.kind) if primary_time else None,
        "exposure_time_raw": primary_exposure.raw if primary_exposure else None,
        "instrument": _nearest_instrument(text, start, end),
        "ambiguous_time": ambiguous_time,
        "ambiguous_exposure": len(exposures) > 1,
    }


class ProsePhotometryExtractor:
    extractor_id = "photometry-prose-v1"
    extractor_version = "0.1"

    def extract(self, doc: CanonicalDocument) -> list[PhotometricMeasurementAnnotation]:
        text = doc.rendered_text
        if not is_optical_circular(text):
            return []

        candidates = find_prose_magnitudes(text)
        annotations: list[PhotometricMeasurementAnnotation] = []
        for candidate in candidates:
            companion_data = find_companion_fields(text, candidate)
            companions = CompanionFields(**companion_data)
            review_reasons: list[str] = []
            if companions.obs_time_raw is None:
                review_reasons.append(
                    "Measurement time not found in the circular; the annotator must confirm it."
                )
            if companions.photometric_band is None:
                review_reasons.append("Photometric band not found; the annotator must confirm it.")
            if companions.photometric_system == "unknown":
                review_reasons.append("Photometric system is unknown; verify AB or Vega.")
            if candidate.cited_from_other_gcn:
                review_reasons.append("Magnitude cited from another GCN circular; verify ownership.")
            if companions.ambiguous_time:
                review_reasons.append("Multiple observation times found; verify the time associated with this magnitude.")
            if companions.ambiguous_exposure:
                review_reasons.append("Multiple exposure descriptions found; verify the associated exposure.")

            context = text[max(0, candidate.span_start - 250) : min(len(text), candidate.span_end + 250)]
            certainty = "tentative" if _TENTATIVE_RE.search(context) else "confirmed"
            target = "counterpart" if _COUNTERPART_RE.search(context) else "event"
            needs_review = bool(review_reasons)
            annotation = PhotometricMeasurementAnnotation(
                circular_id=doc.circular_id,
                text_sha256=doc.text_sha256,
                span_start=candidate.span_start,
                span_end=candidate.span_end,
                text=candidate.raw,
                measurement_type=candidate.measurement_type,
                target=target,
                certainty=certainty,
                magnitude_or_limit=candidate.magnitude_or_limit,
                magnitude_error=candidate.magnitude_error,
                limit_sigma=candidate.limit_sigma,
                unit="mag",
                photometric_band=companions.photometric_band,
                photometric_system=companions.photometric_system,
                obs_time_raw=companions.obs_time_raw,
                obs_time_type=companions.obs_time_type,
                obs_time_reference=companions.obs_time_reference,
                exposure_time_raw=companions.exposure_time_raw,
                instrument=companions.instrument,
                comment=" ".join(review_reasons) if needs_review else None,
                provenance_inherited=[],
                extractor_id=self.extractor_id,
                extractor_version=self.extractor_version,
                method="prose",
                rule_id=candidate.rule_id,
                confidence=0.65 if needs_review else 0.9,
                needs_review=needs_review,
            )
            if not annotation.verify(text):
                raise ValueError(
                    "Prose photometry annotation failed offset verification: "
                    f"{annotation.span_start}-{annotation.span_end}"
                )
            annotations.append(annotation)
        return annotations


def _should_discard_candidate(text: str, start: int, end: int) -> bool:
    window = text[max(0, start - 80) : min(len(text), end + 80)]
    if _CATALOG_GATE_RE.search(window):
        return True
    prefix = text[max(0, start - 80) : start]
    if _CALIBRATION_GATE_RE.search(prefix):
        return True
    direct = text[max(0, start - 40) : min(len(text), end + 40)]
    if _EXTINCTION_RE.search(direct):
        return True
    if _NON_PHOTOMETRIC_UNIT_RE.search(direct):
        return True
    sentence_start, sentence_end = _sentence_bounds(text, start, end)
    sentence = text[sentence_start:sentence_end]
    raw = text[start:end]
    if _SEARCH_DEPTH_RE.search(sentence) and ">" not in raw and "<" not in raw:
        return True
    return False


def _find_prose_limit_sigma(text: str, start: int, end: int) -> str | None:
    """Find limit confidence in the measurement sentence or the one before it."""

    sentence_start, sentence_end = _sentence_bounds(text, start, end)
    search_start = _previous_sentence_start(text, sentence_start)
    region = text[search_start:sentence_end]
    matches = list(_PROSE_LIMIT_SIGMA_RE.finditer(region))
    if not matches:
        return None
    absolute_start = start - search_start
    nearest = min(
        matches,
        key=lambda match: abs(match.start() - absolute_start),
    )
    return nearest.group("sigma")


def _previous_sentence_start(text: str, sentence_start: int) -> int:
    prefix = text[:sentence_start].rstrip()
    if not prefix:
        return 0
    boundaries = list(re.finditer(r"[.!?](?=\s|$)", prefix))
    if len(boundaries) < 2:
        return 0
    return boundaries[-2].end()


def _is_non_photometric_band_expression(
    text: str,
    start: int,
    end: int,
    band: str | None,
    magnitude: str,
) -> bool:
    if band is None:
        return False
    local = text[max(0, start - 80) : min(len(text), end + 50)]
    if _COORDINATE_CONTEXT_RE.search(local):
        return True
    if band.lower() == "z":
        value = float(magnitude)
        raw = text[start:end]
        has_mag_suffix = bool(re.search(r"\bmag(?:nitudes?)?\b", raw, re.IGNORECASE))
        # This is the photometry-side mirror of redshift.py's anti-band-z gate.
        # Values in the plausible redshift range without a photometric unit are
        # interpreted as redshifts; explicit z-band magnitudes remain valid.
        if 0 <= value <= 12 and not has_mag_suffix:
            return True
        if 0 <= value <= 12 and _REDSHIFT_CONTEXT_RE.search(local):
            return True
    return False


def _is_cited_measurement(text: str, start: int, end: int) -> bool:
    prefix = text[max(0, start - 120) : start]
    suffix = text[end : min(len(text), end + 100)]
    if _DIRECT_CITATION_SUFFIX_RE.search(suffix) or _DIRECT_CITATION_PREFIX_RE.search(prefix):
        return True

    # Only a parenthetical citation immediately attached to the value transfers
    # ownership. A GCN mention elsewhere in the paragraph is unrelated evidence.
    parenthetical = re.match(r"\s*\((?P<body>[^)\n]{0,80})\)", suffix)
    if parenthetical is not None and re.search(
        r"\bGCN\b|\bet\s+al\.", parenthetical.group("body"), re.IGNORECASE
    ):
        return True
    return False


def _resolve_candidate_overlaps(
    candidates: list[ProseMagnitudeCandidate],
) -> list[ProseMagnitudeCandidate]:
    accepted: list[ProseMagnitudeCandidate] = []
    for candidate in sorted(
        candidates,
        key=lambda item: (-(item.span_end - item.span_start), item.span_start, item.rule_id),
    ):
        if any(
            candidate.span_start < existing.span_end and existing.span_start < candidate.span_end
            for existing in accepted
        ):
            continue
        accepted.append(candidate)
    return sorted(accepted, key=lambda item: (item.span_start, item.span_end))


def _canonical_band(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if stripped in _BAND_VALUES:
        return stripped
    for known in _BAND_VALUES:
        if known.lower() == stripped.lower():
            return known
    return stripped


def _parse_system(value: str | None) -> str | None:
    if value is None:
        return None
    return "AB" if "ab" in value.lower() else "Vega"


def _nearest_band(text: str, start: int, end: int) -> str | None:
    window_start = max(0, start - 200)
    window_end = min(len(text), end + 200)
    window = text[window_start:window_end]
    matches: list[tuple[int, str]] = []
    patterns = (
        re.compile(rf"\bin\s+(?:the\s+)?(?P<band>{_BAND_PATTERN})\s+(?:band|filter)\b", re.IGNORECASE),
        re.compile(rf"\b(?:band|filter)\s+(?P<band>{_BAND_PATTERN})\b", re.IGNORECASE),
        re.compile(rf"\b(?P<band>{_BAND_PATTERN})\s*[- ]band\b", re.IGNORECASE),
        re.compile(rf"\bin\s+(?P<band>{_BAND_PATTERN})(?=\s|[,.;])", re.IGNORECASE),
    )
    for pattern in patterns:
        for match in pattern.finditer(window):
            absolute = window_start + match.start()
            matches.append((_distance_to_span(absolute, window_start + match.end(), start, end), match.group("band")))
    if not matches:
        return None
    return _canonical_band(min(matches, key=lambda item: item[0])[1])


def _nearest_system(text: str, start: int, end: int) -> str | None:
    patterns = (
        ("AB", re.compile(r"\bAB\s+(?:mag(?:nitude)?|system)|\(\s*AB(?:\s+mag)?\s*\)", re.IGNORECASE)),
        ("Vega", re.compile(r"\bVega\s+(?:mag(?:nitude)?|system)|\(\s*Vega(?:\s+mag)?\s*\)", re.IGNORECASE)),
    )
    matches: list[tuple[int, str]] = []
    for system, pattern in patterns:
        for match in pattern.finditer(text):
            matches.append((_distance_to_span(match.start(), match.end(), start, end), system))
    return min(matches, key=lambda item: item[0])[1] if matches else None


def _find_time_fields(text: str) -> list[_FieldMatch]:
    matches: list[_FieldMatch] = []
    body_start = _canonical_body_start(text)
    for kind, pattern in _TIME_PATTERNS:
        for match in pattern.finditer(text):
            if match.start() < body_start:
                continue
            matches.append(_FieldMatch(match.start(), match.end(), match.group(0), kind))
    return _deduplicate_fields(matches)


def _select_observation_time(
    text: str,
    matches: list[_FieldMatch],
    magnitude_start: int,
    magnitude_end: int,
) -> tuple[_FieldMatch | None, bool]:
    observation_matches = [
        match for match in matches if not _is_trigger_epoch(text, match)
    ]
    if not observation_matches:
        return None, False

    groups = _group_time_matches(text, observation_matches)
    magnitude_sentence = _sentence_bounds(text, magnitude_start, magnitude_end)
    magnitude_paragraph = _paragraph_bounds(text, magnitude_start, magnitude_end)

    ranked: list[tuple[int, int, _FieldMatch]] = []
    for group in groups:
        representative = _representative_time(group)
        group_start = min(item.start for item in group)
        group_end = max(item.end for item in group)
        if _spans_overlap((group_start, group_end), magnitude_sentence):
            priority = 0
        elif _spans_overlap((group_start, group_end), magnitude_paragraph):
            priority = 1
        elif any(_has_observation_time_context(text, item) for item in group):
            priority = 2
        else:
            priority = 3
        ranked.append(
            (
                priority,
                _distance_to_span(group_start, group_end, magnitude_start, magnitude_end),
                representative,
            )
        )

    ranked.sort(key=lambda item: (item[0], item[1], item[2].start))
    best_priority = ranked[0][0]
    same_priority = [item for item in ranked if item[0] == best_priority]
    ambiguous = False
    if len(same_priority) > 1:
        # A clearly nearer epoch resolves the choice. Similar-distance epochs at
        # the same semantic priority remain a human-review ambiguity.
        ambiguous = same_priority[1][1] - same_priority[0][1] <= 120
    return ranked[0][2], ambiguous


def _group_time_matches(text: str, matches: list[_FieldMatch]) -> list[list[_FieldMatch]]:
    groups: list[list[_FieldMatch]] = []
    for match in sorted(matches, key=lambda item: item.start):
        if groups:
            previous = groups[-1][-1]
            same_sentence = _sentence_bounds(text, previous.start, previous.end) == _sentence_bounds(
                text, match.start, match.end
            )
            if same_sentence and match.start - previous.end <= 120:
                groups[-1].append(match)
                continue
        groups.append([match])
    return groups


def _representative_time(group: list[_FieldMatch]) -> _FieldMatch:
    # An absolute timestamp is more directly reusable than a relative epoch when
    # both describe the same observation in one sentence.
    return min(group, key=lambda item: (item.kind != "utc_datetime", item.start))


def _is_trigger_epoch(text: str, match: _FieldMatch) -> bool:
    if match.kind == "relative_to_trigger":
        return False
    before = text[max(0, match.start - 70) : match.start]
    after = text[match.end : min(len(text), match.end + 70)]
    if _TRIGGER_TIME_BEFORE_RE.search(before):
        return True
    if _TRIGGER_TIME_AFTER_RE.search(after) and not _OBSERVATION_TIME_CONTEXT_RE.search(before[-70:]):
        return True
    return False


def _has_observation_time_context(text: str, match: _FieldMatch) -> bool:
    if match.kind == "relative_to_trigger":
        return True
    window = text[max(0, match.start - 100) : min(len(text), match.end + 80)]
    return bool(_OBSERVATION_TIME_CONTEXT_RE.search(window))


def _canonical_body_start(text: str) -> int:
    if text.startswith("SUBJECT:"):
        marker = text.find("\n\n")
        if marker >= 0:
            return marker + 2
    return 0


def _sentence_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    boundaries = list(re.finditer(r"[.!?](?=\s|$)", text))
    sentence_start = 0
    sentence_end = len(text)
    for boundary in boundaries:
        if boundary.end() <= start:
            sentence_start = boundary.end()
        elif boundary.start() >= end:
            sentence_end = boundary.end()
            break
    return sentence_start, sentence_end


def _paragraph_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    paragraph_breaks = list(re.finditer(r"\n\s*\n", text))
    paragraph_start = 0
    paragraph_end = len(text)
    for boundary in paragraph_breaks:
        if boundary.end() <= start:
            paragraph_start = boundary.end()
        elif boundary.start() >= end:
            paragraph_end = boundary.start()
            break
    return paragraph_start, paragraph_end


def _spans_overlap(first: tuple[int, int], second: tuple[int, int]) -> bool:
    return first[0] < second[1] and second[0] < first[1]


def _find_exposure_fields(text: str) -> list[_FieldMatch]:
    matches = [
        _FieldMatch(match.start(), match.end(), match.group(0), "exposure")
        for pattern in _EXPOSURE_PATTERNS
        for match in pattern.finditer(text)
    ]
    return _deduplicate_fields(matches)


def _deduplicate_fields(matches: list[_FieldMatch]) -> list[_FieldMatch]:
    accepted: list[_FieldMatch] = []
    for match in sorted(matches, key=lambda item: (-(item.end - item.start), item.start)):
        if any(match.start < other.end and other.start < match.end for other in accepted):
            continue
        accepted.append(match)
    return sorted(accepted, key=lambda item: item.start)


def _nearest_field(
    matches: list[_FieldMatch],
    start: int,
    end: int,
) -> _FieldMatch | None:
    if not matches:
        return None
    return min(matches, key=lambda item: (_distance_to_span(item.start, item.end, start, end), item.start))


def _nearest_instrument(text: str, start: int, end: int) -> str | None:
    matches: list[tuple[int, str]] = []
    for pattern in _INSTRUMENT_PATTERNS:
        for match in pattern.finditer(text):
            raw = match.group(0)
            if _is_valid_instrument_name(raw):
                matches.append((_distance_to_span(match.start(), match.end(), start, end), raw))
    return min(matches, key=lambda item: item[0])[1] if matches else None


def _is_valid_instrument_name(value: str) -> bool:
    stripped = value.strip()
    if not stripped or stripped in {"not", "the", "and", "with"}:
        return False
    if re.search(r"\bS\s*/\s*N\b|\bsigma\b|~", stripped, re.IGNORECASE):
        return False
    return bool(re.search(r"[A-Za-z]", stripped))


def _distance_to_span(field_start: int, field_end: int, start: int, end: int) -> int:
    if field_end < start:
        return start - field_end
    if field_start > end:
        return field_start - end
    return 0


def _time_reference(time_type: str) -> str:
    return "trigger_time_t0" if time_type == "relative_to_trigger" else "absolute_time"


__all__ = [
    "CompanionFields",
    "ProseMagnitudeCandidate",
    "ProsePhotometryExtractor",
    "find_companion_fields",
    "find_prose_magnitudes",
    "is_optical_circular",
]
