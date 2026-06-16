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

## 6. Build the current selection from a small inventory union

The current selection workflow now starts from the union of:

- `gcn`
- `grb`
- `ep`
- `grandma_base`

Why this union:

- `gcn`, `grb`, and `ep` are the direct source-ID filtered subsets we want to
  preserve end to end;
- `grandma_base` keeps the broad GRANDMA context and also catches cases where
  the main `id` does not start with `GCN`, `GRB`, `GW`, or `EP`, but one alias
  does.

Current consequence:

- the current base list is no longer tied to one inventory only;
- alias-based GCN-derived events can still enter the selection.

## 7. Treat all GCN-derived IDs as one source family

For the current workflow, `GCN-*`, `GRB-*`, `GW-*`, and `EP-*` are treated as
coming from the same GCN ingestion path.

Current consequence:

- the first derived list is `gcn_grandma`;
- the current workflow treats all those subtypes as one shared event universe
  before any later filtering or ranking step.

## 8. Keep the pre-GCN event layer compact but informative

The current `gcn_grandma.json` base keeps a small set of fields that are
already available in the inventory and are useful later when comparing
SkyPortal against GCN:

- redshift;
- trigger time when exposed as inventory `t0`;
- compact spectrum flag;
- comments;
- compact detection counts;
- compact classification labels.

Current consequence:

- the base list stays easy to inspect by eye;


