# Canonical Text

For whom: architects and developers who need to understand why offsets are stable.

Canonical text is the one string that every extractor reads and every annotation points into. It solves the offset problem by rendering a Circular once, normalizing it once, and never changing it after offsets can be computed.

## Why This Layer Exists

Extracting directly from raw `subject` and `body` is tempting, but unsafe. If one script normalizes line endings, another strips illegal XML characters, and a third concatenates fields differently, the same scientific value can have different character positions in each place. That breaks offsets.

Pipeline v2 fixes that by making all downstream extractors read `CanonicalDocument.rendered_text`.

## Rendered Structure

The renderer builds exactly this shape:

```text
SUBJECT: {subject}
DATE: {created_on or ''}
FROM: {submitter or ''}

{body}
```

Before rendering, the code normalizes line endings to `\n` and removes XML 1.0 illegal control characters while keeping tab and newline. That matters because INCEpTION import uses XML, and XML cannot safely carry every raw control byte that may appear in scraped text.

## The Golden Rule

After `rendered_text` is built, it is never modified.

The consequence is strict and useful: every `span_start` and `span_end` in later annotations refers to the exact same string. If the text changed after extraction, offsets would become untrustworthy even if the visible words looked similar.

## SHA-256 Fingerprint

`CanonicalDocument.text_sha256` is the SHA-256 hash of `rendered_text.encode("utf-8")`. It is a fingerprint of the exact text version used by the extractors. If two documents have different hashes, their offsets must not be mixed.

## Models

`Segment` describes a named slice of canonical text. The current segments are `header` and `body`; each stores `start`, `end`, and `text`, and validates that the text length matches the span.

`CanonicalDocument` stores the Circular identity, normalized subject/date, rendered text, text hash, and segments. It validates that each segment text is exactly equal to `rendered_text[start:end]`.

## Real Example

For Circular `33130`, the body contains:

```text
At 02:16:38 UT on 1 Jan 2023, the Fermi Gamma-ray Burst Monitor (GBM) triggered and located GRB 230101A
```

The trigger-time extractor does not annotate a copy of that sentence. It stores offsets into the canonical text and also stores the exact span text `02:16:38 UT on 1 Jan 2023` so the annotation can be verified later.

