# CORRECTIONS_FROM_ANNOTATORS.md

## Purpose and scope

This document consolidates issues reported by astronomers while validating automatic pre-annotations in INCEpTION for the MAFORAI GCN corpus. It is intended as a handover document for a future V2 of the extraction and annotation workflow.

The primary source of this document is the Slack feedback reviewed during this task. Most entries are based directly on annotator messages and the decisions recorded in those conversations. A small subset of entries — specifically [A-10], [A-11], and [A-12] — is additionally supported by evidence from the validated corpus itself, including rejected or corrected pre-annotations and annotator comments. No additional cases, repository behavior, or external assumptions have been introduced beyond those two evidence sources. When neither the discussion nor the validated corpus established whether something was a real bug, the point is kept in the final **Open questions** section instead of being promoted to a confirmed correction.

The correction categories are:

- **A. RULE FIXES** — the extractor captures something it should not, or fails to capture something it should.
- **B. FIELD POPULATION** — the annotation/span is present, but one of its structured fields is missing or incorrectly populated.
- **C. SCHEMA GAPS** — the current schema cannot represent information the annotators considered relevant.
- **D. GUIDE GAPS** — the schema can represent the information, but the annotation or corpus guide does not define the convention clearly enough.

> **Schema note from Slack:** the discussion with Priya explicitly refers to a `magnitude_error` field in `PHOTOMETRIC_MEASUREMENT`. That terminology is preserved here because it appears directly in the Slack validation discussion.

---

# A. RULE FIXES

### [A-01] Photometric measurements are sometimes not pre-annotated at all

- **Reported by:** Dahlia; Zhanat Maksut; Yodgor; Sarah.
- **Layer / label:** `PHOTOMETRIC_MEASUREMENT`.
- **Symptom:** A non-negligible fraction of valid photometric measurements is absent from the automatic pre-annotations and must be created manually by the annotator.
- **Evidence:** Dahlia reported: **“Photometry not highlighted or detected at all.”** Zhanat estimated that **“10–20% of the photometry values were left unannotated.”** Yodgor reported a case with **“4 measurements with 4 their MJD time”** that the tool had not captured. Sarah also reported missing infrared J-band photometry in `GCN-251013_173943`: **“Infrared J-band : Missing information and extract the photometric measurements.”**
- **Likely cause:** The current photometry rules do not cover all formatting styles used in GCN circulars. Slack identifies several concrete sub-patterns elsewhere in this document, but does not establish a single root cause for all misses.
- **Suggested fix:** Build a V2 regression set from all manually added photometric annotations and audit false negatives by textual pattern. The first objective should be improving recall without relaxing the rule so broadly that non-transient or host-galaxy photometry is captured incorrectly. The specific compact/tabular and narrative patterns reported by Sarah should be handled with dedicated rules rather than only a generic fallback.
- **Effort:** medium.
- **Confidence:** high.

### [A-02] Compact and tabular photometric syntax is repeatedly missed

- **Reported by:** Sarah; Yodgor.
- **Layer / label:** `PHOTOMETRIC_MEASUREMENT`.
- **Symptom:** Measurements written as compact sequences of date/time, exposure, filter, magnitude, uncertainty, and related values are often not converted into photometric annotations.
- **Evidence:** Sarah gave the concrete example from `GCN-260604_202037`: **“2026.06.08 20:01:14 4.01102 12*300 Rc 23.08 +/- 0.18 23.8”** and said **“ce type de syntaxe pour la mesure est souvent oublié”**, adding that she had seen the same problem in the previous event. Yodgor independently reported four measurements with four MJD times that were not captured.
- **Likely cause:** Rules appear to rely more successfully on narrative phrasing than on dense, table-like or whitespace-separated measurement records.
- **Suggested fix:** Add explicit parsing patterns for compact measurement rows. The parser should identify the complete measurement unit first and then populate date/time, exposure, band, magnitude/limit, uncertainty, and instrument fields when those values are present. Use the exact manually corrected examples as regression fixtures.
- **Effort:** medium.
- **Confidence:** high.

### [A-03] Narrative photometric evolution such as “decline from X to Y” is not captured

- **Reported by:** Sarah.
- **Layer / label:** `PHOTOMETRIC_MEASUREMENT` and/or `ASTRO_EVIDENCE → LIGHTCURVE_EVOLUTION`, depending on the intended representation.
- **Symptom:** Photometric information expressed as a narrative change between two values can be missed even though the sentence contains scientifically useful evolution information.
- **Evidence:** For `GCN-251013_173943`, Sarah described a sentence similar to **“photometry decline from XXX to XXX”** and said that the information **“ça s'est pas suivi”** / was not picked up correctly.
- **Likely cause:** The extraction logic likely expects individual measurement syntax and does not recognize a range/evolution construction in prose.
- **Suggested fix:** Add a dedicated rule for the exact reported construction in which the circular states that photometry declined from one value to another. Before generalizing to other verbs or phrasings, verify them from actual corrected annotations rather than inventing variants.
- **Effort:** low.
- **Confidence:** low.

### [A-04] Radio measurements, radio fluxes, and radio-counterpart semantics are under-extracted

- **Reported by:** Sarah.
- **Layer / label:** `PHOTOMETRIC_MEASUREMENT` for radio measurements/fluxes where applicable; `ASTRO_EVIDENCE → COUNTERPART_ASSOCIATION` for radio-counterpart identification.
- **Symptom:** Radio information may be partially detected as a localization or generic radio mention while the actual measurement points, flux, or the fact that the source is a radio counterpart is omitted.
- **Evidence:** In event `2026owq`, Sarah reported: **“sur la radio, il a pas pris tous les points de radio, il a pris les points de optique.”** In `GCN-251013_173943`, she said the system identified radio/localization but **“pas que c'était une contrepart radio”** and did not capture the flux; she also wrote **“AMI-LA : Radio-counterpart missing info.”** In `GCN-260604_202037`, she again noted a missing **“Radio counterpart ... from VLA”** and explicitly said the radio problem had already appeared in her other comments.
- **Likely cause:** Radio-specific reporting formats and counterpart language are not covered as thoroughly as optical photometry, and current rules may separate localization detection from counterpart/measurement semantics.
- **Suggested fix:** Add radio-specific regression cases covering at least three distinct outputs: (1) radio measurement/flux, (2) radio counterpart association, and (3) localization linked to the radio counterpart. Do not consider the issue fixed if only the word “radio” or a position is detected.
- **Effort:** medium.
- **Confidence:** high.

### [A-05] A better Swift localization can be missed while only localization uncertainty is captured

- **Reported by:** Yodgor.
- **Layer / label:** `ASTRO_EVIDENCE → LOCALIZATION`.
- **Symptom:** The extractor can annotate a localization-related uncertainty while missing a more useful Swift localization present in the same circular.
- **Evidence:** Yodgor reported: **“you can see better localization from Swift which not grabbed by your tool (program). Of course it grabbed uncertainty localization (only).”**
- **Likely cause:** The localization rule may match the uncertainty expression independently without requiring or preferentially capturing the full coordinate/localization statement.
- **Suggested fix:** Revisit the corrected circular and identify the exact syntax of the missed Swift localization. Add a regression test ensuring that the complete localization is captured, not only the uncertainty fragment. The Slack transcript does not contain the actual coordinate text, so the precise pattern must be recovered from the annotated document.
- **Effort:** medium.
- **Confidence:** low.

### [A-06] High-energy instrument and modality context can be assigned incorrectly

- **Reported by:** Sarah.
- **Layer / label:** `ASTRO_EVIDENCE`, especially `COUNTERPART_ASSOCIATION`, `TRIGGER_INSTRUMENT`, and context attached to high-energy properties.
- **Symptom:** The extractor can detect a high-energy statement but fail to preserve which instrument/modality it belongs to, or can attribute it to the wrong instrument.
- **Evidence:** In `GCN-251013_173943`, Sarah reported three related problems: (1) an MXT localization was detected but **not that it was an X-ray counterpart**; (2) information had been attributed to **ECLAIRs** when **“non, c'était Swift XRT”**; and (3) **“fast rising”** associated with ECLAIRs was gamma-ray prompt information, **“c'est des gamma ray data”**, not X-ray information.
- **Likely cause:** The rules appear to identify nearby scientific phrases without sufficiently binding them to the correct instrument and energy-domain context.
- **Suggested fix:** Make instrument/modality association part of the extraction rule rather than a post-hoc label guess. Add regression examples in which the same circular contains multiple high-energy instruments and require that counterpart type, prompt-emission description, and localization remain linked to the correct instrument.
- **Effort:** medium.
- **Confidence:** low.

### [A-07] A GRB redshift can be mislabeled as `REDSHIFT_CONTEXT`

- **Reported by:** Priya Gokuldass.
- **Layer / label:** `ASTRO_EVIDENCE → REDSHIFT_EVENT` vs `REDSHIFT_CONTEXT`.
- **Symptom:** A redshift belonging to the GRB itself can be labeled as contextual redshift when it appears inside another scientific analysis, such as an intrinsic-absorption fit.
- **Evidence:** Priya compared GCN 37982, where **“Assuming the redshift z = 1.411”** was labeled `REDSHIFT_EVENT`, with GCN 37988, where the same GRB redshift was labeled `REDSHIFT_CONTEXT`. Carlos explicitly resolved the case: **“both should be REDSHIFT_EVENT ... 37988 is mislabeled ... That's a rule bug on our side.”**
- **Likely cause:** The rule may use surrounding contextual language to decide the label instead of determining what physical object the redshift refers to.
- **Suggested fix:** Classify a redshift by its referent. If the value is the event/GRB redshift, keep `REDSHIFT_EVENT` even when the value is used as an input to another calculation or fit. Add GCN 37988 as a regression example.
- **Effort:** low.
- **Confidence:** high.

### [A-08] Photometric colors such as `g-z` or `r-z` can be mistaken for redshift

- **Reported by:** Sarah.
- **Layer / label:** `ASTRO_EVIDENCE → REDSHIFT_EVENT` / `REDSHIFT_CONTEXT` false positive.
- **Symptom:** The presence of the symbol/band `z` in a color expression can trigger a redshift annotation even though the text refers to a photometric color difference.
- **Evidence:** In `GCN-260604_202037`, Sarah wrote: **“G-z measurement : it is a color difference from the LC, not a measurement from the redshift.”** In the audio she also mentioned `g-z` and `r-z` and said they were related to color evolution, not redshift.
- **Likely cause:** A redshift rule may be over-triggering on `z` without enough syntactic context.
- **Suggested fix:** Add a negative gate for photometric color expressions such as the reported `g-z` and `r-z` patterns. Require redshift-specific syntax/context before assigning a redshift label.
- **Effort:** low.
- **Confidence:** low.

### [A-09] Relevant classification interpretation can be omitted

- **Reported by:** Sarah.
- **Layer / label:** `ASTRO_EVIDENCE → CLASSIFICATION_INTERPRETATION`.
- **Symptom:** A scientifically relevant comparative/interpretive statement about the transient can be left unannotated.
- **Evidence:** In `GCN-251013_173943`, Sarah quoted: **“Also a SN1998bw-like supernova would be much fainter at this redshift”** and stated that it was scientifically interesting and **“il aurait fallu le taguer.”**
- **Likely cause:** The current rule set may focus on direct classifications and miss conditional, comparative, or counterfactual interpretation statements.
- **Suggested fix:** Add this exact sentence as a regression case for `CLASSIFICATION_INTERPRETATION`. Expand the rule only after inspecting similar corrected spans, because Slack provides one concrete phrasing rather than evidence for a broad family of constructions.
- **Effort:** low.
- **Confidence:** low.

### [A-10] Follow-up instruments are labeled as `TRIGGER_INSTRUMENT`

- **Reported by:** Camille Douzet.
- **Layer / label:** `ASTRO_EVIDENCE → TRIGGER_INSTRUMENT`.
- **Symptom:** Instruments that only observed the event in follow-up are labeled as the instrument that triggered the alert.
- **Evidence:** Camille rejected 11 `TRIGGER_INSTRUMENT` pre-annotations by setting `certainty` to `rejected`, across three documents. Cases include **Fermi-LAT**, **Fermi/LAT**, **GECAM** (`event_GRB-260708A.xmi`) and **SVOM/ECLAIRs**, **SVOM/GRM**, **GRM** (`event_GCN-251222_170549.xmi`), with comments such as **“Just a follow-up instrument”**, **“not the trigger instrument”** and **“It is the instrument that detected the burst...”**. The same confusion was raised independently by Priya, who noted that the guide asks for the trigger instrument but the SkyPortal summary also records follow-up instruments.
- **Likely cause:** The instrument vocabulary matches a facility name without checking whether the governing clause describes a trigger (“triggered and located”, “detected at T0”) or a follow-up observation (“observations with X in response to the alert”).
- **Suggested fix:** Require trigger-governing language in the same clause before emitting `TRIGGER_INSTRUMENT`; otherwise emit nothing. Use the listed spans as regression cases.
- **Effort:** medium.
- **Confidence:** high — 11 rejections, three documents, and corroborated by a second annotator.

### [A-11] Observation times are labeled as `TRIGGER_TIME`

- **Reported by:** Camille Douzet.
- **Layer / label:** `ASTRO_EVIDENCE → TRIGGER_TIME`.
- **Symptom:** Times marking when a telescope observed are labeled as the burst trigger time.
- **Evidence:** Camille rejected two `TRIGGER_TIME` pre-annotations: **“2026-07-08 22:40:00 UT”** with the comment **“Not the trigger time”** (`event_GRB-260708A.xmi`) and **“2025-12-22T17:05:46 UTC”** with **“t0, not trigger time”** (`event_GCN-251222_170549.xmi`). A third case, **“2025-12-22T17:05:52”**, was downgraded to `tentative` with **“1sec after the trigger time”**.
- **Likely cause:** The rule matches a timestamp without checking whether the governing clause is observation-based (“observations started”, “we observed”, “exposure”) or trigger-based.
- **Suggested fix:** Apply the same governing-clause test as A-10 to timestamps, and keep observation epochs in the photometry layer, which already carries `obs_time_raw`.
- **Effort:** medium.
- **Confidence:** high — three cases with explicit annotator comments.

### [A-12] `NEGATIVE_STATEMENT` fires on conditional hypotheses

- **Reported by:** Dahlia.
- **Layer / label:** `ASTRO_EVIDENCE → NEGATIVE_STATEMENT`.
- **Symptom:** A negated phrase inside a conditional clause is captured as a rejected association about the event.
- **Evidence:** In GCN 37959 (`GRB241030`), the sentence **“...the redshift of the GRB is likely to be 1.411, but perhaps larger if the highest-redshift doublet is not associated with the interstellar medium in the host galaxy”** produced a `NEGATIVE_STATEMENT` with `certainty = rejected` on **“not associated with the interstellar medium”**. Dahlia flagged it: the phrase is a conditional hypothesis about where an absorption doublet originates, not a rejected association about the event. Carlos confirmed it is a false positive.
- **Likely cause:** The `not_associated` rule matches the negated phrase without checking whether it sits inside a conditional or hypothetical clause (“if”, “unless”, “perhaps ... if”, “assuming”, “in case”).
- **Suggested fix:** Gate `NEGATIVE_STATEMENT` against conditional and hypothetical context, in the same way the extractor already gates negated light-curve behavior (“no longer fading”). Use GCN 37959 as a regression case.
- **Effort:** low.
- **Confidence:** high — one case, but precisely located and confirmed.

---

# B. FIELD POPULATION

### [B-01] Observation time parsing and `obs_time_type` semantics are frequently wrong

- **Reported by:** Dahlia; Zhanat Maksut; Sarah.
- **Layer / label:** `PHOTOMETRIC_MEASUREMENT`; primarily `obs_time_raw` and `obs_time_type`.
- **Symptom:** Observation times are often detected but assigned the wrong temporal meaning, especially `absolute_time` versus observation start time or mid-time. Different date/time formats also cause misinterpretation.
- **Evidence:** Dahlia reported: **“Every single time it is automatically detected as absolute_time, and that is almost always incorrect. It is always either the start time or the mid-time when it's given as a UT or MJD date.”** She later repeated that **“whether its obs start time, mid time, etc is mostly incorrect.”** Zhanat similarly reported that observation dates were **“sometimes misinterpreted”** because circulars use heterogeneous formats. Sarah repeatedly identified start-time/mid-time problems in her events.
- **Likely cause:** The current field-population logic appears to use a default temporal type instead of deriving semantics from local wording and the structure of the observation record.
- **Suggested fix:** Replace the unconditional/default `absolute_time` behavior with context-sensitive rules. Preserve the raw time text first, then infer `start`, `mid`, or other supported types only when the circular provides enough evidence. Add separate regression cases for UT, MJD, explicit intervals, and start-time plus exposure. When the semantics are not recoverable, do not invent them.
- **Effort:** medium.
- **Confidence:** high.

### [B-02] Mid-time is not derived when the circular provides an interval or start time plus exposure

- **Reported by:** Sarah.
- **Layer / label:** `PHOTOMETRIC_MEASUREMENT`; `obs_time_raw` / derived mid-time, with `exposure_time_raw` as supporting information.
- **Symptom:** The system can retain the start time but fail to compute or populate the observational mid-time when enough information is present.
- **Evidence:** For event `2026owq`, Sarah said **“il y a plusieurs fois où il ne prend pas le mid-time parce qu'il ne sait pas calculer ça par rapport à l'exposure.”** For `GCN-260604_202037`, the circular said **“2026-06-05 03:41 to 03:51.”** Sarah's audio says the system took the start time and **“il faudrait calculer le mid-time.”** The written note for that same case says “it should take the start time,” which conflicts with the audio; the audio is consistent with her earlier mid-time comments.
- **Likely cause:** No arithmetic derivation step is applied after parsing exposure duration or a start/end interval.
- **Suggested fix:** Add an explicit, testable derivation step when the corpus convention requires mid-time: `mid_time = start_time + exposure_time / 2`, or the midpoint of an explicit start/end interval. Preserve the original raw expression for traceability. Before implementing the Colibri example, verify the manually corrected annotation because the written and spoken Slack notes conflict.
- **Effort:** medium.
- **Confidence:** low.

### [B-03] Time-of-day can be captured without enough date context

- **Reported by:** Sarah.
- **Layer / label:** `PHOTOMETRIC_MEASUREMENT → obs_time_raw`.
- **Symptom:** A value such as an hour in UTC can be extracted without the corresponding calendar date needed to resolve the full observation timestamp.
- **Evidence:** In `GCN-260604_202037`, Sarah wrote: **“At 05:01:UTC —> ok, but I suggest to also flag the date as well.”** She explained that otherwise the system does not know which day the time belongs to.
- **Likely cause:** The extractor treats a local time expression as self-contained and does not propagate the date from nearby context.
- **Suggested fix:** When an observation gives a time-of-day only, look for a clearly associated date in the same measurement context and preserve the combined timestamp. Do not borrow a date across unrelated measurements or sections when the association is ambiguous.
- **Effort:** low.
- **Confidence:** low.

### [B-04] Trigger-time values can remain incomplete even when the missing information is in the circular

- **Reported by:** Yodgor.
- **Layer / label:** `ASTRO_EVIDENCE → TRIGGER_TIME`.
- **Symptom:** A trigger-time annotation may exist but its value can be incomplete even though the circular itself contains the information required to complete it.
- **Evidence:** Yodgor asked whether he should **“correct (improve) the Trigger time for Swift.”** Carlos clarified that the annotator could improve the value using information already present in the circular and suggested documenting that the **“Value [was] completed using missing information found in the subject.”**
- **Likely cause:** Trigger-time field population may only use the matched span and not complementary information elsewhere in the same circular, including the subject/title.
- **Suggested fix:** Allow trigger-time value construction to use clearly linked information from the circular subject or nearby text when the span alone is incomplete. Keep provenance/comment information so the source of the completed value is auditable.
- **Effort:** low.
- **Confidence:** low.

### [B-05] Explicit AB/Vega photometric-system information is frequently not populated

- **Reported by:** Dahlia; Zhanat Maksut; Sarah.
- **Layer / label:** `PHOTOMETRIC_MEASUREMENT → photometric_system`.
- **Symptom:** `photometric_system` is often empty even when AB or Vega is explicitly written next to the measurement or elsewhere in the relevant text.
- **Evidence:** Dahlia reported that **“the photometric system is almost never detected”** and later specified **“Magnitude systems not detected (AB/Vega) even when they're mentioned in the text or right next to the measurement.”** Zhanat said that for most annotated values the system could not determine AB/Vega **“even when this was explicitly stated in the text.”** Sarah reported a case where AB was written but still treated as missing, and another where **“ABmag —> AB system”** was not recognized.
- **Likely cause:** The field-population rule likely has limited lexical coverage and may not propagate system information from nearby context to the measurement.
- **Suggested fix:** Add direct mappings for explicit markers observed in the corpus, including `AB`, `ABmag`, and explicit `Vega`, and propagate them to the associated measurement when the relation is unambiguous. Keep this separate from the inference/default policy in [D-05].
- **Effort:** low.
- **Confidence:** high.

### [B-06] The observing instrument is usually missing from photometric measurements

- **Reported by:** Dahlia.
- **Layer / label:** `PHOTOMETRIC_MEASUREMENT → instrument`.
- **Symptom:** A photometric measurement is annotated, but the instrument that produced it is usually absent from the structured field.
- **Evidence:** Dahlia first said: **“The instrument is almost never there.”** She later repeated: **“Instruments which made the observation are almost always never detected,”** and suggested that the value could sometimes be extracted **“from the title ... or from the text.”**
- **Likely cause:** Instrument extraction may be restricted to the local measurement span and fail to use the circular subject/title or sentence-level observational context.
- **Suggested fix:** Resolve the instrument from both the measurement text and the circular subject/title when the association is explicit. Add guards for circulars containing several instruments so that a title-level instrument is not blindly assigned to every measurement.
- **Effort:** medium.
- **Confidence:** high.

### [B-07] Photometric magnitude uncertainty is omitted from `magnitude_error`

- **Reported by:** Dahlia; Priya Gokuldass.
- **Layer / label:** `PHOTOMETRIC_MEASUREMENT → magnitude_error`.
- **Symptom:** The magnitude itself can be detected correctly while the associated uncertainty/error is not populated.
- **Evidence:** Dahlia reported **“multiple errors where the magnitude is detected but then the error is not highlighted.”** Priya later asked whether she should extend an annotation span to include an uncertainty. Carlos clarified that **“the uncertainty of a photometry point goes in the magnitude_error field, not in the span”** and that she should fill `magnitude_error` rather than recreate the annotation.
- **Likely cause:** The magnitude parser and uncertainty parser are not consistently linked, or the uncertainty is treated as span text without being copied into the structured field.
- **Suggested fix:** Whenever a measurement contains an explicit uncertainty associated with the magnitude, populate `magnitude_error`. Add tests for the exact `+/-` style seen in Sarah's compact measurement example as well as the corrected examples from Dahlia/Priya.
- **Effort:** low.
- **Confidence:** high.

### [B-08] Explicit photometric filters/bands are sometimes left unpopulated

- **Reported by:** Zhanat Maksut.
- **Layer / label:** `PHOTOMETRIC_MEASUREMENT → photometric_band`.
- **Symptom:** The measurement is annotated but the filter field remains empty even when the filter name is explicitly present in the circular.
- **Evidence:** When Sarah asked specifically about filters, Zhanat replied: **“in roughly 20% cases it could not identify filter, even if it was written in the text.”**
- **Likely cause:** Band/filter lexical coverage is incomplete, or the parser fails to associate an explicit filter token with the correct measurement.
- **Suggested fix:** Audit all manually corrected `photometric_band` values and add the missing literal filter forms. Keep literal extraction separate from the normalization/equivalence rules described in [D-06].
- **Effort:** low.
- **Confidence:** high.

---

# C. SCHEMA GAPS

### [C-01] No field identifies the primary/first trigger instrument when several instruments triggered the event

- **Reported by:** Priya Gokuldass.
- **Layer / label:** `ASTRO_EVIDENCE → TRIGGER_INSTRUMENT`.
- **Symptom:** Several instruments can all be correctly annotated as `TRIGGER_INSTRUMENT`, but the schema has no structured way to identify which one produced the primary/first alert.
- **Evidence:** Priya described an event in which **Fermi/GBM, SVOM/ECLAIRs, and SVOM/GRM** all had trigger context. She asked whether Fermi should be primary because it alerted first. Carlos confirmed that all three should remain `TRIGGER_INSTRUMENT` and stated: **“There's no ‘primary’ field yet; that's a real gap in our schema.”**
- **Likely cause:** `TRIGGER_INSTRUMENT` was modeled as a flat span label without an attribute representing trigger role/order.
- **Suggested fix:** Extend V2 so that multiple trigger instruments can be retained while optionally marking one as primary/first alert when the circular evidence supports that distinction. The exact field name and allowed values should be decided before implementation; Slack only establishes that the distinction is needed.
- **Effort:** medium.
- **Confidence:** high.

### [C-02] X-ray detections, fluxes, and light curves have no structured home

- **Reported by:** Priya Gokuldass; confirmed by Carlos.
- **Layer / label:** Current `PHOTOMETRIC_MEASUREMENT` plus `ASTRO_EVIDENCE`; exact V2 representation undecided.
- **Symptom:** Swift-XRT circulars can contribute a localization, but X-ray detections, fluxes, light curves, and other XRT-specific measurements cannot be represented in the existing measurement schema.
- **Evidence:** Priya reported that Swift-XRT circulars, including **“the Enhanced XRT Position circular,”** had **“very limited coverage in the schema”** and that there was no way to represent **“X-ray detections, fluxes, light curves, or other XRT-specific information.”** Carlos answered: **“that's a real gap ... X-ray detections, fluxes and light curves don't have a home yet.”**
- **Likely cause:** The measurement layer was designed around optical/IR/radio information and does not contain an X-ray-specific or wavelength-general measurement representation.
- **Suggested fix:** Design an extension that can represent X-ray measurement values and their observational context without forcing them into optical-photometry fields. The Slack discussion explicitly leaves the exact design for a later phase, so V2 should begin with a schema decision rather than an ad-hoc rule.
- **Effort:** high.
- **Confidence:** high.

### [C-03] Galactic-extinction correction status is not represented structurally

- **Reported by:** Sarah.
- **Layer / label:** `PHOTOMETRIC_MEASUREMENT`.
- **Symptom:** The schema cannot explicitly record whether a reported photometric value has been corrected for Galactic extinction.
- **Evidence:** In event `2026owq`, Sarah said it would be useful to capture **“si l'information ... est corrigé ou pas l'extinction.”** She added that authors do not always state this and that, in her experience, when it is not stated the value is often effectively **without Galactic extinction correction**.
- **Likely cause:** No dedicated extinction-correction attribute exists in the current measurement fields discussed during annotation.
- **Suggested fix:** Add a structured way to represent extinction-correction status. Do not silently encode Sarah's default assumption as fact; the field should distinguish explicit information from an inferred/default convention if the team chooses to use one.
- **Effort:** medium.
- **Confidence:** low.

### [C-04] `LIGHTCURVE_EVOLUTION` cannot store the epoch of the reported evolution

- **Reported by:** Sarah.
- **Layer / label:** `ASTRO_EVIDENCE → LIGHTCURVE_EVOLUTION`.
- **Symptom:** A phenomenon such as rebrightening can be correctly annotated, but the schema has no clear structured field for when that evolution occurred relative to the event.
- **Evidence:** In `GCN-260604_202037`, Sarah said the system successfully flagged **“Rebrightening”** but **“the pre-annotation didn’t capture the epoch of the re-brightening.”** She gave the example of associating the evolution with an epoch such as **“30 heures après.”**
- **Likely cause:** `ASTRO_EVIDENCE` provides generic attributes such as value/unit/comment but no dedicated epoch or time-since-trigger relation for light-curve evolution.
- **Suggested fix:** Extend V2 so a `LIGHTCURVE_EVOLUTION` span can be associated with an epoch or relative-time expression. The exact representation—new field versus relation to a time span—should be decided at schema level before writing extraction rules.
- **Effort:** medium.
- **Confidence:** low.

### [C-05] A single event-level T90 value is insufficient because T90 depends on energy band

- **Reported by:** Patrice.
- **Layer / label:** `ASTRO_EVIDENCE → T90`; event metadata if a single T90 is currently stored there.
- **Symptom:** Treating T90 as one canonical event-level value loses information because the same event can have several valid T90 measurements in different energy bands.
- **Evidence:** Patrice stated: **“Il n'y a pas qu'un seul T90 (ça dépend de la bande d'énergie).”** When Carlos asked what should be kept, Patrice answered that he would store **“les différents T90 mesurés dans différentes bandes.”** Carlos concluded that those values should not be represented as one metadata value and should instead be taken from the spans. Patrice therefore left T90 unfilled in metadata for event `260614B`.
- **Likely cause:** The event-level representation assumes one scalar T90 and does not preserve the measurement's energy-band context.
- **Suggested fix:** Keep each T90 measurement independently and ensure its energy-band context can be retained. Do not collapse several T90 values into one metadata scalar. If the existing `T90` span attributes cannot encode the band, extend them before using the spans as the authoritative representation.
- **Effort:** medium.
- **Confidence:** high.

### [C-06] Relationships between successive/refined localizations are not represented

- **Reported by:** Sarah.
- **Layer / label:** `ASTRO_EVIDENCE → LOCALIZATION`.
- **Symptom:** The schema can store several localizations independently but cannot express that one localization refines, contains, or is contained within another localization from a different instrument.
- **Evidence:** In `GCN-251013_173943`, Sarah described a cascade: a broad Fermi/GBM localization, then a more precise ECLAIRs localization, then an MXT/X-ray localization. She stressed that the MXT localization is **contained inside** the ECLAIRs localization, likening the sequence to nested Russian dolls.
- **Likely cause:** Localizations are modeled as independent evidence spans without explicit inter-localization relations.
- **Suggested fix:** Consider a V2 relation or structured attribute for localization refinement/containment. Do not force this into free-text comments if the information is expected to support downstream reasoning. The exact relation vocabulary should be designed with the astronomy team because Slack provides one clear example but not a complete ontology.
- **Effort:** high.
- **Confidence:** low.

---

# D. GUIDE GAPS

### [D-01] `best_trigger_time` and `best_trigger_time_source` need an explicit selection rule

- **Reported by:** Yodgor; Sarah.
- **Layer / label:** `EVENT_SUMMARY`; trigger-time summarization.
- **Symptom:** Annotators do not know which trigger time should be selected when several instruments report very similar T0 values, or exactly what should be stored as the source.
- **Evidence:** Yodgor asked what **“best trigger time”** and **“best trigger time source”** mean and gave the example of Fermi/GBM and Swift/BAT differing by milliseconds. Carlos initially said that if there is no significant difference the annotator can select either one, and that the source is the circular corresponding to the selected trigger time. Sarah later gave a more specific convention in event `2026owq`: if the T0 values are within about **two minutes**, use one of them, **generally the first instrument/circular that alerted everyone**. Carlos's Slack message contains one wording slip saying `best_trigger_time` should be the circular number; by context that appears to refer to `best_trigger_time_source`, but the guide should remove that ambiguity explicitly.
- **Likely cause:** The guide defines the fields but not the adjudication rule for multiple valid trigger times.
- **Suggested fix:** Document a deterministic convention: preserve all trigger-time evidence spans, then select the event-summary trigger time according to the agreed rule for near-simultaneous triggers, and store the circular identifier that contains the selected value in `best_trigger_time_source`. The team should confirm whether Sarah's “about two minutes / first alert” rule supersedes Carlos's earlier “either one” guidance.
- **Effort:** low.
- **Confidence:** high.

### [D-02] Uncertainty wording, span boundaries, `certainty`, and normalized `value` need a shared convention

- **Reported by:** Priya Gokuldass; resolved by Carlos.
- **Layer / label:** `ASTRO_EVIDENCE`, especially interpretation/classification spans with `certainty` and `value`.
- **Symptom:** Annotators may choose different span boundaries or certainty values for phrases such as “likely afterglow.”
- **Evidence:** Priya asked whether the span should be only **“afterglow”** or the full phrase **“likely afterglow.”** Carlos defined the rule: span = **“likely afterglow”**, `certainty = tentative`, `value = afterglow`. He also specified: `candidate` / “candidate for” → `candidate`; “likely” / “possible” / “may be” → `tentative`; direct/confirmed statements → `confirmed`; “unlikely” / “ruled out” / “not” → `rejected`.
- **Likely cause:** The guide did not explain the relationship between literal evidence span, uncertainty cue, normalized value, and certainty attribute.
- **Suggested fix:** Add the exact mapping and example above to the guide. Use the full evidential phrase as the span, store the normalized concept separately in `value`, and map uncertainty language to `certainty` consistently.
- **Effort:** low.
- **Confidence:** high.

### [D-03] `review_priority` is undefined and needs scientific-priority criteria

- **Reported by:** Priya Gokuldass; Sarah.
- **Layer / label:** Document/event-level review metadata (`review_priority`).
- **Symptom:** Annotators do not know whether `review_priority` means scientific importance, annotation urgency, or quality-control priority, and the guide lacks examples of what should increase or decrease it.
- **Evidence:** Priya explicitly wrote: **“review_priority is not defined in the annotation guide.”** Carlos clarified that it is **scientific review priority**, based on scientific value or doubts in the data, and **not** annotation urgency or QC priority. Sarah later added practical scientific criteria: multiple gamma triggering systems alone **do not** increase the level of interest; a **more precise localization does**; a **radio counterpart increases importance** because more physics can be done; prompt-emission properties such as Fermi/GBM `Epeak` are interesting but **second order** for immediate follow-up strategy.
- **Likely cause:** The field existed without a decision rubric.
- **Suggested fix:** Add a short rubric with positive and negative examples drawn directly from Sarah's comments. Keep “scientific review priority” distinct from workflow urgency and annotation QC. If the field is meant to support follow-up strategy rather than general scientific interest, state that explicitly.
- **Effort:** low.
- **Confidence:** high.

### [D-04] The purpose of `EVENT_SUMMARY` and the annotator completion workflow are insufficiently explained

- **Reported by:** Yodgor.
- **Layer / label:** `EVENT_SUMMARY` plus manual correction workflow across layers.
- **Symptom:** An annotator may interpret the task as only checking existing pre-annotations and may not realize that missing scientifically important information must also be added manually.
- **Evidence:** Yodgor wrote **“EVENT_SUMMARY unclear to me?”** and later asked whether the task was simply to **“Check the all tags which (your) tool grabbed and complete the summary section.”** Carlos clarified that the summary should contain the most relevant event information and that **“if important scientific information has not been annotated, you must create the annotation.”**
- **Likely cause:** The guide focuses on the fields/layers but not enough on the end-to-end validation objective.
- **Suggested fix:** Add an explicit workflow: (1) inspect every pre-annotation, (2) correct wrong labels/fields, (3) create missing scientifically important annotations, and (4) complete `EVENT_SUMMARY` using the best validated information. Include a short definition of what the summary is for.
- **Effort:** low.
- **Confidence:** high.

### [D-05] Photometric-system inference/default rules are not documented

- **Reported by:** Sarah.
- **Layer / label:** `PHOTOMETRIC_MEASUREMENT → photometric_system`.
- **Symptom:** When AB/Vega is not explicitly stated, different annotators may infer the system differently or leave it empty even when the observing/calibration context provides a convention.
- **Evidence:** Across Sarah's events, she supplied several conventions: calibration against **SDSS** implies AB; calibration around **PS1 / Pan-STARRS** implies AB; **LCO** data are AB even when not stated; Russian `.ru` reports often omit the system and Sarah says they are traditionally treated as **Vega**; capital `R`, `V`, etc. are generally Vega unless the text indicates an AB calibration such as SDSS. In `2026owq`, she initially also said that AB is commonly the default, showing why the guide needs one reconciled rule rather than relying on memory.
- **Likely cause:** The schema has a `photometric_system` field, but the guide does not distinguish explicit extraction from expert inference/default conventions.
- **Suggested fix:** Create a documented decision table with three states of evidence: explicit system in text; system inferred from calibration/instrument convention; unknown. Reconcile Sarah's broad “default AB” comment with her later source-specific rules before implementing automatic defaults. Record inferred values as inferred if the schema supports provenance, rather than presenting them as explicitly reported.
- **Effort:** low.
- **Confidence:** high.

### [D-06] Equivalent/similar photometric filters need a normalization policy

- **Reported by:** Sarah.
- **Layer / label:** `PHOTOMETRIC_MEASUREMENT → photometric_band`.
- **Symptom:** Closely related filters are represented under different names, fragmenting the light curve and making downstream follow-up reasoning less coherent.
- **Evidence:** Sarah proposed several mappings across her events: `VT_B` as a Gaia-blue-like channel; `Gaia BP` to be transformed/grouped with **Bessel B**; **GOTO-L** to be treated with **L / clear**, and later grouped with **clear / V-band / no filter** for downstream light-curve use; **Swift/UVOT white** as effectively **clear** / no conventional filter. She explicitly explained that similar filters should be grouped so the light curve is not split into one point per near-equivalent band.
- **Likely cause:** The guide describes the extracted band value but not a canonical normalization layer for downstream use.
- **Suggested fix:** Define a curated normalization map separate from the raw extracted `photometric_band`. Preserve the original reported filter for traceability and store/use a normalized family only after Sarah/team validation. Do not silently overwrite raw values because some equivalences are approximate rather than exact.
- **Effort:** low.
- **Confidence:** high.

### [D-07] Multiple magnitudes in one sentence must be annotated as separate detections

- **Reported by:** Priya Gokuldass; resolved by Carlos.
- **Layer / label:** `PHOTOMETRIC_MEASUREMENT`.
- **Symptom:** Annotators may treat a sentence containing several magnitudes as one summary statement instead of several measurements.
- **Evidence:** Priya asked about GCN 37993, where a single sentence reports **three ATLAS magnitudes**. Carlos answered: **“each one is a separate DETECTION (one per measurement, even in the same sentence), as long as they're distinct bands or epochs. So three ATLAS magnitudes → three detections.”**
- **Likely cause:** The guide does not define the unit of annotation when several observations share a sentence.
- **Suggested fix:** State explicitly that the annotation unit is the individual measurement, not the sentence. Add the GCN 37993 three-ATLAS-magnitudes case as the guide example.
- **Effort:** low.
- **Confidence:** high.

### [D-08] Inclusion/exclusion rules for MASTER, amateur data, and GRANDMA-internal/duplicate reports are not formalized

- **Reported by:** Sarah; Patrice.
- **Layer / label:** Corpus scope and follow-up-strategy inputs; not an extractor-label bug.
- **Symptom:** Annotators encounter observations that may be scientifically real but should not necessarily influence the follow-up strategy or remain in the same GCN-derived dataset, and the scope policy is not written down.
- **Evidence:** Sarah repeatedly said **MASTER** should be ignored for follow-up strategy; Patrice independently questioned including MASTER because of very shallow **“upper limits à 8 mag,”** and Sarah agreed. Sarah also said **AAVSO** amateur data should be ignored and that **“Using AstroImageJ”** identifies amateur data to ignore. For GRANDMA-related data, she said `NUTTelA-TAO` is a GRANDMA telescope and does not need another report, `Maidanak Observatory` should be ignored as GRANDMA data in that context, and earlier said unreferenced GRANDMA circulars should be removed from the GCN dataset.
- **Likely cause:** Corpus inclusion and follow-up relevance were handled as expert conventions rather than explicit annotation rules.
- **Suggested fix:** Add a source/scope policy table to the guide. Separate at least three decisions: (1) whether data remain in the raw corpus, (2) whether they are annotated, and (3) whether they contribute to follow-up strategy. Do not collapse Sarah's “ignore for strategy” comments into “delete from corpus” unless the team explicitly confirms that stronger rule.
- **Effort:** low.
- **Confidence:** high.

### [D-09] Host/galaxy photometry must be distinguished from transient photometry

- **Reported by:** Sarah.
- **Layer / label:** `PHOTOMETRIC_MEASUREMENT`; scope/target interpretation.
- **Symptom:** Photometry reported for a galaxy can be mistaken for photometry of the transient if the guide does not force annotators/extractor rules to resolve the measurement target.
- **Evidence:** In `GCN-260604_202037`, Sarah warned: **“Colibri reported the galaxy photometry (not to confused with the transient photometry).”**
- **Likely cause:** The measurement layer centers on photometric values and may not make target identity explicit enough in the annotation decision process.
- **Suggested fix:** Add a guide rule that `PHOTOMETRIC_MEASUREMENT` intended for the transient must not absorb host/galaxy measurements unless the schema explicitly supports and marks a different target. Use the Colibri case as a negative example when validating V2 extraction rules.
- **Effort:** low.
- **Confidence:** low.

### [D-10] `CLASSIFICATION_INTERPRETATION` needs clearer examples for manual annotation

- **Reported by:** Sarah.
- **Layer / label:** `ASTRO_EVIDENCE → CLASSIFICATION_INTERPRETATION`.
- **Symptom:** An annotator can recognize that a statement is an astrophysical interpretation (for example, a supernova interpretation) but still be unsure which available layer/label should be used.
- **Evidence:** In event `2026owq`, Sarah said she did not know how to annotate the interpretation because she only had access to the photometric and evidence layers and referred to a case involving **supernova** interpretation. In a later event she explicitly said the SN1998bw-like sentence should have been tagged, providing a concrete interpretation example.
- **Likely cause:** The guide lists `CLASSIFICATION_INTERPRETATION` but does not give enough positive examples or explain that such interpretations belong in `ASTRO_EVIDENCE`.
- **Suggested fix:** Add examples showing direct, tentative, and comparative classification interpretations under `CLASSIFICATION_INTERPRETATION`, including the SN1998bw-like example. Cross-reference the certainty convention from [D-02].
- **Effort:** low.
- **Confidence:** low.

### [D-11] Photometric uncertainty placement and span-editing rules are unclear

- **Reported by:** Priya Gokuldass; resolved by Carlos.
- **Layer / label:** `PHOTOMETRIC_MEASUREMENT`; span editing and `magnitude_error`.
- **Symptom:** Annotators may try to enlarge, delete, or recreate a photometry span to include uncertainty when the intended correction is only to populate an attribute.
- **Evidence:** While reviewing GRB 241030A, GCN 38035, Priya asked whether she should extend an existing photometry annotation to include the uncertainty and whether spans could be edited. Carlos clarified that incorrect spans can be adjusted in INCEpTION, but **“the uncertainty of a photometry point goes in the magnitude_error field, not in the span”** and therefore she likely did not need to extend the span for that case.
- **Likely cause:** The guide does not clearly distinguish evidence-span boundaries from structured measurement attributes or explain how to correct spans in INCEpTION.
- **Suggested fix:** Add one small workflow example: when the evidence span itself is wrong, drag the annotation edge; when the span is correct but magnitude uncertainty is missing, keep the span and populate `magnitude_error`. This prevents unnecessary delete/recreate operations and inconsistent spans.
- **Effort:** low.
- **Confidence:** high.

---

# Open questions preserved from Slack

These points were raised by annotators but were **not resolved clearly enough in the Slack material to classify them as a confirmed A/B/C/D correction without making assumptions**. They should be reviewed before V2 so the information is not lost.

### [OPEN-01] General representation of follow-up instruments and observation start time

Priya noted that the guide tells annotators to mark the trigger instrument but not, in her words, **“the instruments that followed up or the observation start time.”** The subsequent Slack response addressed multiple trigger instruments but did not directly resolve whether a separate general follow-up-instrument representation is needed or whether existing photometric fields are considered sufficient.

### [OPEN-03] Time-lag unit handling across hours, days, and minutes

In event `2026owq`, Sarah observed that lag values appear in **hours, days, or minutes** and said she did not know whether the system handled all of them correctly. This is a validation request, not a confirmed bug. V2 testing should explicitly include all three units before deciding whether a rule change is required.

### [OPEN-04] Cross-circular references and externally referenced photometry

Sarah noted two related situations: circulars may refer to another GCN to identify which counterpart/localization is being discussed, and one report apparently did not repeat its photometric points but referred elsewhere. She suggested that querying and re-extracting referenced data might become complicated and said to **“garder en mémoire ça.”** Slack does not decide whether V2 should add provenance relations, automatically follow GCN references, or leave this as contextual information only.

---

# Summary table — ordered by expected implementation yield

The ordering below prioritizes recurrent issues affecting many measurements, then low-effort high-value consistency fixes, followed by narrower rule fixes and larger schema changes.

| ID | Category | Layer | Effort | Confidence |
|---|---|---|---|---|
| A-01 | A. Rule fix | `PHOTOMETRIC_MEASUREMENT` | medium | high |
| B-05 | B. Field population | `PHOTOMETRIC_MEASUREMENT.photometric_system` | low | high |
| B-08 | B. Field population | `PHOTOMETRIC_MEASUREMENT.photometric_band` | low | high |
| B-06 | B. Field population | `PHOTOMETRIC_MEASUREMENT.instrument` | medium | high |
| B-01 | B. Field population | `PHOTOMETRIC_MEASUREMENT` time fields | medium | high |
| B-07 | B. Field population | `PHOTOMETRIC_MEASUREMENT.magnitude_error` | low | high |
| A-02 | A. Rule fix | `PHOTOMETRIC_MEASUREMENT` | medium | high |
| A-10 | A. Rule fix | `TRIGGER_INSTRUMENT` | medium | high |
| A-11 | A. Rule fix | `TRIGGER_TIME` | medium | high |
| A-12 | A. Rule fix | `NEGATIVE_STATEMENT` | low | high |
| A-04 | A. Rule fix | Radio measurement + `COUNTERPART_ASSOCIATION` | medium | high |
| D-05 | D. Guide gap | `photometric_system` policy | low | high |
| D-06 | D. Guide gap | `photometric_band` normalization | low | high |
| D-07 | D. Guide gap | `PHOTOMETRIC_MEASUREMENT` annotation unit | low | high |
| D-01 | D. Guide gap | `EVENT_SUMMARY` trigger-time fields | low | high |
| D-03 | D. Guide gap | `review_priority` | low | high |
| D-04 | D. Guide gap | `EVENT_SUMMARY` / validation workflow | low | high |
| D-02 | D. Guide gap | `ASTRO_EVIDENCE` certainty/value/span | low | high |
| D-11 | D. Guide gap | Photometry span + `magnitude_error` | low | high |
| D-08 | D. Guide gap | Corpus/follow-up scope | low | high |
| C-05 | C. Schema gap | `T90` / event metadata | medium | high |
| C-01 | C. Schema gap | `TRIGGER_INSTRUMENT` | medium | high |
| C-02 | C. Schema gap | X-ray measurements | high | high |
| A-07 | A. Rule fix | `REDSHIFT_EVENT` vs `REDSHIFT_CONTEXT` | low | high |
| A-08 | A. Rule fix | Redshift false positives | low | low |
| A-09 | A. Rule fix | `CLASSIFICATION_INTERPRETATION` | low | low |
| A-03 | A. Rule fix | Photometric evolution phrasing | low | low |
| B-03 | B. Field population | `obs_time_raw` | low | low |
| B-04 | B. Field population | `TRIGGER_TIME` value | low | low |
| B-02 | B. Field population | Photometric mid-time | medium | low |
| A-05 | A. Rule fix | `LOCALIZATION` | medium | low |
| A-06 | A. Rule fix | High-energy instrument/modality context | medium | low |
| D-09 | D. Guide gap | Galaxy vs transient photometry | low | low |
| D-10 | D. Guide gap | `CLASSIFICATION_INTERPRETATION` guidance | low | low |
| C-03 | C. Schema gap | Galactic-extinction correction | medium | low |
| C-04 | C. Schema gap | `LIGHTCURVE_EVOLUTION` epoch | medium | low |
| C-06 | C. Schema gap | Localization relations | high | low |

---

## Recommended V2 implementation sequence

This section is not a new source of requirements; it only orders the Slack-derived corrections above into a practical implementation sequence.

1. **Fix recurrent photometry field population first:** `photometric_system`, `photometric_band`, `instrument`, observation-time semantics, and `magnitude_error`.
2. **Improve photometry recall using the corrected annotations as regression tests:** especially compact/tabular syntax and cases where several measurements are reported together.
3. **Fix trigger-versus-follow-up context and conditional-negative false positives:** implement [A-10] and [A-11] together because both require a governing-clause test before assigning trigger labels; then apply the low-effort conditional/hypothetical gate in [A-12]. These are among the best-supported V2 corrections because they are backed by validated-corpus corrections in addition to annotator feedback.
4. **Fix repeated modality-specific misses:** radio is the clearest recurrent example across multiple Sarah events.
5. **Apply narrow high-confidence classification guards:** GRB redshift referent logic and color expressions such as `g-z`/`r-z` should not be conflated.
6. **Update the annotation guide in parallel:** trigger-time adjudication, uncertainty/certainty conventions, `review_priority`, `EVENT_SUMMARY`, photometric-system inference, filter normalization, scope rules, and multiple-measurement annotation should be written down before the next annotation round.
7. **Handle schema extensions only after the low-cost rule/guide fixes are stable:** X-ray measurements, primary trigger designation, T90-by-energy-band, extinction status, light-curve evolution epoch, and localization relations require explicit schema decisions rather than regex-only changes.
8. **Resolve the three remaining open questions before freezing V2:** general representation of follow-up instruments/observation start time, lag-unit handling, and cross-circular reference/provenance behavior.
