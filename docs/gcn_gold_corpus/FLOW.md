# GCN Gold Corpus Pipeline

This traces the annotation work from the INCEpTION project to the corpus tables.
See `docs/gcn_gold_corpus/DATASET_CARD.md` for what the corpus contains, and the
notebooks under `notebooks/gcn_gold/` for the evidence behind each decision.

## Overview

```
INCEpTION project
     |  project export, UIMA CAS XMI
     v
data/inception/project-2026-08-08-072803/   zipped XMI per annotator
     |  01_flatten.py
     v
data/interim/gcn_gold_corpus/               five flat tables, no decisions
     |  02_normalise.py
     v
data/gcn_gold_corpus/                       five tables, fourteen decisions
```

## Stage 1 — The annotation campaign

Ten documents, each one astronomical event assembled from its GCN circulars, were
worked in INCEpTION by annotators of the GRANDMA collaboration. Each document
contains several circulars concatenated behind a `===== CIRCULAR NNNNN =====`
header; counted directly from the text, the ten documents hold 297 circulars in
total, from 10 circulars in the smallest document to 52 in the largest.

Thirteen users appear in the project's workflow records; ten are real annotators.
The table below is the document-by-annotator state matrix for those ten
(`F`=`FINISHED`, `I`=`IGNORE`, `N`=`NEW`) — of the 100 (document, annotator) pairs
this defines, 28 are `FINISHED`, 69 are `IGNORE`, and 3 are `NEW`.

| document | Andrii | Camille | Dahlia | Eslam | Patrice | Priyadarshini | Sarah | Xinyue | Yodgor | Zhanat |
|---|---|---|---|---|---|---|---|---|---|---|
| event_2025aji.xmi | I | F | I | I | F | I | I | F | I | I |
| event_2026owq.xmi | I | I | F | I | I | I | F | I | I | F |
| event_EP-260623_025405.xmi | I | I | F | I | I | I | I | I | F | I |
| event_GCN-251013_173943.xmi | F | I | I | F | I | I | F | I | I | I |
| event_GCN-251222_170549.xmi | I | F | I | I | I | F | I | I | I | I |
| event_GCN-260604_202037.xmi | N | I | I | I | I | I | F | I | F | I |
| event_GCN-260614_134953.xmi | N | I | I | I | F | F | I | I | I | I |
| event_GRB-241025_013651.xmi | I | F | I | F | I | I | I | F | I | I |
| event_GRB-260708A.xmi | I | F | I | F | F | I | I | N | I | F |
| event_GRB241030.xmi | I | I | F | I | I | F | I | I | F | F |

Three custom layers are enabled in the project. `ASTRO_EVIDENCE` (6 features) and
`PHOTOMETRIC_MEASUREMENT` (16 features) mark a span of text and carry `begin`/`end`
offsets; `EVENT_SUMMARY` (22 features) is one record per (document, annotator) with
no offsets at all — its table has no `begin` or `end` column.

`INITIAL_CAS` is the pre-annotation baseline every annotator started from, produced
by GRANDMA's rule-based extractors before any human touched the text. One
`INITIAL_CAS.zip` exists per document (10 found), and it appears as its own layer in
both `ASTRO_EVIDENCE` (1,683 baseline rows in the corpus) and
`PHOTOMETRIC_MEASUREMENT` (670 baseline rows). `EVENT_SUMMARY` has none: 0 of its 28
corpus rows carry `layer_source == INITIAL_CAS`.

The corpus's perimeter is every (document, annotator) pair in state `FINISHED` — 28
pairs. `admin`, `Patrick` and `Thomas` are excluded by name; measured directly from
their workflow states, none of the three ever reached `FINISHED` (`Patrick`: 2
`IGNORE`, 1 `NEW`; `Thomas`: 1 `IGNORE`; `admin`: 5 `IN_PROGRESS`), so excluding them
by name does not change the perimeter — it only makes the exclusion explicit.

## Stage 2 — Flattening

`scripts/gcn_gold/01_flatten.py` reads the export and writes one row per XMI
element it finds. It changes shape only: it takes no decision, compares nothing
against the baseline, and drops, trims or recodes no value. This is what makes the
interim tables a faithful, decision-free comparison point for every later stage.

| table | rows | columns |
|---|---|---|
| documents.parquet | 10 | 5 |
| annotators.parquet | 28 | 10 |
| evidence_spans.parquet | 6,610 | 12 |
| photometry_spans.parquet | 2,741 | 22 |
| event_summaries.parquet | 28 | 26 |

The annotator is identified from the zip filename —
`annotation/<document>/<username>.zip` — not from anything inside the CAS/XMI
content, which carries no per-user field. Every row in the three annotation tables
carries two provenance columns recording where it came from: `document_name` (the
source document) and `layer_source` (the zip stem: `INITIAL_CAS` or the
annotator's username).

An XMI attribute can be wholly absent from an element or present with an empty
string, and this script keeps the two apart: `elem.get(feature)` returns `None` for
an absent attribute and `""` for a present-but-empty one, and every feature column
is written as pandas `object` dtype so the distinction survives the Parquet
round-trip. This matters because a later decision (`comment_status`) treats "the
extractor never touched this field" and "the extractor set it to nothing" as
different things, and can only do so if this stage kept them apart.

## Stage 3 — Normalisation

`scripts/gcn_gold/02_normalise.py` applies the fourteen decisions recorded in the
final cell of `notebooks/gcn_gold/A_eda.ipynb`, one function per decision, each
reporting the rows it affected. The fourteen decisions themselves are not restated
here.

| table | interim rows | corpus rows | columns added |
|---|---|---|---|
| documents.parquet | 10 | 10 | 0 |
| annotators.parquet | 28 | 28 | 0 |
| evidence_spans.parquet | 6,610 | 6,615 | 8 |
| photometry_spans.parquet | 2,741 | 2,741 | 12 |
| event_summaries.parquet | 28 | 28 | 0 |

The central classification this stage produces is `match_status`: `accepted` when
an annotator's span matches its baseline span on every feature, `corrected` when
it's matched but at least one feature differs, `created` when the annotator's span
has no baseline counterpart at all, and `deleted` — a synthetic row this stage adds
— when a baseline span was not carried forward into one specific annotator's own
layer. This is what turns a raw comparison into something that separates "the
extractor was right," "the extractor was wrong," and "the extractor missed it
entirely," which a plain diff of the two layers cannot do on its own.

## Stage 4 — The corpus

| table | rows | columns |
|---|---|---|
| documents.parquet | 10 | 5 |
| annotators.parquet | 28 | 10 |
| evidence_spans.parquet | 6,615 | 20 |
| photometry_spans.parquet | 2,741 | 34 |
| event_summaries.parquet | 28 | 26 |

Combined `match_status` totals across `evidence_spans` and `photometry_spans`:
baseline 2,353, accepted 5,881, corrected 875, created 242, deleted 5. Acceptance
rate over matched pairs, accepted / (accepted + corrected): 5,881 / 6,756 = **87.0%**.

The corpus supports two things a raw export cannot: comparing the rule-based
extractor's output against human judgement, field by field, through
`match_status` and `changed_fields`; and measuring agreement between annotators,
since every document carries two or more of them working independently. It does not
resolve that agreement into a single answer — there is no curated layer here.

## Evidence

| question | where it is answered |
|---|---|
| What do the flattened tables contain? | `notebooks/gcn_gold/A_eda.ipynb` |
| Which decisions were taken, and why? | `notebooks/gcn_gold/B_decisions.ipynb` |
| What did each decision change? | `notebooks/gcn_gold/C_normalisation.ipynb` |
| Is the corpus reproducible? | `notebooks/gcn_gold/D_reproducibility.ipynb` |
| What does the corpus contain? | `docs/gcn_gold_corpus/DATASET_CARD.md` |

## Running the pipeline

Neither script takes arguments; both read and write fixed paths relative to the
repository root.

```
.venv/bin/python /home/meneses/project_astronomical/MAFORAI/scripts/gcn_gold/01_flatten.py
.venv/bin/python /home/meneses/project_astronomical/MAFORAI/scripts/gcn_gold/02_normalise.py
```

The export must be present at
`/home/meneses/project_astronomical/MAFORAI/data/inception/project-2026-08-08-072803`
before either command is run.
