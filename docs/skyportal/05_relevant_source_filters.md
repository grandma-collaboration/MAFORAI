# Relevant `/api/sources` Filters

This document summarizes the `/api/sources` query parameters that are the most
useful for building targeted inventories before a deeper source-level
extraction.

The point is not to list every possible filter. It is to keep the practical
ones together in one place.

## 1. Filters already used in the current workflow

The following filters are already part of the documented inventory profiles.

| Profile | Main filter | Why it is useful | Observed result |
|---|---|---|---:|
| `has_spectrum` | `hasSpectrum=true` | Select sources with at least one spectrum | 60 |
| `has_followup` | `hasFollowupRequest=true` | Select sources with at least one follow-up request | 370 |
| `classified` | `classified=true` | Select classified sources | 834 |
| `redshift` | `minRedshift=0.0001` | Select sources with positive redshift | 51 |
| `many_detections` | `numberDetections=5` | Select sources with broader photometric coverage | 71 |
| `gcn` | `sourceID=GCN` | Select GCN-like sources by ID pattern | 144 |
| `ep` | `sourceID=EP` | Select EP-like sources by ID pattern | 193 |

## 2. Response-enrichment flags

These parameters do not necessarily filter sources. They enrich the source rows
returned by `/api/sources`.

| Parameter | Why it is useful |
|---|---|
| `includePhotometryExists=true` | Quickly tells us whether photometry exists |
| `includeSpectrumExists=true` | Quickly tells us whether spectra exist |
| `includeCommentExists=true` | Quickly tells us whether comments exist |
| `includeDetectionStats=true` | Adds compact detection-level statistics |
| `includeHosts=true` | Adds host information when available |
| `includeLabellers=true` | Adds user-labelling information |
| `includeColorMagnitude=true` | Adds Gaia color-magnitude information when available |
| `includeThumbnails=true` | Adds thumbnail metadata |
| `includeComments=true` | Includes comment metadata directly in the inventory response |

The shared profile template currently uses:

```text
includePhotometryExists=true
includeSpectrumExists=true
includeCommentExists=true
includeDetectionStats=true
sortBy=saved_at
sortOrder=desc
```

## 3. Identity and naming filters

These are useful when the source naming convention already tells us something
about the subset we want.

| Parameter | Typical use |
|---|---|
| `sourceID` | Match a portion of the source ID or TNS name, for example `GCN`, `EP`, `SN`, or a specific object ID |
| `rejectedSourceIDs` | Exclude specific object IDs from a query |
| `origin` | Restrict to the source origin or posting origin |
| `hasTNSname=true` | Keep only sources with a TNS name |
| `simbadClass` | Filter by SIMBAD class when available |

Examples:

```bash
--query-param sourceID=GCN
--query-param sourceID=EP
--query-param hasTNSname=true
```

## 4. Time, sorting, and pagination

These parameters matter because inventories are usually either recent slices or
time-bounded subsets.

| Parameter | Typical use |
|---|---|
| `numPerPage` | Number of sources per page |
| `pageNumber` | Page index to retrieve |
| `sortBy` | Sort field such as `saved_at`, `id`, `ra`, `dec`, or `redshift` |
| `sortOrder` | `asc` or `desc` |
| `startDate` | Filter by first detected date |
| `endDate` | Filter by last detected date |
| `savedAfter` | Filter by source save time |
| `savedBefore` | Filter by source save time |
| `createdOrModifiedAfter` | Filter by source creation or update time |

Typical recent-slice pattern:

```bash
--query-param sortBy=saved_at
--query-param sortOrder=desc
```

## 5. Science-content filters

These are the filters that most directly control which kinds of sources end up
in an inventory.

| Parameter | Why it is useful |
|---|---|
| `hasSpectrum=true` | Builds multimodal subsets with spectroscopy |
| `hasFollowupRequest=true` | Selects sources with explicit follow-up activity |
| `classified=true` | Builds labelled subsets |
| `unclassified=true` | Builds unlabeled subsets |
| `minRedshift` / `maxRedshift` | Selects astrophysically meaningful distance ranges |
| `numberDetections` | Selects sources with richer photometric coverage |

Examples:

```bash
--query-param hasSpectrum=true
--query-param hasFollowupRequest=true
--query-param classified=true
--query-param minRedshift=0.0001
--query-param numberDetections=5
```

## 6. Classification filters

When a simple `classified=true` is not enough, `/api/sources` also supports
more specific classification filters.

| Parameter | Typical use |
|---|---|
| `classifications` | Match one or more taxonomy/classification pairs |
| `classifications_simul=true` | Require all requested classifications instead of any one of them |
| `nonclassifications` | Exclude sources matching selected classification pairs |
| `hasBeenLabelled=true` | Keep sources that were labelled |
| `hasNotBeenLabelled=true` | Keep sources that were not labelled |

Examples:

```bash
--query-param classified=true
--query-param "classifications=Sitewide Taxonomy: Type II"
--query-param classifications_simul=true
```

The exact taxonomy and class names should be checked against:

```text
GET /api/taxonomy
GET /api/config
```

## 7. Comment and annotation filters

These are particularly relevant if the later corpus needs human reasoning,
discussion, or derived metadata.

### Comments

| Parameter | Typical use |
|---|---|
| `includeCommentExists=true` | Add a comment-presence flag |
| `includeComments=true` | Include comment metadata in the inventory response |
| `commentsFilter` | Search comments by text |
| `commentsFilterAuthor` | Restrict comment search to selected authors |
| `commentsFilterBefore` | Keep comments before a given UTC datetime |
| `commentsFilterAfter` | Keep comments after a given UTC datetime |

Examples:

```bash
--query-param includeCommentExists=true
--query-param commentsFilter=follow-up
--query-param commentsFilterAfter=2026-05-01T00:00:00
```

### Annotations

| Parameter | Typical use |
|---|---|
| `annotationsFilter` | Filter sources by annotation triplets such as `annotation: value: operator` |
| `annotationsFilterOrigin` | Restrict annotation filtering to selected origins |

Example:

```bash
--query-param "annotationsFilter=redshift: 0.5: lt"
```

## 8. Group, list, and follow-up context

These are useful when the subset is tied to a workflow or collaboration rather
than to pure astrophysical properties.

| Parameter | Typical use |
|---|---|
| `group_ids` | Restrict to one or more groups |
| `listName` | Restrict to a saved user list such as `favorites` |
| `followupRequestStatus` | Restrict by follow-up request status |

Examples:

```bash
--query-param group_ids=2
--query-param listName=favorites
--query-param followupRequestStatus=submitted
```

The exact allowed values for `followupRequestStatus` should be verified from
the instance data before turning that into a shared profile.

## 9. Practical rule

For this project, a filter is worth promoting to a named profile when it meets
at least one of these conditions:

- it is scientifically meaningful;
- it is likely to be reused;
- it produces a subset clearly different from the existing ones;
- the command is long enough that keeping it only on the CLI becomes tedious.
