# Setup

## Goal

This document describes the minimum setup needed to run the current SkyPortal
workflow.

## What the current workflow uses

The repository has broader dependencies for notebooks and later analysis, but
the current SkyPortal scripts mainly depend on:

| Package | Used for |
|---|---|
| `requests` | HTTP requests to the API |
| `python-dotenv` | Loading `SKYPORTAL_API_TOKEN` from a local `.env` file |
| `pyyaml` | Loading the shared SkyPortal config |

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install --no-build-isolation -e .
```
## Authentication

Both scripts read the API token from `SKYPORTAL_API_TOKEN`.

Recommended option:

```bash
export SKYPORTAL_API_TOKEN="your_token_here"
```

Optional local `.env` file:

```env
SKYPORTAL_API_TOKEN=your_token_here
```

If `python-dotenv` is installed, the workflow loads `.env` automatically.

## Shared config

The shared runtime config lives at:

```text
configs/extraction/skyportal.yaml
```

That file is already used by the current scripts. It centralizes:

| Area | Stored there |
|---|---|
| API target | Base URL and token environment-variable name |
| Output paths | Raw output roots for audit and inventory runs |
| Shared HTTP defaults | Timeouts and retries |
| Audit defaults | Timeout, inter-request sleep, and sample context |
| Inventory defaults | Page size, retries, sleep, and start page |
| Named inventory profiles | `recent_500`, `has_spectrum`, `has_followup`, `classified`, `redshift`, `many_detections`, `gcn`, `ep` |

Secrets still belong in `.env`, not in YAML.

## Code layout

The current implementation is intentionally small:

| Path | Role |
|---|---|
| `scripts/01_audit_endpoint_availability.py` | CLI wrapper for the endpoint audit |
| `scripts/02_fetch_source_inventory.py` | CLI wrapper for the source inventory |
| `src/skyportal_corpus/core/` | Shared config and path helpers |
| `src/skyportal_corpus/extraction/` | Shared audit, client, and inventory logic |
| `tests/` | Small tests for config loading and inventory profiles |

## Output layout

The workflow writes one directory per run under `data/raw/skyportal/`.

| Path pattern | Produced by | Typical contents |
|---|---|---|
| `data/raw/skyportal/endpoint_audit/endpoint_audit_<label>_<timestamp>/` | `scripts/01_audit_endpoint_availability.py` | `endpoint_status.csv`, `endpoint_status.json`, `summary.json`, `endpoint_audit.log` |
| `data/raw/skyportal/inventory/source_inventory_<run_label>_<timestamp>/` | `scripts/02_fetch_source_inventory.py` | `manifest.json`, `source_inventory.log`, `sources_page_XXX.json` |
| `data/raw/skyportal/source_bundles/` | Not used yet by the current scripts | Reserved for a later extraction stage |

## Basic verification

```bash
python scripts/01_audit_endpoint_availability.py --help
python scripts/02_fetch_source_inventory.py --help
python -m unittest discover -s tests -p 'test_*.py' -v
```

If the help commands work, the tests pass, and the token is configured, the
local setup is ready for the current workflow.
