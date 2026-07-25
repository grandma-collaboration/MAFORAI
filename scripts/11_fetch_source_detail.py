#!/usr/bin/env python
"""scripts/11_fetch_source_detail.py

Fetch the four SkyPortal per-source collections the listing does NOT carry: comments,
photometry, spectra, follow-up requests. Raw JSON only, GET only. Resumable: each success
is written to its own file at once (temp then rename); a re-run skips existing files
(--force re-fetches); a progress log records one line per call. Paging: numPerPage=500 and
loop pageNumber until totalMatches, so no collection is silently truncated.

REUSES src/skyportal_corpus/extraction/skyportal_client.py for all HTTP — SkyPortalClient
.from_config (token from .env) / .get_json (retry-with-backoff) / JsonRequestMetadata.
Adds only >=0.5 s pacing, file writing, resume/paging logic and audit.

Modes: default = PREFLIGHT (five fixed sources + completeness probes, then STOP); --all =
FULL RUN (remaining 800, separate invocation); --force = re-fetch existing files.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlencode

from skyportal_corpus.core import default_skyportal_config_path, load_skyportal_config
from skyportal_corpus.extraction import SkyPortalClient

ROOT = "/home/meneses/project_astronomical/MAFORAI"
SCRIPT = "scripts/11_fetch_source_detail.py"
SCRIPT_VERSION = "1.0"
MIN_INTERVAL_S = 0.5  # HARD RULE 8: minimum spacing between requests
SOURCE_CSV = os.path.join(ROOT, "notebooks/evidence/01_source_index.csv")
RAW_ROOT = os.path.join(ROOT, "data/raw/skyportal")
AUDIT_MD = os.path.join(ROOT, "data/interim/audit/DL01_source_detail.md")

# collection -> (path template, query-param name for the source id or None => id in path)
COLLECTIONS = {
    "comments": ("/sources/{id}/comments", None),
    "photometry": ("/sources/{id}/photometry", None),
    "spectra": ("/sources/{id}/spectra", None),
    "followup_requests": ("/followup_request", "sourceID"),
}
PREFLIGHT_SOURCES = ["2025aji", "2026owq", "GRB241030", "EP-260623_025405", "GCN-251013_173943"]
LARGE_PAGE = 500  # numPerPage: makes the common case a single call while staying safe
LIST_KEYS = ("followup_requests", "spectra", "comments", "photometry", "requests")
# Sources probed for pagination completeness (max-count for each collection; 2026cex is the
# only spectrum-bearing source in the corpus, per notebooks/evidence/01_source_index.csv).
PROBE_TARGETS = {"comments": "GCN-251013_173943", "photometry": "GCN-251013_173943",
                 "spectra": "2026cex", "followup_requests": "GCN-251013_173943"}
# Known control values (P2) and the July 2026 photometry count for the access-change check.
P2_EXPECT = {("2026owq", "comments"): 92, ("2026owq", "followup_requests"): 9,
             ("GRB241030", "comments"): 57, ("GRB241030", "followup_requests"): 8}
JULY_PHOTOMETRY = {"GRB241030": 131}
PERSONAL_FIELDS = ["first_name", "last_name", "expiration_date", "contact_email",
                   "contact_phone", "oauth_uid", "username", "affiliations"]
KNOWN_INCONSISTENCY = (
    "The source listing was captured on 2026-07-20; the account has since been granted "
    "access to further groups, so this detail capture may see photometry (and other "
    "records) the listing capture could not. Counts here are NOT directly comparable to "
    "the 2026-07-20 listing."
)


# ---- helpers --------------------------------------------------------------------------
def utcnow():
    return datetime.now(timezone.utc).isoformat()


def load_source_ids():
    import csv
    with open(SOURCE_CSV, newline="") as fh:
        ids = [r["source_id"] for r in csv.DictReader(fh)]
    return sorted(set(ids))  # deterministic order


def resolve_out_dir(override):
    if override:
        return override if os.path.isabs(override) else os.path.join(ROOT, override)
    existing = sorted(glob.glob(os.path.join(RAW_ROOT, "source_detail_*")))
    if existing:  # resume the most recent capture dir
        return existing[-1]
    return os.path.join(RAW_ROOT, f"source_detail_{datetime.now(timezone.utc):%Y%m%d}")


def atomic_write(dest, obj):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(dest), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(obj, fh, ensure_ascii=False)
        os.replace(tmp, dest)  # atomic rename — never leaves a partial file
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def append_progress(log_path, sid, collection, status, nbytes, elapsed):
    line = "\t".join([utcnow(), sid, collection, str(status), str(nbytes), f"{elapsed:.3f}"])
    with open(log_path, "a") as fh:
        fh.write(line + "\n")


def extract_records(collection, payload):
    """The record list inside a raw payload: data itself (bare list) or a nested list key."""
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in LIST_KEYS:
            if isinstance(data.get(key), list):
                return data[key]
    return None


def set_records(payload, records):
    """Put a merged record list back into the payload structure (for multi-page merges)."""
    data = payload.get("data")
    if isinstance(data, list):
        payload["data"] = records
    elif isinstance(data, dict):
        for key in LIST_KEYS:
            if isinstance(data.get(key), list):
                data[key] = records
                return


def total_matches(payload):
    """The totalMatches / equivalent count a payload advertises, or None if it carries none."""
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, dict):
        for key in ("totalMatches", "total_matches", "totalCount"):
            if isinstance(data.get(key), int):
                return data[key]
    return None


def count_records(collection, payload):
    r = extract_records(collection, payload)
    return len(r) if isinstance(r, list) else None


def pagination_info(payload):
    """Report whether a payload carries pagination hints (P1)."""
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, list):
        return {"shape": "bare_list", "len": len(data), "paginated": False}
    if isinstance(data, dict):
        page_keys = [k for k in ("totalMatches", "numPerPage", "pageNumber", "total_matches")
                     if k in data]
        return {"shape": "dict", "keys": sorted(data.keys()), "paginated": bool(page_keys),
                "totalMatches": data.get("totalMatches")}
    return {"shape": type(data).__name__, "paginated": False}


def progress_latencies(log_path):
    """Real per-call elapsed seconds from progress.log (resume-safe source for P4)."""
    lats = []
    if os.path.exists(log_path):
        for line in open(log_path):
            p = line.rstrip("\n").split("\t")
            if len(p) >= 6 and p[3] == "200":
                try:
                    lats.append(float(p[5]))
                except ValueError:
                    pass
    return lats


def load_wire_bytes(log_path):
    """Map (source, collection) -> last recorded response bytes from progress.log, so a
    resumed run reports the wire response size rather than the compact stored-file size."""
    m = {}
    if os.path.exists(log_path):
        for line in open(log_path):
            p = line.rstrip("\n").split("\t")
            if len(p) >= 5:
                try:
                    m[(p[1], p[2])] = int(p[4])
                except ValueError:
                    pass
    return m


def collect_personal(obj, found):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in PERSONAL_FIELDS and v not in (None, "", [], {}):
                found.add(k)
            collect_personal(v, found)
    elif isinstance(obj, list):
        for v in obj:
            collect_personal(v, found)


# ---- fetch ----------------------------------------------------------------------------
def paced_get(client, path, params, state):
    wait = MIN_INTERVAL_S - (time.monotonic() - state["last_call"])
    if wait > 0:
        time.sleep(wait)
    payload, meta = client.get_json(path, params=params)
    state["last_call"] = time.monotonic()
    state["calls"] += 1
    return payload, meta


def fetch_one(client, sid, collection, out_dir, log_path, state, force, wire_bytes=None):
    """Fetch one (source, collection). Returns a result dict; writes a file only on 200."""
    path_tmpl, qparam = COLLECTIONS[collection]
    dest = os.path.join(out_dir, sid, f"{collection}.json")
    if os.path.exists(dest) and not force:  # resume: recompute report fields from disk
        payload = json.load(open(dest)).get("payload")
        nbytes = (wire_bytes or {}).get((sid, collection), os.path.getsize(dest))
        return {"sid": sid, "collection": collection, "status": "skip", "http": 200,
                "bytes": nbytes, "elapsed": 0.0,
                "count": count_records(collection, payload),
                "pagination": pagination_info(payload)}

    path = path_tmpl if qparam else path_tmpl.format(id=sid)
    base = {qparam: sid} if qparam else {}
    params = dict(base, numPerPage=LARGE_PAGE, pageNumber=1)
    payload, meta = paced_get(client, path, params, state)
    http = meta.http_status_code
    nbytes = meta.response_size_chars or 0
    elapsed = meta.elapsed_seconds or 0.0
    append_progress(log_path, sid, collection, http, nbytes, elapsed)

    res = {"sid": sid, "collection": collection, "http": http, "bytes": nbytes,
           "elapsed": elapsed, "count": None, "error": meta.error, "pages": 1}
    if http == 429:  # HARD RULE 8: abort the whole run on rate limiting
        res["status"] = "rate_limited"
        return res
    if not (http == 200 and payload is not None):  # non-200: log, no file, resume re-attempts
        res["status"] = "error"
        return res

    total = total_matches(payload)
    records = extract_records(collection, payload)
    pages = 1
    while total is not None and isinstance(records, list) and len(records) < total and pages < 100:
        pages += 1
        params["pageNumber"] = pages
        p2, m2 = paced_get(client, path, params, state)
        append_progress(log_path, sid, collection, m2.http_status_code,
                        m2.response_size_chars or 0, m2.elapsed_seconds or 0.0)
        more = extract_records(collection, p2) if m2.http_status_code == 200 else None
        if not more:
            break
        records.extend(more)
        payload = p2  # keep last page's wrapper fields (numPerPage/totalMatches)
    if pages > 1 and isinstance(records, list):
        set_records(payload, records)  # store the complete, concatenated record list
    endpoint = meta.url + ("?" + urlencode(meta.params) if meta.params else "")
    wrapper = {"captured_at": utcnow(), "endpoint": endpoint, "http_status": 200,
               "source_id": sid, "collection": collection, "pages_fetched": pages,
               "totalMatches": total, "payload": payload}
    atomic_write(dest, wrapper)
    res.update(status="ok", pages=pages, pagination=pagination_info(payload),
               count=len(records) if isinstance(records, list) else count_records(collection, payload))
    return res


def probe_paging(client, sid, collection, state):
    """Diagnostic (not persisted): compare a full page to a numPerPage=1 page to learn whether
    an endpoint honours paging, and whether it advertises totalMatches. Verifies completeness."""
    path_tmpl, qparam = COLLECTIONS[collection]
    path = path_tmpl if qparam else path_tmpl.format(id=sid)
    base = {qparam: sid} if qparam else {}
    full, _ = paced_get(client, path, dict(base, numPerPage=LARGE_PAGE, pageNumber=1), state)
    one, mone = paced_get(client, path, dict(base, numPerPage=1, pageNumber=1), state)
    fc, oc = count_records(collection, full), count_records(collection, one)
    total = total_matches(full)
    honors = oc == 1 and (fc or 0) > 1  # returned exactly 1 when asked for 1 => paginates
    if honors and total is not None:
        verdict = "paginates + advertises totalMatches -> looped to completeness (SAFE)"
    elif honors:
        verdict = f"paginates, NO totalMatches -> numPerPage={LARGE_PAGE} covers <= {LARGE_PAGE}; " \
                  f"a source with >{LARGE_PAGE} would truncate undetectably"
    elif (fc or 0) <= 1:
        verdict = "only <=1 record corpus-wide (cannot stress-test paging); no totalMatches; " \
                  "the single record returned complete"
    else:
        verdict = "ignores paging (numPerPage=1 still returned the full list) -> SAFE"
    return {"collection": collection, "sid": sid, "full": fc, "one": oc,
            "totalMatches": total, "honors_paging": honors, "verdict": verdict,
            "http": mone.http_status_code}


def fetch_groups(client, state):
    """GET /groups once; return (source_key, [{id,name}], raw_payload) for visibility_scope."""
    payload, meta = paced_get(client, "/groups", None, state)
    data = payload.get("data") if isinstance(payload, dict) else {}
    data = data if isinstance(data, dict) else {}
    for key in ("user_accessible_groups", "user_groups", "all_groups"):
        lst = data.get(key)
        if isinstance(lst, list) and lst:
            return key, [{"id": g.get("id"), "name": g.get("name")} for g in lst], payload
    return None, [], payload


# ---- manifest / audit -----------------------------------------------------------------
def scan_state(out_dir, log_path):
    per_collection = {c: {"files": 0, "records": 0, "counts": [], "multipage": 0} for c in COLLECTIONS}
    sources = set()
    for sid in os.listdir(out_dir):
        d = os.path.join(out_dir, sid)
        if not os.path.isdir(d):
            continue
        for c in COLLECTIONS:
            f = os.path.join(d, f"{c}.json")
            if os.path.exists(f):
                sources.add(sid)
                per_collection[c]["files"] += 1
                wrapper = json.load(open(f))
                cnt = count_records(c, wrapper.get("payload"))
                if wrapper.get("pages_fetched", 1) > 1:
                    per_collection[c]["multipage"] += 1
                if cnt is not None:
                    per_collection[c]["records"] += cnt
                    per_collection[c]["counts"].append(cnt)
    errors = Counter()
    if os.path.exists(log_path):
        for line in open(log_path):
            p = line.rstrip("\n").split("\t")
            if len(p) >= 4 and p[3] not in ("200", "None"):
                errors[p[3]] += 1
    return sources, per_collection, dict(errors)


def write_manifest(out_dir, base_url, group_key, groups, mode, wall_s, calls, log_path):
    sources, per_collection, errors = scan_state(out_dir, log_path)
    manifest = {
        "script": SCRIPT, "script_version": SCRIPT_VERSION, "capture_date": f"{datetime.now(timezone.utc):%Y%m%d}",
        "base_url": base_url, "mode": mode,
        "collections": {c: t[0] for c, t in COLLECTIONS.items()},
        "visibility_scope": {"groups_source_key": group_key, "groups": groups},
        "known_inconsistency": KNOWN_INCONSISTENCY,
        "counts": {
            "sources_with_any_file": len(sources),
            "files_written": sum(v["files"] for v in per_collection.values()),
            "per_collection": {c: {"files": v["files"], "records": v["records"],
                                    "sources_needing_multiple_pages": v["multipage"]}
                               for c, v in per_collection.items()},
            "errors_by_status": errors,
        },
        "total_wall_clock_seconds": round(wall_s, 1),
        "total_http_calls_this_run": calls,
    }
    atomic_write(os.path.join(out_dir, "manifest.json"), manifest)
    return manifest, per_collection


def dist(counts):
    if not counts:
        return "n/a"
    s = sorted(counts)
    p = lambda q: s[min(len(s) - 1, int(q * len(s)))]
    return f"min {s[0]} / median {p(0.5)} / p90 {p(0.9)} / max {s[-1]}"


def _count(results, sid, col):
    return next((r["count"] for r in results if r["sid"] == sid and r["collection"] == col), None)


def preflight_findings(results, out_dir, log_path):
    """Compute the P1..P4 answer lines, shared by stdout and the audit report."""
    p3 = personal_scan(out_dir)
    lines = []
    for c in COLLECTIONS:
        pg = next((r["pagination"] for r in results if r["collection"] == c and "pagination" in r), None)
        lines.append(f"P1 {c}: paginated={pg.get('paginated') if pg else '?'} {pg}")
    for (sid, col), want in P2_EXPECT.items():
        got = _count(results, sid, col)
        lines.append(f"P2 {sid}/{col}: got {got}, expect {want} -> {'MATCH' if got == want else 'DIFF'}")
    for sid, jul in JULY_PHOTOMETRY.items():
        got = _count(results, sid, "photometry")
        lines.append(f"P2 {sid}/photometry: now {got} vs July {jul} "
                     f"({'higher' if (got or 0) > jul else 'LOWER, not higher'})")
    lines.append(f"P3 follow-up personal fields: {p3[2]} in {p3[1]}/{p3[0]} records")
    lat = progress_latencies(log_path)
    avg = sum(lat) / len(lat) if lat else 0.0
    est = 800 * len(COLLECTIONS) * (avg + MIN_INTERVAL_S)
    lines.append(f"P4 full run: {800 * len(COLLECTIONS)} calls, avg latency {avg:.2f}s, "
                 f"~{est / 60:.0f} min (~{est / 3600:.1f} h)")
    return lines, p3


def write_audit(out_dir, base_url, results, group_key, groups, findings, p3, manifest,
                per_collection, probes):
    L = ["# DL01 — SkyPortal per-source detail (audit)", "",
         f"Preflight capture into `{os.path.relpath(out_dir, ROOT)}` via {SCRIPT} v{SCRIPT_VERSION}.",
         f"Base URL {base_url}. GET only; >=0.5 s pacing; HTTP via reused SkyPortalClient.", "",
         "## 1. PREFLIGHT", "", "| source | collection | http | count | bytes |",
         "|---|---|---|---|---|"]
    for r in results:
        L.append(f"| {r['sid']} | {r['collection']} | {r['http']} | "
                 f"{'' if r['count'] is None else r['count']} | {r['bytes']} |")
    L.append("")
    L += [f"- {ln}" for ln in findings]
    total, with_p, fields = p3
    L += ["", "### 1b. PAGINATION COMPLETENESS VERIFICATION (numPerPage=1 probe per collection)"]
    for pr in probes:
        L.append(f"- {pr['collection']} (probe {pr['sid']}): full={pr['full']}, "
                 f"numPerPage=1 -> {pr['one']}, totalMatches={pr['totalMatches']}, "
                 f"honors_paging={pr['honors_paging']} -> {pr['verdict']}")
    L += ["", "## 2. COVERAGE (preflight; full distribution after --all)"]
    for c, v in per_collection.items():
        nonempty = sum(1 for x in v["counts"] if x and x > 0)
        L.append(f"- {c}: {v['files']} files, {nonempty} non-empty, {v['multipage']} needed >1 page; "
                 f"records {dist(v['counts'])}")
    cnt = manifest["counts"]
    L += ["", "## 3. VOLUME",
          f"- files written: {cnt['files_written']}; per-collection records: "
          f"{ {c: v['records'] for c, v in cnt['per_collection'].items()} }",
          f"- wall clock: {manifest['total_wall_clock_seconds']} s; HTTP calls this run: "
          f"{manifest['total_http_calls_this_run']}", "", "## 4. ERRORS",
          f"- non-200 by status: {cnt['errors_by_status'] or 'none'}"]
    for r in results:
        if r["status"] == "error":
            L.append(f"  - {r['sid']}/{r['collection']}: HTTP {r['http']} ({r['error']})")
    L += ["", "## 5. VISIBILITY",
          f"- token groups ({group_key}): " + ", ".join(f"{g['name']}(id {g['id']})" for g in groups),
          f"- KNOWN INCONSISTENCY: {KNOWN_INCONSISTENCY}"]
    for sid, jul in JULY_PHOTOMETRY.items():
        got = next((r["count"] for r in results if r["sid"] == sid and r["collection"] == "photometry"), None)
        L.append(f"- {sid} photometry: July {jul} -> now {got}")
    L += ["", "## 6. PERSONAL DATA",
          f"- follow-up request records expose {fields} in {with_p}/{total} records. Flagged; "
          "nothing stripped at this stage (that is a later decision).", "", "## 7. JUDGMENT CALLS"]
    L += [f"- {x}" for x in JUDGMENT_CALLS]
    L += ["", "## 8. DISCREPANCIES vs prompt expectations"]
    diffs = []
    p2_mismatch = False
    for (sid, col), want in P2_EXPECT.items():
        got = next((r["count"] for r in results if r["sid"] == sid and r["collection"] == col), None)
        if got != want:
            diffs.append(f"{sid}/{col}: got {got}, prompt states {want}")
            p2_mismatch = True
    if not p2_mismatch:
        diffs.append("P2 exact control counts (2026owq 92/9, GRB241030 57/8) all match.")
    for sid, jul in JULY_PHOTOMETRY.items():
        got = next((r["count"] for r in results if r["sid"] == sid and r["collection"] == "photometry"), None)
        if got is not None and got <= jul:
            diffs.append(
                f"{sid} photometry now {got} <= July {jul}: prompt expected HIGHER (access change), "
                "got LOWER. Access change is real at group level (token gained 'GRB 122522A science' "
                "id 175, absent from the July listing) but not corroborated here; likely July 131 was "
                "a photstats/detection total (incl. non-permitted rows) vs this endpoint's "
                "permitted-only rows. Full run needed to judge across more known-July sources.")
    fu = [r["pagination"] for r in results
          if r["collection"] == "followup_requests" and "pagination" in r]
    fu_totals = [p.get("totalMatches") for p in fu if p.get("totalMatches") is not None]
    if any(p.get("paginated") for p in fu):
        diffs.append(
            "followup_requests PAGINATES (numPerPage default 100, totalMatches present). RESOLVED: "
            f"the fetch now sends numPerPage={LARGE_PAGE} and loops pageNumber until totalMatches is "
            f"reached (preflight max totalMatches {max(fu_totals) if fu_totals else '?'}, so one page). "
            "See §1b for the per-collection completeness probe covering the other three.")
    L += [f"- {d}" for d in diffs]
    L.append("")
    os.makedirs(os.path.dirname(AUDIT_MD), exist_ok=True)
    open(AUDIT_MD, "w").write("\n".join(L) + "\n")


JUDGMENT_CALLS = [
    "Only HTTP 200 responses are written as files (incl. empty collections as empty-list "
    "payloads). Non-200s are logged but not filed, so a resume re-attempts them — 'absence "
    "means not fetched'.",
    "Output dir resolves to the most recent source_detail_* if present (so --all resumes the "
    "preflight dir), else source_detail_<todayUTC>; override with --out-dir.",
    "0.5 s pacing wraps the reused client; the client's own retry-with-backoff is untouched. "
    "Record counts read payload['data'] (list) or a nested list key, verbatim, no reshaping.",
    "manifest counts and resumed-run wire bytes/latencies are recomputed from the output dir + "
    "progress.log, so they stay correct across resumed runs.",
]


# ---- run modes ------------------------------------------------------------------------
def run_preflight(client, base_url, out_dir, log_path, state, args):
    t0 = time.monotonic()
    print(f"PREFLIGHT (5 sources) -> {os.path.relpath(out_dir, ROOT)}")
    group_key, groups, _ = fetch_groups(client, state)
    wire_bytes = load_wire_bytes(log_path)
    results = []
    aborted = False
    for sid in PREFLIGHT_SOURCES:
        for collection in COLLECTIONS:
            r = fetch_one(client, sid, collection, out_dir, log_path, state, args.force, wire_bytes)
            results.append(r)
            if r["status"] == "rate_limited":
                print("HTTP 429 — aborting per HARD RULE 8.")
                aborted = True
                break
        if aborted:
            break

    print(f"{'source':17s} {'collection':18s} {'http':>4s} {'count':>6s} {'bytes':>8s}")
    for r in results:
        print(f"{r['sid']:17s} {r['collection']:18s} {str(r['http']):>4s} "
              f"{('' if r['count'] is None else str(r['count'])):>6s} {r['bytes']:>8d}")

    findings, p3 = preflight_findings(results, out_dir, log_path)
    for line in findings:
        print(line)

    probes = [] if aborted else [probe_paging(client, sid, coll, state)
                                  for coll, sid in PROBE_TARGETS.items()]
    for pr in probes:
        print(f"VERIFY {pr['collection']}: full={pr['full']} one={pr['one']} "
              f"totalMatches={pr['totalMatches']} -> {pr['verdict']}")

    wall = time.monotonic() - t0
    manifest, per_collection = write_manifest(out_dir, base_url, group_key, groups,
                                              "preflight", wall, state["calls"], log_path)
    write_audit(out_dir, base_url, results, group_key, groups, findings, p3, manifest,
                per_collection, probes)
    print(f"\nSTOP: preflight only. Review, then re-run with --all. Audit: "
          f"{os.path.relpath(AUDIT_MD, ROOT)}")


def personal_scan(out_dir):
    total, with_p, fields = 0, 0, Counter()
    for sid in PREFLIGHT_SOURCES:
        f = os.path.join(out_dir, sid, "followup_requests.json")
        if not os.path.exists(f):
            continue
        payload = json.load(open(f)).get("payload")
        data = payload.get("data") if isinstance(payload, dict) else None
        records = data if isinstance(data, list) else (
            data.get("followup_requests") if isinstance(data, dict) else None) or []
        for rec in records:
            total += 1
            found = set()
            collect_personal(rec, found)
            if found:
                with_p += 1
            for k in found:
                fields[k] += 1
    return total, with_p, dict(fields)


def run_full(client, base_url, out_dir, log_path, state, args):
    t0 = time.monotonic()
    ids = load_source_ids()
    if args.limit:
        ids = ids[: args.limit]
    print(f"FULL RUN: {len(ids)} sources -> {os.path.relpath(out_dir, ROOT)}")
    group_key, groups, _ = fetch_groups(client, state)
    wire_bytes = load_wire_bytes(log_path)
    done = 0
    for i, sid in enumerate(ids, 1):
        for collection in COLLECTIONS:
            r = fetch_one(client, sid, collection, out_dir, log_path, state, args.force, wire_bytes)
            if r["status"] == "rate_limited":
                print(f"HTTP 429 at {sid}/{collection} — aborting per HARD RULE 8.")
                write_manifest(out_dir, base_url, group_key, groups, "full-aborted-429",
                               time.monotonic() - t0, state["calls"], log_path)
                return
        done += 1
        if done % 50 == 0:
            print(f"  {done}/{len(ids)} sources, {state['calls']} calls, "
                  f"{time.monotonic() - t0:.0f}s")
    manifest, per_collection = write_manifest(out_dir, base_url, group_key, groups, "full",
                                              time.monotonic() - t0, state["calls"], log_path)
    # Regenerate the audit so COVERAGE/VOLUME and "sources needing >1 page" reflect all 800.
    pf_results = [fetch_one(client, sid, c, out_dir, log_path, state, False, load_wire_bytes(log_path))
                  for sid in PREFLIGHT_SOURCES for c in COLLECTIONS]
    findings, p3 = preflight_findings(pf_results, out_dir, log_path)
    probes = [probe_paging(client, sid, coll, state) for coll, sid in PROBE_TARGETS.items()]
    write_audit(out_dir, base_url, pf_results, group_key, groups, findings, p3, manifest,
                per_collection, probes)
    print(f"Done: {done} sources, {state['calls']} calls, {time.monotonic() - t0:.0f}s. "
          f"Multipage: { {c: v['multipage'] for c, v in per_collection.items()} }")


def parse_args():
    ap = argparse.ArgumentParser(description="Fetch SkyPortal per-source detail (resumable).")
    ap.add_argument("--all", action="store_true", help="Full run over all 800 sources.")
    ap.add_argument("--force", action="store_true", help="Re-fetch files that already exist.")
    ap.add_argument("--out-dir", default=None, help="Capture dir override (else resume latest).")
    ap.add_argument("--limit", type=int, default=None, help="Limit sources (full run, testing).")
    ap.add_argument("--config", default=str(default_skyportal_config_path()))
    return ap.parse_args()


def main():
    args = parse_args()
    cfg = load_skyportal_config(args.config)
    base_url = cfg.skyportal.base_url
    try:
        client = SkyPortalClient.from_config(cfg)
    except Exception as exc:  # never surface token contents
        raise SystemExit(f"Cannot create authenticated client: {type(exc).__name__}")
    out_dir = resolve_out_dir(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)
    log_path = os.path.join(out_dir, "progress.log")
    state = {"last_call": 0.0, "calls": 0}
    if args.all:
        run_full(client, base_url, out_dir, log_path, state, args)
    else:
        run_preflight(client, base_url, out_dir, log_path, state, args)


if __name__ == "__main__":
    main()
