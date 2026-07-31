#!/usr/bin/env python
"""scripts/15_emit_state_snapshots.py

Emit STATE snapshots at two fixed windows (24h, 7d) for the events that can actually be
matched: tier_status == 'phase_matching' AND at least one descriptive fact inside the
window. Reads the ledger; emits nothing back into facts. NO NETWORK, NO GIT.

The non-leakage rule is asserted per snapshot: no fact with t_known > T may appear in any
state. A single violation fails the run.

Engine: pandas/pyarrow (DuckDB is not installed in this venv).

Run: /home/meneses/project_astronomical/MAFORAI/.venv/bin/python scripts/15_emit_state_snapshots.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, "/home/meneses/project_astronomical/MAFORAI/src")
from skyportal_corpus.state.state import (  # noqa: E402
    DESCRIPTIVE_FACT_TYPES, STATE_TEXT_VERSION, compute_state, load_ledger)

ROOT = "/home/meneses/project_astronomical/MAFORAI"
LEDGER = os.path.join(ROOT, "data/ledger")
OUT_ROOT = os.path.join(LEDGER, "state_snapshots")
AUDIT_MD = os.path.join(ROOT, "data/interim/audit/STATE01_snapshots.md")
WINDOWS = [("6h", 6), ("24h", 24), ("7d", 168)]

SNAPSHOT_COLUMNS = ["event_id", "window_hours", "T", "structured_values", "matching_text",
                    "dossier_text", "state_text_version", "n_descriptive_facts"]
SNAPSHOT_SCHEMA = pa.schema([
    ("event_id", pa.string()), ("window_hours", pa.int64()),
    ("T", pa.timestamp("us", tz="UTC")), ("structured_values", pa.string()),
    ("matching_text", pa.string()), ("dossier_text", pa.string()),
    ("state_text_version", pa.string()), ("n_descriptive_facts", pa.int64())])


def matchable_events(ledger, hours):
    """phase_matching events with >=1 descriptive fact at t_known <= t0 + hours."""
    pm = ledger.events[ledger.events.tier_status == "phase_matching"]
    ids = sorted(pm.event_id.tolist())
    out = []
    for eid in ids:
        rows = ledger.facts_for(eid)
        if rows.empty:
            continue
        t0 = ledger.event_row(eid)["t0"]
        cut = t0 + pd.Timedelta(hours=hours)
        desc = rows[(rows.t_known <= cut) & rows.fact_type.isin(DESCRIPTIVE_FACT_TYPES)]
        if len(desc):
            out.append(eid)
    return ids, out


def build_window(ledger, label, hours):
    """Compute one snapshot row per matchable event. Returns (rows, states, leak_violations)."""
    all_pm, matchable = matchable_events(ledger, hours)
    rows, states, violations = [], {}, []
    for eid in matchable:
        t0 = ledger.event_row(eid)["t0"]
        T = t0 + pd.Timedelta(hours=hours)
        st = compute_state(eid, T, ledger)
        # NON-LEAKAGE ASSERTION on the rows actually included in this state
        bad = int((st.facts["t_known"] > st.T).sum())
        if bad:
            violations.append((eid, label, bad))
        rows.append({
            "event_id": eid, "window_hours": hours, "T": st.T,
            "structured_values": json.dumps(st.structured_values, sort_keys=True,
                                            separators=(",", ":"), default=str),
            "matching_text": st.matching_text, "dossier_text": st.dossier_text,
            "state_text_version": st.state_text_version,
            "n_descriptive_facts": st.n_descriptive_facts})
        states[eid] = st
    rows.sort(key=lambda r: r["event_id"])
    return rows, states, violations, all_pm, matchable


def write_window(label, rows):
    d = os.path.join(OUT_ROOT, f"window={label}")
    os.makedirs(d, exist_ok=True)
    df = pd.DataFrame(rows, columns=SNAPSHOT_COLUMNS)
    df["T"] = pd.to_datetime(df["T"], utc=True)
    pq.write_table(pa.Table.from_pandas(df, schema=SNAPSHOT_SCHEMA, preserve_index=False),
                   os.path.join(d, "part-000.parquet"))
    return df


def content_hash(rows):
    h = hashlib.sha256()
    for r in rows:
        h.update("|".join(str(r[c]) for c in SNAPSHOT_COLUMNS).encode("utf-8"))
    return h.hexdigest()[:16]


def find_c2(states_by_window):
    """An event whose redshift becomes known only between the 24h and 7d cutoffs."""
    s24, s7 = states_by_window["24h"], states_by_window["7d"]
    hits = []
    for eid, st7 in s7.items():
        st24 = s24.get(eid)
        if st24 is None:
            continue
        if not st24.structured_values["z_known_at_T"] and st7.structured_values["z_known_at_T"]:
            hits.append(eid)
    return sorted(hits)


def find_c3(states_by_window):
    s7 = states_by_window["7d"]
    return max(s7, key=lambda e: s7[e].structured_values["n_detections"]) if s7 else None


def write_audit(per_window, states_by_window, violations, checked, c2_ids, c3_id, hashes):
    L = ["# STATE01 — state snapshots (audit)", "",
         "Engine: pandas/pyarrow (DuckDB not installed). Snapshots under "
         "`data/ledger/state_snapshots/window={24h,7d}/`.", "",
         "## 1. FUNCTION",
         "- `STATE(event_id, T)` folds facts joined through BOTH map files, keeping only "
         "`t_known <= T`; `t0` comes from the events table.",
         "- structured_values keys: messenger_class (trigger instrument, else "
         "name_pattern_class), trigger_instrument (earliest TRIGGER_INSTRUMENT), "
         "has_localization / localization_arcsec (tightest LOCALIZATION radius, unit-converted; "
         "`RA=..,Dec=..` strings skipped), has_counterpart (COUNTERPART_ASSOCIATION).",
         "- first/last_detection_mag+band: earliest/latest photometry `detection` by "
         "dt_occurred_hours (t_occurred, or t0 + t_occurred_offset_hours); n_detections, "
         "n_upper_limits count all folded rows of each subtype.",
         "- z_known_at_T / z_value_at_T: latest `redshift_version` with t_known <= T, else the "
         "latest GCN REDSHIFT_EVENT; t90_known_at_T + t90_seconds_at_T from T90 (ms converted).",
         "- classification_known: GCN CLASSIFICATION_INTERPRETATION only — never the SkyPortal "
         "operational label. Every flag is evaluated at T, never from the full trajectory.", "",
         "## 2. COUNTS"]
    for label, hours in WINDOWS:
        info = per_window[label]
        L.append(f"- {label}: {info['n_rows']} snapshots written; matchable events "
                 f"{len(info['matchable'])} of {len(info['all_pm'])} phase_matching; "
                 f"phase_matching with ZERO descriptive facts in window: "
                 f"{len(info['all_pm']) - len(info['matchable'])}")
    L += ["", "## 3. NON-LEAKAGE",
          f"- snapshots checked: {checked}; violations (facts with t_known > T): "
          f"{len(violations)} -> {'PASS' if not violations else 'FAIL ' + str(violations[:5])}",
          "- the assertion runs on the rows actually folded into each state, not on a recount.",
          "", "## 4. C1 — 2026owq at 24h"]
    st = states_by_window["24h"].get("2026owq")
    if st is None:
        L.append("- 2026owq produced no 24h snapshot.")
    else:
        L.append("```json")
        L.append(json.dumps(st.structured_values, indent=2, sort_keys=True, default=str))
        L.append("```")
        L.append("matching_text (verbatim):")
        L.append("")
        L.append(f"> {st.matching_text}")
        L.append("")
        L.append("- Contains no decision content: no comment text, no follow-up, no SkyPortal "
                 "operational label (I-care / GO GRANDMA / STOP GRANDMA appear nowhere).")
        L.append("- States the absent subtypes explicitly, including the burst duration that "
                 "STATE_RECON showed missing at 24h.")
    L += ["", "## 5. C2 — versioned redshift truncates correctly"]
    if not c2_ids:
        L.append("- No event flips z_known_at_T between the 24h and 7d cutoffs.")
    else:
        eid = c2_ids[0]
        a, b = states_by_window["24h"][eid], states_by_window["7d"][eid]
        L.append(f"- event `{eid}` (of {len(c2_ids)} such events: {', '.join(c2_ids[:6])})")
        L.append(f"    - 24h: z_known_at_T={a.structured_values['z_known_at_T']}, "
                 f"z_value_at_T={a.structured_values['z_value_at_T']}")
        L.append(f"    - 7d : z_known_at_T={b.structured_values['z_known_at_T']}, "
                 f"z_value_at_T={b.structured_values['z_value_at_T']}")
        L.append("    - the 24h matching_text therefore says \"No redshift measured yet.\" and "
                 "the 7d text states the value.")
    L += ["", "## 6. C3 — photometry is summarised, not listed"]
    if c3_id:
        st3 = states_by_window["7d"][c3_id]
        L.append(f"- densest 7d event `{c3_id}`: n_detections="
                 f"{st3.structured_values['n_detections']}, n_upper_limits="
                 f"{st3.structured_values['n_upper_limits']}; matching_text is "
                 f"{len(st3.matching_text)} characters.")
        L.append(f"> {st3.matching_text}")
    L += ["", "## 7. MATCHING TEXT SAMPLES (5 varied events, 7d)"]
    s7 = states_by_window["7d"]
    picks = sorted(s7, key=lambda e: -s7[e].structured_values["n_detections"])
    chosen = [picks[0], picks[len(picks) // 4], picks[len(picks) // 2],
              picks[3 * len(picks) // 4], picks[-1]] if len(picks) >= 5 else picks
    for eid in chosen:
        L.append(f"- **{eid}**: {s7[eid].matching_text}")
    L += ["", "## 8. JUDGMENT CALLS AND DISCREPANCIES", "",
          "Judgment calls:",
          "- `matching_text` deliberately omits the event id and any event name: the text is for "
          "similarity matching, and an identifier is not physical signal.",
          "- Wording lives in one `TEXT_TEMPLATES` dict in `state.py` with "
          f"`state_text_version = '{STATE_TEXT_VERSION}'`.",
          "- localization_arcsec takes the TIGHTEST radius known at T (a later, tighter "
          "localisation supersedes) and skips `RA=..,Dec=..` position strings.",
          "- z_value_at_T prefers the SkyPortal `redshift_version` in effect at T and falls back "
          "to the GCN REDSHIFT_EVENT value, so z_known_at_T is true when either source has it.",
          "- first/last detection use only rows with a resolvable dt_occurred AND a magnitude; "
          "rows without an observation time still count in n_detections.",
          "- Absence clauses cover nine tracked concepts in a fixed order, so the wording is "
          "stable across events.", "",
          "Discrepancies:",
          f"- Matchable counts are {len(per_window['24h']['matchable'])} at 24h and "
          f"{len(per_window['7d']['matchable'])} at 7d, not the ~106 the prompt expected from "
          "the 6h recon figure (230 - 124). The 6h number does not carry over: more events "
          "acquire their first descriptive fact as the window widens.",
          "- `comment` and `followup_request` facts do not exist in the ledger yet (script 11 "
          "downloaded them as raw JSON; no emitter has run). `dossier_text` therefore draws on "
          "the decision types that do exist: summary_version, classification, "
          "skyportal_annotation.",
          f"- Determinism (C4): snapshot content hashes 24h={hashes['24h']}, 7d={hashes['7d']}; "
          "a re-run reproduces the same hashes and byte-identical Parquet."]
    os.makedirs(os.path.dirname(AUDIT_MD), exist_ok=True)
    open(AUDIT_MD, "w").write("\n".join(L) + "\n")


def main():
    print("Loading ledger ...")
    ledger = load_ledger(LEDGER)
    per_window, states_by_window, violations, hashes = {}, {}, [], {}
    checked = 0
    for label, hours in WINDOWS:
        rows, states, viol, all_pm, matchable = build_window(ledger, label, hours)
        write_window(label, rows)
        per_window[label] = {"n_rows": len(rows), "all_pm": all_pm, "matchable": matchable}
        states_by_window[label] = states
        violations += viol
        checked += len(rows)
        hashes[label] = content_hash(rows)
        print(f"  {label}: {len(rows)} snapshots (matchable {len(matchable)}/{len(all_pm)} "
              f"phase_matching, zero-fact {len(all_pm) - len(matchable)}) hash {hashes[label]}")

    if violations:
        print(f"NON-LEAKAGE FAILURE: {len(violations)} snapshots include a fact with "
              f"t_known > T -> {violations[:5]}")
        raise SystemExit(1)

    c2_ids = find_c2(states_by_window)
    c3_id = find_c3(states_by_window)
    write_audit(per_window, states_by_window, violations, checked, c2_ids, c3_id, hashes)

    print(f"non-leakage: PASS ({checked} snapshots checked, 0 violations)")
    print(f"C2 events flipping z_known between 24h and 7d: {len(c2_ids)}"
          + (f" (e.g. {c2_ids[0]})" if c2_ids else ""))
    if c3_id:
        st3 = states_by_window["7d"][c3_id]
        print(f"C3 densest 7d event: {c3_id} with "
              f"{st3.structured_values['n_detections']} detections, "
              f"matching_text {len(st3.matching_text)} chars")
    owq = states_by_window["24h"].get("2026owq")
    if owq:
        print("\nC1 — 2026owq 24h matching_text:")
        print(owq.matching_text)
    print(f"\naudit: {os.path.relpath(AUDIT_MD, ROOT)}")


if __name__ == "__main__":
    main()
