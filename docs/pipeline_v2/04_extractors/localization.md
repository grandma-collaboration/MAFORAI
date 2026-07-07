# Localization Extractor

For whom: developers maintaining localization extraction and annotators reviewing coordinate preannotations.

`LocalizationExtractor` finds sky positions and error-region phrases in canonical Circular text. It emits `LOCALIZATION` annotations for both coordinates and uncertainty values because both are evidence about where the event or counterpart is located.

## Output

| Field | Value |
|---|---|
| `label` | `LOCALIZATION` |
| `target` | `event` by default, or `counterpart` when local text says counterpart/afterglow/optical transient |
| `certainty` | `confirmed` |
| `method` | `regex` |
| `extractor_id` | `localization-v1` |
| `extractor_version` | `0.1` |

## Patterns

| Rule ID | What it captures | Example |
|---|---|---|
| `localization.radec_decimal` | Labeled RA/Dec decimal degrees | `RA = 206.3, Dec = -21.9` |
| `localization.radec_sexagesimal` | Labeled RA/Dec sexagesimal pairs | `RA = 13:45:00, Dec = -21:53:00` |
| `localization.error_radius` | Localization uncertainty phrases | `statistical uncertainty of 2.8 degrees` |

The extractor accepts common labels such as `RA`, `R.A.`, `Dec`, `Decl.`, and `Declination`.

## Values And Units

For coordinate pairs, `value` preserves the raw numeric representation:

```text
RA=206.3, Dec=-21.9
```

The extractor does not convert sexagesimal coordinates to degrees. That decision is intentional: conversion adds scientific assumptions and is not required for span evidence. The raw span remains the evidence, and any later coordinate-normalization layer can convert values explicitly.

For uncertainty spans, `value` is the number and `unit` is normalized where possible. A prime symbol is normalized to `arcmin`; `deg`, `degrees`, and `d` normalize to `deg`. The `comment` is `positional uncertainty`.

## Decimal-Sexagesimal De-Duplication

GCN Circulars often report the same point twice:

```text
RA = 206.3, Dec = -21.9 (J2000 degrees, equivalent to J2000 13h 45m, -21d 53')
```

The extractor keeps the decimal coordinate and suppresses a nearby sexagesimal duplicate when it falls within +/-120 characters of the accepted decimal match. This is a transparent heuristic: decimal coordinates are usually easier to compare at scale, while the span evidence still points to the reported value.

## Target Selection

The default target is `event`. If the local context contains words such as `counterpart`, `afterglow`, `optical transient`, or `OT`, the target becomes `counterpart`.

```text
the optical counterpart is at RA = 150.1, Dec = 22.2
```

That coordinate is a `LOCALIZATION` annotation with `target="counterpart"`.

## Known Limitations

The extractor does not parse unlabeled coordinate pairs. It also does not model coordinate frames, confidence levels, or polygon/skymap regions. It is designed as a first span-first layer for the most common RA/Dec and uncertainty statements.
