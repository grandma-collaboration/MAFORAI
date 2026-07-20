# Reproducing An Event XMI

For whom: developers and tutors who need to regenerate and inspect an event-level INCEpTION deliverable.

The current flow selects Circulars automatically from the SkyPortal-derived event registry and reusable identity index. One command then builds the immutable event document, extracts both annotation layers, exports XMI, and verifies the round-trip.

## Prerequisites

Run every command from the repository root with Python 3.10 or newer.

| Requirement | Expected path | How it is produced |
|---|---|---|
| Virtual environment | `.venv/bin/python` | `python -m venv .venv` and `.venv/bin/pip install -e ".[dev]"` |
| INCEpTION TypeSystem | `data/inception/TypeSystem.xml` | Exported from the target INCEpTION project as UIMA CAS XMI XML 1.0 |
| Circular index | `data/interim/gcn/circulars/` | `scripts/gcn/02_build_circulars_index.py` |
| Event search terms | `data/interim/gcn/event_matching/event_search_terms.csv` | `scripts/gcn/03a_build_event_search_terms.py` |
| Event registry | `data/interim/gcn/event_matching/event_registry.csv` | `scripts/build_event_registry.py` |
| Identity index | `data/interim/gcn/event_matching/identity_index/identity_index.parquet` | `scripts/build_identity_index.py` |

The TypeSystem must define `webanno.custom.ASTRO_EVIDENCE` and `webanno.custom.PHOTOMETRIC_MEASUREMENT`. It is currently ignored by the repository's final `/data/` rule and is not available in a fresh clone; place the matching exported file at the required path before generating XMI.

For the complete upstream rebuild, use [the repository runbook](../RUNBOOK.md).

## Refresh Selection Inputs

After changing `gcn_grandma.json` or refreshing the Circular index, rebuild the dependent selection products in order:

```bash
.venv/bin/python scripts/gcn/03a_build_event_search_terms.py
.venv/bin/python scripts/build_event_registry.py
.venv/bin/python scripts/build_identity_index.py
```

The identity-index metadata records the 2023-and-later corpus scope and the `EventIdentityExtractor` version. `event_build.py` refuses an incompatible extractor version or `min_year`.

## Choose An Event

Run the registry-wide viability report when the event is not already known:

```bash
.venv/bin/python scripts/event_viability_sweep.py
```

Inspect `data/interim/gcn/event_matching/event_viability.csv`. Events with `n_included >= 5` are usually the most useful dossier candidates, but counts alone do not validate membership. Review `suffixless_only`, body-only counts, conflict counts, and temporal range.

## Build The Event

Run:

```bash
.venv/bin/python scripts/event_build.py --source-id 2026owq
```

Replace `2026owq` with a canonical or merged `source_id` from `event_registry.csv`. The command uses `select_event_candidates()`, builds the event document, runs every active evidence extractor plus both photometry paths, exports both layers, and performs an immediate round-trip check.

To inspect membership without requiring a TypeSystem or writing XMI, use:

```bash
.venv/bin/python scripts/event_build.py --source-id 2026owq --no-xmi
```

## Review The Selection Report

Every build writes:

```text
data/interim/gcn/event_matching/selections/selection_<source_id>.txt
```

Read this file before importing the XMI.

| Section | Review question |
|---|---|
| Header fields | Are the terms, merged IDs, trigger time, corpus scope, counts, and flags expected? |
| `INCLUDED` | Does every selected Circular actually belong to the event? |
| `EXCLUDED_CONFLICT` | Did a competing subject identity correctly suppress a body mention? |
| `BODY_ONLY - IDENTITY ANNOTATION` | Is the extracted body identity sufficient membership evidence? |
| `BODY_ONLY - BODY NAME MATCH` | Is the raw boundary-aware name match a legitimate event reference? |
| `FAR_IN_TIME` | Is a selected Circular more than 365 days from the trigger still credible? |

`delta_days` and `FAR_IN_TIME` are visibility fields. They never remove a Circular automatically.

## Inspect The Outputs

For source ID `2026owq`, the generated files are:

```text
data/inception/out/2026owq/event_2026owq.xmi
data/inception/out/2026owq/event_2026owq_manifest.txt
```

The manifest reports the event title, Circular count, text hash and length, evidence and photometry totals, counts by extractor and label, and the ordered Circular list.

## Verify The Round-Trip

The console must report:

```text
broken_global_offsets_event_evidence: 0
broken_global_offsets_photometry: 0
text_matches: True
all_spans_ok: True
all_features_ok: True
photometry_all_spans_ok: True
photometry_all_features_ok: True
FINAL: OK
```

For event evidence, `n_original` must equal `n_roundtripped`, and `discrepancies` must be empty. `FINAL: OK` requires both layers to preserve their text, spans, and exported features.

Translation errors are printed under `TRANSLATION ERRORS`. Any such entry or `FINAL: FAIL` blocks import until diagnosed.

## Run Focused Tests

```bash
.venv/bin/python -m pytest \
  tests/test_event_grouping.py \
  tests/test_event_selection.py \
  tests/test_identity_index.py \
  tests/test_event_document.py \
  tests/test_event_annotations.py \
  tests/test_xmi_roundtrip.py -q
```

These tests cover matching hierarchy, boundary-aware body names, registry/index selection agreement, immutable segment slices, local-to-global offsets, both XMI layers, and round-trip integrity.

## Import Into INCEpTION

1. Open the INCEpTION project whose layer definitions match `data/inception/TypeSystem.xml`.
2. If necessary, import that TypeSystem into the project.
3. Add a document using the **UIMA CAS XMI XML 1.0** format.
4. Select `data/inception/out/<source_id>/event_<source_id>.xmi`.
5. Open the document and inspect both `ASTRO_EVIDENCE` and `PHOTOMETRIC_MEASUREMENT`.
6. Review non-empty annotation comments first because comments encode machine review reasons.

The XMI contains the immutable event text and the exported layer features. Internal fields such as `source_circular_id`, `needs_review`, and extractor provenance are not TypeSystem features.

## Event Summary

`EVENT_SUMMARY` is a document metadata layer, not a span layer emitted by this export pipeline. Annotators complete it in INCEpTION's **Document Metadata** panel after reviewing the event dossier. Automatic scientific aggregation remains outside the exporter.

## Superseded Manual Demos

These scripts remain historical, event-specific demos and are not the current build path:

```text
scripts/event_xmi_export.py
scripts/event_grouping_demo.py
scripts/event_document_demo.py
```

They use pilot constants and manual candidate controls. Do not edit their `SOURCE_ID`, aliases, or Circular range to build a new event. Use `scripts/event_build.py --source-id <id>`.

## Related Documents

- [Automatic event selection](./13_event_selection.md)
- [Event-to-document flow](./10_event_flow.md)
- [INCEpTION export](./05_inception_export.md)
- [Canonical text](./02_canonical_text.md)
- [Status and roadmap](./07_status_and_roadmap.md)

## Known Limitations

- A fresh clone still needs an externally supplied `data/inception/TypeSystem.xml` until its `.gitignore` exception is committed.
- The automatic identity index currently covers Circulars from 2023 onward.
- Events whose registry row contains only an internal trigger ID select no ordinary Circulars.
- Round-trip success proves serialization integrity, not scientific correctness or event-membership correctness.
