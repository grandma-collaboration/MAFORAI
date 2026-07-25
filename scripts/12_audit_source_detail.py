#!/usr/bin/env python
"""scripts/12_audit_source_detail.py

Regenerate data/interim/audit/DL01_source_detail.md from the FULL source-detail corpus
downloaded by scripts/11 (--all), joined against the frozen 2026-07-20 listing (for July
photstats) and notebooks/evidence/01_source_index.csv (for t0 / name_pattern_class).

Read-only, NO NETWORK. Keeps the existing 8 sections (full-run numbers) and adds sections
A-G. Reports differences; never adjusts numbers to match expectations. Audit < 200 lines.

Run: /home/meneses/project_astronomical/MAFORAI/.venv/bin/python scripts/12_audit_source_detail.py
"""
from __future__ import annotations

import csv
import glob
import json
import os
from collections import Counter, defaultdict

ROOT = "/home/meneses/project_astronomical/MAFORAI"
CORPUS = sorted(glob.glob(os.path.join(ROOT, "data/raw/skyportal/source_detail_*")))[-1]
INDEX_CSV = os.path.join(ROOT, "notebooks/evidence/01_source_index.csv")
JULY_INV = os.path.join(ROOT, "data/raw/skyportal/inventory")
JULY_DIRS = {
    "grandma_base": "source_inventory_grandma_base_20260720_093939",
    "gcn": "source_inventory_gcn_20260720_093955",
    "ep": "source_inventory_ep_20260720_094001",
    "grb": "source_inventory_grb_20260720_094006",
}
AUDIT_MD = os.path.join(ROOT, "data/interim/audit/DL01_source_detail.md")
COLLECTIONS = ["comments", "photometry", "spectra", "followup_requests"]
LIST_KEYS = ("followup_requests", "spectra", "comments", "photometry", "requests")
PREFLIGHT = ["2025aji", "2026owq", "GRB241030", "EP-260623_025405", "GCN-251013_173943"]
# Step-0 (July) ENDPOINT photometry counts — directly comparable to the same endpoint now.
JULY_ENDPOINT = {"2025aji": 345, "2026owq": 106, "GRB241030": 131, "EP-260623_025405": 30}
PERSONAL_FIELDS = ["first_name", "last_name", "expiration_date", "contact_email",
                   "contact_phone", "oauth_uid", "username", "affiliations"]


# ---- loaders --------------------------------------------------------------------------
def extract_records(payload):
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in LIST_KEYS:
            if isinstance(data.get(k), list):
                return data[k]
    return None


def load_corpus():
    """Per source: {collection: count|None}, pages, totalMatches, and raw followup records."""
    counts, pages, totals, followups = {}, {}, {}, {}
    for sid in sorted(os.listdir(CORPUS)):
        d = os.path.join(CORPUS, sid)
        if not os.path.isdir(d):
            continue
        counts[sid] = {}
        for c in COLLECTIONS:
            f = os.path.join(d, f"{c}.json")
            if not os.path.exists(f):
                counts[sid][c] = None
                continue
            w = json.load(open(f))
            recs = extract_records(w.get("payload"))
            counts[sid][c] = len(recs) if isinstance(recs, list) else 0
            if w.get("pages_fetched", 1) > 1:
                pages[(sid, c)] = w["pages_fetched"]
            if w.get("totalMatches") is not None:
                totals[(sid, c)] = w["totalMatches"]
            if c == "followup_requests" and isinstance(recs, list):
                followups[sid] = recs
    return counts, pages, totals, followups


def load_july_photstats():
    """(num_det_global, num_obs_global) per source from the frozen July listing.

    num_det_global counts DETECTIONS only; num_obs_global counts all observations (incl.
    non-detections/limits). The endpoint returns all points, so num_obs_global is the true
    all-points upper bound; num_det_global is used because the prompt names it.
    """
    by_id = defaultdict(dict)
    for prof, d in JULY_DIRS.items():
        for f in sorted(glob.glob(os.path.join(JULY_INV, d, "sources_page_*.json"))):
            for s in json.load(open(f))["data"]["sources"]:
                by_id[s["id"]][prof] = s
    det, obs = {}, {}
    for sid, pm in by_id.items():
        s = pm.get("grandma_base") or next(iter(pm.values()))
        ps = s.get("photstats")
        if isinstance(ps, list) and ps:
            if ps[0].get("num_det_global") is not None:
                det[sid] = ps[0]["num_det_global"]
            if ps[0].get("num_obs_global") is not None:
                obs[sid] = ps[0]["num_obs_global"]
    return det, obs


def load_index():
    with open(INDEX_CSV, newline="") as fh:  # strip: one id ('AT2023toh\t') carries a trailing tab
        return {r["source_id"].strip(): r for r in csv.DictReader(fh)}


def load_progress():
    """(latencies[200], errors{status:[sids]}) from progress.log.

    Parsed from the END: one source id ('AT2023toh\\t') contains a tab, so a positional
    split from the front would misalign the status/collection fields.
    """
    lats, errors = [], defaultdict(list)
    log = os.path.join(CORPUS, "progress.log")
    if os.path.exists(log):
        for line in open(log):
            p = line.rstrip("\n").split("\t")
            if len(p) < 6:
                continue
            status, sid = p[-3], p[1]
            if status == "200":
                try:
                    lats.append(float(p[-1]))
                except ValueError:
                    pass
            elif status != "None":
                errors[status].append(sid)
    return lats, errors


# ---- stats helpers --------------------------------------------------------------------
def pct(vals, q):
    if not vals:
        return 0
    s = sorted(vals)
    return s[min(len(s) - 1, int(round(q * (len(s) - 1))))]


def dist_row(vals):
    zeros = sum(1 for v in vals if v == 0)
    return (f"0-count {zeros} | min {min(vals) if vals else 0} | p25 {pct(vals, .25)} | "
            f"median {pct(vals, .5)} | p75 {pct(vals, .75)} | p90 {pct(vals, .9)} | "
            f"max {max(vals) if vals else 0} | total {sum(vals)}")


def col_bytes(collection):
    total = 0
    for f in glob.glob(os.path.join(CORPUS, "*", f"{collection}.json")):
        total += os.path.getsize(f)
    return total


# ---- audit builder --------------------------------------------------------------------
def build():
    counts, pages, totals, followups = load_corpus()
    july, july_obs = load_july_photstats()
    index = load_index()
    lats, errors = load_progress()
    manifest = json.load(open(os.path.join(CORPUS, "manifest.json")))
    sids = list(counts)
    n = len(sids)
    missing = sorted(set(index) - set(sids))  # index ids with no corpus dir (all 4 collections errored)

    # per-collection present-count lists (record counts where a file was written)
    present = {c: [counts[s][c] for s in sids if counts[s][c] is not None] for c in COLLECTIONS}
    # sources returning zero across ALL FOUR (files present, all empty)
    zero_all = [s for s in sids
                if all(counts[s][c] == 0 for c in COLLECTIONS)]

    L = ["# DL01 — SkyPortal per-source detail (audit, FULL RUN)", "",
         f"Full-run capture in `{os.path.relpath(CORPUS, ROOT)}` regenerated by "
         f"scripts/12_audit_source_detail.py (read-only). {n} source directories of "
         f"{len(index)} index ids ({len(missing)} produced no dir — all four collections errored).",
         f"On-disk note: the 5 preflight sources are 2.00 MB on disk; the prompt's ~2.65 MB is "
         "the sum of wire response sizes, not stored bytes.", ""]

    # -- Section 1: PREFLIGHT (5 sources) + verification --------------------------------
    L += ["## 1. PREFLIGHT (5 fixed sources)", "", "| source | comments | photometry | spectra | followup |",
          "|---|---|---|---|---|"]
    for s in PREFLIGHT:
        c = counts.get(s, {})
        L.append(f"| {s} | {c.get('comments')} | {c.get('photometry')} | {c.get('spectra')} | "
                 f"{c.get('followup_requests')} |")
    L += ["", "### 1b. Pagination completeness (verified in preflight, numPerPage=1 probe)",
          "- comments & photometry: ignore paging (numPerPage=1 still returned the full list) -> SAFE",
          "- followup_requests: honours paging but advertises totalMatches -> looped to completeness",
          "- spectra: only 1 record corpus-wide (2026cex); cannot stress-test; returned complete"]

    # -- Section 2: COVERAGE (brief; detail in A) ---------------------------------------
    L += ["", "## 2. COVERAGE (full run; detailed distribution in A)"]
    for c in COLLECTIONS:
        nonempty = sum(1 for v in present[c] if v > 0)
        L.append(f"- {c}: {len(present[c])} files, {nonempty} non-empty, total {sum(present[c])} records")

    # -- Section 3 / 4 pointers ---------------------------------------------------------
    L += ["", "## 3. VOLUME (detail in G)", f"- total on disk see G; dominant collection: "
          "followup_requests", "", "## 4. ERRORS (detail in F)",
          f"- non-200 statuses: { {k: len(v) for k, v in errors.items()} or 'none'}"]

    # -- Section 5: VISIBILITY ----------------------------------------------------------
    groups = manifest["visibility_scope"]["groups"]
    now_grb = counts.get("GRB241030", {}).get("photometry")
    L += ["", "## 5. VISIBILITY",
          "- token groups: " + ", ".join(f"{g['name']}(id {g['id']})" for g in groups),
          "- access change vs July: token gained 'GRB 122522A science' (id 175), absent from the "
          "2026-07-20 listing's 3 groups.",
          f"- GRB241030 photometry (same endpoint): 77 (pre-access) -> 131 (July) -> {now_grb} (now)."]

    # -- Section 6: PERSONAL DATA (all sources) -----------------------------------------
    pfields, prec_with, prec_total, psrc = Counter(), 0, 0, 0
    for s, recs in followups.items():
        if recs:
            psrc += 1
        for rec in recs:
            prec_total += 1
            found = set()
            _collect_personal(rec, found)
            if found:
                prec_with += 1
            for k in found:
                pfields[k] += 1
    L += ["", "## 6. PERSONAL DATA (follow-up requests, all sources)",
          f"- {psrc} sources carry follow-up requests ({prec_total} records). Personal fields "
          f"in {prec_with}/{prec_total} records: {dict(pfields)}. Flagged; nothing stripped."]

    # -- Section A: count distributions -------------------------------------------------
    L += ["", "## A. COUNT DISTRIBUTIONS (per collection, over fetched sources)"]
    for c in COLLECTIONS:
        L.append(f"- {c}: {dist_row(present[c])}")
    L.append(f"- sources returning ZERO records across ALL FOUR collections: {len(zero_all)} "
             f"(the genuinely empty part of the corpus)")

    # -- Section B: pagination in practice ----------------------------------------------
    multi = Counter(c for (s, c) in pages)
    max_total = max(totals.values()) if totals else 0
    L += ["", "## B. PAGINATION IN PRACTICE",
          f"- sources needing >1 page: { {c: multi.get(c, 0) for c in COLLECTIONS} }",
          f"- largest totalMatches seen: {max_total}"]
    if not multi:
        L.append("- No source needed more than one page: the page-loop is insurance, not a fix "
                 "for an observed truncation.")

    # -- Section C: photometry now vs July ----------------------------------------------
    now_phot = {s: counts[s]["photometry"] for s in sids if counts[s]["photometry"] is not None}
    c1 = [(s, now_phot[s], july[s]) for s in now_phot if s in july and now_phot[s] > july[s]]
    c1_obs = [(s, now_phot[s], july_obs[s]) for s in now_phot
              if s in july_obs and now_phot[s] > july_obs[s]]
    deltas = [july[s] - now_phot[s] for s in now_phot if s in july]
    L += ["", "## C. PHOTOMETRY: NOW vs JULY (july = photstats.num_det_global, a GLOBAL count)"]
    L.append(f"- C.1 now_count > july num_det_global: {len(c1)} sources. CAVEAT: num_det_global "
             "counts DETECTIONS only, whereas the endpoint returns all points incl. non-detections "
             "(upper limits), so exceedance is EXPECTED and is not evidence of added rows.")
    L.append(f"    cross-check vs num_obs_global (all-points upper bound): {len(c1_obs)} sources exceed"
             + ((", incl. " + ", ".join(f"{s}(now {a}>obs {b})" for s, a, b in c1_obs[:8]))
                if c1_obs else "")
             + " -> these ARE genuine additions or stale July photstats.")
    invisible = sum(d for d in deltas if d > 0)
    L.append(f"- C.2 (num_det_global - now), positive = invisible-detection lower bound: total "
             f"{invisible} over {sum(1 for d in deltas if d > 0)} sources; per-source "
             f"{dist_row([max(0, d) for d in deltas])}")
    L.append("- C.3 step-0 July ENDPOINT controls vs now (directly comparable, same endpoint):")
    deleted_control = []
    for s, jul in JULY_ENDPOINT.items():
        now = now_phot.get(s)
        diff = None if now is None else now - jul
        sign = "" if diff is None else ("+" if diff > 0 else "")
        L.append(f"    - {s}: July {jul} -> now {now} (diff {sign}{diff})")
        if diff is not None and diff < 0:
            deleted_control.append((s, jul, now, diff))
    if deleted_control:
        verdict = ("Rows APPEAR DELETED. On the same endpoint, "
                   + "; ".join(f"{s} {j}->{n2} ({d})" for s, j, n2, d in deleted_control)
                   + ": a same-endpoint count that FALLS can only mean rows were removed, so the "
                   "photometry endpoint is NOT append-only. (Prior 'photstats total' explanation "
                   "withdrawn: July's 131 was the endpoint count; photstats reported 151.) The C.1 "
                   "num_det_global exceedances are the detections-vs-all-points artifact, not additions")
        verdict += (f"; but the num_obs_global cross-check flags {len(c1_obs)} sources whose all-points "
                    "count now exceeds July's global observations — genuine additions or stale photstats."
                    if c1_obs else ".")
    else:
        verdict = "No same-endpoint control decreased; C.3 gives no evidence of deletion."
    L += ["- C.4 VERDICT: " + verdict]

    # -- Section D: spectra -------------------------------------------------------------
    spec_total = sum(v for v in present["spectra"])
    L += ["", "## D. SPECTRA",
          f"- total spectra across all {n} sources: {spec_total}"
          + ("  -> spectrum is NOT a usable fact type in this population." if spec_total == 0
             else "  (spectrum remains residual).")]

    # -- Section E: activity vs t0 (table only; no thresholds, no candidate list) --------
    no_t0 = [s for s in sids if index.get(s, {}).get("t0_source") not in (None, "skyportal_t0")]
    def has(s, c): return (counts[s][c] or 0) >= 1
    L += ["", f"## E. ACTIVITY vs t0 — sources WITHOUT a real t0 ({len(no_t0)} of {n}); table only"]
    L.append(f"- E.1 with >=1: followup {sum(1 for s in no_t0 if has(s,'followup_requests'))}; "
             f"comment {sum(1 for s in no_t0 if has(s,'comments'))}; "
             f"photometry {sum(1 for s in no_t0 if has(s,'photometry'))}")
    L.append("- E.2 count distribution within this group:")
    for c in COLLECTIONS:
        vals = [counts[s][c] for s in no_t0 if counts[s][c] is not None]
        L.append(f"    - {c}: {dist_row(vals)}")
    L.append("- E.3 cross-tab has_followup x has_photometry x has_comments (source counts):")
    ct = Counter((has(s, "followup_requests"), has(s, "photometry"), has(s, "comments")) for s in no_t0)
    for (fu, ph, co), k in sorted(ct.items(), key=lambda x: -x[1]):
        L.append(f"    - fu={int(fu)} phot={int(ph)} comm={int(co)}: {k}")
    L.append("- E.4 by name_pattern_class (fu>=1 / phot>=1 / comm>=1 / n):")
    by_npc = defaultdict(list)
    for s in no_t0:
        by_npc[index.get(s, {}).get("name_pattern_class", "?")].append(s)
    for npc, group in sorted(by_npc.items(), key=lambda x: -len(x[1])):
        L.append(f"    - {npc}: fu {sum(1 for s in group if has(s,'followup_requests'))} / "
                 f"phot {sum(1 for s in group if has(s,'photometry'))} / "
                 f"comm {sum(1 for s in group if has(s,'comments'))} / n {len(group)}")

    # -- Section F: errors and disappearances -------------------------------------------
    L += ["", "## F. ERRORS AND DISAPPEARANCES"]
    if errors:
        for st, ss in sorted(errors.items()):
            uniq = sorted(set(ss))
            L.append(f"- HTTP {st}: {len(uniq)} sources -> {', '.join(uniq[:15])}"
                     + (" ..." if len(uniq) > 15 else ""))
    else:
        L.append("- no non-200 responses recorded.")
    gone = sorted(set(errors.get("404", [])))
    L.append(f"- sources in the July listing that no longer resolve (404): {len(gone)}"
             + (": " + ", ".join(gone[:15]) if gone else ""))
    L.append(f"- index ids that produced no directory (all four collections failed): {len(missing)}"
             + (": " + ", ".join(missing[:15]) if missing else "")
             + ". Note: 'AT2023toh' is stored in the index with a trailing tab, so scripts/11 "
             "requested a malformed path and got HTTP 400; the id as stored does not resolve.")

    # -- Section G: volume --------------------------------------------------------------
    bytes_by = {c: col_bytes(c) for c in COLLECTIONS}
    total_bytes = sum(bytes_by.values())
    avg_lat = sum(lats) / len(lats) if lats else 0.0
    dominant = max(bytes_by, key=bytes_by.get)
    L += ["", "## G. VOLUME",
          f"- bytes per collection: { {c: f'{b/1048576:.1f}MB' for c, b in bytes_by.items()} }",
          f"- total on disk: {total_bytes/1048576:.1f} MB",
          f"- wall clock: {manifest.get('total_wall_clock_seconds')} s; HTTP calls (run): "
          f"{manifest.get('total_http_calls_this_run')}; avg latency {avg_lat:.2f}s",
          f"- {dominant} dominates the footprint because each record embeds the full "
          "requester/allocation/obj objects."]

    # -- Section 7 / 8 ------------------------------------------------------------------
    L += ["", "## 7. JUDGMENT CALLS",
          "- Audit regenerated by a separate read-only script (scripts/12) to avoid modifying the "
          "validated fetcher scripts/11 (HARD RULE 1).",
          "- 'without a real t0' = t0_source != 'skyportal_t0' (the id-timestamp and created_at tiers).",
          "- Distributions are over sources with a written file; missing files (fetch errors) are in F.",
          "", "## 8. DISCREPANCIES vs prompt/prior expectations",
          f"- Preflight on-disk size 2.00 MB (5 sources) vs prompt's ~2.65 MB (that figure is wire "
          "bytes, not stored bytes).",
          "- CORRECTION carried in: the prior audit's 'July 131 was a photstats total' explanation "
          "is WITHDRAWN. July's 131 was the endpoint count (photstats reported 151); the real "
          "sequence is 77 -> 131 -> 125. See C.4 for the deletion evidence."]

    os.makedirs(os.path.dirname(AUDIT_MD), exist_ok=True)
    open(AUDIT_MD, "w").write("\n".join(L) + "\n")

    return dict(n=n, present=present, zero_all=zero_all, errors=errors, spec_total=spec_total,
                verdict=verdict, manifest=manifest, total_bytes=total_bytes, deleted=deleted_control)


def _collect_personal(obj, found):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in PERSONAL_FIELDS and v not in (None, "", [], {}):
                found.add(k)
            _collect_personal(v, found)
    elif isinstance(obj, list):
        for v in obj:
            _collect_personal(v, found)


def main():
    r = build()
    print("=" * 60 + "\nDL01 FULL-RUN AUDIT SUMMARY\n" + "=" * 60)
    print(f"source directories: {r['n']}")
    for c in COLLECTIONS:
        print(f"  {c:18s}: {len(r['present'][c])} files, total {sum(r['present'][c])} records")
    print(f"sources empty across ALL four collections: {len(r['zero_all'])}")
    print(f"spectra total across corpus: {r['spec_total']}")
    print(f"C.4 deletion controls (July->now, same endpoint): "
          + (", ".join(f"{s} {j}->{n2}({d})" for s, j, n2, d in r["deleted"]) or "none decreased"))
    m = r["manifest"]
    print(f"wall clock: {m.get('total_wall_clock_seconds')} s | HTTP calls: "
          f"{m.get('total_http_calls_this_run')} | total on disk: {r['total_bytes']/1048576:.1f} MB")
    print(f"errors by status: { {k: len(v) for k, v in r['errors'].items()} or 'none'}")
    print(f"audit written: {os.path.relpath(AUDIT_MD, ROOT)}")


if __name__ == "__main__":
    main()
