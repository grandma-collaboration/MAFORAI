# Architecture

For whom: architects and developers who need the end-to-end design and module responsibilities.

Pipeline v2 is a deterministic chain from raw Circular records to offset-verified annotations. The architecture separates immutable text rendering, extractor logic, corpus-scale diagnostics, and INCEpTION export so that each layer can be tested without changing the others.

## End-To-End Flow

```text
SkyPortal inventories                 GCN Circular archive
        |                                      |
        v                                      v
gcn_grandma.json                    yearly Circular index
        |                                      |
        v                                      v
event_search_terms                  identity_index.parquet
        |                                      |
        v                                      |
event_registry.csv -----------------+
        |                            |
        +--> select_event_candidates()
             boundary-aware membership decisions
                    |
                    v
             selected Circulars
                    |
                    v
             EventCanonicalDocument
                    |
          +---------+----------+
          |                    |
          v                    v
get_active_extractors()   table + prose photometry
13 evidence extractors    measurement extractors
          |                    |
          +---------+----------+
                    |
                    v
event XMI + manifest + round-trip verification

All indexed Circulars can also flow through render_canonical(),
get_active_extractors(), sweep_report.py, and alerts_report.py.
```

The active evidence registry contains:

```text
EventIdentityExtractor
TriggerTimeExtractor
LocalizationExtractor
TriggerInstrumentExtractor
RedshiftExtractor
DurationExtractor
HighEnergyPropertyExtractor
NegativeStatementExtractor
LightcurveEvolutionExtractor
CounterpartAssociationExtractor
ClassificationInterpretationExtractor
HostContextExtractor
SpectroscopyExtractor
```

## Stages

| Stage | Receives | Produces | Implemented by |
|---|---|---|---|
| Circular loading | Yearly CSV/Parquet indexes or raw JSON | `dict` with Circular fields | `iter_real_circulars()` and `iter_stratified_circulars()` in `canonical/document.py` |
| Canonical rendering | Circular fields | `CanonicalDocument` | `render_canonical()` in `canonical/document.py` |
| Event term generation | `gcn_grandma.json` IDs, aliases, and TNS names | Search-term CSV/Parquet | `extraction/gcn_event_matching.py`, `scripts/gcn/03a_build_event_search_terms.py` |
| Event registry | Event terms plus SkyPortal position/time metadata | Deduplicated `event_registry.csv` | `extraction_v2/event_registry.py`, `scripts/build_event_registry.py` |
| Identity index | Circular corpus | Reusable subject/body identity Parquet plus metadata | `extraction_v2/identity_index.py`, `scripts/build_identity_index.py` |
| Event selection | Registry row plus identity index | Included Circulars, conflicts, body-only evidence, and flags | `select_event_candidates()` in `extraction_v2/event_selection.py` |
| Event document | Selected Circulars | Immutable `EventCanonicalDocument` and local/global segment map | `extraction_v2/event_document.py` |
| Annotation model | Extracted spans | Validated `EventEvidenceAnnotation` | `extraction_v2/annotations.py` |
| Tagset validation | Label, target, certainty strings | Accepted or rejected annotation | `extraction_v2/tagsets.py` |
| Active extractor registry | Extractor classes | Sweep-ready extractor list | `get_active_extractors()` in `extraction_v2/sweep.py` |
| Event identity extraction | `CanonicalDocument` | `EVENT_IDENTITY` annotations | `extraction_v2/event_identity.py` |
| Trigger time extraction | `CanonicalDocument` | `TRIGGER_TIME` annotations | `extraction_v2/trigger_time.py` |
| Localization extraction | `CanonicalDocument` | `LOCALIZATION` annotations | `extraction_v2/localization.py` |
| Trigger instrument extraction | `CanonicalDocument` | `TRIGGER_INSTRUMENT` annotations | `extraction_v2/trigger_instrument.py` |
| Redshift extraction | `CanonicalDocument` | `REDSHIFT_EVENT` and `REDSHIFT_CONTEXT` annotations | `extraction_v2/redshift.py` |
| Duration extraction | `CanonicalDocument` | `T90` and `DURATION_GENERAL` annotations | `extraction_v2/duration.py` |
| High-energy extraction | `CanonicalDocument` | `HIGH_ENERGY_PROPERTY` annotations | `extraction_v2/high_energy.py` |
| Negative-statement extraction | `CanonicalDocument` | `NEGATIVE_STATEMENT` annotations | `extraction_v2/negative_statement.py` |
| Light-curve extraction | `CanonicalDocument` | `LIGHTCURVE_EVOLUTION` annotations | `extraction_v2/lightcurve_evolution.py` |
| Counterpart extraction | `CanonicalDocument` | `COUNTERPART_ASSOCIATION` annotations | `extraction_v2/counterpart_association.py` |
| Classification extraction | `CanonicalDocument` | `CLASSIFICATION_INTERPRETATION` annotations | `extraction_v2/classification_interpretation.py` |
| Host extraction | `CanonicalDocument` | `HOST_CONTEXT` annotations | `extraction_v2/host_context.py` |
| Spectroscopy extraction | `CanonicalDocument` | `SPECTROSCOPY` annotations | `extraction_v2/spectroscopy.py` |
| Sweep diagnostics | Real Circular batches plus extractors | JSON report and text alert report | `extraction_v2/sweep.py`, `scripts/sweep_report.py`, `scripts/alerts_report.py` |
| Event annotation translation | Event segments plus local annotations | Globally offset event evidence and photometry | `extraction_v2/event_annotations.py`, `extraction_v2/event_photometry.py` |
| XMI export | Event document plus both layers | UIMA CAS XMI file | `inception_v2/event_xmi_export.py`, `scripts/event_build.py` |
| Round-trip check | XMI plus original data | Verification dictionary | `inception_v2/xmi_roundtrip.py` |

## Module Map

| File | Responsibility |
|---|---|
| `src/skyportal_corpus/canonical/document.py` | Builds immutable canonical text, stores header/body segments, computes SHA-256, and loads real Circulars. |
| `src/skyportal_corpus/extraction_v2/tagsets.py` | Defines the closed tagsets for `label`, `target`, and `certainty`. |
| `src/skyportal_corpus/extraction_v2/annotations.py` | Defines `EventEvidenceAnnotation` and verifies spans against text. |
| `src/skyportal_corpus/extraction_v2/event_identity.py` | Finds event identities and trigger identifiers, normalizes canonical values, and filters table-row AT/SN/ZTF entries. |
| `src/skyportal_corpus/extraction_v2/trigger_time.py` | Finds trigger-time evidence using pure helper functions for candidates, gates, date adjacency, normalization, and de-overlap. |
| `src/skyportal_corpus/extraction_v2/localization.py` | Finds RA/Dec positions and positional uncertainty phrases. |
| `src/skyportal_corpus/extraction_v2/instruments_vocab.py` | Stores canonical trigger instruments and aliases. |
| `src/skyportal_corpus/extraction_v2/trigger_instrument.py` | Finds trigger instruments using instrument vocabulary plus trigger/follow-up/reference gates. |
| `src/skyportal_corpus/extraction_v2/redshift.py` | Finds redshift values and classifies them as event or context with conservative attribution. |
| `src/skyportal_corpus/extraction_v2/duration.py` | Finds explicit T90 and general event durations with instrument/band context. |
| `src/skyportal_corpus/extraction_v2/high_energy.py` | Finds fluence, peak flux, spectral parameters, peak/cutoff energies, and Eiso. |
| `src/skyportal_corpus/extraction_v2/negative_statement.py` | Finds scientific rejections and negative findings while deferring photometric non-detections and light-curve behavior. |
| `src/skyportal_corpus/extraction_v2/lightcurve_evolution.py` | Finds observed fading, rising, flattening, variability, and confirmed absence of evolution. |
| `src/skyportal_corpus/extraction_v2/counterpart_association.py` | Finds explicit candidate or confirmed counterpart/afterglow associations. |
| `src/skyportal_corpus/extraction_v2/classification_interpretation.py` | Finds GRB/transient classes and physical interpretations. |
| `src/skyportal_corpus/extraction_v2/host_context.py` | Finds host candidates, offsets, ambiguity, and nearby-galaxy context. |
| `src/skyportal_corpus/extraction_v2/spectroscopy.py` | Finds optical/NIR spectroscopy observations and spectral features. |
| `src/skyportal_corpus/extraction_v2/event_registry.py` | Deduplicates SkyPortal events, merges terms, and records dropped/absorbed identifiers. |
| `src/skyportal_corpus/extraction_v2/identity_index.py` | Runs event identity once per Circular and stores the reusable subject/body partition. |
| `src/skyportal_corpus/extraction_v2/event_selection.py` | Scans the identity index, applies the membership hierarchy, and checks cached decisions against live grouping. |
| `src/skyportal_corpus/extraction_v2/sweep.py` | Runs active extractors over batches, aggregates coverage/review/alerts, records gaps, and supports `only=` filtering. |
| `src/skyportal_corpus/inception_v2/xmi_export.py` | Provides shared CAS and TypeSystem helpers for INCEpTION-compatible XMI. |
| `src/skyportal_corpus/inception_v2/event_xmi_export.py` | Writes event evidence and photometry over one event sofa and verifies both layers. |
| `src/skyportal_corpus/inception_v2/xmi_roundtrip.py` | Loads exported XMI back and checks text, spans, and features. |

## Circular 33130 Walkthrough

The real Circular `33130` has the subject:

```text
GRB 230101A: Fermi GBM Final Real-time Localization
```

The canonical renderer places it in the header:

```text
SUBJECT: GRB 230101A: Fermi GBM Final Real-time Localization
DATE: 2023-01-01T02:26:46+00:00
FROM: Fermi GBM Team at MSFC/Fermi-GBM  <do_not_reply@GIOC.nsstc.nasa.gov>
```

`EventIdentityExtractor` emits `GRB 230101A` as `EVENT_IDENTITY`. Because the normalized value also appears in the header, it is treated as the main event identity and does not need review.

The body contains:

```text
At 02:16:38 UT on 1 Jan 2023, the Fermi Gamma-ray Burst Monitor (GBM) triggered and located GRB 230101A
```

`TriggerTimeExtractor` emits `02:16:38 UT on 1 Jan 2023` as `TRIGGER_TIME` with normalized value `2023-01-01T02:16:38`.

`TriggerInstrumentExtractor` emits the instrument mention as `TRIGGER_INSTRUMENT` with value `Fermi/GBM`.

The XMI exporter writes these annotations to the `webanno.custom.ASTRO_EVIDENCE` layer so INCEpTION can display the same spans for human review.
