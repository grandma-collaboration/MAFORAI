# Event-To-Document Flow

For whom: developers and architects who need to understand how Circular-level evidence becomes one event-level INCEpTION document.

This flow groups related GCN Circulars, preserves each Circular's canonical text inside one immutable event document, translates local evidence spans to global offsets, and exports one UIMA CAS XMI file. It provides the document foundation for future `EVENT_SUMMARY` work without inventing event-level facts or changing the five Circular-level extractors.

## Purpose

A transient event is usually described by multiple Circulars. Each Circular contributes different evidence, but annotators need one document that can be read and reviewed as a coherent event dossier.

The event flow produces that document while preserving the central v2 invariant:

```text
annotation.text
    ==
event_rendered_text[annotation.span_start:annotation.span_end]
```

The resulting XMI contains the full event text and all accepted `ASTRO_EVIDENCE` spans. The current verified example is `2026owq`, titled `GRB 260610B / AT2026owq`: 28 Circulars, 120 annotations, 11 annotations marked for review, and a successful XMI round-trip.

## End-To-End Flow

```text
event metadata + aliases
          |
          v
event_grouping.py
  include/exclude candidate Circulars
          |
          v
event_document.py
  immutable EventCanonicalDocument
  + CircularSegment map
          |
          v
event_annotations.py
  run 5 extractors on each local CanonicalDocument
  + translate local offsets to global offsets
          |
          v
event_xmi_export.py
  ASTRO_EVIDENCE annotations over one event text
          |
          v
data/inception/out/event_2026owq.xmi
          |
          v
xmi_roundtrip.py
  verify text, spans, features, and annotation count
```

## 1. Grouping Circulars By Event

The implementation lives in:

```text
src/skyportal_corpus/extraction_v2/event_grouping.py
```

The grouping input is an event `source_id`, a list of aliases, and a candidate sequence of real Circular dictionaries. For the verified example, the aliases are:

```python
["GRB 260610B", "AT2026owq", "2026owq"]
```

### Alias matching

`canonical_aliases()` first tries to interpret every alias with `EventIdentityExtractor`. Standard names such as `GRB 260610B` and `AT2026owq` therefore use the same canonical normalization as the extractor itself.

Aliases that the extractor does not recognize, such as the source identifier `2026owq`, remain available through direct normalized matching. `normalize_for_match()` lowercases the text and removes non-alphanumeric characters:

```text
GRB 260610B -> grb260610b
AT2026owq   -> at2026owq
2026owq     -> 2026owq
```

This fallback is deliberately simple. It supports known non-standard aliases without creating a second event-name parser.

### Membership hierarchy

`group_event_circulars()` renders each candidate with `render_canonical()`, runs `EventIdentityExtractor`, and separates identities found in the header from identities found elsewhere.

The hierarchy is:

1. **Confirmed subject identity:** an identity in the header with `needs_review=False` is authoritative. If it matches an event alias, the Circular is included with `reason="confirmed_subject_match"`.
2. **Confirmed competing event:** if the subject confirms another event while the body mentions the requested event, the Circular is excluded with `reason="confirmed_other_event"`. A body reference cannot override the event named by the subject.
3. **Body fallback:** only when there is no confirmed subject identity may an extracted body identity or direct normalized body mention include the Circular with `reason="body_mention"`.
4. **No evidence:** candidates without a usable match are excluded with `reason="no_match"`.

The real Circular `44891` demonstrates why this ordering matters. Its subject identifies `GRB 260610A`, while its body mentions `GRB 260610B`. It is excluded from `2026owq` as `confirmed_other_event`; otherwise a comparison or reference could silently contaminate the event dossier.

Included and excluded entries retain the `circular_id`, subject, creation time, decision reason, and matching evidence. Both lists are sorted by `created_on` and then `circular_id`.

## 2. Building The Event Canonical Document

The implementation lives in:

```text
src/skyportal_corpus/extraction_v2/event_document.py
```

`build_event_document()` sorts included Circulars chronologically and calls the existing `render_canonical()` for each one. It does not reimplement Circular canonicalization.

Before every local canonical text, it inserts this immutable separator:

```text


===== CIRCULAR <circular_id> =====


```

In Python, the exact template is:

```python
"\n\n===== CIRCULAR {circular_id} =====\n\n"
```

The separators are part of `event_rendered_text` and therefore count toward global offsets. A `CircularSegment` records the half-open range `[global_start, global_end)` occupied by the local canonical text after its separator.

### Preserved-text invariant

For every segment:

```python
event_rendered_text[segment.global_start:segment.global_end]
```

must equal the original Circular's `CanonicalDocument.rendered_text`. The segment also stores that Circular's `text_sha256`, so equality can be checked without modifying either text.

The complete event text receives its own `event_text_sha256`. Once built, this text is treated as immutable for the same reason as Circular canonical text: every global annotation offset depends on it.

### Offset map

`local_to_global()` translates a Circular-local offset:

```python
global_offset = segment.global_start + local_offset
```

`global_to_circular()` maps a global character position inside a segment back to:

```text
(circular_id, local_offset)
```

Offsets inside separators return `None`. The same is true for the one-past-the-end boundary because segment membership uses half-open ranges. For character positions inside Circular text, the two functions are exact inverses.

## 3. Producing Event-Level Annotations

The implementation lives in:

```text
src/skyportal_corpus/extraction_v2/event_annotations.py
```

`extract_event_annotations()` walks the event segments and retrieves the matching local `CanonicalDocument`. It verifies that the local SHA-256 agrees with the segment before extraction.

For each Circular, it calls the five extractors returned by `get_active_extractors()`:

```text
event_identity
trigger_time
localization
trigger_instrument
redshift
```

Each extractor still works against the local Circular document. Its accepted offsets are translated afterward:

```python
global_start = local_to_global(event_doc, circular_id, annotation.span_start)
global_end = local_to_global(event_doc, circular_id, annotation.span_end)
```

The translated annotation receives the event text SHA-256 and is verified against `event_rendered_text`. A mismatch is recorded and excluded rather than exported with a broken span. The verified `2026owq` run reported zero broken global offsets.

`source_circular_id` preserves the source Circular as structured internal provenance. It is not exported to INCEpTION because `ASTRO_EVIDENCE` does not define that feature. The original `circular_id` also remains available in the Python annotation.

The `comment` field has a narrower purpose: it contains an English review instruction only when `needs_review=True`. Confirmed annotations have an empty comment. Provenance is never encoded in `comment`.

## 4. Exporting One Event XMI

The executable entry point is:

```text
scripts/event_xmi_export.py
```

The script reuses `export_document_to_xmi()` with an adapter whose `rendered_text` is the immutable event text. This keeps CAS creation, minimal sentence/token segmentation, feature mapping, and span validation in the existing XMI exporter.

The internal INCEpTION layer is:

```text
webanno.custom.ASTRO_EVIDENCE
```

It exports six string features:

```text
label
target
certainty
value
unit
comment
```

`needs_review` and `source_circular_id` are internal fields and are not features in the current TypeSystem. Reviewable annotations remain visible through their non-empty review comment.

The event script writes:

```text
data/inception/out/event_2026owq.xmi
data/inception/out/event_2026owq_manifest.txt
```

The manifest lists the event hash, output path, counts by extractor and label, and all 28 Circulars with their date, subject, annotation count, and label counts.

Finally, `roundtrip_check()` reloads the XMI and verifies:

```text
text_matches
all_spans_ok
all_features_ok
n_original == n_roundtripped
```

For the verified `2026owq` export, all checks passed for 120 annotations.

## Known Limitations And Decisions

- **Aliases are manual.** `SOURCE_ID`, `TITLE`, and `ALIASES` are currently constants in the event scripts. Automatic use of the existing `event_search_terms` data is future work.
- **Candidate selection is example-specific.** The current scripts use year 2026 and Circular IDs `44880..45050`. A general command-line interface has not yet replaced these constants.
- **One annotation layer carries all labels.** Event identity, time, localization, instrument, and redshift evidence are all exported to `ASTRO_EVIDENCE`.
- **Comments are review-only.** A comment is present only when human review is requested. It is not a general metadata or provenance field.
- **Extraction remains Circular-local.** The five extractors do not reason across Circular boundaries. The event document only preserves and combines their evidence.
- **No event summary is inferred yet.** Repeated or conflicting evidence is intentionally retained. Resolving it into `EVENT_SUMMARY` is future work built on this global offset map.

## Related Documents

- [Canonical text](./02_canonical_text.md)
- [Annotations and tagsets](./03_annotations_and_tagsets.md)
- [INCEpTION export](./05_inception_export.md)
- [Reproducing an event XMI](./11_reproduce_event_xmi.md)
- [Status and roadmap](./07_status_and_roadmap.md)
