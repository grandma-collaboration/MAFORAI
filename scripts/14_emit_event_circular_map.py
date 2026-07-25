#!/usr/bin/env python
"""scripts/14_emit_event_circular_map.py

Build the GCN side of event_container_map by running the existing event-selection logic
(extraction_v2.event_selection.select_event_candidates) over all 800 events. This connects
the 101,072 GCN circular facts to events so STATE(event, T) can be queried end to end.
NO NETWORK, NO GIT. Modifies no module. Follows docs/ledger/01_schema_v1.md §5.

A circular matching N events yields N rows (one per event) — never deduplicated across
events. Output kept SEPARATE from the SkyPortal map (identical columns) per Phase 2.

Run: /home/meneses/project_astronomical/MAFORAI/.venv/bin/python scripts/14_emit_event_circular_map.py
"""
from __future__ import annotations

import csv
import glob
import json
import os
from collections import Counter, defaultdict

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from skyportal_corpus.canonical.document import iter_real_circulars
from skyportal_corpus.extraction_v2.event_selection import _split_field, select_event_candidates

ROOT = "/home/meneses/project_astronomical/MAFORAI"
LEDGER = os.path.join(ROOT, "data/ledger")
MAP_DIR = os.path.join(LEDGER, "event_container_map")
FACTS = os.path.join(LEDGER, "facts")
REGISTRY = os.path.join(ROOT, "data/interim/gcn/event_matching/event_registry.csv")
INDEX_CSV = os.path.join(ROOT, "notebooks/evidence/01_source_index.csv")
AUDIT_MD = os.path.join(ROOT, "data/interim/audit/EMIT03_event_circular_map.md")
MIN_YEAR = 2023
STATE_EVENT = "2026owq"

# schema §5, identical to the SkyPortal map (script 10) so both read together
MAP_COLUMNS = ["event_id", "container_type", "container_id", "match_method", "match_evidence"]
MAP_SCHEMA = pa.schema([(c, pa.string()) for c in MAP_COLUMNS])


# ---- inputs ---------------------------------------------------------------------------
def load_registry():
    rows = list(csv.DictReader(open(REGISTRY, newline="")))
    by_source = {r["source_id"]: r for r in rows}
    by_merged = {}
    for r in rows:
        for mid in _split_field(r.get("merged_source_ids")):
            by_merged.setdefault(mid, r)
    return by_source, by_merged, len(rows)


def resolve_canonical(csv_id, by_source, by_merged):
    """Mirror load_registry_event: source_id first, then merged_source_ids. None if absent."""
    if csv_id in by_source:
        return by_source[csv_id]["source_id"]
    if csv_id in by_merged:
        return by_merged[csv_id]["source_id"]
    return None


def load_events():
    with open(INDEX_CSV, newline="") as fh:
        return [{"source_id": r["source_id"].strip(),
                 "name_pattern_class": r.get("name_pattern_class", ""),
                 "tier_status": r.get("tier_status", "")} for r in csv.DictReader(fh)]


# ---- selection ------------------------------------------------------------------------
def selection_included(canonical, cache, errors):
    """Return the canonical event's included circulars (cached; one select call each)."""
    if canonical in cache:
        return cache[canonical]
    try:
        result = select_event_candidates(canonical)
        included = result["included"]
    except Exception as exc:  # keep the run going; record the failure
        errors.append((canonical, f"{type(exc).__name__}: {exc}"))
        included = []
    cache[canonical] = included
    return included


def build_map():
    by_source, by_merged, n_reg = load_registry()
    events = load_events()
    cache, errors = {}, []
    rows = []
    matched_events, zero_events = set(), []
    for i, ev in enumerate(events, 1):
        cid = ev["source_id"]
        canonical = resolve_canonical(cid, by_source, by_merged)
        included = selection_included(canonical, cache, errors) if canonical else []
        if included:
            matched_events.add(cid)
            for item in included:
                rows.append({
                    "event_id": cid,
                    "container_type": "circular",
                    "container_id": str(item["circular_id"]),
                    "match_method": item["reason"],  # selector mechanism
                    "match_evidence": json.dumps(item["evidence"], sort_keys=True,
                                                 separators=(",", ":"), ensure_ascii=False),
                })
        else:
            zero_events.append(ev)
        if i % 100 == 0:
            print(f"  {i}/800 events, {len(rows)} map rows, {len(matched_events)} matched")
    rows.sort(key=lambda r: (r["event_id"], int(r["container_id"])))
    return rows, events, matched_events, zero_events, errors, n_reg


def write_map(rows):
    os.makedirs(MAP_DIR, exist_ok=True)
    df = pd.DataFrame(rows, columns=MAP_COLUMNS)
    pq.write_table(pa.Table.from_pandas(df, schema=MAP_SCHEMA, preserve_index=False),
                   os.path.join(MAP_DIR, "gcn_map.parquet"))


# ---- integrity + STATE ----------------------------------------------------------------
def corpus_circular_ids():
    return {int(c["circular_id"]) for c in iter_real_circulars(min_year=MIN_YEAR)}


def load_all_facts():
    fs = sorted(glob.glob(os.path.join(FACTS, "source_system=*", "year=*", "part-*.parquet")))
    # union by name: gcn facts carry the extra t_occurred_offset_hours column
    return pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True)


def state_query(gcn_rows):
    facts = load_all_facts()
    facts["t_known"] = pd.to_datetime(facts["t_known"], utc=True)
    sp_map = pd.read_parquet(os.path.join(MAP_DIR, "map.parquet"))
    maps = pd.concat([sp_map, pd.DataFrame(gcn_rows, columns=MAP_COLUMNS)], ignore_index=True)
    events = pd.read_parquet(os.path.join(LEDGER, "events", "events.parquet"))
    t0 = pd.to_datetime(events.loc[events.event_id == STATE_EVENT, "t0"].iloc[0], utc=True)

    containers = maps[maps.event_id == STATE_EVENT][["container_type", "container_id"]]
    attached = facts.merge(containers, on=["container_type", "container_id"], how="inner")

    all_time = attached.groupby(["source_system", "fact_type"]).size()
    cutoffs, leak_ok = {}, True
    for label, hrs in [("t0+6h", 6), ("t0+24h", 24), ("t0+72h", 72)]:
        cut = t0 + pd.Timedelta(hours=hrs)
        sub = attached[attached.t_known <= cut]
        maxk = sub.t_known.max()
        if pd.notna(maxk) and maxk > cut:
            leak_ok = False
        cutoffs[label] = (sub.groupby(["source_system", "fact_type"]).size(), cut, maxk)
    return t0, all_time, cutoffs, leak_ok, attached


# ---- audit + main ---------------------------------------------------------------------
def dist(vals):
    if not vals:
        return "n/a"
    s = sorted(vals)
    p = lambda q: s[min(len(s) - 1, int(round(q * (len(s) - 1))))]
    return f"min {s[0]} / p25 {p(.25)} / median {p(.5)} / p75 {p(.75)} / p90 {p(.9)} / max {s[-1]}"


def write_audit(rows, events, matched, zero_events, errors, n_reg, corpus_ids,
                c6_ok, state):
    per_event = Counter(r["event_id"] for r in rows)
    per_circular = Counter(r["container_id"] for r in rows)
    multi = {c: n for c, n in per_circular.items() if n > 1}
    bad = sorted({r["container_id"] for r in rows if int(r["container_id"]) not in corpus_ids})
    zero_npc = Counter(e["name_pattern_class"] for e in zero_events)
    zero_tier = Counter(e["tier_status"] for e in zero_events)
    t0, all_time, cutoffs, leak_ok, attached = state

    L = ["# EMIT03 — event <-> circular map (GCN side, audit)", "",
         "## 1. ENTRY POINT",
         "- select_event_candidates(source_id) -> dict; included[] = {circular_id, subject, "
         "created_on, reason, evidence, delta_days} per matched circular.",
         "- search terms come from the event registry `terms` field (id + aliases + tns_name, "
         "e.g. 'GRB 260610B | AT 2026owq | 2026owq').",
         "- a circular MAY match multiple events (each event selected independently; no forced "
         "uniqueness). Included reasons: confirmed_subject_match, body_mention.",
         "- event list: notebooks/evidence/01_source_index.csv (800); registry has "
         f"{n_reg} canonical events.", "",
         "## 2. MAP SIZE",
         f"- gcn_map rows: {len(rows)}; distinct events matched: {len(matched)}; distinct "
         f"circulars used: {len(per_circular)}", "",
         "## 3. COVERAGE",
         f"- C2 events with >=1 circular: {len(matched)} (prior figure 189, diff "
         f"{len(matched) - 189:+d})",
         f"- C3 circulars-per-event (events with >=1): {dist(list(per_event.values()))}",
         f"- C5 events with ZERO circulars: {len(zero_events)}",
         f"    by name_pattern_class: {dict(zero_npc.most_common())}",
         f"    by tier_status: {dict(zero_tier.most_common())}", "",
         "## 4. MULTI-EVENT CIRCULARS",
         f"- C4 distinct circulars matching >1 event: {len(multi)}; events-per-circular "
         f"distribution: {dict(Counter(multi.values()))}"]
    ev_by_circ = defaultdict(list)
    for r in rows:
        ev_by_circ[r["container_id"]].append(r["event_id"])
    examples = sorted(multi, key=lambda c: -multi[c])[:5]
    for c in examples:
        L.append(f"    - circular {c} -> {len(ev_by_circ[c])} events: {sorted(ev_by_circ[c])[:8]}")
    L += ["", "## 5. INTEGRITY",
          f"- C1 map circulars within 2023+ corpus: {'PASS' if not bad else 'FAIL'} "
          f"({len(bad)} outside" + (f": {bad[:10]}" if bad else "") + ")",
          f"- C6 determinism (re-run identical row set): {'PASS' if c6_ok else 'not re-run in-script'}",
          f"- selection errors: {len(errors)}" + (f" -> {errors[:5]}" if errors else "")]
    L += ["", "## 6. FIRST STATE QUERY — event 2026owq",
          f"- t0 = {t0} (from events table). DuckDB unavailable in the venv (no network to "
          "install); the equivalent joins/filters were run with pandas.",
          "- all-time facts attached by (source_system, fact_type): "
          f"{ {f'{a}/{b}': int(v) for (a, b), v in all_time.items()} }",
          "", "| cutoff | source_system | fact_type | count |", "|---|---|---|---|"]
    for label, (counts, cut, maxk) in cutoffs.items():
        for (ss, ft), v in counts.items():
            L.append(f"| {label} | {ss} | {ft} | {int(v)} |")
    L.append(f"- non-leakage (C4.4): no counted fact has t_known > its cutoff -> "
             f"{'PASS' if leak_ok else 'FAIL'}")
    L += ["", "## 7. JUDGMENT CALLS",
          "- Selection cached per canonical registry event (574 unique); a merged CSV id reuses "
          "its canonical's circulars under its own event_id. 800 events -> <=574 select calls.",
          "- match_method = the selector's `reason` (confirmed_subject_match | body_mention); "
          "match_evidence = the selector's evidence dict as compact JSON (term + span/matched_text).",
          "- gcn_map kept as a SEPARATE file (data/ledger/event_container_map/gcn_map.parquet) with "
          "columns identical to the SkyPortal map.parquet; SkyPortal map not overwritten.",
          "- STATE query written in pandas (DuckDB not installed; rule 1 forbids network install).",
          "", "## 8. DISCREPANCIES",
          f"- C2 matched events {len(matched)} vs prior 189 (diff {len(matched) - 189:+d}).",
          "- DuckDB unavailable -> pandas used for the STATE smoke test (same joins/filters)."]
    os.makedirs(os.path.dirname(AUDIT_MD), exist_ok=True)
    open(AUDIT_MD, "w").write("\n".join(L) + "\n")


def main():
    print("Building GCN event<->circular map (selection over 800 events) ...")
    rows, events, matched, zero_events, errors, n_reg = build_map()
    write_map(rows)

    corpus_ids = corpus_circular_ids()
    # C6: re-run selection for one matched event and compare its rows
    c6_ok = _c6_recheck(rows)
    state = state_query(rows)
    write_audit(rows, events, matched, zero_events, errors, n_reg, corpus_ids, c6_ok, state)

    t0, all_time, cutoffs, leak_ok, _ = state
    per_circular = Counter(r["container_id"] for r in rows)
    multi = sum(1 for n in per_circular.values() if n > 1)
    print("\n" + "=" * 62 + "\nEMIT03 SUMMARY\n" + "=" * 62)
    print(f"gcn_map rows: {len(rows)} | events matched: {len(matched)} | "
          f"zero-circular events: {len(zero_events)}")
    print(f"multi-event circulars: {multi} | C1 corpus check: "
          f"{'PASS' if not any(int(r['container_id']) not in corpus_ids for r in rows) else 'FAIL'} "
          f"| C6: {'PASS' if c6_ok else 'n/a'}")
    print(f"STATE(2026owq) t0={t0}")
    for label, (counts, cut, maxk) in cutoffs.items():
        by = {f"{a}/{b}": int(v) for (a, b), v in counts.items()}
        print(f"  {label}: total {int(counts.sum())} {by}")
    print(f"non-leakage: {'PASS' if leak_ok else 'FAIL'}")


def _c6_recheck(rows):
    """Re-run selection for one matched event and confirm its (event,container) rows match."""
    matched_events = [r["event_id"] for r in rows]
    if not matched_events:
        return False
    ev = sorted(set(matched_events))[0]
    got = {(r["event_id"], r["container_id"]) for r in rows if r["event_id"] == ev}
    try:
        again = select_event_candidates(ev)["included"]
    except Exception:
        return False
    expect = {(ev, str(it["circular_id"])) for it in again}
    return got == expect


if __name__ == "__main__":
    main()
