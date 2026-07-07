# Architecture

For whom: architects and developers who need the end-to-end design and module responsibilities.

Pipeline v2 is a deterministic chain from raw Circular records to offset-verified annotations. The architecture separates immutable text rendering, extractor logic, corpus-scale diagnostics, and INCEpTION export so that each layer can be tested without changing the others.

## End-To-End Flow

```text
data/raw or data/interim Circular record
        |
        | iter_real_circulars() or iter_stratified_circulars()
        v
dict: circular_id, subject, body, created_on, event_id, submitter, year
        |
        | render_canonical()
        v
CanonicalDocument
  - rendered_text
  - text_sha256
  - header/body segments
        |
        | get_active_extractors()
        v
EventIdentityExtractor
TriggerTimeExtractor
LocalizationExtractor
TriggerInstrumentExtractor
RedshiftExtractor
        |
        v
list[EventEvidenceAnnotation]
  - span_start/span_end
  - exact text
  - label/target/certainty
  - extractor provenance
        |
        +--> sweep_report.py / alerts_report.py
        |    corpus diagnostics, alert context, gaps, run_id
        |
        +--> export_document_to_xmi()
             UIMA CAS XMI for INCEpTION
```

## Stages

| Stage | Receives | Produces | Implemented by |
|---|---|---|---|
| Circular loading | Yearly CSV/Parquet indexes or raw JSON | `dict` with Circular fields | `iter_real_circulars()` and `iter_stratified_circulars()` in `canonical/document.py` |
| Canonical rendering | Circular fields | `CanonicalDocument` | `render_canonical()` in `canonical/document.py` |
| Annotation model | Extracted spans | Validated `EventEvidenceAnnotation` | `extraction_v2/annotations.py` |
| Tagset validation | Label, target, certainty strings | Accepted or rejected annotation | `extraction_v2/tagsets.py` |
| Active extractor registry | Extractor classes | Sweep-ready extractor list | `get_active_extractors()` in `extraction_v2/sweep.py` |
| Event identity extraction | `CanonicalDocument` | `EVENT_IDENTITY` annotations | `extraction_v2/event_identity.py` |
| Trigger time extraction | `CanonicalDocument` | `TRIGGER_TIME` annotations | `extraction_v2/trigger_time.py` |
| Localization extraction | `CanonicalDocument` | `LOCALIZATION` annotations | `extraction_v2/localization.py` |
| Trigger instrument extraction | `CanonicalDocument` | `TRIGGER_INSTRUMENT` annotations | `extraction_v2/trigger_instrument.py` |
| Redshift extraction | `CanonicalDocument` | `REDSHIFT_EVENT` and `REDSHIFT_CONTEXT` annotations | `extraction_v2/redshift.py` |
| Sweep diagnostics | Real Circular batches plus extractors | JSON report and text alert report | `extraction_v2/sweep.py`, `scripts/sweep_report.py`, `scripts/alerts_report.py` |
| XMI export | Document plus annotations | UIMA CAS XMI file | `inception_v2/xmi_export.py` |
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
| `src/skyportal_corpus/extraction_v2/sweep.py` | Runs active extractors over batches, aggregates coverage/review/alerts, records gaps, and supports `only=` filtering. |
| `src/skyportal_corpus/inception_v2/xmi_export.py` | Builds a CAS, adds optional Sentence/Token annotations, and writes INCEpTION-compatible XMI. |
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
