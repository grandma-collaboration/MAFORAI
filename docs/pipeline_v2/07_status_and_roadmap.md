# Status And Roadmap

For whom: architects and developers planning the next pipeline v2 work.

This document separates implemented, scale-tested components from future work. It should be updated whenever a new extractor is connected to the sweep, the INCEpTION layer changes, or human evaluation results become available.

## Current Health Snapshot

| Check | Current result |
|---|---|
| Full test suite | 282 tests passing across 24 test files |
| Active extractors | 5 |
| Tagsets | Shared EVENT_EVIDENCE tagsets plus photometry measurement, time, reference, and system tagsets |
| INCEpTION layers | `webanno.custom.ASTRO_EVIDENCE` and `webanno.custom.PHOTOMETRIC_MEASUREMENT` |
| XMI round-trip | OK: text, spans, and features preserved |
| Event XMI | Both custom layers share one sofa and pass independent span/feature round-trip checks |
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
| Event grouping | Implemented | `tests/test_event_grouping.py`; confirmed subject identity takes precedence over body references |
| `EventCanonicalDocument` | Implemented | `tests/test_event_document.py`; local canonical text and SHA-256 survive inside global event text |
| Event annotation offset translation | Implemented | `tests/test_event_annotations.py`; local spans map to verified global spans with `source_circular_id` |
| `PhotometricMeasurementAnnotation` model and tagsets | Implemented | `tests/test_photometry_annotations.py` |
| Table photometry extraction | Implemented | `tests/test_photometry_tables.py`, `tests/test_photometry_rows.py` |
| Prose photometry extraction | Implemented | `tests/test_photometry_prose.py` |
| Photometry XMI export and round-trip | Implemented | `tests/test_photometry_xmi.py` |
| Event-level XMI deliverable | Implemented | `scripts/event_xmi_export.py`; both custom layers are checked independently during round-trip |

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
| Event-to-document flow | Groups Circulars, builds immutable global text, translates both evidence and photometry offsets, and exports one event XMI. |
| Photometry audit report | Audits table and prose extraction by source, format, rule, field, review reason, year, overlap, and uncovered format. |
| Review-only comments | Keeps `comment` empty for confirmed annotations and reserves it for human review instructions. |

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
| `PHOTOMETRY_TABLE` | Implemented as table-detection evidence | The same detected blocks feed row-level `PHOTOMETRIC_MEASUREMENT` parsing. |

## Larger Missing Pieces

The `PHOTOMETRIC_MEASUREMENT` layer is implemented for magnitude-based optical, NIR, and UV measurements in tables and prose. X-ray count rates, radio flux densities, high-energy quantities, and spectroscopy remain outside its schema and need separately designed layers.

Event document aggregation is implemented: related Circulars can be grouped into one immutable `EventCanonicalDocument`, and their annotations can be exported with global offsets. Scientific aggregation into `EVENT_SUMMARY` is still future work; the current flow deliberately preserves repeated and conflicting Circular evidence instead of resolving it automatically.

Event aliases and candidate ranges are currently configured manually in the event scripts. Automatically loading aliases from the existing `event_search_terms` outputs is future work.

The pipeline still needs quantitative evaluation against human annotations. Round-trip success proves that offsets and features survive export; it does not prove scientific correctness.

## Recommended Next Step

For event-level work, the next architectural step is automatic alias integration from `event_search_terms`, followed by a separately designed `EVENT_SUMMARY` model. For extraction work, `T90` remains narrow and testable, while `SPECTROSCOPY` needs its own scope and schema. Photometry maintenance and extension points are documented in [12_photometry.md](./12_photometry.md).

See [10_event_flow.md](./10_event_flow.md) for the implemented architecture and [11_reproduce_event_xmi.md](./11_reproduce_event_xmi.md) for the reproduction procedure.
