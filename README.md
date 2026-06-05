# MAFORAI

Repository for the MAFORAI internship work.

## Current focus

The current phase is a study of the SkyPortal API. The goal is to understand
what we can actually extract, which endpoint families are usable, and how to
build representative source subsets before committing to a final corpus design.

Right now the work is centered on five things:

- auditing endpoint availability and response shape;
- downloading raw source inventories from `GET /api/sources`;
- building a GCN-derived subset inside `GRANDMA`;
- assigning a compact, explainable priority to those events;
- downloading per-source bundles for the current `high` subset and exporting a
  shared sample for review.

## Where to start

The main operational guide lives in:

- `docs/skyportal/README.md`

That folder covers setup, audit runs, source inventories, GCN-derived
selection, source-bundle extraction, shared samples, and the current findings.

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
| `tests/` | Small tests for config loading, inventory profiles, selection, bundles, and shared sample exports |

The main entrypoints used today are:

- `scripts/01_audit_endpoint_availability.py`
- `scripts/02_fetch_source_inventory.py`
- `scripts/03_build_gcn_grandma.py`
- `scripts/04_build_selected_sources.py`
- `scripts/05_fetch_source_bundles.py`
- `scripts/06_export_high_priority_samples.py`

## Raw outputs

Generated files are written locally under `data/raw/skyportal/`, one folder per
run:

- `endpoint_audit/endpoint_audit_<label>_<timestamp>/`
- `inventory/source_inventory_<run_label>_<timestamp>/`
- `source_bundles/source_bundle_run_<timestamp>/`

Those folders are working artifacts. The repository keeps the directory
structure and the documentation, but not the generated run folders themselves.

Compact shared review artifacts are written under `data/samples/`, including:

- `gcn_grandma_grandma_base.json`
- `selected_sources_for_bundles.json`
- `selected_sources_high.json`
- `selected_sources_high_bundle_summary.csv`

## Current takeaways

- `/api/sources` is a practical inventory layer and already supports useful
  filters for targeted subsets.
- `GET /api/sources/{source_id}` is a strong root object, but it is not enough
  on its own for full photometry, comments, or spectra.
- the current first-pass event ranking is intentionally explicit and
  reproducible: it uses redshift, comments, compact detection counts, and a
  small set of classification labels to prioritize GCN-derived `GRANDMA`
  events before deeper review.
