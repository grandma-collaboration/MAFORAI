# MAFORAI Extraction Pipeline v2

For whom: annotators, developers, and architects who need a clear entry point into the span-first extraction pipeline.

Pipeline v2 turns raw GCN Circulars into validated preannotations for INCEpTION. Its central idea is simple: render one immutable canonical text, anchor every machine proposal to offsets in that exact text, export those annotations to XMI, and let humans review them in INCEpTION.

```text
raw Circular
    |
    v
canonical text
    |
    v
extractors
    |
    v
validated annotations
    |
    v
sweep diagnostics
    |
    v
XMI export
    |
    v
INCEpTION
    |
    v
human review
```

## Where To Start

| If you are | Start with | Why |
|---|---|---|
| Annotator | [05_inception_export.md](./05_inception_export.md), then [11_reproduce_event_xmi.md](./11_reproduce_event_xmi.md) | You need to know what is imported into INCEpTION and how the event deliverable is generated. |
| Developer | [04_extractors/README.md](./04_extractors/README.md), [09_method_and_lessons.md](./09_method_and_lessons.md), then [10_event_flow.md](./10_event_flow.md) and [12_photometry.md](./12_photometry.md) | You need the extractor contract, scale-validation method, local-to-global offset flow, and photometry maintenance guide. |
| Architect | [00_overview.md](./00_overview.md), [01_architecture.md](./01_architecture.md), then [10_event_flow.md](./10_event_flow.md) | You need the design rationale and the transition from Circular evidence to an event document. |

## Documents

| Document | What it explains |
|---|---|
| [00_overview.md](./00_overview.md) | The problem, the goal, and the principles behind v2. |
| [01_architecture.md](./01_architecture.md) | The complete pipeline flow and module map. |
| [02_canonical_text.md](./02_canonical_text.md) | Why canonical text exists and why it must never change after rendering. |
| [03_annotations_and_tagsets.md](./03_annotations_and_tagsets.md) | The annotation model and the exact label, target, and certainty tagsets. |
| [04_extractors/README.md](./04_extractors/README.md) | The common extractor pattern and how to add a new extractor. |
| [04_extractors/event_identity.md](./04_extractors/event_identity.md) | The `EVENT_IDENTITY` extractor, canonical identity values, review logic, and table-row filter. |
| [04_extractors/trigger_time.md](./04_extractors/trigger_time.md) | The `TRIGGER_TIME` extractor, context gates, observation exclusions, date capture, and limitations. |
| [04_extractors/localization.md](./04_extractors/localization.md) | The `LOCALIZATION` extractor for RA/Dec positions and uncertainty spans. |
| [04_extractors/trigger_instrument.md](./04_extractors/trigger_instrument.md) | The `TRIGGER_INSTRUMENT` extractor, instrument vocabulary, trigger/follow-up gates, and false-positive gates. |
| [04_extractors/redshift.md](./04_extractors/redshift.md) | The redshift extractor for `REDSHIFT_EVENT` and `REDSHIFT_CONTEXT`, including the attribution safety policy. |
| [05_inception_export.md](./05_inception_export.md) | XMI export, INCEpTION import, and round-trip verification. |
| [06_glossary.md](./06_glossary.md) | Short definitions of the terms used by the pipeline. |
| [07_status_and_roadmap.md](./07_status_and_roadmap.md) | What is implemented, what is missing, and the next roadmap areas. |
| [08_sweep_and_reports.md](./08_sweep_and_reports.md) | The corpus sweep, stratified sampling, run synchronization, alert context, and gap diagnostics. |
| [09_method_and_lessons.md](./09_method_and_lessons.md) | The development method and lessons learned from hardening extractors at scale. |
| [10_event_flow.md](./10_event_flow.md) | Event grouping, global canonical text, global annotation offsets, and event XMI export. |
| [11_reproduce_event_xmi.md](./11_reproduce_event_xmi.md) | Exact commands and prerequisites for regenerating an event-level INCEpTION document. |
| [12_photometry.md](./12_photometry.md) | Developer guide to table/prose photometry extraction, field semantics, XMI export, auditing, and extension points. |
