# Source Inventory Extraction

## Goal

The source inventory workflow downloads raw paginated responses from
`GET /api/sources` and saves each page as JSON.

It does not normalize fields or build the final dataset. Its role is to create
reproducible source subsets that can later feed deeper extraction.

## Entry points

| File | Role |
|---|---|
| `scripts/02_fetch_source_inventory.py` | Thin CLI wrapper |
| `src/skyportal_corpus/extraction/source_inventory.py` | Actual extraction logic |

The script reads `configs/extraction/skyportal.yaml` by default and can use a
named profile through `--profile`.

## Practical modes

The current workflow has two practical modes:

| Mode | Typical use | Result |
|---|---|---|
| Named profile | Run a known inventory recipe from the shared config | Short command, consistent defaults |
| Ad hoc query | Try a new filter without editing the YAML yet | Flexible one-off run |

## Core arguments

| Argument | Meaning |
|---|---|
| `--profile` | Use a named profile from `configs/extraction/skyportal.yaml` |
| `--run-label` | Override the run label used in the output directory |
| `--num-per-page` | Override page size |
| `--start-page` | Override the first page |
| `--max-pages` | Override the page limit; `0` means "continue until the API total is reached" |
| `--timeout` | Override request timeout |
| `--max-retries` | Override retry count |
| `--sleep` | Override inter-request delay |
| `--query-param key=value` | Add or override `/api/sources` query parameters |

CLI arguments override the shared config and the selected profile.

## Typical commands

Recent bounded inventory:

```bash
python scripts/02_fetch_source_inventory.py \
  --profile recent_500
```

Complete filtered subset:

```bash
python scripts/02_fetch_source_inventory.py \
  --profile has_spectrum
```

Profile with one override:

```bash
python scripts/02_fetch_source_inventory.py \
  --profile classified \
  --max-pages 2 \
  --run-label classified_preview
```

Ad hoc query without a named profile:

```bash
python scripts/02_fetch_source_inventory.py \
  --run-label recent_custom \
  --max-pages 2 \
  --query-param sortBy=saved_at \
  --query-param sortOrder=desc
```

## Output files

Each run creates a directory under:

```text
data/raw/skyportal/inventory/source_inventory_<run_label>_<timestamp>/
```

The run directory contains:

| File | Purpose |
|---|---|
| `manifest.json` | Reproducibility record for the run |
| `source_inventory.log` | Execution log |
| `sources_page_001.json`, `sources_page_002.json`, ... | Raw page responses |

## What `manifest.json` captures

| Field | Meaning |
|---|---|
| `run_label` | Semantic label for the run |
| `profile_name` | Named profile used, if any |
| `query_parameters` | Effective query parameters used for the request |
| `pagination` | Starting page and page limit |
| `api_reported_total_matches` | API-reported `totalMatches` value |
| `counts.pages_saved` | Number of saved response pages |
| `counts.sources_seen_in_saved_pages` | Total number of sources saved across pages |
| `stopped_reason` | Why the loop stopped |
| `errors` | Page-level failures, if any |

Common `stopped_reason` values:

| Value | Meaning |
|---|---|
| `max_pages_reached` | The configured page limit was reached |
| `api_total_matches_reached` | All API-reported matches were downloaded |
| `empty_sources_page` | The API returned an empty page |
| `request_failed` | A page failed after retries |

## Current defaults

Unless you override them, the inventory workflow uses the shared defaults from
`configs/extraction/skyportal.yaml`:

| Setting | Value |
|---|---:|
| `num_per_page` | 100 |
| `start_page` | 1 |
| `max_pages` | 5 |
| `timeout_seconds` | 30 |
| `max_retries` | 3 |
| `sleep_seconds` | 0.3 |

The main named profiles are documented in
[03_filtered_inventories.md](./03_filtered_inventories.md).
