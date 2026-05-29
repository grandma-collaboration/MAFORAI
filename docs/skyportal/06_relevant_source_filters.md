# Relevant `/api/sources` Filters

This document summarizes the `/api/sources` query parameters that are relevant for selecting sources before extracting complete source bundles.


## 1. Why `/api/sources` filters matter

`GET /api/sources` is the main inventory endpoint. It allows us to search and retrieve sources using filters before downloading complete source-level data.

This is important because the SkyPortal database contains many sources. Instead of downloading everything, we can create targeted inventories such as:

* sources with spectra;
* sources with follow-up requests;
* classified sources;
* sources with redshift;
* sources with several detections;
* GCN-like sources;
* EP-like sources;
* sources with comments;
* sources with annotations;
* sources inside a localization region.

These filtered inventories are used to select representative events for deeper source-bundle extraction.

---

## 2. Filters already used in the current audit

The following filters were already tested and used to create complete inventories.

| Inventory label   | Filter                    | Purpose                                               | Current result |
| ----------------- | ------------------------- | ----------------------------------------------------- | -------------: |
| `has_spectrum`    | `hasSpectrum=true`        | Select sources with at least one associated spectrum. |             60 |
| `has_followup`    | `hasFollowupRequest=true` | Select sources with at least one follow-up request.   |            370 |
| `classified`      | `classified=true`         | Select sources with classifications.                  |            834 |
| `redshift`        | `minRedshift=0.0001`      | Select sources with a positive redshift.              |             51 |
| `many_detections` | `numberDetections=5`      | Select sources with at least 5 detections.            |             71 |
| `gcn`             | `sourceID=GCN`            | Select GCN-like sources based on their source ID.     |            144 |
| `ep`              | `sourceID=EP`             | Select EP-like sources based on their source ID.      |            193 |

All these inventories were fully downloaded and reached:

```text
api_total_matches_reached
```

---

## 3. Common include flags

These parameters do not necessarily filter sources. Instead, they enrich the response returned by `/api/sources`.

They are useful for deciding which sources should be selected for deeper extraction.

| Parameter                      | Type    | Why it is useful                                                                                                                                                                           |
| ------------------------------ | ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `includePhotometryExists=true` | boolean | Adds information about whether the source has photometry. Useful before downloading complete light curves.                                                                                 |
| `includeSpectrumExists=true`   | boolean | Adds information about whether the source has spectra. Useful for multimodal source selection.                                                                                             |
| `includeCommentExists=true`    | boolean | Adds information about whether the source has comments. Useful for LLM/human reasoning analysis.                                                                                           |
| `includeDetectionStats=true`   | boolean | Adds detection statistics such as last detection and peak detection. Useful for selecting sources with meaningful light-curve coverage.                                                    |
| `includeHosts=true`            | boolean | Includes host-galaxy information when available. Useful for extragalactic context.                                                                                                         |
| `includeLabellers=true`        | boolean | Includes users who labelled the source. Potentially useful for classification provenance.                                                                                                  |
| `includeColorMagnitude=true`   | boolean | Includes Gaia color-magnitude data when available through annotations. Useful for star/galaxy or variable/transient separation.                                                            |
| `includeThumbnails=true`       | boolean | Includes associated thumbnails. Useful later for visual/multimodal exploration.                                                                                                            |
| `includeComments=true`         | boolean | Includes comment metadata in the response. Potentially useful. |

Recommended default include flags for inventory extraction:

```bash
--query-param includePhotometryExists=true
--query-param includeSpectrumExists=true
--query-param includeCommentExists=true
--query-param includeDetectionStats=true
```

Optional include flags depending on the analysis:

```bash
--query-param includeHosts=true
--query-param includeLabellers=true
--query-param includeColorMagnitude=true
--query-param includeThumbnails=true
```

---

## 4. Identity and source-name filters

These filters are useful to search for specific sources or source families.

| Parameter           | Type    | Use case                                                                                                                 |
| ------------------- | ------- | ------------------------------------------------------------------------------------------------------------------------ |
| `sourceID`          | string  | Filter by a portion of the source ID or TNS name. Useful for `GCN`, `EP`, `ZTF`, `AT`, `SN`, or a specific object ID.    |
| `rejectedSourceIDs` | string  | Comma-separated object IDs to exclude from a query. Useful when searching for new sources that are not already selected. |                                                                       |
| `origin`            | string  | Filter by who posted or discovered the source.                                                                           |
| `hasTNSname=true`   | boolean | Select only sources with TNS names. Useful for externally reported/official transients.                                  |
| `simbadClass`       | string  | Filter by SIMBAD class. Useful for separating stars, galaxies, AGN, variables, etc., when available.                     |

Examples:

```bash
--query-param sourceID=GCN
--query-param sourceID=EP
--query-param sourceID=SN
--query-param hasTNSname=true
```

Project relevance:

* `sourceID=GCN` helps select GCN-like or multimessenger-like sources.
* `sourceID=EP` helps select EP-like high-energy event sources.
* `hasTNSname=true` helps select sources reported to TNS.
* `simbadClass` may be useful later for crossmatch-based filtering.

---

## 5. Pagination and sorting

These parameters control how many sources are returned and in which order.

| Parameter    | Type    | Use case                                                                                  |
| ------------ | ------- | ----------------------------------------------------------------------------------------- |
| `numPerPage` | integer | Number of sources per page. Default is 100. Maximum is 500.                               |
| `pageNumber` | integer | Page number to retrieve.                                                                  |
| `sortBy`     | string  | Field used for sorting. Allowed values include `id`, `ra`, `dec`, `redshift`, `saved_at`. |
| `sortOrder`  | string  | Sorting order: `asc` or `desc`.                                                           |

Recommended sorting for recent inventories:

```bash
--query-param sortBy=saved_at
--query-param sortOrder=desc
```

This helps retrieve recently saved sources first.

---

## 6. Date and time filters

These filters are important for creating time-bounded inventories.

| Parameter                | Type   | Meaning                                                     |
| ------------------------ | ------ | ----------------------------------------------------------- |
| `startDate`              | string | Filters by `PhotStat.first_detected_mjd >= startDate`.      |
| `endDate`                | string | Filters by `PhotStat.last_detected_mjd <= endDate`.         |
| `savedAfter`             | string | Returns sources saved after a UTC datetime.                 |
| `savedBefore`            | string | Returns sources saved before a UTC datetime.                |
| `createdOrModifiedAfter` | string | Returns sources created or modified after a datetime.       |

Examples:

```bash
--query-param startDate=2026-05-01
--query-param endDate=2026-05-28
--query-param savedAfter=2026-05-01T00:00:00
--query-param createdOrModifiedAfter=2026-05-01T00:00:00
```

Project relevance:

* `startDate` / `endDate` are useful for selecting events detected in a scientific time window.
* `savedAfter` / `savedBefore` are useful for reproducing source-save periods.
* `createdOrModifiedAfter` is useful for finding recently updated sources.


---

## 7. Group and list filters

These filters are useful for selecting sources associated with specific observing programs, teams, or lists.

| Parameter          | Type             | Use case                                                                    |
| ------------------ | ---------------- | --------------------------------------------------------------------------- |
| `group_ids`        | list of integers | Filter sources saved to one of the provided group IDs.                      |
| `listName`         | string           | Return only sources saved to the querying user's list, such as `favorites`. |

Examples:

```bash
--query-param group_ids=2
--query-param listName=favorites
```

Project relevance:

* `group_ids` may be important if we want to focus on a specific scientific group or collaboration.

---

## 8. Classification filters

These filters are essential for selecting labelled and unlabelled sources.

| Parameter                    | Type         | Use case                                                         |
| ---------------------------- | ------------ | ---------------------------------------------------------------- |
| `classified=true`            | boolean      | Select sources with at least one classification.                 |
| `unclassified=true`          | boolean      | Select sources without classifications.                          |
| `classifications`            | array/string | Select sources matching specific taxonomy/classification pairs.  |
| `classifications_simul=true` | boolean      | Require all requested classifications instead of any of them.    |
| `nonclassifications`         | array/string | Exclude sources matching specific taxonomy/classification pairs. |
| `hasBeenLabelled=true`       | boolean      | Select objects that have been labelled.                          |
| `hasNotBeenLabelled=true`    | boolean      | Select objects that have not been labelled.                      |

Examples:

```bash
--query-param classified=true
--query-param unclassified=true
--query-param "classifications=Sitewide Taxonomy: Type II"
--query-param "classifications=Sitewide Taxonomy: Type II,Sitewide Taxonomy: AGN"
--query-param classifications_simul=true
```

Project relevance:

* `classified=true` is useful for building labelled subsets.
* `unclassified=true` is useful for identifying sources where a decision-support assistant could help.
* `classifications` can be used later to select specific science classes such as supernovae, AGN, kilonova candidates, GRB afterglows, etc., depending on the taxonomy available in the instance.
* `nonclassifications` can help create negative or contrast sets.

Important note:

Specific classification filters require knowing the exact taxonomy and class names. These should be checked using:

(TODO)
```text
GET /api/taxonomy
GET /api/config
```
---

## 9. Comment filters

Comments are important for the LLM part of the project because they may contain human reasoning, uncertainty, follow-up decisions, urgency, and scientific discussion.

| Parameter                   | Type         | Use case                                                |
| --------------------------- | ------------ | ------------------------------------------------------- |
| `includeCommentExists=true` | boolean      | Adds a flag indicating whether the source has comments. |
| `includeComments=true`      | boolean      | Includes comment metadata in the inventory response.    |
| `commentsFilter`            | array/string | Select sources with comments matching a text query.     |
| `commentsFilterAuthor`      | string       | Restrict comment filtering to selected authors.         |
| `commentsFilterBefore`      | string       | Select sources with comments before a UTC datetime.     |
| `commentsFilterAfter`       | string       | Select sources with comments after a UTC datetime.      |

Examples:

```bash
--query-param includeCommentExists=true
--query-param includeComments=true
--query-param commentsFilter=GRB
--query-param commentsFilter=follow-up
--query-param commentsFilterAfter=2026-05-01T00:00:00
```

Project relevance:

* `includeCommentExists=true` should be used in inventories to identify sources with comments.
* `commentsFilter` may help find sources where humans discussed specific concepts such as `GRB`, `kilonova`, `follow-up`, `redshift`, `host`, or `candidate`.


---

## 10. Annotation filters

Annotations may contain automatic metrics, broker outputs, crossmatches, scores, or derived information.

| Parameter                 | Type         | Use case                                                                               |
| ------------------------- | ------------ | -------------------------------------------------------------------------------------- |
| `annotationsFilter`       | array/string | Filter sources matching annotation triplets of the form `annotation: value: operator`. |
| `annotationsFilterOrigin` | string       | Restrict annotation filtering to specific annotation origins.                          |

Example from the API documentation:

```bash
--query-param "annotationsFilter=redshift: 0.5: lt"
```

Possible future examples:

```bash
--query-param annotationsFilterOrigin=broker_name
```

Project relevance:

* Auto-annotations are potentially very useful for the corpus.
* They may contain automatic classification scores, broker metadata, crossmatches, or derived metrics.


---

## 11. Redshift and magnitude filters

These filters are useful for selecting astrophysically meaningful subsets.

| Parameter            | Type   | Use case                                                          |
| -------------------- | ------ | ----------------------------------------------------------------- |
| `minRedshift`        | number | Select sources with redshift greater than or equal to this value. |
| `maxRedshift`        | number | Select sources with redshift lower than or equal to this value.   |
| `numberDetections`   | number | Select sources with at least this number of detections.           |

Examples:

```bash
--query-param minRedshift=0.0001
--query-param maxRedshift=0.5
--query-param numberDetections=5
--query-param numberDetections=10
```

Project relevance:

* `minRedshift=0.0001` is useful for selecting sources with positive redshift.
* `numberDetections=5` is useful for selecting sources with enough photometric coverage.

---

## 12. Spectroscopy filters

These filters are important for multimodal event selection.

| Parameter                    | Type    | Use case                                                 |
| ---------------------------- | ------- | -------------------------------------------------------- |
| `hasSpectrum=true`           | boolean | Select sources with at least one associated spectrum.    |
| `includeSpectrumExists=true` | boolean | Adds a flag indicating whether spectra exist.            |

Examples:

```bash
--query-param hasSpectrum=true
--query-param includeSpectrumExists=true
```

Project relevance:

* Spectra are important for multimodal source characterization.
* Sources with spectra are useful for building high-information event examples.

---

## 13. Follow-up filters

Follow-up filters are important because the project is related to decision support.

| Parameter                 | Type    | Use case                                            |
| ------------------------- | ------- | --------------------------------------------------- |
| `hasFollowupRequest=true` | boolean | Select sources with at least one follow-up request. |
| `followupRequestStatus`   | string  | Select follow-up requests matching a given status.  |

Examples:

```bash
--query-param hasFollowupRequest=true
--query-param followupRequestStatus=submitted
--query-param followupRequestStatus=completed
```

Project relevance:

* They are good candidates for LLM summarization and urgency extraction.

(TODO)
The exact values of `followupRequestStatus` should be verified from the actual data.

---
