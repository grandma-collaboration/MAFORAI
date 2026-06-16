# Event Matching Against GCN Circulars

## Goal

This stage links the compact SkyPortal-side event universe to the relevant GCN
Circulars.

Current input universe:

```text
data/samples/gcn_grandma.json
```

The matching is conservative. It uses event IDs, aliases, small formatting
variants, and the GCN fields `subject`, `event_id`, and `body`.

## Entry points

| File | Role |
|---|---|
| `scripts/gcn/03a_build_event_search_terms.py` | Build reviewable search terms from the event universe |
| `scripts/gcn/03b_match_events_to_circulars.py` | Match those terms against yearly GCN indexes |
| `scripts/gcn/03c_build_event_match_summary.py` | Build deduplicated associations and event summary |
| `src/skyportal_corpus/extraction/gcn_event_matching.py` | Shared matching, scoring, associations, and summary logic |

## Default inputs

SkyPortal-side input:

```text
data/samples/gcn_grandma.json
```

GCN-side input root:

```text
data/interim/gcn/circulars
```

Default year range:

- `2023`
- `2024`
- `2025`
- `2026`

## Step 03a. Build search terms

Typical command:

```bash
python scripts/gcn/03a_build_event_search_terms.py \
  --selected-sources data/samples/gcn_grandma.json \
  --output-dir data/interim/gcn/event_matching
```

Outputs:

- `data/interim/gcn/event_matching/event_search_terms.csv`
- `data/interim/gcn/event_matching/event_search_terms.parquet`

Each row keeps:

- `source_id`
- `gcn_source_type`
- `origin_field`
- `origin_value`
- `search_term`
- `search_term_normalized`
- `variant_type`
- `variant_rank`
- `is_trigger_like`
- `groups`

Less obvious fields in `event_search_terms`:

| Field | Meaning | Where values come from |
|---|---|---|
| `variant_type` | Tells whether the term is the original event string or a generated conservative variant | Set in `build_event_search_term_rows` as `original`, `compact_variant`, or `spaced_variant` |
| `variant_rank` | Small priority number used to sort/prefer original terms before generated variants | `0` for the original term, `1` for generated variants |
| `is_trigger_like` | Marks internal timestamp-like IDs that look more generic and should score lower | Computed by `is_trigger_like_term` with the `TRIGGER_LIKE_PATTERN` regex |

What this stage does:

- uses `id` and `aliases` from `gcn_grandma.json`;
- creates conservative variants such as `GRB250424A` and `GRB 250424A`;
- preserves the original source of each term;

## Step 03b. Match terms against Circulars

Typical command:

```bash
python scripts/gcn/03b_match_events_to_circulars.py \
  --terms-path data/interim/gcn/event_matching/event_search_terms.parquet \
  --gcn-root data/interim/gcn/circulars \
  --year-from 2023 \
  --year-to 2026 \
  --output-dir data/interim/gcn/event_matching
```

Outputs:

- `data/interim/gcn/event_matching/event_gcn_matches.csv`
- `data/interim/gcn/event_matching/event_gcn_matches.parquet`

This stage searches the fields:

- `subject`
- `event_id`
- `body`

Scoring currently used:

- `100` for exact original-term hit in `subject`
- `95` for exact original-term hit in `event_id`
- `80` for generated-variant hit in `subject`
- `75` for exact original-term hit in `body`
- `60` for generated-variant hit in `body`
- `40` for trigger-like internal matches

Confidence buckets:

- `high_confidence` Assigned when `match_score >= 80`
- `medium_confidence` Assigned when `60 <= match_score < 80`
- `low_confidence`  Assigned when `match_score < 60`

For `event_gcn_match_summary.csv`, rows with `status = no_match` keep
`best_match_score = 0` and leave `best_confidence_level` empty. The
`no_match` state lives in `status`, not in the confidence bucket itself.


Less obvious fields in `event_gcn_matches`:

| Field | Meaning | Where values come from |
|---|---|---|
| `match_score` | Numeric strength assigned to that raw hit | Computed by `classify_match_score` from `matched_field`, `variant_type`, and `is_trigger_like` |
| `confidence_level` | Bucket derived from `match_score` | Computed by `confidence_level_from_score`: `high_confidence`, `medium_confidence`, `low_confidence` |

## Step 03c. Build associations and match summary

Typical command:

```bash
python scripts/gcn/03c_build_event_match_summary.py \
  --matches-path data/interim/gcn/event_matching/event_gcn_matches.parquet \
  --terms-path data/interim/gcn/event_matching/event_search_terms.parquet \
  --output-dir data/interim/gcn/event_matching
```

Outputs:

- `data/interim/gcn/event_matching/event_gcn_associations.csv`
- `data/interim/gcn/event_matching/event_gcn_associations.parquet`
- `data/interim/gcn/event_matching/event_gcn_match_summary.csv`

Granularity:

- `event_gcn_matches`: one row per raw term hit;
- `event_gcn_associations`: one best row per `source_id + circular_id`;
- `event_gcn_match_summary`: one summary row per event.

Important behavior:

- `event_gcn_match_summary.csv` still includes events without match;
- rows are ordered with matched events first and `no_match` last;
- later extraction steps only carry forward the matched subset.

Less obvious fields in `event_gcn_associations`:

| Field | Meaning | Where values come from |
|---|---|---|
| `best_matched_term` | The term that won after deduplicating all raw hits for one `source_id + circular_id` pair | Taken from the best row inside `build_event_gcn_associations_dataframe` |
| `best_matched_field` | Which GCN field produced that winning hit | Comes from the winning row: `subject`, `event_id`, or `body` |
| `best_match_type` | Whether the winning hit came from an original term, generated variant, or trigger-like term | Comes from `match_type` on the winning row |
| `best_match_score` | Numeric score of the winning hit for that event-circular association | Comes from `match_score` on the winning row |
| `best_confidence_level` | Confidence bucket of that winning hit | Comes from `confidence_level` on the winning row |


## What to inspect after Step A

Main files to inspect:

- `event_gcn_match_summary.csv`
  - which events matched
  - best score
  - status per event
- `event_gcn_associations.csv`
  - which Circulars are attached to each event after deduplication


## Handoff to Step B

The claim-extraction stage starts from:

- `data/interim/gcn/event_matching/event_gcn_associations.parquet`
- `data/interim/gcn/event_matching/event_gcn_match_summary.csv`

Only matched events continue into Step B.
