from __future__ import annotations

import re
from dataclasses import dataclass

from skyportal_corpus.canonical.document import CanonicalDocument
from skyportal_corpus.extraction_v2.annotations import EventEvidenceAnnotation


SPECTROSCOPY_SIGNAL_RE = re.compile(
    r"(?:"
    r"spectroscop|spectrum|spectra|absorption|emission\s+line|"
    r"P-Cygni|Mg\s*II|Ca\s*II|\[O\s*II\]|(?<!\w)H[- ]alpha|spectral"
    r")",
    re.IGNORECASE,
)

_SPECTROGRAPH = (
    r"(?:ALFOSC|FORS2|OSIRIS|X[- ]shooter|GMOS(?:-[NS])?|"
    r"LRIS|MISTRAL|DEIMOS|MODS|LRS2)"
)
_LINE_TOKEN = (
    r"(?:"
    r"Mg\s*I{1,2}|Ca\s*II|Fe\s*I{1,2}|Al\s*I{1,3}|Si\s*I{1,4}|"
    r"C\s*I{1,4}|O\s*I{1,3}|S\s*I{1,3}|Mn\s*II|Zn\s*II|Cr\s*II|"
    r"\[O\s*(?:II|III)\]|\[N\s*II\]|"
    r"H[- ]?(?:alpha|beta)|He\s*II"
    r")"
)
_LINE_LIST = rf"{_LINE_TOKEN}(?:\s*(?:,|and)\s*{_LINE_TOKEN})*"
_OPTICAL_SPECTROGRAPH = (
    rf"(?:{_SPECTROGRAPH}|DBSP|SEDM|GTC|VLT|NOT|Gemini|Keck)"
)
_OPTICAL_SPECTRUM_CONTEXT_RE = re.compile(
    rf"(?:"
    rf"\b(?:optical|NIR|near[- ]infrared)\b|"
    rf"\b{_OPTICAL_SPECTROGRAPH}\b|"
    rf"\b\d+(?:\.\d+)?(?:\s*-\s*\d+(?:\.\d+)?)?\s*"
    rf"(?:Angstroms?|\u00c5|nm)\b|"
    rf"\b(?:emission|absorption)\s+(?:features?|lines?)\b|"
    rf"\bP[- ]Cygni\b|"
    rf"(?<!\w){_LINE_TOKEN}(?!\w)|"
    rf"\bspectroscop(?:y|ic|ical|ically)\b"
    rf")",
    re.IGNORECASE,
)
_HIGH_ENERGY_SPECTRUM_CONTEXT_RE = re.compile(
    r"(?:"
    r"\b\d+(?:\.\d+)?\s*(?:(?:keV|MeV)\s*)?(?:-|to)\s*"
    r"\d+(?:\.\d+)?\s*"
    r"(?:keV|MeV)\b|"
    r"\b\d+(?:\.\d+)?\s*(?:keV|MeV)\s+spectrum\b|"
    r"\b(?:WXT|FXT|GRM|GBM|Konus(?:-Wind)?|BAT|ECLAIRs|CZTI|"
    r"GECAM|HXMT)\b|"
    r"\b(?:X[- ]ray|gamma[- ]ray|high[- ]energy)\b|"
    r"\b(?:power[- ]law|CPL|Band\s+model|cutoff\s+power[- ]law|"
    r"time[- ]averaged\s+spectrum|average\s+[^.!?;\n]{0,30}spectrum|"
    r"count\s+spectrum|energy\s+spectrum|photon\s+spectrum|"
    r"best\s+fit[^.!?;\n]{0,40}power[- ]law)\b"
    r")",
    re.IGNORECASE,
)
_FOLLOWUP_ONLY_RE = re.compile(
    r"\b(?:"
    r"encourage|request|recommend|plan(?:ned)?|future|further|needed|"
    r"required|will\s+(?:obtain|perform)|in\s+progress"
    r")\b",
    re.IGNORECASE,
)
_PROGRAM_NAME_RE = re.compile(
    r"\b(?:program|programme|pipeline|survey|collaboration)\b",
    re.IGNORECASE,
)
_EVENT_SPECTRUM_RE = re.compile(
    r"\b(?:"
    r"prompt|gamma[- ]ray|high[- ]energy|BAT|GBM|GRM|Konus(?:-Wind)?|"
    r"WXT|FXT|"
    r"(?:burst|GRB|event)(?:'s)?\s+(?:spectrum|spectra)|"
    r"(?:spectrum|spectra)\s+of\s+(?:the\s+)?(?:burst|GRB|event)"
    r")\b",
    re.IGNORECASE,
)
_COUNTERPART_SPECTROSCOPY_RE = re.compile(
    r"\b(?:spectroscopy|spectroscopic|spectrograph|spectrometer)\b",
    re.IGNORECASE,
)
_CONTINUUM_ONLY_RE = re.compile(
    r"^(?:(?:featureless|red|blue|faint|strong|weak)\s+)?continuum$",
    re.IGNORECASE,
)
_SPECTRAL_CONTEXT_RE = re.compile(
    r"\b(?:"
    r"spectrum|spectra|spectroscop|spectrograph|wavelength|"
    r"absorption|emission|line|feature"
    r")\b",
    re.IGNORECASE,
)
_BARE_REDSHIFT_RE = re.compile(
    r"\b(?:redshift|z\s*[=~])\b",
    re.IGNORECASE,
)
_CLASSIFICATION_RE = re.compile(
    r"\b(?:"
    r"Type\s+(?:Ia|Ib|Ic|II|IIb|IIn)\s+supernova|"
    r"(?:long|short)(?:-duration)?\s+GRB|kilonova|TDE"
    r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SpectroscopyCandidate:
    span_start: int
    span_end: int
    raw: str
    target: str
    rule_id: str
    priority: int


@dataclass(frozen=True)
class _SpectroscopyRule:
    rule_id: str
    pattern: re.Pattern[str]
    priority: int
    requires_spectral_context: bool = False


_RULES = (
    _SpectroscopyRule(
        "spectroscopy.observation",
        re.compile(
            rf"(?P<span>\bwe\s+(?:have\s+)?"
            rf"(?:obtained|performed|carried\s+out)\s+"
            rf"(?:(?:optical|NIR|near[- ]infrared|UV)\s+)?"
            rf"spectroscopy(?:\s+with\s+(?:the\s+)?{_SPECTROGRAPH})?)",
            re.IGNORECASE,
        ),
        0,
    ),
    _SpectroscopyRule(
        "spectroscopy.observation",
        re.compile(
            r"(?P<span>\bwe\s+(?:have\s+)?obtained\s+"
            r"(?:(?:an?|the)\s+)?"
            r"(?:(?:optical|NIR|near[- ]infrared|UV|X[- ]ray)\s+)?"
            r"spectrum\b)",
            re.IGNORECASE,
        ),
        0,
    ),
    _SpectroscopyRule(
        "spectroscopy.observation",
        re.compile(
            rf"(?P<span>\bwe\s+observed\b[^.!?;\n]{{0,120}}?"
            rf"\b(?:with|using)\s+(?:the\s+)?{_SPECTROGRAPH}"
            rf"\s+(?:spectrograph|spectrometer))",
            re.IGNORECASE,
        ),
        0,
    ),
    _SpectroscopyRule(
        "spectroscopy.observation",
        re.compile(
            r"(?P<span>\b(?:(?:an?|the)\s+)?"
            r"spectroscopic\s+observations?\b)",
            re.IGNORECASE,
        ),
        1,
    ),
    _SpectroscopyRule(
        "spectroscopy.observation",
        re.compile(
            r"(?P<span>\b(?:the\s+)?spectrum\s+was\s+obtained\b)",
            re.IGNORECASE,
        ),
        1,
    ),
    _SpectroscopyRule(
        "spectroscopy.observation",
        re.compile(
            rf"(?P<span>\b{_SPECTROGRAPH}\s+"
            rf"(?:spectrograph|spectrometer)\b)",
            re.IGNORECASE,
        ),
        2,
    ),
    _SpectroscopyRule(
        "spectroscopy.observation",
        re.compile(
            r"(?P<span>\bspectroscopic\s+classification\b)",
            re.IGNORECASE,
        ),
        2,
    ),
    _SpectroscopyRule(
        "spectroscopy.observation",
        re.compile(
            r"(?P<span>\bspectroscopy\b)",
            re.IGNORECASE,
        ),
        3,
    ),
    _SpectroscopyRule(
        "spectroscopy.spectrum",
        re.compile(
            r"(?P<span>\b(?:"
            r"(?:(?:our|the|an?|combined)\s+)?"
            r"(?:optical|NIR|near[- ]infrared)\s+(?:spectrum|spectra)|"
            r"(?:our|the|an?|combined)\s+(?:spectrum|spectra)"
            r")\b)",
            re.IGNORECASE,
        ),
        3,
    ),
    _SpectroscopyRule(
        "spectroscopy.features",
        re.compile(
            rf"(?P<span>\b{_LINE_LIST}\s+absorption\s+"
            rf"(?:features|lines)\b)",
            re.IGNORECASE,
        ),
        0,
    ),
    _SpectroscopyRule(
        "spectroscopy.features",
        re.compile(
            rf"(?P<span>(?<!\w){_LINE_TOKEN}\s+emission\s+lines?\b)",
            re.IGNORECASE,
        ),
        0,
    ),
    _SpectroscopyRule(
        "spectroscopy.features",
        re.compile(
            rf"(?P<span>(?<!\w){_LINE_TOKEN}"
            rf"(?:\s+doublet)?\s+in\s+(?:absorption|emission)\b)",
            re.IGNORECASE,
        ),
        0,
    ),
    _SpectroscopyRule(
        "spectroscopy.features",
        re.compile(
            r"(?P<span>\bP[- ]Cygni\s+profile"
            r"(?:\s+of\s+(?:the\s+)?H[- ]?(?:alpha|beta)\s+line)?)",
            re.IGNORECASE,
        ),
        0,
    ),
    _SpectroscopyRule(
        "spectroscopy.features",
        re.compile(
            r"(?P<span>\b(?:(?:multiple|several|narrow|broad|metal)\s+)?"
            r"(?:absorption\s+(?:features|lines)|emission\s+lines|"
            r"flash[- ]ionisation\s+features|spectral\s+features)\b)",
            re.IGNORECASE,
        ),
        2,
    ),
    _SpectroscopyRule(
        "spectroscopy.features",
        re.compile(
            r"(?P<span>\b(?:(?:featureless|red|blue|faint|strong|weak)\s+)?"
            r"continuum\b)",
            re.IGNORECASE,
        ),
        4,
        requires_spectral_context=True,
    ),
)


class SpectroscopyExtractor:
    extractor_id = "spectroscopy-v1"
    extractor_version = "0.1"

    def extract(self, doc: CanonicalDocument) -> list[EventEvidenceAnnotation]:
        annotations: list[EventEvidenceAnnotation] = []
        candidates = resolve_spectroscopy_overlaps(
            find_spectroscopy_candidates(doc.rendered_text)
        )
        for candidate in candidates:
            annotation = EventEvidenceAnnotation(
                circular_id=doc.circular_id,
                text_sha256=doc.text_sha256,
                span_start=candidate.span_start,
                span_end=candidate.span_end,
                text=candidate.raw,
                label="SPECTROSCOPY",
                target=candidate.target,
                certainty="confirmed",
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
                    "Spectroscopy annotation failed offset verification: "
                    f"{annotation.span_start}-{annotation.span_end}"
                )
            annotations.append(annotation)
        return annotations


def find_spectroscopy_candidates(text: str) -> list[SpectroscopyCandidate]:
    candidates: list[SpectroscopyCandidate] = []
    for rule in _RULES:
        for match in rule.pattern.finditer(text):
            span_start, span_end = _trim_span(text, *match.span("span"))
            if span_start >= span_end:
                continue
            if _is_followup_only(text, span_start, span_end):
                continue
            if (
                rule.rule_id == "spectroscopy.observation"
                and text[span_start:span_end].lower() == "spectroscopy"
                and _is_program_name_context(text, span_start, span_end)
            ):
                continue
            if rule.requires_spectral_context and not _has_spectral_context(
                text,
                span_start,
                span_end,
            ):
                continue
            if rule.rule_id == "spectroscopy.spectrum" and not _is_optical_spectrum(
                text,
                span_start,
                span_end,
            ):
                continue
            candidates.append(
                SpectroscopyCandidate(
                    span_start=span_start,
                    span_end=span_end,
                    raw=text[span_start:span_end],
                    target=_target(text, span_start, span_end),
                    rule_id=rule.rule_id,
                    priority=rule.priority,
                )
            )
    return sorted(
        candidates,
        key=lambda item: (
            item.span_start,
            item.priority,
            item.span_end,
            item.rule_id,
        ),
    )


def resolve_spectroscopy_overlaps(
    candidates: list[SpectroscopyCandidate],
) -> list[SpectroscopyCandidate]:
    selected: list[SpectroscopyCandidate] = []
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
        if any(_overlaps(candidate, existing) for existing in selected):
            continue
        selected.append(candidate)
    return sorted(
        selected,
        key=lambda item: (item.span_start, item.span_end, item.rule_id),
    )


def spectroscopy_deferral_reason(
    text: str,
    start: int,
    end: int,
) -> str | None:
    sentence_start, sentence_end = sentence_bounds(text, start, end)
    sentence = text[sentence_start:sentence_end]
    if _CLASSIFICATION_RE.search(sentence) and not _SPECTRAL_CONTEXT_RE.search(
        sentence
    ):
        return "CLASSIFICATION"
    if _BARE_REDSHIFT_RE.search(sentence) and not re.search(
        r"\b(?:obtained|observed|detect|identify|shows?|reveals?)\b",
        sentence,
        re.IGNORECASE,
    ):
        return "REDSHIFT"
    return None


def sentence_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    left = start
    while left > 0 and text[left - 1] not in ".!?;\n":
        left -= 1
    right = end
    while right < len(text) and text[right] not in ".!?;\n":
        right += 1
    return left, right


def _target(text: str, start: int, end: int) -> str:
    raw = text[start:end]
    if _COUNTERPART_SPECTROSCOPY_RE.search(raw):
        return "counterpart"
    sentence_start, sentence_end = sentence_bounds(text, start, end)
    sentence = text[sentence_start:sentence_end]
    if _EVENT_SPECTRUM_RE.search(raw):
        return "event"
    if re.search(
        r"\b(?:spectrum|spectra)\s+of\s+(?:the\s+)?(?:burst|GRB|event)\b",
        sentence,
        re.IGNORECASE,
    ):
        return "event"
    return "counterpart"


def _is_followup_only(text: str, start: int, end: int) -> bool:
    sentence_start, sentence_end = sentence_bounds(text, start, end)
    sentence = text[sentence_start:sentence_end]
    return bool(
        _FOLLOWUP_ONLY_RE.search(sentence)
        and not re.search(
            r"\b(?:obtained|observed|performed|carried\s+out)\b",
            sentence,
            re.IGNORECASE,
        )
    )


def _is_program_name_context(text: str, start: int, end: int) -> bool:
    sentence_start, sentence_end = sentence_bounds(text, start, end)
    return bool(_PROGRAM_NAME_RE.search(text[sentence_start:sentence_end]))


def _has_spectral_context(text: str, start: int, end: int) -> bool:
    raw = text[start:end].strip()
    if not _CONTINUUM_ONLY_RE.fullmatch(raw):
        return True
    sentence_start, sentence_end = sentence_bounds(text, start, end)
    sentence = text[sentence_start:sentence_end]
    context = f"{sentence[: start - sentence_start]} {sentence[end - sentence_start :]}"
    return bool(_SPECTRAL_CONTEXT_RE.search(context))


def _is_optical_spectrum(text: str, start: int, end: int) -> bool:
    sentence_start, sentence_end = sentence_bounds(text, start, end)
    sentence = text[sentence_start:sentence_end]
    if _HIGH_ENERGY_SPECTRUM_CONTEXT_RE.search(sentence):
        return False
    return bool(_OPTICAL_SPECTRUM_CONTEXT_RE.search(sentence))


def _trim_span(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and (text[end - 1].isspace() or text[end - 1] in ",;:"):
        end -= 1
    return start, end


def _overlaps(
    first: SpectroscopyCandidate,
    second: SpectroscopyCandidate,
) -> bool:
    return first.span_start < second.span_end and second.span_start < first.span_end


__all__ = [
    "SPECTROSCOPY_SIGNAL_RE",
    "SpectroscopyCandidate",
    "SpectroscopyExtractor",
    "find_spectroscopy_candidates",
    "resolve_spectroscopy_overlaps",
    "sentence_bounds",
    "spectroscopy_deferral_reason",
]
