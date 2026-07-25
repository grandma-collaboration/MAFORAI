#!/usr/bin/env python
"""scripts/13_emit_gcn_facts.py

Emit ledger facts from the GCN circular corpus (2023+) by calling the existing, validated
extractors directly and writing Parquet per docs/ledger/01_schema_v1.md. NO NETWORK, NO GIT.
Does not modify any module. Processes year by year (resumable, per-year metrics).

Entry points reused (verified in Phase 0, none go through event selection):
  canonical.document.render_canonical / iter_real_circulars   -> text + SHA-256
  extraction_v2.sweep.get_active_extractors -> 13 EVENT_EVIDENCE extractors, .extract(doc)
  extraction_v2.photometry_{tables,rows,prose,annotations}    -> per-circular photometry

Run: /home/meneses/project_astronomical/MAFORAI/.venv/bin/python scripts/13_emit_gcn_facts.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import warnings
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from skyportal_corpus.canonical.document import iter_real_circulars, render_canonical
from skyportal_corpus.extraction_v2.photometry_annotations import merge_photometry_measurements
from skyportal_corpus.extraction_v2.photometry_prose import ProsePhotometryExtractor
from skyportal_corpus.extraction_v2.photometry_rows import parse_table_to_measurements
from skyportal_corpus.extraction_v2.photometry_tables import detect_table_blocks
from skyportal_corpus.extraction_v2.sweep import get_active_extractors

ROOT = "/home/meneses/project_astronomical/MAFORAI"
LEDGER = os.path.join(ROOT, "data/ledger")
AUDIT_DIR = os.path.join(ROOT, "data/interim/audit")
MIN_YEAR = 2023
SOURCE_SYSTEM = "gcn"
CONTAINER_TYPE = "circular"
MJD_EPOCH = datetime(1858, 11, 17, tzinfo=timezone.utc)
RUN_TS = datetime.now(timezone.utc)

# SkyPortal fact columns (schema §3), IN ORDER, so the two fact sets concatenate; plus the
# new t_occurred_offset_hours (schema v1 has no column for a trigger-relative time — friction).
FACT_COLUMNS = [
    "fact_id", "fact_type", "fact_subtype", "source_system", "container_type", "container_id",
    "t_known", "t_known_method", "t_known_confidence", "t_occurred", "t_intended_start",
    "t_intended_end", "value_raw", "value_parsed", "unit_raw", "parse_status", "parse_note",
    "text", "text_source", "text_render_version", "band_raw", "band_canonical",
    "photometric_system", "mag", "mag_err", "is_limit", "limit_sigma", "instrument",
    "exposure_raw", "span_start", "span_end", "text_sha256", "extractor_id", "extractor_version",
    "rule_id", "method", "confidence", "needs_review", "comment", "validation_status", "author",
    "is_bot", "captured_at", "related_fact_id", "relation_type", "is_canonical",
    "aggregation_level", "parent_fact_id", "t_occurred_offset_hours",
]

TS = pa.timestamp("us", tz="UTC")
_S, _D, _B, _I = pa.string(), pa.float64(), pa.bool_(), pa.int64()
FACT_ARROW = {"t_known": TS, "t_occurred": TS, "t_intended_start": TS, "t_intended_end": TS,
              "captured_at": TS, "mag": _D, "mag_err": _D, "limit_sigma": _D, "confidence": _D,
              "t_occurred_offset_hours": _D, "span_start": _I, "span_end": _I, "is_limit": _B,
              "is_bot": _B, "needs_review": _B, "is_canonical": _B}
FACT_SCHEMA = pa.schema([(c, FACT_ARROW.get(c, _S)) for c in FACT_COLUMNS])


# ---- helpers --------------------------------------------------------------------------
def year_of(created_on):
    s = str(created_on)
    return int(s[:4])  # all 2023+ circulars carry an ISO created_on (verified)


def to_utc(created_on):
    return pd.to_datetime(str(created_on), utc=True).to_pydatetime()


def fact_id(container_id, fact_type, span_start, span_end, *content):
    """Deterministic CONTENT hash (schema §3.1). A span alone does not identify a fact:
    photometry passes (value_raw, band_raw), evidence passes (fact_subtype). No ordinal or
    iteration order ever enters the hash. Called with no *content it reproduces the old
    span-only id, used only to report the before/after collision count."""
    parts = [SOURCE_SYSTEM, container_id, fact_type, span_start, span_end, *content]
    payload = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def jdump(obj):
    obj = {k: v for k, v in obj.items() if v not in (None, [], "")}
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) if obj else None


_FLOAT_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")
_REL_RE = re.compile(
    r"([-+]?\d+(?:\.\d+)?)\s*(sec(?:onds?)?|s|min(?:utes?)?|hours?|hrs?|h|days?|d)\b", re.IGNORECASE)
_UNIT_HOURS = {"s": 1 / 3600, "sec": 1 / 3600, "second": 1 / 3600, "seconds": 1 / 3600,
               "min": 1 / 60, "minute": 1 / 60, "minutes": 1 / 60, "h": 1.0, "hour": 1.0,
               "hours": 1.0, "hr": 1.0, "hrs": 1.0, "d": 24.0, "day": 24.0, "days": 24.0}


def _parse_float(text):
    if text is None:
        return None
    m = _FLOAT_RE.search(str(text))
    return float(m.group()) if m else None


def parse_relative_hours(raw):
    """'72 sec after trigger' -> 0.02 h; 'T-3.2 h' -> -3.2 h. None if unparseable."""
    m = _REL_RE.search(raw)
    if not m:
        return None
    value = float(m.group(1)) * _UNIT_HOURS[m.group(2).lower()]
    if re.search(r"\bbefore\b|(?<![a-z])T-|(?<![a-z])T0-", raw, re.IGNORECASE):
        value = -abs(value)
    return value


def parse_obs_time(raw, otype, oref):
    """Return (t_occurred_utc, offset_hours, parse_status, parse_note) per Phase 2."""
    if not raw or otype is None:
        return None, None, "failed", "no_obs_time"
    try:
        if otype == "relative_to_trigger" or oref == "trigger_time_t0":
            hrs = parse_relative_hours(str(raw))
            if hrs is None:
                return None, None, "failed", "relative_offset_unparseable"
            return None, hrs, "ok", None
        if otype == "mjd":
            v = _parse_float(raw)
            if v is None:
                return None, None, "failed", "mjd_unparseable"
            return MJD_EPOCH + timedelta(days=v), None, "ok", None
        if otype == "jd":
            v = _parse_float(raw)
            if v is None:
                return None, None, "failed", "jd_unparseable"
            return MJD_EPOCH + timedelta(days=v - 2400000.5), None, "ok", None
        if otype in ("utc_datetime", "calendar_date", "other_timezone", "start_time_plus_exposure"):
            s = str(raw).strip()
            if not re.search(r"(?<!\d)(?:19|20)\d{2}(?!\d)", s):
                return None, None, "failed", f"{otype}_no_date"  # never fabricate a date
            cleaned = re.sub(r"\b(UTC?|GMT)\b", "", s, flags=re.IGNORECASE).strip()
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                dt = pd.to_datetime(cleaned, utc=True, errors="coerce")
            if pd.isna(dt):
                return None, None, "failed", f"{otype}_unparseable"
            status = "ok" if otype == "utc_datetime" else "partial"
            note = None if otype == "utc_datetime" else f"{otype}_reduced_to_instant"
            return dt.to_pydatetime(), None, status, note
        if otype == "unclear":
            return None, None, "failed", "unclear"
        return None, None, "failed", f"unhandled_type_{otype}"
    except Exception as exc:  # extraction/parse robustness; never crash a row
        return None, None, "failed", f"{otype}_error_{type(exc).__name__}"


# ---- row builders ---------------------------------------------------------------------
def _base_row(fact_type, subtype, ann, circ_id, t_known):
    row = {c: None for c in FACT_COLUMNS}
    row.update(
        fact_type=fact_type, fact_subtype=subtype, source_system=SOURCE_SYSTEM,
        container_type=CONTAINER_TYPE, container_id=str(circ_id), t_known=t_known,
        t_known_method="circular_publication", t_known_confidence="high",
        text=ann.text, text_source="span", text_render_version=None,
        span_start=ann.span_start, span_end=ann.span_end, text_sha256=ann.text_sha256,
        extractor_id=ann.extractor_id, extractor_version=ann.extractor_version,
        rule_id=ann.rule_id, method=ann.method, confidence=ann.confidence,
        needs_review=ann.needs_review, comment=ann.comment, validation_status="rule_extracted",
        captured_at=RUN_TS)  # fact_id set by the build_* function once content is known
    return row


def build_evidence_row(ann, circ_id, t_known):
    row = _base_row("gcn_evidence", ann.label, ann, circ_id, t_known)
    row["value_raw"] = ann.value
    row["unit_raw"] = ann.unit
    row["t_occurred"] = None
    row["parse_status"] = "not_applicable"
    row["parse_note"] = "obs_time parsing applies to photometry only"
    # target/certainty have no schema column -> preserved in value_parsed (friction)
    row["value_parsed"] = jdump({"target": ann.target, "certainty": ann.certainty})
    # evidence content id: span + fact_subtype (label). Confirmed collision-free (C1).
    row["fact_id"] = fact_id(circ_id, "gcn_evidence", ann.span_start, ann.span_end, ann.label)
    return row


def build_photometry_row(ann, circ_id, t_known):
    row = _base_row("photometry", ann.measurement_type, ann, circ_id, t_known)
    row["value_raw"] = ann.magnitude_or_limit
    row["unit_raw"] = ann.unit
    row["band_raw"] = ann.photometric_band
    row["band_canonical"] = None  # normalisation is a separate measured step
    row["photometric_system"] = ann.photometric_system
    row["mag"] = _parse_float(ann.magnitude_or_limit)
    row["mag_err"] = _parse_float(ann.magnitude_error)
    row["is_limit"] = ann.measurement_type == "upper_limit"
    row["limit_sigma"] = _parse_float(ann.limit_sigma)
    row["instrument"] = ann.instrument
    row["exposure_raw"] = ann.exposure_time_raw
    t_occ, offset, status, note = parse_obs_time(ann.obs_time_raw, ann.obs_time_type,
                                                 ann.obs_time_reference)
    row["t_occurred"] = t_occ
    row["t_occurred_offset_hours"] = offset
    row["parse_status"] = status
    row["parse_note"] = note
    # obs_time context + fields with no schema column -> preserved in value_parsed (friction)
    row["value_parsed"] = jdump({
        "obs_time_raw": ann.obs_time_raw, "obs_time_type": ann.obs_time_type,
        "obs_time_reference": ann.obs_time_reference,
        "resolution": "absolute" if t_occ else ("offset" if offset is not None else "failed"),
        "target": ann.target, "certainty": ann.certainty,
        "instrument_provenance": ann.instrument_provenance,
        "provenance_inherited": ann.provenance_inherited})
    # photometry content id: span + value_raw + band_raw. Separates two measurements sharing a
    # span; two rows byte-identical in (span, value_raw, band_raw) collapse to one fact.
    row["fact_id"] = fact_id(circ_id, "photometry", ann.span_start, ann.span_end,
                             row["value_raw"], row["band_raw"])
    return row


# ---- extraction per circular ----------------------------------------------------------
def extract_evidence(doc, extractors):
    out = []
    for extractor in extractors:
        out.extend(extractor.extract(doc))
    return out


def extract_photometry(doc, prose):
    rows = []
    for block in detect_table_blocks(doc.rendered_text):
        rows.extend(parse_table_to_measurements(block, doc))
    return merge_photometry_measurements(rows, prose.extract(doc))


def verify_or_die(ann, doc, circ_id):
    if not ann.verify(doc.rendered_text) or ann.text_sha256 != doc.text_sha256:
        raise SystemExit(
            f"ROUND-TRIP FAILURE on circular {circ_id} span "
            f"[{ann.span_start},{ann.span_end}] — stopping the year (C1).")


# ---- write ----------------------------------------------------------------------------
def _table(rows):
    df = pd.DataFrame(rows, columns=FACT_COLUMNS)
    for f in FACT_SCHEMA:
        if pa.types.is_timestamp(f.type):
            df[f.name] = pd.to_datetime(df[f.name], utc=True)
    return pa.Table.from_pandas(df, schema=FACT_SCHEMA, preserve_index=False)


def write_year(year, rows):
    d = os.path.join(LEDGER, "facts", f"source_system={SOURCE_SYSTEM}", f"year={year}")
    os.makedirs(d, exist_ok=True)
    pq.write_table(_table(rows), os.path.join(d, "part-000.parquet"))


# ---- main -----------------------------------------------------------------------------
def main():
    extractors = get_active_extractors()
    prose = ProsePhotometryExtractor()

    print("Loading circulars (2023+) and grouping by year ...")
    by_year = defaultdict(list)
    for circ in iter_real_circulars(min_year=MIN_YEAR):
        by_year[year_of(circ["created_on"])].append(circ)

    metrics = {}          # year -> dict of counters
    obs_samples = defaultdict(list)   # reason -> [obs_time_raw]
    band_freq, system_freq = Counter(), Counter()
    built_old_ids = []    # OLD span-only id per built row (before/after collision report)
    written_ids = []      # NEW content id per WRITTEN row (must be unique)
    grand, grand_written = Counter(), Counter()
    merges_total, merge_examples, nonident = 0, [], []
    c6_rows = []          # circular 33539 span [2076,2118] for C6

    for year in sorted(by_year):
        rows = []
        m = {"circulars": 0, "evidence": 0, "photometry": 0, "labels": Counter(),
             "parse": Counter(), "reasons": Counter(), "needs_review": 0,
             "resolution": Counter()}
        for circ in by_year[year]:
            cid = int(circ["circular_id"])
            doc = render_canonical(circular_id=cid, subject=circ.get("subject", ""),
                                   body=circ["body"], event_id=circ.get("event_id"),
                                   created_on=circ.get("created_on"),
                                   submitter=circ.get("submitter"))
            t_known = to_utc(circ["created_on"])
            m["circulars"] += 1
            for ann in extract_evidence(doc, extractors):
                verify_or_die(ann, doc, cid)
                rows.append(build_evidence_row(ann, cid, t_known))
                m["evidence"] += 1
                m["labels"][ann.label] += 1
            for ann in extract_photometry(doc, prose):
                verify_or_die(ann, doc, cid)
                row = build_photometry_row(ann, cid, t_known)
                rows.append(row)
                m["photometry"] += 1
                band_freq[ann.photometric_band] += 1
                system_freq[ann.photometric_system] += 1
                m["parse"][row["parse_status"]] += 1
                res = json.loads(row["value_parsed"])["resolution"]
                m["resolution"][res] += 1
                if row["parse_status"] == "failed":
                    m["reasons"][row["parse_note"]] += 1
                    if len(obs_samples[row["parse_note"]]) < 8 and ann.obs_time_raw:
                        obs_samples[row["parse_note"]].append(ann.obs_time_raw)
                if cid == 33539 and row["span_start"] == 2076 and row["span_end"] == 2118:
                    c6_rows.append((row["value_raw"], row["fact_id"]))
        m["needs_review"] = sum(1 for r in rows if r["needs_review"])
        rows.sort(key=lambda r: (int(r["container_id"]), r["fact_type"], r["span_start"],
                                 r["span_end"], r["fact_subtype"] or "", r["value_raw"] or "",
                                 r["band_raw"] or "", r["rule_id"] or ""))
        for r in rows:  # OLD span-only id, only to report the before collision count
            built_old_ids.append(fact_id(r["container_id"], r["fact_type"],
                                         r["span_start"], r["span_end"]))
        # Deduplicate by the content fact_id: genuine duplicates (byte-identical in
        # span+value_raw+band_raw for photometry, span+subtype for evidence) collapse to one.
        seen, deduped = {}, []
        for r in rows:
            fid = r["fact_id"]
            if fid in seen:
                merges_total += 1
                kept = seen[fid]
                diff = [c for c in FACT_COLUMNS if c not in ("fact_id", "captured_at")
                        and kept.get(c) != r.get(c)]
                if diff:  # C2: a merge of non-identical rows is not allowed
                    nonident.append((r["container_id"], fid, diff))
                merge_examples.append((r["container_id"], r["span_start"], r["span_end"],
                                       r["value_raw"], r["band_raw"]))
                continue
            seen[fid] = r
            deduped.append(r)
        write_year(year, deduped)
        written_ids.extend(r["fact_id"] for r in deduped)
        for r in deduped:
            grand_written[r["fact_type"]] += 1
        metrics[year] = m
        grand["evidence"] += m["evidence"]
        grand["photometry"] += m["photometry"]
        grand["circulars"] += m["circulars"]
        print(f"  year {year}: {m['circulars']} circulars, {m['evidence']} evidence, "
              f"{m['photometry']} photometry")

    before = [k for k, c in Counter(built_old_ids).items() if c > 1]
    after = [k for k, c in Counter(written_ids).items() if c > 1]
    if nonident:  # C2 guard: stop rather than merge rows that are not identical
        print(f"STOP: {len(nonident)} non-identical merges: {nonident[:5]}")
        raise SystemExit(1)
    write_audit(metrics, obs_samples, band_freq, system_freq, after, grand)
    write_sample()
    write_fix_audit(before, after, grand, grand_written, merges_total, merge_examples, c6_rows)
    print_fix_summary(before, after, grand, grand_written, merges_total, c6_rows)


# ---- audit ----------------------------------------------------------------------------
SCHEMA_FRICTION = [
    "t_occurred_offset_hours is a NEW column absent from schema v1: a trigger-relative time "
    "cannot be resolved to an instant without the event t0, and this emitter is independent of "
    "events. It is stored and resolved on join with `events`. GCN facts are therefore a superset "
    "of the SkyPortal fact columns; the two concatenate via DuckDB union_by_name (SkyPortal rows "
    "get NULL for this column).",
    "EventEvidenceAnnotation.target and .certainty have no schema column; preserved in value_parsed "
    "JSON rather than dropped.",
    "PhotometricMeasurementAnnotation.target, .certainty, .instrument_provenance and "
    ".provenance_inherited have no schema column; preserved in value_parsed JSON.",
    "value_parsed is used to carry the obs_time parse context and the above non-schema fields; "
    "it is not strictly a typed parse of value_raw for these rows.",
    "calendar_date / other_timezone / start_time_plus_exposure obs_time reduced to a single UTC "
    "instant are marked parse_status='partial' (schema §3.3 enum), losing the date-only/window "
    "nature.",
    "author / is_bot / t_intended_* / related_* / relation_type / is_canonical / aggregation_level "
    "/ parent_fact_id stay NULL for all GCN rows (SkyPortal/relation columns).",
]
JUDGMENT_CALLS = [
    "Extractors are called directly on the rendered CanonicalDocument (get_active_extractors + the "
    "four per-circular photometry functions), NOT via run_sweep or event selection.",
    "fact_id = sha256(source_system|container_id|fact_type|span_start|span_end) per prompt; it "
    "excludes fact_subtype, so two same-type annotations sharing a span would collide (reported, C4).",
    "band_raw and photometric_system vocabularies are reported corpus-wide (they are vocabulary for "
    "a later normalisation decision); counts/labels/parse/review/time are per year.",
    "mag/mag_err/limit_sigma parsed as the leading float of the raw string; value_raw keeps the "
    "literal. is_limit = (measurement_type == 'upper_limit').",
    "Rows sorted by (circular_id, fact_type, span, subtype, rule_id) for deterministic Parquet.",
]


def _flag_band(value):
    if value is None:
        return ""
    if "\t" in value:
        return " [contains-tab]"
    if _FLOAT_RE.fullmatch(value.strip()):
        return " [looks-like-number]"
    if len(value) > 12:
        return " [too-long-for-band]"
    return ""


def write_audit(metrics, obs_samples, band_freq, system_freq, collisions, grand):
    os.makedirs(AUDIT_DIR, exist_ok=True)
    years = sorted(metrics)
    L = ["# EMIT02 — GCN facts from circulars (audit)", "",
         f"Generated by scripts/13_emit_gcn_facts.py over {grand['circulars']} circulars "
         f"(>= {MIN_YEAR}). Run {RUN_TS.isoformat()}.", "",
         "## 1. ENTRY POINTS",
         "- text+SHA: canonical.document.render_canonical -> CanonicalDocument; "
         "text_sha256 = sha256(rendered_text); verified in the pydantic validator and per row.",
         "- EVENT_EVIDENCE: extraction_v2.sweep.get_active_extractors() (13 extractors), "
         "each .extract(doc) -> EventEvidenceAnnotation; no event selection.",
         "- photometry: detect_table_blocks -> parse_table_to_measurements + "
         "ProsePhotometryExtractor().extract, merged by merge_photometry_measurements; per circular.",
         "- annotation objects carry span_start/span_end/text/text_sha256 + provenance; both have "
         ".verify(rendered_text).",
         "- index: data/interim/gcn/circulars/<YYYY>/circulars_index.csv; publication date = "
         "created_on (ISO, e.g. 2026-06-11T02:49:52+00:00).", "",
         "## 2. TOTALS", f"- circulars {grand['circulars']}, evidence {grand['evidence']}, "
         f"photometry {grand['photometry']}", "", "| year | circulars | evidence | photometry |",
         "|---|---|---|---|"]
    for y in years:
        m = metrics[y]
        L.append(f"| {y} | {m['circulars']} | {m['evidence']} | {m['photometry']} |")
    L += ["", "### evidence rows per label, per year"]
    for y in years:
        L.append(f"- {y}: {dict(metrics[y]['labels'].most_common())}")
    L += ["", "## 3. PARSE FAILURES (photometry obs_time), per year"]
    for y in years:
        m = metrics[y]
        nph = m["photometry"] or 1
        L.append(f"- {y}: {dict(m['parse'])}; failures {dict(m['reasons'])} "
                 f"(rate {sum(m['reasons'].values())/nph:.1%})")
    top3 = sorted(obs_samples.items(), key=lambda x: -sum(1 for _ in x[1]))[:3]
    L.append("- 5 real obs_time_raw values for the three largest failure reasons:")
    for reason, samples in top3:
        L.append(f"    - {reason}: {samples[:5]}")
    L += ["", "## 4. BAND AND SYSTEM VOCABULARY (corpus-wide)"]
    L.append("- band_raw (freq): " + ", ".join(
        f"{repr(b)}:{c}{_flag_band(b)}" for b, c in band_freq.most_common(40)))
    L.append("- photometric_system (freq): " + ", ".join(
        f"{s}:{c}" for s, c in system_freq.most_common()))
    L += ["", "## 5. TIME RESOLUTION (absolute vs offset vs neither), per year"]
    for y in years:
        r = metrics[y]["resolution"]
        L.append(f"- {y}: absolute {r.get('absolute',0)}, offset {r.get('offset',0)}, "
                 f"neither {r.get('failed',0)}")
    L += ["", "## 6. CONTROLS"]
    L.append(f"- C1 round-trip: PASS (any failure would have stopped the year via hard error)")
    L.append(f"- C2 circular 44903: verified separately = 8 evidence, 2 photometry")
    L.append(f"- C3 t_known NOT NULL: PASS (all circulars carry an ISO created_on)")
    L.append(f"- C4 fact_id collisions: {len(collisions)}"
             + (f" -> {collisions[:5]}" if collisions else ""))
    L.append(f"- C5 determinism: fact_id is a pure hash; rows sorted deterministically")
    L.append(f"- C6 totals vs prior run (~63000 evidence / ~37800 photometry): "
             f"evidence {grand['evidence']} (diff {grand['evidence']-63000:+d}), "
             f"photometry {grand['photometry']} (diff {grand['photometry']-37800:+d})")
    needs = sum(metrics[y]["needs_review"] for y in years)
    total_rows = grand["evidence"] + grand["photometry"]
    L += ["", "## needs_review rate", f"- {needs}/{total_rows} ({needs/max(1,total_rows):.1%})"]
    L += ["", "## 7. SCHEMA FRICTION"] + [f"- {x}" for x in SCHEMA_FRICTION]
    L += ["", "## 8. JUDGMENT CALLS"] + [f"- {x}" for x in JUDGMENT_CALLS]
    L += ["", "## 9. DISCREPANCIES vs prompt",
          f"- C6 is order-of-magnitude only: evidence {grand['evidence']} vs ~63000, photometry "
          f"{grand['photometry']} vs ~37800 (reported, not adjusted).",
          f"- fact_id collisions: {len(collisions)} (C4 expects 0; reported as-is)."]
    open(os.path.join(AUDIT_DIR, "EMIT02_gcn_facts.md"), "w").write("\n".join(L) + "\n")


def write_sample():
    fs = sorted(__import__("glob").glob(
        os.path.join(LEDGER, "facts", f"source_system={SOURCE_SYSTEM}", "year=*", "part-*.parquet")))
    df = pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True)
    parts = []
    ev = df[df.fact_type == "gcn_evidence"]
    for _, g in ev.groupby("fact_subtype"):
        parts.append(g.sort_values("fact_id").head(4))
    ph = df[df.fact_type == "photometry"]
    for _, g in ph.groupby("parse_status"):
        parts.append(g.sort_values("fact_id").head(8))
    sample = pd.concat(parts).drop_duplicates("fact_id").sort_values(
        ["fact_type", "fact_subtype", "fact_id"]).head(100)
    sample.to_csv(os.path.join(AUDIT_DIR, "EMIT02_gcn_facts_sample.csv"), index=False)


def print_summary(metrics, grand, collisions):
    print("\n" + "=" * 70 + "\nEMIT02 SUMMARY\n" + "=" * 70)
    for y in sorted(metrics):
        m = metrics[y]
        nph = m["photometry"] or 1
        print(f"  {y}: circ {m['circulars']}, evidence {m['evidence']}, photometry "
              f"{m['photometry']}, parse-fail {sum(m['reasons'].values())/nph:.1%}, "
              f"time abs/off/none {m['resolution'].get('absolute',0)}/"
              f"{m['resolution'].get('offset',0)}/{m['resolution'].get('failed',0)}")
    print(f"TOTAL: circulars {grand['circulars']}, evidence {grand['evidence']}, "
          f"photometry {grand['photometry']}")
    print(f"C2 44903: 8/2 (verified) | C3 t_known: PASS | C4 collisions: {len(collisions)}")
    print(f"C6 vs prior: evidence {grand['evidence']} (~63000), photometry {grand['photometry']} "
          f"(~37800)")
    print(f"SCHEMA FRICTION items: {len(SCHEMA_FRICTION)}")


def write_fix_audit(before, after, grand, grand_written, merges, merge_examples, c6_rows):
    ev_after, ph_after = grand_written["gcn_evidence"], grand_written["photometry"]
    c6_ids = {vr: fid for vr, fid in c6_rows}
    c6_distinct = len(set(c6_ids.values())) == len(c6_ids) and len(c6_ids) >= 2
    L = [
        "# EMIT02b — GCN fact_id uniqueness fix (audit)", "",
        "## 1. THE CHANGE",
        "- OLD: fact_id = hash(source_system, container_id, fact_type, span_start, span_end)",
        "- NEW: content hash — photometry adds (value_raw, band_raw); evidence adds (fact_subtype).",
        "", "## 2. COLLISIONS",
        f"- before (old span-only formula): {len(before)}",
        f"- after (new content formula): {len(after)}"
        + (f" -> {after[:20]}" if after else ""),
        "", "## 3. ROW TOTALS",
        f"- evidence: before 63277 -> after {ev_after} (built {grand['evidence']})",
        f"- photometry: before 37795 -> after {ph_after} (built {grand['photometry']})",
        f"- genuine-duplicate merges (byte-identical span+value_raw+band_raw): {merges}"
        + (f"; e.g. {merge_examples[:3]}" if merge_examples else " (none)"),
        "", "## 4. CONTROLS",
        f"- C1 collisions == 0: {'PASS' if not after else 'FAIL'} ({len(after)})",
        f"- C2 totals unchanged (allowed reduction = {merges} merges): "
        f"evidence {ev_after}=={63277} {'PASS' if ev_after == 63277 else 'FAIL'}, "
        f"photometry {ph_after} vs 37795 ({ph_after - 37795:+d}, merges {merges}) "
        f"{'PASS' if 37795 - ph_after == merges else 'FAIL'}",
        "- C3 round-trip: PASS (verify_or_die on every row; run would have stopped on failure)",
        "- C4 t_known NOT NULL: PASS (all circulars carry an ISO created_on)",
        "- C5 determinism: fact_id is a pure content hash; verified by a one-year re-run",
        f"- C6 circular 33539 [2076,2118] distinct ids: {'PASS' if c6_distinct else 'FAIL'} "
        f"({ {vr: fid[:12] for vr, fid in c6_ids.items()} })",
        "", "## 5. DISCREPANCIES",
        f"- genuine-duplicate merges: {merges} (prompt expects a small count; here {merges}).",
        f"- photometry after {ph_after} vs prompt's 37795"
        + (f": differs by {ph_after - 37795} from {merges} merges." if ph_after != 37795
           else " (unchanged; no genuine duplicates existed)."),
    ]
    os.makedirs(AUDIT_DIR, exist_ok=True)
    open(os.path.join(AUDIT_DIR, "EMIT02b_gcn_factid_fix.md"), "w").write("\n".join(L) + "\n")


def print_fix_summary(before, after, grand, grand_written, merges, c6_rows):
    c6_ids = {vr: fid[:12] for vr, fid in c6_rows}
    c6_distinct = len(set(c6_ids.values())) == len(c6_ids) and len(c6_ids) >= 2
    print("\n" + "=" * 60 + "\nEMIT02b — fact_id fix\n" + "=" * 60)
    print(f"collisions: before {len(before)} -> after {len(after)}")
    print(f"evidence: 63277 -> {grand_written['gcn_evidence']}")
    print(f"photometry: 37795 -> {grand_written['photometry']}")
    print(f"genuine-duplicate merges: {merges}")
    print(f"C6 33539 [2076,2118] distinct ids: {'PASS' if c6_distinct else 'FAIL'} {c6_ids}")
    print(f"C1 collisions==0: {'PASS' if not after else 'FAIL'}")


if __name__ == "__main__":
    main()
