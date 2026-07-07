# Trigger Time Extractor

For whom: developers maintaining trigger-time extraction and annotators reviewing time preannotations.

`TriggerTimeExtractor` finds time expressions that are likely to be the event trigger time, not an observation start or publication time. Its behavior is intentionally conservative: a time needs trigger context, observation-time gates run first, and clock-only trigger times are marked for review because the date is incomplete.

## Output

| Field | Value |
|---|---|
| `label` | `TRIGGER_TIME` |
| `target` | `event` |
| `certainty` | `confirmed` |
| `method` | `regex` |
| `extractor_id` | `trigger-time-v1` |
| `extractor_version` | `0.1` |

## Patterns

| Rule ID | What it captures | Example |
|---|---|---|
| `trigger_time.t0_explicit` | `T0 =` followed by an ISO-like date and time | `T0 = 2023-05-10T14:22:00` |
| `trigger_time.iso` | ISO-like date and time | `2023-01-01T02:16:38 UTC` |
| `trigger_time.date_before_clock` | Date before clock time | `on 2023-01-16 at 21:04:43 UT` |
| `trigger_time.clock_on_date` | Clock time followed by a date | `02:16:38 UT on 1 Jan 2023` |
| `trigger_time.clock` | Clock time without adjacent date | `21:04:43 UT` |
| `trigger_time.mjd` | Modified Julian Date | `MJD 60010.655` |

## Order Of Decisions

```text
candidate time
    |
    v
exclude header DATE line
    |
    v
negative observation gates
    |
    v
positive trigger-context gate
    |
    v
adjacent date lookup and ISO normalization
    |
    v
verified TRIGGER_TIME annotation
```

The negative gates have priority. The extractor rejects coordinate-like clocks, observation starts, scan times with `(t0+...)`, and phrases like `72 sec after trigger time at 2023-01-01 02:17:51 UT`. A date next to a time does not rescue it if the sentence says it is an observation epoch.

## Date Capture

The extractor combines date and clock only when the date is textually adjacent to the time. Wrapping newlines are allowed inside the same sentence:

```text
T0 = 2023-01-04
06:03:15.00 +/- 0.01 s (UTC)
```

The span may include the newline, and `verify()` still requires the annotation text to equal `rendered_text[start:end]`. The normalized value becomes:

```text
2023-01-04T06:03:15.00
```

The extractor does not combine across a sentence boundary or a blank line. It also does not infer dates from the event name or from the header.

## Clock-Only Review

Swift reports often say:

```text
At 21:04:43 UT, the Swift Burst Alert Telescope (BAT) triggered and located GRB 230116D
```

The extractor emits the clock span as `TRIGGER_TIME`, but `value` remains `21:04:43 UT` and `needs_review=True`. The date is not adjacent in the evidence text, so the annotator must complete it.

## Multiple Times

If more than one accepted trigger time appears in the same Circular, all accepted times are marked `needs_review=True`. This covers legitimate multi-instrument cases such as Swift-BAT and Fermi-GBM trigger times in the same sentence.

## Real Example: Circular 33130

The body contains:

```text
At 02:16:38 UT on 1 Jan 2023, the Fermi Gamma-ray Burst Monitor (GBM) triggered and located GRB 230101A
```

The extractor emits:

```text
text  = 02:16:38 UT on 1 Jan 2023
value = 2023-01-01T02:16:38
```

## Known Limitations

Mission elapsed time systems are not fully interpreted. Konus-style seconds-of-day plus a parenthesized clock can still produce a clock-only annotation with review. The extractor treats these as useful evidence, not as complete timestamps.
