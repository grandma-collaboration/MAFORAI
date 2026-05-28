# Endpoint Audit

## Goal

`scripts/01_audit_endpoint_availability.py` checks which SkyPortal API
endpoints are reachable with the current token and with the sample identifiers
provided through the command line.

It is an access-and-structure audit, not a full scientific extraction step.

## Script

```text
scripts/01_audit_endpoint_availability.py
```

## What the audit records

| Field family | Description |
|---|---|
| Request target | URL and query parameters used for the endpoint |
| Transport result | HTTP status code and elapsed time |
| Payload validation | Whether the response is valid JSON |
| API status | SkyPortal `status` and `message` when present |
| Structure summary | Top-level keys, `data` type, `data` keys, and data length |
| Failure mode | Request error, HTTP error, or skipped reason |

## Common inputs

Some endpoints need example IDs to be meaningful.

| Argument | Used for |
|---|---|
| `--source-id` | Source-level endpoints such as `/sources/{source_id}` |
| `--candidate-id` | Candidate endpoints |
| `--resource-type` and `--resource-id` | Comments and annotations |
| `--dateobs` | GCN-related endpoints |
| `--category` | Restrict the run to one endpoint family |
| `--save-responses` | Persist full payloads under `responses/` |

## Typical commands

Minimal audit:

```bash
python scripts/01_audit_endpoint_availability.py \
  --run-label initial \
  --source-id 2023qye
```

Audit one category:

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
| `endpoint_status.csv` | Tabular endpoint-by-endpoint summary |
| `endpoint_status.json` | Full structured results for each endpoint |
| `summary.json` | Compact aggregate metrics |
| `endpoint_audit.log` | Execution log |

## Example run

During the current audit, one example run was generated at:

```text
data/raw/skyportal/endpoint_audit/endpoint_audit_initial_20260528_141555/
```

The metrics below are documented from that run's `summary.json`:

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
| `skipped` | Required context was missing; this is not necessarily a failure |
| `request_error` | Transport-level failure such as timeout or connection issue |
| `http_<code>` | HTTP response was received, but it was not a successful API call |
| `http_200_non_json` | Endpoint returned content successfully, but not as JSON |

## Reading the result correctly

The audit should be interpreted with two constraints in mind:

| Constraint | Practical meaning |
|---|---|
| Missing IDs | Many endpoints require identifiers such as `spectrum_id`, `classification_id`, `followup_request_id`, or `taxonomy_id` |
| Non-JSON resources | Some endpoints naturally behave like file or asset downloads rather than JSON APIs |

That is why the audit is best used to establish reachable endpoint families and
response shapes before building a deeper extractor.
