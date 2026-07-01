# INCEpTION Pilot Dossiers

## Goal

This stage builds a **blind plain-text dossier** for one matched event so it can
be uploaded to INCEpTION as a normal text document for pilot scientific
annotation.

It does **not** run new extraction logic.
It does **not** include our automatic claims or event-level best values.
It only reorganizes already matched GCN Circulars into one clean dossier.

## Entry points

| File | Role |
|---|---|
| `scripts/gcn/07_build_inception_event_dossier.py` | Build one dossier for one event |
| `src/skyportal_corpus/extraction/gcn_inception_dossiers.py` | Shared dossier-building logic |

## Inputs

- `data/interim/gcn/event_matching/event_gcn_associations.parquet`
- `data/interim/skyportal/gcn_grandma.json`
- raw circular JSON paths referenced from the associations file
- year-partitioned circular index under `data/interim/gcn/circulars/` as a fallback

## Typical command

```bash
python scripts/gcn/07_build_inception_event_dossier.py \
  --source-id 2026owq \
  --title "GRB 260610B / AT2026owq" \
  --output-dir data/interim/gcn/event_validation/inception_dossiers
```

## Outputs

- `data/interim/gcn/event_validation/inception_dossiers/<safe_source_id>_inception_dossier.txt`
- `data/interim/gcn/event_validation/inception_dossiers/<safe_source_id>_inception_dossier_manifest.json`

## What the dossier contains

The dossier includes:

- event title
- source id
- aliases
- annotation instructions for the astronomer
- **all matched Circulars** for that event after deduplication by `circular_id`
- each Circular sorted chronologically by `created_at_iso`, then by `circular_id`
- `circular_id`, `created_at_iso`, `subject`, and full `body`

The dossier is intentionally **blind**:

- no extracted claims
- no best values
- no review decisions

## How it fits in the workflow

This step comes **after event matching** and before any manual INCEpTION pilot
annotation.

It is a packaging step:

- matching already decided which Circulars belong to the event
- this dossier simply turns those matched Circulars into one plain-text file
  that astronomers can annotate independently in INCEpTION
