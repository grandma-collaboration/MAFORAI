# Telescope Resource Catalog — Data Flow

## Production architecture

The reproducible runtime path is:

```text
ICARE API (only for a deliberate new acquisition)
    |
    v
01_fetch.py
    |
    v
frozen ICARE raw capture
    |
    v
02_flatten.py
    |
    v
shape-only Stage-2 Parquets: telescopes + instruments
    |                                      |
    |                                      |
    +------------------+  +----------------+
                       |  |
                       v  v
             03_build_resource_catalog.py
                       |
                       v
        20-column resource_catalog.parquet
```

The second Stage-3 input has a distinct provenance boundary:

```text
historical/manual/expert research and adjudication
    |  (not fully reproducible from this repository)
    v
data/raw/reference/telescope_external_capabilities.csv
    |  (authoritative curated runtime input)
    +------------------------------> 03_build_resource_catalog.py
```

Only the curated CSV—not the full human curation history—is a runtime dependency. The catalog pipeline is reproducible from the frozen ICARE capture plus that CSV. The boundary is a property of curated reference provenance, not a pipeline failure.

## Stage 1 — ICARE acquisition

[`configs/telescopes/extraction.yaml`](../../configs/telescopes/extraction.yaml) configures [`scripts/telescopes/01_fetch.py`](../../scripts/telescopes/01_fetch.py). A deliberate live acquisition requires `SKYPORTAL_API_TOKEN` and creates a new timestamped raw capture. Neither notebook C nor D calls the API.

The frozen recertified capture is `data/raw/telescopes/icare/capture_20260808_071334/` (ICARE API version `1.4.0`):

| Resource | Endpoint | Rows |
| --- | --- | ---: |
| Telescopes | `/telescope` | 89 |
| Instruments | `/instrument` | 95 |
| Allocations | `/allocation` | 38 |
| Observations | `/observation` | 93 |

The capture includes raw responses, `manifest.json`, and `fetch.log`. Once selected, it is immutable downstream input.

## Stage 2 — Shape-only flattening

[`scripts/telescopes/02_flatten.py`](../../scripts/telescopes/02_flatten.py) converts the selected raw response shapes into ZSTD Parquet tables under `data/interim/telescopes/capture_20260808_071334/`:

| Output | Rows |
| --- | ---: |
| `telescopes.parquet` | 89 |
| `instruments.parquet` | 95 |
| `allocations.parquet` | 38 |
| `observations.parquet` | 93 |

Stage 2 adds stable tabular shape and capture lineage. It does not apply catalog-policy decisions. Stage 3 consumes only `telescopes.parquet` and `instruments.parquet`; allocations and observations remain outside the static catalog.

## Decisions and authority

- [`notebooks/telescopes/A_eda.ipynb`](../../notebooks/telescopes/A_eda.ipynb) is descriptive ICARE evidence.
- [`notebooks/telescopes/B_decisions.ipynb`](../../notebooks/telescopes/B_decisions.ipynb) records the closed construction decisions.
- Neither notebook is a producer runtime input.

ICARE controls catalog membership, relationships, and native fields. The curated CSV enriches matched ICARE resources with accepted external metadata. Explicit native ICARE sensitivity metadata takes precedence over a conflicting external Mlim tuple. Historical observations do not supply nominal Mlim, and allocations do not supply resource capability.

## Stage 3 — Catalog construction and safe publication

[`scripts/telescopes/03_build_resource_catalog.py`](../../scripts/telescopes/03_build_resource_catalog.py) reads exactly:

- the selected Stage-2 telescope table;
- the selected Stage-2 instrument table; and
- [`data/raw/reference/telescope_external_capabilities.csv`](../../data/raw/reference/telescope_external_capabilities.csv).

The producer associates instruments with telescopes, then performs an ICARE-left enrichment from the curated input. Matching uses outer-whitespace stripping plus Unicode-aware case folding, with no fuzzy matching. The curated input has 89 unique rows: 88 exact name matches, all 89 after minimal normalization, and zero unmatched. Six ICARE-only instruments remain, yielding 95 rows.

The producer completed 36/36 checks. Publication order is deliberately fail-safe:

```text
build candidate in memory
    |
    v
validate candidate in memory
    |
    v
write temporary ZSTD Parquet beside the target
    |
    v
read back and validate the temporary candidate
    |
    v
atomically publish validated candidate
```

A failed in-memory or read-back validation cannot replace the official output. The frozen artifact has 95 rows, 20 columns, ZSTD compression, and SHA-256 `af2fc49fccb7346c77182c8a54ded954f56e4c27a65c1dfafa8582a60ebec164`.

The 20 output columns retain native `telescope_diameter` and `instrument_band` alongside identity, coordinates, type, filters, Mlim tuple/status/source, usage classification, targeted-optical suitability, restrictions, and provenance.

## C — Independent persisted-data verification

[`notebooks/telescopes/C_normalisation.ipynb`](../../notebooks/telescopes/C_normalisation.ipynb) reads the authoritative ICARE telescope/instrument tables, curated CSV, and persisted final artifact directly. It does not import the producer. It independently reconstructs all 20 columns and checks native-field preservation, corrected Mlim and suitability semantics, schema, provenance/context, values, and source/final hashes.

Result: **32/32 PASS, 0 FAIL, zero execution errors, and zero full-value mismatches**.

This establishes correctness of the persisted transformation relative to the current authoritative inputs. It does not independently prove that every expert-curated capability is scientifically true.

## D — Isolated deterministic regeneration

[`notebooks/telescopes/D_reproducibility.ipynb`](../../notebooks/telescopes/D_reproducibility.ipynb) starts from the frozen raw capture and authoritative curated CSV:

```text
frozen raw capture
    |
    v
actual 02_flatten.py -> isolated Stage-2 Parquets
    |
    v
actual 03_build_resource_catalog.py + curated CSV
    |
    v
isolated final Parquet
```

D never calls the live API, never runs C, never uses official interim tables as producer inputs, and never uses the official final as producer input. It compares only after regeneration and removes its temporary directory on success.

Result: **32/32 PASS and zero execution errors**. All four regenerated Stage-2 artifacts are semantically and byte identical to the official interim artifacts. The regenerated 20-column final is schema-, dtype-, order-, null-position-, value-, and byte-identical to the official artifact, with the same SHA-256 `af2fc49fccb7346c77182c8a54ded954f56e4c27a65c1dfafa8582a60ebec164`.

D demonstrates deterministic isolated regeneration from the frozen inputs. It does not reproduce the upstream expert-curation history or equate reproducibility with scientific correctness.

## Persistent artifacts

| Role | Path |
| --- | --- |
| Acquisition configuration | `configs/telescopes/extraction.yaml` |
| Acquisition | `scripts/telescopes/01_fetch.py` |
| Flattening | `scripts/telescopes/02_flatten.py` |
| Construction and safe publication | `scripts/telescopes/03_build_resource_catalog.py` |
| Frozen ICARE evidence | `data/raw/telescopes/icare/capture_20260808_071334/` |
| Shape-only interim tables | `data/interim/telescopes/capture_20260808_071334/` |
| Authoritative curated capabilities | `data/raw/reference/telescope_external_capabilities.csv` |
| Descriptive evidence / closed decisions | `notebooks/telescopes/A_eda.ipynb`, `notebooks/telescopes/B_decisions.ipynb` |
| Independent verification | `notebooks/telescopes/C_normalisation.ipynb` |
| Isolated reproducibility | `notebooks/telescopes/D_reproducibility.ipynb` |
| Frozen final catalog | `data/telescope_catalog/resource_catalog.parquet` |
| Final documentation | `docs/telescope_catalog/DATASET_CARD.md`, `docs/telescope_catalog/FLOW.md` |

## Excluded future work

Future consumers may combine the catalog with event data and live state for observability, sensitivity/detectability analysis, availability, scheduling, ranking, or ML/LLM-assisted follow-up. None of those functions is part of catalog construction, schema, validation, or present behavior.
