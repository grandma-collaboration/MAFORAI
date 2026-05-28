# Filtered Inventories

## Goal

This document organizes the inventory recipes used with
`scripts/02_fetch_source_inventory.py` and distinguishes between:

| Type | Meaning |
|---|---|
| Baseline bounded inventory | A recent slice used for orientation, not a complete semantic subset |
| Complete filtered inventory | A subset defined by a semantic filter and downloaded until `api_total_matches_reached` |

## Inventory matrix

| Run label | Type | Primary query condition | Intended use | Output folder pattern |
|---|---|---|---|---|
| `recent_500` | Baseline bounded inventory | `sortBy=saved_at`, `sortOrder=desc`, `max-pages=5` | Inspect a recent slice of saved sources | `source_inventory_recent_500_<timestamp>/` |
| `has_spectrum` | Complete filtered inventory | `hasSpectrum=true` | Sources with at least one spectrum | `source_inventory_has_spectrum_<timestamp>/` |
| `has_followup` | Complete filtered inventory | `hasFollowupRequest=true` | Sources with at least one follow-up request | `source_inventory_has_followup_<timestamp>/` |
| `classified` | Complete filtered inventory | `classified=true` | Sources with at least one classification | `source_inventory_classified_<timestamp>/` |
| `redshift` | Complete filtered inventory | `minRedshift=0.0001` | Sources with positive redshift | `source_inventory_redshift_<timestamp>/` |
| `many_detections` | Complete filtered inventory | `numberDetections=5` | Sources with at least five detections | `source_inventory_many_detections_<timestamp>/` |
| `gcn` | Complete filtered inventory | `sourceID=GCN` | GCN-like sources | `source_inventory_gcn_<timestamp>/` |
| `ep` | Complete filtered inventory | `sourceID=EP` | EP-like sources | `source_inventory_ep_<timestamp>/` |

## Shared enrichment flags

The complete filtered inventories use the same enrichment flags.

| Query parameter | Why it is included |
|---|---|
| `includePhotometryExists=true` | Indicates whether photometry is available |
| `includeSpectrumExists=true` | Indicates whether spectra are available |
| `includeCommentExists=true` | Indicates whether comments are available |
| `includeDetectionStats=true` | Adds detection-level summary information |
| `sortBy=saved_at` | Sorts results by most recently saved sources |
| `sortOrder=desc` | Returns newest matching sources first |
| `numPerPage=100` | Uses the standard page size for these runs |

## Command recipes

### 1. Baseline recent slice

This command retrieves up to 500 recently saved sources and is useful as a
general orientation run.

```bash
python scripts/02_fetch_source_inventory.py \
  --run-label recent_500 \
  --num-per-page 100 \
  --max-pages 5 \
  --query-param sortBy=saved_at \
  --query-param sortOrder=desc
```

Notes:

| Aspect | Value |
|---|---|
| Semantic filter | None |
| Completeness | No; bounded to five pages |
| Expected stop reason | `max_pages_reached` |
| Example observed run | `source_inventory_recent_500_20260528_161939` |

### 2. Complete filtered subsets

Common command template:

```bash
python scripts/02_fetch_source_inventory.py \
  --run-label YOUR_LABEL \
  --num-per-page 100 \
  --max-pages 0 \
  --query-param YOUR_FILTER \
  --query-param includePhotometryExists=true \
  --query-param includeSpectrumExists=true \
  --query-param includeCommentExists=true \
  --query-param includeDetectionStats=true \
  --query-param sortBy=saved_at \
  --query-param sortOrder=desc
```

Primary filter substitutions:

| Run label | Substitute `YOUR_FILTER` with |
|---|---|
| `has_spectrum` | `hasSpectrum=true` |
| `has_followup` | `hasFollowupRequest=true` |
| `classified` | `classified=true` |
| `redshift` | `minRedshift=0.0001` |
| `many_detections` | `numberDetections=5` |
| `gcn` | `sourceID=GCN` |
| `ep` | `sourceID=EP` |

## Example run summaries

The table below records the runs used while writing this documentation.

| Run label | Example folder | Main filter | API reported total matches | Pages saved | Sources saved | Stopped reason |
|---|---|---|---:|---:|---:|---|
| `recent_500` | `source_inventory_recent_500_20260528_161939` | `sortBy=saved_at`, `sortOrder=desc` | 50618 | 5 | 500 | `max_pages_reached` |
| `has_spectrum` | `source_inventory_has_spectrum_20260528_135105` | `hasSpectrum=true` | 60 | 1 | 60 | `api_total_matches_reached` |
| `has_followup` | `source_inventory_has_followup_20260528_135114` | `hasFollowupRequest=true` | 370 | 4 | 370 | `api_total_matches_reached` |
| `classified` | `source_inventory_classified_20260528_135135` | `classified=true` | 834 | 9 | 834 | `api_total_matches_reached` |
| `redshift` | `source_inventory_redshift_20260528_135144` | `minRedshift=0.0001` | 51 | 1 | 51 | `api_total_matches_reached` |
| `many_detections` | `source_inventory_many_detections_20260528_135148` | `numberDetections=5` | 71 | 1 | 71 | `api_total_matches_reached` |
| `gcn` | `source_inventory_gcn_20260528_135155` | `sourceID=GCN` | 144 | 2 | 144 | `api_total_matches_reached` |
| `ep` | `source_inventory_ep_20260528_135202` | `sourceID=EP` | 193 | 2 | 193 | `api_total_matches_reached` |
