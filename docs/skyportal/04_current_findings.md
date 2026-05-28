# Current Findings

## Evidence base

The current findings are grounded in the runs executed during the audit.

| Evidence source | What it contributes |
|---|---|
| Endpoint audit `summary.json` | Aggregate endpoint audit metrics |
| Inventory `manifest.json` files | Inventory counts, pagination, filters, and stop reasons |
| `sources_page_001.json` files | Representative examples from each subset |

## Inventory results

The observed complete filtered inventories produced the following results.

| Run label | API reported total matches | Sources saved | Pages saved | Stopped reason |
|---|---:|---:|---:|---|
| `has_spectrum` | 60 | 60 | 1 | `api_total_matches_reached` |
| `has_followup` | 370 | 370 | 4 | `api_total_matches_reached` |
| `classified` | 834 | 834 | 9 | `api_total_matches_reached` |
| `redshift` | 51 | 51 | 1 | `api_total_matches_reached` |
| `many_detections` | 71 | 71 | 1 | `api_total_matches_reached` |
| `gcn` | 144 | 144 | 2 | `api_total_matches_reached` |
| `ep` | 193 | 193 | 2 | `api_total_matches_reached` |

## Representative first-page examples

These examples come from the first saved page of each observed inventory and
show the kind of objects surfaced by the filters.

| Run label | Example source ID | Example name or TNS name | RA | Dec |
|---|---|---|---:|---:|
| `has_spectrum` | `2023qye` | `SN 2023qye` | 316.4845949 | -14.3431405 |
| `has_followup` | `EP-260527_061954` | `-` | 193.105 | 1.453 |
| `classified` | `GCN-260515_190819` | `-` | 227.6852 | 24.5562 |
| `redshift` | `GCN-260509_215104` | `-` | 176.899834 | 0.288276 |
| `many_detections` | `GCN-260303_060127` | `-` | 93.1877 | 41.1512 |
| `gcn` | `GCN-260303_060127` | `-` | 93.1877 | 41.1512 |
| `ep` | `EP-260527_061954` | `-` | 193.105 | 1.453 |

## Main technical conclusions

| Finding | Evidence | Implication |
|---|---|---|
| `/api/sources` is a practical inventory layer | All observed subsets were retrieved through `/api/sources` with query filters | The endpoint is sufficient for building targeted candidate pools |
| The filters expose meaningful subsets | Spectra, follow-up, classification, redshift, GCN-like, and EP-like subsets all returned non-trivial results | We can build diverse source slices without a full-catalog crawl |
| The subsets are reproducible | Every observed run had a `manifest.json`, per-page raw JSON, counts, and `stopped_reason` | Downstream selection can be traced back to exact request conditions |
| Some objects appear in more than one subset | `EP-260527_061954` appears in both `ep` and `has_followup`; `GCN-260303_060127` appears in both `gcn` and `many_detections` | Overlapping subsets can help identify richer candidates for deeper extraction |

## Relationship with the endpoint audit

The endpoint audit complements the inventories rather than replacing them.

| Audit observation | Inventory implication |
|---|---|
| `/api/sources/{source_id}` is information-rich | It is a strong entry point for a future source-level extractor |
| Many specialized endpoints require additional IDs | Deeper extraction will need source selection first, then endpoint-specific expansion |
| Some endpoints behave like non-JSON resources or downloads | A later source-bundle stage must handle mixed payload types explicitly |

## Practical next step

The current evidence supports a staged extraction strategy:

1. use `/api/sources` to create bounded or semantic inventories
2. choose a small but diverse set of candidate sources
3. expand those candidates with source-level and specialized endpoints
