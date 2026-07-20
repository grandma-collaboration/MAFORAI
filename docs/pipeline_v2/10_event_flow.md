# Event-To-Document Flow

For whom: developers and architects who need to understand how Circular-level evidence becomes one event-level INCEpTION document.

This flow selects related GCN Circulars automatically, preserves each Circular's canonical text inside one immutable event document, translates local evidence spans to global offsets, and exports one UIMA CAS XMI file. It provides the document foundation for human `EVENT_SUMMARY` work without inventing event-level facts or changing the registered Circular-level extractors.

## Purpose

A transient event is usually described by multiple Circulars. Each Circular contributes different evidence, but annotators need one document that can be read and reviewed as a coherent event dossier.

The event flow produces that document while preserving the central v2 invariant:

```text
annotation.text
    ==
event_rendered_text[annotation.span_start:annotation.span_end]
```

The resulting XMI contains the full event text and two independent annotation layers: accepted `ASTRO_EVIDENCE` spans and row/prose `PHOTOMETRIC_MEASUREMENT` spans. Both layers use the same immutable sofa text and are round-trip checked independently.

## End-To-End Flow

```text
event_registry.csv + identity_index.parquet
          |
          v
event_selection.py
  scan all indexed Circulars
  + verify decisions through event_grouping.py
          |
          v
event_document.py
  immutable EventCanonicalDocument
  + CircularSegment map
          |
          +------------------------------+
          |                              |
          v                              v
event_annotations.py            event_photometry.py
  run 13 evidence extractors      run table + prose photometry
  + translate local offsets        + translate local offsets
          |                              |
          v                              v
ASTRO_EVIDENCE                  PHOTOMETRIC_MEASUREMENT
          |                              |
          +---------------+--------------+
                          |
                          v
scripts/event_build.py
  both annotation layers over one event text
                          |
                          v
data/inception/out/<source_id>/event_<source_id>.xmi
                          |
                          v
event_layers_roundtrip_check()
  verify text, spans, features, and annotation counts by layer
```

## 1. Grouping Circulars By Event

The implementation lives in:

```text
src/skyportal_corpus/extraction_v2/event_grouping.py
```

`select_event_candidates()` loads the event `source_id`, title, and terms from `event_registry.csv`, then applies `circular_matches_event()` to every row in the reusable identity index. The selected IDs are resolved to complete Circular dictionaries and passed through `group_event_circulars()` for an authoritative live-extraction check. Any disagreement between cached and live decisions raises an error.

The grouping primitive still receives an event `source_id`, aliases, and a candidate sequence. For the verified example, the active terms include:

```python
["GRB 260610B", "AT2026owq", "2026owq"]
```

### Alias matching

`canonical_aliases()` first tries to interpret every alias with `EventIdentityExtractor`. Standard names such as `GRB 260610B` and `AT2026owq` therefore use the same canonical normalization as the extractor itself.

`normalize_for_match()` lowercases text and removes non-alphanumeric characters for exact alias-to-identity comparison:

```text
GRB 260610B -> grb260610b
AT2026owq   -> at2026owq
2026owq     -> 2026owq
```

The raw-body fallback is not a normalized substring search. `_body_name_pattern()` splits one term into alphanumeric runs, joins them with `[^A-Za-z0-9]*`, wraps the expression in `\b` boundaries, and uses case-insensitive matching. This accepts spacing or punctuation variants but prevents `GRB240912` from matching the sibling `GRB240912A`. Its evidence records `match_type="body_name_match"` and the exact source substring.

### Membership hierarchy

`group_event_circulars()` renders each candidate with `render_canonical()`, runs `EventIdentityExtractor`, and separates identities found in the header from identities found elsewhere.

The hierarchy is:

1. **Confirmed subject identity:** an identity in the header with `needs_review=False` is authoritative. If it matches an event alias, the Circular is included with `reason="confirmed_subject_match"`.
2. **Confirmed competing event:** if the subject confirms another event while the body mentions the requested event, the Circular is excluded with `reason="confirmed_other_event"`. A body reference cannot override the event named by the subject.
3. **Body fallback:** only when there is no confirmed subject identity may an extracted body identity or boundary-aware body-name match include the Circular with `reason="body_mention"`.
4. **No evidence:** candidates without a usable match are excluded with `reason="no_match"`.

The real Circular `44891` demonstrates why this ordering matters. Its subject identifies `GRB 260610A`, while its body mentions `GRB 260610B`. It is excluded from `2026owq` as `confirmed_other_event`; otherwise a comparison or reference could silently contaminate the event dossier.

Included and excluded entries retain the `circular_id`, subject, creation time, decision reason, and matching evidence. Both lists are sorted by `created_on` and then `circular_id`. The complete selection audit is written to `data/interim/gcn/event_matching/selections/selection_<source_id>.txt`.

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

For each Circular, it calls the 13 extractors returned by `get_active_extractors()`:

```text
event_identity
trigger_time
localization
trigger_instrument
redshift
duration
high_energy
negative_statement
lightcurve_evolution
counterpart_association
classification_interpretation
host_context
spectroscopy
```

Each extractor still works against the local Circular document. Its accepted offsets are translated afterward:

```python
global_start = local_to_global(event_doc, circular_id, annotation.span_start)
global_end = local_to_global(event_doc, circular_id, annotation.span_end)
```

The translated annotation receives the event text SHA-256 and is verified against `event_rendered_text`. A mismatch is recorded and excluded rather than exported with a broken span. The verified `2026owq` run reported zero broken global offsets.

`source_circular_id` preserves the source Circular as structured internal provenance. It is not exported to INCEpTION because `ASTRO_EVIDENCE` does not define that feature. The original `circular_id` also remains available in the Python annotation.

The `comment` field has a narrower purpose: it contains an English review instruction only when `needs_review=True`. Confirmed annotations have an empty comment. Provenance is never encoded in `comment`.

### Photometry offsets

`extract_event_photometry()` in `event_photometry.py` runs table-row and prose photometry against each local `CanonicalDocument`, translates accepted spans with the same `local_to_global()` map, verifies the event-text slice, and stores `source_circular_id` as internal provenance. Broken translated spans are excluded rather than exported.

## 4. Exporting One Event XMI

The executable entry point is:

```text
scripts/event_build.py --source-id <id>
```

The script runs automatic selection, builds the event document, and calls `export_event_layers_xmi()` from `inception_v2/event_xmi_export.py`. It creates one CAS whose sofa is the immutable event text, adds minimal segmentation, verifies every span, and writes both custom layers.

The INCEpTION layers are:

```text
webanno.custom.ASTRO_EVIDENCE
webanno.custom.PHOTOMETRIC_MEASUREMENT
```

`ASTRO_EVIDENCE` exports six string features:

```text
label
target
certainty
value
unit
comment
```

Photometry features are mapped by `photometry_feature_values()` and include measurement type, magnitude/error/limit confidence, band/system, observation time, exposure, instrument, and review comment when those features exist in the loaded TypeSystem. `needs_review` and `source_circular_id` remain internal fields for both paths; reviewable annotations remain visible through their non-empty review comment.

The event script writes:

```text
data/inception/out/<source_id>/event_<source_id>.xmi
data/inception/out/<source_id>/event_<source_id>_manifest.txt
```

The manifest lists the event hash, output path, summaries for both layers, and per-Circular contributions.

The tracked flat pilot files under `data/inception/out/` are superseded. The current automatic build always uses the source-specific directory shown above.

Finally, `event_layers_roundtrip_check()` reloads the XMI and verifies each layer independently:

```text
text_matches
all_spans_ok
all_features_ok
n_original == n_roundtripped
```

## Related Documents

- [Canonical text](./02_canonical_text.md)
- [Annotations and tagsets](./03_annotations_and_tagsets.md)
- [INCEpTION export](./05_inception_export.md)
- [Reproducing an event XMI](./11_reproduce_event_xmi.md)
- [Automatic event selection](./13_event_selection.md)
- [Status and roadmap](./07_status_and_roadmap.md)
- [Photometric measurement layer](./12_photometry.md)

## Known Limitations

- **Selection starts in 2023.** The current identity index excludes older Circulars unless rebuilt with a lower `min_year`.
- **Internal IDs are weak names.** Events whose only term is an internal trigger ID usually select no Circulars.
- **Suffixless-only terms need review.** They can still match `.NN` day-fraction sibling names and are not automatically resolved with coordinates or trigger time.
- **The export has two annotation layers.** All 13 evidence extractors write to `ASTRO_EVIDENCE`; individual optical/NIR/UV measurements use `PHOTOMETRIC_MEASUREMENT`.
- **Comments are review-only.** A comment is present only when human review is requested. It is not a general metadata or provenance field.
- **Extraction remains Circular-local.** The evidence extractors and both photometry paths do not reason across Circular boundaries. The event document only preserves and combines their outputs.
- **No event summary is inferred.** Repeated or conflicting evidence is intentionally retained. Annotators fill `EVENT_SUMMARY` in INCEpTION's Document Metadata panel.
