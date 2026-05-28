# Setup

## Goal

This document describes the minimum setup needed to run the current SkyPortal
audit and inventory scripts.

## Prerequisites

| Item | Required | Notes |
|---|---|---|
| Python 3 | Yes | Used to run both extraction scripts |
| `SKYPORTAL_API_TOKEN` | Yes | Required for authenticated API requests |
| `requirements.txt` dependencies | Yes | Includes the packages used by the scripts |

Current packages used directly by the two scripts:

| Package | Used for |
|---|---|
| `requests` | HTTP requests to the API |
| `pandas` | Exporting the endpoint audit summary to CSV |
| `python-dotenv` | Loading the token from a local `.env` file |

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Authentication

Both scripts read the API token from the `SKYPORTAL_API_TOKEN` environment
variable.

Recommended option:

```bash
export SKYPORTAL_API_TOKEN="your_token_here"
```

Optional local `.env` file:

```env
SKYPORTAL_API_TOKEN=your_token_here
```

If `python-dotenv` is installed, the scripts will load `.env` automatically.

## Default API target

| Setting | Value |
|---|---|
| Default base URL | `https://skyportal-icare.ijclab.in2p3.fr/api` |

## Output layout

The current workflow writes one directory per run under `data/raw/skyportal/`.

| Path pattern | Produced by | Typical contents |
|---|---|---|
| `data/raw/skyportal/endpoint_audit/endpoint_audit_<label>_<timestamp>/` | `scripts/01_audit_endpoint_availability.py` | `endpoint_status.csv`, `endpoint_status.json`, `summary.json`, `endpoint_audit.log`, optional `responses/` |
| `data/raw/skyportal/inventory/source_inventory_<run_label>_<timestamp>/` | `scripts/02_fetch_source_inventory.py` | `manifest.json`, `source_inventory.log`, `sources_page_XXX.json` |
| `data/raw/skyportal/sources_bundles/` | Not used yet by the current scripts | Reserved for a later extraction stage |

Current on-disk structure:

```text
data/
  raw/
    skyportal/
      endpoint_audit/
      inventory/
      sources_bundles/
```

## Basic verification

```bash
python scripts/01_audit_endpoint_availability.py --help
python scripts/02_fetch_source_inventory.py --help
```

If both commands print help successfully and the token is configured, the local
setup is ready for the current workflow.
