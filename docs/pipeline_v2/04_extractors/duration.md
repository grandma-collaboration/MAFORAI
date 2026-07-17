# Duration Extractor

For whom: developers maintaining event-duration extraction and annotators reviewing `T90`, `T50`, and general burst-duration preannotations.

`DurationExtractor` emits `T90` for values explicitly or locally attributed to T90 and `DURATION_GENERAL` for other measured event durations, including T50. It keeps timing measurements separate from exposure lengths, observation windows, and times relative to the trigger.

## Output

| Field | T90 | General duration |
|---|---|---|
| `label` | `T90` | `DURATION_GENERAL` |
| `target` | `event` | `event` |
| `certainty` | `confirmed` or `tentative` | `confirmed` or `tentative` |
| `method` | `regex` | `regex` |
| `extractor_id` | `duration-v1` | `duration-v1` |
| `extractor_version` | `0.1` | `0.1` |

The normalized numeric expression, including any error and approximation marker, is stored in `value`. The source unit is stored in `unit`; a missing unit produces an empty unit, `needs_review=True`, and a review comment. The exact matched substring remains in `text`.

## Rules

| Rule ID | What it captures | Example |
|---|---|---|
| `duration.t90_explicit` | an explicit `T90` or `duration (T90)` expression | `a T90 of 65.0 +/-8.0 s` |
| `duration.t50_explicit` | an explicit standalone `T50` duration | `T50=0.6 s` |
| `duration.t90_nearby` | a general duration whose nearest `T90` token is in the same sentence and within 60 characters | `duration (T90)\nof about 24.8 s` |
| `duration.duration_general` | event, burst, pulse, emission, or episode duration language without local T90 attribution | `a single-peak structure with a duration of about 30 sec` |
| `duration.t90_t50_pair_t90` | the first value in a paired `T90 and T50` statement | `0.28 +/- 0.03 sec` |
| `duration.t90_t50_pair_t50` | the second value in a paired `T90 and T50` statement | `0.23 +/- 0.04 sec` |

## T90 Boundary

Explicit `T90` syntax wins. General duration patterns become `T90` only when `T90` is in the same sentence and close to the measured value. Otherwise they remain `DURATION_GENERAL`.

`T50` is never emitted as `T90`. A paired statement is split into two non-overlapping value spans:

```text
The T90 and T50 durations ... are 0.28 +/- 0.03 sec and 0.23 +/- 0.04 sec
                                      | T90 |             | DURATION_GENERAL |
```

The T50 annotation keeps the semantic marker in `comment` as `T50`, followed by any instrument and energy band.

## Certainty And Normalization

Values containing `about`, `approximately`, `around`, `at least`, `estimated`, `preliminary`, or `~` are `tentative`. Other accepted values are `confirmed`.

The normalizer renders `+/-`, the Unicode plus-minus sign, and `+-` variants consistently as `+/-`. It preserves asymmetric errors such as `+0.4/-0.4` and parenthesized errors such as `81 (+12, -27)`.

## Scientific Context Comment

Duration comments are scientific context rather than review instructions. The shared format is:

```text
<instrument>, <energy band>
```

Either component may stand alone. The reporting instrument is the default; a different instrument overrides it only when it governs the value in the same clause. This prevents a neighboring episode instrument from being attached to the wrong duration.

Examples include `Fermi/GBM, 50-300 keV`, `Konus-Wind`, and `T50, SGM`.

## Non-Duration Gates

The extractor rejects exposure and integration lengths, repeated-exposure forms such as `4x90s`, observation or image windows such as `observations lasted 2 hours`, and relative times such as `130.9 seconds after the BAT trigger`.

Adjectival class descriptions such as `long-duration GRB` and `short-duration burst` are not measurements and are left to `CLASSIFICATION_INTERPRETATION`.

## De-Overlap

Paired T90/T50 parsing has highest priority, followed by explicit T90/T50 rules and then general duration rules. Overlapping lower-priority candidates are discarded, and accepted annotations are returned in source order.

## Known Limitations

The extractor does not convert duration units to seconds, infer omitted units, or resolve complex prose that pairs several episodes and durations indirectly. Instrument attribution depends on the known instrument vocabulary and explicit reporting or same-clause measurement language.
