# How We Build Extractors Well

For whom: anyone who will build, review, or maintain a pipeline v2 extractor.

This document describes the working method behind pipeline v2. The short version is that an extractor is not finished when it passes small examples; it is finished only after it survives scale, exposes its uncertainty honestly, and keeps every value tied to a verified span.

## 1. The Extractor Development Cycle

Build the extractor in isolation first. A new extractor starts with one module, one demo script, and synthetic pytest cases that cover the intended behavior and the first known traps.

```text
isolated extractor
    |
    v
demo + synthetic tests
    |
    v
connect to sweep
    |
    v
per_year=100 sweep
    |
    v
read alerts with context
    |
    v
fix with real regression tests
    |
    v
re-sweep
    |
    v
stress test at larger scale
```

The first sweep is not a pass/fail test. It is a discovery tool. It shows which rules fire too often, which subjects produce no annotations, and where the real corpus uses a style the tests did not cover.

Every fix should come with a regression test using the real pattern that exposed the problem. The test may be synthetic text, but it should preserve the important wording. For example, `LAT data` became a trigger-instrument regression because it was a repeated false positive for Fermi/LAT analysis text.

After the extractor is connected to `get_active_extractors()`, run:

```bash
.venv/bin/python scripts/sweep_report.py per_year=100 only=<extractor>
.venv/bin/python scripts/alerts_report.py
```

Before calling an extractor stable, run a larger stress pass. The redshift work showed why this matters: the expensive attribution bugs did not appear clearly in the small sample.

## 2. Design Principles We Learned

Every annotation must be anchored by offset and verified. A value without `span_start`, `span_end`, exact `text`, and `verify(rendered_text)` is not safe to export to INCEpTION.

Preserve the raw text and normalize separately. The raw evidence stays in `text`; the machine-readable form goes in `value`. `GRB230101.09` becomes value `GRB 230101.09`, but the raw span remains exactly what the Circular said.

When attribution is uncertain, keep the evidence and mark review. Do not discard useful evidence simply because the machine cannot finish the scientific interpretation. Body-only event identities, clock-only trigger times, and ambiguous redshifts are examples.

When one error direction is more expensive than the other, encode that asymmetry. For redshift, a false `REDSHIFT_CONTEXT` can hide the event redshift. Therefore every `REDSHIFT_CONTEXT` has `needs_review=True`, and ambiguous values default to `REDSHIFT_EVENT` with review.

Negative gates run before positive gates. If a sentence says a time is an observation start, trigger words nearby do not rescue it. If an instrument mention is a catalog or data reference, trigger language elsewhere nearby does not make it a trigger instrument.

Use a single source of truth. The project already hit this bug twice: ZTF and EP-WXT values were normalized correctly by the extractor but marked weird by a duplicated validation rule in the sweep. `is_canonical_identity()` now lets the detector use the extractor's canonical formats directly.

Keep fixes as narrow as the evidence allows. A systematic false positive deserves a gate; one strange example does not justify a broad rule that may suppress valid evidence elsewhere.

## 3. The Central Lesson From Redshift

Small samples can make an extractor look finished. Redshift looked safe after focused tests and smaller sweeps because it found values and avoided obvious z-band magnitudes.

The larger sweep exposed the expensive bug: some redshifts of the burst were classified as context when the same Circular also mentioned intervening systems. One real pattern was:

```text
we infer a common redshift of z = 5.178.
We conclude this is the redshift of the burst.
```

That must be `REDSHIFT_EVENT`, not context. Another pattern contained both an event redshift and intervening systems:

```text
common redshift of 2.006 ... redshift of GRB 260511B
intervening systems ... at z = 1.437
```

The fix was not to remove context detection. The fix was to classify each value by local evidence and give explicit event anchors priority over context words elsewhere nearby.

The lesson is simple: "it works on the small sample" is not the same as "it works." Any extractor that can make asymmetric scientific errors needs a stress sweep before it is considered done.

## 4. How To Diagnose A Sweep

Start with rule counts. A rule that dominates alerts is either a high-value review rule or a systematic problem. Do not assume which one until reading the context.

Read `context_window` and `source_line`. They show the exact evidence span in local text, with enough surrounding words to see whether the rule overreached.

Separate legitimate review from false positives. `GRB 230101.09` as a day-fraction identity is a legitimate review case. `Fermi-LAT catalog are located within the region` was a false trigger-instrument pattern.

Look for missing evidence as well as bad evidence. Gaps are crucial because a missed extractor produces no alert. The event-identity gap report revealed EP-WXT trigger identifiers and EP day-fraction formats.

Use year-stratified sweeps. Styles change over time as missions change. Einstein Probe and SVOM examples are much easier to find when the sample includes later years instead of only early 2023.

## 5. Refactor When Complexity Demands It

`TriggerTimeExtractor` is the example. It accumulated date capture, observation exclusions, coordinate exclusions, wrapping-newline handling, multi-time review logic, and ISO normalization. Several fixes worked locally but caused regressions because the logic was entangled.

The refactor split the extractor into pure helpers: candidate finding, observation context, trigger context, adjacent date lookup, ISO normalization, and overlap resolution. The public behavior did not change; the tests were the contract.

A behavior-preserving refactor needs two checks:

```text
all existing tests still pass
same sweep summary before and after
```

After that split, new fixes could target one function without accidentally changing another part of the extractor. That is the standard to follow for the next complex extractor.
