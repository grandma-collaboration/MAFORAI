# Source Selection for Bundles

## Goal

This step turns the enriched `GRANDMA` inventory into a compact list of
GCN-derived events to inspect in more detail before downloading per-source
bundles.

The current workflow uses two stages:

1. build the enriched `gcn_grandma` base list;
2. build the final prioritized `selected_sources_for_bundles.json`.

## Current source model

For this workflow, the following IDs are treated as coming from the same GCN
ingestion path:

- `GCN-*`
- `GRB-*`
- `GW-*`
- `EP-*`

They stay in the same selection pool. We do not split them into separate
families at this stage.

## Entry points

| File | Role |
|---|---|
| `scripts/03_build_gcn_grandma.py` | Thin CLI wrapper for the GCN-derived GRANDMA base list |
| `scripts/04_build_selected_sources.py` | Thin CLI wrapper for the final selected source list |
| `src/skyportal_corpus/extraction/source_selection.py` | Selection logic and JSON builders |

## Step 1. Build `gcn_grandma`

Input:

- enriched `grandma_base` inventory

Typical command:

```bash
python scripts/03_build_gcn_grandma.py \
  --inventory-dir data/raw/skyportal/inventory/source_inventory_grandma_base_<timestamp>
```

Default output:

```text
data/samples/gcn_grandma_<run_label>.json
```

Fields kept per event:

- `id`
- `gcn_source_type`
- `redshift`
- `comment_exists`
- `num_det_global`
- `has_host`
- `groups`
- `classification_labels`
- `source_summary`

Current observed run:

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

You can also run it explicitly:

```bash
python scripts/04_build_selected_sources.py \
  --gcn-grandma-path data/samples/gcn_grandma_grandma_base.json
```

Default output:

```text
data/samples/selected_sources_for_bundles.json
```

## Priority rules

The final file assigns one priority bucket to every GCN-derived event.

| Priority | Rule |
|---|---|
| `high` | extreme redshift, or redshift + comments + `num_det_global >= 5`, or `GO GRANDMA (HIGH PRIORITY)` |
| `medium` | redshift known, or comments + `num_det_global >= 5`, or supportive `GRB` / `GO GRANDMA` classification |
| `low` | remaining GCN-derived events |

Signals currently used:

- `redshift`
- `comment_exists`
- `num_det_global`
- `classification_labels`

`has_host` is kept in the JSON for reference, but it is not a strong ranking
signal yet.

## Fields kept in the final JSON

Each selected record contains:

- `id`
- `gcn_source_type`
- `priority`
- `selection_score`
- `selection_reasons`
- `selection_context`
- `source_summary`

The file stays compact on purpose. It is meant to guide manual review and the
next bundle-download step, not to store every source field.

## Current observed final run

Based on `gcn_grandma_grandma_base.json`, the current output contains:

| Metric | Value |
|---|---:|
| Total selected-source records | 156 |
| `high` priority | 31 |
| `medium` priority | 38 |
| `low` priority | 87 |

This file is the current starting point for deciding which events should be
evaluated in depth first.
