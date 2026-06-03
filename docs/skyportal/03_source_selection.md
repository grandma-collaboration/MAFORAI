# Source Selection for Bundles

## Goal

This step turns one saved inventory into a smaller, explicit list of source IDs
to inspect in more detail during the later bundle-extraction stage.

The point is not to build the final dataset yet. The point is to keep a short,
reproducible candidate list with clear reasons for why each source was kept.

## Entry points

| File | Role |
|---|---|
| `scripts/03_select_sources_for_bundles.py` | Thin CLI wrapper |
| `src/skyportal_corpus/extraction/source_selection.py` | Selection logic and JSON builder |

## Input

The current selection step uses one saved inventory as its only input:

- `grandma_followup_det2_base`

This inventory was chosen because it already encodes the operational baseline
we wanted to preserve:

- source belongs to `GRANDMA` (`group_ids=3`);
- source has at least one follow-up request;
- source has at least two detections.

## Why this baseline was chosen

The goal of this first selection pass is to stay close to the events that are
already active and informative inside SkyPortal.

In practice, this baseline gives us:

- sources that already triggered follow-up interest;
- enough detections to avoid obviously empty or too-thin cases;
- a subset tied to the `GRANDMA` workflow rather than the full catalog.

It is a practical starting point for later per-source extraction.

## Family rules

The current selection uses three source families:

| Family | Rule | Outcome |
|---|---|---|
| `grb_like` | Source ID starts with `GCN` or `GRB` | Kept |
| `non_grb` | Source ID does not start with `GCN`, `GRB`, or `EP` | Kept |
| `ep` | Source ID starts with `EP` | Excluded |

`EP` sources are excluded on purpose in this first pass. Some of them are
GRB-like, but others are FXTs or less clear cases. Keeping them out of the
initial `non_grb` sample avoids mixing categories too early.

## Priority rules

Each selected candidate is assigned one simple priority level.

| Priority | Rule |
|---|---|
| `high` | `redshift < 1` or `redshift > 4` |
| `medium` | redshift is present, or `comment_exists=true` and `num_det_global >= 5` |
| `low` | all other sources in the base inventory |

The reasoning is straightforward:

- extreme redshifts are scientifically interesting enough to deserve the top
  bucket;
- comments and a higher detection count are used as signs that the source has
  more context and better observational support;
- the remaining sources are still valid candidates, just less urgent.

## Selection quotas

The current target sample is:

| Family | Target count |
|---|---:|
| `grb_like` | 20 |
| `non_grb` | 10 |

This keeps the sample small enough to inspect manually while still preserving a
clear GRB-heavy subset and a smaller comparison set.

## Fields kept in the output JSON

Each selected source record contains:

| Field | Purpose |
|---|---|
| `id` | Source identifier |
| `source_family` | `grb_like` or `non_grb` |
| `priority` | `high`, `medium`, or `low` |
| `selection_reasons` | Explicit list of criteria the source passed |
| `selection_context.redshift` | Compact redshift context |
| `selection_context.num_det_global` | Compact detection-count context |
| `selection_context.comment_exists` | Whether comments exist |
| `selection_context.groups` | Relevant group names kept for review |
| `source_summary` | Short human-readable context from the inventory |

The JSON intentionally stays compact. It does not include fields like
`host_id`, `spectrum_exists`, or internal provenance fields that would make the
file noisier without helping the first manual review.

## Typical command

```bash
python scripts/03_select_sources_for_bundles.py \
  --inventory-dir data/raw/skyportal/inventory/source_inventory_grandma_followup_det2_base_<timestamp>
```

By default, the output is written under `data/samples/`:

```text
data/samples/selected_sources_for_bundles_<run_label>.json
```

## Current observed run

The current documented run based on `grandma_followup_det2_base` produced:

| Metric | Value |
|---|---:|
| Total input sources | 82 |
| `grb_like` candidates | 36 |
| `non_grb` candidates | 39 |
| Excluded `EP` candidates | 7 |
| Selected `grb_like` sources | 20 |
| Selected `non_grb` sources | 10 |
