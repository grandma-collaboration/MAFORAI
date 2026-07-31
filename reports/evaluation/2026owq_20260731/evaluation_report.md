# Reproducible XMI comparison: 2026owq

## 1. Inputs

| Role | Path | File SHA-256 | Text length | Text SHA-256 | Evidence | Photometry |
|---|---|---|---:|---|---:|---:|
| automatic | `data/inception/out/event_2026owq.xmi` | `0cf1a61da156175fce32bdf792c2a532d653a861c9dd389f346dae5c718031d3` | 54631 | `a51b058b1e19cdbaa71dd858451999825147b8f38ac9d36f6fe45e45e9c234d6` | 193 | 76 |
| expert | `data/interim/gcn/annotation_review/camille/Camille.xmi` | `9ba85b2f4fbaf7eb3beebafc9ec222ba4c1ed0337450596deef17b2d8eb9c2e7` | 54631 | `a51b058b1e19cdbaa71dd858451999825147b8f38ac9d36f6fe45e45e9c234d6` | 199 | 69 |

TypeSystem: `data/inception/TypeSystem.xml` (`06146ae3a7276213a9f9075a85e5a9a33b8cfcf71b10437fca3502419eeb975e`).

The canonical texts are byte-identical after UTF-8 decoding. The preserved automatic XMI has 193 evidence annotations and 76 photometric annotations; there is no surviving automatic XMI with the historical current-rule count 193/68.

TypeSystem compatibility augmentation applied in memory: `webanno.custom.EVENT_SUMMARY.corpus_value:uima.cas.String`. It affects EVENT_SUMMARY metadata only, not either evaluated layer.

Missing expert labels accepted explicitly: `EVENT_EVIDENCE:203:218:original_index=1`, `EVENT_EVIDENCE:5000:5017:original_index=22`, `PHOTOMETRIC_MEASUREMENT:11462:11480:original_index=12`. Strict mode rejects these annotations; this run preserves them as the visible sentinel `<unset>` because the historical report documents the same two evidence relabellings and one expert-only photometric annotation.

## 2. Matching Definitions

Matching is one-to-one and layer-local. Phases are exact span/same label, overlap/same label, then exact or strong overlap/different label. Candidate score: `0.60 * span_iou + 0.25 * covered_text_similarity + 0.15 * boundary_similarity`. The relabel IoU threshold is 0.50. Ties use automatic span, expert span, labels, then original indexes.

Categories: EXACT_MATCH, FEATURE_CHANGED, SPAN_ADJUSTED, RELABELED, AUTOMATIC_ONLY, EXPERT_ONLY, and HUMAN_REJECTION_MARKER_EXCLUDED.

## 3. Feature Normalization

- None, missing values, and empty strings normalize to an empty string.
- Leading, trailing, and repeated internal whitespace is collapsed.
- Booleans normalize to lowercase true/false.
- Pure numeric strings normalize through Decimal without changing magnitude.
- ISO-8601 timestamps normalize Z to an explicit UTC offset.
- Sequences preserve order; mappings sort keys before deterministic JSON serialization.
- Ordinary strings and scientific unit strings remain case-sensitive.

## 4. Human Rejection Markers

The primary metrics exclude only expert TRIGGER_TIME annotations carrying certainty `rejected` and an explicit comment identifying an observation time. This is the convention documented in the preserved historical report. Both the marker and its exact automatic counterpart are removed from primary denominators. Metrics including them are retained in metrics.json.

- EVENT_EVIDENCE 1843:1865 `TRIGGER_TIME` “2026-06-10 23:58:04 UT” - Expert TRIGGER_TIME annotation has certainty=rejected and an explicit comment identifying an observation time, matching the documented pilot rejection convention.
- EVENT_EVIDENCE 1913:1935 `TRIGGER_TIME` “2026-06-11 00:31:39 UT” - Expert TRIGGER_TIME annotation has certainty=rejected and an explicit comment identifying an observation time, matching the documented pilot rejection convention.
- EVENT_EVIDENCE 15719:15730 `TRIGGER_TIME` “19:43:01 UT” - Expert TRIGGER_TIME annotation has certainty=rejected and an explicit comment identifying an observation time, matching the documented pilot rejection convention.
- EVENT_EVIDENCE 20058:20081 `TRIGGER_TIME` “2026-06-11T13:05:40 UTC” - Expert TRIGGER_TIME annotation has certainty=rejected and an explicit comment identifying an observation time, matching the documented pilot rejection convention.
- EVENT_EVIDENCE 48017:48045 `TRIGGER_TIME` “on 2026-06-15 at 16:53:40 UT” - Expert TRIGGER_TIME annotation has certainty=rejected and an explicit comment identifying an observation time, matching the documented pilot rejection convention.

The primary policy and the inclusive diagnostic are both reported below. The inclusive values retain the five documented human rejection markers and their automatic counterparts.

| Layer | Policy | Automatic | Expert | Relaxed precision | Relaxed recall | Exact automatic agreement |
|---|---|---:|---:|---:|---:|---:|
| EVENT_EVIDENCE | primary (markers excluded) | 188 | 194 | 98.94% | 95.88% | 88.83% |
| EVENT_EVIDENCE | inclusive | 193 | 199 | 98.96% | 95.98% | 86.53% |
| PHOTOMETRIC_MEASUREMENT | primary (markers excluded) | 76 | 69 | 89.47% | 98.55% | 0.00% |
| PHOTOMETRIC_MEASUREMENT | inclusive | 76 | 69 | 89.47% | 98.55% | 0.00% |

## 5. Span, Label, and End-to-End Metrics

### EVENT_EVIDENCE

| Metric | Precision | Recall | F1 | TP |
|---|---:|---:|---:|---:|
| Exact span | 100.00% | 96.91% | 98.43% | 188 |
| Overlap span | 100.00% | 96.91% | 98.43% | 188 |
| Exact end-to-end | 88.83% | 86.08% | 87.43% | 167 |
| Relaxed overlap + same label | 98.94% | 95.88% | 97.38% | 186 |

Automatic=188; expert=194; paired=188; relabelled=2; label accuracy on matched spans=98.94%; full-feature agreement on matched spans=88.83%.

### PHOTOMETRIC_MEASUREMENT

| Metric | Precision | Recall | F1 | TP |
|---|---:|---:|---:|---:|
| Exact span | 89.47% | 98.55% | 93.79% | 68 |
| Overlap span | 89.47% | 98.55% | 93.79% | 68 |
| Exact end-to-end | 0.00% | 0.00% | n/a | 0 |
| Relaxed overlap + same label | 89.47% | 98.55% | 93.79% | 68 |

Automatic=76; expert=69; paired=68; relabelled=0; label accuracy on matched spans=100.00%; full-feature agreement on matched spans=0.00%.

## 6. Feature Metrics

Complete per-feature results are in `feature_metrics.csv`. Photometric span performance is not complete annotation correctness.

| Photometric feature | Accuracy |
|---|---:|
| instrument | 2.94% |
| photometric_band | 100.00% |
| obs_time_type | 83.82% |
| obs_time_reference | 32.35% |
| magnitude_or_limit | 94.12% |
| magnitude_error | 100.00% |
| measurement_type | 100.00% |

## 7. Comparison With Historical Metrics

Historical values came from a missing script that re-ran corrected rules on the 28-circular text. The reproducible comparison below instead uses the surviving automatic XMI (193/76). Differences must not be tuned away.

| Layer | Measure | Historical | Reproducible | Absolute difference |
|---|---|---:|---:|---:|
| EVENT_EVIDENCE | relaxed precision | 98.96% | 98.94% | -0.02 pp |
| EVENT_EVIDENCE | relaxed recall | 98.45% | 95.88% | -2.57 pp |
| EVENT_EVIDENCE | exact automatic agreement | 67.36% | 88.83% | +21.47 pp |
| PHOTOMETRIC_MEASUREMENT | relaxed precision | 100.00% | 89.47% | -10.53 pp |
| PHOTOMETRIC_MEASUREMENT | relaxed recall | 98.55% | 98.55% | +0.00 pp |
| PHOTOMETRIC_MEASUREMENT | exact automatic agreement | 0.00% | 0.00% | +0.00 pp |

Strict historical reconstruction did not succeed because the automatic 193/68 current-rule annotation set was never exported as a surviving XMI. The different input annotation set is the principal discrepancy; the new matching formula, overlap threshold, normalization, and rejection policy are also now explicit instead of inferred.

## 8. Known Limitations

- One event was reviewed; results do not generalize to the ten documents.
- The same pilot informed rule corrections, so this is not an independent test.
- There is no inter-annotator agreement measurement.
- The expert XMI contains a metadata feature absent from the surviving TypeSystem; the controlled in-memory augmentation is documented above.
- Feature normalization is conservative and keeps case-sensitive scientific strings distinct.

## 9. Interpretation Allowed in the PRe

The pilot supports a qualified statement about span recovery and reveals substantial feature correction work. Photometric span precision must never be presented as complete photometric correctness. The historical metrics are not strictly reproducible; these new results are reproducible for the preserved 193/76 baseline XMI and must be reported with the single-pilot, non-independent evaluation limitation.
