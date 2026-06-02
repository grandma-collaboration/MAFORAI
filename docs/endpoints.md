# SkyPortal Endpoints

This document is the broad endpoint catalog for the current SkyPortal study.
It is wider than the scripts we use today: not every endpoint listed here is
already part of the workflow, but each one matters when thinking about a later
source-bundle extractor.

## How to read this list

The priority column is only a working guide:

- lower numbers are more relevant for the current phase;
- higher numbers are still useful, but usually for later expansion or for
  context around the main source data.

## 1. Source inventory and identity

| Priority | Endpoint | What it gives us |
|---:|---|---|
| 1 | `GET /api/sources` | Main inventory endpoint. Supports filters such as date, `sourceID`, `group_ids`, classification, redshift, spectra, follow-up, comments, annotations, and more. |
| 2 | `GET /api/sources/{obj_id}` | Full source record for one object. |
| 3 | `GET /api/candidates` | Candidate list, usually before a source is saved. |
| 4 | `GET /api/candidates/{obj_id}` | Detail for one candidate. |
| 5 | `GET /api/source_exists/{obj_id}` | Quick existence check for one object ID. |

## 2. Photometry

| Priority | Endpoint | What it gives us |
|---:|---|---|
| 6 | `GET /api/sources/{obj_id}/photometry` | Photometric points for a source. |
| 7 | `GET /api/sources/{obj_id}/phot_stat` | Compact photometric statistics. |
| 8 | `GET /api/photometry/{photometry_id}` | Detail for one photometry record. |
| 9 | `GET /api/photometry/range` | Photometry filtered by range or query conditions. |
| 10 | `GET /api/photometric_series/{photometric_series_id}` | Detail for one photometric series. |

## 3. Spectroscopy

| Priority | Endpoint | What it gives us |
|---:|---|---|
| 11 | `GET /api/sources/{obj_id}/spectra` | Spectra associated with a source. |
| 12 | `GET /api/spectrum/{spectrum_id}` | Detail for one spectrum. |
| 13 | `GET /api/spectrum` | Global spectrum list. |
| 14 | `GET /api/spectrum/range` | Spectra filtered by range or query conditions. |

## 4. Classifications and taxonomies

| Priority | Endpoint | What it gives us |
|---:|---|---|
| 15 | `GET /api/sources/{obj_id}/classifications` | Classifications attached to a source. |
| 16 | `GET /api/classification/{classification_id}` | Detail for one classification. |
| 17 | `GET /api/classification` | Global classification list. |
| 18 | `GET /api/taxonomy` | Available taxonomies. |
| 19 | `GET /api/taxonomy/{taxonomy_id}` | Detail for one taxonomy. |

## 5. Comments, annotations, and tags

| Priority | Endpoint | What it gives us |
|---:|---|---|
| 20 | `GET /api/{associated_resource_type}/{resource_id}/comments` | Comments attached to a source or other resource. |
| 21 | `GET /api/{associated_resource_type}/{resource_id}/comments/{comment_id}` | Detail for one comment. |
| 22 | `GET /api/{associated_resource_type}/{resource_id}/annotations` | Annotations attached to a resource. |
| 23 | `GET /api/{associated_resource_type}/{resource_id}/annotations/{annotation_id}` | Detail for one annotation. |
| 24 | `GET /api/objtag` | Object tags currently in use. |
| 25 | `GET /api/objtagoption` | Available tag options. |

## 6. Astronomical context and catalogs

| Priority | Endpoint | What it gives us |
|---:|---|---|
| 26 | `GET /api/sources/{obj_id}/tns` | TNS information for a source. |
| 27 | `GET /api/sources/{obj_id}/position` | Positional information for a source. |
| 28 | `GET /api/sources/{obj_id}/offsets` | Offsets relative to possible hosts or nearby objects. |
| 29 | `GET /api/sources/{obj_id}/color_mag` | Color-magnitude information, usually Gaia-linked. |
| 30 | `GET /api/galaxy_catalog/{catalog_name}` | One galaxy catalog. |
| 31 | `GET /api/spatial_catalog` | Available spatial catalogs. |
| 32 | `GET /api/spatial_catalog/{catalog_id}` | Detail for one spatial catalog. |

## 7. GCN and multimessenger

| Priority | Endpoint | What it gives us |
|---:|---|---|
| 33 | `GET /api/gcn_event` | GCN or multimessenger event list. |
| 34 | `GET /api/gcn_event/{dateobs}` | One GCN event by `dateobs`. |
| 35 | `GET /api/sources_in_gcn/{dateobs}` | Sources associated with one GCN event. |
| 36 | `GET /api/sources_in_gcn/{dateobs}/{source_id}` | Relationship between one source and one GCN event. |
| 37 | `GET /api/associated_gcns/{source_id}` | GCNs associated with one source. |
| 38 | `GET /api/gcn_event/{gcnevent_id}/observation_plan_requests` | Observation-plan requests associated with a GCN event. |
| 39 | `GET /api/gcn_event/{gcnevent_id}/survey_efficiency` | Survey efficiency or coverage for a GCN event. |
| 40 | `GET /api/gcn_event/{gcnevent_id}/catalog_query` | Catalog queries associated with a GCN event. |
| 41 | `GET /api/gcn_event/{dateobs}/notice/{notice_id}/download` | Original GCN notice download. |

## 8. Localizations and observability

| Priority | Endpoint | What it gives us |
|---:|---|---|
| 42 | `GET /api/localization/{dateobs}/name/{localization_name}` | One localization or skymap. |
| 43 | `GET /api/localization/{dateobs}/name/{localization_name}/download` | Localization file download. |
| 44 | `GET /api/localization/{localization_id}/observability` | Observability for one localization. |
| 45 | `GET /api/sources/{obj_id}/observability` | Observability for one source. |

## 9. Follow-up and observation planning

| Priority | Endpoint | What it gives us |
|---:|---|---|
| 46 | `GET /api/followup_request` | Follow-up request list. |
| 47 | `GET /api/followup_request/{followup_request_id}` | Detail for one follow-up request. |
| 48 | `GET /api/photometry_request/{request_id}` | Detail for one photometry request. |
| 49 | `GET /api/observation_plan` | Observation-plan list. |
| 50 | `GET /api/observation_plan/{observation_plan_request_id}` | Detail for one observation plan. |
| 51 | `GET /api/observation` | Completed observation list. |

## 10. Images and visual context

| Priority | Endpoint | What it gives us |
|---:|---|---|
| 52 | `GET /api/thumbnail/{thumbnail_id}` | One thumbnail or cutout. |
| 53 | `GET /api/thumbnailPath` | Thumbnail paths. |
| 54 | `GET /api/sources/{obj_id}/finder` | Finder chart for a source. |

## 11. Analysis services

| Priority | Endpoint | What it gives us |
|---:|---|---|
| 55 | `GET /api/analysis_service` | Available analysis services. |
| 56 | `GET /api/analysis_service/{analysis_service_id}` | Detail for one analysis service. |
| 57 | `GET /api/{analysis_resource_type}/analysis` | Analyses available for one resource type. |
| 58 | `GET /api/{analysis_resource_type}/analysis/{analysis_id}` | Detail for one analysis result. |

## 12. Operational metadata

| Priority | Endpoint | What it gives us |
|---:|---|---|
| 59 | `GET /api/groups` | Group list. |
| 60 | `GET /api/groups/{group_id}` | Detail for one group. |
| 61 | `GET /api/sources/{obj_id}/groups` | Groups associated with one source. |
| 62 | `GET /api/instrument` | Instrument list. |
| 63 | `GET /api/instrument/{instrument_id}` | Detail for one instrument. |
| 64 | `GET /api/telescope` | Telescope list. |
| 65 | `GET /api/telescope/{telescope_id}` | Detail for one telescope. |
| 66 | `GET /api/filters` | Alert or broker filter list. |
| 67 | `GET /api/filters/{filter_id}` | Detail for one filter. |
| 68 | `GET /api/streams` | Alert-stream list. |
| 69 | `GET /api/config` | Exposed instance configuration. |

## Practical reading

For the current phase, the most important pieces are:

1. `GET /api/sources` to build inventories;
2. `GET /api/sources/{source_id}` as the root object for a selected source;
3. specialized source-level endpoints for photometry, spectra, comments,
   classifications, and GCN context.

The shorter operational shortlist lives in `docs/skyportal/05_relevant_endpoints.md`.
