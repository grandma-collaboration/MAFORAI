# SkyPortal Endpoints


## 1. Source Inventory and Identity

| Priority | Endpoint | What it does |
| --- | --- | --- |
| 1 | `GET /api/sources` | Returns sources saved in SkyPortal with filters such as detection date, `sourceID`, `group_ids`, classification, redshift, whether the source has spectra, follow-up, comments, annotations, GCN localization, and more. |
| 2 | `GET /api/sources/{obj_id}` | Returns the full information for a specific source. |
| 3 | `GET /api/candidates` | Lists candidates, usually objects that passed broker or filter stages before becoming saved sources. |
| 4 | `GET /api/candidates/{obj_id}` | Returns information for a specific candidate. |
| 5 | `GET /api/source_exists/{obj_id}` | Checks whether a source exists. |

## 2. Photometry

| Priority | Endpoint | What it does |
| --- | --- | --- |
| 6 | `GET /api/sources/{obj_id}/photometry` | Returns the photometric points for a source. |
| 7 | `GET /api/sources/{obj_id}/phot_stat` | Returns summarized photometric statistics. |
| 8 | `GET /api/photometry/{photometry_id}` | Returns a specific photometric record. |
| 9 | `GET /api/photometry/range` | Returns photometry by range or filtering criteria. |
| 10 | `GET /api/photometric_series/{photometric_series_id}` | Returns a specific photometric series. |

## 3. Spectroscopy

| Priority | Endpoint | What it does |
| --- | --- | --- |
| 11 | `GET /api/sources/{obj_id}/spectra` | Returns spectra associated with a source. |
| 12 | `GET /api/spectrum/{spectrum_id}` | Returns a specific spectrum. |
| 13 | `GET /api/spectrum` | Lists spectra. |
| 14 | `GET /api/spectrum/range` | Returns spectra by range or filters. |

## 4. Classifications and Taxonomies

| Priority | Endpoint | What it does |
| --- | --- | --- |
| 15 | `GET /api/sources/{obj_id}/classifications` | Returns classifications associated with a source. |
| 16 | `GET /api/classification/{classification_id}` | Returns a specific classification. |
| 17 | `GET /api/classification` | Lists classifications. |
| 18 | `GET /api/taxonomy` | Lists available taxonomies. |
| 19 | `GET /api/taxonomy/{taxonomy_id}` | Returns a specific taxonomy. |

## 5. Comments, Annotations, and Tags

| Priority | Endpoint | What it does |
| --- | --- | --- |
| 20 | `GET /api/{associated_resource_type}/{resource_id}/comments` | Returns comments associated with a source, spectrum, GCN, or another resource. |
| 21 | `GET /api/{associated_resource_type}/{resource_id}/comments/{comment_id}` | Returns a specific comment. |
| 22 | `GET /api/{associated_resource_type}/{resource_id}/annotations` | Returns annotations associated with a resource. |
| 23 | `GET /api/{associated_resource_type}/{resource_id}/annotations/{annotation_id}` | Returns a specific annotation. |
| 24 | `GET /api/objtag` | Returns tags applied to objects. |
| 25 | `GET /api/objtagoption` | Returns the available object tag options. |

## 6. Astronomical Context and Catalogs

| Priority | Endpoint | What it does |
| --- | --- | --- |
| 26 | `GET /api/sources/{obj_id}/tns` | Returns Transient Name Server information for a source. |
| 27 | `GET /api/sources/{obj_id}/position` | Returns positional information for a source. |
| 28 | `GET /api/sources/{obj_id}/offsets` | Returns offsets relative to possible hosts or nearby sources. |
| 29 | `GET /api/sources/{obj_id}/color_mag` | Returns color-magnitude information, typically linked to Gaia. |
| 30 | `GET /api/galaxy_catalog/{catalog_name}` | Returns data from a galaxy catalog. |
| 31 | `GET /api/spatial_catalog` | Lists available spatial catalogs. |
| 32 | `GET /api/spatial_catalog/{catalog_id}` | Returns a specific spatial catalog. |

## 7. GCN and Multimessenger

| Priority | Endpoint | What it does |
| --- | --- | --- |
| 33 | `GET /api/gcn_event` | Lists GCN or multimessenger events. |
| 34 | `GET /api/gcn_event/{dateobs}` | Returns a specific GCN event. |
| 35 | `GET /api/sources_in_gcn/{dateobs}` | Lists sources associated with a GCN event. |
| 36 | `GET /api/sources_in_gcn/{dateobs}/{source_id}` | Returns the relationship between a source and a GCN event. |
| 37 | `GET /api/associated_gcns/{source_id}` | Returns GCNs associated with a source. |
| 38 | `GET /api/gcn_event/{gcnevent_id}/observation_plan_requests` | Returns observation plans or requests associated with a GCN event. |
| 39 | `GET /api/gcn_event/{gcnevent_id}/survey_efficiency` | Returns survey efficiency or coverage for the event. |
| 40 | `GET /api/gcn_event/{gcnevent_id}/catalog_query` | Returns catalog queries associated with the GCN event. |
| 41 | `GET /api/gcn_event/{dateobs}/notice/{notice_id}/download` | Downloads an original GCN notice. |

## 8. Localizations and Observability

| Priority | Endpoint | What it does |
| --- | --- | --- |
| 42 | `GET /api/localization/{dateobs}/name/{localization_name}` | Returns a localization or skymap associated with an event. |
| 43 | `GET /api/localization/{dateobs}/name/{localization_name}/download` | Downloads the localization file. |
| 44 | `GET /api/localization/{localization_id}/observability` | Returns observability information for a localization. |
| 45 | `GET /api/sources/{obj_id}/observability` | Returns observability information for a source. |

## 9. Follow-up and Observation Planning

| Priority | Endpoint | What it does |
| --- | --- | --- |
| 46 | `GET /api/followup_request` | Lists follow-up requests. |
| 47 | `GET /api/followup_request/{followup_request_id}` | Returns a specific follow-up request. |
| 48 | `GET /api/photometry_request/{request_id}` | Returns a photometry request. |
| 49 | `GET /api/observation_plan` | Lists observation plans. |
| 50 | `GET /api/observation_plan/{observation_plan_request_id}` | Returns a specific observation plan. |
| 51 | `GET /api/observation` | Lists completed observations. |

## 10. Images and Visual Context

| Priority | Endpoint | What it does |
| --- | --- | --- |
| 52 | `GET /api/thumbnail/{thumbnail_id}` | Returns a thumbnail or cutout. |
| 53 | `GET /api/thumbnailPath` | Returns thumbnail paths. |
| 54 | `GET /api/sources/{obj_id}/finder` | Returns or generates a finder chart for a source. |

## 11. Analysis Services

| Priority | Endpoint | What it does |
| --- | --- | --- |
| 55 | `GET /api/analysis_service` | Lists available analysis services. |
| 56 | `GET /api/analysis_service/{analysis_service_id}` | Returns information for a specific analysis service. |
| 57 | `GET /api/{analysis_resource_type}/analysis` | Lists analyses for a given resource type. |
| 58 | `GET /api/{analysis_resource_type}/analysis/{analysis_id}` | Returns a specific analysis result. |

## 12. Operational Metadata

| Priority | Endpoint | What it does |
| --- | --- | --- |
| 59 | `GET /api/groups` | Lists groups. |
| 60 | `GET /api/groups/{group_id}` | Returns detailed information for a group. |
| 61 | `GET /api/sources/{obj_id}/groups` | Returns the groups associated with a source. |
| 62 | `GET /api/instrument` | Lists instruments. |
| 63 | `GET /api/instrument/{instrument_id}` | Returns detailed information for an instrument. |
| 64 | `GET /api/telescope` | Lists telescopes. |
| 65 | `GET /api/telescope/{telescope_id}` | Returns detailed information for a telescope. |
| 66 | `GET /api/filters` | Lists alert or broker filters. |
| 67 | `GET /api/filters/{filter_id}` | Returns a specific filter. |
| 68 | `GET /api/streams` | Lists alert streams. |
| 69 | `GET /api/config` | Returns exposed instance configuration. |
