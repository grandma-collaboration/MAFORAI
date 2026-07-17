# Photometric Measurement Layer

For whom: developers maintaining or extending optical photometry extraction, validation, reporting, and INCEpTION export in pipeline v2.

## 1. Purpose And Scope

`PHOTOMETRIC_MEASUREMENT` represents one offset-anchored photometric measurement. A table row may emit one measurement, or more than one when the row contains both a detection and a separate upper limit. A prose expression emits one measurement per magnitude or limit value. In every case, `annotation.text == rendered_text[span_start:span_end]` must hold.

The INCEpTION type is `webanno.custom.PHOTOMETRIC_MEASUREMENT`. Version 1 is intentionally centered on optical, near-infrared, and ultraviolet magnitudes, filters, observation epochs, exposures, and instruments. X-ray count rates, radio flux densities in Jy-derived units, high-energy fluence, and spectroscopy are outside this layer: they use different physical quantities, units, uncertainty conventions, and scientific semantics, so forcing them into a magnitude-and-band schema would make the data ambiguous.

```text
CanonicalDocument
    +---------------- table path ----------------+---------------- prose path ----------------+
    | detect blocks -> infer roles -> parse rows | optical gate -> find magnitude -> companions |
    +--------------------------+-----------------+----------------------+-----------------------+
                               v                                        v
                               PhotometricMeasurementAnnotation
                                                |
                                                v
                              PHOTOMETRIC_MEASUREMENT CAS annotations
```

## 2. Modules

| Module | Responsibility |
|---|---|
| `extraction_v2/photometry_tagsets.py` | Central values for `measurement_type`, `obs_time_type`, `obs_time_reference`, and `photometric_system`; it reuses `TARGETS` and `CERTAINTIES` from `tagsets.py`. These values must agree with the INCEpTION project tagsets. |
| `extraction_v2/photometry_annotations.py` | Frozen Pydantic model `PhotometricMeasurementAnnotation`, span invariants, validators for measurement type, target, certainty, observation-time type/reference, the upper-limit-only constraint for `limit_sigma`, and `verify()`. `photometric_system` is normalized by producers/export but is not currently field-validated by this model. |
| `extraction_v2/photometry_tables.py` | Detects `TableBlock` objects, preserves block offsets and raw lines, recovers headers and surrounding context, splits rows, and infers `ColumnRole` values with confidence and optional time subtype. The detected blocks feed row-level `PHOTOMETRIC_MEASUREMENT` parsing. |
| `extraction_v2/photometry_rows.py` | Validates that a block is photometric and converts its `data_rows` into measurements. It parses magnitude, error, limit confidence, time, exposure, filter, instrument, and system. |
| `extraction_v2/photometry_prose.py` | `ProsePhotometryExtractor`: optical pre-filter, magnitude candidates, negative gates, companion-field search, review decisions, and offset verification. |
| `extraction_v2/event_photometry.py` | Runs both photometry paths per Circular, translates local spans into event-global spans, and retains `source_circular_id` as internal provenance. |
| `inception_v2/photometry_xmi_export.py` | Standalone CAS export, feature mapping, valid defaults for tagset-backed features, and photometry round-trip validation. |
| `inception_v2/event_xmi_export.py` | Writes `ASTRO_EVIDENCE` and `PHOTOMETRIC_MEASUREMENT` into the same event CAS and verifies each layer independently. |
| `scripts/photometry_report.py` | Corpus audit with `limit=N`, `per_year=N`, and optional `keywords=` sampling; writes the complete JSON report and a readable summary. |

## 3. The Table Pipeline

```text
detect_table_blocks(text)
        -> recover header and context
        -> infer_column_roles(block)
        -> is_photometry_table(block)
        -> parse_table_to_measurements(block, doc)
        -> PhotometricMeasurementAnnotation[]
```

### Block detection and headers

`detect_table_blocks()` recognizes three `delimiter_type` families. `pipe` blocks contain repeated pipe-delimited rows; `bordered` blocks use ASCII borders such as `+---+` around pipe rows; `whitespace` blocks use repeated columns separated by aligned whitespace. `_run_blocks()` groups contiguous compatible lines and permits a single blank line when the following line continues the same structure. Compact whitespace layouts whose cells are separated by single spaces use the structured path in `_structured_whitespace_ranges()` and `_split_structured_whitespace_data_row()`.

Header recovery is part of block construction, not row parsing. `_expand_range_with_header()` looks above a data run across blank or separator lines, while `_detect_header()` accepts a line whose cells map to known roles. Supported structured layouts may have a second header line containing only aligned units or confidence markers, for example `(mid,d)`, `(n*s)`, and `(3-sigma)`; `_combine_header_continuation()` attaches those fragments to their semantic columns. Separator, unit, repeated-header, URL-like, prose-like, and empty blocks are removed before `data_rows` is exposed. `context_before` stores nearby non-empty lines above the header, and `context_after` stores nearby lines below the block without changing its span.

### Column roles

`infer_column_roles()` applies two levels. First, `_role_from_header()` maps header vocabulary to `time`, `exposure`, `filter`, `magnitude`, `mag_error`, `instrument`, `coordinate`, `name`, `observer`, `comment`, or `unknown`. Time headers also carry a tentative subtype such as `mjd`, `jd`, `utc_datetime`, or `relative_to_trigger`. Metadata roles exist so row parsing can deliberately ignore coordinates, object names, observers, and comments rather than misusing them as measurements.

When a header is absent or inconclusive, `_role_from_content()` evaluates cell signatures in a deliberate order: exposure and coordinate patterns, known filters, absolute time formats, MJD/JD ranges, optical magnitudes, relative times, instruments, and names. A plain value in the optical range is considered magnitude-like before it is considered a generic relative time. `_refine_magnitude_error_roles()` then distinguishes adjacent error columns: a pure error header such as `err` or `mag_err` must contain consistently small values, while headers containing `mag`, `magnitude`, `limit`, `UL`, or `upper` remain magnitude columns even if they mention sigma or error. This prevents confidence notation from turning a limit column into an uncertainty column.

### Photometry validation and row parsing

Generic numeric tables are intentionally detected more broadly than photometry. `is_photometry_table()` requires a magnitude role plus at least one of a filter role, a photometry-specific header, or explicit photometry context. `parse_table_to_measurements()` repeats the minimum-signal check per row and rejects rows without a usable magnitude. A table with transient-name and coordinate columns across multiple rows is treated as a multi-object catalog; its measurements are retained but marked for review because event association is not guaranteed.

`_parse_magnitude_cell_details()` determines detection versus upper limit from the cell marker first and the magnitude-column header second. It removes an inline or parenthetical uncertainty into `magnitude_error`, removes a parenthetical confidence marker into `limit_sigma`, and keeps the principal magnitude separate. A distinct `mag_error` column is attached only to detections. If one row has both a `Mag` column and an `Upper limit` column, each non-empty cell emits a separate annotation with shared time, band, exposure, and instrument metadata.

Time cells retain their source text. `_combine_date_and_clock_candidates()` joins a date-only column and a clock-only column into one `utc_datetime`; `_select_primary_time()` prefers MJD, then UTC datetime, calendar date, JD, and relative-to-trigger time. Secondary epochs remain in `provenance_inherited`. Instrument values pass `_is_valid_instrument_value()` so numeric cells, dimensions, signal-to-noise remarks, and common lowercase words are not exported as telescope names.

## 4. The Prose Pipeline

`is_optical_circular()` is a precision pre-filter. It requires optical vocabulary, a known optical/NIR/UV band used in a photometric construction, or an optical telescope. High-energy, radio, and neutrino language does not pass on its own. This prevents scalar quantities such as count rates, fluences, and flux densities from reaching magnitude regexes.

Prose uses the magnitude expression as the anchor because its companion fields may be elsewhere in the Circular. `find_prose_magnitudes()` finds candidates; `find_companion_fields()` then searches for the nearest band, system, observation time, exposure, and instrument. Observation-time selection prefers the same sentence, then the same paragraph, then explicit observation context, while trigger epochs are excluded. Multiple equally plausible times or exposures become review reasons instead of silent guesses.

Supported rule families are defined in `_PATTERNS` plus `_ENUMERATED_LIMIT_RE`: `prose_band_eq` (`R = 21.86 +/- 0.06`), `prose_brightness` (`brightness of R = 21.86`), `prose_limit_gt` (`L > 19.65 mag`), `prose_limit_upto` (`upper limit of 21 mag`), `prose_magnitude_of` (`magnitude of 19.2 in r'`), `prose_sigma_depth` (`down to a 5-sigma depth of >20.8 AB mag`), and enumerated limits (`>20.20 and >20.35 AB mag`). Overlapping candidates are resolved longest-first.

Negative gates run before annotation construction. Catalog completeness statements are not object measurements; calibration-star and catalog language must not create measurements; extinction quantities and non-photometric units are rejected locally; average search depth without an object limit is rejected; direct citations remain measurements but request ownership review. The `z` token is treated as redshift when its value and context are redshift-like and no magnitude unit establishes z-band photometry. Any prose value outside the optical magnitude range is discarded because it is much more likely to be a color, redshift, coordinate, or unrelated scalar; table values are retained with review because table structure provides stronger evidence that a malformed cell was intended as photometry.

## 5. Field Semantics And Design Decisions

| Field or policy | Semantics and rationale |
|---|---|
| `magnitude_or_limit` | Principal magnitude or limiting magnitude only. It must not contain the uncertainty or sigma confidence. |
| `magnitude_error` | Uncertainty attached to the principal value, whether inline or in a separate error column. Detections normally carry it. If a source explicitly labels a parenthetical uncertainty on an upper limit, the parser preserves that value rather than treating it as sigma. |
| `limit_sigma` | Confidence level of an upper limit, taken in priority order from the limit cell, its header, then table/prose context. The model rejects it on non-upper-limit annotations. Absence is allowed because many sources do not state a confidence level. Error and sigma are never inferred from the same token: a standard detection has error and no sigma, while a standard upper limit has sigma and no error. |
| `photometric_system` | Table priority is the measurement cell, then its column header, then unambiguous table context. A single system attached to another magnitude cell in the same row may be shared with the row's limit. Mixed `AB`/`Vega` context is not inherited because a table may select the system per filter. Explicit cell evidence therefore always wins. |
| Clear/unfiltered bands | Values in `CLEAR_UNFILTERED_BANDS` may legitimately have `photometric_system="unknown"`. That absence does not request review because a standard AB/Vega system may not exist in the source. |
| Raw temporal fields | `obs_time_raw` and `exposure_time_raw` preserve source strings; `obs_time_type` and `obs_time_reference` are interpretations. `timezone_raw` exists in the INCEpTION TypeSystem and export feature list, but the current Pydantic model does not yet populate it; adding that model field is required before extractors can preserve an explicit timezone separately. |
| `provenance_inherited` | Internal audit trail for context-derived system, secondary time columns, and combined date/time columns. It is not an INCEpTION feature. |
| `comment` | Review instruction only. Producers populate it when `needs_review=True`, and the exporter suppresses it otherwise; provenance and general notes do not belong here. |
| Offset anchoring | Table annotations span the complete raw data line; prose annotations span the matched magnitude expression. Every producer calls `verify()` before returning. |

The configured values are `detection`, `upper_limit`, `non_detection`, and `unclear` for measurement type; `utc_datetime`, `mjd`, `jd`, `relative_to_trigger`, `start_time_plus_exposure`, `other_timezone`, `calendar_date`, and `unclear` for time type; `absolute_time`, `trigger_time_t0`, `observation_start`, `observation_mid`, and `unknown` for time reference; and `AB`, `Vega`, and `unknown` for system. Targets and certainties come from the shared EVENT_EVIDENCE tagsets.

The exporter writes only features present in the loaded TypeSystem. Missing free-text features become empty strings. Missing tagset-backed features receive valid defaults through `PHOTOMETRY_TAGSET_DEFAULTS`: `unclear` for measurement/time type and certainty, and `unknown` for target, system, and time reference. `photometry_roundtrip_check()` compares sofa text, span multiplicities, span text, and all exported feature signatures.

## 6. How To Add A New Table Format

1. **Classify the delimiter.** Start with `detect_table_blocks()` and `split_row()` in `photometry_tables.py`. Extend `_is_pipe_line()`, `_bordered_ranges()`, or `_is_whitespace_table_line()` for an existing family. A compact single-space layout with strong semantics belongs in `_structured_whitespace_ranges()`, `_known_whitespace_header_cells()`, and `_split_structured_whitespace_data_row()`. Add a new `delimiter_type` only if none of the three existing row models can represent the source.
2. **Teach header vocabulary.** Extend `_role_from_header()` for a new synonym. Magnitude and pure-error distinctions belong in `_header_is_magnitude_like()` and `_header_is_pure_error()`. Limit-specific wording used during row parsing belongs in `_LIMIT_HEADER_RE` and `_header_indicates_limit()` in `photometry_rows.py`. Keep flux/count headers explicitly non-photometric.
3. **Teach content signatures.** Extend `_role_from_content()` and the relevant `_looks_like_*()` helper when the header cannot identify a column. Preserve signature priority so exposure, coordinates, absolute time, magnitude, and relative time remain distinguishable.
4. **Teach cell parsing.** Embedded units or notation changes belong in `_parse_magnitude_cell_details()`, `_parse_time_cell_details()`, or `parse_exposure_cell()`. Keep principal magnitude, uncertainty, limit confidence, and system separate. If row tokenization is the problem, fix `split_row()` or the structured-row splitter rather than compensating in the annotation constructor.
5. **Add filters centrally.** Add new passbands to `FILTER_VALUES` in `photometry_tables.py`. Add a genuinely clear/unfiltered convention to `CLEAR_UNFILTERED_BANDS` in `photometry_rows.py` only when an unknown AB/Vega system is expected by design.
6. **Add regression coverage.** Put block/header/role tests in `tests/test_photometry_tables.py` and emitted-field/span tests in `tests/test_photometry_rows.py`. Use the smallest complete header plus representative raw row, and assert `verify()`.
7. **Audit corpus behavior.** Run `scripts/photometry_report.py` with stratified sampling and inspect `data/interim/gcn/photometry/photometry_report.json`. Check source rows, context, zero-measurement blocks, possible problems, review reasons, and year/source-family changes; passing a unit test is necessary but not sufficient.

To add prose support, add a narrowly scoped `_Pattern` to `_PATTERNS` or a dedicated enumerated parser in `photometry_prose.py`, apply `_should_discard_candidate()` and range/redshift safeguards, add cases to `tests/test_photometry_prose.py`, and audit `prose_samples` grouped by `rule_id` in the report JSON. Do not broaden the optical pre-filter merely to make one regex reachable.

To add a field, update `PhotometricMeasurementAnnotation`, the real INCEpTION TypeSystem, `PHOTOMETRY_FEATURES` and (for a tagset field) `PHOTOMETRY_TAGSET_DEFAULTS`, then extend standalone and combined XMI round-trip tests. Internal provenance fields should not be exported unless the INCEpTION layer explicitly defines them.

## 7. Known Limitations

- X-ray rates, radio flux densities, high-energy quantities, and spectroscopy require separate schemas and extractors.
- Measurements hosted only in external services cannot be offset-anchored when the Circular contains only a link.
- Positional prose such as “first and second exposures” paired with “X and Y, respectively” is extracted conservatively; ambiguous field-to-value association remains a human-review task.
- Multi-object catalog tables are retained with review rather than discarded, because a row may still be scientifically relevant but event association is not established by the table alone.
- When a Circular contains both table measurements and prose measurements, `photometry_report.py` marks the prose items as possible table summaries. They remain available because the prose statement may instead describe an independent measurement.
- The current model does not populate `timezone_raw`; timezone detail remains embedded in `obs_time_raw` until that field is added end to end.

## Report As A Maintenance Tool

`scripts/photometry_report.py` reports source (`table`/`prose`), table family, measurement type, limit sigma, system and system provenance, time type/reference, common bands, review reasons, optical pre-filter decisions, year breakdowns, table/prose overlap, detailed source-row samples, prose samples by rule, potentially uncovered formats, and automatically flagged problems. Its JSON includes every measurement, context excerpts, `verify()` results, source metadata, run metadata, and a deterministic `run_id`; maintainers should diagnose from the JSON rather than from aggregate totals alone.
