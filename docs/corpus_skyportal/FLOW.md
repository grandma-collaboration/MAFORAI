# SkyPortal Pipeline

This traces the SkyPortal data from the API to the corpus. For what the
corpus contains, see `data/corpus_skyportal/DATASET_CARD.md`; for the
evidence behind each decision, see the notebooks referenced throughout.

## Overview

```
SkyPortal API
     |  02_fetch_source_inventory.py, 11_fetch_source_detail.py
     v
data/raw/skyportal/                     paginated JSON, frozen
     |  01_flatten.py
     v
data/interim/skyportal_corpus/          five flat tables, no decisions
     |  02_normalise.py
     v
data/corpus_skyportal/                  six tables, sixteen decisions
```

## Stage 1 — Acquisition

### Listing

`scripts/02_fetch_source_inventory.py` is a thin CLI wrapper; the logic
lives in `src/skyportal_corpus/extraction/source_inventory.py`. It calls
`GET /sources`, quoted from the code:

```python
payload, request_meta = client.get_json(
    "/sources",
    params=params,
    ...
)
```

Page size (`numPerPage`) defaults to 100 (`configs/extraction/skyportal.yaml`,
`inventory.defaults.num_per_page`). The loop stops on the first of:
an empty page (`stopped_reason = "empty_sources_page"`), the API-reported
`totalMatches` being reached (`"api_total_matches_reached"`), or the
configured page limit (`"max_pages_reached"`, only `recent_500` sets this;
the four profiles used here run to completion). Each request goes through
`client.get_json`, which retries up to 3 times with a backoff of
`2.0 * attempt` seconds; between pages the script sleeps
`sleep_seconds` (0.3s by default). The output directory is named
`source_inventory_<run_label>_<timestamp>`, timestamp at second precision
(`datetime.now().strftime("%Y%m%d_%H%M%S")`). The token is read from the
environment variable `SKYPORTAL_API_TOKEN`.

The four profiles, query parameters quoted verbatim from
`configs/extraction/skyportal.yaml` (each profile's own `query_params`
merged onto the shared `enriched_recent_desc` template:
`includePhotometryExists=true`, `includeSpectrumExists=true`,
`includeCommentExists=true`, `includeDetectionStats=true`,
`sortBy=saved_at`, `sortOrder=desc`):

| profile | query parameters (profile-specific, on top of the shared template) | records captured |
|---|---|---:|
| `grandma_base` | `group_ids=3`, `includeHosts=true` | 407 |
| `gcn` | `sourceID=GCN` | 155 |
| `ep` | `sourceID=EP` | 219 |
| `grb` | `sourceID=GRB` | 201 |

`grandma_base` filters on group membership; `gcn`, `ep` and `grb` filter
on a substring of the source identifier. These are different filtering
axes, so a source can satisfy both at once — overlap between profiles is
structural, not a capture error.

The four capture runs actually read by `01_flatten.py` (the fixed
`_20260720_*` directories), measured from their logs:

| directory | pages | records | duration | stop reason |
|---|---:|---:|---:|---|
| `source_inventory_grandma_base_20260720_093939` | 5 | 407 | 2.50s | `api_total_matches_reached` |
| `source_inventory_gcn_20260720_093955` | 2 | 155 | 0.79s | `api_total_matches_reached` |
| `source_inventory_ep_20260720_094001` | 3 | 219 | 1.24s | `api_total_matches_reached` |
| `source_inventory_grb_20260720_094006` | 3 | 201 | 1.29s | `api_total_matches_reached` |

### Detail

`scripts/11_fetch_source_detail.py` fetches four per-source collections the
listing does not carry, using the same shared client. Endpoints, quoted
from the code:

```python
COLLECTIONS = {
    "comments": ("/sources/{id}/comments", None),
    "photometry": ("/sources/{id}/photometry", None),
    "spectra": ("/sources/{id}/spectra", None),
    "followup_requests": ("/followup_request", "sourceID"),
}
```

(`None` means the source id is a URL path segment; `"sourceID"` means it
is a query parameter instead.) Page size is 500 (`numPerPage=500`,
looped by `pageNumber` until the collected count reaches `totalMatches`).
Pacing is enforced with a minimum 0.5-second interval between requests
(`MIN_INTERVAL_S = 0.5`). On HTTP 429 the whole run aborts immediately
rather than retrying:

```python
if http == 429:  # HARD RULE 8: abort the whole run on rate limiting
    res["status"] = "rate_limited"
    return res
```

The output directory resolves to the most recent `data/raw/skyportal/source_detail_*`
if one exists (so a `--all` run resumes a prior preflight), otherwise
`source_detail_<todayUTC:%Y%m%d>` (day precision).

Measured from `data/raw/skyportal/source_detail_20260724/progress.log`
(3240 lines) and its `manifest.json`:

| quantity | value |
|---|---|
| duration | 09:22:19 to 14:51:25 UTC, 5.49 hours |
| HTTP 200 | 3237 |
| HTTP 400 | 3 |
| files written | 3197 |
| comments | 799 files, 2950 records |
| photometry | 799 files, 7968 records |
| spectra | 799 files, 1 record |
| followup_requests | 800 files, 2359 records |

The three HTTP 400 failures are all for a single source, whose raw
identifier carries a trailing tab character. The tab survives into the
URL path for the three endpoints that place the id in the path
(`comments`, `photometry`, `spectra`), and each of those three calls
fails with HTTP 400. The fourth collection, `followup_requests`, passes
the id as the `sourceID` query parameter instead of a path segment, and
that call succeeds (HTTP 200).

The detail manifest carries its own advisory on cross-capture
comparability, quoted verbatim:

> "The source listing was captured on 2026-07-20; the account has since
> been granted access to further groups, so this detail capture may see
> photometry (and other records) the listing capture could not. Counts
> here are NOT directly comparable to the 2026-07-20 listing."

## Stage 2 — Flattening

`scripts/skyportal/01_flatten.py` reads the raw captures and flattens
nested JSON into five tables. It changes shape only: no cleaning, no
merging of duplicate sources, no decisions — so the interim tables remain
a faithful comparison point for what the corpus later changes.

JSON access paths used to reach the records:

| file | access path | what it yields |
|---|---|---|
| listing page | `data.sources` | source listing records |
| `comments.json` | `payload.data` | comment records |
| `photometry.json` | `payload.data` | photometry records |
| `spectra.json` | `payload.data.spectra` | spectrum records |
| `followup_requests.json` | `payload.data.followup_requests` | follow-up request records |

The five interim tables:

| table | rows | columns |
|---|---:|---:|
| sources | 982 | 114 |
| comments | 2950 | 13 |
| photometry | 7968 | 44 |
| spectra | 1 | 52 |
| followup_requests | 2359 | 164 |

Provenance columns added to every table: `source_profile` (sources only —
which of the four listing profiles returned this row) or `source_dir`
(the four detail tables — the capture subdirectory the record came from);
`source_file` (the specific JSON page or file read); `capture_run` (the
fixed capture date the row belongs to, `20260720` or `20260724`).

## Stage 3 — Normalisation

`scripts/skyportal/02_normalise.py` applies the sixteen decisions recorded
in the final cell of `notebooks/skyportal/A_eda.ipynb`, one function per
decision, each returning the rows it affected. The full set of decisions
is not restated here.

What changes between interim and corpus, measured:

| table | interim rows | corpus rows | columns dropped | columns added |
|---|---:|---:|---:|---|
| sources | 982 | 800 | 26 | `source_profiles`, `ra_is_zero`, `dec_is_zero` |
| comments | 2950 | 2950 | 2 | — |
| photometry | 7968 | 7968 | 2 | `mjd_out_of_range` |
| spectra | 1 | 1 | 10 | — |
| followup_requests | 2359 | 2339 | 20 | `status_normalised`, `obj.ra_is_zero`, `obj.dec_is_zero` |

The sixth table, `source_field_history` (1357 rows), is expanded from two
serialised columns of `sources` (`redshift_history`, `summary_history`),
not transformed from a flat interim table — it has no interim
counterpart.

## Stage 4 — The corpus

| table | rows | columns | sources covered |
|---|---:|---:|---:|
| sources | 800 | 91 | 800 |
| comments | 2950 | 11 | 351 |
| photometry | 7968 | 43 | 240 |
| spectra | 1 | 42 | 1 |
| followup_requests | 2339 | 147 | 393 |
| source_field_history | 1357 | 10 | 266 |

`created_at` span across the five event and source tables:
2022-11-10 02:28:36 to 2026-07-24 12:20:01 UTC.
`set_at_utc` span in `source_field_history`:
2023-05-21 19:41:45 to 2026-07-19 09:50:32 UTC.

`created_at` is the truncation anchor for the five event and source
tables, present on 100% of rows in each and typed as explicit UTC.
`source_field_history` extends that anchor to two fields of `sources`
(`redshift`, `summary`) that would otherwise only reflect their value at
capture time: `set_at_utc` records when each change happened, so the
value in force at any instant is recoverable as the latest entry at or
before it.

## Evidence

| question | where it is answered |
|---|---|
| What do the flattened tables contain? | `notebooks/skyportal/A_eda.ipynb` |
| Which decisions were taken, and why? | `notebooks/skyportal/B_decisions.ipynb` |
| What did each decision change? | `notebooks/skyportal/C_normalisation.ipynb` |
| Is the corpus reproducible? | `notebooks/skyportal/D_reproducibility.ipynb` |
| What does the corpus contain? | `docs/corpus_skyportal/DATASET_CARD.md` |

## Running the pipeline

Acquisition — needs network access and `SKYPORTAL_API_TOKEN` set:

```
/home/meneses/project_astronomical/MAFORAI/.venv/bin/python \
  /home/meneses/project_astronomical/MAFORAI/scripts/02_fetch_source_inventory.py --profile grandma_base
/home/meneses/project_astronomical/MAFORAI/.venv/bin/python \
  /home/meneses/project_astronomical/MAFORAI/scripts/02_fetch_source_inventory.py --profile gcn
/home/meneses/project_astronomical/MAFORAI/.venv/bin/python \
  /home/meneses/project_astronomical/MAFORAI/scripts/02_fetch_source_inventory.py --profile ep
/home/meneses/project_astronomical/MAFORAI/.venv/bin/python \
  /home/meneses/project_astronomical/MAFORAI/scripts/02_fetch_source_inventory.py --profile grb

/home/meneses/project_astronomical/MAFORAI/.venv/bin/python \
  /home/meneses/project_astronomical/MAFORAI/scripts/11_fetch_source_detail.py --all
```

(`02_fetch_source_inventory.py` also accepts `--config`, `--run-label`,
`--base-url`, `--output-dir`, `--num-per-page`, `--start-page`,
`--max-pages`, `--timeout`, `--max-retries`, `--sleep` and repeatable
`--query-param key=value` overrides. `11_fetch_source_detail.py` also
accepts `--force`, `--out-dir`, `--limit` and `--config`; without `--all`
it runs a five-source preflight only.)

Build — reads only what acquisition already wrote, no network, no
credentials:

```
/home/meneses/project_astronomical/MAFORAI/.venv/bin/python \
  /home/meneses/project_astronomical/MAFORAI/scripts/skyportal/01_flatten.py
/home/meneses/project_astronomical/MAFORAI/.venv/bin/python \
  /home/meneses/project_astronomical/MAFORAI/scripts/skyportal/02_normalise.py
```
