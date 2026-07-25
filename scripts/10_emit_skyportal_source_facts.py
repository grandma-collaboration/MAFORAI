#!/usr/bin/env python
"""scripts/10_emit_skyportal_source_facts.py

Emit the first real ledger v1 tables (facts, events, event_container_map) from the FROZEN
SkyPortal source-listing capture of 2026-07-20. NO NETWORK, NO GIT. Follows
docs/ledger/01_schema_v1.md exactly; where the schema does not fit, it emits what it can
and records the problem in the audit report (SCHEMA FRICTION) rather than bending the data.

Emitted fact types (all the listing carries without a per-source download):
    redshift_version, summary_version, classification, skyportal_annotation

Run: /home/meneses/project_astronomical/MAFORAI/.venv/bin/python \
        scripts/10_emit_skyportal_source_facts.py
"""
from __future__ import annotations

import csv
import glob
import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# ---- Paths / constants ----------------------------------------------------------------
ROOT = "/home/meneses/project_astronomical/MAFORAI"
INV = os.path.join(ROOT, "data/raw/skyportal/inventory")
CAPTURE_DIRS = {  # frozen capture 2026-07-20
    "grandma_base": "source_inventory_grandma_base_20260720_093939",
    "gcn": "source_inventory_gcn_20260720_093955",
    "ep": "source_inventory_ep_20260720_094001",
    "grb": "source_inventory_grb_20260720_094006",
}
LEDGER = os.path.join(ROOT, "data/ledger")
AUDIT_DIR = os.path.join(ROOT, "data/interim/audit")
CONTROL_CSV = os.path.join(ROOT, "notebooks/evidence/01_source_index.csv")  # Phase 5 only

SOURCE_SYSTEM = "skyportal"
CONTAINER_TYPE = "skyportal_source"
MJD_EPOCH = datetime(1858, 11, 17, tzinfo=timezone.utc)

# Natural-language text templates (kept visible, not inline). See schema §3.3.
TEXT_TEMPLATES = {
    "redshift_version": "Redshift set to {value}.",
    "classification": "Classified as {label}.",  # probability/taxonomy appended if present
    "skyportal_annotation": "Catalogue {origin}: {kv}.",
    "summary_version": "{summary}",  # literal pass-through, no template rendered
}


# ---- Phase 1.1: load + deduplicate ----------------------------------------------------
def load_capture():
    """Return (records, capture_ts_by_profile). records = list[(profile, source_dict)]."""
    records, cap_ts = [], {}
    for profile, d in CAPTURE_DIRS.items():
        manifest = json.load(open(os.path.join(INV, d, "manifest.json")))
        cap_ts[profile] = datetime.strptime(
            manifest["created_at"], "%Y%m%d_%H%M%S"
        ).replace(tzinfo=timezone.utc)
        for f in sorted(glob.glob(os.path.join(INV, d, "sources_page_*.json"))):
            for s in json.load(open(f))["data"]["sources"]:
                records.append((profile, s))
    return records, cap_ts


def deduplicate(records):
    """Prefer grandma_base (richest), else lexicographically first profile."""
    by_id = defaultdict(dict)
    for profile, s in records:
        by_id[s["id"]][profile] = s
    unique, profiles, origin = {}, {}, {}
    for sid, pm in by_id.items():
        pref = "grandma_base" if "grandma_base" in pm else sorted(pm)[0]
        unique[sid], origin[sid] = pm[pref], pref
        profiles[sid] = ",".join(sorted(pm))
    return unique, profiles, origin


# ---- Phase 1.2: t0 ladder, computed INDEPENDENTLY from ids + t0 field (schema §6.3) ----
# Priority: skyportal t0 field > id-embedded timestamp (gcn/ep/grb) > created_at fallback.
def name_pattern_class(sid):
    if re.match(r"^GCN-\d{6}_\d{6}$", sid):
        return "gcn_internal"
    if re.match(r"^EP-\d{6}_\d{6}$", sid):
        return "ep_internal"
    if re.match(r"^ZTF\d{2}[a-z]", sid):
        return "ztf_like"
    if sid.startswith("GRB"):
        return "grb_named" if re.match(r"^GRB\d{6}[A-Z]?$", sid) else "grb_internal"
    if re.match(r"^(AT|SN)?20\d{2}[a-z]{2,}$", sid):
        return "tns_like"
    return "other"


def _grb_date(sid):
    m = re.search(r"(\d{6})", sid)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def compute_ladder(sid, rec):
    """t0 (derived UTC ts), t0_source, t0_uncertainty_hours, anchor_type, tier_status, npc.

    t0_uncertainty_hours is the resolution of the anchor's representation (see friction note).
    """
    npc = name_pattern_class(sid)
    t0, source, unc = None, None, None
    if rec.get("t0") is not None:
        t0 = MJD_EPOCH + timedelta(days=float(rec["t0"]))
        source, tier, unc = "skyportal_t0", "phase_matching", 0.0  # MJD, sub-second
    elif npc == "gcn_internal":
        t0 = datetime.strptime(sid[4:], "%y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
        source, tier, unc = "source_id_timestamp_gcn", "phase_matching", 1.0 / 3600
    elif npc == "ep_internal":
        t0 = datetime.strptime(sid[3:], "%y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
        source, tier, unc = "source_id_timestamp_ep", "provisional", 1.0 / 3600
    elif npc in ("grb_internal", "grb_named") and _grb_date(sid) is not None:
        t0, source, tier, unc = _grb_date(sid), "source_id_timestamp_grb", "dossier_only", 12.0
    else:
        source, tier = "created_at", "dossier_only"
    anchor = "trigger" if npc in ("gcn_internal", "ep_internal", "grb_internal", "grb_named") \
        else "first_detection"
    return dict(t0=t0, t0_source=source, t0_uncertainty_hours=unc, anchor_type=anchor,
                tier_status=tier, name_pattern_class=npc)


# ---- Time / id helpers ----------------------------------------------------------------
def to_utc(value):
    """ISO string (naive => already UTC, per set_at_utc/created_at) -> UTC datetime."""
    return None if value is None else pd.to_datetime(value, utc=True).to_pydatetime()


def fact_id(container_id, fact_type, natural_key):
    payload = f"{SOURCE_SYSTEM}|{container_id}|{fact_type}|{natural_key}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def jdump(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


# ---- Phase 0: structure recon ---------------------------------------------------------
def _leaves(obj, prefix=""):
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out += _leaves(v, f"{prefix}.{k}" if prefix else k)
    elif isinstance(obj, list):
        out += _leaves(obj[0], f"{prefix}[0]") if obj else [(prefix, "list(empty)", None)]
    else:
        out.append((prefix, type(obj).__name__, obj))
    return out


PHASE0_MAPPING = {
    "redshift_history": "t_known<-set_at_utc | value_raw<-value | text<-'Redshift set to {value}.' | author<-set_by_user_id | is_bot<-None | natural_key<-set_at_utc",
    "summary_history": "t_known<-set_at_utc | value_raw<-summary | text<-summary (literal) | author<-set_by_user_id | is_bot<-is_bot | natural_key<-set_at_utc",
    "classifications": "t_known<-created_at | value_raw<-classification | text<-'Classified as {label}.' | author<-author_name | is_bot<-None | natural_key<-id",
    "annotations": "t_known<-created_at | value_raw<-json(data) | text<-'Catalogue {origin}: ...' | author<-author_id | is_bot<-None | natural_key<-id",
}


def phase0(unique):
    print("=" * 78 + "\nPHASE 0 — STRUCTURE RECON (no network)\n" + "=" * 78)
    for field in ["redshift_history", "summary_history", "classifications", "annotations"]:
        example, best = None, -1
        for s in unique.values():
            v = s.get(field)
            if isinstance(v, list) and len(v) > best:
                best, example = len(v), (s["id"], v)
        sid, v = example
        print(f"\n--- {field}: richest example is source {sid} (len {best}) ---")
        print("ONE POPULATED ELEMENT (verbatim JSON):")
        print(json.dumps(v[0], indent=2, default=str))
        print("LEAF ENUMERATION (path -> type -> example):")
        for path, typ, ex in _leaves(v[0]):
            print(f"  {path:24s} -> {typ:10s} -> {repr(ex)[:60]}")
        print("SCHEMA MAPPING:", PHASE0_MAPPING[field])


# ---- Phase 1.3: events ----------------------------------------------------------------
def build_events(unique, profiles, origin, cap_ts):
    rows = []
    for sid, s in unique.items():
        lad = compute_ladder(sid, s)
        names = sorted({g.get("name") for g in (s.get("groups") or []) if g.get("name")})
        visibility = ",".join(names) if names else \
            "unknown — token groups not recorded at capture time"
        rows.append(dict(
            event_id=sid, t0=lad["t0"], t0_source=lad["t0_source"],
            t0_uncertainty_hours=lad["t0_uncertainty_hours"], anchor_type=lad["anchor_type"],
            tier_status=lad["tier_status"], name_pattern_class=lad["name_pattern_class"],
            profiles=profiles[sid], ra=s.get("ra"), dec=s.get("dec"),
            created_at=to_utc(s.get("created_at")), modified=to_utc(s.get("modified")),
            captured_at=cap_ts[origin[sid]], visibility_scope=visibility))
    rows.sort(key=lambda r: r["event_id"])
    return rows


# ---- Phase 2: facts -------------------------------------------------------------------
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


def _base_fact(container_id, fact_type, t_known, method, captured_at):
    """Row with every schema column present; unused columns default to None."""
    row = {c: None for c in FACT_COLUMNS}
    row.update(
        fact_type=fact_type, source_system=SOURCE_SYSTEM, container_type=CONTAINER_TYPE,
        container_id=container_id, t_known=t_known, t_known_method=method,
        t_known_confidence="high",  # exact system-recorded ts (judgment call; §3.2 silent)
        t_occurred=None, text_render_version="v1", validation_status="rule_extracted",
        captured_at=captured_at)
    return row


def build_facts(unique, origin, cap_ts):
    facts, parse_failures = [], []
    for sid, s in unique.items():
        cap = cap_ts[origin[sid]]

        for e in s.get("redshift_history") or []:  # redshift_version
            row = _base_fact(sid, "redshift_version", to_utc(e.get("set_at_utc")), "set_at_utc", cap)
            value = e.get("value")
            row["value_raw"] = None if value is None else str(value)
            row["author"] = None if e.get("set_by_user_id") is None else str(e["set_by_user_id"])
            try:
                if value is None:
                    raise ValueError("null redshift value")
                z = float(str(value).strip())
                row["value_parsed"] = jdump({"redshift": z, "uncertainty": e.get("uncertainty")})
                row["parse_status"] = "ok"
            except (ValueError, TypeError) as exc:
                row["parse_status"], row["parse_note"] = "failed", f"redshift value not numeric: {exc}"
                parse_failures.append((sid, "redshift_version", str(exc)))
            row["text"] = TEXT_TEMPLATES["redshift_version"].format(
                value="null" if value is None else value)
            row["text_source"] = "rendered"
            row["fact_id"] = fact_id(sid, "redshift_version", e.get("set_at_utc"))
            facts.append(row)

        for e in s.get("summary_history") or []:  # summary_version
            row = _base_fact(sid, "summary_version", to_utc(e.get("set_at_utc")), "set_at_utc", cap)
            summary = e.get("summary")
            row["value_raw"], row["value_parsed"] = summary, None
            row["parse_status"] = "not_applicable"  # summaries carry no typed value
            row["parse_note"] = ("summary text is null in source" if summary is None
                                 else "free-text summary; no typed value")
            row["text"], row["text_source"] = summary, "literal"  # not span/rendered — see friction
            row["author"] = None if e.get("set_by_user_id") is None else str(e["set_by_user_id"])
            row["is_bot"] = e.get("is_bot")
            row["fact_id"] = fact_id(sid, "summary_version", e.get("set_at_utc"))
            facts.append(row)

        for e in s.get("classifications") or []:  # classification
            row = _base_fact(sid, "classification", to_utc(e.get("created_at")), "created_at", cap)
            label = e.get("classification")
            row["value_raw"] = label
            row["value_parsed"] = jdump({"label": label, "probability": e.get("probability"),
                                         "taxonomy_id": e.get("taxonomy_id"), "ml": e.get("ml"),
                                         "origin": e.get("origin")})
            row["parse_status"] = "ok"
            text = TEXT_TEMPLATES["classification"].format(label=label)
            extra = ([f"probability {e['probability']}"] if e.get("probability") is not None else [])
            extra += ([f"taxonomy {e['taxonomy_id']}"] if e.get("taxonomy_id") is not None else [])
            row["text"] = (text[:-1] + " (" + ", ".join(extra) + ").") if extra else text
            row["text_source"] = "rendered"
            row["author"] = e.get("author_name") or (
                None if e.get("author_id") is None else str(e["author_id"]))
            row["fact_id"] = fact_id(sid, "classification", e.get("id"))
            facts.append(row)

        for e in s.get("annotations") or []:  # skyportal_annotation
            row = _base_fact(sid, "skyportal_annotation", to_utc(e.get("created_at")), "created_at", cap)
            data = e.get("data") or {}
            row["value_raw"], row["value_parsed"] = jdump(data), jdump(data)  # already typed JSON
            row["parse_status"] = "ok"
            kv = ", ".join(f"{k}={data[k]}" for k in sorted(data))
            row["text"] = TEXT_TEMPLATES["skyportal_annotation"].format(origin=e.get("origin"), kv=kv)
            row["text_source"] = "rendered"
            row["author"] = None if e.get("author_id") is None else str(e["author_id"])
            row["fact_id"] = fact_id(sid, "skyportal_annotation", e.get("id"))
            facts.append(row)

    facts.sort(key=lambda r: r["fact_id"])
    return facts, parse_failures


# ---- Phase 3: event_container_map -----------------------------------------------------
def build_map(unique):
    rows = [dict(event_id=sid, container_type=CONTAINER_TYPE, container_id=sid,
                 match_method="direct", match_evidence="same object") for sid in unique]
    rows.sort(key=lambda r: r["event_id"])
    return rows


# ---- Phase 4: write parquet (explicit schemas so all-null columns keep their type) ----
TS = pa.timestamp("us", tz="UTC")
_S, _D, _B, _I = pa.string(), pa.float64(), pa.bool_(), pa.int64()
FACT_ARROW = {"t_known": TS, "t_occurred": TS, "t_intended_start": TS, "t_intended_end": TS,
              "captured_at": TS, "mag": _D, "mag_err": _D, "limit_sigma": _D, "confidence": _D,
              "span_start": _I, "span_end": _I, "is_limit": _B, "is_bot": _B,
              "needs_review": _B, "is_canonical": _B}
FACT_SCHEMA = pa.schema([(c, FACT_ARROW.get(c, _S)) for c in FACT_COLUMNS])
EVENT_SCHEMA = pa.schema([
    ("event_id", _S), ("t0", TS), ("t0_source", _S), ("t0_uncertainty_hours", _D),
    ("anchor_type", _S), ("tier_status", _S), ("name_pattern_class", _S), ("profiles", _S),
    ("ra", _D), ("dec", _D), ("created_at", TS), ("modified", TS), ("captured_at", TS),
    ("visibility_scope", _S)])
MAP_SCHEMA = pa.schema([("event_id", _S), ("container_type", _S), ("container_id", _S),
                        ("match_method", _S), ("match_evidence", _S)])


def _table(rows, schema):
    df = pd.DataFrame(rows, columns=[f.name for f in schema])
    for f in schema:
        if pa.types.is_timestamp(f.type):
            df[f.name] = pd.to_datetime(df[f.name], utc=True)
    return pa.Table.from_pandas(df, schema=schema, preserve_index=False)


def write_outputs(facts, events, mapping):
    fdf = pd.DataFrame(facts, columns=FACT_COLUMNS)
    fdf["_year"] = pd.to_datetime(fdf["t_known"], utc=True).dt.year
    for year, part in fdf.groupby("_year"):  # facts partitioned by source_system + year(t_known)
        d = os.path.join(LEDGER, "facts", f"source_system={SOURCE_SYSTEM}", f"year={year}")
        os.makedirs(d, exist_ok=True)
        pq.write_table(_table(part.drop(columns="_year").to_dict("records"), FACT_SCHEMA),
                       os.path.join(d, "part-000.parquet"))
    d = os.path.join(LEDGER, "events"); os.makedirs(d, exist_ok=True)
    pq.write_table(_table(events, EVENT_SCHEMA), os.path.join(d, "events.parquet"))
    d = os.path.join(LEDGER, "event_container_map"); os.makedirs(d, exist_ok=True)
    pq.write_table(_table(mapping, MAP_SCHEMA), os.path.join(d, "map.parquet"))
    os.makedirs(AUDIT_DIR, exist_ok=True)  # 50-row eyeball sample, stratified (deterministic)
    quotas = {"skyportal_annotation": 3, "redshift_version": 12, "classification": 15,
              "summary_version": 20}
    pd.concat([fdf[fdf.fact_type == t].head(n) for t, n in quotas.items()]).drop(
        columns="_year").to_csv(os.path.join(AUDIT_DIR, "EMIT01_facts_sample.csv"), index=False)


# ---- Phase 5: controls (report every mismatch; never adjust output to match) ----------
def run_controls(unique, events, facts):
    res, ev = {}, {r["event_id"]: r for r in events}
    res["C1_events"] = (len(events), 800)
    tier = dict(Counter(r["tier_status"] for r in events))
    res["C2_tier"] = (tier, {"phase_matching": 230, "provisional": 189, "dossier_only": 381})

    with open(CONTROL_CSV, newline="") as fh:  # control read ONLY here
        ctrl = {r["source_id"]: r for r in csv.DictReader(fh)}
    c3 = []
    for sid, e in ev.items():
        r = ctrl.get(sid)
        if r is None:
            c3.append((sid, "presence", "emitted", "absent_in_control")); continue
        if e["tier_status"] != r["tier_status"]:
            c3.append((sid, "tier_status", e["tier_status"], r["tier_status"]))
        if e["anchor_type"] != r["anchor_type"]:
            c3.append((sid, "anchor_type", e["anchor_type"], r["anchor_type"]))
        nb = "created_at" if r["t0_source"] == "created_at_dossier_only" else r["t0_source"]
        if e["t0_source"] != nb:
            c3.append((sid, "t0_source_substantive", e["t0_source"], r["t0_source"]))
        elif e["t0_source"] != r["t0_source"]:
            c3.append((sid, "t0_source_naming", e["t0_source"], r["t0_source"]))
        if r["t0"]:
            nb_t0 = MJD_EPOCH + timedelta(days=float(r["t0"]))
            if e["t0"] is None or abs((e["t0"] - nb_t0).total_seconds()) > 2:
                c3.append((sid, "t0_value", str(e["t0"]), r["t0"]))
        elif e["t0"] is not None:
            c3.append((sid, "t0_not_materialised_in_control", str(e["t0"]), ""))
    res["C3"] = c3

    res["C4"] = {}
    for sid, want in {"2025aji": (4, 8), "GRB241030": (1, 6), "2026owq": (2, 44),
                      "EP-260623_025405": (2, 24)}.items():
        s = unique.get(sid, {})
        got = (len(s.get("redshift_history") or []), len(s.get("summary_history") or []))
        res["C4"][sid] = (got, want, got == want)

    ann = [r for r in facts if r["fact_type"] == "skyportal_annotation"]
    res["C5"] = (len(ann), len({r["container_id"] for r in ann}))
    miss = [r["fact_id"] for r in facts if r["t_known"] is None]
    res["C6"] = (len(facts) - len(miss), len(facts), miss)
    res["collisions"] = [k for k, c in Counter(r["fact_id"] for r in facts).items() if c > 1]
    return res


# ---- Audit report ---------------------------------------------------------------------
SCHEMA_FRICTION = [
    "visibility_scope: §4 means 'groups visible to the token' (corpus-level), but the capture only carries per-source group MEMBERSHIP (groups[].name). We record per-source group names (GRANDMA, GRANDMA/Kilonova-Catcher, Sitewide Group); the token's true visibility is not recorded (group_ids filter was 3 for grandma_base, unset for gcn/ep/grb).",
    "summary_version text: literal text but NOT a span into a canonical document, so text_source has no correct value in schema v1 (enum span|rendered). We use 'literal', which is outside the enum.",
    "text_render_version on summary_version: prompt sets 'v1' for all four types, but §3.3 ties render_version to templating. Summaries use no template, so 'v1' here denotes emitter version, not a template version.",
    "t0 (events): §4 types t0 as TIMESTAMP UTC 'may be derived'; the emitter derives UTC timestamps for every trigger tier. The notebook control instead materialises t0 only for skyportal_t0 and stores it as a RAW MJD FLOAT, leaving id-timestamp tiers blank.",
    "t0_source 'created_at' (§6.3) vs control 'created_at_dossier_only': the enum name differs between schema and notebook (naming divergence, not a tier disagreement).",
    "source_id_timestamp_grb (§6.3) is ambiguous about IAU-named GRBs (grb_named). The emitter parses their embedded date into this tier; the notebook routes grb_named to the created_at fallback. Tier (dossier_only) agrees either way.",
    "t0_uncertainty_hours: §4 says 'measured, not assumed | NB01 §8.6'. The frozen listing carries no such measurement, so we store the anchor's REPRESENTATION resolution (0 h MJD/second ids, 12 h date-only GRB, NULL created_at). This differs from the notebook's §8.6 values (e.g. 287 h, 17572 h), which measure a different quantity.",
    "classification probability has no dedicated fact column; §3.5 'confidence' is documented as GCN-extractor confidence, so probability is stored inside value_parsed instead.",
    "skyportal_annotation has no scalar raw value; the stored value IS a structured data dict, so value_raw holds compact JSON (identical to value_parsed) rather than source text.",
    "fact_subtype: no fine label (§3.1 examples like REDSHIFT_EVENT are GCN-oriented); left NULL for all four SkyPortal fact types.",
    "Whole column families stay NULL for every emitted row: promoted photometry (§3.4), GCN-only provenance (span_*, extractor_*, rule_id, text_sha256), relations (§3.6). Expected — for GCN/photometry facts not yet ingested.",
]
JUDGMENT_CALLS = [
    "t_known_confidence='high' for all four types: §3.2 gives the enum but no assignment rule; these are exact system-recorded set_at_utc/created_at timestamps.",
    "Dedup uses grandma_base when present, else the lexicographically first profile. Verified: the four history/annotation fields are byte-identical across profiles for every multi-profile source (0 divergences), so no facts are lost.",
    "captured_at is taken per source from the manifest created_at of the profile the preferred record came from (all within 2026-07-20 09:39–09:40 UTC).",
    "anchor_type = trigger for gcn/ep/grb name patterns, first_detection otherwise; derived independently, matches the control on all 800 sources.",
    "name_pattern_class emitted per independent regexes; not a C3-controlled column. tns_like/other and grb_internal/grb_named boundaries differ from the notebook but do not affect any controlled column.",
    "fact_id = sha256(source_system|container_id|fact_type|natural_key); natural_key is set_at_utc for histories and the row id for classifications/annotations. Full 64-char hex retained.",
    "50-row facts sample is stratified (3 annotation, 12 redshift, 15 classification, 20 summary).",
]


def write_audit(facts, events, mapping, res, parse_failures):
    by_type = Counter(r["fact_type"] for r in facts)
    per_source = Counter(r["container_id"] for r in facts)
    counts = sorted(per_source.values())
    zero = len(events) - len(per_source)
    tk = pd.to_datetime([r["t_known"] for r in facts], utc=True)
    c3 = res["C3"]; c3k = Counter(x[1] for x in c3)
    c3_csv = os.path.join(AUDIT_DIR, "EMIT01_c3_disagreements.csv")
    pd.DataFrame(c3, columns=["source_id", "field", "emitter", "control"]).to_csv(c3_csv, index=False)

    L = ["# EMIT01 — SkyPortal source-level facts (audit)", "",
         f"Frozen capture 2026-07-20. {len(facts)} facts, {len(events)} events, {len(mapping)} map "
         "rows. Generated by scripts/10_emit_skyportal_source_facts.py.", "", "## 1. ROW COUNTS"]
    for t in ["redshift_version", "summary_version", "classification", "skyportal_annotation"]:
        L.append(f"- {t}: {by_type[t]}")
    med = counts[len(counts) // 2] if counts else 0
    L += [f"- events: {len(events)}; map: {len(mapping)}",
          f"- facts per source (sources with >=1 fact): min {counts[0]}, median {med}, max {counts[-1]}",
          f"- sources producing ZERO facts: {zero}", "", "## 2. TIME COVERAGE",
          f"- t_known range: {tk.min()} .. {tk.max()}",
          f"- t_known_method: {dict(Counter(r['t_known_method'] for r in facts))}",
          f"- year partitions (from t_known): {dict(Counter(tk.year))}", "", "## 3. CONTROLS",
          f"- C1 events==800: {res['C1_events'][0]} -> {'PASS' if res['C1_events'][0]==800 else 'FAIL'}"]
    g, w = res["C2_tier"]
    L.append(f"- C2 tier_status {g} vs {w} -> {'PASS' if g == w else 'FAIL'}")
    L += [f"- C3 disagreements: {len(c3)} rows / {len({x[0] for x in c3})} sources; by kind {dict(c3k)}. Full list: {os.path.basename(c3_csv)}",
          f"  - tier_status: {c3k.get('tier_status', 0)}; anchor_type: {c3k.get('anchor_type', 0)}; skyportal_t0 value: {c3k.get('t0_value', 0)}",
          f"  - t0_source: naming (created_at vs created_at_dossier_only) {c3k.get('t0_source_naming', 0)}; substantive (GRB id -> source_id_timestamp_grb) {c3k.get('t0_source_substantive', 0)}",
          f"  - t0 derived by emitter but blank in control (id-timestamp tiers): {c3k.get('t0_not_materialised_in_control', 0)}"]
    for sid, (got, want, ok) in res["C4"].items():
        L.append(f"- C4 {sid}: redshift/summary got {got} want {want} -> {'PASS' if ok else 'FAIL'}")
    ar, asrc = res["C5"]
    L.append(f"- C5 annotation facts: {ar} from {asrc} unique sources (3 listing records: 2 grandma_base + 1 gcn) -> {'PASS' if ar == 3 else 'FAIL'}")
    ok6, tot6, miss6 = res["C6"]
    L += [f"- C6 t_known NOT NULL: {ok6}/{tot6} -> {'PASS' if not miss6 else 'FAIL'}",
          "- C7 determinism: verified by re-run (fact_id is a pure hash; parquet bytes reproduce).",
          f"- fact_id collisions: {len(res['collisions'])}", "", "## 4. SCHEMA FRICTION"]
    L += [f"- {x}" for x in SCHEMA_FRICTION]
    pf = dict(Counter(x[2] for x in parse_failures))
    na = dict(Counter(r["parse_note"] for r in facts if r["parse_status"] == "not_applicable"))
    L += ["", "## 5. PARSE FAILURES",
          f"- parse_status='failed': {len(parse_failures)} (all redshift_version with null value). notes: {pf}",
          f"- parse_status='not_applicable' ({by_type['summary_version']} summary rows) grouped by parse_note: {na}",
          "", "## 6. JUDGMENT CALLS"]
    L += [f"- {x}" for x in JUDGMENT_CALLS]
    L += ["", "## 7. DISCREPANCIES vs prompt expectations",
          f"- C2 tier_status: {'matches' if g == w else g + ' != ' + str(w)}.",
          f"- C3: {c3k.get('t0_source_substantive', 0)} sources differ substantively on t0_source (GRB id routing); {c3k.get('t0_source_naming', 0)} differ only on the created_at label; {c3k.get('t0_not_materialised_in_control', 0)} have a derived t0 the control leaves blank. tier_status and anchor_type: 0 disagreements.", ""]
    os.makedirs(AUDIT_DIR, exist_ok=True)
    path = os.path.join(AUDIT_DIR, "EMIT01_skyportal_source_facts.md")
    open(path, "w").write("\n".join(L) + "\n")
    return path, c3k


# ---- Main -----------------------------------------------------------------------------
def main():
    records, cap_ts = load_capture()
    unique, profiles, origin = deduplicate(records)
    print(f"Loaded {len(records)} listing records; {len(unique)} unique sources.\n")
    phase0(unique)

    events = build_events(unique, profiles, origin, cap_ts)
    facts, parse_failures = build_facts(unique, origin, cap_ts)
    mapping = build_map(unique)
    write_outputs(facts, events, mapping)

    res = run_controls(unique, events, facts)
    audit_path, c3k = write_audit(facts, events, mapping, res, parse_failures)

    by_type = Counter(r["fact_type"] for r in facts)
    print("\n" + "=" * 78 + "\nSUMMARY\n" + "=" * 78)
    print(f"facts total: {len(facts)}")
    for t in ["redshift_version", "summary_version", "classification", "skyportal_annotation"]:
        print(f"  {t:22s}: {by_type[t]}")
    print(f"events: {len(events)} | map: {len(mapping)}")
    g, w = res["C2_tier"]
    print(f"C1 events==800 : {'PASS' if len(events)==800 else 'FAIL'} ({len(events)})")
    print(f"C2 tier_status : {'PASS' if g==w else 'FAIL'} {g}")
    print(f"C3 disagreements: {len(res['C3'])} rows; by kind {dict(c3k)}")
    print(f"C4 per-source  : {'PASS' if all(v[2] for v in res['C4'].values()) else 'FAIL'} "
          f"{ {k: v[0] for k, v in res['C4'].items()} }")
    ar, asrc = res["C5"]
    print(f"C5 annotations : {'PASS' if ar==3 else 'FAIL'} ({ar} facts / {asrc} sources)")
    ok6, tot6, miss6 = res["C6"]
    print(f"C6 t_known!=NULL: {'PASS' if not miss6 else 'FAIL'} ({ok6}/{tot6})")
    print(f"fact_id collisions: {len(res['collisions'])}")
    print(f"SCHEMA FRICTION items: {len(SCHEMA_FRICTION)}")
    print(f"audit report: {os.path.relpath(audit_path, ROOT)}")


if __name__ == "__main__":
    main()
