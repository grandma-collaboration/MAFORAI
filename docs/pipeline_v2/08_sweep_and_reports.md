# Sweep And Reports

For whom: developers and architects who validate extractor behavior on real GCN Circulars.

The sweep is the pipeline v2 scale-test harness. It runs active extractors over real Circulars, records what each extractor found, and highlights suspicious cases with enough context to diagnose problems without opening the raw JSON by hand.

## Why Sweep Exists

Unit tests prove that known cases behave correctly. They do not prove that a regex survives the variety of real Circulars. The sweep fills that gap: it runs against the corpus and exposes systematic false positives, missed subjects, review load, and year-specific coverage changes.

```text
real circulars
    |
    | render_canonical()
    v
CanonicalDocument
    |
    | get_active_extractors()
    v
all extractor annotations
    |
    | flag_suspicious()
    v
aggregated report + full alert report
```

## Active Extractor Registry

The active list is centralized in `get_active_extractors()` in `src/skyportal_corpus/extraction_v2/sweep.py`.

To add a new extractor to the sweep, add one line there. The report, coverage tables, rule counts, and alert summaries are derived from that registry and from annotation metadata.

## Filtering By Extractor

The sweep can run all extractors or focus on a subset:

```bash
.venv/bin/python scripts/sweep_report.py per_year=100
.venv/bin/python scripts/sweep_report.py per_year=100 only=redshift
.venv/bin/python scripts/sweep_report.py per_year=100 only=redshift,localization
```

The `only=` mode is useful while hardening a new extractor. It keeps the report focused on the rules under active development.

## Stratified Sampling By Year

`per_year=N` samples up to `N` eligible Circulars from each year, spread uniformly through that year. This avoids the bias of taking the first `N` Circulars, which would overrepresent early 2023.

This matters because the corpus changes over time. Einstein Probe appears in the 2024+ era, SVOM appears from 2024, and LIGO/Virgo/KAGRA O4 changed the mix of Circular subjects in 2023+. A year-stratified sweep is the right default for scale validation.

## Run Synchronization

`sweep_report.py` writes `data/interim/gcn/sweep/sweep_report.json` with a `run_meta` block:

```text
generated_at
mode
extractors
n_circulars_processed
total_alerts
run_id
```

`alerts_report.py` reads that JSON, recomputes the alert count, and prints `SINCRONIZADO` when the numbers match. This prevents a common failure mode: reading an old `alerts_report.txt` after a new sweep has changed the JSON.

## Gaps

Alerts only show annotations that were produced. They do not show missing extractions. The sweep therefore records identity gaps: Circulars where `event_identity` produced zero annotations, including the `circular_id`, year, and subject.

These gaps are how the EP-WXT and EP day-fraction identity formats were discovered.

## Alert Context

Only flagged annotations carry expensive context fields:

| Field | Purpose |
|---|---|
| `context_window` | About 120 characters before and after the span, with the span wrapped in markers. |
| `source_line` | The full rendered-text line that contains the span start. |

Healthy annotations do not carry context in the JSON. This keeps the report light while making suspicious cases easy to inspect.

## How To Read A Sweep Report

Coverage shows how many Circulars produced at least one annotation per extractor. A sudden drop by year can mean the vocabulary is missing a new mission or naming style.

Review rate shows how much human attention an extractor is requesting. High review is not always bad; for redshift, review is a deliberate safety mechanism.

Rule counts show which patterns dominate. If one rule causes most alerts, fix that rule first.

The alert report groups by `flag`, `extractor`, and `rule_id`, so similar problems are clustered together. Read the context windows before changing code; many alerts are legitimate review requests, not bugs.

## Current Verification Snapshot

The current all-extractor `per_year=100` sweep processed 400 Circulars, produced 1478 annotations, had 0 extraction errors, and generated 219 review alerts. The alert report was synchronized with `run_id=f20d31ac` for that run.
