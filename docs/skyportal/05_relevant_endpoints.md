# Relevant SkyPortal API Endpoints

This document summarizes the SkyPortal API endpoints that are most relevant for the first corpus-oriented extraction workflow.

The goal is to identify which endpoints are useful for discovering sources, extracting complete event information, and interpreting the extracted data.

---

## 1. Inventory endpoint

| Endpoint | Why we use it |
|---|---|
| `GET /api/sources` | Main endpoint to discover and filter sources before extracting complete event data. It supports filters such as spectra, follow-up, classifications, redshift, detections, GCN-like IDs and EP-like IDs. |

This endpoint is used to create targeted inventories instead of downloading the full SkyPortal database.

---

## 2. Core source-bundle endpoints

These endpoints are the most important ones for extracting complete information about a selected source/event.

| Endpoint | Why we use it |
|---|---|
| `GET /api/sources/{source_id}` | Root source object. Contains metadata, coordinates, TNS information, redshift, summaries, groups, tags, classifications, annotations, follow-up requests and GCN crossmatch information when available. |
| `GET /api/sources/{source_id}/photometry?format=flux` | Full light curve in flux format. Useful for numerical analysis and ML-oriented processing. |
| `GET /api/sources/{source_id}/photometry?format=mag` | Full light curve in magnitude format. Useful for astronomical interpretation. |
| `GET /api/sources/{source_id}/phot_stat` | Compact photometric statistics: first/last detection, peak magnitude, number of detections, rise/decay rates, non-detections, etc. |
| `GET /api/sources/{source_id}/comments` | Human comments. Useful for understanding reasoning, uncertainty, follow-up decisions and for the future LLM component. |
| `GET /api/sources/{source_id}/classifications` | Classification labels, taxonomy IDs, probabilities, authorship and timestamps. |
| `GET /api/sources/{source_id}/spectra` | Spectra associated with the source, when available. Important for multimodal event examples. |
| `GET /api/sources/{source_id}/annotations` | Source annotations. Potentially useful for automatic scores, broker metadata, crossmatches or derived information. |
| `GET /api/associated_gcns/{source_id}` | Retrieves GCN associations. Useful for GCN/EP/GRB-like sources. |

Although `GET /api/sources/{source_id}` is a rich root object, specialized endpoints are still useful because some information, such as full photometry and comments, is not fully contained in the root response.

---

## 3. Global metadata endpoints

These endpoints are not downloaded for every source. They are downloaded once to interpret the source data.

| Endpoint | Why we use it |
|---|---|
| `GET /api/taxonomy` | Interpret classification labels and taxonomy IDs. |
| `GET /api/objtag` | Retrieve tags applied to sources. |
| `GET /api/objtagoption` | Interpret available tag names/options. |
| `GET /api/groups` | Interpret groups associated with saved sources. |
| `GET /api/instrument` | Interpret `instrument_id` and `instrument_name` in photometry, spectra and follow-up. |
| `GET /api/telescope` | Interpret telescope metadata associated with instruments. |
| `GET /api/config` | Understand allowed classes, spectrum types, bandpasses, GCN notice types and instance configuration. |
| `GET /api/analysis_service` | Check which automatic analysis or summary services are available in the SkyPortal instance. |

---

## 4. Proposed extraction strategy

For each selected source, the first source-bundle extraction should retrieve:

```text
GET /api/sources/{source_id}
GET /api/sources/{source_id}/photometry?format=flux
GET /api/sources/{source_id}/photometry?format=mag
GET /api/sources/{source_id}/phot_stat
GET /api/sources/{source_id}/comments
GET /api/sources/{source_id}/classifications
GET /api/sources/{source_id}/spectra
GET /api/sources/{source_id}/annotations
GET /api/associated_gcns/{source_id}