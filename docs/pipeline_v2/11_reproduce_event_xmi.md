# Reproducing An Event XMI

For whom: developers and tutors who need to regenerate and inspect the event-level INCEpTION deliverable.

This guide reproduces the verified `2026owq` flow from event grouping through XMI round-trip. The commands use the repository's Python virtual environment directly, so they do not depend on shell activation.

## Prerequisites

Run every command from the repository root:

```text
MAFORAI/
```

The required interpreter is:

```text
.venv/bin/python
```

The real INCEpTION TypeSystem must exist at:

```text
data/inception/TypeSystem.xml
```

It must define `webanno.custom.ASTRO_EVIDENCE` with the six string features `label`, `target`, `certainty`, `value`, `unit`, and `comment`. The real Circular index or raw archive used by `iter_real_circulars()` must also be available under the repository's `data/` tree.

## 1. Check The Event Definition

The current example is defined manually in each event script:

```python
SOURCE_ID = "2026owq"
TITLE = "GRB 260610B / AT2026owq"
ALIASES = ["GRB 260610B", "AT2026owq", "2026owq"]
MIN_CIRCULAR_ID = 44880
MAX_CIRCULAR_ID = 45050
```

These constants appear in:

```text
scripts/event_grouping_demo.py
scripts/event_document_demo.py
scripts/event_xmi_export.py
```

The scripts currently request real Circulars from 2026 and then retain the configured Circular ID range. Keep the definitions aligned across all three scripts.

## 2. Inspect Event Grouping

Run:

```bash
.venv/bin/python scripts/event_grouping_demo.py
```

The command prints:

```text
SUMMARY
INCLUDED
EXCLUDED
CHECK 44891
```

For each candidate, inspect the decision reason and evidence:

- `confirmed_subject_match` means the authoritative subject identity matches an alias.
- `body_mention` means no confirmed subject identity existed and the body supplied the match.
- `confirmed_other_event` means the subject identified another event and overruled a body reference.
- `no_match` means the candidate did not provide usable membership evidence.

The final `CHECK 44891` must report exclusion as `confirmed_other_event`: its subject is `GRB 260610A`, not the requested `GRB 260610B`.

This demo writes no report file automatically; its complete report is standard output.

## 3. Verify The Event Canonical Document

Run:

```bash
.venv/bin/python scripts/event_document_demo.py
```

The command groups the same candidates, keeps the included Circulars, and builds `EventCanonicalDocument`. It prints the event SHA-256, total text length, and every segment's global range.

The expected checks are:

```text
segment_sha256_survives: OK
local_global_inverse_offsets: OK
segment_count_is_28: OK
```

The first 800 characters show the immutable separator followed by the first Circular's canonical `SUBJECT`, `DATE`, `FROM`, and body.

## 4. Generate The XMI And Manifest

Run:

```bash
.venv/bin/python scripts/event_xmi_export.py
```

The script repeats grouping and event-document construction, runs all five active extractors on every included Circular, translates local offsets to global offsets, and exports the event CAS.

The output files are:

```text
data/inception/out/event_2026owq.xmi
data/inception/out/event_2026owq_manifest.txt
```

The verified summary is:

```text
n_circulars: 28
total_annotations: 120
needs_review: 11
annotations_with_comment: 11
comments_only_when_needs_review: OK
broken_global_offsets: 0
FINAL: OK
```

`FINAL: OK` requires an exact text match, valid round-tripped spans, identical exported features, and equal original/round-tripped annotation counts.

The manifest is the human-readable companion to the XMI. Use it to inspect the Circular list and annotation distribution without parsing XML.

## 5. Run The Focused Tests

The event flow has synthetic tests that do not depend on the real `2026owq` data:

```bash
.venv/bin/python -m pytest \
  tests/test_event_grouping.py \
  tests/test_event_document.py \
  tests/test_event_annotations.py \
  tests/test_xmi_roundtrip.py
```

These tests cover membership hierarchy, immutable segment slices, local/global offset translation, source-Circular provenance, XMI features, and round-trip integrity.

## 6. Import Into INCEpTION

1. Create an INCEpTION project, or import the existing project archive that owns the expected annotation layer.
2. Import the TypeSystem corresponding to `data/inception/TypeSystem.xml` if the project does not already contain it.
3. Add a document using the **UIMA CAS XMI XML 1.0** format.
4. Select `data/inception/out/event_2026owq.xmi`.
5. Open the imported document and select the `ASTRO_EVIDENCE` span layer.
6. Review annotations with non-empty comments first; those are the machine proposals marked for human review.

The XMI contains the event text and the six INCEpTION features. Internal fields such as `source_circular_id` and `needs_review` are not TypeSystem features.

## Reproducing A Different Event

Until a command-line event configuration is added, edit the same constants in all three event scripts:

```text
SOURCE_ID
TITLE
ALIASES
MIN_CIRCULAR_ID
MAX_CIRCULAR_ID
```

Also update the `min_year` used by `_candidate_circulars()` and change `XMI_PATH` and `MANIFEST_PATH` in `scripts/event_xmi_export.py` so the new run does not overwrite the `2026owq` deliverable.

Then run the three commands in order:

```bash
.venv/bin/python scripts/event_grouping_demo.py
.venv/bin/python scripts/event_document_demo.py
.venv/bin/python scripts/event_xmi_export.py
```

Do not skip the grouping review. Manual aliases and candidate ranges are temporary controls, and an incorrect event membership decision will propagate into the canonical event text and every global annotation offset.

Automatic alias loading from `event_search_terms` is planned but not yet connected to this flow.

## Related Documents

- [Event-to-document flow](./10_event_flow.md)
- [INCEpTION export](./05_inception_export.md)
- [Canonical text](./02_canonical_text.md)
- [Status and roadmap](./07_status_and_roadmap.md)
