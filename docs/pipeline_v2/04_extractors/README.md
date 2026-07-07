# Extractors

For whom: developers who add or maintain pipeline v2 extractors.

An extractor receives a `CanonicalDocument` and returns verified `EventEvidenceAnnotation` objects. The important contract is not the regex itself; it is that every proposed value is anchored to an exact span in `doc.rendered_text`, validated against the tagsets, and checked with `verify()` before export.

## Common Shape

```text
CanonicalDocument
    |
    | find candidates in doc.rendered_text
    v
raw span candidates
    |
    | gates, normalization, de-overlap
    v
EventEvidenceAnnotation[]
    |
    | annotation.verify(doc.rendered_text)
    v
safe to export
```

The mature extractors now follow the same internal pattern:

1. `find_candidates(text)` finds raw spans and stable `rule_id` provenance.
2. Negative gates run before positive gates when exclusion is safer than acceptance.
3. Positive gates require local evidence that the match means the target concept.
4. De-overlap keeps the best match when two rules cover the same text.
5. Normalization produces `value`; the raw exact substring remains in `text`.
6. The orchestrator builds `EventEvidenceAnnotation` objects with valid `label`, `target`, and `certainty`.
7. Every annotation calls `verify(doc.rendered_text)` before the extractor returns.

This decomposition came from `TriggerTimeExtractor`, where observation-time exclusions, trigger context, date capture, and ISO normalization had become too entangled. Keeping those responsibilities separate makes future fixes easier to test without changing behavior elsewhere.

## Shared Concepts

Context gating means a match is only accepted if nearby text supports the interpretation. `TriggerTimeExtractor` requires trigger context before a clock time becomes `TRIGGER_TIME`; `TriggerInstrumentExtractor` requires trigger or detection language before an instrument becomes `TRIGGER_INSTRUMENT`.

Negative gates have priority. If text says an XRT observation began at a time, that time is discarded even if the word `trigger` appears nearby. If a Fermi/LAT mention is followed by `data` or `catalog`, it is treated as a reference, not as the trigger instrument.

De-overlap prevents duplicate annotations over the same evidence. For example, `02:16:38 UT on 1 Jan 2023` wins over the shorter overlapping `02:16:38 UT`.

`needs_review` is used when the extractor found real evidence but cannot safely make the scientific decision. Multiple trigger times, multiple trigger instruments, body-only event names, and ambiguous redshifts are deliberately surfaced to the human annotator instead of silently discarded.

## How To Add A New Extractor

1. Create a new file under `src/skyportal_corpus/extraction_v2/`.
2. Define `extractor_id` and `extractor_version`.
3. Define candidate rules with stable `rule_id` values.
4. Split complex logic into pure helpers: candidate finding, negative gates, positive gates, de-overlap, normalization, and annotation construction.
5. Map each accepted match to exactly one `label` from [../03_annotations_and_tagsets.md](../03_annotations_and_tagsets.md).
6. Use only allowed `target` and `certainty` values.
7. Use `doc.rendered_text[start:end]` for `text`; never rebuild the span text from groups.
8. Normalize `value` only when the transformation is deterministic and scientifically safe.
9. Add `needs_review=True` when the extractor is proposing evidence but not resolving the scientific ambiguity.
10. Verify every annotation before returning.
11. Add a demo script and synthetic pytest tests.
12. Connect the extractor to the sweep registry in `get_active_extractors()`.
13. Run the scale validation cycle described in [../09_method_and_lessons.md](../09_method_and_lessons.md).

Use the project interpreter directly:

```bash
.venv/bin/python -m pytest tests/test_<extractor>.py
.venv/bin/python scripts/<extractor>_demo.py
.venv/bin/python scripts/sweep_report.py per_year=100 only=<short_name>
.venv/bin/python scripts/alerts_report.py
```

## Existing Extractors

| Extractor | Label(s) | Rules | Documentation |
|---|---:|---:|---|
| `EventIdentityExtractor` | `EVENT_IDENTITY` | 11 | [event_identity.md](./event_identity.md) |
| `TriggerTimeExtractor` | `TRIGGER_TIME` | 6 | [trigger_time.md](./trigger_time.md) |
| `LocalizationExtractor` | `LOCALIZATION` | 3 | [localization.md](./localization.md) |
| `TriggerInstrumentExtractor` | `TRIGGER_INSTRUMENT` | 16 instrument rules | [trigger_instrument.md](./trigger_instrument.md) |
| `RedshiftExtractor` | `REDSHIFT_EVENT`, `REDSHIFT_CONTEXT` | 4 | [redshift.md](./redshift.md) |
