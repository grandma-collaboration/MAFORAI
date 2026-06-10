# Design Decisions

## 1. Audit first, design later

We started by auditing the API instead of jumping directly to a final corpus
schema.

The reason is straightforward: SkyPortal exposes several different data
families, and the schema should be shaped by what is actually accessible and
useful, not by assumptions made too early.

Current consequence:

- the first phase focuses on endpoint coverage, raw inventories, and source
  selection;

## 2. Keep raw responses before normalizing

For now, the workflow saves raw API responses rather than immediately
flattening them into a final tabular or canonical format.

That choice preserves nested structures, metadata, and optional fields while we
are still learning what matters.

Current consequence:

- audit runs and inventory runs are stored separately under
  `data/raw/skyportal/`;

## 3. Use `/api/sources` as the inventory layer

The current extraction strategy uses `GET /api/sources` as the main entry point
for discovering and filtering sources.

This endpoint already gives us a practical way to build targeted subsets:
spectra, follow-up, classifications, redshift, multiple detections, GCN-like
IDs, and EP-like IDs.

Current consequence:

- inventories are built first;
- deeper extraction comes only after a subset of sources has been selected.

## 4. Combine the source root object with specialized endpoints

The audit showed that `GET /api/sources/{source_id}` is rich, but not complete
for every modality.

In practice, a later source-bundle stage will still need specialized endpoints
for at least:

- photometry;
- spectra;
- comments;
- classifications;
- GCN-related context.

Current consequence:

- the root source object is the hub;
- specialized endpoints remain part of the design.

## 5. Keep runtime configuration shared, but keep secrets out of it

The current workflow now uses a shared config file at
`configs/extraction/skyportal.yaml`.

That file is meant for stable runtime settings such as base URL, output paths,
HTTP defaults, and named inventory profiles.

Current consequence:

- the scripts no longer need to repeat the same defaults;
- inventory recipes can be run by profile name;

## 6. Build the current selection from one enriched GRANDMA inventory

The current selection workflow now starts from the enriched
`grandma_base` inventory.

That inventory keeps the scope broad:

- membership in the `GRANDMA` group;
- comment enrichment;
- compact detection statistics;
- host enrichment when available.

Current consequence:

- the current base list is broad enough to keep GCN-derived events even when
  they do not pass a follow-up or detection-count filter.

## 7. Treat all GCN-derived IDs as one source family

For the current workflow, `GCN-*`, `GRB-*`, `GW-*`, and `EP-*` are treated as
coming from the same GCN ingestion path.

Current consequence:

- the first derived list is `gcn_grandma`;
- the final `selected_sources_for_bundles.json` keeps all GCN-derived subtypes
  in the same prioritized pool instead of splitting them into separate
  selection families.

## 8. Keep the first prioritized list explainable

The current prioritized list uses simple signals that are already available in
the enriched inventory:

- redshift;
- comments;
- compact detection counts;
- compact classification labels.

Priority is still assigned with explicit rules rather than a complex model:

- `high` for extreme redshift cases, or strong combined evidence;
- `medium` for events with useful scientific or operational support;
- `low` for the remaining GCN-derived events.

Current consequence:

- every event can be traced back to a small set of explicit reasons.

## 9. Use a small set of ranking signals, and keep each one interpretable

The first prioritized list uses a compact set of signals already available in the enriched
inventory:

- `redshift`;
- `comment_exists`;
- `num_det_global`;
- selected `classification_labels`.

Each signal was kept for a specific reason:

- `redshift` is the strongest compact science signal currently available at
  inventory level;
- `comment_exists` is a cheap proxy for human attention and discussion;
- `num_det_global` is a cheap proxy for photometric richness;
- selected labels such as `GRB`, `GO GRANDMA`, and
  `GO GRANDMA (HIGH PRIORITY)` preserve compact operational or scientific
  support without forcing full downstream parsing.

Current consequence:

- the ranking can be explained field by field;
- changing the ranking later is straightforward because every signal has an
  explicit role.