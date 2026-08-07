# SkyPortal Corpus

## What this is

A structured corpus of astronomical transient records from SkyPortal, the
observation platform of the GRANDMA collaboration, covering 800 sources
observed between November 2022 and July 2026. It is built for
time-truncated reconstruction: recovering what was known about a source at
a past instant, rather than what is known about it now.

## Contents

| table | rows | columns | sources covered (of 800) | description |
|---|---:|---:|---:|---|
| sources | 800 | 91 | 800 | One row per distinct astronomical source: identity, coordinates, redshift, classification, host-galaxy enrichment, and TNS cross-match fields. |
| comments | 2950 | 11 | 351 | Free-text annotations attached to sources by collaboration members. |
| photometry | 7968 | 43 | 240 | Individual brightness measurements (magnitude, filter, instrument, timing). |
| spectra | 1 | 42 | 1 | Spectroscopic observations. A single record in this corpus. |
| followup_requests | 2339 | 147 | 393 | Telescope follow-up observation requests and their submission status. |
| source_field_history | 1357 | 10 | 266 | One row per recorded change to a source's `redshift` or `summary`. See Field history, below. |

`created_at` span per table (UTC):

| table | earliest | latest |
|---|---|---|
| sources | 2022-11-10 02:28:36 | 2026-07-18 11:17:50 |
| comments | 2022-11-10 06:21:24 | 2026-07-21 07:31:02 |
| photometry | 2022-11-10 15:36:48 | 2026-07-24 12:20:01 |
| spectra | 2026-02-18 08:18:01 | 2026-02-18 08:18:01 |
| followup_requests | 2023-05-20 15:32:23 | 2026-07-18 13:27:33 |

`set_at_utc` span for `source_field_history`: 2023-05-21 19:41:45 to 2026-07-19 09:50:32.

## Provenance

The corpus is built from two fixed raw captures:

```
listing  data/raw/skyportal/inventory/source_inventory_<profile>_20260720_093939/
         four profiles: grandma_base, grb, ep, gcn
detail   data/raw/skyportal/source_detail_20260724/
```

JSON access paths used to reach the records:

| capture | record type | access path |
|---|---|---|
| listing | sources | `data.sources` |
| detail | comments | `payload.data` |
| detail | photometry | `payload.data` |
| detail | spectra | `payload.data.spectra` |
| detail | followup_requests | `payload.data.followup_requests` |

## How it was produced

Two scripts, run in order:

| script | does | writes |
|---|---|---|
| `scripts/skyportal/01_flatten.py` | Reads the raw captures and flattens nested JSON into tables. Shape only — no cleaning, no merging, no decisions. | `data/interim/skyportal_corpus/` |
| `scripts/skyportal/02_normalise.py` | Reads the interim tables and applies the sixteen normalisation decisions. | `data/corpus_skyportal/` (this corpus) |

Both scripts are deterministic: given the same raw captures, they produce
byte-identical output on every run. This was verified by regenerating both
stages into an isolated temporary directory and comparing every output
file's SHA-256 hash against the committed one, across all eleven files (five
interim, six corpus) — see `notebooks/skyportal/D_reproducibility.ipynb`.

## Decisions applied

Sixteen decisions were applied during normalisation. The ones below change
what a user of this corpus sees directly — row counts, dropped columns,
added columns, nulled values, or an entirely new table. The full set, with
the measurements that motivated each one, is recorded in the final cell of
`notebooks/skyportal/A_eda.ipynb`.

| decision | effect | measured |
|---|---|---|
| 1 | `sources`: one row per source; `source_profile` renamed to `source_profiles` (list) | 982 -> 800 rows |
| 3 | `followup_requests`: kept the row where `source_dir == obj_id` | 2359 -> 2339 rows |
| 6 | dropped columns with no content in any row | sources 25, comments 1, photometry 2, spectra 10, followup_requests 20 |
| 7 | dropped `comments.resourceType` | 1 column |
| 9 | added `status_normalised` | followup_requests, 8 values |
| 11 | `limiting_mag == -1.0` (sentinel) set to null | 10 rows |
| 12 | out-of-range `mjd` set to null; `mjd_out_of_range` flag added | 5 rows |
| 13 | zero-coordinate flag columns added | 4 columns (2 in sources, 2 in followup_requests) |
| 16 | `redshift_history` and `summary_history` expanded into `source_field_history` | 1357 rows from 266 sources |

## Added columns

| column | table | what it records |
|---|---|---|
| `source_profiles` | sources | The list of listing profiles (of grandma_base, grb, ep, gcn) under which this source was returned. |
| `status_normalised` | followup_requests | The request's status, resolved to one of 7 lifecycle prefixes or `processing_result`, from the free-form `status` text. |
| `mjd_out_of_range` | photometry | True where the row's `mjd` fell outside the plausible range [55000, 61250] and was set to null. |
| `ra_is_zero` | sources | True where `ra` is exactly 0.0. |
| `dec_is_zero` | sources | True where `dec` is exactly 0.0. |
| `obj.ra_is_zero` | followup_requests | True where `obj.ra` is exactly 0.0. |
| `obj.dec_is_zero` | followup_requests | True where `obj.dec` is exactly 0.0. |

## Field history

`source_field_history` holds one row per recorded change to `redshift` or
`summary` on a source, expanded from the two serialised history columns
SkyPortal returns alongside each source listing.

| column | type | description |
|---|---|---|
| `source_id` | string | The parent source identifier. |
| `field` | string | `redshift` or `summary`. |
| `entry_index` | integer | The entry's original position in its source array, 0-based. |
| `value` | string | The value as recorded; null for a deletion event. |
| `value_is_null` | boolean | True for a deletion event (the field was cleared, not just left unset). |
| `set_at_utc` | datetime (UTC) | The instant the change was recorded. |
| `set_by_user_id` | integer | The numeric id of the user who made the change. |
| `uncertainty` | string | Redshift entries only; null on summary rows. |
| `origin` | string | Redshift entries only; null on summary rows. |
| `is_bot` | boolean | Summary entries only; null on redshift rows. |

| field | rows | sources | deletion events |
|---|---:|---:|---:|
| redshift | 83 | 60 | 3 |
| summary | 1274 | 256 | 25 |

266 distinct sources carry a history in at least one of the two fields.
Entries with a null value are retained as deletion events rather than
dropped. `entry_index` records the original array position because 141 of
the 256 summary histories are not stored in chronological order — for those
sources, array position cannot be read as recency.

## Time and truncation

`created_at` is the truncation anchor for the five event and source tables.
It is present on 100% of rows in all five and is typed as
`datetime64[ns, UTC]`. MJD columns (`mjd`, `t0`, `obj.t0`,
`observed_at_mjd`) remain numeric; they record observation time, not
knowledge time, and are not suitable for truncation.

Scope limit: event records — comments, photometry, spectra and follow-up
requests — are immutable once created, and cutting them by `created_at` is
exact. Rows in `sources` are records that get updated, so a cut determines
which sources existed at instant T while their values are those held at
capture time. For `redshift` and `summary` this limit does not apply:
`source_field_history` gives the value in force at any instant as the
latest entry with `set_at_utc` at or before it. No other field of
`sources` carries a change history.

## Known limitations

- `spectra` holds a single row.
- Coverage of the 800 sources is uneven across the detail tables:

  | table | sources covered | of 800 |
  |---|---:|---:|
  | comments | 351 | 43.9% |
  | photometry | 240 | 30.0% |
  | spectra | 1 | 0.1% |
  | followup_requests | 393 | 49.1% |
  | source_field_history | 266 | 33.2% |

- One source, `AT2023toh`, holds no comments, photometry or spectra: those
  three requests failed with HTTP 400 because its identifier carries a
  trailing tab character, which breaks the endpoints that place the id in
  the URL path. The follow-up request collection succeeded for the same
  source because it passes the id as a query parameter, not a path
  segment. Its absence from those three tables is a capture failure, not
  an empty source.
- The source listing was captured on 2026-07-20 and the source-detail
  collections on 2026-07-24; between the two, the account's group access
  widened, so the detail capture may include records for sources the
  listing capture could not have returned at the time. Counts taken
  across the two captures are therefore not strictly comparable.
- Columns with content coverage below 1% exist because the API returns its
  full model regardless of what a given source populated:

  | table | columns below 1% coverage |
  |---|---:|
  | sources | 21 |
  | comments | 0 |
  | photometry | 13 |
  | spectra | 0 |
  | followup_requests | 19 |
  | source_field_history | 0 |

- Identity follows SkyPortal: related entries — a source and an
  instrument-suffixed counterpart capturing the same physical event — are
  kept as separate source rows, not merged. For example, `EP240626A` and
  `EP240626A-FXT`, `GRB241002` and `GRB241002C`, `GRB241209` and
  `GRB241209A` each exist as two distinct sources.
- 369 of the 800 sources (46.1%) have `modified` later than `created_at`,
  meaning their listing-capture snapshot reflects at least one edit after
  the source was first created in SkyPortal. This is what bounds the time
  and truncation limit above: for these sources, the column values held at
  the `created_at` instant are not necessarily what is stored in this
  corpus. (`source_field_history` narrows this for `redshift` and
  `summary` specifically, but not for any other field.)
- Free-text fields in `comments` and `followup_requests` contain personal
  names written by collaboration members (see Personal data, below).

## Personal data

Follow-up request records carry the requester's name: 911 of 2339
`followup_requests` rows (39.0%) carry a non-empty requester first or last
name. Comment text (`comments.text`) and summary text
(`sources.summary`, `source_field_history.value` where `field == 'summary'`)
are retained as written and may contain names. `source_field_history`
identifies the author of each change by numeric `set_by_user_id` only — it
carries no name field. The corpus is therefore internal to the GRANDMA
collaboration and is not for distribution.

## Terms of use

Internal to the GRANDMA collaboration and to IJCLab. Not for
redistribution. Derived from SkyPortal data owned by the collaboration.

## Regenerating this corpus

Raw captures must be present at the paths listed under Provenance. Then,
from the repository root:

```
/home/meneses/project_astronomical/MAFORAI/.venv/bin/python \
  /home/meneses/project_astronomical/MAFORAI/scripts/skyportal/01_flatten.py

/home/meneses/project_astronomical/MAFORAI/.venv/bin/python \
  /home/meneses/project_astronomical/MAFORAI/scripts/skyportal/02_normalise.py
```

The first writes `data/interim/skyportal_corpus/`; the second reads it and
writes this corpus, `data/corpus_skyportal/`, including
`source_field_history.parquet`.
