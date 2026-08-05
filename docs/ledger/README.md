# Ledger

For whom: anyone starting on the event ledger who needs to know which document to read,
which script produces which table, and where the evidence for a design decision lives.

The ledger is a single store of dated facts about transient events, built from SkyPortal
and the GCN circular corpus, designed so the state of an event at any past time can be
reconstructed without temporal leakage.

## Documents

- [00_construction.md](./00_construction.md) — where the data came from, what was measured,
  and why the ledger is shaped the way it is. **Start here.**
- [01_schema_v1.md](./01_schema_v1.md) — column-level specification of the tables, the
  enumerations, and the query patterns.

## Evidence

Design decisions are justified by six notebooks, each starting from raw data and answering one question.

| Notebook | Question | Evidence file |
|---|---|---|
| [01_corpus_structure](../../notebooks/01_corpus_structure.ipynb) | What is in the corpus? | `01_source_index.csv`, `01_field_coverage.csv` |
| [02_temporal_anchor](../../notebooks/02_temporal_anchor.ipynb) | When did each event occur (`t0`)? | `01_source_index.csv` |
| [03_knowledge_time](../../notebooks/03_knowledge_time.ipynb) | Does SkyPortal record when it knew? | — |
| [04_two_speeds](../../notebooks/04_two_speeds.ipynb) | How fast does each channel deliver? | `04_photometry_lag.csv` |
| [04b_two_speeds_audits](../../notebooks/04b_two_speeds_audits.ipynb) | Supporting checks for 04 | — |
| [05_photometry_reconciliation](../../notebooks/05_photometry_reconciliation.ipynb) | Is it the same measurement on both sides? | `05_photometry_pairs.csv` |
| [06_ledger_construction](../../notebooks/06_ledger_construction.ipynb) | Is the ledger reproducible from raw data? | `06_regeneration_check.csv` |

Evidence CSVs are under [`notebooks/evidence/`](../../notebooks/evidence/).

## Tables

All under `data/ledger/`, Parquet, queried with DuckDB.

| Table | Path | Produced by | Rows |
|---|---|---|---:|
| `facts` (SkyPortal) | `facts/source_system=skyportal/` | `scripts/10_emit_skyportal_source_facts.py` | 1,776 |
| `facts` (GCN) | `facts/source_system=gcn/year=<YYYY>/` | `scripts/13_emit_gcn_facts.py` | 101,072 |
| `events` | `events/events.parquet` | `scripts/10_emit_skyportal_source_facts.py` | 800 |
| `event_container_map` (SkyPortal) | `event_container_map/map.parquet` | `scripts/10_emit_skyportal_source_facts.py` | 800 |
| `event_container_map` (GCN) | `event_container_map/gcn_map.parquet` | `scripts/14_emit_event_circular_map.py` | 2,335 |
| `state_snapshots` | `state_snapshots/window=<W>/` | `scripts/15_emit_state_snapshots.py` | 106 / 114 / 116 |
| `state_index` | `state_index/window=<W>/` | `scripts/16_build_state_index.py` | same, plus `.npy` vectors |

The two `facts` sources share one schema and concatenate with DuckDB `union_by_name`; the
only GCN-extra column is `t_occurred_offset_hours`. The two map files share identical
columns and are read together.

State windows are `6h`, `24h` and `7d`. Index vectors are `float32`, 1024 dimensions
(BGE-M3).

## Build order

| # | Script | Purpose | Network |
|---|---|---|---|
| 1 | `11_fetch_source_detail.py` | Download per-source detail: comments, photometry, spectra, follow-up requests. Resumable. | yes, needs a SkyPortal token |
| 2 | `12_audit_source_detail.py` | Audit the downloaded detail before emitting. | no |
| 3 | `10_emit_skyportal_source_facts.py` | Emit `events` and SkyPortal source facts from the frozen listing. | no |
| 4 | `13_emit_gcn_facts.py` | Emit GCN facts by calling the validated extractors over the 2023-onward circulars. | no |
| 5 | `14_emit_event_circular_map.py` | Emit the GCN event↔circular map. | no |
| 6 | `15_emit_state_snapshots.py` | Emit state snapshots for the three windows. | no |
| 7 | `16_build_state_index.py` | Embed snapshots into the retrieval index. | no |
| 8 | `17_retrieval_backtest.py` | Leave-one-out retrieval backtest. | no |

Steps 1–5 build the ledger. Steps 6–8 build the state and retrieval layer on top of it.