# Backlog Crosswalk

This document maps two independently produced backlogs: one derived from private Slack messages and one derived from in-corpus annotator comments. Symptom-level overlap is corroboration, not duplication; counts remain qualitative and are not performance metrics.

## Correspondence

| Slack ID | Comment-derived ID | Same symptom? | Relationship |
|---|---|---|---|
| A-01 | AC-01a | yes | Both sources report valid photometric detections absent from the baseline. |
| A-02 | AC-01a | partial | The 48 missed detections include compact/table spans, but AC-01a is not syntax-specific. |
| A-03 | AC-01r | partial | AC-01r contains two low-support LIGHTCURVE_EVOLUTION creations, not a dedicated decline-from-X-to-Y group. |
| A-04 | AC-01d, CC-01, CC-02 | yes | Comments independently record missed radio counterparts, radio measurements, and missing radio flux. |
| A-05 | AC-01b | yes | Thirty created localization spans include BAT/XRT/UVOT coordinates and confidence radii. |
| A-06 | AC-01e, AC-03, BC-05 | partial | Comments show missed high-energy quantities and modality relabels, but not every Slack instrument-binding case. |
| A-07 | BC-05 | yes | A structured correction explicitly says event redshift rather than REDSHIFT_CONTEXT. |
| A-08 | CC-01 | yes | A comment explicitly identifies a colour expression as photometric rather than redshift. |
| A-09 | CC-01 | yes | A comment explicitly identifies the SN1998bw-like statement as classification information. |
| A-10 | AC-02 | yes | Five TRIGGER_INSTRUMENT comments explicitly deny trigger role; the comments support and extend the Slack case set. |
| A-11 | AC-02 | yes | Four TRIGGER_TIME comments identify observation/start/offset times rather than triggers. |
| A-12 | AC-03, DC-03 | yes | A comment states that the conditional absorption phrase is not a NEGATIVE_STATEMENT. |
| B-01 | BC-01, BC-03, DC-03 | yes | Both sources repeatedly distinguish absolute, start, mid, and trigger-relative time semantics. |
| B-02 | BC-03, DC-03 | yes | Comments explicitly request mid-time instead of start-time in recurrent rows. |
| B-03 | BC-03, BC-05 | partial | Comments cover missing date context and time-field changes, but combine photometry and trigger-time cases. |
| B-04 | BC-05 | yes | Evidence comments repeatedly complete trigger times with dates recovered from circular context. |
| B-05 | BC-01, BC-04, DC-03 | yes | AB/Vega population and uncertainty conventions recur throughout the comments. |
| B-06 | BC-01, BC-02 | yes | Instrument additions are a recurrent structured photometry correction. |
| B-07 | BC-01, BC-04 | yes | Photometry field corrections include magnitude-error population. |
| B-08 | BC-01, BC-04 | yes | Photometric-band population is represented among single- and multi-field corrections. |
| C-01 | DC-02 | partial | Comments strongly request a primary trigger convention; they do not by themselves decide field versus guide design. |
| C-02 | AC-01e, CC-01 | partial | Comments show missed high-energy quantities and unrepresented non-optical measurements, but not a complete X-ray schema. |
| C-03 | CC-02 | yes | Comments repeatedly request explicit Galactic-extinction correction status absent from structured fields. |
| C-04 |  | no | No comment-derived backlog entry isolates a structured epoch for LIGHTCURVE_EVOLUTION. |
| C-05 | AC-01r | partial | The residual contains one T90-accuracy comment, but not a systematic T90-by-energy-band representation task. |
| C-06 |  | no | No comment-derived backlog entry represents relations among successive localizations. |
| D-01 | DC-02 | yes | Both sources record ambiguity in selecting the primary/best trigger time and source. |
| D-02 | BC-05, DC-03 | partial | Comments cover certainty/value changes and uncertain conventions, but not the full span-boundary rubric. |
| D-03 |  | no | No comment-derived backlog entry concerns review_priority. |
| D-04 |  | no | No comment-derived backlog entry concerns EVENT_SUMMARY workflow. |
| D-05 | BC-04, DC-03 | yes | Comments repeatedly expose explicit and inferred AB/Vega conventions. |
| D-06 | BC-04, DC-03 | partial | Comments discuss filter equivalences and band population, but do not establish a complete normalization policy. |
| D-07 | AC-01a | partial | Missing detections corroborate the annotation-unit problem, but AC-01a does not isolate multi-value sentences. |
| D-08 | DC-01 | yes | DC-01 directly reproduces MASTER, amateur, GRANDMA, duplicate, and LLM scope exclusions. |
| D-09 | DC-01 | yes | DC-01 includes explicit comments excluding galaxy photometry from transient measurements. |
| D-10 | CC-01 | yes | A comment explicitly identifies a supernova interpretation needing classification representation. |
| D-11 | BC-01, BC-04 | partial | Comments support magnitude-error population, but do not fully encode the span-editing workflow. |
|  | AC-01c | no | Comments report missing trigger-instrument spans; Slack A-10 instead concerns false-positive follow-up instruments. |
|  | AC-01f | no | Comments report entirely missed REDSHIFT_EVENT spans; Slack A-07 concerns an existing span with the wrong redshift label. |

## Symptoms Confirmed By Both Sources

A-01 <-> AC-01a; A-04 <-> AC-01d, CC-01, CC-02; A-05 <-> AC-01b; A-07 <-> BC-05; A-08 <-> CC-01; A-09 <-> CC-01; A-10 <-> AC-02; A-11 <-> AC-02; A-12 <-> AC-03, DC-03; B-01 <-> BC-01, BC-03, DC-03; B-02 <-> BC-03, DC-03; B-04 <-> BC-05; B-05 <-> BC-01, BC-04, DC-03; B-06 <-> BC-01, BC-02; B-07 <-> BC-01, BC-04; B-08 <-> BC-01, BC-04; C-03 <-> CC-02; D-01 <-> DC-02; D-05 <-> BC-04, DC-03; D-08 <-> DC-01; D-09 <-> DC-01; D-10 <-> CC-01

## Symptoms Only In Slack

C-04, C-06, D-03, D-04

## Symptoms Only In Comments

AC-01c, AC-01f

## Partial Correspondences

A-02 <-> AC-01a; A-03 <-> AC-01r; A-06 <-> AC-01e, AC-03, BC-05; B-03 <-> BC-03, BC-05; C-01 <-> DC-02; C-02 <-> AC-01e, CC-01; C-05 <-> AC-01r; D-02 <-> BC-05, DC-03; D-06 <-> BC-04, DC-03; D-07 <-> AC-01a; D-11 <-> BC-01, BC-04

## Required Spot Checks

- **DC-01 versus D-08:** supports and extends. DC-01 contains 152 comments from 2 annotators across 4 documents.
- **TRIGGER_INSTRUMENT versus A-10:** supports and extends, without contradiction. There are 96 TRIGGER_INSTRUMENT comments, including 5 explicit false-positive rows.
