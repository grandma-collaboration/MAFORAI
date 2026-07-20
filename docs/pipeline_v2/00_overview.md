# Overview

For whom: everyone working with pipeline v2, including annotators, developers, and architects.

GCN Circulars are short astronomical reports used to communicate transient-event information such as GRB names, trigger times, localizations, redshifts, and follow-up observations. MAFORAI pipeline v2 extracts candidate evidence from those Circulars as preannotations for INCEpTION, where a human annotator validates what the machine proposes. The final goal is a scientific corpus whose annotations are traceable back to exact text spans.

## The Problem

The older GCN workflow in this repository downloads Circulars, builds yearly indexes, matches SkyPortal events against Circulars, extracts structured claims, and builds review tables. That workflow is useful, but it is not built around one invariant text representation. When text is assembled, cleaned, or normalized in different places, an offset can point to the wrong substring.

Pipeline v2 exists to fix that. It starts at the Circular level, renders one canonical text for each Circular, and makes every extractor work against that exact string. Automatic selection then combines verified Circular spans into an immutable event document; scientific adjudication into `EVENT_SUMMARY` remains a human task.

## Design Principles

1. The canonical text is immutable.
   The pipeline renders a single `rendered_text` string from the Circular subject, date, submitter, and body. After that render step, the string is never modified. Every offset is measured against that exact text.

2. Every annotation is anchored by offset and verifiable.
   A span is the substring selected by `span_start` and `span_end`. An offset is a character position inside `rendered_text`. The annotation stores both offsets and the exact `text`, so `verify(rendered_text)` can prove that the annotation still points to the same substring.

3. Tagsets come from INCEpTION, not from extractor convenience.
   The `label`, `target`, and `certainty` values are closed sets. The model rejects values outside those sets, such as an invented `other_event` target.

4. The machine proposes and the human validates.
   Extractors are intentionally conservative. Ambiguous cases use `needs_review=True` instead of pretending the decision is final.

5. Circular-level evidence remains the extraction unit.
   Automatic event selection aggregates verified local annotations into immutable event documents without cross-Circular inference. Annotators perform event-level adjudication through `EVENT_SUMMARY` in INCEpTION.

## Why v2 Exists Beside `extraction/`

The existing `src/skyportal_corpus/extraction/` workflow remains in the repository and is not replaced here. It handles archive download, indexing, matching, claim extraction, enrichment comparison, and review tables. Pipeline v2 is a new span-first foundation under `canonical/`, `extraction_v2/`, and `inception_v2/`; it is designed for offset-stable preannotation and INCEpTION import.

## Real Example

For Circular `33130`, the subject is:

```text
GRB 230101A: Fermi GBM Final Real-time Localization
```

Pipeline v2 renders that into canonical text, extracts `GRB 230101A` as `EVENT_IDENTITY`, extracts `02:16:38 UT on 1 Jan 2023` as `TRIGGER_TIME`, and exports both as span annotations for human review.
