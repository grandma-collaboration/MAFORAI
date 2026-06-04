# Filtered Inventories

## Goal

This document organizes the inventory profiles currently used with
`scripts/02_fetch_source_inventory.py`.

The important distinction is simple:

- `recent_500` is a bounded orientation run;
- the other named profiles are semantic subsets intended to run until the API
  total is reached.

## Current profile matrix

| Profile | Type | Main filter | Intended use |
|---|---|---|---|
| `recent_500` | Bounded recent slice | `sortBy=saved_at`, `sortOrder=desc`, `max_pages=5` | Quick overview of recently saved sources |
| `has_spectrum` | Complete filtered subset | `hasSpectrum=true` | Sources with at least one spectrum |
| `has_robotic_followup` | Complete filtered subset | `hasFollowupRequest=true` | Sources carrying the explicit robotic/request-based follow-up flag |
| `grandma_has_robotic_followup_det2_base` | Complete filtered subset | `hasFollowupRequest=true`, `group_ids=3`, `numberDetections=2` | GRANDMA sources with the robotic follow-up request flag and at least two detections |
| `grandma_base` | Complete filtered subset | `group_ids=3` | Enriched GRANDMA inventory without follow-up or detection filters |
| `grandma_det2_base` | Complete filtered subset | `group_ids=3`, `numberDetections=2` | GRANDMA sources with at least two detections, without a follow-up filter |
| `classified` | Complete filtered subset | `classified=true` | Sources with at least one classification |
| `redshift` | Complete filtered subset | `minRedshift=0.0001` | Sources with positive redshift |
| `many_detections` | Complete filtered subset | `numberDetections=5` | Sources with at least five detections |
| `gcn` | Complete filtered subset | `sourceID=GCN` | GCN-like sources |
| `ep` | Complete filtered subset | `sourceID=EP` | EP-like sources |

## Shared query templates

The YAML config uses two shared query templates:

| Template | Parameters |
|---|---|
| `recent_desc` | `sortBy=saved_at`, `sortOrder=desc` |
| `enriched_recent_desc` | `includePhotometryExists=true`, `includeSpectrumExists=true`, `includeCommentExists=true`, `includeDetectionStats=true`, `sortBy=saved_at`, `sortOrder=desc` |

In practice:

- `recent_500` uses `recent_desc`;
- the filtered subsets use `enriched_recent_desc`.

## Commands

The normal way to run these inventories is now by profile name:

```bash
python scripts/02_fetch_source_inventory.py --profile recent_500
python scripts/02_fetch_source_inventory.py --profile has_spectrum
python scripts/02_fetch_source_inventory.py --profile has_robotic_followup
python scripts/02_fetch_source_inventory.py --profile grandma_has_robotic_followup_det2_base
python scripts/02_fetch_source_inventory.py --profile grandma_base
python scripts/02_fetch_source_inventory.py --profile grandma_det2_base
python scripts/02_fetch_source_inventory.py --profile classified
python scripts/02_fetch_source_inventory.py --profile redshift
python scripts/02_fetch_source_inventory.py --profile many_detections
python scripts/02_fetch_source_inventory.py --profile gcn
python scripts/02_fetch_source_inventory.py --profile ep
```

If you need a quick variation, use CLI overrides instead of editing the profile
immediately. Example:

```bash
python scripts/02_fetch_source_inventory.py \
  --profile recent_500 \
  --max-pages 2 \
  --run-label recent_200_preview
```

## Observed run summaries

The table below records the runs used while writing this documentation.

| Run label | Main filter | API reported total matches | Pages saved | Sources saved | Stopped reason |
|---|---|---:|---:|---:|---|
| `recent_500` | `sortBy=saved_at`, `sortOrder=desc` | 50,618 | 5 | 500 | `max_pages_reached` |
| `has_spectrum` | `hasSpectrum=true` | 60 | 1 | 60 | `api_total_matches_reached` |
| `has_robotic_followup` | `hasFollowupRequest=true` | 370 | 4 | 370 | `api_total_matches_reached` |
| `grandma_has_robotic_followup_det2_base` | `hasFollowupRequest=true`, `group_ids=3`, `numberDetections=2`, `includeHosts=true` | 82 | 1 | 82 | `api_total_matches_reached` |
| `grandma_base` | `group_ids=3`, `includeHosts=true` | 382 | 4 | 382 | `api_total_matches_reached` |
| `grandma_det2_base` | `group_ids=3`, `numberDetections=2`, `includeHosts=true` | 95 | 1 | 95 | `api_total_matches_reached` |
| `classified` | `classified=true` | 834 | 9 | 834 | `api_total_matches_reached` |
| `redshift` | `minRedshift=0.0001` | 51 | 1 | 51 | `api_total_matches_reached` |
| `many_detections` | `numberDetections=5` | 71 | 1 | 71 | `api_total_matches_reached` |
| `gcn` | `sourceID=GCN` | 144 | 2 | 144 | `api_total_matches_reached` |
| `ep` | `sourceID=EP` | 193 | 2 | 193 | `api_total_matches_reached` |
