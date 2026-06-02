# MAFORAI

Repository for the MAFORAI internship work.

## Current focus

The current phase is a study of the SkyPortal API. The goal is to understand
what we can actually extract, which endpoint families are usable, and how to
build representative source subsets before committing to a final corpus design.

Right now the work is centered on three things:

- auditing endpoint availability and response shape;
- downloading raw source inventories from `GET /api/sources`;
- testing filters that produce useful subsets such as sources with spectra,
  follow-up, classifications, redshift, GCN-like IDs, and EP-like IDs.

## Where to start

The main operational guide lives in:

- `docs/skyportal/README.md`

That folder covers setup, audit runs, source inventories, named inventory
profiles, and the current findings.

The broader context stays in:

- `docs/decisiones.md`: design decisions taken so far;
- `docs/endpoints.md`: broad endpoint catalog for the next extraction steps;
- `docs/questions_for_team.md`: place to record open questions when they appear.

## Current code layout

The current SkyPortal workflow is split into a few small layers:

| Path | Role |
|---|---|
| `scripts/` | Thin CLI entrypoints |
| `src/skyportal_corpus/core/` | Shared config and path helpers |
| `src/skyportal_corpus/extraction/` | Reusable audit and extraction logic |
| `pyproject.toml` | Project metadata and package/dependency definition |
| `configs/extraction/skyportal.yaml` | Shared runtime configuration |
| `tests/` | Small tests for config loading and inventory-profile resolution |

The two entrypoints used today are:

- `scripts/01_audit_endpoint_availability.py`
- `scripts/02_fetch_source_inventory.py`

## Raw outputs

Generated files are written locally under `data/raw/skyportal/`, one folder per
run:

- `endpoint_audit/endpoint_audit_<label>_<timestamp>/`
- `inventory/source_inventory_<run_label>_<timestamp>/`

Those folders are working artifacts. The repository keeps the directory
structure and the documentation, but not the generated run folders themselves.

## Current takeaways

- `/api/sources` is a practical inventory layer and already supports useful
  filters for targeted subsets.
- `GET /api/sources/{source_id}` is a strong root object, but it is not enough
  on its own for full photometry, comments, or spectra.
