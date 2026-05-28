# Design Decisions

## Decision 001 — Audit before corpus design

We decided to audit the API and data availability before defining the corpus schema.

### Motivation

The SkyPortal API exposes many heterogeneous data families. Designing the corpus too early could lead to missing important modalities or overfitting the schema to a small subset of sources.

### Consequence

The first phase focuses on raw extraction, endpoint availability, filtered inventories and source selection.

---

## Decision 002 — Preserve raw JSON responses

We decided to save raw API responses instead of immediately normalizing them.

### Motivation

Raw JSON preserves nested structures, metadata and fields that may later become important.

### Consequence

Normalization and feature engineering will be done only after inspecting the raw
data. Raw outputs are stored per run under `data/raw/skyportal/`, which keeps
audit runs and source inventories separated and reproducible. These outputs are
treated as local artifacts rather than repository content.

---

## Decision 003 — Use `/api/sources` as a targeted inventory endpoint

The documentation shows that `/api/sources` supports filters such as `hasSpectrum`, `hasFollowupRequest`, `classified`, `minRedshift`, `numberDetections`, `sourceID`, and optional include flags.

### Motivation

The API contains a large source catalog. Downloading everything is unnecessary
for the first audit phase. Filtered inventories allow us to build small,
meaningful subsets.

### Consequence

We created complete filtered inventories for spectra, follow-up,
classifications, redshift, multiple detections, GCN-like sources and EP-like
sources in local runs under `data/raw/skyportal/inventory/source_inventory_*`.

---

## Decision 004 — Use specialized endpoints when source root data is incomplete

`/api/sources/{source_id}` is a rich root object, but the audit showed that some modalities, such as full photometry and comments, require specialized endpoints.

### Consequence

The future source-bundle extractor will combine the root source endpoint with specialized source-level endpoints.
