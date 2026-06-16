# GCN Workflow Documentation

This folder documents the current, reproducible GCN workflow used in this
repository.

It starts from the compact SkyPortal-side event universe:

```text
data/samples/gcn_grandma.json
```

and covers the full GCN side:

1. raw Circular archive download;
2. normalized yearly indexing;
3. event-to-Circular matching;
4. claim extraction from matched Circular bodies;
5. event-level enrichment comparison against the compact SkyPortal metadata.

## How this fits with the rest of the project

The GCN workflow is downstream from the SkyPortal workflow.

Current handoff:

```text
SkyPortal inventories -> gcn_grandma.json -> GCN matching -> claim extraction -> enrichment comparison
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

## Suggested reading order

1. [01_circulars_archive.md](./01_circulars_archive.md)
2. [02_event_matching.md](./02_event_matching.md)
3. [03_claim_extraction.md](./03_claim_extraction.md)
4. [04_event_enrichment.md](./04_event_enrichment.md)

## Code layout

| Layer | Purpose |
|---|---|
| `scripts/gcn/` | Thin CLI entrypoints for each GCN step |
| `src/skyportal_corpus/extraction/gcn_circulars_archive.py` | Raw archive download logic |
| `src/skyportal_corpus/extraction/gcn_circulars_index.py` | Normalized Circular index builder |
| `src/skyportal_corpus/extraction/gcn_event_matching.py` | Step-A matching and summary logic |
| `src/skyportal_corpus/extraction/gcn_core_claims.py` | Step-B body-claim extraction and claim summary logic |
| `src/skyportal_corpus/extraction/gcn_event_enrichment.py` | Step-C event-level best-claims and comparison logic |

## Local output roots

The GCN workflow writes to these main roots:

| Path | Purpose |
|---|---|
| `data/raw/gcn/circulars/archive_json/` | One directory per raw archive download run |
| `data/interim/gcn/circulars/` | Year-partitioned normalized Circular indexes plus shared logs/reports |
| `data/interim/gcn/event_matching/` | Step-A matching outputs |
| `data/interim/gcn/event_extraction/` | Step-B claim extraction outputs |
| `data/interim/gcn/event_enrichment/` | Step-C event-level enrichment outputs |

## Current default assumptions

Unless overridden from the CLI, the active workflow currently assumes:

- the SkyPortal-side event universe is `data/samples/gcn_grandma.json`;
- the matching stage uses GCN Circular years `2023` through `2026`;
- extraction and enrichment work only on the subset of events that already got
  a GCN match in Step A.
