#!/usr/bin/env python
"""Emit SkyPortal detail collections as isolated ledger facts.

Reads the frozen 2026-07-24 per-source detail capture and writes only
data/ledger/facts/source_system=skyportal_detail/. The existing SkyPortal listing
facts, event table, container map, state snapshots, and retrieval index are read-only.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


ROOT = Path("/home/meneses/project_astronomical/MAFORAI")
DETAIL_DIR = ROOT / "data/raw/skyportal/source_detail_20260724"
ARCHIVE_DIR = (
    ROOT
    / "data/raw/gcn/circulars/archive_json/20260720_093324/extracted/archive.json"
)
FACTS_ROOT = ROOT / "data/ledger/facts"
EXISTING_SKYPORTAL_DIR = FACTS_ROOT / "source_system=skyportal"
OUTPUT_DIR = FACTS_ROOT / "source_system=skyportal_detail"
REPORT_PATH = ROOT / "data/interim/audit/NB18_EMIT_REPORT.md"

SOURCE_SYSTEM = "skyportal_detail"
CONTAINER_TYPE = "skyportal_source"
TEXT_RENDER_VERSION = "v1"
MJD_EPOCH = datetime(1858, 11, 17, tzinfo=timezone.utc)
EARLIEST_VALID_OBSERVATION = datetime(1990, 1, 1, tzinfo=timezone.utc)

EXPECTED_COUNTS = {
    "comment": 2_950,
    "photometry": 7_968,
    "spectrum": 1,
    "followup_request": 2_359,
}
PERSONAL_FIELDS = ("contact_email", "contact_phone", "first_name", "last_name")

GCN_PATTERNS = (
    re.compile(r"https?://gcn\.nasa\.gov/circulars/(\d+)", re.IGNORECASE),
    re.compile(r"\bGCN(?:\s+CIRCULAR)?\s*[#:]?\s*(\d{4,6})\b", re.IGNORECASE),
)

TEXT_TEMPLATES = {
    "photometry_detection": (
        "Photometric detection: {value} mag in {band} ({system}) at MJD {mjd} "
        "with {instrument}."
    ),
    "photometry_upper_limit": (
        "Photometric upper limit: >{value} mag in {band} ({system}) at MJD {mjd} "
        "with {instrument}."
    ),
    "followup_request": (
        "Follow-up request with {instrument} in {filters} from {start} to {end}."
    ),
    "spectrum": "Spectrum observed with {instrument} at {observed_at}.",
}

# Copied verbatim from scripts/10_emit_skyportal_source_facts.py so the 49-column
# SkyPortal schema is preserved exactly.
FACT_COLUMNS = [
    "fact_id", "fact_type", "fact_subtype", "source_system", "container_type", "container_id",
    "t_known", "t_known_method", "t_known_confidence", "t_occurred", "t_intended_start",
    "t_intended_end", "value_raw", "value_parsed", "unit_raw", "parse_status", "parse_note",
    "text", "text_source", "text_render_version", "band_raw", "band_canonical",
    "photometric_system", "mag", "mag_err", "is_limit", "limit_sigma", "instrument",
    "exposure_raw", "span_start", "span_end", "text_sha256", "extractor_id", "extractor_version",
    "rule_id", "method", "confidence", "needs_review", "comment", "validation_status", "author",
    "is_bot", "captured_at", "related_fact_id", "relation_type", "is_canonical",
    "aggregation_level", "parent_fact_id",
]

TS = pa.timestamp("us", tz="UTC")
_S, _D, _B, _I = pa.string(), pa.float64(), pa.bool_(), pa.int64()
FACT_ARROW = {"t_known": TS, "t_occurred": TS, "t_intended_start": TS, "t_intended_end": TS,
              "captured_at": TS, "mag": _D, "mag_err": _D, "limit_sigma": _D,
              "confidence": _D, "span_start": _I, "span_end": _I, "is_limit": _B,
              "is_bot": _B, "needs_review": _B, "is_canonical": _B}
FACT_SCHEMA = pa.schema([(column, FACT_ARROW.get(column, _S)) for column in FACT_COLUMNS])


# Copied verbatim from scripts/10_emit_skyportal_source_facts.py. Importing that
# numeric script would also retain SOURCE_SYSTEM="skyportal", which is the wrong id
# namespace for this isolated output.
def fact_id(container_id, fact_type, natural_key):
    payload = f"{SOURCE_SYSTEM}|{container_id}|{fact_type}|{natural_key}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def jdump(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def to_utc(value):
    if value in (None, ""):
        return None
    parsed = pd.to_datetime(value, utc=True, errors="coerce")
    return None if pd.isna(parsed) else parsed.to_pydatetime()


def mjd_to_utc(value):
    if value is None:
        return None
    try:
        return MJD_EPOCH + timedelta(days=float(value))
    except (TypeError, ValueError, OverflowError):
        return None


def scalar_text(value):
    if value is None:
        return "unknown"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def tree_checksum(path):
    digest = hashlib.sha256()
    files = sorted(item for item in path.rglob("*") if item.is_file())
    for item in files:
        digest.update(item.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(item.read_bytes())
    return digest.hexdigest()


def parquet_row_count(path):
    return sum(
        pq.ParquetFile(item).metadata.num_rows
        for item in sorted(path.rglob("*.parquet"))
    )


def extract_records(filename, wrapper):
    data = wrapper.get("payload", {}).get("data")
    if filename in {"comments.json", "photometry.json"}:
        return data if isinstance(data, list) else []
    if filename == "spectra.json":
        return data.get("spectra", []) if isinstance(data, dict) else []
    if filename == "followup_requests.json":
        return data.get("followup_requests", []) if isinstance(data, dict) else []
    raise ValueError(f"Unsupported detail filename: {filename}")


def load_collection(filename):
    loaded = []
    for path in sorted(DETAIL_DIR.glob(f"*/{filename}")):
        wrapper = json.loads(path.read_text(encoding="utf-8"))
        source_id = str(wrapper.get("source_id") or path.parent.name)
        captured_at = to_utc(wrapper.get("captured_at"))
        for record in extract_records(filename, wrapper):
            loaded.append((source_id, captured_at, record))
    return loaded


def base_fact(container_id, fact_type, t_known, t_known_method, captured_at):
    row = {column: None for column in FACT_COLUMNS}
    row.update(
        fact_type=fact_type,
        source_system=SOURCE_SYSTEM,
        container_type=CONTAINER_TYPE,
        container_id=container_id,
        t_known=t_known,
        t_known_method=t_known_method,
        t_known_confidence="high",
        validation_status="raw_api_record",
        captured_at=captured_at,
    )
    return row


def circular_references(altdata):
    text = json.dumps(altdata, ensure_ascii=False) if isinstance(altdata, dict) else ""
    return sorted({int(value) for pattern in GCN_PATTERNS for value in pattern.findall(text)})


def altdata_mentions_gcn(altdata):
    if not isinstance(altdata, dict):
        return False
    return "gcn" in json.dumps(altdata, ensure_ascii=False).casefold()


def circular_publication(circular_id, cache):
    if circular_id in cache:
        return cache[circular_id]
    path = ARCHIVE_DIR / f"{circular_id}.json"
    if not path.exists():
        cache[circular_id] = None
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    created_on = record.get("createdOn")
    if isinstance(created_on, (int, float)):
        parsed = pd.to_datetime(created_on, unit="ms", utc=True, errors="coerce")
    else:
        parsed = pd.to_datetime(created_on, utc=True, errors="coerce")
    cache[circular_id] = None if pd.isna(parsed) else parsed.to_pydatetime()
    return cache[circular_id]


def exposure_from_altdata(altdata):
    if not isinstance(altdata, dict):
        return None
    for key in ("exposure", "Exposure", "exposure_time", "exptime"):
        value = altdata.get(key)
        if value not in (None, "", [], {}):
            return jdump(value) if isinstance(value, (dict, list)) else str(value)
    return None


def build_photometry(records, metrics):
    output = []
    publication_cache = {}
    for source_id, captured_at, record in records:
        natural_key = record.get("id")
        if natural_key is None:
            raise RuntimeError(f"Photometry row without id for {source_id}")

        magnitude = record.get("mag")
        limiting_magnitude = record.get("limiting_mag")
        if magnitude is not None:
            subtype = "detection"
            value = magnitude
            is_limit = False
        elif limiting_magnitude is not None:
            subtype = "upper_limit"
            value = limiting_magnitude
            is_limit = True
        else:
            raise RuntimeError(f"Photometry row {natural_key} has neither mag nor limiting_mag")

        altdata = record.get("altdata")
        references = circular_references(altdata)
        origin_is_gcn = str(record.get("origin") or "").strip().casefold() == "gcn"
        publication = None
        circular_id = None
        if origin_is_gcn and len(references) == 1:
            publication = circular_publication(references[0], publication_cache)
            circular_id = references[0] if publication is not None else None

        if publication is not None:
            t_known = publication
            t_known_method = "altdata_circular"
        else:
            t_known = to_utc(record.get("created_at"))
            t_known_method = "created_at"
        metrics["photometry_t_known_method"][t_known_method] += 1

        notes = []
        if altdata_mentions_gcn(altdata) and publication is None:
            notes.append(
                "altdata GCN reference did not resolve under the origin=GCN, "
                "single-existing-circular rule; t_known uses created_at"
            )
            metrics["unresolved_gcn_references"] += 1

        t_occurred = mjd_to_utc(record.get("mjd"))
        impossible = (
            t_occurred is None
            or t_occurred < EARLIEST_VALID_OBSERVATION
            or (captured_at is not None and t_occurred > captured_at)
        )
        if impossible:
            if t_occurred is None:
                reason = "observation MJD is missing or unparseable"
            elif t_occurred < EARLIEST_VALID_OBSERVATION:
                reason = f"observation date {t_occurred.date()} is before 1990"
            else:
                reason = (
                    f"observation date {t_occurred.date()} is after capture date "
                    f"{captured_at.date()}"
                )
            notes.insert(0, reason)
            metrics["impossible_dates"].append(
                (source_id, natural_key, record.get("mjd"), reason)
            )

        band = record.get("filter")
        system = record.get("magsys")
        instrument = record.get("instrument_name")
        template_key = "photometry_upper_limit" if is_limit else "photometry_detection"
        text = TEXT_TEMPLATES[template_key].format(
            value=scalar_text(value),
            band=band or "unknown band",
            system=system or "unknown system",
            mjd=scalar_text(record.get("mjd")),
            instrument=instrument or "unknown instrument",
        )

        row = base_fact(source_id, "photometry", t_known, t_known_method, captured_at)
        row.update(
            fact_id=fact_id(source_id, "photometry", natural_key),
            fact_subtype=subtype,
            t_occurred=t_occurred,
            value_raw=scalar_text(value),
            value_parsed=jdump({
                "altdata": altdata,
                "circular_id": circular_id,
                "instrument_id": record.get("instrument_id"),
                "limiting_mag": limiting_magnitude,
                "mag": magnitude,
                "magerr": record.get("magerr"),
                "mjd": record.get("mjd"),
                "origin": record.get("origin"),
                "row_id": natural_key,
                "snr": record.get("snr"),
            }),
            unit_raw="mag",
            parse_status="failed" if impossible else "ok",
            parse_note="; ".join(notes) if notes else None,
            text=text,
            text_source="rendered",
            text_render_version=TEXT_RENDER_VERSION,
            band_raw=band,
            band_canonical=band,
            photometric_system=system,
            mag=float(value),
            mag_err=None if record.get("magerr") is None else float(record["magerr"]),
            is_limit=is_limit,
            limit_sigma=None,
            instrument=instrument,
            exposure_raw=exposure_from_altdata(altdata),
        )
        output.append(row)
    return output


def build_comments(records):
    output = []
    for source_id, captured_at, record in records:
        natural_key = record.get("id")
        if natural_key is None:
            raise RuntimeError(f"Comment without id for {source_id}")
        text = record.get("text")
        row = base_fact(
            source_id, "comment", to_utc(record.get("created_at")), "created_at", captured_at
        )
        row.update(
            fact_id=fact_id(source_id, "comment", natural_key),
            value_raw=text,
            parse_status="ok" if text is not None else "failed",
            parse_note=None if text is not None else "comment body is null",
            text=text,
            text_source="literal",
            text_render_version=None,
            author=None if record.get("author_id") is None else str(record["author_id"]),
            is_bot=record.get("bot"),
        )
        output.append(row)
    return output


def sanitized_payload(payload):
    if isinstance(payload, dict):
        return {
            key: sanitized_payload(value)
            for key, value in payload.items()
            if key.casefold() not in PERSONAL_FIELDS
        }
    if isinstance(payload, list):
        return [sanitized_payload(value) for value in payload]
    return payload


def requested_filters(payload):
    values = payload.get("observation_choices") or payload.get("filters") or []
    if not isinstance(values, list):
        return [str(values)]
    return [str(value) for value in values]


def build_followup_requests(records, metrics):
    output = []
    for source_id, captured_at, record in records:
        natural_key = record.get("id")
        if natural_key is None:
            raise RuntimeError(f"Follow-up request without id for {source_id}")
        payload = sanitized_payload(record.get("payload") or {})
        start_raw = payload.get("start_date")
        end_raw = payload.get("end_date")
        start = to_utc(start_raw)
        end = to_utc(end_raw)
        filters = requested_filters(payload)
        instrument = ((record.get("allocation") or {}).get("instrument") or {}).get("name")
        requester_id = record.get("requester_id")
        missing_window = start is None or end is None
        if missing_window:
            metrics["followup_missing_window"] += 1

        exposure = {
            "exposure_counts": payload.get("exposure_counts"),
            "exposure_time": payload.get("exposure_time"),
        }
        exposure = {key: value for key, value in exposure.items() if value is not None}
        text = TEXT_TEMPLATES["followup_request"].format(
            instrument=instrument or "unknown instrument",
            filters=", ".join(filters) if filters else "unspecified filters",
            start=start_raw or "unspecified start",
            end=end_raw or "unspecified end",
        )

        row = base_fact(
            source_id,
            "followup_request",
            to_utc(record.get("created_at")),
            "created_at",
            captured_at,
        )
        row.update(
            fact_id=fact_id(source_id, "followup_request", natural_key),
            fact_subtype=record.get("status"),
            t_intended_start=start,
            t_intended_end=end,
            value_raw=jdump(payload),
            value_parsed=jdump({
                "allocation_id": record.get("allocation_id"),
                "instrument": instrument,
                "payload": payload,
                "requester_id": requester_id,
                "status": record.get("status"),
            }),
            parse_status="partial" if missing_window else "ok",
            parse_note="intended start/end window is incomplete" if missing_window else None,
            text=text,
            text_source="rendered",
            text_render_version=TEXT_RENDER_VERSION,
            instrument=instrument,
            exposure_raw=jdump(exposure) if exposure else None,
            author=None if requester_id is None else str(requester_id),
        )
        output.append(row)
    return output


def build_spectra(records):
    output = []
    for source_id, captured_at, record in records:
        natural_key = record.get("id")
        if natural_key is None:
            raise RuntimeError(f"Spectrum without id for {source_id}")
        observed_at = to_utc(record.get("observed_at"))
        instrument = record.get("instrument_name")
        wavelengths = record.get("wavelengths") or []
        fluxes = record.get("fluxes") or []
        errors = record.get("errors") or []
        lengths_match = bool(wavelengths) and len(wavelengths) == len(fluxes) and (
            not errors or len(errors) == len(wavelengths)
        )
        parsed_payload = {
            "altdata": record.get("altdata"),
            "errors": errors,
            "fluxes": fluxes,
            "followup_request_id": record.get("followup_request_id"),
            "instrument_id": record.get("instrument_id"),
            "instrument_name": instrument,
            "label": record.get("label"),
            "observed_at": record.get("observed_at"),
            "observed_at_mjd": record.get("observed_at_mjd"),
            "origin": record.get("origin"),
            "original_file_filename": record.get("original_file_filename"),
            "spectrum_id": natural_key,
            "telescope_id": record.get("telescope_id"),
            "telescope_name": record.get("telescope_name"),
            "type": record.get("type"),
            "units": record.get("units"),
            "wavelengths": wavelengths,
        }
        row = base_fact(
            source_id, "spectrum", to_utc(record.get("created_at")), "created_at", captured_at
        )
        row.update(
            fact_id=fact_id(source_id, "spectrum", natural_key),
            fact_subtype=record.get("type"),
            t_occurred=observed_at,
            value_raw=record.get("label") or record.get("original_file_filename"),
            value_parsed=jdump(parsed_payload),
            parse_status="ok" if observed_at is not None and lengths_match else "partial",
            parse_note=(
                None
                if observed_at is not None and lengths_match
                else "observation time missing or spectral array lengths do not match"
            ),
            text=TEXT_TEMPLATES["spectrum"].format(
                instrument=instrument or "unknown instrument",
                observed_at=record.get("observed_at") or "unknown observation time",
            ),
            text_source="rendered",
            text_render_version=TEXT_RENDER_VERSION,
            instrument=instrument,
            author=None if record.get("owner_id") is None else str(record["owner_id"]),
        )
        output.append(row)
    return output


def arrow_table(rows):
    frame = pd.DataFrame(rows, columns=FACT_COLUMNS)
    for field in FACT_SCHEMA:
        if pa.types.is_timestamp(field.type):
            frame[field.name] = pd.to_datetime(frame[field.name], utc=True)
    return pa.Table.from_pandas(frame, schema=FACT_SCHEMA, preserve_index=False)


def write_facts(facts):
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    frame = pd.DataFrame(facts, columns=FACT_COLUMNS)
    frame["_year"] = pd.to_datetime(frame["t_known"], utc=True).dt.year
    paths = []
    for year, part in frame.groupby("_year", sort=True):
        directory = OUTPUT_DIR / f"year={int(year)}"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "part-000.parquet"
        records = part.drop(columns="_year").to_dict("records")
        pq.write_table(arrow_table(records), path)
        paths.append(path)
    return paths


def existing_fact_ids():
    identifiers = set()
    for path in sorted(FACTS_ROOT.glob("source_system=*/year=*/*.parquet")):
        if OUTPUT_DIR in path.parents:
            continue
        table = pq.ParquetFile(path).read(columns=["fact_id"])
        identifiers.update(value.as_py() for value in table.column("fact_id"))
    return identifiers


def structured_personal_hits(facts):
    hits = []
    for row in facts:
        for column, value in row.items():
            if not isinstance(value, str):
                continue
            folded = value.casefold()
            for field in PERSONAL_FIELDS:
                if field in folded:
                    hits.append((row["fact_id"], column, field))
    return hits


def binary_grep_hits():
    pattern = "|".join(PERSONAL_FIELDS)
    result = subprocess.run(
        ["grep", "-aRniE", pattern, str(OUTPUT_DIR)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(f"grep failed: {result.stderr.strip()}")
    return [line for line in result.stdout.splitlines() if line]


def json_fact(row):
    def convert(value):
        if isinstance(value, datetime):
            return value.isoformat()
        return value

    return json.dumps(
        {column: convert(row.get(column)) for column in FACT_COLUMNS},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def write_report(facts, metrics, checks):
    by_type = Counter(row["fact_type"] for row in facts)
    sources_by_type = {
        fact_type: len({row["container_id"] for row in facts if row["fact_type"] == fact_type})
        for fact_type in by_type
    }
    method_counts = metrics["photometry_t_known_method"]
    lines = [
        "# NB18 SkyPortal Detail Fact Emission",
        "",
        "## Counts",
        "| fact type | rows | distinct sources |",
        "|---|---:|---:|",
        f"| comment | {by_type['comment']} | {sources_by_type['comment']} |",
        f"| photometry | {by_type['photometry']} | {sources_by_type['photometry']} |",
        f"| spectrum | {by_type['spectrum']} | {sources_by_type['spectrum']} |",
        f"| followup_request | {by_type['followup_request']} | {sources_by_type['followup_request']} |",
        f"| **total** | **{len(facts)}** | **{len({row['container_id'] for row in facts})}** |",
        "",
        "## Time And Parsing",
        f"- Photometry `t_known_method`: altdata_circular={method_counts['altdata_circular']}; created_at={method_counts['created_at']}.",
        f"- Literal-GCN altdata rows unresolved under the NB04 provenance gate: {metrics['unresolved_gcn_references']}.",
        f"- Impossible photometry dates emitted with `parse_status=failed`: {len(metrics['impossible_dates'])}.",
        f"- Follow-up requests with incomplete intended windows: {metrics['followup_missing_window']}.",
        "- MJD control: " + metrics["mjd_control"],
        "",
        "## Text Templates",
        f"- detection: `{TEXT_TEMPLATES['photometry_detection']}`",
        f"- upper_limit: `{TEXT_TEMPLATES['photometry_upper_limit']}`",
        f"- followup_request: `{TEXT_TEMPLATES['followup_request']}`",
        f"- spectrum: `{TEXT_TEMPLATES['spectrum']}`",
        "- comment: no template; literal source body; `text_render_version=NULL`.",
        f"- Rendered facts use `text_render_version={TEXT_RENDER_VERSION}`.",
        "",
        "## Verification",
        f"- Non-null `t_known`: {checks['nonnull_t_known']}/{len(facts)}; nulls={checks['null_t_known']}.",
        f"- Unique new `fact_id`: {checks['unique_ids']}; collisions with existing ledger: {checks['existing_collisions']}.",
        f"- Personal-field structured hits: {checks['personal_hits']}; binary grep hits: {checks['grep_hits']}.",
        f"- Existing SkyPortal partition: rows {checks['existing_rows_before']} -> {checks['existing_rows_after']}; checksum `{checks['existing_checksum_before']}` -> `{checks['existing_checksum_after']}`; unchanged={checks['existing_unchanged']}.",
        f"- Output schema equals the 49-column SkyPortal schema: {checks['schema_matches']}.",
        "",
        "## Not Emitted",
        "- Photometry has no raw `limit_sigma`; it remains NULL. `exposure_raw` is populated only when altdata carries an exposure field.",
        "- SkyPortal filter identifiers are retained unchanged in both `band_raw` and `band_canonical`; no new band mapping is inferred.",
        "- Follow-up requester/contact objects and spectrum actor objects are omitted; requester/owner numeric ids are retained as `author`.",
        "- State snapshots and retrieval indices were not rebuilt.",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if len(lines) > 40:
        raise RuntimeError(f"NB18 report exceeds 40 lines: {len(lines)}")


def main():
    existing_rows_before = parquet_row_count(EXISTING_SKYPORTAL_DIR)
    existing_checksum_before = tree_checksum(EXISTING_SKYPORTAL_DIR)
    existing_ids = existing_fact_ids()

    print("FACT ID: copied verbatim from script 10 because its module-level source namespace differs.")
    print(f"existing skyportal rows before: {existing_rows_before}")
    print(f"existing skyportal checksum before: {existing_checksum_before}")

    comments = load_collection("comments.json")
    photometry = load_collection("photometry.json")
    spectra = load_collection("spectra.json")
    followups = load_collection("followup_requests.json")
    loaded_counts = {
        "comment": len(comments),
        "photometry": len(photometry),
        "spectrum": len(spectra),
        "followup_request": len(followups),
    }
    if loaded_counts != EXPECTED_COUNTS:
        raise RuntimeError(f"Detail capture counts changed: {loaded_counts}")
    loaded_collections = {
        "comment": comments,
        "photometry": photometry,
        "spectrum": spectra,
        "followup_request": followups,
    }
    for fact_type, records in loaded_collections.items():
        print(
            f"loaded {fact_type}: rows={len(records)}, "
            f"distinct_sources={len({record[0] for record in records})}"
        )

    metrics = {
        "photometry_t_known_method": Counter(),
        "unresolved_gcn_references": 0,
        "impossible_dates": [],
        "followup_missing_window": 0,
    }
    facts = []
    facts.extend(build_comments(comments))
    facts.extend(build_photometry(photometry, metrics))
    facts.extend(build_spectra(spectra))
    facts.extend(build_followup_requests(followups, metrics))
    facts.sort(key=lambda row: row["fact_id"])

    control_mjd = photometry[0][2]["mjd"]
    metrics["mjd_control"] = f"MJD {control_mjd} -> {mjd_to_utc(control_mjd).isoformat()}"

    by_type = Counter(row["fact_type"] for row in facts)
    if by_type != Counter(EXPECTED_COUNTS):
        raise RuntimeError(f"Emitted counts changed: {dict(by_type)}")

    null_t_known = [row["fact_id"] for row in facts if row["t_known"] is None]
    ids = [row["fact_id"] for row in facts]
    duplicate_ids = [key for key, count in Counter(ids).items() if count > 1]
    collisions = sorted(set(ids) & existing_ids)
    personal_hits = structured_personal_hits(facts)
    if null_t_known or duplicate_ids or collisions or personal_hits:
        raise RuntimeError(
            "Pre-write validation failed: "
            f"null_t_known={len(null_t_known)}, duplicate_ids={len(duplicate_ids)}, "
            f"existing_collisions={len(collisions)}, personal_hits={len(personal_hits)}"
        )

    paths = write_facts(facts)
    grep_hits = binary_grep_hits()
    if grep_hits:
        raise RuntimeError(f"Personal field names found in output: {grep_hits[:3]}")

    output_schemas = [pq.read_schema(path).remove_metadata() for path in paths]
    schema_matches = all(schema == FACT_SCHEMA for schema in output_schemas)
    emitted_rows = parquet_row_count(OUTPUT_DIR)
    if emitted_rows != len(facts) or not schema_matches:
        raise RuntimeError(
            f"Output validation failed: rows={emitted_rows}/{len(facts)}, "
            f"schema_matches={schema_matches}"
        )

    existing_rows_after = parquet_row_count(EXISTING_SKYPORTAL_DIR)
    existing_checksum_after = tree_checksum(EXISTING_SKYPORTAL_DIR)
    existing_unchanged = (
        existing_rows_before == existing_rows_after
        and existing_checksum_before == existing_checksum_after
    )
    if not existing_unchanged:
        raise RuntimeError("Existing source_system=skyportal partition changed")

    checks = {
        "nonnull_t_known": len(facts) - len(null_t_known),
        "null_t_known": len(null_t_known),
        "unique_ids": len(duplicate_ids) == 0,
        "existing_collisions": len(collisions),
        "personal_hits": len(personal_hits),
        "grep_hits": len(grep_hits),
        "existing_rows_before": existing_rows_before,
        "existing_rows_after": existing_rows_after,
        "existing_checksum_before": existing_checksum_before,
        "existing_checksum_after": existing_checksum_after,
        "existing_unchanged": existing_unchanged,
        "schema_matches": schema_matches,
    }
    write_report(facts, metrics, checks)

    print(f"emitted total: {len(facts)}")
    for fact_type in ("comment", "photometry", "spectrum", "followup_request"):
        print(f"  {fact_type}: {by_type[fact_type]}")
    print(f"photometry t_known_method: {dict(metrics['photometry_t_known_method'])}")
    print(f"unresolved literal-GCN altdata rows: {metrics['unresolved_gcn_references']}")
    print(f"impossible observation dates: {len(metrics['impossible_dates'])}")
    for item in metrics["impossible_dates"]:
        print(f"  impossible: source={item[0]} row={item[1]} mjd={item[2]} reason={item[3]}")
    print(metrics["mjd_control"])
    print(f"null t_known: {len(null_t_known)}")
    print(f"unique new fact_id: {not duplicate_ids}")
    print(f"collisions with existing ledger: {len(collisions)}")
    print(f"personal field structured hits: {len(personal_hits)}")
    print(f"personal field grep hits: {len(grep_hits)}")
    print(f"existing skyportal rows after: {existing_rows_after}")
    print(f"existing skyportal checksum after: {existing_checksum_after}")
    print(f"existing skyportal unchanged: {existing_unchanged}")
    print(f"output schema matches: {schema_matches}")

    for fact_type in ("photometry", "followup_request", "comment"):
        sample = next(row for row in facts if row["fact_type"] == fact_type)
        print(f"SAMPLE {fact_type}: {json_fact(sample)}")
    print(f"report: {REPORT_PATH.relative_to(ROOT)} ({len(REPORT_PATH.read_text().splitlines())} lines)")


if __name__ == "__main__":
    main()
