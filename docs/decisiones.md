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

## 6. Select source bundles from one clear operational baseline

The current source-selection step starts from one saved inventory:
`grandma_followup_det2_base`.

That baseline was chosen because it already combines the practical conditions
we wanted to preserve for the next stage:

- membership in the `GRANDMA` group;
- at least one follow-up request;
- at least two detections.

Current consequence:

- bundle selection is based on one explicit and reproducible inventory, not on
  a mix of ad hoc subsets;
- the first curated sample favors `GCN*` and `GRB*` sources as `grb_like`
  candidates;
- `EP*` sources are excluded from the initial `non_grb` set to avoid mixing
  ambiguous cases too early.

## 7. Keep the first selection compact and explainable

The first curated selection is intentionally small and easy to review:

- 20 `grb_like` sources;
- 10 `non_grb` sources.

Priority is assigned with simple rules rather than a complex score:

- `high` for extreme redshift cases (`z < 1` or `z > 4`);
- `medium` when redshift is present, or when comments and stronger detection
  coverage suggest a better-documented source;
- `low` for the remaining valid candidates.

Current consequence:

- the selection JSON stays readable and reproducible;
- every chosen source can be justified with explicit criteria instead of opaque
  ranking logic.
