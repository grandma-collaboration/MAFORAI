# Claim Extraction From Matched Circular Bodies

## Goal

This stage extracts structured, traceable claims from GCN Circulars that were
already matched to SkyPortal events in Step A.

The output is not final event truth. Each extracted value is stored as a claim
with evidence, provenance, and the exact rule that produced it.

## Entry points

| File | Role |
|---|---|
| `scripts/gcn/04a_extract_core_claims.py` | Extract claim rows from matched Circulars |
| `scripts/gcn/04b_build_claim_summary.py` | Build one compact event-level summary from those claims |
| `src/skyportal_corpus/extraction/gcn_core_claims.py` | Shared extraction and summary logic |

## Inputs

Main machine inputs:

- `data/interim/gcn/event_matching/event_gcn_associations.parquet`
- `data/interim/gcn/event_matching/event_gcn_match_summary.csv`

Important behavior:

- this stage only processes the matched subset from Step A;
- events with `no_match` are not carried into Step B outputs;
- the extractor reads raw Circular bodies through `raw_file_path`.

## Step 04a. Extract core claims

Typical command:

```bash
python scripts/gcn/04a_extract_core_claims.py \
  --associations-path data/interim/gcn/event_matching/event_gcn_associations.parquet \
  --output-dir data/interim/gcn/event_extraction
```

Outputs:

- `data/interim/gcn/event_extraction/gcn_core_claims.csv`
- `data/interim/gcn/event_extraction/gcn_core_claims.parquet`
- `data/interim/gcn/event_extraction/extraction_report.json`
- `data/interim/gcn/event_extraction/extraction_errors.jsonl`

Each claim row keeps fields such as:

- `source_id`
- `circular_id`
- `year`
- `created_at_iso`
- `subject`
- `claim_type`
- `raw_value`
- `normalized_value`
- `instrument_if_any`
- `evidence_text`
- `extraction_rule`
- `claim_confidence`
- `source_field`
- `raw_file_path`
- `best_match_score`
- `best_confidence_level`

## What `claim_type` means

`claim_type` is the semantic family of the extracted information.

Current active claim types:

| `claim_type` | What it stores | Main notes |
|---|---|---|
| `instrument_mention` | Mention of a known mission, telescope, or instrument | Uses a fixed instrument catalog |
| `trigger_time_t0` | Trigger time, T0-like timestamp, MJD, or relative trigger time | Comes from explicit timing phrases |
| `duration_t90` | Numeric burst duration / T90 value | Keeps the parsed numeric value in `normalized_value` |
| `duration_class` | Long/short duration label | Keeps normalized value such as `long` or `short` |
| `redshift` | Redshift value with context | Only extracted when redshift context is strong |
| `counterpart_type` | Counterpart or afterglow mention | Keeps counterpart family in `normalized_value` |
| `detection_status` | Detection, non-detection, upper-limit-like status, or `not_grb`/`false_alarm` state | Line-based logic where negation dominates |
| `upper_limit_simple` | Simple magnitude upper limit | Separate from `detection_status` so the numeric limit is preserved |
| `spectroscopy_mention` | Spectroscopy mention | Keyword-based or instrument-based |
| `host_candidate_mention` | Mention of a host galaxy or host candidate | Conservative host context only |
| `classification_or_interpretation` | Event interpretation or classification | Examples: `afterglow`, `supernova`, `not_grb`, `retraction` |


## What `extraction_rule` means

`extraction_rule` is the exact rule name that fired inside the extractor.
It tells you how the claim was found, not just what type of claim it is.

The extractor is rule-based. Some rules use direct regex patterns, and some use
small line-level keyword checks.

## Active `extraction_rule` catalog

### `instrument_mention`

- `instrument_catalog`
  Looks for exact or conservative regex matches from the internal instrument
  catalog, such as `Swift/XRT`, `Fermi GBM`, `EP-WXT`, or `VLT/X-shooter`.

### `trigger_time_t0`

- `trigger_t0_explicit`
  Looks for explicit `T0 = ...` or `T0: ...` patterns.
- `trigger_tb_explicit`
  Looks for `Tb = ...` or `TimeTb = ...`.
- `trigger_iso_timestamp`
  Looks for ISO-like timestamps such as `2025-01-03T09:56:33.551 UTC`, and keeps
  them only when the surrounding text looks trigger-related.
- `trigger_mjd`
  Looks for `MJD = ...`.
- `trigger_ut_context`
  Looks for phrases like `At 13:22:50 UT` and keeps them only when nearby text
  suggests trigger context.
- `trigger_relative_t`
  Looks for relative timing like `T+120 s`, `T+3 hr`, or `T+1 day`.

### `duration_t90`

- `duration_t90_explicit`
  Looks for explicit `T90 ... 19 s` style expressions.
- `duration_t90_about`
  Looks for looser phrases such as `duration of about 40 sec`.

### `duration_class`

- `duration_class_long`
  Looks for explicit long-burst wording such as `long GRB` or `long-duration GRB`.
- `duration_class_short`
  Looks for explicit short-burst wording such as `short GRB` or `short-duration GRB`.
- `duration_class_long_likely`
  Looks for tentative long wording such as `likely LONG GRB`.
- `duration_class_short_relative`
  Looks for softer short wording such as `relatively short-duration GRB`.

### `redshift`

- `redshift_z_equals`
  Looks for expressions like `z = 2.31` or `z ~ 4.1`, but only keeps them if
  the local evidence also mentions redshift context.
- `redshift_photoz`
  Looks for `photo-z ...` patterns, again requiring redshift context nearby.

Important safeguard:

- the extractor rejects `z` values when the evidence looks like photometry in
  the `z` band, such as `mag z = 22.23` or `z-band`.

### `counterpart_type`

- `counterpart_counterpart`
  Looks for direct counterpart phrases like `optical counterpart`,
  `X-ray counterpart`, `radio counterpart`, `NIR counterpart`, or `UV counterpart`.
- `counterpart_afterglow`
  Looks for afterglow phrases like `optical afterglow`, `X-ray afterglow`,
  or `NIR afterglow`.
- `counterpart_candidate`
  Looks for `candidate counterpart`.

The specific counterpart family is stored in `normalized_value`, for example
`optical`, `xray`, `radio`, `nir`, `uv`, or `candidate_counterpart`.

### `detection_status`

- `detection_not_grb`
  Looks for explicit phrases such as `not a GRB`.
- `detection_false_alarm`
  Looks for `false alarm`.
- `detection_negative`
  Looks for strong non-detection phrases such as `we do not detect`,
  `not detected`, or `no detection`.
- `detection_upper_limit`
  Looks for upper-limit wording such as `upper limit` or `limiting magnitude`.
- `detection_positive`
  Looks for positive detection wording such as `we detect`, `was detected`,
  `was found`, or `afterglow detection`.

Important behavior:

- the extractor works line by line;
- negative wording is checked before positive wording;

### `upper_limit_simple`

- `upper_limit_band_gt`
  Looks for simple limits like `r > 23.5` or `H > 17.3`.
- `upper_limit_context`
  Looks for upper-limit wording plus a numeric magnitude in the same line.

### `spectroscopy_mention`

- `spectroscopy_keyword`
  Looks for words such as `spectroscopy`, `spectroscopic`, or `spectrum`.
- `spectroscopy_instrument`
  Looks for common spectroscopy-related instrument names such as `X-shooter`,
  `Gemini`, `Keck`, `GTC`, or `OSIRIS+`.

### `host_candidate_mention`

- `host_galaxy`
  Looks for `host galaxy`.
- `nearby_galaxy`
  Looks for `nearby galaxy`.
- `proposed_host`
  Looks for `proposed host`.
- `associated_galaxy`
  Looks for `associated galaxy`.
- `host_candidate`
  Looks for `host candidate` or `galaxy candidate`.

### `classification_or_interpretation`

- `candidate_afterglow`
  Looks for `candidate afterglow`.
- `afterglow`
  Looks for `afterglow`.
- `xray_transient`
  Looks for `X-ray transient`.
- `kilonova_candidate`
  Looks for `kilonova candidate`.
- `supernova`
  Looks for `supernova`.
- `type_ia`
  Looks for `Type Ia`.
- `type_ic_bl`
  Looks for `Type Ic-BL`.
- `agn`
  Looks for `AGN`.
- `stellar_flare`
  Looks for `stellar flare`.
- `solar_flare`
  Looks for `solar flare`.
- `not_grb`
  Looks for `not a GRB` or `is not a GRB`.
- `false_alarm`
  Looks for `false alarm`.
- `false_trigger`
  Looks for `false trigger`.
- `retraction`
  Looks for `retraction`.
- `galactic_transient`
  Looks for `Galactic Transient`.


## Step 04b. Build claim summary

Typical command:

```bash
python scripts/gcn/04b_build_claim_summary.py \
  --claims-path data/interim/gcn/event_extraction/gcn_core_claims.parquet \
  --match-summary-path data/interim/gcn/event_matching/event_gcn_match_summary.csv \
  --output-dir data/interim/gcn/event_extraction
```

Output:

- `data/interim/gcn/event_extraction/event_gcn_claim_summary.csv`

This summary has one row per matched event and answers compact questions like:

- does this event have trigger-time information?
- is there any T90 claim?
- is there any redshift claim?
- is there detection or non-detection context?
- is spectroscopy or host context mentioned?

Typical fields include:

- `n_claims`
- `n_circulars_with_claims`
- `has_trigger_time`
- `has_t90`
- `has_duration_class`
- `has_redshift`
- `has_counterpart`
- `has_detection`
- `has_non_detection`
- `has_upper_limit`
- `has_negative_interpretation`
- `has_retraction`
- `has_spectroscopy`
- `has_host_candidate`
- `instruments_found`
- `classification_flags`
- `best_redshift_value`
- `best_redshift_method`
- `best_t90_seconds`
- `best_duration_class`

## What to inspect after Step B

Main files to inspect:

- `gcn_core_claims.csv`
  Raw extracted claims with evidence and rule names.
- `event_gcn_claim_summary.csv`
  Compact per-event extraction overview.

`extraction_report.json` is the quick health check:

- number of associations read;
- number of Circulars processed;
- number of failures;
- number of claims extracted;
- counts by claim type;
- counts by confidence.

## Handoff to Step C

The enrichment stage starts from:

- `data/interim/gcn/event_extraction/gcn_core_claims.parquet`
- `data/interim/gcn/event_matching/event_gcn_match_summary.csv`
- `data/samples/gcn_grandma.json`

It uses only the claims already extracted here. It does not create new claims.
