# Relevant SkyPortal Endpoints

This document is the short operational shortlist of endpoints that matter most
for the current inventory-first workflow and for any future deeper extraction
stage.

The broader catalog still lives in `docs/endpoints.md`. Here the goal is simply
to keep the useful subset easy to read.

## 1. Inventory layer

| Endpoint | Why it matters now |
|---|---|
| `GET /api/sources` | Main discovery endpoint. It is the practical way to build targeted source subsets before attempting deeper extraction. |

## 2. Core source-bundle endpoints

These are the endpoints that make the most sense to call for each selected
source.

| Endpoint | Why it matters |
|---|---|
| `GET /api/sources/{source_id}` | Root source object with metadata, coordinates, TNS information, redshift, groups, tags, classifications, annotations, and some follow-up context when available. |
| `GET /api/sources/{source_id}/photometry?format=flux` | Full light curve in flux format, useful for numeric analysis and later ML-oriented processing. |
| `GET /api/sources/{source_id}/photometry?format=mag` | Full light curve in magnitude format, useful for direct astronomical interpretation. |
| `GET /api/sources/{source_id}/phot_stat` | Compact photometric statistics such as first detection, last detection, peak magnitude, and detection counts. |
| `GET /api/sources/{source_id}/comments` | Human comments that may capture reasoning, uncertainty, follow-up decisions, and scientific discussion. |
| `GET /api/sources/{source_id}/classifications` | Classification labels, taxonomy IDs, authorship, timestamps, and probabilities when available. |
| `GET /api/sources/{source_id}/spectra` | Spectra associated with the source. Important for multimodal examples. |
| `GET /api/sources/{source_id}/annotations` | Source annotations, potentially useful for automatic scores, broker metadata, and derived values. |
| `GET /api/associated_gcns/{source_id}` | GCN associations for GCN-like, EP-like, GRB-like, or multimessenger candidates. |
| `GET /api/sources/{source_id}/position` | Per-source positional context, useful when checking localization quality or derived position products. |
| `GET /api/sources/{source_id}/offsets` | Offset-star and nearby-offset context. Useful to inspect whether the instance exposes a structured proximity signal around the source. |
| `GET /api/sources/{source_id}/color_mag` | Gaia-linked color-magnitude context when available. |

The important point is that `GET /api/sources/{source_id}` is a strong hub, but
it is not a full replacement for the specialized endpoints above.

## 3. Global reference endpoints

These endpoints are usually fetched once, not per source.

| Endpoint | Why it matters |
|---|---|
| `GET /api/taxonomy` | Interprets classification labels and taxonomy IDs. |
| `GET /api/objtag` | Lists object tags already applied to sources. |
| `GET /api/objtagoption` | Interprets the available tag vocabulary. |
| `GET /api/groups` | Interprets groups associated with sources. |
| `GET /api/instrument` | Interprets `instrument_id` and related metadata in photometry, spectra, and follow-up data. |
| `GET /api/telescope` | Adds telescope-level context for instruments and observations. |
| `GET /api/config` | Helps interpret instance-level configuration such as classes, spectrum types, or other exposed defaults. |
| `GET /api/analysis_service` | Shows which automatic analysis services are available in the instance. |

## 4. Conditional endpoints

These endpoints are useful, but only when the selected source or event context
actually requires them.

| Endpoint family | When it becomes useful |
|---|---|
| `GET /api/sources_in_gcn/{dateobs}` and related GCN routes | When the source is tied to a GCN or multimessenger event |
| Localization routes | When the event has a sky localization that matters for interpretation |
| Follow-up request detail routes | When the source already shows follow-up activity worth reconstructing |
| Thumbnail or finder routes | When the visual context becomes part of the workflow |

## 5. First source-bundle recipe

If we had to define the first extraction bundle today, it would look like this:

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
GET /api/sources/{source_id}/position
GET /api/sources/{source_id}/offsets
GET /api/sources/{source_id}/color_mag
```

That bundle is small enough to be practical and rich enough to tell us what a
useful event-level extraction really looks like.

In the current extraction workflow, `offsets` does return useful context, but
it looks more like offset-star observing support than a direct "host galaxy
proximity" measurement. For host proximity itself, the more relevant
structured fields remain `host_id` and any populated `galaxies` information
in the root source object.

## 6. Current status

This endpoint bundle is still useful as a reference for future deeper
extractions, but it is not part of the active operational workflow anymore.

Current consequence:

- the SkyPortal workflow currently stops at
  `data/interim/skyportal/gcn_grandma.json` and
  `data/interim/skyportal/skyportal_event_baseline.parquet`;
- GCN matching starts from the compact inventory-derived base;
- later GCN enrichment and review use the prebuilt SkyPortal baseline;
- deeper per-source endpoint downloads are postponed until they are clearly
  needed again.
