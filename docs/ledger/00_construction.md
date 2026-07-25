# Ledger Construction

For whom: developers and scientists who need to understand why the event ledger is
shaped the way it is, and how the two data sources were turned into one queryable store.
The column-level specification lives in [01_schema_v1.md](./01_schema_v1.md); this
document is the reasoning behind it.

The ledger is a single store of dated facts about transient events, built from two
sources — SkyPortal and the GCN circular corpus — so that the state of an event at any
past time `T` can be reconstructed without leaking information that was not yet known at
`T`. Every design choice below serves that one requirement.

## Why a ledger at all

The system we are building takes a new event, finds past events that looked similar at
the same stage of maturity, and uses how those analogues actually evolved as a forecast.
That requires being able to rewind an event: to ask what was known about it at `t0 + 3h`,
not just what is known now. A flat table of current values cannot answer that. A ledger
of dated facts can, because each fact carries when it became known and the state is
recovered by folding the ledger up to a cutoff.

## Two clocks, and why they must not be confused

A single photometric point carries two different times, and the difference between them
is the whole reason the ledger exists.

`t_occurred` is when the telescope took the image — the physical epoch. It places the
point on the light curve.

`t_known` is when that measurement entered the record — when it became knowable. It
places the point in the information timeline.

These are not the same. A measurement can be observed minutes after a trigger yet enter
the record months later. Truncation for state reconstruction uses `t_known` only: a
point observed early but reported late was not available early, and must not appear in
an early state. Both clocks are stored, because the light curve needs `t_occurred` and
causality needs `t_known` (schema §3.2).

## The two sources are complementary, not redundant

The event is the SkyPortal source; the GCN circulars are evidence about it. Neither
source contains the other. SkyPortal holds comments, classifications, follow-up
requests and its own photometry; the circulars hold the near-trigger optical follow-up
and the annotated text that supports explanations. For the events we can match, roughly
two thirds of a circular's photometric measurements are not present in SkyPortal at all,
and SkyPortal in turn carries X-ray, ultraviolet and infrared bands that the circular
extraction does not cover. Both are ingested as first-class evidence.

## Why SkyPortal photometry cannot anchor early state

SkyPortal is not a real-time store for photometry. Its ingestion is dominated by
records entered long after the observation. The GRANDMA team confirms the mechanism:
photometry reported in circulars was for a long time typed into SkyPortal by hand, often
weeks later, to fill in events whose decisions had already been taken over other
channels. A `created_at` produced that way records when someone typed the value, not
when the information became available.

The GCN circulars are the opposite: a measurement is published in a circular within a
few hours of the observation. This gives the ledger two speeds. GCN facts are dated by
the circular's publication time and carry the early state; SkyPortal photometry is dated
by `created_at`, is overwhelmingly retrospective, and feeds the later trajectory and the
full dossier rather than the early state. This split is the reason `t_known_method`
exists as a column: the same nominal timestamp means different things depending on where
the fact came from.

The first STATE query confirms the design directly. For event `2026owq` at `t0 + 6h`,
the ledger returns only GCN facts and zero SkyPortal facts; SkyPortal source facts enter
in the following days. The two-speed shape is not a theory — the reconstructed timeline
reproduces it.

## Why facts belong to containers, not events

A fact references its container — a circular, or a SkyPortal source — never an event
directly. Two reasons.

First, a single circular can be about more than one event, so attaching `event_id` to
the fact row would duplicate spans and break `fact_id` uniqueness. A separate map assigns
containers to events, and a circular that legitimately concerns two events produces two
map rows.

Second, the event↔circular matching will improve over time — many events currently match
no circular only because their sole search term is an internal SkyPortal ID. If facts
depended on events, every matching improvement would force re-emitting the facts. Because
facts depend on containers, improving the match only adds rows to the map and never
touches the 100,000+ facts already written. This is a deliberate decoupling.

## The temporal anchor problem

Every Δt in the system is measured from the event's trigger time `t0`. But `t0` is
directly present for only a minority of sources (notebook 01 §8.1). The ledger resolves
this with a measured fallback ladder rather than a guess (notebook 01 §8.6–§8.7):

- a real SkyPortal `t0` where present;
- the timestamp encoded in an internal source ID, which was measured to sit within a
  fraction of an hour of the true trigger for GCN-prefixed sources, and is accepted for
  those (notebook 01 §8.3, §8.5);
- for EP-prefixed sources the same rule is only weakly validated and is marked
  provisional, not accepted for phase matching, until a causality check on ingested
  photometry can confirm it (notebook 01 §8.7);
- for GRB-prefixed sources the ID rule is rejected, because one validated case was wrong
  by twelve days and such a late-created record cannot be told apart from a correct one
  in advance (notebook 01 §8.5.4);
- otherwise `created_at`, as a dossier-only anchor that is not a physical phase anchor.

Each source therefore carries `t0`, `t0_source`, a measured `t0_uncertainty_hours`, an
`anchor_type` distinguishing a measured trigger from an inferred first detection, and a
`tier_status` recording whether it may enter phase matching (schema §4). Of 800 sources,
230 can enter phase matching, 189 are provisional, and 381 are dossier-only.

## What is deliberately excluded

`photstats`, SkyPortal's cached per-source counters, are not ingested: they carry no
timestamp, are computed over photometry the API token is not permitted to read, and have
been observed to hold stale values. They cannot serve as a completeness control, and the
corpus is documented as the view visible to one account (`visibility_scope`).

The current `source_summary` field is excluded because it is superseded by the dated
`summary_version` rows. Spectra and SkyPortal annotations are admitted by the schema but
are residual in this population — one spectrum and three annotation records across the
whole corpus (notebook 01 §5) — so nothing is designed around them.

## How the ledger was built

The build is deterministic and reproducible, and reuses the validated extractors rather
than re-implementing them.

1. **Inventory** — the SkyPortal source listing is captured and frozen (notebook 01).
   The population is the union of four inventory profiles; this defines the corpus.
2. **Source detail** — `scripts/11_fetch_source_detail.py` downloads the four collections
   the listing does not carry (comments, photometry, spectra, follow-up requests),
   resumably, recording the token's group list as `visibility_scope`.
3. **Source facts** — `scripts/10_emit_skyportal_source_facts.py` emits the `events`
   table and the source-level facts (redshift and summary versions, classifications,
   annotations) from the frozen listing, with no network access.
4. **GCN facts** — `scripts/13_emit_gcn_facts.py` calls the validated extractors directly
   over the 2023-onward circulars and emits one fact per annotation and per photometric
   measurement, with round-trip verification on every row.
5. **Event↔circular map** — `scripts/14_emit_event_circular_map.py` runs the existing
   selection logic over all sources and emits the GCN side of `event_container_map`.

Scale is chosen for validation, not coverage: the extractors were built and validated on
formats from 2023 on, so running them over older circulars would produce unvalidated
output that looked valid.

## What the ledger contains today

Concatenating both sources gives 102,848 facts with globally unique `fact_id` values.
The GCN side contributes 63,277 evidence annotations and 37,795 photometric measurements,
extracted from the 12,012-circular 2023-onward corpus; 11,955 distinct circulars carry at
least one fact, and 57 produced no extractable evidence or photometry. The SkyPortal side
contributes 1,776 source-level facts over 800 events. The event↔circular map connects 191 events to their circulars, with a median of
ten circulars per matched event.

`STATE(event, T)` is a single query — a join of facts, the two map files and the events
table, filtered on `t_known <= T` — and the non-leakage invariant has been checked
directly on the data: no fact with `t_known` after the cutoff appears in any truncated
state.

## Known Limitations

- **Coverage is uneven.** Only 191 of 800 events match any circular, so the remaining
  events have SkyPortal facts but no annotated text to cite. The matching is deliberately
  conservative and is the first candidate for later improvement (notebook 01 §4).
- **The corpus is a moving target.** The SkyPortal photometry endpoint is not
  append-only — rows can be added and deleted between captures — so a re-download does
  not reproduce an earlier capture. Every fact carries `captured_at`, and the ledger is
  a snapshot, not a live view.
- **`created_at` is the weakest anchor.** For sources with neither a real `t0` nor a
  usable ID timestamp, `t0` rests on `created_at`, whose lag can reach hundreds of hours;
  these sources are dossier-only.
- **The EP provisional tier is unresolved.** The 189 EP sources cannot yet be validated
  for phase matching, because the intended check needs ingested photometry that most of
  them do not have. Einstein Probe events are reported in circulars, so the validation
  will come from extracted `TRIGGER_TIME` on the GCN side.
- **Parsing failures are visible, not fixed.** Observation-time parsing fails on a
  measurable fraction of photometric measurements; the failures are recorded with a
  reason (`parse_status`, `parse_note`) rather than dropped, and the decision about which
  extraction rules to fix is deferred to a dedicated evidence notebook.
- **Follow-up requests embed personal data.** Requester name, email and phone appear in
  the raw records; the emitter that consumes them must reduce this to a stable identifier
  before the ledger is shared.

## Change log

| version | date | change |
|---|---|---|
| v1 | 2026-07-25 | initial construction narrative |
