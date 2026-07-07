"""Build auditable INCEpTION preannotation candidates from existing GCN claims."""

from __future__ import annotations

import argparse
import json
import logging
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from ..core import resolve_project_path
from .gcn_core_claims import DEFAULT_GCN_CORE_CLAIMS_PATH
from .gcn_event_matching import (
    DEFAULT_GCN_EVENT_MATCHING_SELECTED_SOURCES_PATH,
    ensure_output_dir,
    load_json_object,
)
from .gcn_inception_dossiers import (
    DEFAULT_GCN_INCEPTION_CIRCULARS_ROOT,
    DEFAULT_GCN_INCEPTION_DOSSIERS_OUTPUT_DIR,
    DOSSIER_SUFFIX,
    MANIFEST_SUFFIX,
    build_default_title,
    load_body_from_index,
    load_body_from_raw_json,
    load_selected_sources_lookup,
    normalize_newlines,
    safe_source_id,
)

DEFAULT_GCN_PREANNOTATIONS_OUTPUT_DIR = "data/interim/gcn/preannotations"
DEFAULT_GCN_PREANNOTATION_CANDIDATES_CSV_PATH = (
    f"{DEFAULT_GCN_PREANNOTATIONS_OUTPUT_DIR}/preannotation_candidates.csv"
)
DEFAULT_GCN_PREANNOTATION_CANDIDATES_PARQUET_PATH = (
    f"{DEFAULT_GCN_PREANNOTATIONS_OUTPUT_DIR}/preannotation_candidates.parquet"
)
DEFAULT_GCN_PREANNOTATION_CANDIDATES_REPORT_PATH = (
    f"{DEFAULT_GCN_PREANNOTATIONS_OUTPUT_DIR}/preannotation_candidates_report.md"
)

PREANNOTATION_CANDIDATES_CSV = "preannotation_candidates.csv"
PREANNOTATION_CANDIDATES_PARQUET = "preannotation_candidates.parquet"
PREANNOTATION_CANDIDATES_REPORT = "preannotation_candidates_report.md"

PREANNOTATION_CANDIDATE_COLUMNS = [
    "source_id",
    "event_name",
    "document_name",
    "circular_id",
    "raw_file_path",
    "subject",
    "created_at_iso",
    "claim_type",
    "extraction_rule",
    "extraction_method",
    "claim_confidence",
    "evidence_text",
    "raw_value",
    "normalized_value",
    "unit_original",
    "source_field",
    "body_begin_offset",
    "body_end_offset",
    "subject_begin_offset",
    "subject_end_offset",
    "dossier_path",
    "dossier_begin_offset",
    "dossier_end_offset",
    "offset_text",
    "offset_valid",
    "inception_layer",
    "inception_label",
    "measurement_type",
    "target",
    "certainty",
    "value",
    "unit",
    "comment",
    "magnitude_or_limit",
    "photometric_band",
    "obs_time_raw",
    "obs_time_type",
    "obs_time_reference",
    "exposure_time_raw",
    "timezone_raw",
    "instrument",
    "can_preannotate",
    "needs_llm_verification",
    "needs_human_review",
    "risk_level",
    "risk_reason",
    "recommended_action",
    "preannotation_status",
    "quality_flags",
]

QUALITY_FLAG_OFFSET_NOT_FOUND = "offset_not_found"
QUALITY_FLAG_AMBIGUOUS = "ambiguous_multiple_matches"
QUALITY_FLAG_MISMATCH = "offset_text_mismatch"
QUALITY_FLAG_DOSSIER_MISSING = "dossier_missing"

EXPLICIT_TRIGGER_RULES = {
    "trigger_t0_explicit",
    "trigger_iso_timestamp",
    "trigger_mjd",
    "trigger_ut_context",
}
T90_RULES = {"duration_t90_explicit", "duration_t90_about"}
MEDIUM_RISK_RULES = {
    "counterpart_candidate",
    "candidate_afterglow",
    "nearby_galaxy",
    "host_candidate",
}
UPPER_LIMIT_BAND_PATTERN = re.compile(
    r"\b([ugrizYJHKRIVB])['’]?\s*>\s*([0-9]+(?:\.\d+)?)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class OffsetMatch:
    """One validated exact span match."""

    begin: int
    end: int
    text: str


def setup_console_logging() -> None:
    """Configure simple console logging for one run."""
    logging.basicConfig(level=logging.INFO, format="%(message)s", force=True)


def load_claims(path_value: str | Path) -> pd.DataFrame:
    """Load claims from parquet or CSV."""
    path = resolve_project_path(path_value)
    if not path.exists():
        raise FileNotFoundError(f"Claims path not found: {path}")

    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    if path.suffix == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"Unsupported claims path: {path}")


def discover_available_dossiers(dossiers_dir: str | Path) -> dict[str, Path]:
    """Discover available INCEpTION dossiers and map them to source ids."""
    root = resolve_project_path(dossiers_dir)
    if not root.exists():
        return {}

    discovered: dict[str, Path] = {}
    for manifest_path in sorted(root.glob(f"*{MANIFEST_SUFFIX}")):
        try:
            payload = load_json_object(manifest_path)
        except Exception:
            continue
        source_id = str(payload.get("source_id") or "").strip()
        output_path = str(payload.get("output_path") or "").strip()
        if not source_id:
            continue
        dossier_path = Path(output_path) if output_path else manifest_path.with_name(
            manifest_path.name.replace(MANIFEST_SUFFIX, DOSSIER_SUFFIX)
        )
        if not dossier_path.is_absolute():
            dossier_path = resolve_project_path(dossier_path)
        discovered[source_id] = dossier_path

    for dossier_path in sorted(root.glob(f"*{DOSSIER_SUFFIX}")):
        safe_id = dossier_path.name[: -len(DOSSIER_SUFFIX)]
        discovered.setdefault(safe_id, dossier_path)

    return discovered


def resolve_selected_source_ids(
    *,
    claims_dataframe: pd.DataFrame,
    dossiers_dir: str | Path,
    source_ids: list[str] | None,
    document_names: list[str] | None,
) -> tuple[set[str], dict[str, Path]]:
    """Resolve the pilot subset of events that should be processed."""
    available_dossiers = discover_available_dossiers(dossiers_dir)
    if not available_dossiers:
        raise ValueError(
            "No INCEpTION dossiers were found. This builder now defaults to the pilot subset based on available dossiers."
        )

    selected_source_ids = set(available_dossiers.keys())
    if source_ids:
        selected_source_ids &= {source_id.strip() for source_id in source_ids if source_id.strip()}

    if document_names:
        normalized_names = {name.strip() for name in document_names if name.strip()}
        allowed_from_documents = {
            source_id
            for source_id, dossier_path in available_dossiers.items()
            if dossier_path.name in normalized_names or dossier_path.stem in normalized_names
        }
        selected_source_ids &= allowed_from_documents

    claim_source_ids = {str(value).strip() for value in claims_dataframe["source_id"].dropna().astype(str)}
    selected_source_ids &= claim_source_ids

    if not selected_source_ids:
        raise ValueError(
            "No claims remain after applying the dossier-based pilot scope and optional source/document filters."
        )

    filtered_dossiers = {
        source_id: path
        for source_id, path in available_dossiers.items()
        if source_id in selected_source_ids
    }
    return selected_source_ids, filtered_dossiers


def find_offsets(text: str, evidence_text: str) -> list[OffsetMatch]:
    """Return exact span matches for one evidence string within one text."""
    if not text or not evidence_text:
        return []

    matches: list[OffsetMatch] = []
    start = 0
    while True:
        index = text.find(evidence_text, start)
        if index < 0:
            break
        end = index + len(evidence_text)
        extracted = text[index:end]
        matches.append(OffsetMatch(begin=index, end=end, text=extracted))
        start = index + 1
    return matches


def choose_unique_offset(matches: list[OffsetMatch]) -> tuple[OffsetMatch | None, list[str]]:
    """Return one unique exact match or the corresponding quality flags."""
    if not matches:
        return None, [QUALITY_FLAG_OFFSET_NOT_FOUND]
    if len(matches) > 1:
        return None, [QUALITY_FLAG_AMBIGUOUS]
    match = matches[0]
    return match, []


def validate_offset(text: str, match: OffsetMatch | None, evidence_text: str) -> tuple[bool, list[str]]:
    """Validate one offset against the expected evidence text."""
    if match is None:
        return False, []
    if text[match.begin : match.end] != evidence_text:
        return False, [QUALITY_FLAG_MISMATCH]
    return True, []


def find_circular_block_span(dossier_text: str, circular_id: str) -> tuple[int, int] | None:
    """Locate one circular block inside one dossier."""
    marker = f"CIRCULAR {circular_id}\n"
    start = dossier_text.find(marker)
    if start < 0:
        return None

    next_marker = dossier_text.find("\n\n================================================================================\nCIRCULAR ", start + len(marker))
    if next_marker < 0:
        next_marker = len(dossier_text)
    return (start, next_marker)


def resolve_dossier_offsets(
    *,
    evidence_text: str,
    dossier_text: str,
    circular_id: str,
) -> tuple[OffsetMatch | None, list[str]]:
    """Resolve one evidence span inside the dossier, prioritizing the circular block."""
    if not dossier_text:
        return None, [QUALITY_FLAG_DOSSIER_MISSING]

    block_span = find_circular_block_span(dossier_text, circular_id)
    if block_span is not None:
        block_text = dossier_text[block_span[0] : block_span[1]]
        block_matches = find_offsets(block_text, evidence_text)
        if len(block_matches) == 1:
            block_match = block_matches[0]
            return (
                OffsetMatch(
                    begin=block_span[0] + block_match.begin,
                    end=block_span[0] + block_match.end,
                    text=block_match.text,
                ),
                [],
            )
        if len(block_matches) > 1:
            return None, [QUALITY_FLAG_AMBIGUOUS]
        return None, [QUALITY_FLAG_OFFSET_NOT_FOUND]

    return choose_unique_offset(find_offsets(dossier_text, evidence_text))


def infer_unit_original(row: pd.Series) -> str:
    """Infer the original unit when it is safe to do so."""
    claim_type = str(row.get("claim_type") or "")
    raw_value = str(row.get("raw_value") or "")
    if claim_type == "duration_t90":
        return "s"
    if claim_type == "upper_limit_simple":
        return "mag"
    if claim_type == "redshift" and raw_value:
        return ""
    return ""


def infer_photometric_band(text: str) -> str:
    """Extract a compact photometric band when it is present in an upper-limit claim."""
    match = UPPER_LIMIT_BAND_PATTERN.search(text)
    if match is not None:
        return match.group(1)
    return ""


def confidence_to_certainty(claim_confidence: str) -> str:
    """Map current claim confidence to one compact annotation certainty."""
    lowered = str(claim_confidence or "").strip().lower()
    if lowered == "high":
        return "confirmed"
    if lowered in {"medium", "low"}:
        return "tentative"
    return "unknown"


def preferred_value(row: pd.Series) -> str:
    """Pick the best compact value representation from one claim row."""
    normalized = str(row.get("normalized_value") or "").strip()
    if normalized:
        return normalized
    return str(row.get("raw_value") or "").strip()


def map_claim_to_inception(row: pd.Series) -> dict[str, Any]:
    """Build the conservative INCEpTION mapping metadata for one claim."""
    claim_type = str(row.get("claim_type") or "").strip()
    extraction_rule = str(row.get("extraction_rule") or "").strip()
    claim_confidence = str(row.get("claim_confidence") or "").strip()
    raw_value = str(row.get("raw_value") or "").strip()
    normalized_value = str(row.get("normalized_value") or "").strip()
    evidence_text = str(row.get("evidence_text") or "").strip()
    instrument = str(row.get("instrument_if_any") or "").strip()

    mapping: dict[str, Any] = {
        "inception_layer": "",
        "inception_label": "",
        "measurement_type": "",
        "target": "",
        "certainty": confidence_to_certainty(claim_confidence),
        "value": preferred_value(row),
        "unit": "",
        "comment": evidence_text,
        "magnitude_or_limit": "",
        "photometric_band": "",
        "obs_time_raw": "",
        "obs_time_type": "",
        "obs_time_reference": "",
        "exposure_time_raw": "",
        "timezone_raw": "",
        "instrument": instrument,
        "can_preannotate": False,
        "needs_llm_verification": "no",
        "needs_human_review": "yes",
        "risk_level": "medium",
        "risk_reason": "",
        "recommended_action": "keep_as_candidate_only",
    }

    if claim_type == "trigger_time_t0":
        mapping.update(
            {
                "inception_layer": "EVENT_EVIDENCE",
                "inception_label": "TRIGGER_TIME",
                "target": "event",
                "certainty": "confirmed"
                if claim_confidence == "high" or extraction_rule in EXPLICIT_TRIGGER_RULES
                else "tentative",
                "value": normalized_value or raw_value,
                "risk_level": "low",
                "risk_reason": "Explicit trigger-time claims are already conservative, but they still need exact span offsets in the imported text.",
                "recommended_action": "preannotate_directly",
                "can_preannotate": True,
                "needs_human_review": "no",
            }
        )
        return mapping

    if claim_type == "duration_t90":
        mapping.update(
            {
                "inception_layer": "EVENT_EVIDENCE",
                "inception_label": "T90",
                "target": "event",
                "certainty": "confirmed",
                "value": normalized_value or raw_value,
                "unit": "s",
                "risk_level": "low",
                "risk_reason": "Explicit T90 claims are strong, but they still need exact span offsets in the imported text.",
                "recommended_action": "preannotate_directly",
                "can_preannotate": True,
                "needs_human_review": "no",
            }
        )
        return mapping

    if claim_type == "spectroscopy_mention":
        mapping.update(
            {
                "inception_layer": "EVENT_EVIDENCE",
                "inception_label": "SPECTROSCOPY",
                "target": "counterpart"
                if re.search(r"\b(counterpart|afterglow)\b", evidence_text, re.IGNORECASE)
                else "event",
                "risk_level": "medium",
                "risk_reason": "The claim marks spectroscopy context, but it does not separate actual spectroscopic results from looser mentions or planned observations.",
                "recommended_action": "keep_as_candidate_only",
            }
        )
        return mapping

    if claim_type == "host_candidate_mention":
        mapping.update(
            {
                "inception_layer": "EVENT_EVIDENCE",
                "inception_label": "HOST_CONTEXT",
                "target": "event",
                "needs_llm_verification": "optional",
                "risk_level": "high" if extraction_rule in MEDIUM_RISK_RULES else "medium",
                "risk_reason": "The claim preserves host-related wording, but it does not resolve whether the text names a true host, a nearby galaxy, or a weaker contextual association.",
                "recommended_action": "keep_as_candidate_only",
            }
        )
        return mapping

    if claim_type == "counterpart_type":
        mapping.update(
            {
                "inception_layer": "EVENT_EVIDENCE",
                "inception_label": "COUNTERPART_ASSOCIATION",
                "target": "counterpart",
                "certainty": "tentative"
                if normalized_value == "candidate_counterpart" or claim_confidence != "high"
                else "confirmed",
                "needs_llm_verification": "optional",
                "risk_level": "medium",
                "risk_reason": "The claim identifies counterpart-family wording, but it does not encode a full relation structure or a fully verified counterpart identity.",
                "recommended_action": "keep_as_candidate_only",
            }
        )
        return mapping

    if claim_type == "redshift":
        mapping.update(
            {
                "inception_layer": "EVENT_EVIDENCE",
                "inception_label": "REDSHIFT_EVENT",
                "target": "event",
                "needs_llm_verification": "yes",
                "risk_level": "high",
                "risk_reason": "The current extractor keeps strong redshift candidates, but it does not split event redshift from contextual redshift inside the evidence span.",
                "recommended_action": "preannotate_after_llm_verification",
            }
        )
        return mapping

    if claim_type == "classification_or_interpretation":
        mapping.update(
            {
                "inception_layer": "EVENT_EVIDENCE",
                "inception_label": "CLASSIFICATION_INTERPRETATION",
                "target": "event",
                "needs_llm_verification": "yes",
                "risk_level": "high",
                "risk_reason": "This family mixes physical interpretation with negative or rejection states, so it is not stable enough for direct span preannotation.",
                "recommended_action": "preannotate_after_llm_verification",
            }
        )
        return mapping

    if claim_type == "detection_status":
        mapping.update(
            {
                "inception_layer": "EVENT_EVIDENCE",
                "needs_llm_verification": "yes",
                "risk_level": "high",
                "risk_reason": "This family mixes positive detections, non-detections, upper-limit-like statements, and non-GRB interpretations.",
                "recommended_action": "split_claim_type_before_preannotation",
            }
        )
        return mapping

    if claim_type == "instrument_mention":
        mapping.update(
            {
                "inception_layer": "EVENT_EVIDENCE",
                "inception_label": "TRIGGER_INSTRUMENT",
                "target": "event",
                "needs_llm_verification": "optional",
                "risk_level": "medium",
                "risk_reason": "The extractor finds instrument names, but not whether the instrument is the trigger instrument or only follow-up context.",
                "recommended_action": "keep_as_candidate_only",
            }
        )
        return mapping

    if claim_type == "upper_limit_simple":
        mapping.update(
            {
                "inception_layer": "PHOTOMETRIC_MEASUREMENT",
                "measurement_type": "upper_limit",
                "target": "counterpart",
                "value": "",
                "unit": "mag",
                "magnitude_or_limit": normalized_value or raw_value,
                "photometric_band": infer_photometric_band(raw_value or evidence_text),
                "risk_level": "medium",
                "risk_reason": "The claim captures useful upper limits, but it still lacks structured observation-time features and a richer photometric object.",
                "recommended_action": "improve_regex_or_parser",
            }
        )
        return mapping

    if claim_type == "duration_class":
        mapping.update(
            {
                "inception_layer": "EVENT_EVIDENCE",
                "inception_label": "CLASSIFICATION_INTERPRETATION",
                "target": "event",
                "risk_level": "medium",
                "risk_reason": "Long/short GRB wording is useful context, but it is not a direct T90 span and the current schema has no dedicated duration-class label.",
                "recommended_action": "keep_as_candidate_only",
            }
        )
        return mapping

    return mapping


def load_gcn_text(
    row: pd.Series,
    *,
    gcn_root: str | Path,
    body_cache: dict[str, str],
) -> tuple[str, str]:
    """Load subject and body text for one claim row."""
    subject = normalize_newlines(str(row.get("subject") or ""))
    raw_file_path = str(row.get("raw_file_path") or "").strip()

    body = body_cache.get(raw_file_path)
    if body is None:
        body = load_body_from_raw_json(raw_file_path)
        if not body:
            body = load_body_from_index(
                circular_id=str(row.get("circular_id") or "").strip(),
                year=row.get("year"),
                gcn_root=gcn_root,
            )
        body_cache[raw_file_path] = body

    return subject, body


def resolve_event_name_lookup(
    *,
    selected_sources_path: str | Path,
    dossiers_dir: str | Path,
) -> dict[str, str]:
    """Resolve one best-effort event-name lookup from existing event metadata."""
    lookup: dict[str, str] = {}
    try:
        selected_sources = load_selected_sources_lookup(selected_sources_path)
    except Exception:
        selected_sources = {}

    dossiers_root = resolve_project_path(dossiers_dir)
    for source_id, source_row in selected_sources.items():
        manifest_path = dossiers_root / f"{safe_source_id(source_id)}_inception_dossier_manifest.json"
        if manifest_path.exists():
            try:
                payload = load_json_object(manifest_path)
            except Exception:
                payload = {}
            title = str(payload.get("title") or "").strip()
            if title:
                lookup[source_id] = title
                continue
        lookup[source_id] = build_default_title(
            source_id,
            source_row=source_row,
            explicit_title=None,
        )
    return lookup


def determine_preannotation_status(
    *,
    mapping: dict[str, Any],
    dossier_available: bool,
    dossier_offset_valid: bool,
    body_or_subject_offset_valid: bool,
    quality_flags: list[str],
) -> tuple[str, bool]:
    """Determine one compact preannotation status and final readiness flag."""
    mapping_found = bool(mapping["inception_layer"] or mapping["measurement_type"])

    if not mapping_found:
        return "not_mapped", False

    if mapping["needs_llm_verification"] == "yes":
        return "needs_llm_verification", False

    if QUALITY_FLAG_AMBIGUOUS in quality_flags:
        return "not_ready_ambiguous_offsets", False

    if mapping["can_preannotate"]:
        offset_valid = dossier_offset_valid or (not dossier_available and body_or_subject_offset_valid)
        if not offset_valid:
            return "not_ready_no_offsets", False
        if mapping["risk_level"] == "low":
            return "ready_for_preannotation", True

    if mapping["recommended_action"] in {
        "keep_as_candidate_only",
        "improve_regex_or_parser",
    }:
        return "candidate_only", False

    if mapping["recommended_action"] == "preannotate_after_llm_verification":
        return "needs_llm_verification", False

    if mapping["recommended_action"] == "discard_or_ignore":
        return "rejected", False

    if QUALITY_FLAG_OFFSET_NOT_FOUND in quality_flags and mapping["can_preannotate"]:
        return "not_ready_no_offsets", False

    return "candidate_only", False


def load_dossier_text(
    source_id: str,
    *,
    dossier_lookup: dict[str, Path],
    dossier_cache: dict[str, str],
) -> tuple[Path, str]:
    """Load the dossier text for one source id when it exists."""
    dossier_path = dossier_lookup.get(source_id)
    if dossier_path is None:
        dossier_path = resolve_project_path(DEFAULT_GCN_INCEPTION_DOSSIERS_OUTPUT_DIR) / f"{safe_source_id(source_id)}{DOSSIER_SUFFIX}"
    cache_key = str(dossier_path)
    if cache_key in dossier_cache:
        return dossier_path, dossier_cache[cache_key]
    if not dossier_path.exists():
        dossier_cache[cache_key] = ""
        return dossier_path, ""
    dossier_text = normalize_newlines(dossier_path.read_text(encoding="utf-8"))
    dossier_cache[cache_key] = dossier_text
    return dossier_path, dossier_text


def build_preannotation_candidates(
    claims_dataframe: pd.DataFrame,
    *,
    gcn_root: str | Path,
    dossiers_dir: str | Path,
    selected_sources_path: str | Path,
    dossier_lookup: dict[str, Path],
) -> pd.DataFrame:
    """Build the auditable preannotation-candidates table from existing claims."""
    event_name_lookup = resolve_event_name_lookup(
        selected_sources_path=selected_sources_path,
        dossiers_dir=dossiers_dir,
    )
    body_cache: dict[str, str] = {}
    dossier_cache: dict[str, str] = {}

    rows: list[dict[str, Any]] = []
    for _, claim_row in claims_dataframe.iterrows():
        source_id = str(claim_row.get("source_id") or "").strip()
        circular_id = str(claim_row.get("circular_id") or "").strip()
        evidence_text = str(claim_row.get("evidence_text") or "")
        dossier_path, dossier_text = load_dossier_text(
            source_id,
            dossier_lookup=dossier_lookup,
            dossier_cache=dossier_cache,
        )
        dossier_available = bool(dossier_text)

        subject_text, body_text = load_gcn_text(
            claim_row,
            gcn_root=gcn_root,
            body_cache=body_cache,
        )

        body_match, body_flags = choose_unique_offset(find_offsets(body_text, evidence_text))
        body_valid, body_validation_flags = validate_offset(body_text, body_match, evidence_text)

        subject_match, subject_flags = choose_unique_offset(find_offsets(subject_text, evidence_text))
        subject_valid, subject_validation_flags = validate_offset(subject_text, subject_match, evidence_text)

        dossier_match, dossier_flags = resolve_dossier_offsets(
            evidence_text=evidence_text,
            dossier_text=dossier_text,
            circular_id=circular_id,
        )
        dossier_valid, dossier_validation_flags = validate_offset(
            dossier_text,
            dossier_match,
            evidence_text,
        )
        has_valid_offsets = dossier_valid or (not dossier_available and (body_valid or subject_valid))
        source_field = str(claim_row.get("source_field") or "").strip()

        quality_flags: set[str] = set()
        if source_field == "body":
            quality_flags.update(body_flags)
            quality_flags.update(body_validation_flags)
        elif source_field == "subject":
            quality_flags.update(subject_flags)
            quality_flags.update(subject_validation_flags)
        else:
            quality_flags.update(body_flags)
            quality_flags.update(body_validation_flags)
            quality_flags.update(subject_flags)
            quality_flags.update(subject_validation_flags)

        if dossier_available:
            quality_flags.update(dossier_flags)
            quality_flags.update(dossier_validation_flags)
        elif QUALITY_FLAG_DOSSIER_MISSING in dossier_flags:
            quality_flags.add(QUALITY_FLAG_DOSSIER_MISSING)

        mapping = map_claim_to_inception(claim_row)
        status, can_preannotate_now = determine_preannotation_status(
            mapping=mapping,
            dossier_available=dossier_available,
            dossier_offset_valid=dossier_valid,
            body_or_subject_offset_valid=body_valid or subject_valid,
            quality_flags=sorted(flag for flag in quality_flags if flag),
        )

        offset_text = ""
        if dossier_valid and dossier_match is not None:
            offset_text = dossier_text[dossier_match.begin : dossier_match.end]
        elif not dossier_available and body_valid and body_match is not None:
            offset_text = body_text[body_match.begin : body_match.end]
        elif not dossier_available and subject_valid and subject_match is not None:
            offset_text = subject_text[subject_match.begin : subject_match.end]

        row = {
            "source_id": source_id,
            "event_name": event_name_lookup.get(source_id, source_id),
            "document_name": dossier_path.name if dossier_path.exists() else "",
            "circular_id": circular_id,
            "raw_file_path": str(claim_row.get("raw_file_path") or ""),
            "subject": str(claim_row.get("subject") or ""),
            "created_at_iso": str(claim_row.get("created_at_iso") or ""),
            "claim_type": str(claim_row.get("claim_type") or ""),
            "extraction_rule": str(claim_row.get("extraction_rule") or ""),
            "extraction_method": "regex_rule",
            "claim_confidence": str(claim_row.get("claim_confidence") or ""),
            "evidence_text": evidence_text,
            "raw_value": str(claim_row.get("raw_value") or ""),
            "normalized_value": str(claim_row.get("normalized_value") or ""),
            "unit_original": infer_unit_original(claim_row),
            "source_field": source_field,
            "body_begin_offset": body_match.begin if body_valid and body_match is not None else None,
            "body_end_offset": body_match.end if body_valid and body_match is not None else None,
            "subject_begin_offset": subject_match.begin if subject_valid and subject_match is not None else None,
            "subject_end_offset": subject_match.end if subject_valid and subject_match is not None else None,
            "dossier_path": str(dossier_path) if dossier_path.exists() else "",
            "dossier_begin_offset": dossier_match.begin if dossier_valid and dossier_match is not None else None,
            "dossier_end_offset": dossier_match.end if dossier_valid and dossier_match is not None else None,
            "offset_text": offset_text,
            "offset_valid": has_valid_offsets,
            "inception_layer": mapping["inception_layer"],
            "inception_label": mapping["inception_label"],
            "measurement_type": mapping["measurement_type"],
            "target": mapping["target"],
            "certainty": mapping["certainty"],
            "value": mapping["value"],
            "unit": mapping["unit"],
            "comment": mapping["comment"],
            "magnitude_or_limit": mapping["magnitude_or_limit"],
            "photometric_band": mapping["photometric_band"],
            "obs_time_raw": mapping["obs_time_raw"],
            "obs_time_type": mapping["obs_time_type"],
            "obs_time_reference": mapping["obs_time_reference"],
            "exposure_time_raw": mapping["exposure_time_raw"],
            "timezone_raw": mapping["timezone_raw"],
            "instrument": mapping["instrument"],
            "can_preannotate": can_preannotate_now,
            "needs_llm_verification": mapping["needs_llm_verification"],
            "needs_human_review": mapping["needs_human_review"],
            "risk_level": mapping["risk_level"],
            "risk_reason": mapping["risk_reason"],
            "recommended_action": mapping["recommended_action"],
            "preannotation_status": status,
            "quality_flags": ";".join(sorted(flag for flag in quality_flags if flag)),
        }
        rows.append(row)

    return pd.DataFrame(rows, columns=PREANNOTATION_CANDIDATE_COLUMNS)


def format_examples(dataframe: pd.DataFrame, *, limit: int) -> list[str]:
    """Format a few example rows for the Markdown report."""
    examples: list[str] = []
    for _, row in dataframe.head(limit).iterrows():
        label = str(row.get("inception_label") or row.get("measurement_type") or "unmapped")
        examples.append(
            "- "
            f"{row['source_id']} | circular {row['circular_id']} | "
            f"{row['claim_type']} -> {label} | "
            f"status={row['preannotation_status']} | "
            f"value={row['value'] or row['raw_value']} | "
            f"flags={row['quality_flags'] or 'none'}"
        )
    return examples or ["- none"]


def write_report(
    dataframe: pd.DataFrame,
    *,
    claims_path: str | Path,
    dossiers_dir: str | Path,
    output_path: Path,
    selected_source_ids: list[str],
) -> None:
    """Write the Markdown report for the generated preannotation candidates."""
    total = len(dataframe)
    body_offsets = int(dataframe["body_begin_offset"].notna().sum()) if total else 0
    dossier_offsets = int(dataframe["dossier_begin_offset"].notna().sum()) if total else 0

    claim_counts = dataframe["claim_type"].value_counts().sort_values(ascending=False)
    label_counts = (
        dataframe.assign(
            inception_key=lambda frame: frame["inception_layer"].fillna("")
            + "::"
            + frame["inception_label"].fillna("")
            + "::"
            + frame["measurement_type"].fillna("")
        )["inception_key"]
        .value_counts()
        .sort_values(ascending=False)
    )

    flag_counter: Counter[str] = Counter()
    for value in dataframe["quality_flags"].fillna(""):
        for flag in [item for item in str(value).split(";") if item]:
            flag_counter[flag] += 1

    ready_rows = dataframe[dataframe["preannotation_status"] == "ready_for_preannotation"]
    not_ready_rows = dataframe[
        dataframe["preannotation_status"].isin(
            [
                "not_ready_no_offsets",
                "not_ready_ambiguous_offsets",
                "needs_llm_verification",
                "not_mapped",
                "candidate_only",
            ]
        )
    ]

    lines = [
        "# Preannotation Candidates Report",
        "",
        "## Run Context",
        "",
        f"- Claims input: `{claims_path}`",
        f"- Dossiers dir: `{dossiers_dir}`",
        f"- Output: `{output_path}`",
        f"- Pilot source_ids included: `{', '.join(selected_source_ids)}`",
        "",
        "## Counts",
        "",
        f"- Total claims read: {total}",
        f"- Total candidates generated: {total}",
        f"- Body offsets found: {body_offsets} ({(body_offsets / total * 100):.1f}%)" if total else "- Body offsets found: 0 (0.0%)",
        f"- Dossier offsets found: {dossier_offsets} ({(dossier_offsets / total * 100):.1f}%)" if total else "- Dossier offsets found: 0 (0.0%)",
        f"- ready_for_preannotation: {int((dataframe['preannotation_status'] == 'ready_for_preannotation').sum())}",
        f"- candidate_only: {int((dataframe['preannotation_status'] == 'candidate_only').sum())}",
        f"- needs_llm_verification: {int((dataframe['preannotation_status'] == 'needs_llm_verification').sum())}",
        f"- not_ready_no_offsets: {int((dataframe['preannotation_status'] == 'not_ready_no_offsets').sum())}",
        "",
        "## Counts by Claim Type",
        "",
    ]

    for claim_type, count in claim_counts.items():
        lines.append(f"- `{claim_type}`: {int(count)}")

    lines.extend(["", "## Counts by INCEpTION Mapping", ""])
    for key, count in label_counts.items():
        layer, label, measurement_type = key.split("::")
        display = " / ".join(item for item in [layer, label or measurement_type] if item) or "unmapped"
        lines.append(f"- `{display}`: {int(count)}")

    lines.extend(["", "## Top Quality Flags", ""])
    if flag_counter:
        for flag, count in flag_counter.most_common(10):
            lines.append(f"- `{flag}`: {count}")
    else:
        lines.append("- none")

    lines.extend(["", "## Examples Ready for Preannotation", ""])
    lines.extend(format_examples(ready_rows, limit=5))
    lines.extend(["", "## Examples Not Ready", ""])
    lines.extend(format_examples(not_ready_rows, limit=5))
    lines.extend(
        [
            "",
            "## Technical Recommendation",
            "",
            "- The current table is already useful for auditing which claim families can move toward INCEpTION preannotation.",
            "- The next minimal code step should be improving exact span recovery, because normalized `evidence_text` fragments often do not survive as exact substrings in the dossier text.",
            "- After offsets improve, direct low-risk preannotations should start with `trigger_time_t0` and `duration_t90`; the other mapped families should remain candidate-only or require contextual verification.",
        ]
    )

    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def select_default_claims_path() -> str:
    """Pick the default claims path, preferring parquet and falling back to CSV."""
    parquet_path = resolve_project_path(DEFAULT_GCN_CORE_CLAIMS_PATH)
    if parquet_path.exists():
        return DEFAULT_GCN_CORE_CLAIMS_PATH

    csv_path = parquet_path.with_suffix(".csv")
    if csv_path.exists():
        return str(csv_path.relative_to(resolve_project_path(".")))
    return DEFAULT_GCN_CORE_CLAIMS_PATH


def run_gcn_preannotation_candidates_build(args: argparse.Namespace) -> None:
    """Build auditable INCEpTION preannotation candidates from existing claims."""
    setup_console_logging()

    claims_dataframe = load_claims(args.claims_path)
    output_dir = ensure_output_dir(args.output_dir)

    if not resolve_project_path(args.dossiers_dir).exists():
        logging.warning("Dossiers directory not found: %s", resolve_project_path(args.dossiers_dir))
    if not resolve_project_path(args.selected_sources_path).exists():
        logging.warning(
            "Selected-sources path not found: %s",
            resolve_project_path(args.selected_sources_path),
        )

    selected_source_ids, dossier_lookup = resolve_selected_source_ids(
        claims_dataframe=claims_dataframe,
        dossiers_dir=args.dossiers_dir,
        source_ids=getattr(args, "source_id", None),
        document_names=getattr(args, "document_name", None),
    )
    claims_dataframe = claims_dataframe[
        claims_dataframe["source_id"].astype(str).isin(selected_source_ids)
    ].copy()

    candidates = build_preannotation_candidates(
        claims_dataframe,
        gcn_root=args.gcn_root,
        dossiers_dir=args.dossiers_dir,
        selected_sources_path=args.selected_sources_path,
        dossier_lookup=dossier_lookup,
    )

    csv_path = output_dir / PREANNOTATION_CANDIDATES_CSV
    parquet_path = output_dir / PREANNOTATION_CANDIDATES_PARQUET
    report_path = output_dir / PREANNOTATION_CANDIDATES_REPORT

    candidates.to_csv(csv_path, index=False)
    candidates.to_parquet(parquet_path, index=False)
    write_report(
        candidates,
        claims_path=args.claims_path,
        dossiers_dir=args.dossiers_dir,
        output_path=report_path,
        selected_source_ids=sorted(selected_source_ids),
    )

    quality_counter: Counter[str] = Counter()
    for value in candidates["quality_flags"].fillna(""):
        for flag in [item for item in str(value).split(";") if item]:
            quality_counter[flag] += 1

    logging.info("Pilot source_ids: %s", ", ".join(sorted(selected_source_ids)))
    logging.info("Total claims: %s", len(candidates))
    logging.info(
        "ready_for_preannotation: %s",
        int((candidates["preannotation_status"] == "ready_for_preannotation").sum()),
    )
    logging.info(
        "candidate_only: %s",
        int((candidates["preannotation_status"] == "candidate_only").sum()),
    )
    logging.info(
        "needs_llm_verification: %s",
        int((candidates["preannotation_status"] == "needs_llm_verification").sum()),
    )
    logging.info(
        "not_ready_no_offsets: %s",
        int((candidates["preannotation_status"] == "not_ready_no_offsets").sum()),
    )
    top_flags = ", ".join(f"{flag}={count}" for flag, count in quality_counter.most_common(5)) or "none"
    logging.info("Top quality flags: %s", top_flags)
    logging.info("CSV: %s", csv_path)
    logging.info("Parquet: %s", parquet_path)
    logging.info("Report: %s", report_path)
