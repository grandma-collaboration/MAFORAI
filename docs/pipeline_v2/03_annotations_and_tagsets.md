# Annotations And Tagsets

For whom: developers who create or validate pipeline v2 annotations.

`EventEvidenceAnnotation` is the shared output model for every extractor. It combines exact text offsets, INCEpTION tagset values, normalized values, provenance, confidence, and review flags in one validated object.

## Annotation Fields

| Field | Why it exists |
|---|---|
| `circular_id` | Keeps the annotation tied to the GCN Circular that produced it. |
| `text_sha256` | Identifies the exact canonical text version used for extraction. |
| `span_start`, `span_end` | Character offsets into `CanonicalDocument.rendered_text`. |
| `text` | The exact substring selected by the offsets. |
| `label` | The scientific evidence type, such as `EVENT_IDENTITY` or `TRIGGER_TIME`. |
| `target` | The entity the evidence refers to, such as `event` or `instrument`. |
| `certainty` | The extractor's certainty category using the INCEpTION tagset. |
| `value` | A normalized machine-readable value, when available. The raw text remains in `text`. |
| `unit` | A normalized unit, when a quantity has one. |
| `comment` | Human-readable context for review, especially ambiguity. |
| `extractor_id`, `extractor_version` | Provenance for the software that produced the annotation. |
| `method`, `rule_id` | Provenance for the extraction method and specific rule. |
| `confidence` | Numeric confidence used by the extractor. |
| `needs_review` | Marks cases where the machine can propose but should not decide alone. |
| `schema_version` | Version of this annotation schema. |

The key invariant is:

```python
rendered_text[span_start:span_end] == text
```

The method `verify(rendered_text)` checks exactly that condition and also confirms that the offsets are inside the text bounds.

## Tagsets

The tagsets are the single source of truth for extractor outputs and must match the `EVENT_EVIDENCE` layer in INCEpTION.

### Labels: 17 Values

```text
EVENT_IDENTITY
TRIGGER_TIME
TRIGGER_INSTRUMENT
LOCALIZATION
COUNTERPART_ASSOCIATION
PHOTOMETRY_TABLE
REDSHIFT_EVENT
REDSHIFT_CONTEXT
T90
DURATION_GENERAL
SPECTROSCOPY
HIGH_ENERGY_PROPERTY
HOST_CONTEXT
CLASSIFICATION_INTERPRETATION
FOLLOWUP_ACTION
NEGATIVE_STATEMENT
LIGHTCURVE_EVOLUTION
```

### Targets: 6 Values

```text
event
counterpart
host
nearby_galaxy
instrument
unknown
```

### Certainties: 5 Values

```text
confirmed
candidate
tentative
rejected
unclear
```

## Referenced Events

When an extractor sees an event name that may be a referenced comparison event rather than the main Circular event, it still uses `target="event"` and sets `needs_review=True`.

For example, `EventIdentityExtractor` marks an event name as lower confidence when the normalized value appears only in the body and not in the header. The human annotator then decides whether it is an alias for the main event or a referenced event.

