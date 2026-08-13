# Telescope Resource Catalog

## Overview

The Telescope Resource Catalog is a curated, normalized inventory of telescope and instrument resources represented in ICARE. One row represents one ICARE instrument associated with one ICARE telescope. ICARE defines the canonical resource universe, so an instrument remains in the catalog even when it has no row in the curated external capability input.

The catalog combines native ICARE resource metadata with selected static or semi-static capability metadata. It describes neither live resource state nor event-specific observing feasibility.

## Intended use and scope

The artifact provides stable resource metadata for downstream consumers. It includes:

- canonical telescope/instrument identities and relationships;
- native coordinates, telescope diameter, instrument type, broad band, and filters;
- accepted representative limiting-magnitude metadata and retained context;
- retained external usage/status classifications; and
- static suitability and restrictions for targeted optical photometric/imaging follow-up.

It does not implement event observability or detectability, live availability, weather, queue state, scheduling, ranking, or ML/LLM outputs. FoV is intentionally excluded from this catalog version; that scope choice is not a statement about its scientific relevance.

## Authoritative inputs and curation boundary

The catalog has two authoritative runtime inputs:

1. The frozen ICARE capture, flattened into native telescope and instrument tables. ICARE is authoritative for row membership, identity, relationships, and selected native fields.
2. [`data/raw/reference/telescope_external_capabilities.csv`](../../data/raw/reference/telescope_external_capabilities.csv), the authoritative curated input for the retained external capability, restriction, and provenance fields.

The executable pipeline is reproducible from the frozen ICARE capture plus the curated external CSV. The upstream human/expert research and adjudication that produced every value in that CSV is not fully reproducible from the current repository. This is the provenance boundary of the curated reference input, not a failure of the catalog pipeline. Earlier research material is neither restored nor used at runtime.

Native ICARE values take precedence for native catalog fields. For limiting-magnitude metadata, an explicit native ICARE sensitivity tuple takes precedence over a conflicting external tuple, as for TAROT/TRE. The external CSV otherwise supplies accepted curated values. Historical observations and allocations are not final-catalog inputs.

## Frozen artifact

| Property | Value |
| --- | --- |
| Path | `data/telescope_catalog/resource_catalog.parquet` |
| Format | Apache Parquet |
| Compression | ZSTD |
| Rows | 95 |
| Columns | 20 |
| SHA-256 | `af2fc49fccb7346c77182c8a54ded954f56e4c27a65c1dfafa8582a60ebec164` |

The artifact contains 95 unique ICARE instrument identifiers and 95 unique telescope/instrument pairs.

## Schema

These are the 20 Arrow fields persisted in the Parquet artifact, in order.

| Column | Arrow type | Authority | Description |
| --- | --- | --- | --- |
| `telescope_id` | `int64` | ICARE | Canonical ICARE telescope identifier. |
| `telescope_name` | `string` | ICARE | Native ICARE telescope name, with only documented outer-whitespace handling. |
| `latitude` | `double` | ICARE | Native telescope latitude; null when ICARE omits it. |
| `longitude` | `double` | ICARE | Native telescope longitude; null when ICARE omits it. |
| `elevation` | `double` | ICARE | Native telescope elevation; null when ICARE omits it. |
| `telescope_diameter` | `double` | ICARE | Native ICARE telescope diameter/aperture field, propagated without scientific normalization. |
| `instrument_id` | `int64` | ICARE | Canonical ICARE instrument identifier and row-level resource key. |
| `instrument_name` | `string` | ICARE | Native ICARE instrument name, with only documented outer-whitespace handling. |
| `instrument_type` | `string` | ICARE | Native ICARE instrument type. |
| `instrument_band` | `string` | ICARE | Native ICARE broad instrument band; semantics and casing are preserved. |
| `filters` | `string` | ICARE | Native ICARE instrument-filter list serialized as a string; distinct from `mlim_filter`. |
| `mlim_mag` | `double` | curated external / ICARE native tuple | Accepted representative limiting-magnitude/depth value, or null when no accepted nominal value is retained. |
| `mlim_filter` | `string` | curated external / ICARE native tuple | Available band/filter context associated specifically with `mlim_mag`. |
| `mlim_exposure` | `string` | curated external / ICARE native tuple | Available exposure context associated specifically with `mlim_mag`. |
| `mlim_status` | `string` | derived | `KNOWN` when `mlim_mag` is numeric; otherwise `UNKNOWN`. |
| `mlim_source` | `string` | curated external / ICARE native tuple | Concise source category or attribution for retained Mlim metadata. |
| `usage_class` | `string` | curated external | Retained external usage/status classification, when present. |
| `followup_eligible` | `bool` | curated external / derived | Static suitability for targeted optical photometric/imaging follow-up. |
| `restriction_note` | `string` | curated external / derived | Static restriction, scope explanation, or clearly historical operational context, when present. |
| `provenance_note` | `string` | curated external / ICARE native tuple | Concise context for the retained curated or native capability value. |

Both newly retained native fields are complete: `telescope_diameter` is populated for 95/95 rows and `instrument_band` for 95/95 rows.

## Limiting-magnitude semantics

`mlim_mag` is an accepted representative limiting-magnitude/depth value. It is not a full sensitivity model, guaranteed performance under every observing condition, or an implemented detectability threshold. The tuple (`mlim_mag`, `mlim_filter`, `mlim_exposure`) preserves available context where supported; absence of filter or exposure context must not be filled by inference.

- `KNOWN`: a numeric accepted representative value is retained — 77 rows.
- `UNKNOWN`: no accepted nominal value is retained — 18 rows.

`UNKNOWN` does not mean that the instrument cannot detect a source. Some network/group representative values remain in the catalog. Their provenance marks them as representative, and they must not be interpreted as instrument-specific measurements. Explicit native metadata is retained where applicable; TAROT/TRE, for example, uses the native ICARE tuple `18`, `ps1::open`, `30 s`.

## Follow-up suitability

`followup_eligible` means exactly: **static suitability for targeted optical photometric/imaging follow-up**. The artifact has 83 eligible and 12 ineligible rows.

`False` can encode stable properties such as spectroscopy-only scope, high-energy/X-ray-only scope, a generic or non-physical aggregate, or a non-repointable survey. It does not encode current availability, current operational state, weather, queue state, event observability, or event detectability. A clearly historical operational statement may be retained in `restriction_note`, but it does not determine the boolean.

The six ICARE-only instruments are retained. Their suitability is derived only from documented native type/band scope rules; missing external data is not itself an ineligibility rule.

## Usage classification

`usage_class` preserves the controlled values present in the curated external input: `F`, `O`, `R`, `VF`, `VR`, and `nOP`. It is sparsely populated, with 53 null rows. The catalog retains these values literally as external usage/status classifications where available and does not assign broader semantics beyond the curated source.

## Missingness and provenance

Parquet nulls represent absence; the producer does not fabricate capability values. Nine rows lack each coordinate/elevation field, 18 lack `mlim_mag`, and 53 lack `usage_class`. All 89 curated external rows match ICARE resources after documented minimal normalization; 88 match exactly. Six additional ICARE instruments have no external row and remain because ICARE defines membership.

`mlim_source` and `provenance_note` preserve concise row-level context. This is intentionally a bounded provenance model. In particular, representative network/group values are labeled as such, but the repository does not reconstruct the full expert-curation history behind the authoritative CSV.

## Validation and recertification

Construction, independent verification, and reproducibility have distinct scopes:

- [`scripts/telescopes/03_build_resource_catalog.py`](../../scripts/telescopes/03_build_resource_catalog.py) completed 36/36 producer checks. It validates the in-memory candidate, writes a temporary ZSTD Parquet, validates the read-back, and atomically publishes only a validated candidate.
- [`notebooks/telescopes/C_normalisation.ipynb`](../../notebooks/telescopes/C_normalisation.ipynb) completed 32/32 checks with zero execution errors. It independently reconstructs and compares all 20 columns against the current authoritative inputs without importing producer code: zero full-value mismatches. This is implementation-level and value-level verification of the persisted transformation; it does not prove the scientific truth of every expert-curated value.
- [`notebooks/telescopes/D_reproducibility.ipynb`](../../notebooks/telescopes/D_reproducibility.ipynb) completed 32/32 checks with zero execution errors. From the frozen raw ICARE capture and curated external CSV, it ran the real Stage 2 and Stage 3 in isolation. All four Stage-2 outputs were semantically and byte identical, and the final catalog was byte identical with the official SHA-256. Deterministic regeneration does not establish scientific correctness of the curated input.

## Limitations

- Metadata is static or semi-static, not live state.
- Accepted nominal Mlim metadata is absent for 18 resources.
- Mlim values can lack filter/exposure context and cannot substitute for a sensitivity model.
- Static suitability cannot establish whether a resource can observe a particular event.
- The authoritative external CSV has an upstream human-curation provenance boundary.
- Allocations and historical observations remain in the flattened ICARE layer and are not joined here.
- FoV is not represented.
- Future ICARE or curated-reference changes require a deliberate refresh, rebuild, and recertification.

## Regeneration

Run from the repository root with the project virtual environment available. Stage 1 is only for a deliberate new live acquisition and requires `SKYPORTAL_API_TOKEN`:

```bash
.venv/bin/python -B scripts/telescopes/01_fetch.py \
  --config configs/telescopes/extraction.yaml
```

The frozen recertified path begins with Stage 2:

```bash
.venv/bin/python -B scripts/telescopes/02_flatten.py \
  --capture-dir data/raw/telescopes/icare/capture_20260808_071334 \
  --output-dir data/interim/telescopes/capture_20260808_071334

.venv/bin/python -B scripts/telescopes/03_build_resource_catalog.py \
  --input-dir data/interim/telescopes/capture_20260808_071334 \
  --external-capabilities data/raw/reference/telescope_external_capabilities.csv \
  --output-path data/telescope_catalog/resource_catalog.parquet
```

Stage 3 publishes atomically only after candidate and persisted read-back validation. The reproducibility notebook uses temporary output paths and never calls the live API or overwrites the official artifact.
