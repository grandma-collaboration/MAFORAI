# Event-Level GCN Enrichment

## Goal

This stage aggregates the Step-B claims into compact event-level enrichment
candidates and compares them against the compact SkyPortal metadata already
present in `gcn_grandma.json`.

It does not overwrite SkyPortal fields. It only shows where GCN adds useful
information.

## Entry points

| File | Role |
|---|---|
| `scripts/gcn/05a_build_event_enrichment_candidates.py` | Build one compact best-claims table per event |
| `scripts/gcn/05b_compare_gcn_enrichment_with_skyportal.py` | Compare those best claims against the SkyPortal-side event base |
| `src/skyportal_corpus/extraction/gcn_event_enrichment.py` | Shared event-level aggregation and comparison logic |

## Inputs

For best-claims aggregation:

- `data/interim/gcn/event_extraction/gcn_core_claims.parquet`
- `data/interim/gcn/event_matching/event_gcn_match_summary.csv`

For the SkyPortal comparison:

- `data/samples/gcn_grandma.json`
- `data/interim/gcn/event_enrichment/gcn_event_best_claims.parquet`


## Step 05a. Build event-level best claims

Typical command:

```bash
python scripts/gcn/05a_build_event_enrichment_candidates.py \
  --claims-path data/interim/gcn/event_extraction/gcn_core_claims.parquet \
  --match-summary-path data/interim/gcn/event_matching/event_gcn_match_summary.csv \
  --output-dir data/interim/gcn/event_enrichment
```

Outputs:

- `data/interim/gcn/event_enrichment/gcn_event_best_claims.csv`
- `data/interim/gcn/event_enrichment/gcn_event_best_claims.parquet`
- `data/interim/gcn/event_enrichment/gcn_event_best_claims_report.json`

This table has one row per matched event and keeps compact candidates such as:

- `best_trigger_time`
- `best_t90_seconds`
- `best_duration_class`
- `best_redshift`
- `best_redshift_method`
- `has_counterpart`
- `counterpart_types`
- `has_detection`
- `has_non_detection`
- `has_upper_limit`
- `has_spectroscopy`
- `has_host_candidate`
- `instruments_found`
- `classification_flags`
- `claim_types_found`

The selection rules are intentionally simple:

- prefer stronger claim methods when relevant, such as spectroscopic redshift
  over photometric redshift;
- prefer higher claim confidence;
- prefer explicit numeric values when choosing T90-like candidates;
- for trigger time, prefer cleaner absolute timestamps and more complete values
  such as full ISO datetimes over less complete time-only representations.

## Step 05b. Compare GCN enrichment against SkyPortal

Typical command:

```bash
python scripts/gcn/05b_compare_gcn_enrichment_with_skyportal.py \
  --selected-sources data/samples/gcn_grandma.json \
  --best-claims-path data/interim/gcn/event_enrichment/gcn_event_best_claims.parquet \
  --output-dir data/interim/gcn/event_enrichment
```

Outputs:

- `data/interim/gcn/event_enrichment/event_enrichment_comparison.csv`
- `data/interim/gcn/event_enrichment/event_enrichment_comparison.parquet`
- `data/interim/gcn/event_enrichment/enrichment_report.json`

This comparison answers questions like:

- does GCN add redshift where SkyPortal inventory did not have one?
- does GCN add spectroscopy context?
- does GCN add host-candidate context?
- does GCN provide T90 or trigger-time information?
- how many events receive high-value enrichment?

## Current comparison fields

The comparison table currently keeps compact fields such as:

- `source_id`
- `has_gcn_match`
- `match_status`
- `n_matched_circulars`
- `n_claims`
- `skyportal_has_redshift`
- `gcn_has_redshift`
- `gcn_adds_redshift`
- `skyportal_has_classification`
- `gcn_has_classification`
- `gcn_adds_classification`
- `skyportal_has_spectroscopy`
- `gcn_has_spectroscopy`
- `gcn_adds_spectroscopy`
- `skyportal_has_host`
- `gcn_has_host_candidate`
- `gcn_adds_host_candidate`
- `gcn_has_t90`
- `skyportal_has_trigger_time`
- `gcn_has_trigger_time`
- `gcn_adds_trigger_time`
- `gcn_has_counterpart`
- `gcn_has_detection`
- `gcn_has_non_detection`
- `gcn_has_upper_limit`
- `n_enrichment_fields`
- `enrichment_priority`

Current priority interpretation:

- `high`
  - GCN adds redshift, or
  - GCN provides T90, or
  - GCN provides counterpart context together with added spectroscopy
- `medium`
  - GCN adds trigger time, host-candidate context, upper limits, or
    non-detection context
- `low`
  - some tracked enrichment signal exists, but not enough to fall into the
    higher-value groups above
- `none`
  - the event had GCN claims, but none of the currently tracked enrichment
    signals were present

`n_enrichment_fields` counts the currently tracked useful signals exposed in the
comparison table. Today that includes:

- added redshift
- added classification
- added spectroscopy
- added host-candidate context
- T90 present in GCN
- added trigger time
- counterpart context
- detection context
- non-detection context
- upper-limit context

## What to inspect after Step C

Main files to inspect:

- `gcn_event_best_claims.csv`
  - compact best candidates per matched event
- `event_enrichment_comparison.csv`
  - direct GCN-vs-SkyPortal comparison
- `enrichment_report.json`
  - quick counts by enrichment type and priority

`enrichment_report.json` is the fastest way to see:

- how many matched events got claims;
- how many got useful enrichment;
- how many got redshift, T90, trigger-time additions, counterpart, or host additions.
