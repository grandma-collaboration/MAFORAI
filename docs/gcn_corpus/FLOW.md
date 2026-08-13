# GCN Corpus Pipeline

This document traces GCN circulars from the archive-derived circular index to the final corpus tables. See [the dataset card](DATASET_CARD.md) for the corpus contents and the notebooks listed under Evidence for the measurements behind each corpus decision.

## Overview

```text
GCN circular archive
     |  01_extract.py — runs 15 extractors
     v
data/interim/gcn_corpus/          three tables + manifest, no decisions
     |  02_normalise.py
     v
data/gcn_corpus/                  four tables + manifest, 13 decisions
```

## Stage 1 — Extraction

`scripts/gcn_corpus/01_extract.py` iterates over the archive-derived circular index from 2023 onward, renders each circular with `render_canonical`, runs the active evidence and photometry extractors, verifies every offset, and emits one row per annotation. It makes no cleaning or corpus-normalization decision: the interim output remains the faithful comparison point for what the rules emitted.

### Extractors

The layer, rule ownership, and output below are measured from the interim span tables. Extractor versions come from those rows and agree with the interim manifest.

| `extractor_id` | Version | Layer | Rules owned | Annotations produced |
|---|---|---|---:|---:|
| `classification-interpretation-v1` | `0.1` | `EVENT_EVIDENCE` | 10 | 2,061 |
| `counterpart-association-v1` | `0.1` | `EVENT_EVIDENCE` | 8 | 3,070 |
| `duration-v1` | `0.1` | `EVENT_EVIDENCE` | 6 | 2,502 |
| `event-identity-v1` | `0.1` | `EVENT_EVIDENCE` | 10 | 27,820 |
| `high-energy-v1` | `0.1` | `EVENT_EVIDENCE` | 9 | 5,973 |
| `host-context-v1` | `0.1` | `EVENT_EVIDENCE` | 5 | 463 |
| `lightcurve-evolution-v1` | `0.1` | `EVENT_EVIDENCE` | 5 | 2,708 |
| `localization-v1` | `0.1` | `EVENT_EVIDENCE` | 4 | 4,912 |
| `negative-statement-v1` | `0.1` | `EVENT_EVIDENCE` | 17 | 978 |
| `redshift-v1` | `0.1` | `EVENT_EVIDENCE` | 4 | 960 |
| `spectroscopy-v1` | `0.1` | `EVENT_EVIDENCE` | 3 | 831 |
| `trigger-instrument-v1` | `0.1` | `EVENT_EVIDENCE` | 16 | 6,974 |
| `trigger-time-v1` | `0.1` | `EVENT_EVIDENCE` | 6 | 4,025 |
| `photometry-prose-v1` | `0.1` | `PHOTOMETRIC_MEASUREMENT` | 7 | 4,263 |
| `photometry-row-v1` | `0.1` | `PHOTOMETRIC_MEASUREMENT` | 3 | 33,532 |

Together these 15 extractors own 113 distinct rules.

### Interim Artifacts

| Table | Rows | Columns |
|---|---:|---:|
| `circulars.parquet` | 12,012 | 11 |
| `evidence_spans.parquet` | 63,277 | 20 |
| `photometry_spans.parquet` | 37,795 | 30 |

The fixed scope is `min_year=2023`. It contains 12,012 circulars published from 2023-01-01 through 2026-07-19. The full archive-wide circular count is not recorded in either permitted manifest or table, so it is not asserted here.

Stage 1 establishes the invariant `canonical_text[span_start:span_end] == text`. It verified all 101,072 emitted annotations with zero failures.

## Stage 2 — Normalisation

`scripts/gcn_corpus/02_normalise.py` applies the 13 decisions recorded in the final cell of `notebooks/gcn_corpus/A_eda.ipynb`. The script implements one function per decision, from `d01_verify_span_key` through `d13_write_manifest`, and each function reports the rows and columns it affects. It does not rerun an extractor.

| Table | Interim rows | Corpus rows | Columns dropped | Columns added |
|---|---:|---:|---|---|
| `circulars.parquet` | 12,012 | 12,012 | None | `has_annotations`, `has_mojibake`, `n_evidence`, `n_photometry` |
| `evidence_spans.parquet` | 63,277 | 63,277 | `source_circular_id` | `has_mojibake`, `is_overlapping` |
| `photometry_spans.parquet` | 37,795 | 37,795 | None | `exposure_time_numeric`, `has_mojibake`, `is_overlapping` |
| `vocabulary_coverage.parquet` | Not present | 57 | None | `layer`, `field`, `declared_value`, `rows` |

`vocabulary_coverage.parquet` materializes the model declarations instead of describing them only in prose. Its 57 rows cover every declared value across seven controlled-vocabulary fields, including 17 values carried by no annotation, so rule coverage can be measured against the schema in each generation.

## Stage 3 — The Corpus

| Table | Rows | Columns |
|---|---:|---:|
| `circulars.parquet` | 12,012 | 15 |
| `evidence_spans.parquet` | 63,277 | 21 |
| `photometry_spans.parquet` | 37,795 | 33 |
| `vocabulary_coverage.parquet` | 57 | 4 |

The corpus contains 101,072 annotations: 63,277 in `EVENT_EVIDENCE` and 37,795 in `PHOTOMETRIC_MEASUREMENT`. Its circular date range is 2023-01-01 through 2026-07-19. The generation is identified by content hash `f004042629952c9fded14183943663392180f124a591e99a88243fa6e59ae9f3`.

The tables support auditing an extracted value against the exact text that produced it and comparing generations through rule inventories and content hashes. Filtering on `created_on_utc` reconstructs which retained circular records had become public by a past instant; because edited bodies are not versioned here, it does not reconstruct the original pre-edit wording of an edited circular.

## Evidence

| Question | Where it is answered |
|---|---|
| What do the extracted tables contain? | [`notebooks/gcn_corpus/A_eda.ipynb`](../../notebooks/gcn_corpus/A_eda.ipynb) |
| Which decisions were taken, and why? | [`notebooks/gcn_corpus/B_decisions.ipynb`](../../notebooks/gcn_corpus/B_decisions.ipynb) |
| What did each decision change? | [`notebooks/gcn_corpus/C_normalisation.ipynb`](../../notebooks/gcn_corpus/C_normalisation.ipynb) |
| Is the corpus reproducible? | [`notebooks/gcn_corpus/D_reproducibility.ipynb`](../../notebooks/gcn_corpus/D_reproducibility.ipynb) |
| What does the corpus contain? | [`docs/gcn_corpus/DATASET_CARD.md`](DATASET_CARD.md) |

## Relation to the Other Corpora

`data/corpus_skyportal/` holds records from the SkyPortal platform. `data/gcn_gold_corpus/` holds human validation for 10 event documents drawn from these annotations; its tables do not encode the number of constituent circulars, which is documented with that corpus instead. This corpus depends on neither: its perimeter is the circular archive alone.

## Running the Pipeline

Neither script defines command-line arguments. The GCN circular archive and its archive-derived indexes under `data/interim/gcn/circulars/<year>/circulars_index.parquet` must already exist; these two stages do not download or index the circular archive.

Run the stages in order from the repository root:

```bash
/home/meneses/project_astronomical/MAFORAI/.venv/bin/python /home/meneses/project_astronomical/MAFORAI/scripts/gcn_corpus/01_extract.py
/home/meneses/project_astronomical/MAFORAI/.venv/bin/python /home/meneses/project_astronomical/MAFORAI/scripts/gcn_corpus/02_normalise.py
```

Stage 1 runs the extractors; Stage 2 only transforms and verifies their persisted output. Neither manifest stores elapsed runtime, and the extractors were not rerun for this document, so no stage runtime is asserted.
