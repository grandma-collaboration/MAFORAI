# Source Selection for Bundles

## Goal

This document explains the current event-selection workflow end to end:

1. build the enriched `gcn_grandma` base list from `grandma_base`;
2. assign a priority and ordering score to every GCN-derived event;
3. fetch per-source bundles for the current `high` subset;
4. export compact shared sample files so the team can review the same events.

The important point is that the current workflow is intentionally simple and
explainable. It does not try to infer a final scientific truth. It creates a
reproducible shortlist for deeper manual evaluation.

## Entry points

| File | Role |
|---|---|
| `scripts/03_build_gcn_grandma.py` | Build the enriched GCN-derived GRANDMA base list |
| `scripts/04_build_selected_sources.py` | Build the prioritized `selected_sources_for_bundles.json` file |
| `scripts/05_fetch_source_bundles.py` | Download per-source endpoint bundles for one priority bucket |
| `scripts/06_export_high_priority_samples.py` | Export compact shared sample files for the current `high` set |
| `src/skyportal_corpus/extraction/source_selection.py` | Base-list construction, priority rules, scoring, and JSON builders |
| `src/skyportal_corpus/extraction/source_bundles.py` | Bundle download logic |
| `src/skyportal_corpus/extraction/high_priority_samples.py` | Shared sample export logic |

## Current source model

For this workflow, the following IDs are treated as coming from the same GCN
ingestion path:

- `GCN-*`
- `GRB-*`
- `GW-*`
- `EP-*`

They stay in the same pool on purpose.

Why:

- the source naming logic in SkyPortal uses these prefixes as variants of the
  same GCN-ingested channel;
- filtering only `GCN-*` would drop scientifically relevant events already
  identified upstream as `GRB-*`, `GW-*`, or `EP-*`;
- the first selection goal is to keep the whole GCN-derived universe visible
  inside `GRANDMA`, then prioritize inside that universe.

## Why the workflow starts from `grandma_base`

The current selection does not start from a follow-up-specific inventory or a
minimum-detections-only inventory. It starts from the enriched `grandma_base`
inventory because that keeps the universe broad while still adding compact
signals useful for ranking.

What `grandma_base` guarantees:

- the event belongs to `GRANDMA` via `group_ids=3`;
- `comment_exists` is available through `includeCommentExists=true`;
- `num_det_global` is available through `includeDetectionStats=true`;
- host information is preserved when available through `includeHosts=true`.

Why this matters:

- we do not want to lose GCN-derived events just because they do not already
  pass a narrow photometry or follow-up filter;
- but we do want enough enrichment to rank events with simple, explicit rules.

## Step 1. Build `gcn_grandma`

Input:

- one enriched `grandma_base` inventory run

Typical command:

```bash
python scripts/03_build_gcn_grandma.py \
  --inventory-dir data/raw/skyportal/inventory/source_inventory_grandma_base_<timestamp>
```

Default output:

```text
data/samples/gcn_grandma_<run_label>.json
```

### Fields kept in `gcn_grandma`

Each event is reduced to a compact record:

- `id`
- `gcn_source_type`
- `redshift`
- `comment_exists`
- `num_det_global`
- `has_host`
- `groups`
- `classification_labels`
- `source_summary`

### Why these fields were kept

| Field | Why it matters now |
|---|---|
| `id` | Preserves the original SkyPortal identifier and the GCN-derived subtype prefix |
| `gcn_source_type` | Makes it explicit whether the source currently looks like `gcn`, `grb`, `gw`, or `ep` |
| `redshift` | Strongest compact science signal currently available in the inventory |
| `comment_exists` | Cheap proxy for whether humans interacted with the event |
| `num_det_global` | Cheap proxy for how much photometric support the event has |
| `has_host` | Preserved for reference because host proximity matters scientifically, even though it is weak in the current data |
| `groups` | Keeps `GRANDMA` and `GRANDMA/Kilonova-Catcher` context visible |
| `classification_labels` | Preserves the most compact operational and scientific labels already attached in SkyPortal |
| `source_summary` | Keeps a human-readable summary for later manual inspection |

### Current observed `gcn_grandma` run

The current base list was built from `source_inventory_grandma_base_20260604_112909`.

| Metric | Value |
|---|---:|
| Total input sources | 382 |
| GCN-derived sources | 156 |
| `GCN-*` | 35 |
| `GRB-*` | 95 |
| `GW-*` | 0 |
| `EP-*` | 26 |

## Step 2. Build `selected_sources_for_bundles.json`

Input:

- `data/samples/gcn_grandma_grandma_base.json`

Typical command:

```bash
python scripts/04_build_selected_sources.py
```

Explicit path variant:

```bash
python scripts/04_build_selected_sources.py \
  --gcn-grandma-path data/samples/gcn_grandma_grandma_base.json
```

Default output:

```text
data/samples/selected_sources_for_bundles.json
```

### Selection philosophy

The current selection is not a final scientific classifier. It is a first-pass
ranking.

The design goals were:

- keep the rules small enough to inspect by eye;
- rely only on fields already present in the enriched inventory;
- prefer explicit astrophysical or operational signals over opaque heuristics;
- keep all GCN-derived events, then sort them by interest.

### Why these criteria were chosen

#### `redshift`

This is the strongest compact science signal currently available at inventory
level.

Why it matters:

- it immediately tells us whether the event has a known distance estimate;
- extreme cases are especially interesting for the current workflow:
  - `z < 1` keeps nearby events visible;
  - `z > 4` keeps very distant events visible;
- it is present as a clean numeric field, so it can be used reproducibly.

#### `comment_exists`

This is a weak but useful proxy for human attention.

Why it matters:

- comments usually indicate that someone discussed the event, added context, or
  tracked follow-up decisions;
- it is much cheaper and cleaner at inventory level than parsing all comments
  immediately;
- it helps separate events with some collaborative activity from events that are
  still mostly untouched.

Important limitation:

- `comment_exists=true` only means comments exist; it does not tell us how many
  there are or whether they are scientifically informative.

#### `num_det_global`

This is the compact photometric richness proxy used in the first pass.

Why it matters:

- it gives a quick signal about whether the event has usable light-curve
  support;
- `>= 2` marks events with at least a minimal multi-point detection history;
- `>= 5` marks events with richer coverage and therefore higher value for a
  first corpus review.

Important limitation:

- this is still a compact summary from `photstats`, not a substitute for
  inspecting the full photometry bundle.

#### `classification_labels`

These labels are kept because they add compact scientific or operational
context without requiring full downstream parsing.

Labels currently used directly:

- `GRB`
- `GO GRANDMA`
- `GO GRANDMA (HIGH PRIORITY)`
- `STOP GRANDMA`

Why they matter:

- `GRB` is a positive scientific signal for the current GCN-first corpus;
- `GO GRANDMA` and especially `GO GRANDMA (HIGH PRIORITY)` are useful
  operational support signals;
- `STOP GRANDMA` is kept as explicit context, even though it does not currently
  reduce the score.

Why we do not use “has any classification” as a criterion:

- many classifications are operational rather than scientific;
- using classification presence alone would be too coarse.

#### `has_host`

This field is intentionally kept in the JSON, but it is not a strong ranking
signal yet.

Why:

- host proximity is scientifically interesting;
- but in the current inventory and high-priority bundle run, structured host
  information is sparse and unreliable for ranking;
- we prefer to keep it visible without pretending that it is already usable.

### Priority rules

Each event gets one priority bucket.

| Priority | Rule |
|---|---|
| `high` | `GO GRANDMA (HIGH PRIORITY)`, or extreme redshift (`z < 1` or `z > 4`), or `redshift + comments + num_det_global >= 5` |
| `medium` | known redshift, or `comments + num_det_global >= 5`, or supportive `GRB` / `GO GRANDMA` classification |
| `low` | remaining GCN-derived events |

These are the exact rule families currently encoded in `source_selection.py`.

### How `selection_score` is built

`selection_score` is not the main science label. It is a deterministic ordering
score used inside the priority buckets.

Current contributions:

| Signal | Score contribution | Why |
|---|---:|---|
| redshift known | `+2` | having a measured redshift is already useful |
| extreme redshift (`z < 1` or `z > 4`) | `+4` | these are the most distinctive science cases in the current first pass |
| comments exist | `+1` | some human interaction exists |
| `num_det_global >= 2` | `+1` | minimal light-curve support |
| `num_det_global >= 5` | `+2` | stronger light-curve support |
| `GRB` classification | `+2` | direct support for the GCN-first GRB-oriented corpus |
| `GO GRANDMA` classification | `+1` | useful operational support signal |
| `GO GRANDMA (HIGH PRIORITY)` | `+3` | strongest operational priority label currently used |

Important interpretation:

- `priority` is the primary bucket;
- `selection_score` only orders events inside or across similar cases;
- the score is intentionally additive and small so that it stays easy to audit.

### How events are ordered in the final file

The final list is sorted deterministically by:

1. priority bucket: `high`, then `medium`, then `low`
2. descending `selection_score`
3. descending `num_det_global`
4. ascending `id`

This keeps the JSON reproducible and avoids manual reordering.

### What `selection_reasons` means

Each event also keeps an explicit `selection_reasons` list.

That list is not a second scoring system. It is a trace of which compact
signals were actually present for that event, such as:

- `has_redshift`
- `redshift_extreme`
- `has_comments`
- `num_det_global_gte_2`
- `num_det_global_gte_5`
- `classified_as_grb`
- `go_grandma`
- `go_grandma_high_priority`
- `stop_grandma`

This is important because the workflow must stay explainable during manual
review.

### Fields kept in the final JSON

Each selected record contains:

- `id`
- `gcn_source_type`
- `priority`
- `selection_score`
- `selection_reasons`
- `selection_context`
- `source_summary`

The file stays compact on purpose. It is meant to guide manual review and the
next bundle-download step, not to duplicate all source fields.

### Current observed final run

Based on `gcn_grandma_grandma_base.json`, the current output contains:

| Metric | Value |
|---|---:|
| Total selected-source records | 156 |
| `high` priority | 31 |
| `medium` priority | 38 |
| `low` priority | 87 |

## Step 3. Fetch source bundles for the current `high` subset

Input:

- `data/samples/selected_sources_for_bundles.json`

Typical command:

```bash
python scripts/05_fetch_source_bundles.py
```

Current default behavior:

- reads `data/samples/selected_sources_for_bundles.json`
- keeps only `priority=high`
- writes one run under:

```text
data/raw/skyportal/source_bundles/source_bundle_run_<timestamp>/
```

Endpoints currently fetched per source:

- `GET /api/sources/{source_id}`
- `GET /api/sources/{source_id}/photometry?format=flux`
- `GET /api/sources/{source_id}/photometry?format=mag`
- `GET /api/sources/{source_id}/phot_stat`
- `GET /api/sources/{source_id}/comments`
- `GET /api/sources/{source_id}/classifications`
- `GET /api/sources/{source_id}/spectra`
- `GET /api/sources/{source_id}/annotations`
- `GET /api/associated_gcns/{source_id}`
- `GET /api/sources/{source_id}/position`
- `GET /api/sources/{source_id}/offsets`
- `GET /api/sources/{source_id}/color_mag`

Current observed bundle run:

| Metric | Value |
|---|---:|
| Selected sources available | 156 |
| `high` sources kept | 31 |
| Sources completed without endpoint failures | 29 |
| Sources with partial failures | 2 |
| Endpoint requests attempted | 372 |
| Endpoint requests succeeded | 367 |
| Endpoint requests failed | 5 |

Known partial-failure cases in the current run:

- `GRB250319B`
- `GRB-250129_044509`

## Step 4. Export shared high-priority sample files

Input:

- one `source_bundle_run_<timestamp>` directory
- `data/samples/selected_sources_for_bundles.json`

Typical command:

```bash
python scripts/06_export_high_priority_samples.py \
  --bundle-run-dir data/raw/skyportal/source_bundles/source_bundle_run_<timestamp>
```

Outputs:

```text
data/samples/selected_sources_high.json
data/samples/selected_sources_high_bundle_summary.csv
```

Why this export exists:

- the raw bundle run is the reproducible evidence;
- the shared sample files give the team a small common working set;
- the CSV makes it easy to compare availability across the current `high`
  events without opening every bundle directory manually.

What the shared files contain:

- `selected_sources_high.json`
  - the 31 current `high` events with their selection context
- `selected_sources_high_bundle_summary.csv`
  - per-source availability summary for photometry, comments,
    classifications, spectra, follow-up requests, associated GCNs,
    annotations, `phot_stat`, `summary`, and `tns_info`

## Current operational interpretation

At this stage, the workflow should be read as:

1. start broad inside `GRANDMA`;
2. keep the whole GCN-derived universe visible;
3. rank events with compact, explicit signals;
4. fetch only the current `high` subset for deeper inspection;
5. share a compact common sample for collaborative review.

That is the current purpose of the score and of the bundle pipeline. It is a
first-pass triage system, not the final corpus definition.
