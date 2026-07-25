# Ledger

For whom: anyone starting on the event ledger who needs to know which document to read
and which script produces which table.

The ledger is a single store of dated facts about transient events, built from SkyPortal
and the GCN circular corpus, designed so the state of an event at any past time can be
reconstructed without temporal leakage.

## Documents

- [00_construction.md](./00_construction.md) — why the ledger exists and how it was
  built. Start here for the reasoning.
- [01_schema_v1.md](./01_schema_v1.md) — the column-level specification of the three
  tables, the enumerations, and the query patterns.

Evidence for the design decisions lives in
[../../notebooks/01_skyportal_inventory_coverage.ipynb](../../notebooks/01_skyportal_inventory_coverage.ipynb),
referenced from both documents as `NB01 §x`.

## Tables

All under `data/ledger/`, Parquet, queried with DuckDB.

| table | path | produced by |
|---|---|---|
| `facts` (SkyPortal) | `facts/source_system=skyportal/` | `scripts/10_emit_skyportal_source_facts.py` |
| `facts` (GCN) | `facts/source_system=gcn/year=<YYYY>/` | `scripts/13_emit_gcn_facts.py` |
| `events` | `events/events.parquet` | `scripts/10_emit_skyportal_source_facts.py` |
| `event_container_map` (SkyPortal) | `event_container_map/map.parquet` | `scripts/10_emit_skyportal_source_facts.py` |
| `event_container_map` (GCN) | `event_container_map/gcn_map.parquet` | `scripts/14_emit_event_circular_map.py` |

The two `facts` sources share one schema and concatenate with DuckDB `union_by_name`;
the only GCN-extra column is `t_occurred_offset_hours`. The two map files share identical
columns and are read together.

## Build order

1. `scripts/11_fetch_source_detail.py` — download per-source detail (comments,
   photometry, spectra, follow-up requests). Requires network and a SkyPortal token.
2. `scripts/10_emit_skyportal_source_facts.py` — emit `events` and SkyPortal source
   facts from the frozen listing. No network.
3. `scripts/13_emit_gcn_facts.py` — emit GCN facts from the circular corpus. No network.
4. `scripts/14_emit_event_circular_map.py` — emit the GCN event↔circular map. No network.

## Known Limitations

See the Known Limitations section of [00_construction.md](./00_construction.md).
