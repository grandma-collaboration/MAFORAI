# Event Review Table For Astronomer Validation

## Goal

This stage builds the final human-review table used to validate the most useful
GCN-derived fields before they are treated as candidate corpus enrichments.

The table is intentionally compact and review-oriented:

- one row per `source_id + field_name`;
- only the fields worth validating are kept;
- each row preserves short evidence from the matched GCN Circular.
- it is designed to be the direct base for the later astronomer-facing Excel export.

## Entry points

| File | Role |
|---|---|
| `scripts/gcn/05c_build_event_review_table.py` | Build the final review table |
| `scripts/gcn/06_export_astronomer_review_xlsx.py` | Export the curated astronomer-facing workbook |
| `src/skyportal_corpus/extraction/gcn_event_review.py` | Shared logic for field-by-field review rows |
| `src/skyportal_corpus/extraction/gcn_event_review_export.py` | Curated Excel export for astronomer delivery |

## Inputs

- `data/interim/skyportal/skyportal_event_baseline.parquet`
- `data/interim/gcn/event_enrichment/gcn_event_best_claims.parquet`
- `data/interim/gcn/event_extraction/gcn_core_claims.parquet`

## Typical command

```bash
python scripts/gcn/05c_build_event_review_table.py \
  --skyportal-baseline-path data/interim/skyportal/skyportal_event_baseline.parquet \
  --best-claims-path data/interim/gcn/event_enrichment/gcn_event_best_claims.parquet \
  --claims-path data/interim/gcn/event_extraction/gcn_core_claims.parquet \
  --output-dir data/interim/gcn/event_validation
```

## Outputs

- `data/interim/gcn/event_validation/gcn_event_review_table.csv`
- `data/interim/gcn/event_validation/gcn_event_review_table.parquet`

## Curated Excel export

After the canonical review table exists, export the astronomer-facing workbook:

```bash
python scripts/gcn/06_export_astronomer_review_xlsx.py \
  --review-table-path data/interim/gcn/event_validation/gcn_event_review_table.csv \
  --output-path data/interim/gcn/event_validation/astronomer_review/gcn_event_review_for_astronomer_high.xlsx
```

Workbook output:

- `data/interim/gcn/event_validation/astronomer_review/gcn_event_review_for_astronomer_high.xlsx`

The workbook keeps two sheets:

- `review_high`
- `legend`

`review_high` is intentionally a curated subset of the canonical review table.
It also preserves `skyportal_value_source`, so astronomers can see whether the
SkyPortal-side value came from native metadata, summary extraction, tag
normalization, or a combination of those layers.

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
| `skyportal_value` | Compact value already present in the prebuilt SkyPortal baseline |
| `skyportal_value_source` | Where that SkyPortal-side value came from: `native`, `summary_extracted`, `tag_normalized`, or their ordered combination |
| `gcn_candidate_value` | Candidate recovered from matched GCN Circulars; for `counterpart`, this can be the union of several normalized counterpart types |
| `gcn_candidate_context` | Short context such as `spectroscopic`, `optical afterglow`, or, for `counterpart`, the compact union of representative raw labels |
| `comparison_status` | Compact relation between the SkyPortal value and the GCN candidate |
| `circular_id` | GCN Circular used for that candidate; for `counterpart`, this can be a compact list of representative circulars |
| `evidence_text` | Short evidence fragment from the Circular; for `counterpart`, this can be a compact union of representative evidence snippets |
| `astronomer_decision` | Manual review column, initialized as `pending` |
| `validated_value` | Manual column for the accepted value |
| `astronomer_notes` | Manual notes column |

## `skyportal_value_source`

This column explains how the SkyPortal-side value entered the baseline.

Allowed values:

- `native`
  - the value already existed in the compact structured SkyPortal fields
- `summary_extracted`
  - the value was re-extracted from `source_summary`
- `tag_normalized`
  - the value came from normalized astronomer tags
- combinations such as `native+summary_extracted`
  - the baseline already had the same field from more than one SkyPortal-side layer

## Comparison status values

- `missing_in_skyportal`
  - GCN provides a value and the SkyPortal baseline does not
- `same_or_consistent`
  - both sides appear consistent
- `complementary_context`
  - SkyPortal already had some value, but GCN adds useful context
- `possible_conflict`
  - the GCN candidate does not look consistent with the SkyPortal-side value
- `gcn_only_context_flag`
  - GCN adds contextual information such as spectroscopy, counterpart, or host-candidate mention


## Curated workbook rules

The astronomer-facing workbook is filtered and reordered for easier manual review.

Included `comparison_status` values in `review_high`:

- `possible_conflict`
- `missing_in_skyportal`
- `complementary_context`
- `gcn_only_context_flag`

Excluded from the workbook:

- `same_or_consistent`

Additional field filters:

- `complementary_context` is exported only for `t90` and `counterpart`
- `gcn_only_context_flag` is exported only for `counterpart` and `host_candidate`

Sorting inside `review_high`:

1. `possible_conflict`
2. `missing_in_skyportal`
3. `complementary_context`
4. `gcn_only_context_flag`

Then by:

- `source_id`
- `field_name`
- `circular_id`

This keeps the workbook grouped by event inside each `comparison_status` block,
so astronomers can review all rows of the same source together.


## Practical use

Its purpose is to make manual scientific review easier by placing, side by
side:

- the compact value already present in the SkyPortal baseline;
- the provenance of that SkyPortal-side value;
- the candidate value recovered from GCN;
- one short evidence fragment;
- the manual columns needed to validate or correct the final value.
