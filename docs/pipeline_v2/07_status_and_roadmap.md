# Status And Roadmap

For whom: architects and developers planning the next pipeline v2 work.

This document separates implemented, scale-tested components from future work. It should be updated whenever a new extractor is connected to the sweep, the INCEpTION layer changes, or human evaluation results become available.

## Current Health Snapshot

| Check | Current result |
|---|---|
| Full test suite | Dedicated tests cover all active extractors and shared pipeline components |
| Active extractors | 13 |
| Tagsets | Shared EVENT_EVIDENCE tagsets plus photometry measurement, time, reference, and system tagsets |
| INCEpTION layers | `webanno.custom.ASTRO_EVIDENCE` and `webanno.custom.PHOTOMETRIC_MEASUREMENT` |
| XMI round-trip | OK: text, spans, and features preserved |
| Event XMI | Both custom layers share one sofa and pass independent span/feature round-trip checks |
| Latest combined sweep | Regenerate a synchronized 13-extractor snapshot before using aggregate counts |
| Latest alert report | Regenerate from the same combined sweep before using aggregate review counts |

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
| `T90` / `DURATION_GENERAL` extractor | Implemented and scale-tested | 6 rules, `tests/test_duration.py`, focused sweep diagnostics |
| `HIGH_ENERGY_PROPERTY` extractor | Implemented and scale-tested | 10 rules, `tests/test_high_energy.py`, focused sweep diagnostics |
| `NEGATIVE_STATEMENT` extractor | Implemented and scale-tested | 18 rules, `tests/test_negative_statement.py`, cross-layer photometry checks |
| `LIGHTCURVE_EVOLUTION` extractor | Implemented and scale-tested | 5 rules, `tests/test_lightcurve_evolution.py`, negative-statement handoff checks |
| `COUNTERPART_ASSOCIATION` extractor | Implemented and scale-tested | 8 rules, `tests/test_counterpart_association.py`, identity/negation boundary checks |
| `CLASSIFICATION_INTERPRETATION` extractor | Implemented and scale-tested | 10 rules, `tests/test_classification_interpretation.py`, light-curve boundary checks |
| `HOST_CONTEXT` extractor | Implemented and scale-tested | 5 rules, `tests/test_host_context.py`, redshift boundary checks |
| `SPECTROSCOPY` extractor | Implemented and scale-tested | 3 rules, `tests/test_spectroscopy.py`, optical/high-energy boundary checks |
| XMI export to INCEpTION | Implemented | `tests/test_xmi_roundtrip.py` |
| XMI round-trip check | Implemented | `scripts/xmi_roundtrip_demo.py` reports `OK final` |
| Event grouping | Implemented | `tests/test_event_grouping.py`; confirmed subject identity takes precedence over body references |
| `EventCanonicalDocument` | Implemented | `tests/test_event_document.py`; local canonical text and SHA-256 survive inside global event text |
| Event annotation offset translation | Implemented | `tests/test_event_annotations.py`; local spans map to verified global spans with `source_circular_id` |
| `PhotometricMeasurementAnnotation` model and tagsets | Implemented | `tests/test_photometry_annotations.py` |
| Table photometry extraction | Implemented | `tests/test_photometry_tables.py`, `tests/test_photometry_rows.py` |
| Prose photometry extraction | Implemented | `tests/test_photometry_prose.py` |
| Photometry XMI export and round-trip | Implemented | `tests/test_photometry_xmi.py` |
| Event-level XMI deliverable | Implemented | `scripts/event_build.py --source-id <id>`; automatic selection and both custom layers are checked during the build |

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
| Automatic event selection | Builds `event_search_terms`, a deduplicated registry, and a reusable identity index; `select_event_candidates()` applies the verified membership hierarchy without a Circular-ID range. |
| Selection audit | Every event build records included Circulars, subject conflicts, body-only matches, and far-in-time matches before XMI export. |
| Photometry audit report | Audits table and prose extraction by source, format, rule, field, review reason, year, overlap, and uncovered format. |
| Review and scientific-context comments | Qualitative comments are review-only; duration and high-energy comments preserve governing instrument and energy-band context. |

## Extractor Roadmap

| Label | Status | Notes |
|---|---|---|
| `EVENT_IDENTITY` | Implemented | Header-aware identity extraction plus EP-WXT, day-fraction, and table-row handling. |
| `TRIGGER_TIME` | Implemented | Trigger-context gated, observation-time exclusions, adjacent-date normalization. |
| `LOCALIZATION` | Implemented | Decimal/sexagesimal RA-Dec and uncertainty spans. |
| `TRIGGER_INSTRUMENT` | Implemented | Trigger/detection verb gating and follow-up/reference exclusions. |
| `REDSHIFT_EVENT` | Implemented | Event redshift attribution with review on ambiguity. |
| `REDSHIFT_CONTEXT` | Implemented | Explicit context/intervening redshifts, always reviewed. |
| `T90` | Implemented | Explicit and nearby T90 attribution, error normalization, units, instrument, and energy band. |
| `DURATION_GENERAL` | Implemented | Event-duration language outside T90, including T50 with an explicit comment marker. |
| `SPECTROSCOPY` | Implemented | Optical/NIR observations, spectra, lines, features, and high-energy spectrum exclusions. |
| `HIGH_ENERGY_PROPERTY` | Implemented | Fluence, peak flux, spectral parameters, peak energy, cutoff energy, and Eiso. |
| `HOST_CONTEXT` | Implemented | Host, candidate host, offset, ambiguity, and nearby-galaxy context. |
| `CLASSIFICATION_INTERPRETATION` | Implemented | GRB classes, transient classes, physical mechanisms, and interpretation language. |
| `NEGATIVE_STATEMENT` | Implemented | Scientific rejections and negative findings with photometry and light-curve deferrals. |
| `LIGHTCURVE_EVOLUTION` | Implemented | Observed fading, rising, plateaus, variability, and confirmed absence of evolution. |
| `COUNTERPART_ASSOCIATION` | Implemented | Candidate and confirmed event-to-counterpart role statements. |

## Larger Missing Pieces

The `PHOTOMETRIC_MEASUREMENT` layer is implemented for magnitude-based optical, NIR, and UV measurements in tables and prose. X-ray count rates and radio flux densities remain outside its schema. High-energy properties and optical/NIR spectroscopy are represented as `EVENT_EVIDENCE`, not as photometric measurements.

Event document aggregation is implemented: related Circulars can be grouped into one immutable `EventCanonicalDocument`, and their annotations can be exported with global offsets. Scientific aggregation into `EVENT_SUMMARY` is still future work; the current flow deliberately preserves repeated and conflicting Circular evidence instead of resolving it automatically.

Event aliases are loaded automatically from `event_search_terms` through the deduplicated event registry. Circular membership is selected over the reusable identity index with no manual Circular-ID range or event-specific date window.

The pipeline still needs quantitative evaluation against human annotations. Round-trip success proves that offsets and features survive export; it does not prove scientific correctness.

## Recommended Next Step

For event-level work, the next architectural step is a separately designed automatic `EVENT_SUMMARY` model; annotators currently fill that document metadata layer in INCEpTION. For extraction work, the next step is quantitative evaluation against human annotations. Photometry maintenance and extension points are documented in [12_photometry.md](./12_photometry.md).

See [10_event_flow.md](./10_event_flow.md) for the implemented architecture, [13_event_selection.md](./13_event_selection.md) for automatic membership, and [11_reproduce_event_xmi.md](./11_reproduce_event_xmi.md) for the reproduction procedure.
