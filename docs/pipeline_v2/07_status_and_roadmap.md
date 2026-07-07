# Status And Roadmap

For whom: architects and developers planning the next pipeline v2 work.

This document separates implemented, scale-tested components from future work. It should be updated whenever a new extractor is connected to the sweep, the INCEpTION layer changes, or human evaluation results become available.

## Current Health Snapshot

| Check | Current result |
|---|---|
| Full test suite | 266 tests passing across 21 test files |
| Active extractors | 5 |
| Tagsets | 17 labels, 6 targets, 5 certainties |
| INCEpTION layer | `webanno.custom.ASTRO_EVIDENCE` |
| XMI round-trip | OK: text, spans, and features preserved |
| Latest all-extractor sweep | `per_year=100`, 400 Circulars, 1478 annotations, 0 errors |
| Latest alert report | synchronized, 219 review alerts |

## Implemented And Tested

| Component | Status | Verification |
|---|---|---|
| Canonical text rendering | Implemented | `tests/test_canonical_document.py` |
| `EventEvidenceAnnotation` model | Implemented | extractor tests plus tagset validation tests |
| Tagsets for `label`, `target`, `certainty` | Implemented | `tests/test_event_identity.py`, `tests/test_sweep.py` |
| `EVENT_IDENTITY` extractor | Implemented and scale-tested | 11 rules, `tests/test_event_identity.py`, sweep coverage 97.25 percent |
| `TRIGGER_TIME` extractor | Implemented and scale-tested | 6 rules, `tests/test_trigger_time.py`, sweep coverage 35.75 percent |
| `LOCALIZATION` extractor | Implemented and scale-tested | 3 rules, `tests/test_localization.py`, sweep coverage 23.75 percent |
| `TRIGGER_INSTRUMENT` extractor | Implemented and scale-tested | 16 instrument rules, `tests/test_trigger_instrument.py`, sweep coverage 50.25 percent |
| `REDSHIFT_EVENT` / `REDSHIFT_CONTEXT` extractor | Implemented and scale-tested | 4 rules, `tests/test_redshift.py`, sweep coverage 6.50 percent |
| XMI export to INCEpTION | Implemented | `tests/test_xmi_roundtrip.py` |
| XMI round-trip check | Implemented | `scripts/xmi_roundtrip_demo.py` reports `OK final` |

## Implemented Infrastructure

| Feature | Why it matters |
|---|---|
| Central extractor registry | New extractors are connected to the sweep in one place: `get_active_extractors()`. |
| `only=` extractor filter | Allows focused sweeps such as `only=redshift` while hardening one extractor. |
| `per_year=N` stratified sampling | Avoids early-year bias and reveals year-specific style changes. |
| Run metadata and `run_id` | Prevents reading stale alert reports after a new sweep. |
| Alert context windows | Suspicious spans carry enough context for diagnosis. |
| Identity gaps | Missing identities are visible even though they produce no annotation alerts. |
| Table-row detection | Avoids treating catalog rows as Circular-level event identity or redshift evidence. |

## Extractor Roadmap

| Label | Status | Notes |
|---|---|---|
| `EVENT_IDENTITY` | Implemented | Header-aware identity extraction plus EP-WXT, day-fraction, and table-row handling. |
| `TRIGGER_TIME` | Implemented | Trigger-context gated, observation-time exclusions, adjacent-date normalization. |
| `LOCALIZATION` | Implemented | Decimal/sexagesimal RA-Dec and uncertainty spans. |
| `TRIGGER_INSTRUMENT` | Implemented | Trigger/detection verb gating and follow-up/reference exclusions. |
| `REDSHIFT_EVENT` | Implemented | Event redshift attribution with review on ambiguity. |
| `REDSHIFT_CONTEXT` | Implemented | Explicit context/intervening redshifts, always reviewed. |
| `T90` | Pending | Numeric duration with unit normalization. |
| `DURATION_GENERAL` | Pending | Broader duration language beyond T90. |
| `SPECTROSCOPY` | Pending | Spectrum observations, absorption/emission systems, instruments, and interpretation. |
| `HIGH_ENERGY_PROPERTY` | Pending | Needs scoped definitions before regex work. |
| `HOST_CONTEXT` | Pending | Must distinguish host, candidate host, nearby galaxy, and field galaxy. |
| `CLASSIFICATION_INTERPRETATION` | Pending | GRB class and transient interpretation with uncertainty. |
| `FOLLOWUP_ACTION` | Pending | Observation actions, planned observations, and recommendations. |
| `NEGATIVE_STATEMENT` | Pending | Non-detections and explicit absence statements. |
| `LIGHTCURVE_EVOLUTION` | Pending | Fading, rising, plateau, and temporal-evolution language. |
| `COUNTERPART_ASSOCIATION` | Pending | Association claims between event and counterpart. |
| `PHOTOMETRY_TABLE` | Pending | Likely needs table-aware extraction rather than line regex only. |

## Larger Missing Pieces

The `PHOTOMETRIC_MEASUREMENT` layer is not implemented in v2. It will need its own model because individual measurements carry magnitude or flux, unit, filter, time, limit/detection status, and table context.

Event aggregation is also future work. Pipeline v2 currently focuses on Circular-level span evidence. Aggregating multiple Circular annotations into an `EVENT_SUMMARY` should happen after span-level annotation quality is measured against human review.

The pipeline still needs quantitative evaluation against human annotations. Round-trip success proves that offsets and features survive export; it does not prove scientific correctness.

## Recommended Next Step

Build the next extractor only after choosing the scientific priority. `T90` is narrow and testable, while `SPECTROSCOPY` and `PHOTOMETRY_TABLE` are higher complexity and should follow the method in [09_method_and_lessons.md](./09_method_and_lessons.md).
