# Endpoint Audit

## Goal

The endpoint audit checks which SkyPortal API routes are reachable with the
current token and with the sample identifiers available at runtime.

It is an access-and-structure audit, not a full scientific extraction step.

## Entry points

| File | Role |
|---|---|
| `scripts/01_audit_endpoint_availability.py` | Thin CLI wrapper |
| `src/skyportal_corpus/extraction/endpoint_audit.py` | Actual audit logic |

By default, the script reads `configs/extraction/skyportal.yaml` for:

- the base URL;
- the default output directory;
- timeout and sleep defaults;
- sample context such as `source_id` and `resource_type`.

CLI arguments still override the config when needed.

## What the audit records

| Field family | Description |
|---|---|
| Request target | URL and query parameters used for the endpoint |
| Transport result | HTTP status code and elapsed time |
| Payload validation | Whether the response is valid JSON |
| API status | SkyPortal `status` and `message` when present |
| Structure summary | Top-level keys, `data` type, `data` keys, and data length |
| Failure mode | Request error, HTTP error, non-JSON response, or skipped reason |

## Common inputs

Some endpoints only make sense if example IDs are available.

| Argument | Typical use |
|---|---|
| `--source-id` | Source-level endpoints such as `/sources/{source_id}` |
| `--candidate-id` | Candidate endpoints |
| `--resource-type` and `--resource-id` | Comments and annotations |
| `--dateobs` | GCN-related endpoints |
| `--category` | Restrict the run to one endpoint family |

If `--source-id` is omitted, the script can fall back to the sample context in
the YAML config. Endpoints that need IDs not present in the config are skipped,
which is expected.

## Typical commands

Minimal audit using the shared config:

```bash
python scripts/01_audit_endpoint_availability.py \
  --run-label initial
```

Audit one category with an explicit source:

```bash
python scripts/01_audit_endpoint_availability.py \
  --run-label photometry \
  --category photometry \
  --source-id 2023qye
```

## Output files

Each run creates a directory under `data/raw/skyportal/endpoint_audit/`.

| File | Purpose |
|---|---|
| `endpoint_status.csv` | Flat endpoint-by-endpoint summary |
| `endpoint_status.json` | Full structured results for each endpoint |
| `summary.json` | Compact aggregate metrics |
| `endpoint_audit.log` | Execution log |

## Example run

One observed run produced the following metrics:

| Metric | Value |
|---|---:|
| Total endpoints tested | 70 |
| Successful endpoints | 33 |
| Skipped endpoints | 31 |
| HTTP errors | 3 |
| Request errors | 3 |

## Status interpretation

| Status | Meaning |
|---|---|
| `success` | Endpoint returned a valid successful JSON response |
| `skipped` | Required context was missing |
| `request_error` | Transport-level failure such as timeout or connection issue |
| `http_<code>` | HTTP response was received, but it was not a successful API call |
| `http_<code>_non_json` | HTTP response was received, but the payload was not JSON |
| `http_200_json_no_api_status` | JSON was returned, but without the usual SkyPortal API status field |

## How to read the result

Two points matter when interpreting the audit:

| Constraint | Practical meaning |
|---|---|
| Missing IDs | Many routes need identifiers such as `spectrum_id`, `classification_id`, `followup_request_id`, or `taxonomy_id` |
| Non-JSON resources | Some endpoints naturally behave like downloads or assets rather than JSON APIs |
