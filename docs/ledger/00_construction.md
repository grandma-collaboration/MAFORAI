# Ledger Construction

For whom: anyone who needs to understand how the event ledger was built and why it is
shaped the way it is. This document is the story. The column-level specification lives in
[01_schema_v1.md](./01_schema_v1.md).

**Citation convention.** Findings cite the notebook that measured them. All notebooks are under
`notebooks/`, and each writes a compact evidence CSV to `notebooks/evidence/`.

---

## 1. What the ledger is for

The system takes a new transient event, finds past events that looked similar at the same
stage of maturity, and uses how those analogues actually evolved as a forecast.

That requires rewinding an event: asking what was known at `t0 + 6h`, not what is known
now. A table of current values cannot answer that. A ledger of dated facts can, because
each fact carries **when it became known**, and the state at any instant is recovered by
folding the ledger up to a cutoff.

Every design choice below serves that one requirement.

---

## 2. Where the data came from

Two independent sources, captured and frozen so results stay reproducible.

**SkyPortal** — the collaboration's observation platform. Structured records per source.

| Capture | Contents |
|---|---|
| `inventory/…_20260720` | 982 listing records → 800 distinct sources, 4 profiles |
| `source_detail_20260724` | 2,950 comments, 7,968 photometry, 1 spectrum, 2,359 follow-up requests |
| `frozen/skyportal_2026-07-22` | the listing, frozen for reconstruction |

The four inventory profiles (`grandma_base`, `gcn`, `ep`, `grb`) overlap: 182 sources are
returned by more than one query. The union of the four defines the corpus (NB01).

**GCN Circulars** — the community's notice board. Free-text announcements of detections,
measurements and interpretations.

| | |
|---|---|
| Downloaded | 45,067 circulars, 1997–2026, capture `20260720_093324` |
| Used | 12,012 circulars, 2023 onward |

The restriction to 2023 onward is a **scope decision, not an omission**: the extractors
were built and validated on formats from 2023 on. Running them over older circulars would
produce unvalidated output that looked valid.

---

## 3. What was measured before designing

Six notebooks, each starting from raw data, each answering one question.

**Golden rule:** a notebook reads only raw data and earlier notebooks.

### NB01 — What is in the corpus?

982 listing records resolve to 800 sources across four profiles (407 / 155 / 219 / 201),
with 182 appearing in more than one. Spectra and SkyPortal annotations are residual: one
spectrum and three annotation records in the entire corpus. Nothing is designed around
them.

### NB02 — When did each event occur?

Every Δt in the system is measured from the trigger time `t0`. A real `t0` is present for
only a minority of sources. The rest are resolved by a **measured ladder**, where the
uncertainty is the worst case observed for that tier — not the precision of the
representation:

| `t0_source` | Uncertainty | Tier |
|---|---:|---|
| `skyportal_t0` | 0 h | phase_matching |
| `source_id_timestamp_gcn` | 0.364 h | phase_matching |
| `source_id_timestamp_ep` | 0.269 h | **provisional** |
| `source_id_timestamp_grb` | 287.3 h | dossier_only |
| `source_id_date_only` | 12 h | dossier_only |
| `created_at` | 349 h / 17,572 h | dossier_only |

The GRB tier illustrates why the worst case is the honest figure: a GRB-prefixed ID can be
read to the second, but one validated case was wrong by twelve days, and a late-created
record cannot be told apart from a correct one in advance. So the tier is rejected for
phase matching.

Result: of 800 sources, **230 can enter phase matching**, 189 are provisional, 381 are
dossier-only. Of the 230, roughly 106 actually carry descriptive facts at 6 h. That — not
800 — is the honest size of the matchable corpus.

### NB03 — Does SkyPortal record when it knew?

Truncation is only possible if every fact carries a knowledge-time. Measured on the raw
capture, coverage is complete:

| Fact type | Field | Coverage |
|---|---|---:|
| comment | `created_at` | 2,950 / 2,950 |
| classification | `created_at` | 416 / 416 |
| photometry | `created_at` | 7,968 / 7,968 |
| redshift version | `set_at_utc` | 83 / 83 |
| summary version | `set_at_utc` | 1,274 / 1,274 |
| follow-up request | `created_at` | 2,359 / 2,359 |

### NB04 — How fast does each channel deliver?

A photometric measurement has three moments: when it was observed, when the circular
announcing it was published, and when it entered SkyPortal. For the 958 measurements
matched to a circular:

| Delay | Median | p90 |
|---|---:|---:|
| Observation → circular published | **10.7 h** | 2.4 d |
| Circular published → SkyPortal | **3.2 d** | **227 d** |
| Observation → SkyPortal | 4.2 d | 235 d |

Photometry with no circular reference reaches SkyPortal in 45.5 d (median).

Two consequences. The GCN channel is fast and SkyPortal ingestion is slow and largely
retrospective — the two speeds are measured. And more sharply: **dating a
GCN-origin fact by SkyPortal's `created_at` dates it late, by more than 227 days in 10% of
cases.** That is the measurement behind `t_known_method`.

In the tail, SkyPortal is equally slow whatever the origin (p90 of 235 d for matched rows
against 266 d for unmatched). The slowness belongs to SkyPortal's ingestion, not to any
one channel.

### NB05 — Is it the same measurement on both sides?

When a measurement exists in both places, it is the same observation — but neither the
label nor the value is preserved. Of 627 compared pairs, 487 magnitudes agree exactly and
140 differ. **Zero band labels are identical**; 620 differ.

The differences are not noise. Within each band pair the offset is constant to
floating-point precision, and the values match Vega-to-AB conversion offsets:

| Circular band | SkyPortal band | Offset | σ |
|---|---|---:|---:|
| `R` | `bessellr` | 0.193 | 0.457 |
| `Rc` | `bessellr` | 0.193 | 0.000 |
| `V` | `bessellv` | 0.010 | 0.000 |
| `B` | `bessellb` | −0.102 | 0.000 |
| `Ic` | `besselli` | 0.441 | 0.000 |
| `J` | `2massj` | 0.899 | 0.000 |
| `H` | `2massh` | 1.373 | 0.000 |
| `u` | `uvot::u` | 1.012 | 0.000 |

SkyPortal normalises each measurement to a canonical photometric system: it renames the
band **and** converts the value. This is the evidence behind linking the two records as
`interpreted_from` rather than `duplicate_of` — they are not copies, and they are not
independent facts either.

SkyPortal also loses the instrument on transcription, storing the origin in its place. If
a dossier needs to know which telescope observed, that survives only on the GCN side.

### NB06 — Is the ledger reproducible?

Facts were regenerated from raw data inside the notebook and compared against the ledger
on disk by `fact_id`:

| Side | Regenerated | Matching | Mismatches |
|---|---:|---:|---:|
| SkyPortal (full) | 1,776 | 1,776 | 0 |
| GCN (50-circular stratified sample) | 292 | 292 | 0 |

Because `fact_id` is a content hash, an exact match means every byte entering the hash was
reproduced — not merely that the counts agree. The GCN side is verified on 0.42% of
circulars; the SkyPortal side in full.

---

## 4. The design decisions

### Two clocks, never confused

Every fact carries both. `t_occurred` is when the telescope took the image — it places the
point on the light curve. `t_known` is when the measurement became knowable — it places
the point on the information timeline.

Truncation uses `t_known` only. A point observed early but reported late was not available
early and must not appear in an early state. NB04 shows how far apart the two can be.

### `t_known_method` records where the date came from

The same nominal timestamp means different things depending on the source. A GCN fact is
dated by circular publication; a SkyPortal-native fact by `created_at` or `set_at_utc`; a
SkyPortal row that declares its source circular is dated by that circular's publication,
not by when someone typed it in.

### Causal truncation is a runtime check, not an assumption

The assertion *no fact with `t_known > T` appears in a state truncated at T* is verified on
every build. It returns **0 violations**. It is never assumed.

### Facts hang off containers, not events

A fact references a container — one circular, or one SkyPortal source — never an event
directly.

A single circular can concern more than one event, so putting `event_id` on the fact row
would duplicate spans and break `fact_id` uniqueness. A separate map assigns containers to
events; a circular about two events produces two map rows.

More importantly, event↔circular matching will improve over time. If facts depended on
events, every improvement would force re-emitting 100,000+ facts. Because they depend on
containers, improving the match only adds rows to the map. This decoupling is deliberate.

### Every fact carries its own text

A fact stores a natural-language form of itself, because that text is what gets embedded
and what gets cited. It arrives three ways:

- **`span`** — the text exists inside a circular and is copied literally, with character
  offsets into the canonical text. All GCN facts.
- **`rendered`** — no text exists to copy, so one is built from the structured fields by a
  template. SkyPortal classifications, redshift versions, annotations.
- **`literal`** — real prose not anchored to any canonical document, stored as written.
  SkyPortal summaries.

The text is stored rather than generated on read, so that embeddings stay aligned with the
text they were built from. A `text_render_version` records which template produced a
rendered text, making a template change detectable.

Templates live in two places: SkyPortal fact templates in
`scripts/10_emit_skyportal_source_facts.py`, state-level clause templates in
`src/skyportal_corpus/state/state.py`. The two carry independent version identifiers and
are unrelated to each other.

### The two sources are complementary

The event is the SkyPortal source; the circulars are evidence about it. SkyPortal holds
comments, classifications, follow-up requests and its own photometry, including X-ray,
ultraviolet and infrared bands the circular extraction does not cover. The circulars hold
the near-trigger optical follow-up and the annotated text that supports explanations.

### What is deliberately excluded

`photstats`, SkyPortal's cached per-source counters, are not ingested: they carry no
timestamp, are computed over photometry the API token cannot read, and have been observed
to hold stale values. The corpus is documented as the view visible to one account
(`visibility_scope`).

The current `source_summary` field is excluded, superseded by dated `summary_version` rows.

---

## 5. How the ledger was built

Deterministic, reproducible, and reusing the validated extractors rather than
re-implementing them.

| Step | Script | Network |
|---|---|---|
| 1. Source detail | `11_fetch_source_detail.py` | yes, resumable |
| 2. Source facts + events | `10_emit_skyportal_source_facts.py` | no |
| 3. GCN facts | `13_emit_gcn_facts.py` | no |
| 4. Event↔circular map | `14_emit_event_circular_map.py` | no |

Step 3 calls the validated extractors directly over the 2023-onward circulars, emitting one
fact per annotation and per photometric measurement, with round-trip verification on every
row.

---

## 6. What the ledger contains today

| | |
|---|---:|
| Facts, total, globally unique `fact_id` | 102,848 |
| GCN evidence annotations | 63,277 |
| GCN photometric measurements | 37,795 |
| SkyPortal source-level facts | 1,776 |
| Events | 800 |
| Circulars contributing at least one fact | 11,955 of 12,012 |
| Events connected to circulars | 191, median 10 circulars each |

`STATE(event, T)` is a single query — facts joined to the two map files and the events
table, filtered on `t_known <= T`. State snapshots exist at three windows: 106 at 6 h, 114
at 24 h, 116 at 7 d.

---

## 7. Known limitations

- **Coverage is uneven.** Only 191 of 800 events match any circular; the rest have
  SkyPortal facts but no annotated text to cite. Matching is deliberately conservative and
  is the first candidate for improvement.
- **The corpus is a moving target.** The SkyPortal photometry endpoint is not append-only —
  rows can be added and removed between captures — so a re-download does not reproduce an
  earlier capture. Every fact carries `captured_at`; the ledger is a snapshot, not a live
  view.
- **`created_at` is the weakest anchor.** Where there is neither a real `t0` nor a usable
  ID timestamp, `t0` rests on `created_at`, whose lag reaches hundreds of hours. Those
  sources are dossier-only.
- **The EP provisional tier is unresolved.** The intended causality check needs ingested
  photometry, and EP sources have none. Validation must come from `TRIGGER_TIME` extracted
  on the GCN side.
- **The circular matcher produces false positives.** 10 of 958 matched rows carry a
  negative publication lag; two link 2026 observations to 2005 circulars through 4-digit
  number collisions. Excluding them moves the median lag by 2.94% (NB05).
- **Parsing failures are visible, not fixed.** Observation-time parsing fails on a
  measurable fraction of measurements. Failures are recorded with `parse_status` and
  `parse_note` rather than dropped. A wrong value is worse than an empty one.
- **Extraction rule bugs await a single fix round**, after which the GCN side will be
  re-emitted once: band field contamination (`Lim`, `P-`/`P/` variants, magnitudes and
  exposures parsed as bands, mojibake), 12 false localisation radii, ~3,626 unparseable
  relative time offsets.
- **Template versions are recorded but not dispatched.** `text_render_version` and the
  state text version identify which template produced a text, but the implementations are
  embedded in the emitter code rather than selected by a version lookup. Changing a
  template makes the previous text unreproducible.
- **Follow-up requests embed personal data** — name, email and phone in 914 of 2,359
  records. The emitter that consumes them must reduce this to a stable identifier before
  the ledger is shared.

---

## 8. Evidence index

| Claim | Measured by | Evidence file |
|---|---|---|
| Corpus is 800 sources over 4 profiles | NB01 | `01_source_index.csv` |
| `t0` ladder and tier assignment | NB02 | `01_source_index.csv` |
| Knowledge-time coverage is complete | NB03 | — |
| GCN publishes in 10.7 h; SkyPortal ingests in days to months | NB04 | `04_photometry_lag.csv` |
| SkyPortal normalises to a canonical photometric system | NB05 | `05_photometry_pairs.csv` |
| The ledger regenerates exactly from raw data | NB06 | `06_regeneration_check.csv` |
| Non-leakage holds on the built ledger | build-time assertion | — |