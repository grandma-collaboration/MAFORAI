# Ledger schema v1

**Status:** provisional. Designed before the ingestion exists. Several columns are
marked `expected → NB02`: they are present because a phenomenon is anticipated on the
grounds stated beside them, not because anything in this repository measures it yet.
`notebooks/02_ledger_evidence.ipynb` will measure them once the emitters produce data,
and any column that turns out not to be needed will be removed.

**Evidence convention.** Every column names where its justification lives. `§` means
"section", and `NB01` is `notebooks/01_skyportal_inventory_coverage.ipynb`.

- `NB01 §8.6` — measured, in the cited section of notebook 01
- `design` — a structural choice; it follows from how the data is organised, and no
  measurement would change it
- `expected → NB02` — the column exists because a phenomenon is expected for the reason
  given beside it. Nothing in this repository measures it yet

---

## 1. Principles

**A fact belongs to a container, not to an event.**
A GCN circular can be associated with more than one event, so putting `event_id` on the
fact row would duplicate spans and break `fact_id` uniqueness. Facts reference their
container (a circular, or a SkyPortal source); a separate map assigns containers to
events. Improving the event↔circular matching then only adds rows to the map and never
rewrites `facts`.

**Two clocks, never conflated.**
`t_occurred` places a fact on the light curve. `t_known` places it in the information
timeline. Truncation for state reconstruction uses `t_known` only.

**No stored Δt.**
Δt is derived at query time from the event `t0`. Storing it would force a rewrite of
every fact each time an anchor improves, and anchors are expected to improve (EP
validation, GCN `TRIGGER_TIME` tier).

**Parse failures are visible nulls, not dropped rows.**
`value_raw` always holds the literal source text. `value_parsed` holds the typed value
or NULL with a reason. Silent discards previously hid extraction bugs.

**Nothing is deleted.**
Duplicates, reinterpretations and annotations judged incorrect are kept and linked.

---

## 2. Storage

Parquet, partitioned, queried through DuckDB.

```
data/ledger/
  facts/source_system=<gcn|skyportal>/year=<YYYY>/part-*.parquet   # year from t_known
  events/events.parquet
  event_container_map/map.parquet
```

Partitioning by `source_system` allows querying one side alone; by year it bounds
time-range scans. Expected scale is a few hundred thousand fact rows, so the layout is
for clarity rather than performance and can be revised.

---

## 3. Table `facts`

### 3.1 Identity and location

| column | type | notes | evidence |
|---|---|---|---|
| `fact_id` | STRING | deterministic content hash; see note below. Must be stable across regenerations and unique per fact, so validation status can be updated in place | design |
| `fact_type` | STRING | coarse enum, see §6.1 | design |
| `fact_subtype` | STRING | fine label (`T90`, `REDSHIFT_EVENT`, …), NULL where not applicable | design |
| `source_system` | STRING | `gcn` \| `skyportal` | design |
| `container_type` | STRING | `circular` \| `skyportal_source` | design |
| `container_id` | STRING | circular id, or SkyPortal source id | design |

`fact_type` and `fact_subtype` are separate so that a single enum does not mix two
vocabularies (record kinds vs annotation labels).

**`fact_id` must be unique per fact.** A span alone does not identify a photometric
measurement: a single table cell can yield several distinct measurements sharing the
same character span (e.g. two magnitudes on one line). The hash therefore includes the
distinguishing content — for photometry, the magnitude/limit value and the band — not
just (`source_system`, `container_id`, `fact_type`, span). Two genuinely identical rows
in the same span collapse to one fact, which is correct; two different measurements do
not collide. Uniqueness is what lets `validation_status` be updated per row without
touching a sibling.

### 3.2 Time

| column | type | notes | evidence |
|---|---|---|---|
| `t_known` | TIMESTAMP UTC | **NOT NULL.** When the fact entered the record | design |
| `t_known_method` | STRING | how `t_known` was derived, see §6.2 | expected → NB02 |
| `t_known_confidence` | STRING | `high` \| `low` | expected → NB02 |
| `t_occurred` | TIMESTAMP UTC | physical epoch, absolute; NULL for comments, classifications, summaries, and for relative times (see `t_occurred_offset_hours`) | design |
| `t_occurred_offset_hours` | DOUBLE | physical epoch stated relative to the trigger ("T+3.2 h"); resolved to an instant on join with `events` as `t0 + offset`; NULL otherwise | design |
| `t_intended_start` | TIMESTAMP UTC | requested window start; follow-up requests only | design |
| `t_intended_end` | TIMESTAMP UTC | requested window end | design |

`t_known` NOT NULL is the core invariant: a fact that cannot be placed in the
information timeline cannot participate in a truncated state.

`t_known_method` exists because the same nominal field is not equally reliable across
sources. The GRANDMA team reports that photometry appearing in GCN circulars was for a
long time entered into SkyPortal by hand, sometimes well after the fact, to fill gaps in
events whose decisions had already been taken elsewhere. A `created_at` produced that
way records when someone typed the value, not when the information became available; the
circular's publication date does. How large that difference is in practice is not
measured yet.

### 3.3 Content

| column | type | notes | evidence |
|---|---|---|---|
| `value_raw` | STRING | literal source text of the value | design |
| `value_parsed` | STRING (JSON) | typed payload, or NULL | design |
| `unit_raw` | STRING | unit as written | design |
| `parse_status` | STRING | `ok` \| `partial` \| `failed` \| `not_applicable` | expected → NB02 |
| `parse_note` | STRING | reason when not `ok` | expected → NB02 |
| `text` | STRING | natural-language form; embedded and cited | design |
| `text_source` | STRING | `span` (offsets into a canonical circular) \| `rendered` (built from a template) \| `literal` (stored as written, not anchored to a document) | design |
| `text_render_version` | STRING | template version; NULL when `text_source` is `span` or `literal` | design |

`text` is stored rather than generated on read so that embeddings remain aligned with
the text they were built from. `text_render_version` makes a template change detectable.

### 3.4 Promoted photometry columns

Kept out of `value_parsed` because they are filtered on constantly.

| column | type | evidence |
|---|---|---|
| `band_raw` | STRING | expected → NB02 |
| `band_canonical` | STRING | expected → NB02 |
| `photometric_system` | STRING | expected → NB02 |
| `mag` | DOUBLE | design |
| `mag_err` | DOUBLE | design |
| `is_limit` | BOOLEAN | design |
| `limit_sigma` | DOUBLE | design |
| `instrument` | STRING | design |
| `exposure_raw` | STRING | design |

`band_raw` and `band_canonical` are both kept: normalisation is lossy and the original
string is needed to audit it. `photometric_system` is mandatory rather than optional
because a magnitude without its system is ambiguous — the Vega and AB scales differ by
more than a magnitude in some ultraviolet bands, so two rows describing the same
observation can disagree numerically while both are correct.

### 3.5 Provenance

| column | type | notes | evidence |
|---|---|---|---|
| `span_start` | INT | **circular-level** character offset; NULL for SkyPortal facts | design |
| `span_end` | INT | idem | design |
| `text_sha256` | STRING | hash of the canonical text the offsets index into | design |
| `extractor_id` | STRING | GCN facts only | design |
| `extractor_version` | STRING | GCN facts only | design |
| `rule_id` | STRING | GCN facts only | design |
| `method` | STRING | extraction method | design |
| `confidence` | DOUBLE | extractor confidence | design |
| `needs_review` | BOOLEAN | review flag | design |
| `comment` | STRING | review reason, or scientific context for `T90`, `DURATION_GENERAL`, `HIGH_ENERGY_PROPERTY` | design |
| `validation_status` | STRING | `rule_extracted` \| `human_validated` \| `human_rejected` | design |
| `author` | STRING | SkyPortal facts: who wrote it | design |
| `is_bot` | BOOLEAN | SkyPortal facts | design |
| `captured_at` | TIMESTAMP UTC | when the underlying data was read | NB01 §0 |

Offsets are **circular-level**, never event-level. Event-level offsets shift whenever
the circular selection for an event changes, which would invalidate every span on any
matching improvement.

`extractor_id`, `extractor_version`, `rule_id` and `needs_review` are dropped by the
INCEpTION XMI export. Carrying them here is what makes provenance survive.

`validation_status` starts at `rule_extracted` for every emitted fact. When validated
INCEpTION documents arrive, rows are updated in place — which is why `fact_id` must be
deterministic.

### 3.6 Relations

| column | type | notes | evidence |
|---|---|---|---|
| `related_fact_id` | STRING | the other side of the relation | expected → NB02 |
| `relation_type` | STRING | `interpreted_from` \| `duplicate_of` | expected → NB02 |
| `is_canonical` | BOOLEAN | which row of a linked pair is preferred for state | expected → NB02 |
| `aggregation_level` | STRING | `reported` \| `frame` | expected → NB02 |
| `parent_fact_id` | STRING | e.g. a spectrum produced by a follow-up request | design |

`interpreted_from` rather than `duplicate_of` for the GCN↔SkyPortal photometry overlap.
The GRANDMA team reports that when a measurement from a circular is entered into
SkyPortal the filter is recorded in SkyPortal's own vocabulary — a circular's `r` may be
stored as `sdssr` — and magnitudes may be converted between photometric systems. The two
rows then hold the same observation under different conventions, and neither is wrong.
For early state the circular row is preferred, since the reinterpretation was made
later, by a person, using conventions the original report did not state.

`aggregation_level` distinguishes a stacked measurement reported in a circular from the
individual exposures held in SkyPortal. A circular usually reports one combined
magnitude for a night, while the pipeline that produced it stores every frame, so one
circular row can legitimately correspond to many SkyPortal rows. `STATE(T)` summarises
frames rather than listing them.

---

## 4. Table `events`

| column | type | notes | evidence |
|---|---|---|---|
| `event_id` | STRING | SkyPortal source id | NB01 §2 |
| `t0` | TIMESTAMP UTC | temporal anchor; may be derived | NB01 §8.6 |
| `t0_source` | STRING | see §6.3 | NB01 §8.6 |
| `t0_uncertainty_hours` | DOUBLE | the tier's measured uncertainty, looked up from `t0_source`; see §6.3 | NB01 §8.6 |
| `anchor_type` | STRING | `trigger` \| `first_detection` | NB01 §8.2 |
| `tier_status` | STRING | `phase_matching` \| `provisional` \| `dossier_only` | NB01 §8.7 |
| `name_pattern_class` | STRING | `gcn_internal`, `ep_internal`, `grb_internal`, `grb_named`, `tns_like`, `ztf_like`, `other` | NB01 §4 |
| `profiles` | STRING | which inventory queries returned this source | NB01 §1 |
| `ra` | DOUBLE | | NB01 §5 |
| `dec` | DOUBLE | | NB01 §5 |
| `created_at` | TIMESTAMP UTC | source record creation | NB01 §5 |
| `modified` | TIMESTAMP UTC | | NB01 §5 |
| `captured_at` | TIMESTAMP UTC | capture date of the frozen inventory (2026-07-20) | NB01 §0 |
| `visibility_scope` | STRING | groups the API token could read at capture time, recorded in the download manifest | design |
| `source_groups` | STRING | groups this source belongs to, as reported by the listing | design |

`anchor_type` matters for comparability: a trigger is a measured physical instant, a
first detection is an upper bound on the explosion time. "Three hours in" does not mean
the same thing in each case.

`visibility_scope` records that the corpus is the view visible to one account. SkyPortal
filters photometry by group membership, and the number of rows returned for a source has
already been seen to change once the account was granted access to further groups.
Without this column the corpus is not reproducible from a different token.

Current distribution: 230 `phase_matching`, 189 `provisional`, 381 `dossier_only`
(NB01 §8.7).

---

## 5. Table `event_container_map`

| column | type | notes | evidence |
|---|---|---|---|
| `event_id` | STRING | | design |
| `container_type` | STRING | `circular` \| `skyportal_source` | design |
| `container_id` | STRING | | design |
| `match_method` | STRING | `identity_term` \| `direct` \| … | design |
| `match_evidence` | STRING | which term matched, and where | design |

For SkyPortal, `container_id = event_id` and `match_method = direct`. For circulars the
row records why the association was made, so a questionable match can be traced.

Containers with no event are still ingested into `facts`. They cost little and become
usable as soon as matching improves — 365 events currently have only an internal
SkyPortal id as a search term (NB01 §4).

---

## 6. Enumerations

### 6.1 `fact_type`

`photometry` · `gcn_evidence` · `comment` · `classification` · `redshift_version` ·
`summary_version` · `followup_request` · `spectrum` · `skyportal_annotation`

`spectrum` and `skyportal_annotation` are residual in the current population — 1 of 800
sources and 3 of 982 listing records respectively (NB01 §5, §8.7). They are admitted by
the enum but nothing is designed around them.

Explicitly excluded: `photstats`, because it carries no timestamp and is computed over
all photometry attached to a source, including rows the API token is not permitted to
return — it therefore cannot serve as a completeness control for what was downloaded.
Also excluded: the current `source_summary` field, superseded by `summary_version` rows.

### 6.2 `t_known_method`

| value | meaning |
|---|---|
| `circular_publication` | circular `created_on`; used for all GCN facts |
| `altdata_circular` | SkyPortal row declaring its source circular; publication date used |
| `created_at` | SkyPortal row creation |
| `set_at_utc` | versioned history entry (redshift, summary) |

### 6.3 `t0_source`

| value | tier status | `t0_uncertainty_hours` |
|---|---|---|
| `skyportal_t0` | phase matching | 0 |
| `source_id_timestamp_gcn` | phase matching | 0.364 |
| `source_id_timestamp_ep` | provisional | 0.269 |
| `source_id_timestamp_grb` | dossier only | 287.3 |
| `source_id_date_only` | dossier only | 12 |
| `gcn_trigger_time` | pending | pending |
| `first_detection` | pending | pending |
| `created_at` | dossier only | 349 (trigger) / 17572 (first_detection) |

`t0_uncertainty_hours` is the **measured worst case of the tier**, not the precision of
the stored representation. An id parsed to the second still carries its tier's measured
uncertainty: `source_id_timestamp_grb` reads as a second-precision timestamp, yet one of
31 validated cases was wrong by 287 h, so 287.3 is the honest figure. Storing 0 there
would tell a downstream consumer the anchor is exact when it is not.

`source_id_date_only` covers IAU-style names such as `GRB240421B`, which encode a date
but no time. They are distinct from second-precision internal ids like
`GRB-241025_013651` and must not inherit their measured uncertainty. A bounded ±12 h is
preferred over `created_at`, which is usually far better (median ~7 min for trigger
anchors) but has an unbounded tail (up to 349 h).

---

## 7. Query patterns

State at time T:

```sql
SELECT f.*
FROM facts f
JOIN event_container_map m
  ON f.container_type = m.container_type
 AND f.container_id   = m.container_id
WHERE m.event_id = :event_id
  AND f.t_known <= :T
```

Full dossier: the same query without the `t_known` predicate.

Δt for the light curve: `f.t_occurred - e.t0`, joined from `events`.

Δt for the information timeline: `f.t_known - e.t0`.

Both are computed on read.

---

## 8. Decisions recorded

| # | decision | rationale |
|---|---|---|
| 1 | Facts reference containers, not events | matching will change; facts must not be rewritten |
| 2 | Truncate on `t_known` | ingestion lag makes `t_occurred` unusable for causality |
| 3 | `t_known` derived per source type | circular publication is ~2.8 h; SkyPortal ingestion can be months |
| 4 | No stored Δt | anchors will improve |
| 5 | Containers without events are ingested | cheap now, usable when matching improves |
| 6 | Parquet partitioned + DuckDB | query pattern is filter by container and time |
| 7 | `text` stored, with render version | embeddings must stay aligned with their source text |
| 8 | Individual frames ingested, flagged | they are the real trajectory; `STATE(T)` summarises them |
| 9 | Nothing deleted; duplicates linked | consistent with the annotation policy |
| 10 | Circular-level span offsets | event-level offsets break on reselection |
| 11 | The emitter assigns tiers; notebook 01 measures them | one implementation, so the two cannot diverge |
| 12 | `t0_uncertainty_hours` is tier-level, not per-row | representation precision is not accuracy |

---

## 9. Open items

Measurements to reproduce in `notebooks/02_ledger_evidence.ipynb` against emitted data:

1. **Ingestion lag by origin** — how far behind the observation each `origin` value
   enters SkyPortal, and whether the split is sharp enough for `t_known_confidence` to
   be a two-valued flag.
2. **Photometry overlap and stacking** — how much of the GCN↔SkyPortal overlap is one
   observation under two conventions, and how often one circular row corresponds to
   several SkyPortal frames.
3. **Parse failure rate** — what fraction of extracted photometric measurements yields
   an unusable observation time, and whether the failures fall into a few recurring
   shapes worth fixing in the extraction rules.
4. **Band normalisation coverage** — how many distinct band strings appear on each side,
   how many map to a canonical band, and whether the mapping is symmetric.
5. **Permission-driven incompleteness** — how many photometry rows the account still
   cannot see, now that broader access has been granted.

Unresolved beyond the schema:

- **EP provisional tier.** Validated by a causality check once photometry is ingested:
  if the ID-derived `t0` is correct, no photometry point may have `mjd < t0`. Applies to
  all 194 EP sources.
- **`t0` for survey-discovered transients.** 252 sources have a first-detection anchor
  rather than a trigger; the first-detection tier is not yet built.
- **Band equivalence convention.** A questionnaire to the GRANDMA astronomers is
  pending; answers become part of this documentation.

---

## 10. Change log

| version | date | change |
|---|---|---|
| v1 | 2026-07-23 | initial design, before ingestion exists |
