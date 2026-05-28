# Source Inventory Extraction

## Goal

`scripts/02_fetch_source_inventory.py` downloads raw paginated responses from
`GET /api/sources` and writes each page as JSON output.

It does not normalize fields, flatten nested objects, or build the final
dataset. Its role is to generate reproducible inventory snapshots.

## Script

```text
scripts/02_fetch_source_inventory.py
```

## Operating modes

The script supports two practical modes.

| Mode | Typical use | Main settings | Result shape |
|---|---|---|---|
| Bounded recent window | Quick baseline inventory of the most recent saved sources | `--max-pages 5`, `sortBy=saved_at`, `sortOrder=desc` | Up to 500 sources with `num-per-page=100` |
| Complete filtered subset | Full retrieval of one meaningful subset | `--max-pages 0` plus a semantic filter | Stops when `api_total_matches_reached` |

## Core arguments

| Argument | Meaning |
|---|---|
| `--run-label` | Human-readable label used in the output folder name |
| `--num-per-page` | Number of sources requested per page |
| `--start-page` | First page to download |
| `--max-pages` | Maximum number of pages to fetch; `0` means "continue until the API-reported total is reached" |
| `--query-param key=value` | Additional `/api/sources` query parameter; can be repeated |

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

## Reference commands

Baseline recent window:

```bash
python scripts/02_fetch_source_inventory.py \
  --run-label recent_500 \
  --num-per-page 100 \
  --max-pages 5 \
  --query-param sortBy=saved_at \
  --query-param sortOrder=desc
```

Observed example for this mode:

| Run label | API reported total matches | Pages saved | Sources saved | Stopped reason |
|---|---:|---:|---:|---|
| `recent_500` | 50618 | 5 | 500 | `max_pages_reached` |

Complete filtered subset:

```bash
python scripts/02_fetch_source_inventory.py \
  --run-label YOUR_LABEL \
  --num-per-page 100 \
  --max-pages 0 \
  --query-param YOUR_FILTER
```

## Directory convention

Generated runs follow the directory pattern shown above under
`data/raw/skyportal/inventory/`.
