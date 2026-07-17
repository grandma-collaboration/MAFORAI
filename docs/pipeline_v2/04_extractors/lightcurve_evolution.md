# Light-Curve Evolution Extractor

For whom: developers maintaining qualitative temporal-behavior extraction and annotators reviewing light-curve evolution spans.

`LightcurveEvolutionExtractor` emits `LIGHTCURVE_EVOLUTION` for observed fading, rising, flattening, variability, and explicit absence of those behaviors. It describes what the counterpart light curve does, not the physical explanation for that behavior.

## Output

| Field | Value |
|---|---|
| `label` | `LIGHTCURVE_EVOLUTION` |
| `target` | `counterpart` |
| `certainty` | `confirmed` |
| `method` | `regex` |
| `extractor_id` | `lightcurve-evolution-v1` |
| `extractor_version` | `0.1` |

`value` and `unit` are unset because the annotation is qualitative. `comment` is unset and `needs_review=False` for current captures; the exact behavior phrase remains in `text`.

## Rules

| Rule ID | What it captures | Example |
|---|---|---|
| `lightcurve_evolution.negative` | confirmed absence of fading, evolution, or variability | `There is no evidence for fading` |
| `lightcurve_evolution.fade_decline` | fading, decline, dimming, steepening, and decay | `The source continues to fade` |
| `lightcurve_evolution.rise_brightening` | rising, brightening, rebrightening, and increased brightness | `optical rebrightening` |
| `lightcurve_evolution.flatten_plateau` | flattening, plateaus, leveling, or constant behavior | `flattening of the light curve` |
| `lightcurve_evolution.variability` | variable, fluctuating, or flaring behavior | `The counterpart is variable` |

## Observed Behavior Boundary

The extractor accepts an observed behavior clause:

```text
We observe a rebrightening.
```

It rejects a clause that uses the behavior only as the subject of a physical explanation:

```text
This rebrightening may be due to late jet activity.
```

Cause connectors include `due to`, `consistent with`, `attributed to`, `indicative of`, `suggests`, `explained by`, `caused by`, and `interpreted as`. Those clauses belong to `CLASSIFICATION_INTERPRETATION`.

If observation and cause are separate clauses, only the observed behavior is emitted here.

## Negative Behavior

`no evidence for fading`, `no significant variability`, `no evolution`, and `does not fade` are positive evidence of flat or absent evolution. They therefore use `certainty="confirmed"` rather than `rejected` and are not `NEGATIVE_STATEMENT` annotations.

## Context Gate

Broad words such as `flat`, `steady`, `constant`, `variable`, and `flaring` require nearby light-curve context. Accepted context includes `light curve`, `source`, `afterglow`, `counterpart`, `transient`, `flux`, `brightness`, `emission`, or `count rate`.

This keeps `The counterpart is variable` while rejecting unrelated classifications such as `The comparison object is a variable star`.

## De-Overlap

The negative-behavior rule has priority over individual behavior tokens. Other family rules share the next priority, and the longest overlapping candidate is retained. Accepted annotations are returned in source order.

## Known Limitations

The extractor does not model temporal phases, associate behavior with numeric epochs, or infer evolution from a sequence of measurements. Generic descriptors without explicit light-curve context remain uncovered, and mixed observation/interpretation clauses may require manual separation.
