"""Provisional tagsets for PHOTOMETRIC_MEASUREMENT annotations.

The real INCEpTION layer definition in data/inception/TypeSystem.xml is:

Type: webanno.custom.PHOTOMETRIC_MEASUREMENT
Supertype: uima.tcas.Annotation
Features:
- measurement_type: uima.cas.String
- target: uima.cas.String
- certainty: uima.cas.String
- magnitude_or_limit: uima.cas.String
- unit: uima.cas.String
- photometric_band: uima.cas.String
- obs_time_raw: uima.cas.String
- obs_time_type: uima.cas.String
- obs_time_reference: uima.cas.String
- exposure_time_raw: uima.cas.String
- timezone_raw: uima.cas.String
- instrument: uima.cas.String
- comment: uima.cas.String

The values below are the CP1.1 values verified in INCEpTION Settings -> Tagsets.
"""

from skyportal_corpus.extraction_v2.tagsets import CERTAINTIES, TARGETS

MEASUREMENT_TYPES = frozenset({"detection", "upper_limit", "non_detection", "unclear"})

OBS_TIME_TYPES = frozenset(
    {
        "utc_datetime",
        "mjd",
        "jd",
        "relative_to_trigger",
        "start_time_plus_exposure",
        "other_timezone",
        "calendar_date",
        "unclear",
    }
)

OBS_TIME_REFERENCES = frozenset(
    {
        "absolute_time",
        "trigger_time_t0",
        "observation_start",
        "observation_mid",
        "unknown",
    }
)

PHOTOMETRIC_SYSTEMS = frozenset({"AB", "Vega", "unknown"})

# Internal-only provenance for the ``instrument`` field. Not an INCEpTION
# feature; it exists to audit attribution and support Round 2 safely.
INSTRUMENT_PROVENANCES = frozenset(
    {"explicit_column", "inferred_column", "prose_same_sentence"}
)

__all__ = [
    "CERTAINTIES",
    "INSTRUMENT_PROVENANCES",
    "MEASUREMENT_TYPES",
    "OBS_TIME_REFERENCES",
    "OBS_TIME_TYPES",
    "PHOTOMETRIC_SYSTEMS",
    "TARGETS",
]
