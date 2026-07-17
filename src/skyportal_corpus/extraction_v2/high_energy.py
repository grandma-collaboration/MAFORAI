from __future__ import annotations

import re
from dataclasses import dataclass

from skyportal_corpus.canonical.document import CanonicalDocument
from skyportal_corpus.extraction_v2.annotations import EventEvidenceAnnotation
from skyportal_corpus.extraction_v2.duration import (
    assemble_instrument_band_comment,
    resolve_measurement_instrument,
)


_NUMBER = r"(?:\d+(?:\.\d+)?|\.\d+)"
_SIGNED_NUMBER = rf"[+-]?{_NUMBER}"
_PLUS_MINUS = r"(?:\+/-|±|\+\s*-)"
_INLINE_ERROR = (
    rf"(?:\s*{_PLUS_MINUS}\s*{_NUMBER}|"
    rf"\s*[+-]\s*{_NUMBER}\s*/\s*[+-]\s*{_NUMBER})"
)
_PAREN_ERROR = (
    rf"(?:\s*\(\s*[+-]?\s*{_NUMBER}\s*,\s*[+-]?\s*{_NUMBER}\s*\)|"
    rf"\s*\(\s*[+-]\s*{_NUMBER}\s*/\s*[+-]\s*{_NUMBER}\s*\)|"
    rf"\s*\(\s*{_PLUS_MINUS}\s*{_NUMBER}\s*\)|"
    rf"\s*\(\s*[+-]?\s*{_NUMBER}\s*\)\s*\(\s*[+-]?\s*{_NUMBER}\s*\))"
)
_ERROR = rf"(?:{_INLINE_ERROR}|{_PAREN_ERROR})?"
_EXPONENT = (
    r"(?:\s*[Ee]\s*[+-]?\d+|"
    r"\s*\*\s*[Ee]\s*[+-]?\d+|"
    r"\s*[xX*×]\s*10\s*(?:\^\s*\(?\s*[+-]?\d+\s*\)?|\(\s*[+-]?\d+\s*\)))?"
)
_VALUE = (
    rf"(?:\(\s*{_SIGNED_NUMBER}{_INLINE_ERROR}\s*\){_EXPONENT}|"
    rf"{_SIGNED_NUMBER}{_ERROR}{_EXPONENT})"
)
_APPROX = r"(?:about|approximately|around|roughly|preliminary|~)"
_CM2 = r"cm\s*(?:\^?\s*2|\(\s*2\s*\))"
_CM_MINUS2 = r"cm\s*(?:\^\s*-\s*2|-\s*2|\(\s*-\s*2\s*\))"
_SECOND = r"(?:s|secs?|seconds?)"
_SECOND_MINUS1 = rf"{_SECOND}\s*(?:\^\s*-\s*1|-\s*1)"
_PHOTON_FLUX_UNIT = (
    rf"(?:ph(?:otons?)?\s*/\s*(?:{_SECOND}\s*/\s*{_CM2}|{_CM2}\s*/\s*{_SECOND})|"
    rf"ph(?:otons?)?\s+{_CM_MINUS2}\s+{_SECOND_MINUS1})"
)
_ENERGY_FLUX_UNIT = (
    rf"(?:ergs?\s*/\s*(?:{_SECOND}\s*/\s*{_CM2}|{_CM2}\s*/\s*{_SECOND})|"
    rf"ergs?\s+{_CM_MINUS2}\s+{_SECOND_MINUS1})"
)
_FLUX_UNIT = rf"(?:{_PHOTON_FLUX_UNIT}|{_ENERGY_FLUX_UNIT})"
_ENERGY_FLUENCE_UNIT = rf"(?:ergs?\s*/\s*{_CM2}|ergs?\s+{_CM_MINUS2})"
_PHYSICAL_UNIT = (
    rf"(?:{_PHOTON_FLUX_UNIT}|{_ENERGY_FLUX_UNIT}|{_ENERGY_FLUENCE_UNIT}|keV|MeV|GeV|ergs?)"
)
_SENTENCE_CHAR = r"(?:(?![.!?](?:\s|$))[\s\S])"

_EPEAK_RE = re.compile(
    rf"\bE[ _-]?peak\b\s*,?\s*(?:is|=|of)?\s*(?P<approx>{_APPROX})?\s*"
    rf"(?P<value>{_VALUE})(?:\s*(?P<unit>{_PHYSICAL_UNIT})\b)?",
    re.IGNORECASE,
)
_KONUS_EP_RE = re.compile(
    rf"(?<![A-Za-z0-9_,])Ep(?![A-Za-z0-9_,])\s*"
    rf"(?P<operator><=|<|=)\s*(?P<value>{_VALUE})\s*(?P<unit>keV)\b",
    re.IGNORECASE,
)
_FLUENCE_RE = re.compile(
    rf"\b(?:(?:event|total)\s+)?fluence\b"
    rf"(?:{_SENTENCE_CHAR}{{0,100}}?(?:\b(?:is|was|of)\b|=|:)\s*|\s+)"
    rf"(?P<approx>{_APPROX})?\s*(?P<value>{_VALUE})"
    rf"(?:\s*(?P<unit>{_PHYSICAL_UNIT})\b)?",
    re.IGNORECASE,
)
_PEAK_FLUX_RE = re.compile(
    rf"\b(?:(?:\d+(?:\.\d+)?-s(?:ec)?\s+)?peak\s+(?:(?:energy|photon)\s+)?flux|the\s+flux)\b"
    rf"(?!\s+density){_SENTENCE_CHAR}{{0,180}}?"
    rf"(?:\b(?:is|was|of|reaches|reached)\b|=|:)\s*(?P<approx>{_APPROX})?\s*"
    rf"(?P<value>{_VALUE})\s*(?P<unit>{_FLUX_UNIT})\b",
    re.IGNORECASE,
)
_POWERLAW_INDEX_RE = re.compile(
    rf"\bpower[- ]?law\s+index\b"
    rf"(?:[^.]{{0,60}}?\b(?:is|was|of|fixed\s+at)\b\s*|\s*(?:=|:)\s*|\s+)"
    rf"(?P<approx>{_APPROX})?\s*(?P<value>{_VALUE})",
    re.IGNORECASE,
)
_PHOTON_INDEX_RE = re.compile(
    rf"\bphoton\s+index\b(?![\s:,-]{{0,10}}beta\b)(?:\s*\(\s*Gamma\s*\))?"
    rf"(?:[^.]{{0,45}}?\b(?:is|was|of|fixed\s+at)\b\s*|\s*(?:=|:)\s*|\s+)"
    rf"(?P<approx>{_APPROX})?\s*(?P<value>{_VALUE})",
    re.IGNORECASE,
)
_SPECTRAL_INDEX_RE = re.compile(
    rf"\bspectral\s+index\b"
    rf"(?:[^.]{{0,45}}?\b(?:is|was|of|fixed\s+at)\b\s*|\s*(?:=|:)\s*|\s+)"
    rf"(?P<approx>{_APPROX})?\s*(?P<value>{_VALUE})",
    re.IGNORECASE,
)
_GAMMA_INDEX_RE = re.compile(
    rf"\bGamma\b\s*(?:is|was|=|:)\s*(?P<approx>{_APPROX})?\s*"
    rf"(?P<value>{_VALUE})",
    re.IGNORECASE,
)
_ALPHA_BETA_RE = re.compile(
    rf"(?<![A-Za-z])(?P<name>alpha|beta)\s*=\s*(?P<approx>{_APPROX})?\s*"
    rf"(?P<value>{_VALUE})",
    re.IGNORECASE,
)
_BETA_LIMIT_RE = re.compile(
    rf"(?<![A-Za-z])beta\s*(?:<=|<)\s*(?P<value>{_VALUE})",
    re.IGNORECASE,
)
_BETA_PHOTON_INDEX_LIMIT_RE = re.compile(
    rf"\bupper\s+limit\s+on\s+the\s+high\s+energy\s+photon\s+index"
    rf"(?:\s*:\s*)?\s+beta\s+(?:of\s+|(?:<=|<)\s*)"
    rf"(?P<value>{_VALUE})",
    re.IGNORECASE,
)
_EISO_RE = re.compile(
    rf"\bE[ _-]?iso\b\s*,?\s*(?:is|=|of|to)?\s*(?P<approx>{_APPROX})?\s*"
    rf"(?P<value>{_VALUE})(?:\s*(?P<unit>{_PHYSICAL_UNIT})\b)?",
    re.IGNORECASE,
)
_CUTOFF_ENERGY_RE = re.compile(
    rf"\bcutoff\s+energy\b[^.\n]{{0,50}}?\b(?:is|=|of)\s*"
    rf"(?P<approx>{_APPROX})?\s*(?P<value>{_VALUE})"
    rf"(?:\s*(?P<unit>{_PHYSICAL_UNIT})\b)?",
    re.IGNORECASE,
)

_ENERGY_BAND_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:keV|MeV|GeV)?\s*[-–]\s*"
    r"\d+(?:\.\d+)?\s*(?:keV|MeV|GeV)\b",
    re.IGNORECASE,
)
_DERIVED_BAND_CONTEXT_RE = re.compile(
    r"\b(?:rest[- ]frame|isotropic|L[_ ]?iso|E[_ ]?iso|Ep\s*,\s*[ip]\s*,\s*z|"
    r"Ep\s*,\s*z)\b",
    re.IGNORECASE,
)
_DURATION_BAND_CONTEXT_RE = re.compile(
    r"\b(?:T90|T50|duration|lasted|lasting)\b",
    re.IGNORECASE,
)
_RADIO_OR_OPTICAL_UNIT_RE = re.compile(r"\b(?:mJy|uJy|µJy|Jy|mag)\b", re.IGNORECASE)
_TENTATIVE_RE = re.compile(
    r"\b(?:about|approximately|around|roughly|preliminary)\b|~",
    re.IGNORECASE,
)
_COLUMN_DENSITY_RE = re.compile(
    r"\b(?:column\s+density|hydrogen\s+column|N[_\s-]?H)\b",
    re.IGNORECASE,
)
_HIGH_ENERGY_CONTEXT_RE = re.compile(
    r"\b(?:X[- ]?ray|gamma(?:-ray)?|GRB|BAT|GBM|WXT|FXT|LAT|spectrum|spectral|"
    r"keV|MeV|GeV)\b",
    re.IGNORECASE,
)
_RADIO_CONTEXT_RE = re.compile(
    r"\b(?:radio|GHz|MHz|mJy|uJy|µJy|Jy|VAST|MeerKAT|ATCA)\b",
    re.IGNORECASE,
)
_SHARED_UNIT_RE = re.compile(
    rf"^\s*(?:\([^()\n]{{1,30}}\)\s*)?(?P<unit>{_PHYSICAL_UNIT})\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class HighEnergyCandidate:
    span_start: int
    span_end: int
    raw: str
    property_name: str
    raw_value: str
    unit: str | None
    rule_id: str
    priority: int
    unit_required: bool
    operator: str = "="


@dataclass(frozen=True)
class _PropertyRule:
    rule_id: str
    property_name: str
    pattern: re.Pattern[str]
    priority: int
    unit_required: bool = True
    operator: str | None = None


_RULES = (
    _PropertyRule("high_energy.epeak", "Epeak", _EPEAK_RE, 0),
    _PropertyRule("high_energy.epeak", "Epeak", _KONUS_EP_RE, 0),
    _PropertyRule("high_energy.fluence", "fluence", _FLUENCE_RE, 1),
    _PropertyRule("high_energy.peak_flux", "peak flux", _PEAK_FLUX_RE, 2),
    _PropertyRule(
        "high_energy.powerlaw_index",
        "power law index",
        _POWERLAW_INDEX_RE,
        3,
        unit_required=False,
    ),
    _PropertyRule(
        "high_energy.photon_index",
        "photon index",
        _PHOTON_INDEX_RE,
        3,
        unit_required=False,
    ),
    _PropertyRule(
        "high_energy.beta",
        "beta",
        _BETA_PHOTON_INDEX_LIMIT_RE,
        3,
        unit_required=False,
        operator="<",
    ),
    _PropertyRule(
        "high_energy.beta",
        "beta",
        _BETA_LIMIT_RE,
        3,
        unit_required=False,
        operator="<",
    ),
    _PropertyRule(
        "high_energy.spectral_index",
        "spectral index",
        _SPECTRAL_INDEX_RE,
        3,
        unit_required=False,
    ),
    _PropertyRule(
        "high_energy.photon_index",
        "photon index",
        _GAMMA_INDEX_RE,
        3,
        unit_required=False,
    ),
    _PropertyRule("high_energy.eiso", "Eiso", _EISO_RE, 4),
    _PropertyRule("high_energy.cutoff_energy", "cutoff energy", _CUTOFF_ENERGY_RE, 5),
)


class HighEnergyPropertyExtractor:
    extractor_id = "high-energy-v1"
    extractor_version = "0.1"

    def extract(self, doc: CanonicalDocument) -> list[EventEvidenceAnnotation]:
        annotations: list[EventEvidenceAnnotation] = []
        for candidate in resolve_high_energy_overlaps(find_high_energy_candidates(doc.rendered_text)):
            missing_unit = candidate.unit_required and candidate.unit is None
            context_comment = _scientific_context(doc.rendered_text, candidate)
            review_comment = (
                f"Unit not identified for {candidate.property_name}; verify the reported value."
                if missing_unit
                else None
            )
            comment = _join_comment(review_comment, context_comment)
            certainty = (
                "tentative"
                if _TENTATIVE_RE.search(candidate.raw)
                else "confirmed"
            )
            value = (
                f"{candidate.property_name} {candidate.operator} "
                f"{_normalize_value(candidate.raw_value)}"
            )
            annotation = EventEvidenceAnnotation(
                circular_id=doc.circular_id,
                text_sha256=doc.text_sha256,
                span_start=candidate.span_start,
                span_end=candidate.span_end,
                text=candidate.raw,
                label="HIGH_ENERGY_PROPERTY",
                target="event",
                certainty=certainty,
                value=value,
                unit=_normalize_unit(candidate.unit),
                comment=comment,
                extractor_id=self.extractor_id,
                extractor_version=self.extractor_version,
                method="regex",
                rule_id=candidate.rule_id,
                confidence=0.5 if missing_unit else 1.0,
                needs_review=missing_unit,
            )
            if not annotation.verify(doc.rendered_text):
                raise ValueError(
                    f"High-energy annotation failed offset verification: {annotation.rule_id} "
                    f"{annotation.span_start}-{annotation.span_end}"
                )
            annotations.append(annotation)
        return annotations


def find_high_energy_candidates(text: str) -> list[HighEnergyCandidate]:
    candidates: list[HighEnergyCandidate] = []
    for rule in _RULES:
        for match in rule.pattern.finditer(text):
            if rule.pattern is _KONUS_EP_RE and _is_model_formula_ep(text, match.start()):
                continue
            if rule.rule_id == "high_energy.cutoff_energy" and _mentions_epeak_nearby(
                text,
                match.start(),
                match.end(),
            ):
                continue
            candidate = _candidate_from_match(text, match, rule)
            if _COLUMN_DENSITY_RE.search(candidate.raw):
                continue
            if rule.pattern in {_SPECTRAL_INDEX_RE, _GAMMA_INDEX_RE} and not _is_high_energy_index(
                text,
                candidate.span_start,
                candidate.span_end,
            ):
                continue
            if _has_non_high_energy_unit(text, candidate.span_end):
                continue
            candidates.append(candidate)

    for match in _ALPHA_BETA_RE.finditer(text):
        property_name = match.group("name").lower()
        candidates.append(
            HighEnergyCandidate(
                span_start=match.start(),
                span_end=match.end(),
                raw=text[match.start() : match.end()],
                property_name=property_name,
                raw_value=match.group("value"),
                unit=None,
                rule_id=f"high_energy.{property_name}",
                priority=3,
                unit_required=False,
            )
        )
    return sorted(candidates, key=lambda item: (item.span_start, item.priority, item.span_end))


def resolve_high_energy_overlaps(candidates: list[HighEnergyCandidate]) -> list[HighEnergyCandidate]:
    accepted: list[HighEnergyCandidate] = []
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


def _candidate_from_match(
    text: str,
    match: re.Match[str],
    rule: _PropertyRule,
) -> HighEnergyCandidate:
    captured_unit = match.groupdict().get("unit")
    unit = captured_unit or _shared_unit_after_value(text, match.end("value"))
    span_end = match.end("unit") if captured_unit is not None else match.end("value")
    property_name = rule.property_name
    if rule.rule_id == "high_energy.peak_flux":
        normalized_unit = _normalize_unit(unit)
        property_name = (
            "peak photon flux"
            if normalized_unit == "ph/s/cm^2"
            else "peak energy flux"
        )
    captured_operator = match.groupdict().get("operator")
    operator = rule.operator or captured_operator or "="
    if operator == "<=":
        operator = "<"
    return HighEnergyCandidate(
        span_start=match.start(),
        span_end=span_end,
        raw=text[match.start() : span_end],
        property_name=property_name,
        raw_value=match.group("value"),
        unit=unit,
        rule_id=rule.rule_id,
        priority=rule.priority,
        unit_required=rule.unit_required,
        operator=operator,
    )


def _normalize_value(value: str) -> str:
    normalized = value.replace("±", "+/-")
    normalized = re.sub(r"\s*\+\s*-\s*", " +/- ", normalized)
    normalized = re.sub(r"\s*\+/-\s*", " +/- ", normalized)
    normalized = re.sub(
        rf"\+\s*({_NUMBER})\s*/\s*-\s*({_NUMBER})",
        lambda match: f"+{match.group(1)}/-{match.group(2)}",
        normalized,
    )
    normalized = re.sub(r"\(\s+", "(", normalized)
    normalized = re.sub(r"\s+\)", ")", normalized)
    normalized = re.sub(
        rf"({_NUMBER})\s+(\(\s*[+-])",
        r"\1\2",
        normalized,
    )
    normalized = re.sub(r"\)\s+([Ee][+-]?\d+)", r")\1", normalized)
    normalized = re.sub(r"\)\s+([xX×]\s*10)", r")\1", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _normalize_unit(unit: str | None) -> str:
    if unit is None:
        return ""
    compact = re.sub(r"\s+", "", unit)
    lowered = compact.lower()
    if lowered.startswith("ph/"):
        return "ph/s/cm^2"
    if lowered.startswith("ph"):
        return "ph/s/cm^2"
    if lowered.startswith("erg") and re.search(
        r"/(?:s|sec|secs|second|seconds)(?:/|$)|(?:s|sec|secs|second|seconds)(?:\^-?1|-1)$",
        lowered,
    ):
        return "erg/cm^2/s"
    if lowered.startswith("erg") and ("cm" in lowered):
        return "erg/cm^2"
    if lowered in {"erg", "ergs"}:
        return "erg"
    return {"kev": "keV", "mev": "MeV", "gev": "GeV"}.get(lowered, unit.strip())


def _has_non_high_energy_unit(text: str, span_end: int) -> bool:
    suffix = text[span_end : min(len(text), span_end + 20)]
    return bool(_RADIO_OR_OPTICAL_UNIT_RE.search(suffix))


def _shared_unit_after_value(text: str, value_end: int) -> str | None:
    suffix = text[value_end : min(len(text), value_end + 60)]
    match = _SHARED_UNIT_RE.match(suffix)
    return match.group("unit") if match is not None else None


def _is_high_energy_index(text: str, start: int, end: int) -> bool:
    window = text[max(0, start - 140) : min(len(text), end + 140)]
    if _RADIO_CONTEXT_RE.search(window):
        return False
    return bool(_HIGH_ENERGY_CONTEXT_RE.search(window))


def _mentions_epeak_nearby(text: str, start: int, end: int) -> bool:
    window = text[max(0, start - 20) : min(len(text), end + 100)]
    return bool(re.search(r"\bE[ _-]?peak\b", window, re.IGNORECASE))


def _is_model_formula_ep(text: str, start: int) -> bool:
    prefix = text[max(0, start - 2) : start].rstrip()
    suffix = text[start + 2 : min(len(text), start + 8)].lstrip()
    return prefix.endswith("/") or suffix.startswith(")")


def _scientific_context(text: str, candidate: HighEnergyCandidate) -> str | None:
    instrument = resolve_measurement_instrument(
        text,
        candidate.span_start,
        candidate.span_end,
    )
    band = _governing_energy_band(text, candidate)
    return assemble_instrument_band_comment(instrument, band)


def _governing_energy_band(
    text: str,
    candidate: HighEnergyCandidate,
) -> str | None:
    if candidate.rule_id == "high_energy.eiso":
        return _eiso_energy_band(text, candidate)
    if candidate.rule_id in {"high_energy.fluence", "high_energy.peak_flux"}:
        return _same_sentence_energy_band(text, candidate, reject_derived=True)
    if candidate.rule_id in {
        "high_energy.epeak",
        "high_energy.cutoff_energy",
        "high_energy.powerlaw_index",
        "high_energy.photon_index",
        "high_energy.spectral_index",
        "high_energy.alpha",
        "high_energy.beta",
    }:
        return _spectral_fit_energy_band(text, candidate)
    return None


def _eiso_energy_band(text: str, candidate: HighEnergyCandidate) -> str | None:
    sentence_start, sentence_end = _sentence_bounds(
        text,
        candidate.span_start,
        candidate.span_end,
    )
    return _nearest_energy_band(
        text,
        sentence_start,
        sentence_end,
        candidate.span_start,
        candidate.span_end,
        reject_derived=False,
        reject_duration=False,
    )


def _same_sentence_energy_band(
    text: str,
    candidate: HighEnergyCandidate,
    reject_derived: bool,
) -> str | None:
    sentence_start, sentence_end = _sentence_bounds(
        text,
        candidate.span_start,
        candidate.span_end,
    )
    return _nearest_energy_band(
        text,
        sentence_start,
        sentence_end,
        candidate.span_start,
        candidate.span_end,
        reject_derived=reject_derived,
        reject_duration=False,
    )


def _spectral_fit_energy_band(
    text: str,
    candidate: HighEnergyCandidate,
) -> str | None:
    sentence_start, sentence_end = _sentence_bounds(
        text,
        candidate.span_start,
        candidate.span_end,
    )
    if _DERIVED_BAND_CONTEXT_RE.search(text[sentence_start:sentence_end]):
        return None

    paragraph_start, paragraph_end = _paragraph_bounds(
        text,
        candidate.span_start,
        candidate.span_end,
    )
    paragraph = text[paragraph_start:paragraph_end]
    band = _nearest_energy_band(
        text,
        paragraph_start,
        paragraph_end,
        candidate.span_start,
        candidate.span_end,
        reject_derived=True,
        reject_duration=True,
    )
    if band is not None:
        return band

    # A derived-energy clause in the governing paragraph is a hard boundary:
    # neighboring observed bands must not be borrowed across that quantity.
    if _DERIVED_BAND_CONTEXT_RE.search(paragraph):
        return None

    analysis_start = max(0, paragraph_start - 700)
    analysis_end = min(len(text), paragraph_end + 700)
    return _nearest_energy_band(
        text,
        analysis_start,
        analysis_end,
        candidate.span_start,
        candidate.span_end,
        reject_derived=True,
        reject_duration=True,
    )


def _nearest_energy_band(
    text: str,
    fragment_start: int,
    fragment_end: int,
    span_start: int,
    span_end: int,
    reject_derived: bool,
    reject_duration: bool,
) -> str | None:
    candidates: list[tuple[re.Match[str], int, int]] = []
    fragment = text[fragment_start:fragment_end]
    for match in _ENERGY_BAND_RE.finditer(fragment):
        absolute_start = fragment_start + match.start()
        absolute_end = fragment_start + match.end()
        sentence_start, sentence_end = _sentence_bounds(
            text,
            absolute_start,
            absolute_end,
        )
        sentence = text[sentence_start:sentence_end]
        if reject_derived and _DERIVED_BAND_CONTEXT_RE.search(sentence):
            continue
        if reject_duration and _DURATION_BAND_CONTEXT_RE.search(sentence):
            continue
        candidates.append((match, absolute_start, absolute_end))
    if not candidates:
        return None
    center = (span_start + span_end) / 2
    nearest = min(
        candidates,
        key=lambda item: abs(((item[1] + item[2]) / 2) - center),
    )
    return re.sub(r"\s+", " ", nearest[0].group(0)).strip()


def _sentence_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    boundaries = list(re.finditer(r"\.(?!\d)|[!?]", text))
    left = max((match.end() for match in boundaries if match.end() <= start), default=0)
    right = min((match.end() for match in boundaries if match.start() >= end), default=len(text))
    return left, right


def _paragraph_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    left_matches = list(re.finditer(r"\n\s*\n", text[:start]))
    left = left_matches[-1].end() if left_matches else 0
    right_match = re.search(r"\n\s*\n", text[end:])
    right = end + right_match.start() if right_match is not None else len(text)
    return left, right


def _join_comment(*parts: str | None) -> str | None:
    values = [part for part in parts if part]
    return "; ".join(values) or None
