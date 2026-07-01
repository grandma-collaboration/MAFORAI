# MAFORAI

Repository for the MAFORAI internship work.

## Current scope

The repository currently has two connected workflows:

1. a SkyPortal workflow to audit the API, build source inventories, and prepare
   the compact `gcn_grandma.json` event universe plus the tabular
   `skyportal_event_baseline`;
2. a GCN workflow to download Circulars, build a searchable index, match
   events against Circulars, extract structured claims from matched bodies, and
   compare those claims against the compact SkyPortal metadata before building
   a final review table for astronomer validation.

The active handoff between both sides is:

```text
SkyPortal inventories -> data/interim/skyportal/gcn_grandma.json -> data/interim/skyportal/skyportal_event_baseline.parquet -> GCN pipeline
```

## Documentation map

The documentation is intentionally split by workflow.

| Area | Entry point | Purpose |
|---|---|---|
| SkyPortal | [docs/skyportal/README.md](docs/skyportal/README.md) | Setup, endpoint audit, source inventories, and construction of `gcn_grandma.json` |
| GCN | [docs/gcn/README.md](docs/gcn/README.md) | Circular archive download, yearly indexing, event matching, claim extraction, and enrichment comparison |
| GCN review table | [docs/gcn/05_event_review.md](docs/gcn/05_event_review.md) | Final field-by-field table for astronomer validation |
| GCN INCEpTION dossiers | [docs/gcn/06_inception_dossiers.md](docs/gcn/06_inception_dossiers.md) | Blind plain-text dossiers built from matched Circulars for pilot annotation |

Supporting documents:

| File | Purpose |
|---|---|
| [docs/decisiones.md](docs/decisiones.md) | Design and workflow decisions |
| [docs/endpoints.md](docs/endpoints.md) | Broad endpoint catalog and notes |
| [docs/questions_for_team.md](docs/questions_for_team.md) | Open questions to discuss with the team |

## Repository layout

| Path | Role |
|---|---|
| `scripts/` | Thin CLI entrypoints for the SkyPortal workflow |
| `scripts/gcn/` | Thin CLI entrypoints for the GCN workflow |
| `src/skyportal_corpus/core/` | Shared config and path helpers |
| `src/skyportal_corpus/extraction/` | Reusable SkyPortal and GCN workflow logic |
| `configs/extraction/skyportal.yaml` | Shared runtime configuration for SkyPortal extraction |
| `tests/` | Small tests for config loading and reusable workflow helpers |

## Main entrypoints

SkyPortal:

- `scripts/01_audit_endpoint_availability.py`
- `scripts/02_fetch_source_inventory.py`
- `scripts/03_build_gcn_grandma.py`
- `scripts/04_build_skyportal_event_baseline.py`

GCN:

- `scripts/gcn/01_download_circulars_archive.py`
- `scripts/gcn/02_build_circulars_index.py`
- `scripts/gcn/03a_build_event_search_terms.py`
- `scripts/gcn/03b_match_events_to_circulars.py`
- `scripts/gcn/03c_build_event_match_summary.py`
- `scripts/gcn/04a_extract_core_claims.py`
- `scripts/gcn/04b_build_claim_summary.py`
- `scripts/gcn/05a_build_event_enrichment_candidates.py`
- `scripts/gcn/05b_compare_gcn_enrichment_with_skyportal.py`
- `scripts/gcn/05c_build_event_review_table.py`
- `scripts/gcn/06_export_astronomer_review_xlsx.py`
- `scripts/gcn/07_build_inception_event_dossier.py`

## Data layout

The repository writes generated data under the project `data/` directory.

| Path | Purpose |
|---|---|
| `data/raw/skyportal/endpoint_audit/` | One directory per SkyPortal endpoint-audit run |
| `data/raw/skyportal/inventory/` | One directory per SkyPortal source-inventory run |
| `data/interim/skyportal/gcn_grandma.json` | Compact event universe handed from SkyPortal to the GCN matching workflow |
| `data/interim/skyportal/skyportal_event_baseline.parquet` | Canonical SkyPortal-side baseline used later by GCN enrichment and review |
| `data/raw/gcn/circulars/archive_json/` | One directory per raw GCN Circular archive download |
| `data/interim/gcn/circulars/` | Year-partitioned normalized GCN Circular indexes |
| `data/interim/gcn/event_matching/` | Step-A matching outputs |
| `data/interim/gcn/event_extraction/` | Step-B claim extraction outputs |
| `data/interim/gcn/event_enrichment/` | Step-C event-level enrichment outputs |
| `data/interim/gcn/event_validation/` | Final review table for astronomer validation |
| `data/interim/gcn/event_validation/astronomer_review/` | Curated `.xlsx` workbook for astronomer review |
| `data/interim/gcn/event_validation/inception_dossiers/` | Blind `.txt` dossiers ready to upload into INCEpTION |

## Minimal starting points

If you want to reproduce the current workflow, start here:

1. read [docs/skyportal/README.md](docs/skyportal/README.md);
2. build or refresh `data/interim/skyportal/gcn_grandma.json`;
3. build or refresh `data/interim/skyportal/skyportal_event_baseline.parquet`;
4. read [docs/gcn/README.md](docs/gcn/README.md) to continue with the GCN side.

This root `README.md` is intentionally kept as a general map. The operational
commands, outputs, and step-by-step details live in the workflow-specific
documentation folders.
