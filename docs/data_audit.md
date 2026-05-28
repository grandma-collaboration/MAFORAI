# Data Audit

## 1. Objective

The goal of this audit is to understand the available SkyPortal/ICARE data before designing the final corpus.

## 2. Endpoint availability audit

### Script

`scripts/01_audit_endpoint_availability.py`

### Current output location

`data/raw/skyportal/endpoint_audit/endpoint_audit_initial_20260528_141555/`

This path refers to the local output generated during the audit. Raw outputs
under `data/raw/skyportal/` are not expected to be committed to the repository,
so a fresh clone may not include this run directory.

When generated locally, this run directory contains:
- `endpoint_status.csv`
- `endpoint_status.json`
- `summary.json`
- `endpoint_audit.log`

### Summary

| Metric | Value |
|---|---:|
| Total endpoints tested | 70 |
| Successful endpoints | 33 |
| Skipped endpoints | 31 |
| HTTP errors | 3 |
| Request errors | 3 |

### Interpretation

Skipped endpoints are not failures: most of them require specific IDs such as `spectrum_id`, `classification_id`, `followup_request_id`, or `taxonomy_id`.

## 3. Important endpoint observations

### Source root endpoint

`GET /api/sources/{source_id}` returns a rich source-level object including metadata, TNS information, redshift, summaries, follow-up requests, annotations, classifications, tags, groups and associated objects.

### Specialized endpoints

Some data are not fully contained in the source root object and require specialized endpoints:
- photometry
- photometric statistics
- comments
- spectra
- classifications
- GCN associations

## 4. Source inventory extraction

### Script

`scripts/02_fetch_source_inventory.py`

### Current output location

Local source inventories are written under:

`data/raw/skyportal/inventory/`

These raw inventories are not expected to be committed to the repository. The
table below summarizes the local runs used to produce the current audit notes.

### Baseline recent window

A bounded recent inventory was also generated to inspect the most recently
saved sources without attempting a full crawl.

| Metric | Value |
|---|---:|
| Run label | `recent_500` |
| API reported total matches | 50,618 |
| Pages saved | 5 |
| Sources saved | 500 |
| Stopped reason | `max_pages_reached` |

## 5. Filtered inventories

| Inventory folder | Filter | Pages saved | Total sources |
|---|---|---:|---:|
| `source_inventory_has_spectrum_20260528_135105` | `hasSpectrum=true` | 1 | 60 |
| `source_inventory_has_followup_20260528_135114` | `hasFollowupRequest=true` | 4 | 370 |
| `source_inventory_classified_20260528_135135` | `classified=true` | 9 | 834 |
| `source_inventory_redshift_20260528_135144` | `minRedshift=0.0001` | 1 | 51 |
| `source_inventory_many_detections_20260528_135148` | `numberDetections=5` | 1 | 71 |
| `source_inventory_gcn_20260528_135155` | `sourceID=GCN` | 2 | 144 |
| `source_inventory_ep_20260528_135202` | `sourceID=EP` | 2 | 193 |

All these inventories include the same enrichment flags in the query:
`includePhotometryExists=true`, `includeSpectrumExists=true`,
`includeCommentExists=true`, `includeDetectionStats=true`,
`sortBy=saved_at`, `sortOrder=desc`, and `numPerPage=100`.

All filtered inventories reached `api_total_matches_reached`, meaning each
filtered subset was fully downloaded in the local audit runs from which these
summary values were recorded.

## 6. Preliminary conclusion

The `/api/sources` endpoint can be used as a targeted inventory tool. Instead of downloading the full database, we can build representative source subsets using filters, then select a diverse sample for full source-bundle extraction.
