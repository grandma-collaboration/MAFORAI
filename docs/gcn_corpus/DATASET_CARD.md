# GCN Circular Annotation Corpus

## What this is

This corpus contains annotations extracted by deterministic rules from the GCN Circular archive. Each annotation is one row carrying the exact text span it covers and the rule that produced it. Its perimeter is the archive alone: it uses no external event registry and does not group circulars by event.

## Contents

| Table | Rows | Columns | Description |
|---|---:|---:|---|
| `circulars.parquet` | 12,012 | 15 | Canonical circular text, publication and edit metadata, hashes, and annotation counts. |
| `evidence_spans.parquet` | 63,277 | 21 | Scientific evidence spans with labels, normalized fields, and rule provenance. |
| `photometry_spans.parquet` | 37,795 | 33 | Photometric detections and upper limits with measurement fields and rule provenance. |
| `vocabulary_coverage.parquet` | 57 | 4 | One row per declared controlled-vocabulary value, including values used by no extracted row. |

The circulars run from 2023-01-01 through 2026-07-19. The two layers contain 101,072 annotations: 63,277 `EVENT_EVIDENCE` spans and 37,795 `PHOTOMETRIC_MEASUREMENT` spans. They were produced by 113 distinct rules in 15 extractors.

## Provenance

The source archive is:

```text
data/raw/gcn/circulars/archive_json/20260720_093324/extracted/archive.json/
```

The extraction represented here has source timestamp `2026-07-20T07:51:22.888128+00:00`. The corpus manifest records this extractor set:

| Extractor | Version |
|---|---|
| `event-identity-v1` | `0.1` |
| `trigger-time-v1` | `0.1` |
| `localization-v1` | `0.1` |
| `trigger-instrument-v1` | `0.1` |
| `redshift-v1` | `0.1` |
| `duration-v1` | `0.1` |
| `high-energy-v1` | `0.1` |
| `negative-statement-v1` | `0.1` |
| `lightcurve-evolution-v1` | `0.1` |
| `counterpart-association-v1` | `0.1` |
| `classification-interpretation-v1` | `0.1` |
| `host-context-v1` | `0.1` |
| `spectroscopy-v1` | `0.1` |
| `photometry-row-v1` | `0.1` |
| `photometry-prose-v1` | `0.1` |

`EVENT_EVIDENCE` records event identities, trigger properties, localization, physical interpretation, counterpart and host context, spectroscopy, and other scientific claims. `PHOTOMETRIC_MEASUREMENT` records detections and upper limits together with magnitude, band, observation-time, exposure, and instrument fields where a rule resolved them.

The corpus records what these extraction rules produced. When measurement reveals a rule defect, the output remains unchanged rather than being repaired during corpus normalization.

## How it was produced

| Stage | Transformation | Role |
|---|---|---|
| `scripts/gcn_corpus/01_extract.py` | Archive to `data/interim/gcn_corpus/` | Runs the 15 extractors and writes their output without corpus decisions. |
| `scripts/gcn_corpus/02_normalise.py` | Interim tables to `data/gcn_corpus/` | Applies the 13 declared corpus decisions and writes the final tables and manifest. |

Both stages are deterministic. [The reproducibility notebook](../../notebooks/gcn_corpus/D_reproducibility.ipynb) records a clean regeneration in which eight of the nine interim and final artifacts reproduce byte for byte. The final corpus `manifest.json` legitimately varies because its `generated_at` field records wall-clock time by design and does not participate in `content_hash`. Current Parquet hashes agree with both manifests. Neither manifest stores elapsed runtime, and this card did not rerun extraction, so no independently measured stage runtime is claimed here; the reproducibility notebook is the record for machine-specific timing.

## Reading a span row

The annotation key is `(circular_id, layer, span_start, span_end, span_index)`, where `layer` is implied by the span table. `span_index` is necessary because 407 offset ranges carry multiple annotations; removing it would collapse 494 rows.

Offsets are character positions in `circulars.canonical_text`. For all 101,072 annotations, the following property was verified with zero failures:

```python
canonical_text[span_start:span_end] == text
```

The provenance columns are `extractor_id`, `extractor_version`, `rule_id`, `method`, `confidence`, `needs_review`, and `schema_version`. They identify the code path and rule responsible for a row and preserve the extractor's own uncertainty signal.

`needs_review` and `comment` record what a rule could not resolve. There are 11,815 review-flagged annotations: 5,583 evidence spans and 6,232 photometry spans. Every flagged row has a comment.

## Added columns

| Column | Table | What it records |
|---|---|---|
| `n_evidence` | `circulars.parquet` | Number of evidence spans linked to the circular. |
| `n_photometry` | `circulars.parquet` | Number of photometry spans linked to the circular. |
| `has_annotations` | `circulars.parquet` | Whether either annotation count is non-zero. |
| `has_mojibake` | Circulars and both span tables | Whether the row contains Unicode replacement character U+FFFD in the fields checked for that table. |
| `is_overlapping` | Both span tables | Whether the span intersects another span in the same circular and layer. No overlap is resolved or removed. |
| `exposure_time_numeric` | `photometry_spans.parquet` | Numeric parsing of `exposure_time_raw`, with null retained for absent or non-parsing input. |
| `was_edited` | `circulars.parquet` | Whether `edited_on_utc` is present and differs from `created_on_utc`; this column originates in extraction rather than normalization. |

## Vocabulary coverage

`vocabulary_coverage.parquet` contains one row for every value declared by each model field with a controlled vocabulary and the number of corpus rows carrying it. It covers 57 values across seven fields. Seventeen declared values carry no rows:

| Layer | Field | Values with zero rows |
|---|---|---|
| `EVENT_EVIDENCE` | `target` | `unknown` |
| `PHOTOMETRIC_MEASUREMENT` | `certainty` | `candidate`, `rejected`, `unclear` |
| `PHOTOMETRIC_MEASUREMENT` | `measurement_type` | `non_detection`, `unclear` |
| `PHOTOMETRIC_MEASUREMENT` | `obs_time_reference` | `observation_mid`, `observation_start`, `unknown` |
| `PHOTOMETRIC_MEASUREMENT` | `obs_time_type` | `calendar_date`, `other_timezone`, `start_time_plus_exposure`, `unclear` |
| `PHOTOMETRIC_MEASUREMENT` | `target` | `host`, `instrument`, `nearby_galaxy`, `unknown` |

Four temporal values among them were introduced by annotators during the INCEpTION validation campaign while no current extraction rule emits them: `calendar_date`, `start_time_plus_exposure`, `observation_mid`, and `observation_start`. Keeping zero-row values makes the gap between the declared schema and current rule coverage visible.

## Time

`created_on_utc` is the instant a circular became public. It is stored as an ISO-8601 string; all 12,012 values are non-null, parse to UTC, and carry the explicit `+00:00` offset. `was_edited` marks the 653 circulars whose edit timestamp is later than the publication timestamp.

| Edit gap statistic | Hours |
|---|---:|
| Minimum | 0.04 |
| 25th percentile | 4.09 |
| Median | 14.99 |
| 75th percentile | 48.08 |
| 90th percentile | 355.68 |
| 95th percentile | 4,871.83 |
| Maximum | 28,791.06 |

Edited circulars account for 5,437 annotations: 3,825 evidence spans and 1,612 photometry spans. The retained canonical body is the edited body, so its text may postdate the publication instant used to date the circular.

## Known limitations

- Layer coverage is uneven. There are 8,048 circulars with evidence but no photometry and 77 with photometry but no evidence.
- Fifty-seven circulars produce no annotation in either layer. Their strongest measured subject commonality is the case-insensitive phrase `not a`, present in 29 of the 57 subjects versus 241 of all 12,012 subjects.
- `photometric_band` is free text, with 207 distinct states when null is included and 2,837 null rows. Four measured anomaly populations prevent treating it as a closed band vocabulary:

  | Population | Distinct values | Rows | Examples |
  |---|---:|---:|---|
  | Alternate apostrophe forms of the same `r` filter | 2 | 174 | `r'` (171), `r’` (3) |
  | A following table cell retained after a tab | 17 | 17 | `m625\t17.64` |
  | Magnitude-with-error strings in the band field | 2 | 2 | `19.20±0.14` |
  | Values that are not filters | 54 | 180 | `Lim`, `n/d`, `4x180s`, `13:54:44` |

- Of 32,540 populated `exposure_time_raw` values, 2,572 do not parse as a number: 7.90% across 1,110 distinct forms. Failures include unit-bearing durations, multiplication or stacking notation, prose descriptions, and misplaced filter or clock values.
- Four annotations carry U+FFFD, all in the photometry layer, while 39 circulars carry it in their canonical text. The original character cannot be recovered from U+FFFD alone.
- Rule output is uneven. `photometry_row.pipe` produces 30,275 rows and `event_identity.grb` 16,566; together they account for 46.34% of all annotations. Twenty-two of the 113 rules fire fewer than ten times, including six that fire once.

## Known rule defects

These outputs are recorded rather than repaired. A corpus regenerated after correcting the rules will differ.

- The photometry table-row parser can assign one uncertainty across several measurements when a row carries multiple magnitude columns.
- `instrument_provenance=inferred_column` attributes classification labels such as `SN_LIKE` to the `instrument` field on 417 rows.
- No rule covers the exact phrase `is not an astrophysical event`. It appears in 11 circular subjects, while zero annotation spans cover that exact phrase.
- `PHOTOMETRIC_SYSTEMS` is declared, but no model validator references it; consequently `photometric_system` accepts values outside that declaration and is absent from `vocabulary_coverage.parquet`.

## Terms of use

This corpus is internal to the GRANDMA collaboration and IJCLab. It is not for redistribution. It is derived from the public GCN Circular archive.

## Regenerating this corpus

The circular archive shown under Provenance must be present. From the repository root, run:

```bash
/home/meneses/project_astronomical/MAFORAI/.venv/bin/python /home/meneses/project_astronomical/MAFORAI/scripts/gcn_corpus/01_extract.py
/home/meneses/project_astronomical/MAFORAI/.venv/bin/python /home/meneses/project_astronomical/MAFORAI/scripts/gcn_corpus/02_normalise.py
```

Stage elapsed times are not stored in either manifest and therefore cannot be recovered from the corpus alone. The clean-run timings and the determinism check — eight of nine artifacts byte-stable, with the final corpus manifest varying only because `generated_at` records wall-clock time by design and does not participate in `content_hash` — are recorded in [the reproducibility notebook](../../notebooks/gcn_corpus/D_reproducibility.ipynb).
