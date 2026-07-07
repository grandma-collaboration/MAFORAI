# Redshift Extractor

For whom: developers maintaining redshift extraction and annotators reviewing the most attribution-sensitive preannotations.

`RedshiftExtractor` emits two labels: `REDSHIFT_EVENT` for redshifts attributed to the event, afterglow, counterpart, or host; and `REDSHIFT_CONTEXT` for explicit contextual galaxies or intervening systems. This extractor is deliberately cautious because the expensive error is to classify an event redshift as context and make the most valuable value easy to ignore.

## Output

| Field | Event redshift | Context redshift |
|---|---|---|
| `label` | `REDSHIFT_EVENT` | `REDSHIFT_CONTEXT` |
| `target` | `event`, `counterpart`, or `host` | `nearby_galaxy` |
| `certainty` | `confirmed`, `tentative`, or `rejected` | `confirmed`, `tentative`, or `rejected` |
| `method` | `regex` | `regex` |
| `extractor_id` | `redshift-v1` | `redshift-v1` |
| `extractor_version` | `0.1` | `0.1` |

## Rules

| Rule ID | What it captures | Example |
|---|---|---|
| `redshift.z_equals` | `z` followed by `=`, `~`, or the approximate sign, then a decimal | `z = 0.473` |
| `redshift.z_spec` | `z_spec`, `zphot`, `zabs`, or `zem` | `z_spec = 1.2` |
| `redshift.redshift_word` | the word `redshift` followed by a decimal, with optional `z=` | `redshift of z=0.887` |
| `redshift.z_range` | bounded redshift ranges | `0.10 < z < 0.17` |

The raw span is stored in `text`; the numeric value or range is stored in `value`. Redshift is dimensionless, so `unit` is empty.

## Golden Rule

When attribution is unclear, the extractor emits `REDSHIFT_EVENT` with `needs_review=True`. It does not emit `REDSHIFT_CONTEXT` unless there is explicit context evidence.

This bias is intentional. A false event redshift can be reviewed and corrected. A false context redshift can hide the main scientific value of the Circular.

## Anti-Band-Z Gate

The letter `z` is also a photometric band. The extractor rejects candidates that look like band or magnitude statements:

```text
z = 21.3 mag
in the g, r, i, z bands
z-band limit of 22.0
```

It also rejects implausible redshift values outside `[0, 12]` and table-like rows using the same table-row idea as `EventIdentityExtractor`.

## Attribution

Attribution is decided after candidate finding and de-overlap.

```text
redshift candidate
    |
    v
explicit EVENT anchor?
    |
    | yes
    v
REDSHIFT_EVENT

otherwise:
    |
    v
direct context signal?
    |
    | yes
    v
REDSHIFT_CONTEXT + needs_review=True

otherwise:
    |
    v
REDSHIFT_EVENT + needs_review=True
```

Explicit event anchors include phrases such as `redshift of the burst`, `redshift for this event`, `this is the redshift`, `we suggest to be the redshift`, `at the redshift of`, `host galaxy`, and `host environment`. These anchors win over nearby context words.

Context signals must be direct to the redshift value. `intervening` or `foreground` elsewhere in the paragraph is not enough. This matters in spectroscopy Circulars where the burst redshift and several intervening systems are reported together.

## Burst Versus Intervening Systems

A real spectroscopy pattern looks like this:

```text
we infer a common redshift of z = 5.178.
We conclude this is the redshift of the burst.
```

That is `REDSHIFT_EVENT`, `target="event"`, and `needs_review=False`.

Another pattern reports both event and context values:

```text
common redshift of 2.006 ... which we suggest to be the redshift of GRB 260511B.
Multiple intervening systems ... including a strong system at z = 1.437
```

The `2.006` value is `REDSHIFT_EVENT`. The `1.437` value is `REDSHIFT_CONTEXT`, and it carries `needs_review=True` because every context redshift must be checked.

The same rule applies to Circulars with a burst redshift such as `z = 2.674` plus intervening systems at `z = 2.000` and `z = 1.824`: each value is classified by its local attribution.

## Needs Review Policy

All `REDSHIFT_CONTEXT` annotations have `needs_review=True` with the comment:

```text
Clasificado como redshift de contexto/intervening; verificar que no sea el redshift del evento.
```

Ambiguous `REDSHIFT_EVENT` annotations also have `needs_review=True`. In the current five-extractor `per_year=100` sweep, redshift produced 37 annotations and 12 review flags, a review rate of 32.43 percent. This review cost is accepted because the extractor is designed to avoid false context classifications.

## Known Limitations

Attribution remains hard. The extractor does not build a full discourse model, does not resolve every event alias, and does not decide all host-candidate cases. When the text says `If EP260321 is associated with this galaxy`, the value remains an event-side candidate with review rather than a confident event or context label.
