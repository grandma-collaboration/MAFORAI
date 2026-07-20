# Automatic Event Selection

For whom: developers building event-level documents and reviewers auditing which GCN Circulars belong to an event.

It derives event terms from the SkyPortal inventory, consolidates duplicate event records, indexes Circular identities once, and applies the same `EventIdentityExtractor`-verified matcher to every event.

## Inputs And Upstream Chain

The event universe starts in `data/interim/skyportal/gcn_grandma.json`.

| Component | Responsibility | Output |
|---|---|---|
| `src/skyportal_corpus/extraction/source_selection.py` | Builds the compact event universe and preserves `tns_name`, `ra`, and `dec` from the SkyPortal inventories. | `data/interim/skyportal/gcn_grandma.json` |
| `src/skyportal_corpus/extraction/gcn_event_matching.py` | Expands each event into searchable names. | `event_search_terms.csv` and `event_search_terms.parquet` |
| `scripts/gcn/03a_build_event_search_terms.py` | Thin CLI that delegates term generation to `gcn_event_matching.py`. | `data/interim/gcn/event_matching/event_search_terms.*` |

Run term generation from the repository root:

```bash
.venv/bin/python scripts/gcn/03a_build_event_search_terms.py
```

Selection uses `event_search_terms`, the identity index, and `circular_matches_event()` directly.

## Event Search Terms

Each row represents one original name or formatting variant.

| Column | Meaning |
|---|---|
| `source_id` | SkyPortal event identifier. |
| `gcn_source_type` | Event family such as `grb`, `gcn`, or `ep`. |
| `origin_field` | `id`, `alias`, or `tns_name`. |
| `origin_value` | Exact source value before variant expansion. |
| `search_term` | Name supplied to later registry construction. |
| `search_term_normalized` | Conservative comparison form. |
| `variant_type` | `original`, `compact_variant`, or `spaced_variant`. |
| `variant_rank` | `0` for the original and `1` for generated formatting variants. |
| `is_trigger_like` | Whether the term has the internal timestamp-like trigger form. |
| `groups` | SkyPortal group names retained for inspection. |

Terms include the event's own `id`, every alias, and a non-empty `tns_name`. Recognized GRB, EP, GW, AT, and SN names receive an original, compact, and spaced family where those spellings differ. For example, `AT 2026owq` also produces `AT2026owq`.

## Event Registry

Build the canonical registry with:

```bash
.venv/bin/python scripts/build_event_registry.py
```

The command writes `data/interim/gcn/event_matching/event_registry.csv`.

| Column | Meaning |
|---|---|
| `source_id` | Canonical event identifier used by selection and output paths. |
| `gcn_source_type` | Type from the canonical SkyPortal record. |
| `title` | Readable title assembled from preferred terms. |
| `terms` | Pipe-separated terms used for matching. |
| `dropped_terms` | Terms removed from matching but retained for provenance. |
| `merged_source_ids` | Duplicate SkyPortal IDs absorbed into the canonical event. |
| `tns_name` | Deduplicated TNS names from all merged members. |
| `trigger_time` | Preferred trigger time, stored as MJD when available. |
| `n_terms` | Number of active matching terms. |
| `flags` | Registry diagnostics such as `merged_from` or `suffixless_only_terms`. |

Duplicate detection forms transitive groups when records share any of these signals:

1. the same `search_term_normalized` with at least six characters;
2. the same non-empty `tns_name`;
3. an identical `trigger_time` and an angular separation below one arcminute.

Within a duplicate group, the canonical ID first prefers a member matching `^(GRB|GCN|EP|GW)[-_]\d{6}_\d{6}$`. If no member has that form, or several do, selection uses the member with the most unique terms and then alphabetical order. All other IDs remain in `merged_source_ids`, and their terms are merged into the canonical row.

The registry drops a suffixless GRB or EP term when a suffixed name for the same date exists. For example, `GRB241030` is retained in `dropped_terms` but is not used when `GRB241030A` or `GRB 241030A` exists. The suffixless SkyPortal ID is a degraded form of the physical name and can match a sibling day-fraction designation such as `GRB241030.77`, which is a different burst.

## Identity Index

Build the reusable index with:

```bash
.venv/bin/python scripts/build_identity_index.py
```

`EventIdentityExtractor` then runs once over the 2023-and-later corpus instead of once per event. The current build covers about 12,000 Circulars in about 10 seconds.

| Stored field | Meaning |
|---|---|
| `circular_id`, `subject`, `created_on` | Circular identity and ordering fields. |
| `body_text` | Raw canonical body segment used by boundary-aware fallback matching. |
| `subject_identities` | Header identity annotations with `needs_review=False`. |
| `body_identities` | Every remaining identity annotation. |

Each identity entry stores `value`, `text`, `span_start`, `span_end`, `rule_id`, and `needs_review`. The files are:

```text
data/interim/gcn/event_matching/identity_index/identity_index.parquet
data/interim/gcn/event_matching/identity_index/index_meta.json
```

`index_meta.json` records the corpus scope, build time, Circular and identity counts, extractor ID/version, file size, SHA-256, and index path. Runtime validation rejects an incompatible extractor ID/version; `event_build.py` also rejects a `min_year` mismatch. Archive freshness is visible through the metadata but is not inferred automatically from raw archive timestamps, so rebuild the index after refreshing the Circular index.

## Matching Hierarchy

`circular_matches_event()` applies this order:

| Priority | Result | Decision |
|---|---|---|
| 1 | `confirmed_subject_match` | Include when a confirmed header identity equals an event alias. |
| 2 | `confirmed_other_event` | Exclude when the subject confirms another event even though the body mentions the requested event. |
| 3 | `body_mention` | Include a body identity or body-name match only when the subject has no confirmed event identity. |
| 4 | `no_match` | Exclude when no admissible evidence exists. |

Extracted identities use exact canonical or normalized equality. The secondary `body_name_match` searches the raw body with a case-insensitive, separator-flexible, boundary-aware expression. It splits an alias into alphanumeric runs, joins them with `[^A-Za-z0-9]*`, and wraps the result in `\b` boundaries.

```text
GRB 240912A -> \bGRB[^A-Za-z0-9]*240912A\b
```

Plain normalized substring matching was removed because `grb240912` is a substring of `grb240912a`, even though those names can identify different events. The fallback evidence records the alias, `match_type="body_name_match"`, and the exact `matched_text`.

## Selection And Event Build

`select_event_candidates()` loads one registry row, scans every indexed Circular through `circular_matches_event()`, resolves selected IDs to full Circular records, and calls `group_event_circulars()` again. It raises an error if the cached index decision and live extraction disagree.

Build one event with:

```bash
.venv/bin/python scripts/event_build.py --source-id 2026owq
```

The event files are written below a source-specific directory:

```text
data/inception/out/<source_id>/event_<source_id>.xmi
data/inception/out/<source_id>/event_<source_id>_manifest.txt
```

The selection audit is written independently of XMI generation:

```text
data/interim/gcn/event_matching/selections/selection_<source_id>.txt
```

| Section | What to inspect |
|---|---|
| Header fields | Terms, merged IDs, trigger time, corpus scope, counts, and flags. |
| `INCLUDED` | Every selected Circular with reason, evidence, and informational `delta_days`. |
| `EXCLUDED_CONFLICT` | Body mentions suppressed because the subject confirms another event. |
| `BODY_ONLY - IDENTITY ANNOTATION` | Fallback inclusions supported by an extracted body identity. |
| `BODY_ONLY - BODY NAME MATCH` | Fallback inclusions supported only by the boundary-aware raw-text pattern. |
| `FAR_IN_TIME` | Selected Circulars more than 365 days from the trigger; these remain included. |


## Viability Sweep

Use the registry-wide audit before choosing events:

```bash
.venv/bin/python scripts/event_viability_sweep.py
```

It writes `data/interim/gcn/event_matching/event_viability.csv` with per-event inclusion counts, match-type counts, conflict counts, temporal range, and flags. The current run took about 400 seconds over 574 registry events.

| Current result | Count |
|---|---:|
| Registry events | 574 |
| Events selecting zero Circulars | 385 |
| Zero-selection events with only an internal trigger ID | 365 |
| Viable events with at least five Circulars | 146 |
| Viable `grb` events | 80 |
| Viable `gcn` events | 47 |
| Viable `ep` events | 19 |

## Known Limitations

- The 365 events whose only term is an internal trigger ID cannot match ordinary Circular names.
- Suffixless-only events can still match sibling bursts through `.NN` day-fraction notation. Those events are reported but are not yet validated using coordinates or trigger time.
- Selection scans the corpus from 2023 onward. Earlier Circulars are outside the current identity index.
- `FAR_IN_TIME` is diagnostic only. Selection deliberately has no date window and does not resolve suspicious matches automatically.
