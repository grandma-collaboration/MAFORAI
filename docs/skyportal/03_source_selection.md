# GCN-Derived Base

## Goal

This document describes the current workflow used to prepare the SkyPortal-side
event universe before any GCN matching.

Today this stage prepares the two canonical SkyPortal-side artifacts that feed
the downstream GCN workflow:

1. build `gcn_grandma.json` from the inventory union;
2. build `skyportal_event_baseline` from `gcn_grandma.json`.


## Entry points

| File | Role |
|---|---|
| `scripts/03_build_gcn_grandma.py` | Build the compact GCN-derived base list from saved inventories |
| `scripts/04_build_skyportal_event_baseline.py` | Build the compact SkyPortal baseline from `gcn_grandma.json` |
| `src/skyportal_corpus/extraction/source_selection.py` | Build and merge the compact `gcn_grandma` base records |
| `src/skyportal_corpus/extraction/skyportal_event_baseline.py` | Extract `summary`/`tags` context into the SkyPortal-side baseline |

## Current source model

For this workflow, the following source-ID families are treated as coming from
the same GCN ingestion path:

- `GCN-*`
- `GRB-*`
- `GW-*`
- `EP-*`

The inclusion rule checks both:

- the main `id`
- every string stored in `aliases`

Only the prefix matters. If an `id` or an alias starts with `GCN`, `GRB`,
`GW`, or `EP`, that source enters the same pool.

Why:

- SkyPortal uses these prefixes as variants of the same GCN-ingested channel;
- we want the whole GCN-derived universe visible across the dedicated `gcn`,
  `grb`, and `ep` inventories;
- `grandma_base` is kept in the union because it can expose alias-based matches
  that would be missed if the main `id` uses another naming scheme.

## Build `gcn_grandma`

Input:

- one saved `gcn` inventory run
- one saved `grb` inventory run
- one saved `ep` inventory run
- one saved `grandma_base` inventory run

Typical command:

```bash
python scripts/03_build_gcn_grandma.py \
  --inventory-dir data/raw/skyportal/inventory/source_inventory_gcn_<timestamp> \
  --inventory-dir data/raw/skyportal/inventory/source_inventory_grb_<timestamp> \
  --inventory-dir data/raw/skyportal/inventory/source_inventory_ep_<timestamp> \
  --inventory-dir data/raw/skyportal/inventory/source_inventory_grandma_base_<timestamp>
```

Default output:

```text
data/interim/skyportal/gcn_grandma.json
```

## Fields kept in `gcn_grandma`

Each event is reduced to a compact record:

- `id`
- `gcn_source_type`
- `aliases`
- `tags`
- `redshift`
- `trigger_time`
- `comment_exists`
- `spectrum_exists`
- `num_det_global`
- `has_host`
- `groups`
- `classification_labels`
- `source_summary`

## Why these fields were kept

| Field | Why it matters now |
|---|---|
| `id` | Preserves the original SkyPortal identifier and the GCN-derived subtype prefix |
| `gcn_source_type` | Makes it explicit whether the source currently looks like `gcn`, `grb`, `gw`, or `ep` |
| `aliases` | Keeps the alias strings that can also trigger inclusion when the main `id` does not start with `GCN`, `GRB`, `GW`, or `EP` |
| `tags` | Keeps only the raw SkyPortal tag names so the later GCN comparison can normalize trusted astronomer categorizations without carrying full tag objects |
| `redshift` | Useful compact science field already exposed in the inventory |
| `trigger_time` | Keeps the inventory-level `t0` value when SkyPortal already exposes it, without needing deeper endpoint downloads |
| `comment_exists` | Cheap proxy for whether the event already has discussion in SkyPortal |
| `spectrum_exists` | Cheap proxy for whether SkyPortal already knows about at least one spectrum |
| `num_det_global` | Cheap proxy for photometric richness at inventory level |
| `has_host` | Keeps the existing host flag visible for later comparison |
| `groups` | Keeps `GRANDMA` and `GRANDMA/Kilonova-Catcher` context visible |
| `classification_labels` | Preserves compact labels already attached in SkyPortal |
| `source_summary` | Keeps a human-readable summary for quick inspection |


## Input logic

The build does two things before writing `gcn_grandma.json`:

1. read all rows from the four input inventories;
2. keep only the rows whose `id` or one alias starts with `GCN`, `GRB`, `GW`,
   or `EP`, then merge duplicates by `id`.

When duplicates are merged:

- aliases are unioned;
- raw tag names are unioned without duplicates;
- boolean flags are OR-combined;
- `num_det_global` keeps the maximum value;
- `redshift` and `trigger_time` are filled from the first non-null value seen;
- compact summary text is kept when available.

## Build `skyportal_event_baseline`

Input:

- `data/interim/skyportal/gcn_grandma.json`

Typical command:

```bash
python scripts/04_build_skyportal_event_baseline.py \
  --selected-sources data/interim/skyportal/gcn_grandma.json \
  --output-dir data/interim/skyportal
```

Outputs:

- `data/interim/skyportal/skyportal_event_baseline.csv`
- `data/interim/skyportal/skyportal_event_baseline.parquet`

This second artifact keeps the compact native fields from `gcn_grandma.json`
and adds:

- claims re-extracted from `source_summary`;
- normalized semantic categories derived from raw `tags`;
- union baseline fields used later to decide whether GCN truly adds new
  information.

## Handoff to the GCN pipeline

For the current workflow, the canonical handoff to the later GCN stages is:

- `data/interim/skyportal/gcn_grandma.json`
- `data/interim/skyportal/skyportal_event_baseline.parquet`

`gcn_grandma.json` is the default event universe to use for:

- GCN Circular matching

`skyportal_event_baseline.parquet` is the default SkyPortal-side artifact to
use for:

- GCN enrichment comparison against the compact SkyPortal inventory view
- the final GCN review table

The downstream operational details for those GCN stages now live in:

- [docs/gcn/README.md](../gcn/README.md)
