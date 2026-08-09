# GCN Gold Annotation Corpus

## What this is

A human-validated annotation corpus over GCN circulars, grouped one document per
astronomical event, produced in INCEpTION by annotators of the GRANDMA collaboration.
It holds independent validations rather than a single merged consensus: every document
was worked by two to four annotators separately, and none of their layers were curated
into one. The pre-annotation baseline that annotators started from is carried alongside
their work, row for row, so the two can be compared directly.

## Contents

| table | rows | columns | description |
|---|---|---|---|
| documents.parquet | 10 | 5 | one row per source document: name, text length, sentence count, sha256 of the text |
| annotators.parquet | 28 | 10 | one row per (document, annotator) pair in scope, with INCEpTION's own workflow-state fields |
| evidence_spans.parquet | 6,615 | 20 | one row per ASTRO_EVIDENCE annotation, baseline or annotator |
| photometry_spans.parquet | 2,741 | 34 | one row per PHOTOMETRIC_MEASUREMENT annotation, baseline or annotator |
| event_summaries.parquet | 28 | 26 | one row per (document, annotator) EVENT_SUMMARY annotation, document-level, no offsets |

Measured: 10 documents, 10 distinct annotators, 28 (document, annotator) pairs.
6,615 ASTRO_EVIDENCE annotations, 2,741 PHOTOMETRIC_MEASUREMENT annotations, 28
EVENT_SUMMARY annotations. Document text length ranges from 16,577 to 108,145
characters, and sentence count from 157 to 1,038 sentences per document.

## Provenance

The export is at `data/inception/project-2026-08-08-072803`, dated 2026-08-08 in its
own path. It contains 10 source documents, one zipped annotation layer per annotator
per document, and one `INITIAL_CAS` zip per document holding the pre-annotation
baseline. Three custom layers are enabled:

- **ASTRO_EVIDENCE** — a span of text marking evidence for one of 15 categories
  (event identity, trigger time, localization, redshift, and others), with a target,
  a certainty, a free-text value, a unit and a comment.
- **PHOTOMETRIC_MEASUREMENT** — a span recording one photometric measurement
  (a detection or an upper limit), with system, magnitude or limit, error,
  observation time, exposure, instrument and comment.
- **EVENT_SUMMARY** — one document-level record per annotator synthesising the
  canonical event name, best trigger time, redshift, T90, localization,
  classification and interpretation.

The perimeter is every (document, annotator) pair in state `FINISHED`, 28 pairs.
Three users — `admin`, `Patrick`, `Thomas` — are excluded by name. None of their
annotation_documents entries ever reached `FINISHED` (admin: 5 `IN_PROGRESS`;
Patrick: 2 `IGNORE`, 1 `NEW`; Thomas: 1 `IGNORE`), so the exclusion does not change
the derived perimeter; it is applied explicitly rather than left to the state filter
alone.

## How it was produced

Two scripts, run in order:

| script | direction | does |
|---|---|---|
| `scripts/gcn_gold/01_flatten.py` | export → `data/interim/gcn_gold_corpus/` | shape only, takes no decisions |
| `scripts/gcn_gold/02_normalise.py` | interim → `data/gcn_gold_corpus/` | applies the fourteen normalisation decisions |

Both scripts are deterministic. Regenerating them from the export into a clean
directory reproduces all ten output files byte for byte, verified at the time this
card was written and in `notebooks/gcn_gold/D_reproducibility.ipynb`.

## What the annotators changed

| layer | baseline | accepted | corrected | created | deleted |
|---|---|---|---|---|---|
| evidence_spans | 1,683 | 4,590 | 224 | 113 | 5 |
| photometry_spans | 670 | 1,291 | 651 | 129 | 0 |

Acceptance rate over matched pairs (accepted / (accepted + corrected)):
5,881 / 6,756 = **87.0%**.

The features corrected most often, as a percentage of matched pairs in their layer:

| layer | feature | matched pairs | differing | pct |
|---|---|---|---|---|
| photometry_spans | comment | 1,942 | 574 | 29.6% |
| photometry_spans | instrument | 1,942 | 213 | 11.0% |
| evidence_spans | comment | 4,814 | 211 | 4.4% |
| photometry_spans | photometric_system | 1,942 | 131 | 6.7% |
| photometry_spans | obs_time_reference | 1,942 | 124 | 6.4% |
| photometry_spans | obs_time_raw | 1,942 | 69 | 3.6% |
| photometry_spans | exposure_time_raw | 1,942 | 39 | 2.0% |
| photometry_spans | photometric_band | 1,942 | 34 | 1.8% |

Most matched spans need no correction at all, and the fields that do change most are
context around a measurement (comment, instrument, system, time reference) rather
than its category. The extractor places spans well and fills their fields less well.

## Added columns

| column | table | what it records |
|---|---|---|
| match_status | both | `baseline`, `accepted`, `corrected`, `created` or `deleted`, against the matching baseline span |
| changed_fields | both | the list of features that differ from the baseline, for `corrected` rows only |
| comment_status | both | `extractor_guidance`, `annotator_note`, `annotator_removed` or `none` |
| is_overlapping | both | whether this span overlaps another span in the same (document, layer_source) |
| has_category | both | whether the row's category feature (`label` or `measurement_type`) is populated; null on synthetic `deleted` rows |
| is_annotator_note | both | a `created` row with no category but a non-blank comment |
| extractor_vocabulary_gap | both | a value used by an annotator that the baseline never produced, per categorical feature |
| magnitude_or_limit_numeric | photometry_spans | `magnitude_or_limit` parsed as a float, null if it does not parse |
| magnitude_error_numeric | photometry_spans | `magnitude_error` parsed as a float, null if it does not parse |
| limit_sigma_numeric | photometry_spans | `limit_sigma` parsed as a float, null if it does not parse |
| exposure_time_raw_numeric | photometry_spans | `exposure_time_raw` parsed as a float, null if it does not parse |

## Using this corpus

A span row's `layer_source` is either `INITIAL_CAS`, the pre-annotation baseline, or
an annotator's username. Every non-baseline row is one person's judgement on one
document; nothing here merges two annotators' work into one row.

To compare a baseline span against an annotator's version of it, join on
`(document_name, begin, end, span_index)`. `span_index` exists because a small
number of offset ranges legitimately carry more than one span; `xmi_id` is not part
of this key and must not be used to relate rows across layers, since the same
underlying span can carry a different `xmi_id` in the baseline and in an annotator's
copy, or the same `xmi_id` in both.

Agreement between annotators is measurable, because every document carries two or
more of them, but it is not resolved here: there is no merged or curated layer, and
this corpus takes no position on which annotator is right where they disagree.

## Known limitations

- **No curated layer.** The corpus holds independent validations only; there is no
  single answer per document, and none is computed here.
- **Uneven coverage.** Annotators per document range from 2 to 4. Annotator-authored
  annotations per document range from 165 (`event_GCN-260614_134953.xmi`) to 1,549
  (`event_GCN-251013_173943.xmi`), a roughly 9-fold spread.
- **Annotator notes concentrate in one annotator.** All 47 `is_annotator_note` rows
  (11 evidence, 36 photometry) belong to a single annotator, Sarah, across three
  documents: `event_2026owq.xmi`, `event_GCN-251013_173943.xmi` and
  `event_GCN-260604_202037.xmi`. Other annotators left similar spans with no category
  uncommented, so they do not carry this flag.
- **A boundary that reads as two separate events.** All 5 `deleted` rows belong to one
  annotator, Camille. In every one of the 5 cases, Camille created at least one other
  span carrying the same label elsewhere in the same document. Read individually as a
  deletion and an unrelated creation, these look like two disagreements; read
  together, they are one relabelling of which text carries the category, which
  understates agreement if the deleted and created rows are counted as separate
  errors.
- **exposure_time_raw is mostly not a number.** Of 1,867 populated values, 915 fail
  to parse as a float — a 49.0% failure rate. The field mixes bare exposure times
  with expressions like `4x90s exposures`, `10x300` and `3x120+12x90`, describing a
  sequence of exposures rather than a single number.
- **Two declared tag values are never used.** `PhotometryMeasurementTypeTags`
  declares `non_detection` and `unclear` alongside `detection` and `upper_limit`;
  every `measurement_type` value in the corpus, baseline or annotator, is `detection`
  or `upper_limit`.
- **EVENT_SUMMARY has no baseline.** All 28 rows carry an annotator's username as
  `layer_source`; none is `INITIAL_CAS`. Nothing about the extractor's performance on
  this layer can be measured from this corpus.

## Terms of use

Internal to the GRANDMA collaboration and to IJCLab. Not for redistribution outside
either. Annotations are authored by named collaboration members and are retained
under their own usernames throughout this corpus.

## Regenerating this corpus

```
.venv/bin/python /home/meneses/project_astronomical/MAFORAI/scripts/gcn_gold/01_flatten.py
.venv/bin/python /home/meneses/project_astronomical/MAFORAI/scripts/gcn_gold/02_normalise.py
```

The export must be present at
`/home/meneses/project_astronomical/MAFORAI/data/inception/project-2026-08-08-072803`
before either command is run.
