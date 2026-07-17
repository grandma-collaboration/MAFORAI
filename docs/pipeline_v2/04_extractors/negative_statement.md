# Negative Statement Extractor

For whom: developers maintaining scientific-negation extraction and annotators reviewing rejections, absences, and cross-layer ownership.

`NegativeStatementExtractor` emits the qualitative label `NEGATIVE_STATEMENT` for non-photometric scientific rejections and negative findings. It selects the smallest clause that carries the negation and deliberately leaves photometric non-detections and light-curve behavior to their dedicated labels.

## Output

| Field | Value |
|---|---|
| `label` | `NEGATIVE_STATEMENT` |
| `target` | unset (`None`) |
| `certainty` | `rejected` or `confirmed` |
| `method` | `regex` |
| `extractor_id` | `negative-statement-v1` |
| `extractor_version` | `0.1` |

`value` and `unit` are unset. `comment` is also unset unless `needs_review=True`; the catalog-sensitivity counterpart rule is the current review-producing case.

## Rules

| Rule ID | What it captures | Example |
|---|---|---|
| `negative_statement.retraction` | retractions and retracted reports | `retraction of GCN 44900` |
| `negative_statement.not_grb` | explicit rejection of GRB identity | `not a GRB` |
| `negative_statement.false_trigger` | false-trigger claims | `GRB 250101A is a false trigger` |
| `negative_statement.not_associated` | explicit association rejection | `not associated with the host galaxy` |
| `negative_statement.unrelated` | `unrelated to` and clause-final `are unrelated` | `GRB 250309B and IceCube-250309A are unrelated` |
| `negative_statement.unlikely` | soft identity or association rejection | `unlikely to be the X-ray counterpart` |
| `negative_statement.rules_out` | positive rule-out statements | `rules out the association` |
| `negative_statement.identity_rejection` | rejection of counterpart or afterglow identity | `not the afterglow` |
| `negative_statement.not_consistent` | explicit inconsistency with a proposal | `not consistent with the proposed association` |
| `negative_statement.not_real` | non-real source, event, signal, or trigger claims | `not a real astrophysical event` |
| `negative_statement.spurious` | spurious trigger, detection, signal, source, or event | `spurious trigger` |
| `negative_statement.cannot_confirm` | inability to confirm an association, classification, or identification | `cannot confirm the association` |
| `negative_statement.no_counterpart` | explicit absence of a counterpart or counterpart candidates | `No optical counterpart consistent with the INTEGRAL position` |
| `negative_statement.no_evidence` | no evidence for or of a scientific phenomenon | `no evidence for a supernova` |
| `negative_statement.no_signature` | absence of a scientific signature | `no signature of a supernova` |
| `negative_statement.no_significant` | no significant signal, excess, emission, or activity | `no significant X-ray signal` |
| `negative_statement.absent_phenomenon` | explicit absent jet break, supernova, kilonova, or host | `no jet break` |
| `negative_statement.not_confirmed` | a finding or association stated as not confirmed | `not confirmed` |

## Certainty Semantics

Retractions, false identities, rejected associations, rule-outs, spurious events, and soft identity rejections use `certainty="rejected"`. Negative scientific findings, counterpart absence, and `not confirmed` use `certainty="confirmed"`: the certainty describes the text's negative claim, not confidence in the rejected hypothesis.

`cannot be ruled out` is not inverted into a rejection. Methodological prose such as `searched ... to rule out unrelated transients` is also excluded.

## Anti-Photometry Gate

Every rule is checked against the complete containing sentence. A negative is deferred to `PHOTOMETRIC_MEASUREMENT` when that sentence contains optical, IR, or radio photometric evidence such as a filter or band, a magnitude or depth, `Jy` units, forced photometry, or imaging language.

Examples rejected here include:

```text
source not detected (J > 20 mag)
no optical counterpart in our i-band images
no evidence ... down to a 5-sigma depth of >20.8 AB mag
```

X-ray or gamma-ray flux units and catalog sensitivity are not photometry-layer evidence. A counterpart absence based on catalog sensitivity is retained with `needs_review=True` and a comment asking the annotator to verify catalog scope and completeness.

## Light-Curve Boundary

Negative behavior such as `no evidence for fading`, `no significant variability`, or `does not fade` belongs to `LIGHTCURVE_EVOLUTION`. These candidates are rejected before annotation construction.

A bare `not detected` without a supported rejection, finding, or counterpart-absence structure is intentionally not emitted.

## De-Overlap

Specific rejection rules have priority over broad negative-finding rules. Within a priority, the smaller overlapping clause wins, preserving the requested evidence granularity. Results are returned in source order.

## Known Limitations

The extractor does not resolve unrestricted natural-language negation or every implied absence. Sentence-scoped photometry gating can defer mixed sentences whose scientific clauses should be separated, and catalog-based counterpart absence still requires human review.
