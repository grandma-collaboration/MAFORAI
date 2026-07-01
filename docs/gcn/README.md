# GCN Workflow Documentation

This folder documents the current, reproducible GCN workflow used in this
repository.

It starts from the compact SkyPortal-side event universe:

```text
data/interim/skyportal/gcn_grandma.json
```

and from the prebuilt SkyPortal baseline used later for comparison:

```text
data/interim/skyportal/skyportal_event_baseline.parquet
```

and covers the full GCN side:

1. raw Circular archive download;
2. normalized yearly indexing;
3. event-to-Circular matching;
4. claim extraction from matched Circular bodies;
5. event-level enrichment comparison against the compact SkyPortal metadata;
6. final event-review table for astronomer validation;
7. curated Excel export for astronomer delivery;
8. blind INCEpTION pilot dossiers built from already matched Circulars.

## How this fits with the rest of the project

The GCN workflow is downstream from the SkyPortal workflow.

Current handoff:

```text
SkyPortal inventories -> gcn_grandma.json -> skyportal_event_baseline -> GCN matching -> claim extraction -> enrichment comparison
```

Companion documentation:

| Area | Entry point |
|---|---|
| SkyPortal-side preparation | [docs/skyportal/README.md](../skyportal/README.md) |
| Project-wide decisions | [docs/decisiones.md](../decisiones.md) |

## Scope

Included here:

| Topic | File |
|---|---|
| Circular archive download and yearly index | [01_circulars_archive.md](./01_circulars_archive.md) |
| Event matching against Circulars | [02_event_matching.md](./02_event_matching.md) |
| Claim extraction from matched Circular bodies | [03_claim_extraction.md](./03_claim_extraction.md) |
| Event-level enrichment candidates and SkyPortal comparison | [04_event_enrichment.md](./04_event_enrichment.md) |
| Final validation table plus curated Excel export | [05_event_review.md](./05_event_review.md) |
| Blind INCEpTION pilot dossiers | [06_inception_dossiers.md](./06_inception_dossiers.md) |

## Suggested reading order

1. [01_circulars_archive.md](./01_circulars_archive.md)
2. [02_event_matching.md](./02_event_matching.md)
3. [03_claim_extraction.md](./03_claim_extraction.md)
4. [04_event_enrichment.md](./04_event_enrichment.md)
5. [05_event_review.md](./05_event_review.md)
6. [06_inception_dossiers.md](./06_inception_dossiers.md)

## Code layout

| Layer | Purpose |
|---|---|
| `scripts/gcn/` | Thin CLI entrypoints for each GCN step |
| `src/skyportal_corpus/extraction/skyportal_event_baseline.py` | SkyPortal-side baseline builder consumed later by GCN comparison and review |
| `src/skyportal_corpus/extraction/gcn_circulars_archive.py` | Raw archive download logic |
| `src/skyportal_corpus/extraction/gcn_circulars_index.py` | Normalized Circular index builder |
| `src/skyportal_corpus/extraction/gcn_event_matching.py` | Step-A matching and summary logic |
| `src/skyportal_corpus/extraction/gcn_core_claims.py` | Step-B body-claim extraction and claim summary logic |
| `src/skyportal_corpus/extraction/gcn_event_enrichment.py` | Step-C event-level best-claims and comparison logic |
| `src/skyportal_corpus/extraction/gcn_event_review.py` | Final field-by-field review table for astronomer validation |
| `src/skyportal_corpus/extraction/gcn_event_review_export.py` | Curated `.xlsx` export built from the review table |
| `src/skyportal_corpus/extraction/gcn_inception_dossiers.py` | Blind plain-text dossier builder for INCEpTION pilot annotation |

## Local output roots

The GCN workflow writes to these main roots:

| Path | Purpose |
|---|---|
| `data/raw/gcn/circulars/archive_json/` | One directory per raw archive download run |
| `data/interim/gcn/circulars/` | Year-partitioned normalized Circular indexes plus shared logs/reports |
| `data/interim/gcn/event_matching/` | Step-A matching outputs |
| `data/interim/gcn/event_extraction/` | Step-B claim extraction outputs |
| `data/interim/gcn/event_enrichment/` | Step-C event-level enrichment outputs |
| `data/interim/gcn/event_validation/` | Final review table for manual scientific validation |
| `data/interim/gcn/event_validation/astronomer_review/` | Curated Excel workbook delivered to astronomers |
| `data/interim/gcn/event_validation/inception_dossiers/` | Plain-text event dossiers ready to upload into INCEpTION |

## Current default assumptions

Unless overridden from the CLI, the active workflow currently assumes:

- the SkyPortal-side event universe is `data/interim/skyportal/gcn_grandma.json`;
- the SkyPortal-side comparison baseline is
  `data/interim/skyportal/skyportal_event_baseline.parquet`;
- the matching stage uses GCN Circular years `2023` through `2026`;
- extraction and enrichment work only on the subset of events that already got
  a GCN match in Step A.
