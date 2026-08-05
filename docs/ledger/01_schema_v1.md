# Ledger schema v1

**Evidence convention.** Every column names where its justification lives. Citations name
the **notebook**. All notebooks are under `notebooks/`.

- `NB01` … `NB06` — measured, in the named notebook
- `design` — a structural choice; it follows from how the data is organised, and no
  measurement would change it
- `unmeasured` — the column exists because a phenomenon is expected for the reason given
  beside it. Nothing in this repository measures it yet

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
or NULL with a reason.

**Nothing is deleted.**
Duplicates, reinterpretations and annotations judged incorrect are kept and linked.

---

## 2. Storage

Parquet, partitioned, queried through DuckDB.

```
data/ledger/
  facts/source_system=<gcn|skyportal>/year=<YYYY>/part-*.parquet   # year from t_known
  events/events.parquet
  event_container_map/map.parquet                                  # SkyPortal
  event_container_map/gcn_map.parquet                              # GCN
  state_snapshots/window=<6h|24h|7d>/part-*.parquet
  state_index/window=<6h|24h|7d>/                                  # .npy vectors + metadata.parquet
```

Partitioning by `source_system` allows querying one side alone; by year it bounds
time-range scans. Actual scale is 102,848 fact rows, so the layout is for clarity rather
than performance and can be revised.

---

## 3. Table `facts`

### 3.1 Identity and location

| column | type | notes | evidence |
|---|---|---|---|
| `fact_id` | STRING | deterministic content hash; see below | NB06 |
| `fact_type` | STRING | coarse enum, see §6.1 | design |
| `fact_subtype` | STRING | fine label (`T90`, `REDSHIFT_EVENT`, …), NULL where not applicable | design |
| `source_system` | STRING | `gcn` \| `skyportal` | design |
| `container_type` | STRING | `circular` \| `skyportal_source` | design |
| `container_id` | STRING | circular id, or SkyPortal source id | design |

`fact_type` and `fact_subtype` are separate so that a single enum does not mix two
vocabularies (record kinds vs annotation labels).

**`fact_id` construction.** Both emitters build a payload and take its SHA-256:

```python
# SkyPortal facts
payload = f"{source_system}|{container_id}|{fact_type}|{natural_key}"

# GCN facts
parts   = [source_system, container_id, fact_type, span_start, span_end, *content]
payload = "|".join("" if p is None else str(p) for p in parts)
```

The GCN payload includes the content because a span alone does not identify a
measurement: a single table cell can yield several distinct measurements sharing the same
character span (e.g. two magnitudes on one line). For photometry the content is the
magnitude or limit value and the band. Two genuinely identical rows in the same span
collapse to one fact, which is correct; two different measurements do not collide.

Uniqueness is what lets `validation_status` be updated per row without touching a sibling.
Determinism is verified: NB06 regenerated facts from raw data and matched them against the
ledger by `fact_id` — 1,776 of 1,776 on the SkyPortal side, 292 of 292 on a stratified
sample, zero mismatches. Because the id is a content hash, an exact match means every byte
entering the hash was reproduced.

### 3.2 Time

| column | type | notes | evidence |
|---|---|---|---|
| `t_known` | TIMESTAMP UTC | **NOT NULL.** When the fact entered the record | NB03 |
| `t_known_method` | STRING | how `t_known` was derived, see §6.2 | NB04 |
| `t_occurred` | TIMESTAMP UTC | physical epoch, absolute; NULL for comments, classifications, summaries, and for relative times (see `t_occurred_offset_hours`) | design |
| `t_occurred_offset_hours` | DOUBLE | physical epoch stated relative to the trigger ("T+3.2 h"); resolved to an instant on join with `events` as `t0 + offset`; NULL otherwise | design |
| `t_intended_start` | TIMESTAMP UTC | requested observation window start; follow-up requests only | design |
| `t_intended_end` | TIMESTAMP UTC | requested observation window end; follow-up requests only | design |

`t_known` NOT NULL is the core invariant: a fact that cannot be placed in the information
timeline cannot participate in a truncated state. NB03 established that the raw capture
supports it — knowledge-time coverage is complete on all six SkyPortal fact types
(comments 2,950/2,950; classifications 416/416; photometry 7,968/7,968; redshift versions
83/83; summary versions 1,274/1,274; follow-up requests 2,359/2,359).

`t_known_method` exists because the same nominal field is not equally reliable across
sources, and NB04 measured how large the difference is. For photometry matched to its
circular, the median delay from observation to circular publication is 10.7 h (p90 2.4 d),
while the median delay from publication to SkyPortal entry is 3.2 d — with a p90 of
**227 days**. Dating a GCN-origin fact by SkyPortal's `created_at` therefore places it more
than seven months late in one case out of ten.

`t_intended_start` and `t_intended_end` record the observation window an astronomer
requested, not a window used by the state layer. They apply only to `followup_request`.

### 3.3 Content and text

| column | type | notes | evidence |
|---|---|---|---|
| `value_raw` | STRING | literal source text of the value | design |
| `value_parsed` | STRING (JSON) | typed payload, or NULL | design |
| `unit_raw` | STRING | unit as written | design |
| `parse_status` | STRING | `ok` \| `partial` \| `failed` \| `not_applicable` | unmeasured |
| `parse_note` | STRING | reason when not `ok` | unmeasured |
| `text` | STRING | natural-language form; embedded and cited | design |
| `text_source` | STRING | `span` \| `rendered` \| `literal`; see below | design |
| `text_render_version` | STRING | template version; NULL where no template applies | design |

`text` is stored rather than generated on read so that embeddings remain aligned with the
text they were built from. `text_render_version` makes a template change detectable.

**The three text sources.**

| `text_source` | Meaning | Fact types | Rows |
|---|---|---|---:|
| `span` | copied literally from a circular, with character offsets into the canonical text | `gcn_evidence`, `photometry` | 101,072 |
| `rendered` | built from structured fields by a template | `classification`, `redshift_version`, `skyportal_annotation` | 502 |
| `literal` | prose stored as written, not anchored to any canonical document | `summary_version` | 1,274 |

**Templates.** SkyPortal fact templates are declared in
`scripts/10_emit_skyportal_source_facts.py`:

| fact_type | template |
|---|---|
| `redshift_version` | `Redshift set to {value}.` |
| `classification` | `Classified as {label}.`, with probability and taxonomy appended when present |
| `skyportal_annotation` | `Catalogue {origin}: {kv}.`, key/value pairs sorted |
| `summary_version` | none — the source summary is copied literally |

GCN facts have no template: the text is the annotation's source span.

Parse failure rate is not measured. Individual failure shapes are known — malformed band
values parsed as numbers, one `-1000` magnitude sentinel — but not quantified.

### 3.4 Promoted photometry columns

Kept out of `value_parsed` because they are filtered on constantly.

| column | type | evidence |
|---|---|---|
| `band_raw` | STRING | NB05 |
| `band_canonical` | STRING | NB05 |
| `photometric_system` | STRING | NB05 |
| `mag` | DOUBLE | design |
| `mag_err` | DOUBLE | design |
| `is_limit` | BOOLEAN | design |
| `limit_sigma` | DOUBLE | design |
| `instrument` | STRING | NB05 |
| `exposure_raw` | STRING | design |

`band_raw` and `band_canonical` are both kept: normalisation is lossy and the original
string is needed to audit it. NB05 measured how lossy — of 627 compared GCN↔SkyPortal
pairs, **zero band labels are identical** and 620 differ. The translations are systematic:
`r → sdssr` (102), `i → sdssi` (54), `z → sdssz` (52), `R → bessellr` (43), `g → sdssg` (34).

`photometric_system` is mandatory rather than optional because a magnitude without its
system is ambiguous. Within each band pair the magnitude offset is constant to
floating-point precision, and the values match Vega-to-AB conversion offsets:

| circular band | SkyPortal band | offset | σ |
|---|---|---:|---:|
| `R` | `bessellr` | 0.193 | 0.457 |
| `Rc` | `bessellr` | 0.193 | 0.000 |
| `V` | `bessellv` | 0.010 | 0.000 |
| `B` | `bessellb` | −0.102 | 0.000 |
| `Ic` | `besselli` | 0.441 | 0.000 |
| `J` | `2massj` | 0.899 | 0.000 |
| `H` | `2massh` | 1.373 | 0.000 |
| `u` | `uvot::u` | 1.012 | 0.000 |

In the ultraviolet the difference exceeds one magnitude. Two rows describing the same
observation disagree numerically while both are correct.

`instrument` is not preserved by SkyPortal on transcription — a measurement from `UVOT` is
stored with instrument `GCN`. The observing instrument survives only on the GCN side.

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
| `needs_review` | BOOLEAN | set by the extractor when its own confidence is low; used to prioritise annotator effort | design |
| `comment` | STRING | review reason, or scientific context for `T90`, `DURATION_GENERAL`, `HIGH_ENERGY_PROPERTY` | design |
| `validation_status` | STRING | `rule_extracted` \| `human_validated` \| `human_rejected` | design |
| `author` | STRING | SkyPortal facts: who wrote it | design |
| `is_bot` | BOOLEAN | SkyPortal facts | design |
| `captured_at` | TIMESTAMP UTC | when the underlying data was read | NB01 |

Offsets are **circular-level**, never event-level. Event-level offsets shift whenever the
circular selection for an event changes, which would invalidate every span on any matching
improvement.

`extractor_id`, `extractor_version`, `rule_id` and `needs_review` are dropped by the
INCEpTION XMI export. Carrying them here is what makes provenance survive.

`validation_status` starts at `rule_extracted` for every emitted fact. Validated documents
returning from INCEpTION are ingested as new rows marked `human_validated`; existing rows
are never updated in place, since a corrected annotation produces a different `fact_id`.
Where a container has validated facts, those supersede its rule-extracted facts for state
reconstruction. Human validation covers a subset of the corpus; any fact carrying
`rule_extracted` has not been seen by a person.

### 3.6 Relations

| column | type | notes | evidence |
|---|---|---|---|
| `related_fact_id` | STRING | the other side of the relation | NB05 |
| `relation_type` | STRING | `interpreted_from` \| `duplicate_of` | NB05 |
| `aggregation_level` | STRING | `reported` \| `frame` | unmeasured |
| `parent_fact_id` | STRING | e.g. a spectrum produced by a follow-up request | design |

`interpreted_from` rather than `duplicate_of` for the GCN↔SkyPortal photometry overlap.
When a measurement from a circular is entered into SkyPortal, the band is recorded in
SkyPortal's own vocabulary and the magnitude is converted to a canonical photometric
system — the translation table in §3.4. The two rows hold the same observation under
different conventions, and neither is wrong. `duplicate_of` would assert a literal equality
that does not hold; treating them as independent facts would overcount observations.

For early state the circular row is preferred, since the reinterpretation was made later,
by a person, using conventions the original report did not state. NB04 supports this
independently: the SkyPortal row is dated a median of 3.2 days after publication.

`aggregation_level` distinguishes a stacked measurement reported in a circular from the
individual exposures held in SkyPortal. A circular usually reports one combined magnitude
for a night, while the pipeline that produced it stores every frame, so one circular row
can legitimately correspond to many SkyPortal rows. `STATE(T)` summarises frames rather
than listing them. Not yet measured.

---

## 4. Table `events`

| column | type | notes | evidence |
|---|---|---|---|
| `event_id` | STRING | SkyPortal source id | NB01 |
| `t0` | TIMESTAMP UTC | temporal anchor; may be derived | NB02 |
| `t0_source` | STRING | see §6.3 | NB02 |
| `t0_uncertainty_hours` | DOUBLE | the tier's measured uncertainty, looked up from `t0_source`; see §6.3 | NB02 |
| `anchor_type` | STRING | `trigger` \| `first_detection` | NB02 |
| `tier_status` | STRING | `phase_matching` \| `provisional` \| `dossier_only` | NB02 |
| `name_pattern_class` | STRING | `gcn_internal`, `ep_internal`, `grb_internal`, `grb_named`, `tns_like`, `ztf_like`, `other` | NB01 |
| `profiles` | STRING | which inventory queries returned this source | NB01 |
| `ra` | DOUBLE | | NB01 |
| `dec` | DOUBLE | | NB01 |
| `created_at` | TIMESTAMP UTC | source record creation | NB01 |
| `modified` | TIMESTAMP UTC | | NB01 |
| `captured_at` | TIMESTAMP UTC | capture date of the frozen inventory (2026-07-20) | NB01 |
| `visibility_scope` | STRING | groups the API token could read at capture time, recorded in the download manifest | design |
| `source_groups` | STRING | groups this source belongs to, as reported by the listing | design |

`anchor_type` matters for comparability: a trigger is a measured physical instant, a first
detection is an upper bound on the explosion time. "Three hours in" does not mean the same
thing in each case.

`visibility_scope` records that the corpus is the view visible to one account. SkyPortal
filters photometry by group membership, and the number of rows returned for a source has
been seen to change once the account was granted access to further groups. Without this
column the corpus is not reproducible from a different token.

Current distribution: 230 `phase_matching`, 189 `provisional`, 381 `dossier_only` (NB02).
Of the 230, roughly 106 carry descriptive facts at 6 h — that, not 800, is the honest size
of the phase-matchable corpus.

---

## 5. Table `event_container_map`

| column | type | notes | evidence |
|---|---|---|---|
| `event_id` | STRING | | design |
| `container_type` | STRING | `circular` \| `skyportal_source` | design |
| `container_id` | STRING | | design |
| `match_method` | STRING | `identity_term` \| `direct` \| … | design |
| `match_evidence` | STRING | which term matched, and where | design |

For SkyPortal, `container_id = event_id` and `match_method = direct`, giving one row per
event. For circulars the row records why the association was made, so a questionable match
can be traced; an event typically has many circulars.

Current coverage: 800 SkyPortal rows and 2,335 GCN rows, connecting 191 events to their
circulars, with a median of ten circulars per matched event. The remaining 609 events have
SkyPortal facts but no annotated text to cite.

Containers with no event are still ingested into `facts`. They cost little and become
usable as soon as matching improves — 365 events currently have only an internal SkyPortal
id as a search term, which would never appear in a circular (NB01).

---

## 6. Enumerations

### 6.1 `fact_type`

`photometry` · `gcn_evidence` · `comment` · `classification` · `redshift_version` ·
`summary_version` · `followup_request` · `spectrum` · `skyportal_annotation`

`spectrum` and `skyportal_annotation` are residual in the current population — 1 of 800
sources and 3 of 982 listing records respectively (NB01). They are admitted by the enum
but nothing is designed around them.

Explicitly excluded: `photstats`, because it carries no timestamp and is computed over all
photometry attached to a source, including rows the API token is not permitted to return —
it therefore cannot serve as a completeness control for what was downloaded. Also
excluded: the current `source_summary` field, superseded by `summary_version` rows.

Two declared photometry subtypes, `non_detection` and `unclear`, have zero rows. Whether
the extractors never emit them or the corpus never contains them is not established.

### 6.2 `t_known_method`

| value | meaning |
|---|---|
| `circular_publication` | circular `created_on`; used for all GCN facts |
| `altdata_circular` | SkyPortal row declaring its source circular; the circular's publication date is used |
| `created_at` | SkyPortal row creation |
| `set_at_utc` | versioned history entry (redshift, summary) |

`altdata_circular` is what keeps a transcribed measurement dated by when it was published
rather than by when someone typed it in — a median of 3.2 days later, and up to 227 days in
the tail (NB04).

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

`t0_uncertainty_hours` is the **measured worst case of the tier** (NB02), not the precision
of the stored representation. An id parsed to the second still carries its tier's measured
uncertainty: `source_id_timestamp_grb` reads as a second-precision timestamp, yet one of 31
validated cases was wrong by 287 h, so 287.3 is the honest figure. Storing 0 there would
tell a downstream consumer the anchor is exact when it is not.

`source_id_date_only` covers IAU-style names such as `GRB240421B`, which encode a date but
no time. They are distinct from second-precision internal ids like `GRB-241025_013651` and
must not inherit their measured uncertainty. A bounded ±12 h is preferred over `created_at`,
which is usually far better (median ~7 min for trigger anchors) but has an unbounded tail
(up to 349 h).

`source_id_timestamp_gcn` reads `t0` from the SkyPortal source name. `gcn_trigger_time`
would read it from the circular text, via the `TRIGGER_TIME` extractor; that tier is not
built. It is the intended route to validating the EP sources, which have no photometry for
the originally planned causality check.

---

## 7. Reingestion from INCEpTION

Validated documents return from INCEpTION as XMI. A document covers one event and all
its circulars, and the annotator revises it as a whole — accepting, correcting,
rejecting and adding annotations across the entire text.

### What comes back

| Returning annotation | Ingested as |
|---|---|
| Pre-annotation accepted unchanged | `human_validated` |
| Pre-annotation corrected | `human_validated`, new `fact_id` |
| Pre-annotation rejected | `human_rejected` |
| Annotation created by the annotator | `human_validated`, no `extractor_id` |

A corrected annotation produces a different `fact_id` than the rule-extracted row it
came from, because the id is a content hash and the content changed. Rows are therefore
never updated in place: the corrected version is a new row, and the original remains.
Nothing is deleted.

### Precedence is per container, not per annotation

A container is validated or it is not. Once a circular has been through INCEpTION, its
facts are those the annotator left behind; the rule-extracted rows for that circular are
superseded in full and take no part in state reconstruction.

    validated_containers AS (
      SELECT DISTINCT container_id
      FROM facts
      WHERE validation_status IN ('human_validated', 'human_rejected')
    )

State and dossier queries select, for each container, the human rows where the container
appears in that set and the rule rows otherwise. This requires no per-annotation
matching, no span comparison and no stable annotation identifier: a document is revised
as a unit, so it is superseded as a unit.

`validation_status` therefore has a function beyond provenance — it decides which rows a
container contributes when both kinds exist.

### Scope

Human validation covers a subset of the corpus. Every other container contributes
rule-extracted facts, and any fact carrying `rule_extracted` has not been seen by a
person. The proportion is recorded in the corpus documentation.

---

## 8. Query patterns

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

**Non-leakage is asserted at build time**: no fact with `t_known` after the
cutoff may appear in any truncated state. The check returns 0 violations.

---

## 9. Decisions recorded

| # | decision | rationale | evidence |
|---|---|---|---|
| 1 | Facts reference containers, not events | matching will change; facts must not be rewritten | design |
| 2 | Truncate on `t_known` | ingestion lag makes `t_occurred` unusable for causality | NB04 |
| 3 | `t_known` derived per source type | circular publication is 10.7 h median; SkyPortal ingestion has a 227 d p90 | NB04 |
| 4 | No stored Δt | anchors will improve | design |
| 5 | Containers without events are ingested | cheap now, usable when matching improves | design |
| 6 | Parquet partitioned + DuckDB | query pattern is filter by container and time | design |
| 7 | `text` stored, with render version | embeddings must stay aligned with their source text | design |
| 8 | Individual frames ingested, flagged | they are the real trajectory; `STATE(T)` summarises them | design |
| 9 | Nothing deleted; duplicates linked | consistent with the annotation policy | design |
| 10 | Circular-level span offsets | event-level offsets break on reselection | design |
| 11 | The emitter assigns tiers; NB02 measures them | one implementation, so the two cannot diverge | NB02 |
| 12 | `t0_uncertainty_hours` is tier-level, not per-row | representation precision is not accuracy | NB02 |
| 13 | GCN↔SkyPortal photometry links as `interpreted_from` | SkyPortal renames the band and converts the magnitude | NB05 |
| 14 | Validated facts enter as new rows, superseding per container | a corrected annotation changes the content hash | design |

---

## 10. Open items

| # | item | status |
|---|---|---|
| 1 | Parse failure rate | not quantified; individual failure shapes observed |
| 2 | Photometry stacking | one circular row to many SkyPortal frames is untested |
| 3 | Permission-driven incompleteness | how many photometry rows the account still cannot see |
| 4 | `text_render_version` on `literal` rows | the emitter sets `v1` on all SkyPortal facts, including the 1,274 `summary_version` rows that use no template; those should be NULL |
| 5 | Template version dispatch | versions are recorded but implementations are embedded in emitter code, so a version change makes earlier text unreproducible |

Unresolved beyond the schema:

- **EP provisional tier.** The intended causality check — if the ID-derived `t0` is correct,
  no photometry point may have `mjd < t0` — cannot run: EP sources have no photometry.
  Validation must come from `TRIGGER_TIME` extracted on the GCN side. *(This section
  previously counted 194 EP sources; NB02 reports 189 in the provisional tier. The
  discrepancy is unreconciled.)*
- **`t0` for survey-discovered transients.** 252 sources have a first-detection anchor
  rather than a trigger; the first-detection tier is not yet built.
- **Band equivalence convention.** NB05 supplies the measured translation table, so the
  open question is not what the equivalences are but whether SkyPortal's conversions are the
  right ones for GRANDMA's use. A questionnaire to the astronomers is pending.
- **Circular matcher reliability.** 10 of 958 matched photometry rows carry a negative
  publication lag; two link 2026 observations to 2005 circulars through 4-digit id
  collisions. Excluding them moves the median lag by 2.94% (NB05).