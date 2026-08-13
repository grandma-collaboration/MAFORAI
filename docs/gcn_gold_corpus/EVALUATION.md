# GCN Gold Corpus Evaluation

Documentation of the evaluation of the rule-based extractors against the human
validations held in `gcn_gold_corpus`. It records the method, the decisions taken and
the measured results, and serves as the basis for writing the evaluation chapter of
the report.

**Notebook:** `notebooks/gcn_gold/E_evaluation.ipynb`
**Outputs:** `data/interim/gcn_gold_eval/*.csv`
**Input:** `data/gcn_gold_corpus/` (read-only)

---

## 1. What is evaluated, and why

The rule-based extractors produce pre-annotations over GCN circulars. Ten documents —
one per astronomical event, 297 circulars in total — were validated in INCEpTION by
annotators of the GRANDMA collaboration. The resulting corpus keeps, for every
annotation, the extractor's version and the annotator's version side by side.

That makes it possible to compare machine output against human judgement and answer:
**how well do the extractors work, and where exactly do they fail?**

### Perimeter

| item | value |
|---|---|
| Documents | 10 |
| Circulars grouped | 297 |
| Distinct annotators | 10 |
| (document, annotator) validations in FINISHED state | 28 |
| Annotators per document | 2 to 4 |
| Evidence annotations | 6,615 |
| Photometric measurements | 2,741 |

There is no curated layer: the corpus holds 28 independent validations, not a
consensus. `admin`, `Patrick` and `Thomas` are excluded by name; none of them ever
reached FINISHED.

---

## 2. The central methodological problem

The annotation guide instructed annotators **not to delete** an incorrect
pre-annotation, but to keep it and explain in the `comment` field why it was wrong.

The intent was sound: preserve the *reason* for the error, which is what allows the
rules to be fixed. The unintended consequence is that **a false positive leaves
almost no countable trace**. There are only 5 rows with `match_status = deleted` in
the whole corpus, and all five turned out to be relocations of a span, not rejections.

Rejections were therefore recorded in two ways, neither of them structured:

1. In the free text of the comment.
2. Improvised through the `certainty` field, by setting it to `rejected`.

This conditions everything that follows: **precision cannot be measured, only
bounded.**

### Decision: do not classify comments

Classifying the comments into categories (rejection, scope exclusion, time
interpretation, and so on) to recover the false positives was explored and then
discarded:

- The categories were invented while reading the texts — a *post-hoc* taxonomy,
  neither reproducible nor defensible.
- The comments were free text with no controlled vocabulary: each of the 30 most
  frequent comment texts was used by **exactly one annotator**. There is no shared
  language to aggregate.

**Every reported result is countable**: derived from filters and counts over existing
columns, with no interpretation of text. The only operation involving `comment` is the
exact test `changed_fields == ["comment"]`.

---

## 3. Operational definitions

### Corpus states

| state | meaning |
|---|---|
| `baseline` | the extractor's pre-annotation row |
| `accepted` | the annotator kept the span, changing no field |
| `corrected` | the annotator kept the span and changed at least one field |
| `created` | the annotator created it; it had no baseline counterpart |
| `deleted` | it was in the baseline and the annotator did not keep it |

### Two kinds of correction

`corrected` mixes different phenomena, so it is split by `changed_fields`:

| kind | criterion | evidence | photometry |
|---|---|---|---|
| comment-only | `changed_fields == ["comment"]` | 167 (75%) | 276 (42%) |
| content | at least one other field | 57 (25%) | 375 (58%) |
| **total** | | **224** | **651** |

The split is **opposite between layers**: in evidence, three out of four corrections
touch no data at all; in photometry, most do. A correction that only adds a comment
does not modify the extracted data, which is why the acceptance rate is reported under
both definitions.

### Precision, recall, F1

| | definition |
|---|---|
| TP | baseline span kept by the annotator (accepted or corrected) |
| FP | baseline span deleted by the annotator |
| FN | span created by the annotator with no baseline counterpart |

47 `is_annotator_note` rows are excluded (created spans with no category, written only
to leave a note): 11 in evidence, 36 in photometry. They are not annotations.

---

## 4. Results

### 4.1 Acceptance rate

| layer | all corrections | content only |
|---|---|---|
| evidence | 95.35% | 98.77% |
| photometry | 66.48% | 77.49% |

Excluding annotators with no corrections at all in that layer:

| layer | all corrections | content only | excluded |
|---|---|---|---|
| evidence | 93.98% | 98.39% | Andrii, Xinyue, Yodgor |
| photometry | 57.23% | 69.90% | Andrii, Xinyue |

**The two layers are never averaged into a single figure.** They are two different
regimes, and the difference is the finding.

### 4.2 Precision, recall, F1

| layer | TP | FP | FN | precision | recall | F1 |
|---|---|---|---|---|---|---|
| evidence | 4,814 | 5 | 102 | 99.90% | 97.93% | 98.90% |
| photometry | 1,942 | 0 | 93 | 100% | 95.43% | 97.66% |

Precision is an **upper bound**, for the reason given in section 2. Recall depends on
review depth: a missed span only counts as a false negative if some annotator added it.

### 4.3 Bounded precision

Recovering the rejections that *are* countable:

- **Signal A** — the annotator changed `certainty` to `rejected`: **14 cases**, all in
  evidence, all from a single annotator (11 `TRIGGER_INSTRUMENT`, 2 `TRIGGER_TIME`,
  1 `LOCALIZATION`).
- **Signal B** — the annotator kept the span but cleared its category: **6 cases**
  (4 evidence, 2 photometry), from two annotators.

| layer | lower bound | upper bound |
|---|---|---|
| evidence | 99.52% | 99.90% |
| photometry | 99.90% | 100% |

**Signal coverage:** of 10 annotators, only 2 produced any structured rejection
signal; 8 produced none. 17 of the 20 signals come from one person.

The interval is narrow **not because the extractor is nearly perfect, but because the
signal is nearly absent**. The lower bound is a floor, not an estimate of the true
number of false positives.

Note: the 14 Signal A cases correspond to follow-up instruments labelled as trigger
instruments and to observation times labelled as trigger times — the same error
pattern found independently during the rule audit.

### 4.4 Per category

Evidence (support / P / R / F1; * support < 20, not interpretable):

| label | n | P | R | F1 |
|---|---|---|---|---|
| LOCALIZATION | 257 | 99.10 | 86.67 | 92.47 |
| TRIGGER_INSTRUMENT | 433 | 100 | 94.92 | 97.39 |
| REDSHIFT_CONTEXT | 20 | 100 | 95.00 | 97.44 |
| REDSHIFT_EVENT | 145 | 100 | 95.86 | 97.89 |
| TRIGGER_TIME | 219 | 99.07 | 97.70 | 98.38 |
| COUNTERPART_ASSOCIATION | 509 | 100 | 97.25 | 98.61 |
| SPECTROSCOPY | 116 | 100 | 97.41 | 98.69 |
| HIGH_ENERGY_PROPERTY | 439 | 100 | 97.95 | 98.96 |
| CLASSIFICATION_INTERPRETATION | 108 | 100 | 99.07 | 99.53 |
| LIGHTCURVE_EVOLUTION | 381 | 100 | 99.21 | 99.60 |
| EVENT_IDENTITY | 2158 | 99.95 | 99.95 | 99.95 |
| DURATION_GENERAL | 33 | 100 | 100 | 100 |
| T90 | 74 | 100 | 100 | 100 |
| HOST_CONTEXT* | 17 | 100 | 100 | 100 |
| NEGATIVE_STATEMENT* | 9 | 100 | 100 | 100 |

Photometry: `detection` 1608 (100 / 95.09 / 97.48); `upper_limit` 421 (100 / 98.10 /
99.04).

`LOCALIZATION` has the worst recall (86.67%) among labels with sufficient support.

### 4.5 Where the extractor fails

**Exact span pairing:** 99.90% (evidence), 100% (photometry).

Fields changed most often, over content corrections, as a percentage of matched pairs:

| layer | field | % |
|---|---|---|
| photometry | comment | 15.35 |
| photometry | **instrument** | **10.97** |
| photometry | photometric_system | 6.75 |
| photometry | obs_time_reference | 6.39 |
| photometry | obs_time_raw | 3.55 |
| photometry | exposure_time_raw | 2.01 |
| photometry | photometric_band | 1.75 |
| evidence | comment | 0.91 |
| evidence | certainty | 0.50 |
| evidence | value | 0.31 |
| evidence | **label** | **0.19** |
| evidence | target | 0.19 |

**Main result:** the extractor places spans almost perfectly and fills their
attributes less well. The category is almost never corrected (`label` 0.19%); the
attributes of a measurement are, above all `instrument` (10.97%).

### 4.6 Inter-annotator agreement

Nominal Krippendorff's alpha (implemented directly; the package was unavailable).
Unit of analysis: one item = one baseline span, identified by
`(document_name, begin, end, span_index)`; the value is the annotator's value for the
field under study.

Alpha was chosen over Cohen's kappa because documents carry 2 to 4 annotators and not
every annotator touches every item; alpha handles both and yields a single coefficient
per document.

Full perimeter (alpha / raw agreement):

| field | layer | alpha | raw agreement |
|---|---|---|---|
| label | evidence | 0.9924 | 99.47% |
| certainty | evidence | 0.9510 | 98.86% |
| measurement_type | photometry | 0.9939 | 99.79% |
| photometric_system | photometry | 0.8318 | 89.75% |
| obs_time_reference | photometry | 0.8120 | 87.83% |
| **instrument** | photometry | **0.7070** | 80.94% |

Restricted perimeter (only annotators with corrections in that layer):

| field | full alpha | restricted alpha |
|---|---|---|
| label | 0.9924 | 0.9894 |
| certainty | 0.9510 | 0.9215 |
| instrument | 0.7070 | **0.5544** |
| photometric_system | 0.8318 | 0.7208 |
| obs_time_reference | 0.8120 | 0.6444 |

Agreement on the fields was inflated by the annotators who corrected nothing. Once
filtered, `instrument` drops to 0.55 — moderate agreement.

**Reading:** the scheme is clear about *what* to annotate (alpha 0.99 on `label`) and
ambiguous about *its attributes* (0.55 on `instrument`). This confirms the result of
4.5 from a second angle.

**Required caveat:** these are not conventional reliability estimates. Annotators did
not annotate from scratch; they reviewed a shared pre-annotation, so their decisions
are not independent — agreement on `label` partly measures that nobody changed what
was already there.

**Note:** per-document alphas with few items are unstable and can come out negative
(e.g. `instrument` −0.86 in a document with 7 items). Report the pooled value;
per-document values with low support are not interpretable.

### 4.7 Review depth

Acceptance rate per annotator:

| layer | minimum | maximum |
|---|---|---|
| evidence | 91.90% | 100% |
| photometry | **7.09%** | **100%** |

In photometry, one annotator corrected 131 of 141 spans and another corrected 3 of
314. Two annotators corrected nothing in either layer (503 spans reviewed in total).

**Methodological finding:** an acceptance rate computed over a review campaign
measures the reviewers as much as the system under review. A single pooled figure is
not a property of the extractor.

---

## 5. Declared limitations

1. **No structured rejection mechanism.** The guide instructed annotators to keep and
   comment rather than delete, so a false positive leaves no countable trace.
   Precision can only be bounded.
2. **The lower bound of precision is itself a floor.** Only 2 of 10 annotators
   improvised a structured rejection signal.
3. **Comments are free text.** With no controlled vocabulary, their content was not
   aggregated. 443 corrections modify only a comment.
4. **Recall depends on review depth.** A missed span only counts as a false negative
   if some annotator added it; two annotators added nothing.
5. **No curated layer.** The corpus holds independent validations rather than a
   consensus; disagreement between annotators is not resolved.
6. **Agreement is not conventional reliability.** Annotators started from a shared
   pre-annotation.
7. **Uneven coverage.** Between 2 and 4 annotators per document, with very unequal
   volumes of work between them.
8. **The guide defined no corpus scope criterion.** Which measurements should be
   included (by facility, quality or provenance) was not documented.

---

## 6. Lessons for a future campaign

1. **A dedicated rejection field.** A boolean or a reserved value recording "this
   pre-annotation should not exist", rather than a free-text convention. It is the
   only way to measure precision.
2. **A controlled vocabulary for correction reasons.** A closed set of reasons can be
   aggregated; free text cannot.
3. **An explicit scope criterion in the guide.** Which data belong in the corpus and
   which do not, documented before annotation begins.
4. **Symmetric instructions across layers.** The `certainty` tagset is shared, but the
   guide documented it in detail for evidence and only briefly for photometry, which
   produced uneven use.
5. **Measure review depth during the campaign**, not after, so shallow reviews can be
   caught while they can still be corrected.

---

## 7. Material for the chapter

The figures supporting the three main results:

**1. The spans are right; the attributes less so.**
Exact pairing 99.90% / 100%. `label` changes 0.19% of the time, `instrument` 10.97%.

**2. The scheme is clear about what to annotate and ambiguous about the attributes.**
Alpha on `label` 0.99 (raw agreement 99.47%) against `instrument` 0.71, dropping to
0.55 when restricted to active reviewers.

**3. The acceptance rate measures the reviewer too.**
Range from 7.09% to 100% in photometry; two annotators with no corrections at all.

With their caveats: bounded precision (99.52–99.90% evidence; 99.90–100% photometry),
recall dependent on review depth, and agreement that is not independent because it
started from a shared pre-annotation.

---

## 8. Reproducing

```
.venv/bin/python -m jupyter nbconvert --execute --inplace \
  notebooks/gcn_gold/E_evaluation.ipynb
```

It reads only `data/gcn_gold_corpus/`. It writes to `data/interim/gcn_gold_eval/`:
`per_pair_profile.csv`, `per_annotator_profile.csv`, `acceptance_rates.csv`,
`acceptance_rates_active_reviewers.csv`, `acceptance_by_document.csv`,
`correction_split.csv`, `metrics_micro.csv`, `metrics_by_annotator.csv`,
`metrics_by_category.csv`, `pairing_rates.csv`, `field_change_rates.csv`,
`krippendorff_alpha.csv`, `declared_rejections.csv`.
