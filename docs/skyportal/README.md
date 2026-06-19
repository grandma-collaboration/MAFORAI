# SkyPortal Workflow Documentation

This folder documents the current, reproducible SkyPortal workflow used in this
repository.

It is focused on what we can run today: setup, endpoint audit, source
inventories, the GCN-derived base built from the current inventory union, the
SkyPortal-side baseline derived from that base, and the conclusions supported
by those runs.

## How this fits with the code

The current implementation is split in a simple way:

| Layer | Purpose |
|---|---|
| `scripts/` | Thin CLI entrypoints |
| `src/skyportal_corpus/core/` | Shared config and path helpers |
| `src/skyportal_corpus/extraction/` | Operational audit, selection, and extraction logic |
| `configs/extraction/skyportal.yaml` | Shared runtime config and named inventory profiles |

## Scope

Included here:

| Topic | File |
|---|---|
| Environment and shared config | [00_setup.md](./00_setup.md) |
| Endpoint audit workflow | [01_endpoint_audit.md](./01_endpoint_audit.md) |
| Source inventory workflow | [02_source_inventory.md](./02_source_inventory.md) |
| GCN-derived base construction | [03_source_selection.md](./03_source_selection.md) |
| Named inventory profiles and observed runs | [04_filtered_inventories.md](./04_filtered_inventories.md) |
| Shortlist of relevant endpoints | [05_relevant_endpoints.md](./05_relevant_endpoints.md) |
| Practical `/api/sources` filters | [06_relevant_source_filters.md](./06_relevant_source_filters.md) |

Related documents outside this folder:

| Topic | Canonical document |
|---|---|
| Design decisions | [docs/decisiones.md](../decisiones.md) |
| Broad endpoint catalog | [docs/endpoints.md](../endpoints.md) |
| Team questions | [docs/questions_for_team.md](../questions_for_team.md) |
| Companion GCN workflow docs | [docs/gcn/README.md](../gcn/README.md) |

## Suggested reading order

1. [00_setup.md](./00_setup.md)
2. [01_endpoint_audit.md](./01_endpoint_audit.md)
3. [02_source_inventory.md](./02_source_inventory.md)
4. [04_filtered_inventories.md](./04_filtered_inventories.md)
5. [03_source_selection.md](./03_source_selection.md)
6. [05_relevant_endpoints.md](./05_relevant_endpoints.md)
7. [06_relevant_source_filters.md](./06_relevant_source_filters.md)

## Local output roots

The workflow writes raw outputs under `data/raw/skyportal/`:

| Path | Purpose |
|---|---|
| `data/raw/skyportal/endpoint_audit/` | One directory per endpoint-audit run |
| `data/raw/skyportal/inventory/` | One directory per `/api/sources` inventory run |

It also writes the canonical compact SkyPortal-side handoff artifacts under
`data/interim/skyportal/`:

| Path | Purpose |
|---|---|
| `data/interim/skyportal/gcn_grandma.json` | Canonical compact GCN-derived event universe built from the inventory union |
| `data/interim/skyportal/skyportal_event_baseline.csv` | Tabular SkyPortal-side baseline combining native fields, `source_summary`, and normalized `tags` |
| `data/interim/skyportal/skyportal_event_baseline.parquet` | Canonical baseline input for later GCN enrichment comparison and review |
