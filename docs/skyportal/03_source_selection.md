# GCN-Derived Base

## Goal

This document describes the current workflow used to prepare the SkyPortal-side
event universe before any GCN matching.

Today this stage does one thing only:

1. build `gcn_grandma.json` from the inventory union.


## Entry points

| File | Role |
|---|---|
| `scripts/03_build_gcn_grandma.py` | Build the compact GCN-derived base list from saved inventories |
| `src/skyportal_corpus/extraction/source_selection.py` | Build and merge the compact `gcn_grandma` base records |

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
data/samples/gcn_grandma.json
```

## Fields kept in `gcn_grandma`

Each event is reduced to a compact record:

- `id`
- `gcn_source_type`
- `aliases`
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
- boolean flags are OR-combined;
- `num_det_global` keeps the maximum value;
- `redshift` and `trigger_time` are filled from the first non-null value seen;
- compact summary text is kept when available.

## Handoff to the GCN pipeline

For the current workflow, the canonical handoff to the later GCN stages is:

- `data/samples/gcn_grandma.json`

That file is now the default event universe to use for:

- GCN Circular matching
- GCN body claim extraction
- GCN enrichment comparison against the compact SkyPortal inventory view

The downstream operational details for those GCN stages now live in:

- [docs/gcn/README.md](../gcn/README.md)
