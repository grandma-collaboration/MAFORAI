# Event-Level GCN Enrichment

## Goal

This stage aggregates the Step-B claims into compact event-level enrichment
candidates and compares them against a richer prebuilt SkyPortal baseline built
from:

- native compact fields already present in `gcn_grandma.json`;
- claims re-extracted from `source_summary`;
- normalized semantic categories derived from compact raw `tags`.

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

- `data/interim/skyportal/skyportal_event_baseline.parquet`
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
- within the same redshift method/confidence tier, prefer more specific rules
  such as `photo-z` over a generic `z = ...` match;
- prefer higher claim confidence;
- prefer explicit numeric values when choosing T90-like candidates;
- for trigger time, keep only absolute timestamps with date context or trigger
  MJD values.

## Step 05b. Compare GCN enrichment against SkyPortal

Typical command:

```bash
python scripts/gcn/05b_compare_gcn_enrichment_with_skyportal.py \
  --skyportal-baseline-path data/interim/skyportal/skyportal_event_baseline.parquet \
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

The prebuilt SkyPortal baseline keeps one row per event and combines three
layers:

- native structured values such as `redshift`, `trigger_time`,
  `spectrum_exists`, `has_host`, `classification_labels`, `comment_exists`,
  and `num_det_global`;
- summary-derived compact claims extracted directly from `source_summary`;
- normalized tag categories derived from the raw tag names stored in
  `gcn_grandma.json`.

Tags are treated as authoritative astronomer categorization when present.
Only the intentionally kept semantic families are normalized:

- temporal classes
  - `LongGRB -> long`
  - `ShortGRB -> short`
  - `Ultralong -> ultralong`
- counterpart contexts
  - `Optical -> optical`
  - `NoOptical -> no_optical`
  - `LAT -> lat`
- instrument contexts
  - `Swift -> swift`
  - `Fermi -> fermi`
  - `SVOM -> svom`
  - `EP -> ep`
  - `INTEGRAL -> integral`
- follow-up contexts
  - `Followup -> followup`
  - `noFollowup -> no_followup`
- classification contexts
  - `Supernova -> supernova`
  - `CV -> cv`
  - `GWcandidate -> gw_candidate`
  - `BBH -> bbh`

## Current comparison fields

The comparison table currently keeps compact fields such as:

- `source_id`
- `has_gcn_match`
- `match_status`
- `n_matched_circulars`
- `n_claims`
- `skyportal_has_redshift`
- `baseline_redshift_values`
- `baseline_has_redshift`
- `gcn_has_redshift`
- `gcn_adds_redshift`
- `baseline_classification_flags`
- `baseline_has_classification`
- `skyportal_has_classification`
- `gcn_has_classification`
- `gcn_adds_classification`
- `baseline_instrument_contexts`
- `skyportal_has_spectroscopy`
- `baseline_has_spectroscopy`
- `gcn_has_spectroscopy`
- `gcn_adds_spectroscopy`
- `skyportal_has_host`
- `baseline_has_host_candidate`
- `gcn_has_host_candidate`
- `gcn_adds_host_candidate`
- `baseline_t90_values`
- `baseline_has_t90`
- `gcn_has_t90`
- `gcn_adds_t90`
- `baseline_duration_classes`
- `baseline_has_duration_class`
- `gcn_has_duration_class`
- `gcn_adds_duration_class`
- `skyportal_has_trigger_time`
- `baseline_trigger_time_values`
- `baseline_has_trigger_time`
- `gcn_has_trigger_time`
- `gcn_adds_trigger_time`
- `baseline_counterpart_contexts`
- `baseline_has_counterpart`
- `gcn_has_counterpart`
- `gcn_adds_counterpart`
- `baseline_has_detection`
- `gcn_has_detection`
- `gcn_adds_detection`
- `baseline_has_non_detection`
- `gcn_has_non_detection`
- `gcn_adds_non_detection`
- `baseline_has_upper_limit`
- `gcn_has_upper_limit`
- `gcn_adds_upper_limit`
- `baseline_followup_contexts`
- `n_enrichment_fields`
- `enrichment_priority`

Important comparison rule:

- `gcn_adds_*` is true only when the GCN side has that information and the
  full SkyPortal baseline does not already have it through native fields,
  `source_summary`, or normalized tags.
- `NoOptical` contributes only to counterpart context. It does not count as
  generic non-detection.

Current priority interpretation:

- `high`
  - GCN adds redshift, or
  - GCN adds T90, or
  - GCN adds counterpart context together with added spectroscopy
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
- added T90
- added duration-class context
- added trigger time
- added counterpart context
- added detection context
- added non-detection context
- added upper-limit context

## What to inspect after Step C

Main files to inspect:

- `gcn_event_best_claims.csv`
  - compact best candidates per matched event
- `data/interim/skyportal/skyportal_event_baseline.csv`
  - compact SkyPortal-side baseline before final comparison
- `event_enrichment_comparison.csv`
  - direct GCN-vs-SkyPortal comparison
- `enrichment_report.json`
  - quick counts by enrichment type and priority

`enrichment_report.json` is the fastest way to see:

- how many matched events got claims;
- how many got useful enrichment;
- how many got redshift, T90, trigger-time additions, counterpart, or host additions.
