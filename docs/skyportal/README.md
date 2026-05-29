# SkyPortal Workflow Documentation

This folder documents the current operational workflow used to audit the
SkyPortal API and generate raw source inventories.

## Scope

Included here:

| Area | Description |
|---|---|
| Setup | Environment variables, dependencies, and output directories |
| Endpoint audit | How endpoint availability is tested |
| Source inventory extraction | How `/api/sources` inventories are downloaded |
| Inventory recipes | Baseline and filtered inventory commands |
| Current findings | What the observed runs already show |
| Endpoint selection | Which API endpoints are the most relevant for source-bundle extraction |
| Filter selection | Which `/api/sources` filters are the most relevant for inventory building |

Not duplicated here:

| Topic | Canonical document |
|---|---|
| Global project decisions | [docs/decisiones.md](../decisiones.md) |
| Endpoint catalog | [docs/endpoints.md](../endpoints.md) |
| Open coordination questions | [docs/questions_for_team.md](../questions_for_team.md) |

## Recommended reading order

| Step | File | Purpose |
|---:|---|---|
| 0 | [00_setup.md](./00_setup.md) | Prepare the environment and understand the raw output layout |
| 1 | [01_endpoint_audit.md](./01_endpoint_audit.md) | Run the endpoint availability audit and interpret its outputs |
| 2 | [02_source_inventory.md](./02_source_inventory.md) | Understand how the paginated `/api/sources` extractor works |
| 3 | [03_filtered_inventories.md](./03_filtered_inventories.md) | Review the inventory recipes and the run summaries used in the documentation |
| 4 | [04_current_findings.md](./04_current_findings.md) | See the current technical conclusions supported by those runs |
| 5 | [05_relevant_endpoints.md](./05_relevant_endpoints.md) | Review the subset of SkyPortal endpoints that matters most for the first corpus-oriented extraction workflow |
| 6 | [06_relevant_source_filters.md](./06_relevant_source_filters.md) | Review the `/api/sources` filters that are the most useful for targeted source selection |

## Raw data roots

Raw outputs are written under `data/raw/skyportal/`. They are working artifacts,
not repository content.

| Path | Purpose |
|---|---|
| `data/raw/skyportal/endpoint_audit/` | One directory per endpoint audit run |
| `data/raw/skyportal/inventory/` | One directory per `/api/sources` inventory run |
| `data/raw/skyportal/sources_bundles/` | Reserved for a later source-bundle stage; not produced by the current two scripts |
