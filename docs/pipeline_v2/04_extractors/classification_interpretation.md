# Classification And Interpretation Extractor

For whom: developers maintaining event classification extraction and annotators reviewing physical-class and interpretation spans.

`ClassificationInterpretationExtractor` emits `CLASSIFICATION_INTERPRETATION` for GRB class statements, transient classes, and physical explanations. It separates an observed behavior from the proposed cause and keeps positional consistency and rejected classifications out of the positive label.

## Output

| Field | Value |
|---|---|
| `label` | `CLASSIFICATION_INTERPRETATION` |
| `target` | `event` |
| `certainty` | `confirmed` or `tentative` |
| `method` | `regex` |
| `extractor_id` | `classification-interpretation-v1` |
| `extractor_version` | `0.1` |

`value` and `unit` are unset because the selected text is the classification or interpretation claim. `comment` is unset and `needs_review=False` for current captures.

## Rules

| Rule ID | What it captures | Example |
|---|---|---|
| `classification_interpretation.firm_classification` | explicit firm classification markers plus a physical class | `spectroscopically classified as a Type Ic supernova` |
| `classification_interpretation.physical_cause` | a behavior or event attributed to a physical mechanism | `This rebrightening may be due to late jet activity` |
| `classification_interpretation.qualified_class` | likely, possible, probable, or potential physical classes | `possible supernova` |
| `classification_interpretation.type_grb` | `Type I GRB` or `Type II GRB` classes | `Type II GRB` |
| `classification_interpretation.extended_emission` | the established short-GRB extended-emission class phrase | `short GRB with extended emission` |
| `classification_interpretation.claim` | event-subject claims such as `this event is a ...` | `this event is a kilonova` |
| `classification_interpretation.this_is` | direct `this is` physical-class claims | `this is a collapsar` |
| `classification_interpretation.inferred_phenomenon` | classes inferred from data, spectra, or observations | `the spectrum suggests a supernova` |
| `classification_interpretation.interpretation` | suggestions, interpretations, physical consistency, class-like forms, and mechanisms | `make a kilonova the most likely interpretation` |
| `classification_interpretation.grb_class` | long, short, ultra-long, soft, or hard GRB class statements | `long-duration GRB 230114A` |

## Certainty

Firm markers such as `classified as`, `confirmed as`, `spectroscopically classified as`, `firmly established as`, and `identified as` produce `confirmed`. Other physical classes and interpretations are `tentative` by default.

`grb_class` has separate statement logic. An unhedged class such as `The long GRB 240205B` is `confirmed`; nearby `likely`, `possible`, `probable`, `tentatively`, or `typical ... of` language makes it `tentative`. A plain `Type II GRB` matched by `type_grb` remains tentative unless a firm marker governs it.

## Physical-Class Vocabulary

Supported classes and mechanisms include long/short GRBs, Type I/II GRBs, supernova and SN subtypes, kilonovae, TDEs, GRB afterglows, magnetars, tidal disruption, compact-binary mergers, blazar or AGN flares, shocks, shock breakout or cooling, jet breaks, collapsars, energy injection, and central-engine activity.

Class-like forms such as `AT2017gfo-like kilonova` and interpretive structures such as `consistent with those of very young supernovae` are accepted.

## Light-Curve Handoff

Observed behavior belongs to `LIGHTCURVE_EVOLUTION`:

```text
The light curve shows a rebrightening.
```

The physical-cause clause belongs here:

```text
This rebrightening may be due to late jet activity.
```

## Consistency Gate

`consistent with` is accepted only when its object is a supported physical class or phenomenon. Positional and result consistency, such as `consistent with the Swift-XRT position` or `upper limits are consistent with ...`, is not captured.

## Rejection And Request Gates

Negated or ruled-out classifications belong to `NEGATIVE_STATEMENT`. The extractor rejects prefixes such as `ruled out as`, `not`, `unlikely to be`, `cannot be`, and `disfavored as`, as well as a tentative classification followed by an explicit retraction.

Calls to `explore`, `determine`, `establish`, `clarify`, or `investigate the nature of` a transient are requests for classification, not class claims, and are excluded.

## De-Overlap

Firm classifications and complete physical-cause clauses outrank qualified or generic classes. Overlapping lower-priority candidates are removed, with accepted annotations returned in source order.

## Known Limitations

The physical vocabulary is finite and does not perform ontology resolution or discourse-level certainty analysis. Complex sentences containing several competing interpretations may yield one longest span rather than separate claims, and unsupported transient classes remain uncovered.
