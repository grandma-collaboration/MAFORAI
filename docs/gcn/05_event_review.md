# Event Review Table For Astronomer Validation

## Goal

This stage builds the final human-review table used to validate the most useful
GCN-derived fields before they are treated as candidate corpus enrichments.

The table is intentionally compact and review-oriented:

- one row per `source_id + field_name`;
- only the fields worth validating are kept;
- each row preserves short evidence from the matched GCN Circular.

## Entry points

| File | Role |
|---|---|
| `scripts/gcn/05c_build_event_review_table.py` | Build the final review table |
| `src/skyportal_corpus/extraction/gcn_event_review.py` | Shared logic for field-by-field review rows |

## Inputs

- `data/samples/gcn_grandma.json`
- `data/interim/gcn/event_enrichment/gcn_event_best_claims.parquet`
- `data/interim/gcn/event_extraction/gcn_core_claims.parquet`

## Typical command

```bash
python scripts/gcn/05c_build_event_review_table.py \
  --selected-sources data/samples/gcn_grandma.json \
  --best-claims-path data/interim/gcn/event_enrichment/gcn_event_best_claims.parquet \
  --claims-path data/interim/gcn/event_extraction/gcn_core_claims.parquet \
  --output-dir data/interim/gcn/event_validation
```

## Outputs

- `data/interim/gcn/event_validation/gcn_event_review_table.csv`
- `data/interim/gcn/event_validation/gcn_event_review_table.parquet`

## Fields currently reviewed

- `redshift`
- `trigger_time`
- `t90`
- `duration_class`
- `counterpart`
- `spectroscopy`
- `host_candidate`

## Output columns

| Column | Meaning |
|---|---|
| `source_id` | SkyPortal-side event identifier |
| `groups` | Compact GRANDMA-related group context |
| `field_name` | The field being validated |
| `skyportal_value` | Compact value already present in `gcn_grandma.json` |
| `gcn_candidate_value` | Best candidate recovered from matched GCN Circulars |
| `gcn_candidate_context` | Short context such as `spectroscopic`, `optical afterglow`, or an instrument name |
| `comparison_status` | Compact relation between the SkyPortal value and the GCN candidate |
| `circular_id` | GCN Circular used for that candidate |
| `evidence_text` | Short evidence fragment from the Circular |
| `claim_confidence` | Claim confidence from Step B |
| `review_priority` | Compact priority for human validation |
| `astronomer_decision` | Manual review column, initialized as `pending` |
| `validated_value` | Manual column for the accepted value |
| `astronomer_notes` | Manual notes column |

## Comparison status values

- `missing_in_skyportal`
  - GCN provides a value and the compact SkyPortal base does not
- `same_or_consistent`
  - both sides appear consistent
- `complementary_context`
  - SkyPortal already had some value, but GCN adds useful context
- `possible_conflict`
  - the GCN candidate does not look consistent with the SkyPortal-side value
- `gcn_only_context_flag`
  - GCN adds contextual information such as spectroscopy, counterpart, or host-candidate mention

## Review priority

- `high`
  - `redshift`
  - `trigger_time`
  - `t90`
  - any row marked as `possible_conflict`
- `medium`
  - `duration_class`
  - `counterpart`
  - `spectroscopy`
  - `host_candidate`

## Practical use

Its purpose is to make manual scientific review easier by placing, side by
side:

- the compact value already present in SkyPortal;
- the candidate value recovered from GCN;
- one short evidence fragment;
- one simple review priority.
