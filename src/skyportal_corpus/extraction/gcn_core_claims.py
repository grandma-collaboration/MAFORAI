"""Helpers for extracting structured claims from matched GCN circular bodies."""

from __future__ import annotations

import argparse
import json
import logging
import re
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd

from ..core import resolve_project_path
from .gcn_event_matching import (
    DEFAULT_GCN_EVENT_MATCHING_ASSOCIATIONS_PATH,
    DEFAULT_GCN_EVENT_MATCHING_SUMMARY_PATH,
    ensure_output_dir,
    filter_match_summary_to_matched,
    load_json_object,
    normalize_whitespace,
    save_json,
)

DEFAULT_GCN_EVENT_EXTRACTION_OUTPUT_DIR = "data/interim/gcn/event_extraction"
DEFAULT_GCN_CORE_CLAIMS_PATH = (
    f"{DEFAULT_GCN_EVENT_EXTRACTION_OUTPUT_DIR}/gcn_core_claims.parquet"
)
DEFAULT_GCN_CORE_CLAIMS_SUMMARY_PATH = (
    f"{DEFAULT_GCN_EVENT_EXTRACTION_OUTPUT_DIR}/event_gcn_claim_summary.csv"
)

CORE_CLAIMS_CSV = "gcn_core_claims.csv"
CORE_CLAIMS_PARQUET = "gcn_core_claims.parquet"
EXTRACTION_REPORT_JSON = "extraction_report.json"
EXTRACTION_ERRORS_JSONL = "extraction_errors.jsonl"
EVENT_CLAIM_SUMMARY_CSV = "event_gcn_claim_summary.csv"

CORE_CLAIM_COLUMNS = [
    "source_id",
    "circular_id",
    "year",
    "created_at_iso",
    "subject",
    "claim_type",
    "raw_value",
    "normalized_value",
    "instrument_if_any",
    "evidence_text",
    "extraction_rule",
    "claim_confidence",
    "source_field",
    "raw_file_path",
    "best_match_score",
    "best_confidence_level",
]
EVENT_CLAIM_SUMMARY_COLUMNS = [
    "source_id",
    "n_claims",
    "n_circulars_with_claims",
    "has_trigger_time",
    "has_t90",
    "has_duration_class",
    "has_redshift",
    "has_counterpart",
    "has_detection",
    "has_non_detection",
    "has_upper_limit",
    "has_negative_interpretation",
    "has_retraction",
    "has_spectroscopy",
    "has_host_candidate",
    "instruments_found",
    "classification_flags",
    "best_redshift_value",
    "best_redshift_method",
    "best_t90_seconds",
    "best_duration_class",
]

CLASSIFICATION_NEGATIVE_INTERPRETATION_VALUES = {
    "false_alarm",
    "false_trigger",
    "not_grb",
    "solar_flare",
    "stellar_flare",
}
DETECTION_NEGATIVE_INTERPRETATION_VALUES = {
    "false_alarm",
    "not_grb",
}
RETRACTION_VALUES = {"retraction"}
DETECTION_VALUES = {"detected"}
NON_DETECTION_VALUES = {
    "non_detection",
    "not_grb",
}
INSTRUMENT_PATTERNS = [
    ("Swift/BAT-GUANO", re.compile(r"\bSwift/BAT-GUANO\b", re.IGNORECASE)),
    ("Swift/BAT", re.compile(r"\bSwift(?: Burst Alert Telescope \(BAT\)|/BAT|-BAT)\b", re.IGNORECASE)),
    ("Swift/XRT", re.compile(r"\bSwift(?: XRT|/XRT|-XRT)\b", re.IGNORECASE)),
    ("Swift/UVOT", re.compile(r"\bSwift/UVOT\b", re.IGNORECASE)),
    ("Fermi GBM", re.compile(r"\bFermi(?: Gamma-ray Burst Monitor \(GBM\)| GBM)\b", re.IGNORECASE)),
    ("Fermi-LAT", re.compile(r"\bFermi-LAT\b", re.IGNORECASE)),
    ("SVOM/ECLAIRs", re.compile(r"\bSVOM/ECLAIRs\b", re.IGNORECASE)),
    ("SVOM/GRM", re.compile(r"\bSVOM/GRM\b", re.IGNORECASE)),
    ("SVOM/MXT", re.compile(r"\bSVOM/MXT\b", re.IGNORECASE)),
    ("SVOM/C-GFT", re.compile(r"\bSVOM/C-GFT\b", re.IGNORECASE)),
    ("EP-WXT", re.compile(r"\bEP-WXT\b", re.IGNORECASE)),
    ("EP-FXT", re.compile(r"\bEP-FXT\b", re.IGNORECASE)),
    ("Einstein Probe", re.compile(r"\bEinstein Probe\b", re.IGNORECASE)),
    ("MAXI/GSC", re.compile(r"\bMAXI/GSC\b", re.IGNORECASE)),
    ("INTEGRAL/SPI-ACS", re.compile(r"\bINTEGRAL/SPI-ACS\b", re.IGNORECASE)),
    ("IceCube", re.compile(r"\bIceCube\b", re.IGNORECASE)),
    ("LIGO/Virgo/KAGRA", re.compile(r"\bLIGO/Virgo/KAGRA\b", re.IGNORECASE)),
    ("VLT/X-shooter", re.compile(r"\bVLT/X-shooter\b", re.IGNORECASE)),
    ("X-shooter", re.compile(r"\bX-shooter\b", re.IGNORECASE)),
    ("GTC/OSIRIS+", re.compile(r"\b(?:GTC/OSIRIS\+|OSIRIS\+/GTC)\b", re.IGNORECASE)),
    ("Liverpool Telescope", re.compile(r"\bLiverpool Telescope\b", re.IGNORECASE)),
    ("MASTER-Net", re.compile(r"\bMASTER(?:-Net)?\b", re.IGNORECASE)),
    ("COLIBRI", re.compile(r"\bCOLIBR[IÍ]\b", re.IGNORECASE)),
    ("GOTO", re.compile(r"\bGOTO\b", re.IGNORECASE)),
    ("REM", re.compile(r"\bREM\b", re.IGNORECASE)),
    ("KAIT", re.compile(r"\bKAIT\b", re.IGNORECASE)),
    ("VLA", re.compile(r"\bVLA\b", re.IGNORECASE)),
    ("Konus-Wind", re.compile(r"\bKonus-Wind\b", re.IGNORECASE)),
    ("LCO", re.compile(r"\bLCO\b", re.IGNORECASE)),
    ("TNG", re.compile(r"\bTNG\b", re.IGNORECASE)),
    ("OHP/T193", re.compile(r"\bOHP/T193\b", re.IGNORECASE)),
]
TRIGGER_CONTEXT_PATTERN = re.compile(
    r"\b(trigger|triggered|detected|located|t0|burst)\b",
    re.IGNORECASE,
)
EXPLICIT_T0_PATTERN = re.compile(r"\bT0\s*[:=]\s*([^\n.;]+)", re.IGNORECASE)
TIME_TB_PATTERN = re.compile(r"\b(?:TimeTb|Tb)\s*[:=]\s*([^\n.;]+)")
ISO_TIME_PATTERN = re.compile(r"\b(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s*(UTC|UT)?\b")
TRIGGER_UT_PATTERN = re.compile(
    r"\bAt\s+(\d{1,2}:\d{2}:\d{2}(?:\.\d+)?)\s*UT(?:\s+on\s+[0-9]{1,2}\s+\w+\s+[0-9]{4})?",
    re.IGNORECASE,
)
MJD_PATTERN = re.compile(r"\bMJD\s*[:=]?\s*(\d{5}(?:\.\d+)?)", re.IGNORECASE)
RELATIVE_T_PATTERN = re.compile(r"\bT\+\s*([0-9]+(?:\.\d+)?)\s*(s|sec|min|hr|day)s?\b", re.IGNORECASE)
T90_PATTERNS = [
    ("duration_t90_explicit", re.compile(r"\bT90\b[^.\n;]{0,120}?([0-9]+(?:\.\d+)?)\s*(s|sec|seconds)\b", re.IGNORECASE), "high"),
    ("duration_t90_about", re.compile(r"\bduration of about\s*([0-9]+(?:\.\d+)?)\s*(s|sec|seconds)\b", re.IGNORECASE), "medium"),
]
DURATION_CLASS_PATTERNS = [
    ("long", re.compile(r"\blong(?:-duration)?\s+GRB\b", re.IGNORECASE), "high", "duration_class_long"),
    ("short", re.compile(r"\bshort(?:-duration)?\s+GRB\b", re.IGNORECASE), "high", "duration_class_short"),
    ("long", re.compile(r"\blikely\s+LONG\s+GRB\b", re.IGNORECASE), "medium", "duration_class_long_likely"),
    ("short", re.compile(r"\brelatively\s+short-duration\s+GRB\b", re.IGNORECASE), "medium", "duration_class_short_relative"),
]
RED_SHIFT_CONTEXT_PATTERN = re.compile(
    r"(redshift|photo-z|photometric redshift|spectroscopic redshift|host redshift|common redshift|emission lines|lyman)",
    re.IGNORECASE,
)
RED_SHIFT_PATTERNS = [
    ("redshift_z_equals", re.compile(r"\bz\s*([=~])\s*([0-9]+(?:\.\d+)?)", re.IGNORECASE)),
    ("redshift_photoz", re.compile(r"\bphoto-z\b[^0-9]{0,20}([0-9]+(?:\.\d+)?)", re.IGNORECASE)),
]
COUNTERPART_PATTERNS = [
    ("optical", re.compile(r"\boptical counterpart\b", re.IGNORECASE), "counterpart", "high"),
    ("xray", re.compile(r"\bX-ray counterpart\b", re.IGNORECASE), "counterpart", "high"),
    ("radio", re.compile(r"\bradio counterpart\b", re.IGNORECASE), "counterpart", "high"),
    ("nir", re.compile(r"\bNIR counterpart\b", re.IGNORECASE), "counterpart", "high"),
    ("uv", re.compile(r"\bUV counterpart\b", re.IGNORECASE), "counterpart", "high"),
    ("optical", re.compile(r"\boptical afterglow\b", re.IGNORECASE), "afterglow", "high"),
    ("xray", re.compile(r"\bX-ray afterglow\b", re.IGNORECASE), "afterglow", "high"),
    ("nir", re.compile(r"\bNIR afterglow\b", re.IGNORECASE), "afterglow", "high"),
    ("candidate_counterpart", re.compile(r"\bcandidate counterpart\b", re.IGNORECASE), "candidate", "medium"),
]
UPPER_LIMIT_BAND_PATTERN = re.compile(
    r"\b([ugrizYJHKRIVB])['’]?\s*>\s*([0-9]+(?:\.\d+)?)",
    re.IGNORECASE,
)
UPPER_LIMIT_CONTEXT_PATTERN = re.compile(
    r"(upper limit|limiting magnitude|3-sigma limit|5-sigma limit)",
    re.IGNORECASE,
)
UPPER_LIMIT_NUMERIC_PATTERN = re.compile(
    r"\b([0-9]+(?:\.\d+)?)\s*mag\b",
    re.IGNORECASE,
)
SPECTROSCOPY_PATTERNS = [
    ("spectroscopy_keyword", re.compile(r"\bspectroscop(?:y|ic)\b|\bspectrum\b", re.IGNORECASE), "high"),
    ("spectroscopy_instrument", re.compile(r"\b(X-shooter|Gemini|Keck|GTC|OSIRIS\+)\b", re.IGNORECASE), "medium"),
]
HOST_PATTERNS = [
    ("host_galaxy", re.compile(r"\bhost galaxy\b", re.IGNORECASE), "host_galaxy", "high"),
    ("nearby_galaxy", re.compile(r"\bnearby galaxy\b", re.IGNORECASE), "nearby_galaxy", "medium"),
    ("proposed_host", re.compile(r"\bproposed host\b", re.IGNORECASE), "proposed_host", "medium"),
    ("associated_galaxy", re.compile(r"\bassociated galaxy\b", re.IGNORECASE), "associated_galaxy", "medium"),
    ("host_candidate", re.compile(r"\bhost candidate\b|\bgalaxy candidate\b", re.IGNORECASE), "host_candidate", "medium"),
]
CLASSIFICATION_PATTERNS = [
    ("candidate_afterglow", re.compile(r"\bcandidate afterglow\b", re.IGNORECASE), "candidate_afterglow", "medium"),
    ("afterglow", re.compile(r"\bafterglow\b", re.IGNORECASE), "afterglow", "medium"),
    ("xray_transient", re.compile(r"\bX-ray transient\b", re.IGNORECASE), "xray_transient", "high"),
    ("kilonova_candidate", re.compile(r"\bkilonova candidate\b", re.IGNORECASE), "kilonova_candidate", "medium"),
    ("supernova", re.compile(r"\bsupernova\b", re.IGNORECASE), "supernova", "medium"),
    ("type_ia", re.compile(r"\bType Ia\b", re.IGNORECASE), "type_ia", "high"),
    ("type_ic_bl", re.compile(r"\bType Ic-BL\b", re.IGNORECASE), "type_ic_bl", "high"),
    ("agn", re.compile(r"\bAGN\b", re.IGNORECASE), "agn", "medium"),
    ("stellar_flare", re.compile(r"\bstellar flare\b", re.IGNORECASE), "stellar_flare", "high"),
    ("solar_flare", re.compile(r"\bsolar flare\b", re.IGNORECASE), "solar_flare", "high"),
    ("not_grb", re.compile(r"\bnot a GRB\b|\bis not a GRB\b", re.IGNORECASE), "not_grb", "high"),
    ("false_alarm", re.compile(r"\bfalse alarm\b", re.IGNORECASE), "false_alarm", "medium"),
    ("false_trigger", re.compile(r"\bfalse trigger\b", re.IGNORECASE), "false_trigger", "high"),
    ("retraction", re.compile(r"\bretraction\b", re.IGNORECASE), "retraction", "high"),
    ("galactic_transient", re.compile(r"\bGalactic Transient\b", re.IGNORECASE), "galactic_transient", "medium"),
]
def setup_console_logging() -> None:
    """Configure simple console logging for one run."""
    logging.basicConfig(level=logging.INFO, format="%(message)s", force=True)


def build_evidence_text(text: str, span: tuple[int, int], *, max_chars: int = 500) -> str:
    """Build a short evidence fragment around one matched span."""
    before = text[: span[0]]
    line_start = before.rfind("\n") + 1
    line_end = text.find("\n", span[1])
    if line_end < 0:
        line_end = len(text)

    line = normalize_whitespace(text[line_start:line_end])
    if line and len(line) <= max_chars:
        return line

    radius = max_chars // 2
    start = max(0, span[0] - radius)
    end = min(len(text), span[1] + radius)
    fragment = normalize_whitespace(text[start:end])
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{fragment}{suffix}"[:max_chars]


def detect_instruments_in_text(text: str) -> list[str]:
    """Extract unique instrument names from one text fragment."""
    instruments: list[str] = []
    for canonical_name, pattern in INSTRUMENT_PATTERNS:
        if pattern.search(text) and canonical_name not in instruments:
            instruments.append(canonical_name)
    return instruments


def detect_first_instrument(text: str) -> str:
    """Return the first known instrument mention found in one text fragment."""
    instruments = detect_instruments_in_text(text)
    return instruments[0] if instruments else ""


def normalize_decimal_string(value: str) -> str:
    """Normalize one decimal value into a compact string."""
    numeric = float(value)
    return f"{numeric:.6f}".rstrip("0").rstrip(".")


def claim_confidence_rank(value: str) -> int:
    """Return a small ranking number for one claim confidence label."""
    return {"high": 0, "medium": 1, "low": 2}.get(value, 9)


def normalize_json_safe_value(value: Any) -> Any:
    """Convert pandas/numpy values into JSON-safe native values."""
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except (AttributeError, ValueError):
            return value
    return value


def normalize_json_safe_record(record: dict[str, Any]) -> dict[str, Any]:
    """Normalize one mapping so it can be written as plain JSON."""
    return {
        str(key): normalize_json_safe_value(value)
        for key, value in record.items()
    }


def build_claim_record(
    *,
    association: dict[str, Any],
    claim_type: str,
    raw_value: str,
    normalized_value: str = "",
    instrument_if_any: str = "",
    evidence_text: str = "",
    extraction_rule: str = "",
    claim_confidence: str = "medium",
    source_field: str = "body",
) -> dict[str, Any]:
    """Build one structured claim record."""
    return {
        "source_id": str(association["source_id"]),
        "circular_id": str(association["circular_id"]),
        "year": int(association["year"]),
        "created_at_iso": str(association["created_at_iso"]),
        "subject": str(association["subject"]),
        "claim_type": claim_type,
        "raw_value": raw_value,
        "normalized_value": normalized_value,
        "instrument_if_any": instrument_if_any,
        "evidence_text": evidence_text[:500],
        "extraction_rule": extraction_rule,
        "claim_confidence": claim_confidence,
        "source_field": source_field,
        "raw_file_path": str(association["raw_file_path"]),
        "best_match_score": int(association["best_match_score"]),
        "best_confidence_level": str(association["best_confidence_level"]),
    }


def deduplicate_claim_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate repeated claims within one extraction run."""
    deduplicated: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        key = (
            row["source_id"],
            row["circular_id"],
            row["claim_type"],
            row["normalized_value"] or row["raw_value"],
            row["instrument_if_any"],
            row["source_field"],
            row["extraction_rule"],
        )
        existing = deduplicated.get(key)
        if existing is None:
            deduplicated[key] = row
            continue

        existing_key = (
            claim_confidence_rank(str(existing["claim_confidence"])),
            len(str(existing["evidence_text"])),
        )
        incoming_key = (
            claim_confidence_rank(str(row["claim_confidence"])),
            len(str(row["evidence_text"])),
        )
        if incoming_key < existing_key:
            deduplicated[key] = row

    return list(deduplicated.values())


def extract_instrument_claims(
    association: dict[str, Any],
    text: str,
    *,
    source_field: str,
) -> list[dict[str, Any]]:
    """Extract instrument mentions from one text field."""
    rows: list[dict[str, Any]] = []
    for canonical_name, pattern in INSTRUMENT_PATTERNS:
        for match in pattern.finditer(text):
            raw_value = normalize_whitespace(match.group(0))
            rows.append(
                build_claim_record(
                    association=association,
                    claim_type="instrument_mention",
                    raw_value=raw_value,
                    normalized_value=canonical_name,
                    instrument_if_any=canonical_name,
                    evidence_text=build_evidence_text(text, match.span()),
                    extraction_rule="instrument_catalog",
                    claim_confidence="high",
                    source_field=source_field,
                )
            )
    return rows


def extract_trigger_time_claims(
    association: dict[str, Any],
    text: str,
    *,
    source_field: str,
) -> list[dict[str, Any]]:
    """Extract explicit trigger/T0-like time claims."""
    rows: list[dict[str, Any]] = []

    for match in EXPLICIT_T0_PATTERN.finditer(text):
        raw_value = normalize_whitespace(match.group(1))
        rows.append(
            build_claim_record(
                association=association,
                claim_type="trigger_time_t0",
                raw_value=raw_value,
                normalized_value=raw_value,
                instrument_if_any=detect_first_instrument(build_evidence_text(text, match.span())),
                evidence_text=build_evidence_text(text, match.span()),
                extraction_rule="trigger_t0_explicit",
                claim_confidence="high",
                source_field=source_field,
            )
        )

    for match in TIME_TB_PATTERN.finditer(text):
        raw_value = normalize_whitespace(match.group(1))
        rows.append(
            build_claim_record(
                association=association,
                claim_type="trigger_time_t0",
                raw_value=raw_value,
                normalized_value=raw_value,
                instrument_if_any=detect_first_instrument(build_evidence_text(text, match.span())),
                evidence_text=build_evidence_text(text, match.span()),
                extraction_rule="trigger_tb_explicit",
                claim_confidence="medium",
                source_field=source_field,
            )
        )

    for match in ISO_TIME_PATTERN.finditer(text):
        evidence_text = build_evidence_text(text, match.span())
        if not TRIGGER_CONTEXT_PATTERN.search(evidence_text) and source_field != "subject":
            continue
        raw_value = normalize_whitespace(match.group(0))
        rows.append(
            build_claim_record(
                association=association,
                claim_type="trigger_time_t0",
                raw_value=raw_value,
                normalized_value=match.group(1),
                instrument_if_any=detect_first_instrument(evidence_text),
                evidence_text=evidence_text,
                extraction_rule="trigger_iso_timestamp",
                claim_confidence="high" if TRIGGER_CONTEXT_PATTERN.search(evidence_text) else "medium",
                source_field=source_field,
            )
        )

    for match in MJD_PATTERN.finditer(text):
        evidence_text = build_evidence_text(text, match.span())
        rows.append(
            build_claim_record(
                association=association,
                claim_type="trigger_time_t0",
                raw_value=normalize_whitespace(match.group(0)),
                normalized_value=match.group(1),
                instrument_if_any=detect_first_instrument(evidence_text),
                evidence_text=evidence_text,
                extraction_rule="trigger_mjd",
                claim_confidence="high",
                source_field=source_field,
            )
        )

    for match in TRIGGER_UT_PATTERN.finditer(text):
        evidence_text = build_evidence_text(text, match.span())
        if not TRIGGER_CONTEXT_PATTERN.search(evidence_text):
            continue
        raw_value = normalize_whitespace(match.group(0))
        rows.append(
            build_claim_record(
                association=association,
                claim_type="trigger_time_t0",
                raw_value=raw_value,
                normalized_value=match.group(1),
                instrument_if_any=detect_first_instrument(evidence_text),
                evidence_text=evidence_text,
                extraction_rule="trigger_ut_context",
                claim_confidence="high",
                source_field=source_field,
            )
        )

    for match in RELATIVE_T_PATTERN.finditer(text):
        evidence_text = build_evidence_text(text, match.span())
        rows.append(
            build_claim_record(
                association=association,
                claim_type="trigger_time_t0",
                raw_value=normalize_whitespace(match.group(0)),
                normalized_value=normalize_whitespace(match.group(0)),
                instrument_if_any=detect_first_instrument(evidence_text),
                evidence_text=evidence_text,
                extraction_rule="trigger_relative_t",
                claim_confidence="medium",
                source_field=source_field,
            )
        )

    return rows


def extract_duration_t90_claims(
    association: dict[str, Any],
    text: str,
    *,
    source_field: str,
) -> list[dict[str, Any]]:
    """Extract T90/duration values from one text field."""
    rows: list[dict[str, Any]] = []
    for extraction_rule, pattern, confidence in T90_PATTERNS:
        for match in pattern.finditer(text):
            evidence_text = build_evidence_text(text, match.span())
            rows.append(
                build_claim_record(
                    association=association,
                    claim_type="duration_t90",
                    raw_value=normalize_whitespace(match.group(0)),
                    normalized_value=normalize_decimal_string(match.group(1)),
                    instrument_if_any=detect_first_instrument(evidence_text),
                    evidence_text=evidence_text,
                    extraction_rule=extraction_rule,
                    claim_confidence=confidence,
                    source_field=source_field,
                )
            )
    return rows


def extract_duration_class_claims(
    association: dict[str, Any],
    text: str,
    *,
    source_field: str,
) -> list[dict[str, Any]]:
    """Extract short/long duration-class labels."""
    rows: list[dict[str, Any]] = []
    for normalized_value, pattern, confidence, extraction_rule in DURATION_CLASS_PATTERNS:
        for match in pattern.finditer(text):
            rows.append(
                build_claim_record(
                    association=association,
                    claim_type="duration_class",
                    raw_value=normalize_whitespace(match.group(0)),
                    normalized_value=normalized_value,
                    evidence_text=build_evidence_text(text, match.span()),
                    extraction_rule=extraction_rule,
                    claim_confidence=confidence,
                    source_field=source_field,
                )
            )
    return rows


def infer_redshift_method(evidence_text: str) -> str:
    """Infer a compact redshift method from one evidence line."""
    lowered = evidence_text.lower()
    if (
        "spectroscopic" in lowered
        or "spectrum" in lowered
        or "spectra" in lowered
        or "grism" in lowered
        or "absorption lines" in lowered
        or "emission lines" in lowered
        or "lyman" in lowered
    ):
        return "spectroscopic"
    if "photo-z" in lowered or "photometric" in lowered:
        return "photometric"
    if "host redshift" in lowered or "host galaxy" in lowered:
        return "host"
    if "~" in evidence_text or "tentative" in lowered or "?" in evidence_text:
        return "tentative"
    return "unknown"


def infer_redshift_confidence(evidence_text: str, method: str) -> str:
    """Infer a small confidence label for one redshift claim."""
    if method == "spectroscopic":
        return "high"
    if method in {"photometric", "host"}:
        return "medium"
    if method == "tentative":
        return "low"
    return "medium"


def extract_redshift_claims(
    association: dict[str, Any],
    text: str,
    *,
    source_field: str,
) -> list[dict[str, Any]]:
    """Extract redshift claims only when the surrounding context is strong."""
    rows: list[dict[str, Any]] = []
    for extraction_rule, pattern in RED_SHIFT_PATTERNS:
        for match in pattern.finditer(text):
            evidence_text = build_evidence_text(text, match.span())
            if not RED_SHIFT_CONTEXT_PATTERN.search(evidence_text):
                continue
            if re.search(r"\bmag z\b|\bz-band\b|\bfilter z\b", evidence_text, re.IGNORECASE):
                continue

            numeric_match = re.search(r"([0-9]+(?:\.\d+)?)", normalize_whitespace(match.group(0)))
            if numeric_match is None:
                continue

            method = infer_redshift_method(evidence_text)
            rows.append(
                build_claim_record(
                    association=association,
                    claim_type="redshift",
                    raw_value=normalize_whitespace(match.group(0)),
                    normalized_value=normalize_decimal_string(numeric_match.group(1)),
                    instrument_if_any=detect_first_instrument(evidence_text),
                    evidence_text=evidence_text,
                    extraction_rule=extraction_rule,
                    claim_confidence=infer_redshift_confidence(evidence_text, method),
                    source_field=source_field,
                )
            )
    return rows


def extract_counterpart_claims(
    association: dict[str, Any],
    text: str,
    *,
    source_field: str,
) -> list[dict[str, Any]]:
    """Extract counterpart-like claims from one text field."""
    rows: list[dict[str, Any]] = []
    for normalized_value, pattern, method, confidence in COUNTERPART_PATTERNS:
        for match in pattern.finditer(text):
            evidence_text = build_evidence_text(text, match.span())
            rows.append(
                build_claim_record(
                    association=association,
                    claim_type="counterpart_type",
                    raw_value=normalize_whitespace(match.group(0)),
                    normalized_value=normalized_value,
                    instrument_if_any=detect_first_instrument(evidence_text),
                    evidence_text=evidence_text,
                    extraction_rule=f"counterpart_{method}",
                    claim_confidence=confidence,
                    source_field=source_field,
                )
            )
    return rows


def extract_detection_status_claims(
    association: dict[str, Any],
    text: str,
    *,
    source_field: str,
) -> list[dict[str, Any]]:
    """Extract positive/negative detection-state claims line by line."""
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        evidence_text = normalize_whitespace(line)
        if not evidence_text:
            continue

        lowered = evidence_text.lower()
        raw_value = ""
        normalized_value = ""
        extraction_rule = ""
        confidence = "medium"

        if "is not a grb" in lowered or "not a grb" in lowered:
            raw_value = "not a GRB"
            normalized_value = "not_grb"
            extraction_rule = "detection_not_grb"
            confidence = "high"
        elif "false alarm" in lowered:
            raw_value = "false alarm"
            normalized_value = "false_alarm"
            extraction_rule = "detection_false_alarm"
            confidence = "medium"
        elif (
            "we do not detect" in lowered
            or "we did not detect" in lowered
            or "not detected" in lowered
            or "no detection" in lowered
            or "no source was detected" in lowered
        ):
            raw_value = evidence_text
            normalized_value = "non_detection"
            extraction_rule = "detection_negative"
            confidence = "high"
        elif "upper limit" in lowered or "limiting magnitude" in lowered:
            raw_value = evidence_text
            normalized_value = "upper_limit"
            extraction_rule = "detection_upper_limit"
            confidence = "high"
        elif (
            "we detect" in lowered
            or "was detected" in lowered
            or "is detected" in lowered
            or "we found" in lowered
            or "was found" in lowered
            or "counterpart was found" in lowered
            or "afterglow is well detected" in lowered
            or "ot detection" in lowered
            or "afterglow detection" in lowered
        ):
            raw_value = evidence_text
            normalized_value = "detected"
            extraction_rule = "detection_positive"
            confidence = "high"

        if not normalized_value:
            continue

        rows.append(
            build_claim_record(
                association=association,
                claim_type="detection_status",
                raw_value=raw_value,
                normalized_value=normalized_value,
                instrument_if_any=detect_first_instrument(evidence_text),
                evidence_text=evidence_text[:500],
                extraction_rule=extraction_rule,
                claim_confidence=confidence,
                source_field=source_field,
            )
        )
    return rows


def extract_upper_limit_claims(
    association: dict[str, Any],
    text: str,
    *,
    source_field: str,
) -> list[dict[str, Any]]:
    """Extract simple upper-limit claims from one text field."""
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        evidence_text = normalize_whitespace(line)
        if not evidence_text:
            continue

        match = UPPER_LIMIT_BAND_PATTERN.search(evidence_text)
        if match is not None:
            rows.append(
                build_claim_record(
                    association=association,
                    claim_type="upper_limit_simple",
                    raw_value=normalize_whitespace(match.group(0)),
                    normalized_value=normalize_decimal_string(match.group(2)),
                    instrument_if_any=detect_first_instrument(evidence_text),
                    evidence_text=evidence_text[:500],
                    extraction_rule="upper_limit_band_gt",
                    claim_confidence="high",
                    source_field=source_field,
                )
            )
            continue

        if not UPPER_LIMIT_CONTEXT_PATTERN.search(evidence_text):
            continue

        numeric_match = UPPER_LIMIT_NUMERIC_PATTERN.search(evidence_text)
        if numeric_match is None:
            continue

        rows.append(
                build_claim_record(
                    association=association,
                    claim_type="upper_limit_simple",
                    raw_value=evidence_text,
                    normalized_value=normalize_decimal_string(numeric_match.group(1)),
                    instrument_if_any=detect_first_instrument(evidence_text),
                    evidence_text=evidence_text[:500],
                    extraction_rule="upper_limit_context",
                claim_confidence="high",
                source_field=source_field,
            )
        )
    return rows


def extract_spectroscopy_claims(
    association: dict[str, Any],
    text: str,
    *,
    source_field: str,
) -> list[dict[str, Any]]:
    """Extract spectroscopy mentions from one text field."""
    rows: list[dict[str, Any]] = []
    for extraction_rule, pattern, confidence in SPECTROSCOPY_PATTERNS:
        for match in pattern.finditer(text):
            evidence_text = build_evidence_text(text, match.span())
            instrument_name = detect_first_instrument(evidence_text)
            rows.append(
                build_claim_record(
                    association=association,
                    claim_type="spectroscopy_mention",
                    raw_value=normalize_whitespace(match.group(0)),
                    normalized_value="spectroscopy",
                    instrument_if_any=instrument_name,
                    evidence_text=evidence_text,
                    extraction_rule=extraction_rule,
                    claim_confidence=confidence,
                    source_field=source_field,
                )
            )
    return rows


def extract_host_candidate_claims(
    association: dict[str, Any],
    text: str,
    *,
    source_field: str,
) -> list[dict[str, Any]]:
    """Extract host-candidate mentions from one text field."""
    rows: list[dict[str, Any]] = []
    for extraction_rule, pattern, normalized_value, confidence in HOST_PATTERNS:
        for match in pattern.finditer(text):
            rows.append(
                build_claim_record(
                    association=association,
                    claim_type="host_candidate_mention",
                    raw_value=normalize_whitespace(match.group(0)),
                    normalized_value=normalized_value,
                    evidence_text=build_evidence_text(text, match.span()),
                    extraction_rule=extraction_rule,
                    claim_confidence=confidence,
                    source_field=source_field,
                )
            )
    return rows


def extract_classification_claims(
    association: dict[str, Any],
    text: str,
    *,
    source_field: str,
) -> list[dict[str, Any]]:
    """Extract conservative interpretation/classification mentions."""
    rows: list[dict[str, Any]] = []
    for extraction_rule, pattern, normalized_value, confidence in CLASSIFICATION_PATTERNS:
        for match in pattern.finditer(text):
            evidence_text = build_evidence_text(text, match.span())
            if normalized_value == "kilonova_candidate" and "kilonova-catcher" in evidence_text.lower():
                continue

            rows.append(
                build_claim_record(
                    association=association,
                    claim_type="classification_or_interpretation",
                    raw_value=normalize_whitespace(match.group(0)),
                    normalized_value=normalized_value,
                    instrument_if_any=detect_first_instrument(evidence_text),
                    evidence_text=evidence_text,
                    extraction_rule=extraction_rule,
                    claim_confidence=confidence,
                    source_field=source_field,
                )
            )
    return rows


def extract_claims_from_text(
    association: dict[str, Any],
    text: str,
    *,
    source_field: str,
) -> list[dict[str, Any]]:
    """Extract all configured claim families from one text field."""
    if not text.strip():
        return []

    rows: list[dict[str, Any]] = []
    rows.extend(extract_instrument_claims(association, text, source_field=source_field))
    rows.extend(extract_trigger_time_claims(association, text, source_field=source_field))
    rows.extend(extract_duration_t90_claims(association, text, source_field=source_field))
    rows.extend(extract_duration_class_claims(association, text, source_field=source_field))
    rows.extend(extract_redshift_claims(association, text, source_field=source_field))
    rows.extend(extract_counterpart_claims(association, text, source_field=source_field))
    rows.extend(extract_detection_status_claims(association, text, source_field=source_field))
    rows.extend(extract_upper_limit_claims(association, text, source_field=source_field))
    rows.extend(extract_spectroscopy_claims(association, text, source_field=source_field))
    rows.extend(extract_host_candidate_claims(association, text, source_field=source_field))
    rows.extend(extract_classification_claims(association, text, source_field=source_field))
    return rows


def load_raw_circular_payload(raw_file_path: str, cache: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Load one raw GCN circular JSON payload, using a small in-memory cache."""
    if raw_file_path in cache:
        return cache[raw_file_path]

    path = Path(raw_file_path)
    payload = load_json_object(path)
    cache[raw_file_path] = payload
    return payload


def build_association_dict(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize one association row into a small string-keyed mapping."""
    return {
        "source_id": str(row["source_id"]),
        "circular_id": str(row["circular_id"]),
        "year": int(row["year"]),
        "created_at_iso": str(row["created_at_iso"]),
        "subject": str(row["subject"]),
        "raw_file_path": str(row["raw_file_path"]),
        "best_match_score": int(row["best_match_score"]),
        "best_confidence_level": str(row["best_confidence_level"]),
    }


def extract_claims_for_association(
    association: dict[str, Any],
    *,
    raw_payload: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Extract all claim families for one source-circular association."""
    subject_text = association["subject"]
    body_text = ""
    if raw_payload is not None:
        raw_body = raw_payload.get("body")
        if isinstance(raw_body, str):
            body_text = raw_body

    rows: list[dict[str, Any]] = []
    rows.extend(extract_claims_from_text(association, subject_text, source_field="subject"))
    rows.extend(extract_claims_from_text(association, body_text, source_field="body"))
    return deduplicate_claim_rows(rows)


def write_error_record(path: Path, *, row: dict[str, Any], exc: Exception) -> None:
    """Append one extraction error record to a JSONL log."""
    error_record = {
        "source_id": str(row.get("source_id", "")),
        "circular_id": str(row.get("circular_id", "")),
        "raw_file_path": str(row.get("raw_file_path", "")),
        "error_type": type(exc).__name__,
        "error_message": str(exc),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(error_record, ensure_ascii=False) + "\n")


def run_gcn_core_claims_extract(args: argparse.Namespace) -> None:
    """Extract core structured claims from matched GCN circular bodies."""
    setup_console_logging()
    associations_path = resolve_project_path(args.associations_path)

    output_dir = ensure_output_dir(args.output_dir)
    errors_path = output_dir / EXTRACTION_ERRORS_JSONL
    errors_path.write_text("", encoding="utf-8")

    associations_dataframe = pd.read_parquet(associations_path)
    associations_rows = associations_dataframe.to_dict(orient="records")
    raw_cache: dict[str, dict[str, Any]] = {}
    claims_rows: list[dict[str, Any]] = []
    failed_rows = 0

    for row in associations_rows:
        association = build_association_dict(row)
        raw_payload: dict[str, Any] | None = None
        try:
            raw_payload = load_raw_circular_payload(association["raw_file_path"], raw_cache)
        except Exception as exc:
            failed_rows += 1
            write_error_record(errors_path, row=association, exc=exc)

        claims_rows.extend(extract_claims_for_association(association, raw_payload=raw_payload))

    claims_rows = deduplicate_claim_rows(claims_rows)
    claims_dataframe = pd.DataFrame(claims_rows, columns=CORE_CLAIM_COLUMNS)
    if not claims_dataframe.empty:
        claims_dataframe = claims_dataframe.sort_values(
            by=["source_id", "created_at_iso", "circular_id", "claim_type", "source_field"],
            kind="stable",
        ).reset_index(drop=True)

    csv_path = output_dir / CORE_CLAIMS_CSV
    parquet_path = output_dir / CORE_CLAIMS_PARQUET
    claims_dataframe.to_csv(csv_path, index=False)
    claims_dataframe.to_parquet(parquet_path, index=False)

    report = {
        "n_associations_read": len(associations_rows),
        "n_circulars_processed": len(associations_rows),
        "n_circulars_failed": failed_rows,
        "n_unique_raw_files": len({str(row["raw_file_path"]) for row in associations_rows}),
        "n_claims_extracted": len(claims_dataframe),
        "claims_by_type": dict(Counter(claims_dataframe["claim_type"])) if not claims_dataframe.empty else {},
        "claims_by_confidence": dict(Counter(claims_dataframe["claim_confidence"])) if not claims_dataframe.empty else {},
        "output_files": {
            "claims_csv": str(csv_path.resolve()),
            "claims_parquet": str(parquet_path.resolve()),
            "report": str((output_dir / EXTRACTION_REPORT_JSON).resolve()),
            "errors": str(errors_path.resolve()),
        },
    }
    save_json(output_dir / EXTRACTION_REPORT_JSON, report)

    logging.info("Associations read: %s", len(associations_rows))
    logging.info("Circulars processed: %s", len(associations_rows))
    logging.info("Circulars failed: %s", failed_rows)
    logging.info("Claims extracted: %s", len(claims_dataframe))
    logging.info("Wrote CSV: %s", csv_path)
    logging.info("Wrote Parquet: %s", parquet_path)
    logging.info("Wrote report: %s", output_dir / EXTRACTION_REPORT_JSON)


def parse_float_or_none(value: object) -> float | None:
    """Parse one numeric value conservatively."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def pick_best_claim(
    claims_dataframe: pd.DataFrame,
    *,
    extra_rank_builder: Callable[[pd.Series], int] | None = None,
) -> dict[str, Any] | None:
    """Pick one best claim using confidence and one optional extra rank."""
    if claims_dataframe.empty:
        return None

    sortable = claims_dataframe.copy()
    sortable["_confidence_rank"] = sortable["claim_confidence"].map(claim_confidence_rank)
    if extra_rank_builder is None:
        sortable["_extra_rank"] = 99
    else:
        sortable["_extra_rank"] = sortable.apply(extra_rank_builder, axis=1)

    sortable = sortable.sort_values(
        by=["_confidence_rank", "_extra_rank", "created_at_iso", "circular_id"],
        kind="stable",
    )
    return sortable.iloc[0].to_dict()


def build_event_claim_summary_dataframe(
    claims_dataframe: pd.DataFrame,
    match_summary_dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """Build one review-oriented event summary from the extracted claims."""
    rows: list[dict[str, Any]] = []

    for match_row in match_summary_dataframe.to_dict(orient="records"):
        source_id = str(match_row["source_id"])
        source_claims = claims_dataframe[claims_dataframe["source_id"] == source_id]

        instruments_found = ""
        if not source_claims.empty:
            instrument_values = [
                str(value)
                for value in source_claims.loc[
                    source_claims["claim_type"] == "instrument_mention",
                    "normalized_value",
                ].tolist()
                if str(value).strip()
            ]
            instruments_found = ";".join(dict.fromkeys(instrument_values))

        classification_flags = ""
        if not source_claims.empty:
            class_values = [
                str(value)
                for value in source_claims.loc[
                    source_claims["claim_type"] == "classification_or_interpretation",
                    "normalized_value",
                ].tolist()
                if str(value).strip()
            ]
            classification_flags = ";".join(dict.fromkeys(class_values))

        redshift_claim = pick_best_claim(
            source_claims[source_claims["claim_type"] == "redshift"],
            extra_rank_builder=lambda row: {
                "spectroscopic": 0,
                "host": 1,
                "photometric": 2,
                "tentative": 3,
                "unknown": 4,
            }.get(infer_redshift_method(str(row.get("evidence_text", ""))), 99),
        )
        t90_claim = pick_best_claim(
            source_claims[
                (source_claims["claim_type"] == "duration_t90")
                & (source_claims["claim_confidence"].isin(["high", "medium"]))
            ]
        )
        duration_class_claim = pick_best_claim(
            source_claims[
                (source_claims["claim_type"] == "duration_class")
                & (source_claims["claim_confidence"].isin(["high", "medium"]))
            ]
        )

        has_non_detection = False
        has_detection = False
        if not source_claims.empty:
            detection_values = {
                str(value)
                for value in source_claims.loc[
                    source_claims["claim_type"] == "detection_status",
                    "normalized_value",
                ].tolist()
            }
            has_detection = bool(detection_values & DETECTION_VALUES)
            has_non_detection = bool(detection_values & NON_DETECTION_VALUES)

        rows.append(
            {
                "source_id": source_id,
                "n_claims": int(len(source_claims)),
                "n_circulars_with_claims": int(source_claims["circular_id"].nunique()) if not source_claims.empty else 0,
                "has_trigger_time": bool((source_claims["claim_type"] == "trigger_time_t0").any()),
                "has_t90": bool((source_claims["claim_type"] == "duration_t90").any()),
                "has_duration_class": bool((source_claims["claim_type"] == "duration_class").any()),
                "has_redshift": bool((source_claims["claim_type"] == "redshift").any()),
                "has_counterpart": bool((source_claims["claim_type"] == "counterpart_type").any()),
                "has_detection": has_detection,
                "has_non_detection": has_non_detection,
                "has_upper_limit": bool((source_claims["claim_type"] == "upper_limit_simple").any()),
                "has_negative_interpretation": bool(
                    (
                        (source_claims["claim_type"] == "classification_or_interpretation")
                        & source_claims["normalized_value"].isin(
                            CLASSIFICATION_NEGATIVE_INTERPRETATION_VALUES
                        )
                    ).any()
                    or (
                        (source_claims["claim_type"] == "detection_status")
                        & source_claims["normalized_value"].isin(
                            DETECTION_NEGATIVE_INTERPRETATION_VALUES
                        )
                    ).any()
                ),
                "has_retraction": bool(
                    (
                        (source_claims["claim_type"] == "classification_or_interpretation")
                        & source_claims["normalized_value"].isin(RETRACTION_VALUES)
                    ).any()
                ),
                "has_spectroscopy": bool((source_claims["claim_type"] == "spectroscopy_mention").any()),
                "has_host_candidate": bool((source_claims["claim_type"] == "host_candidate_mention").any()),
                "instruments_found": instruments_found,
                "classification_flags": classification_flags,
                "best_redshift_value": redshift_claim["normalized_value"] if redshift_claim is not None else "",
                "best_redshift_method": (
                    infer_redshift_method(str(redshift_claim.get("evidence_text", "")))
                    if redshift_claim is not None
                    else ""
                ),
                "best_t90_seconds": t90_claim["normalized_value"] if t90_claim is not None else "",
                "best_duration_class": duration_class_claim["normalized_value"] if duration_class_claim is not None else "",
            }
        )

    dataframe = pd.DataFrame(rows, columns=EVENT_CLAIM_SUMMARY_COLUMNS)
    return dataframe.sort_values(by=["source_id"], kind="stable").reset_index(drop=True)


def run_gcn_claim_summary_build(args: argparse.Namespace) -> None:
    """Build one event-level review summary from extracted claims."""
    setup_console_logging()
    claims_path = resolve_project_path(args.claims_path)
    match_summary_path = resolve_project_path(args.match_summary_path)
    output_dir = ensure_output_dir(args.output_dir)

    claims_dataframe = pd.read_parquet(claims_path)
    match_summary_dataframe = pd.read_csv(match_summary_path)
    match_summary_dataframe = filter_match_summary_to_matched(match_summary_dataframe)
    summary_dataframe = build_event_claim_summary_dataframe(
        claims_dataframe,
        match_summary_dataframe,
    )

    summary_csv_path = output_dir / EVENT_CLAIM_SUMMARY_CSV
    summary_dataframe.to_csv(summary_csv_path, index=False)

    logging.info("Events summarized: %s", len(summary_dataframe))
    logging.info("Claims available: %s", len(claims_dataframe))
    logging.info("Wrote summary CSV: %s", summary_csv_path)
