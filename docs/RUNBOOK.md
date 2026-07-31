# Pipeline Rebuild Runbook

For whom: developers who need to clone MAFORAI and regenerate SkyPortal inputs, the GCN corpus, automatic event selections, and event-level INCEpTION documents.

This runbook is the ordered from-zero path. Run every command from the repository root. Generated data is intentionally outside version control, so a fresh clone must rebuild or download every data product listed below.

## Runtime Summary

| Step | Network | SkyPortal token | Expected runtime |
|---|---|---|---|
| Clone and install | Yes | No | Environment-dependent; package installation usually takes minutes. |
| SkyPortal inventories | Yes | Yes | API- and profile-dependent; usually minutes. |
| SkyPortal derived files | No | No | Seconds for the current inventory size. |
| GCN archive download | Yes | No | Network-dependent; the current compressed archive is about 31 MB. |
| GCN Circular index | No | No | Data-dependent; not benchmarked as a stable runtime. |
| Event terms and registry | No | No | Seconds for the current 574-event registry. |
| Identity index | No | No | About 10 seconds for about 12,000 Circulars. |
| Viability sweep | No | No | About 400 seconds for 574 events. |
| One event build | No | No | Event-size-dependent; normally seconds. |
| Full tests | No | No | About 21 seconds for 727 tests on the current development machine. |

## Gitignored Data

| Path | Why it is absent from a fresh clone | Recovery step |
|---|---|---|
| `data/raw/skyportal/inventory/` | Timestamped authenticated API responses. | Step 2 |
| `data/interim/skyportal/` | Derived compact SkyPortal event files. | Step 2 |
| `data/raw/gcn/circulars/archive_json/` | Downloaded public GCN archive. | Step 3 |
| `data/interim/gcn/circulars/` | Normalized yearly Circular indexes. | Step 3 |
| `data/interim/gcn/event_matching/` | Terms, registry, identity index, selections, and viability output. | Steps 4-8 |
| `data/interim/gcn/sweep/` | Extractor sweep and alert reports. | Step 9 |
| `data/inception/out/<source_id>/` | Generated event XMI and manifests. | Step 8 |
`data/inception/TypeSystem.xml` is required for every XMI export and is tracked
through a narrow `.gitignore` exception, so it is present in a fresh clone.

```text
data/inception/TypeSystem.xml
```

## 0. Clone And Install

Python 3.10 or newer is required. `pydantic>=2` and `dkpro-cassis` are declared runtime dependencies.

```bash
git clone https://github.com/grandma-collaboration/MAFORAI.git MAFORAI
cd MAFORAI
python -m venv .venv
.venv/bin/pip install -e .
```

For the test dependency, install the development extra instead of, or after, the base editable install:

```bash
.venv/bin/pip install -e ".[dev]"
```

Success means `.venv/bin/python` imports `skyportal_corpus`, `pydantic`, and `cassis`.

## 1. Configure Credentials

SkyPortal access is needed only for Step 2. Create the local environment file from the tracked example:

```bash
cp .env.example .env
```

Set:

```text
SKYPORTAL_API_TOKEN="<your-token>"
```

The shared endpoint and token-variable name are defined in `configs/extraction/skyportal.yaml`.

## 2. Build SkyPortal Inventories

Fetch the four complete profiles:

```bash
.venv/bin/python scripts/02_fetch_source_inventory.py --profile gcn
.venv/bin/python scripts/02_fetch_source_inventory.py --profile grb
.venv/bin/python scripts/02_fetch_source_inventory.py --profile ep
.venv/bin/python scripts/02_fetch_source_inventory.py --profile grandma_base
```

Each command writes a timestamped directory such as:

```text
data/raw/skyportal/inventory/source_inventory_gcn_<timestamp>/
```

Read each command's printed output directory. Replace the four `<timestamp>` placeholders below with the directories from the same refresh cycle:

```bash
.venv/bin/python scripts/03_build_gcn_grandma.py \
  --inventory-dir data/raw/skyportal/inventory/source_inventory_gcn_<timestamp> \
  --inventory-dir data/raw/skyportal/inventory/source_inventory_grb_<timestamp> \
  --inventory-dir data/raw/skyportal/inventory/source_inventory_ep_<timestamp> \
  --inventory-dir data/raw/skyportal/inventory/source_inventory_grandma_base_<timestamp>
```

This writes:

```text
data/interim/skyportal/gcn_grandma.json
```

Then build the tabular baseline:

```bash
.venv/bin/python scripts/04_build_skyportal_event_baseline.py
```

Success means both files exist:

```text
data/interim/skyportal/skyportal_event_baseline.csv
data/interim/skyportal/skyportal_event_baseline.parquet
```

## 3. Build The GCN Circular Corpus

The GCN archive is public and does not use `SKYPORTAL_API_TOKEN`.

```bash
.venv/bin/python scripts/gcn/01_download_circulars_archive.py --extract
```

The command downloads `https://gcn.nasa.gov/circulars/archive.json.tar.gz` into a timestamped directory under `data/raw/gcn/circulars/archive_json/` and extracts it.

Build the normalized yearly indexes:

```bash
.venv/bin/python scripts/gcn/02_build_circulars_index.py
```

The index command automatically selects the most recent valid `archive_json/<timestamp>/extracted/archive.json` directory. To use another extracted run, pass it explicitly:

```bash
.venv/bin/python scripts/gcn/02_build_circulars_index.py \
  --input-dir data/raw/gcn/circulars/archive_json/<timestamp>/extracted/archive.json
```

Success means yearly CSV and Parquet partitions exist below `data/interim/gcn/circulars/` and the command reports no failed files.

## 4. Build Event Search Terms

```bash
.venv/bin/python scripts/gcn/03a_build_event_search_terms.py
```

This reads `gcn_grandma.json` and writes:

```text
data/interim/gcn/event_matching/event_search_terms.csv
data/interim/gcn/event_matching/event_search_terms.parquet
```

The console reports the number of selected events, generated terms, and output paths.

## 5. Build The Event Registry

```bash
.venv/bin/python scripts/build_event_registry.py
```

This writes `data/interim/gcn/event_matching/event_registry.csv`. Success means the console reports `registry_events`, duplicate groups, suffixless diagnostics, and the registry path.

## 6. Build The Identity Index

```bash
.venv/bin/python scripts/build_identity_index.py
```

This indexes Circulars from 2023 onward and writes:

```text
data/interim/gcn/event_matching/identity_index/identity_index.parquet
data/interim/gcn/event_matching/identity_index/index_meta.json
```

Success means `index_meta.json` reports matching `n_circulars`, `n_identity_annotations`, `event-identity-v1`, extractor version `0.1`, and a non-empty SHA-256.

## 7. Choose Viable Events

```bash
.venv/bin/python scripts/event_viability_sweep.py
```

The command writes `data/interim/gcn/event_matching/event_viability.csv`. Choose events with `n_included >= 5`, then inspect flags and body-only counts before building them. The current run reports 146 such events from 574 registry entries.

## 8. Build An Event Document

Verify that `data/inception/TypeSystem.xml` exists, then run:

```bash
.venv/bin/python scripts/event_build.py --source-id 2026owq
```

Replace `2026owq` with a `source_id` from `event_registry.csv`. The command writes:

```text
data/interim/gcn/event_matching/selections/selection_2026owq.txt
data/inception/out/2026owq/event_2026owq.xmi
data/inception/out/2026owq/event_2026owq_manifest.txt
```

Success requires these console lines:

```text
broken_global_offsets_event_evidence: 0
broken_global_offsets_photometry: 0
text_matches: True
all_spans_ok: True
all_features_ok: True
FINAL: OK
```

For event evidence, `n_original` must equal `n_roundtripped`. Both photometry round-trip booleans must be `True`. Read the selection report before importing the XMI, especially `EXCLUDED_CONFLICT`, both `BODY_ONLY` sections, and `FAR_IN_TIME`.

## 9. Run Verification

Run the complete test suite:

```bash
.venv/bin/python -m pytest tests/ -q
```

The current suite contains 727 passing tests.

Run a stratified extractor sweep and synchronize its alert report:

```bash
.venv/bin/python scripts/sweep_report.py per_year=200
.venv/bin/python scripts/alerts_report.py
```

The sweep writes `data/interim/gcn/sweep/sweep_report.json`. Success means there are no extraction errors and `alerts_report.py` reports a synchronized run.

## 10. Import Into INCEpTION

Follow [pipeline_v2/05_inception_export.md](./pipeline_v2/05_inception_export.md) for the UIMA CAS XMI XML 1.0 import procedure. Read [pipeline_v2/13_event_selection.md](./pipeline_v2/13_event_selection.md) for the membership hierarchy and selection-report semantics.

Use the INCEpTION project matching `data/inception/TypeSystem.xml`, import the event `.xmi`, and review both `ASTRO_EVIDENCE` and `PHOTOMETRIC_MEASUREMENT`.

`EVENT_SUMMARY` is not generated by this pipeline. It is a document metadata layer completed by annotators in INCEpTION's **Document Metadata** panel.

## Known Limitations

- SkyPortal inventory runtimes and results depend on the live API and token permissions.
- The identity index and automatic event selection currently cover Circulars from 2023 onward.
- Events represented only by internal trigger IDs cannot be matched to ordinary Circular names without additional aliases.
