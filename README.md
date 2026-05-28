# MAFORAI
MAFORAI Internship repository

## Current stage: API and data availability audit

Before designing the final corpus, we first audited the SkyPortal API to understand which data families are available, which endpoints are accessible, and how to retrieve representative source subsets.

The goal of this phase is not to build the final dataset yet, but to identify useful data modalities for a future multimodal corpus: source metadata, photometry, spectra, classifications, comments, annotations, follow-up requests, GCN/EP-like events, and operational metadata.

## Reproducible workflow

The current SkyPortal extraction workflow is documented in:

- `docs/skyportal/README.md`

This documentation explains how to:

1. configure the environment;
2. run the endpoint availability audit;
3. download a general source inventory;
4. create filtered source inventories;
5. interpret the current findings.

## Scripts used so far

- `scripts/01_audit_endpoint_availability.py`: tests endpoint availability and response structure.
- `scripts/02_fetch_source_inventory.py`: downloads raw paginated source inventories from `/api/sources`, optionally using filters.

## Current output layout

The generated raw files are written locally under `data/raw/skyportal/`, with
one folder per run:

- Endpoint audit runs:
  `data/raw/skyportal/endpoint_audit/endpoint_audit_<label>_<timestamp>/`
  containing `endpoint_status.csv`, `endpoint_status.json`, `summary.json`,
  `endpoint_audit.log`, and optionally `responses/`.
- Source inventory runs:
  `data/raw/skyportal/inventory/source_inventory_<run_label>_<timestamp>/`
  containing `manifest.json`, `source_inventory.log`, and one or more
  `sources_page_XXX.json`.

These raw outputs are local artifacts and are not intended to be committed to
the repository. A fresh clone may therefore contain only the directory
placeholders and documentation, not the generated run folders.

## Main findings so far

- `/api/sources/{source_id}` is a rich root object, but specialized endpoints are still needed for complete photometry, comments, spectra and other modalities.
- `/api/sources` supports many useful filters, allowing targeted inventories instead of downloading the full catalog.
- Seven complete filtered inventories were generated in local runs: spectra,
  follow-up, classified, redshift, multiple detections, GCN-like IDs and
  EP-like IDs.
