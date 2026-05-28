"""
Auditing the availability of SkyPortal API endpoints.

This script checks which endpoints are accessible with the current API token and a small set of sample identifiers.

Results:
- endpoint_status.csv
- endpoint_status.json
- summary.json
- endpoint_audit.log
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pandas as pd
import requests


DEFAULT_BASE_URL = "https://skyportal-icare.ijclab.in2p3.fr/api"


@dataclass(frozen=True)
class EndpointSpec:
    """Description of one API endpoint to audit."""

    name: str
    category: str
    priority: int
    method: str
    path_template: str
    required_context: list[str] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)


def load_dotenv_if_available() -> None:
    """
    Load environment variables from .env if python-dotenv is installed.

    This keeps the script usable even if python-dotenv is not installed.
    """
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass


def setup_logging(output_dir: Path) -> None:
    """Configure logging to console and file."""
    log_file = output_dir / "endpoint_audit.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )


def get_token() -> str:
    """Read SkyPortal API token from environment."""
    load_dotenv_if_available()

    token = os.getenv("SKYPORTAL_API_TOKEN")
    if not token:
        raise ValueError(
            "SKYPORTAL_API_TOKEN is not set. "
            "Export it manually or create a local .env file."
        )

    return token


def safe_path_value(value: str) -> str:
    """URL-encode one path component safely."""
    return quote(str(value), safe="")


def render_path(path_template: str, context: dict[str, str]) -> str:
    """
    Render endpoint path by replacing placeholders with context values.

    Example:
    /sources/{source_id}/photometry
    """
    rendered = path_template

    for key, value in context.items():
        rendered = rendered.replace("{" + key + "}", safe_path_value(value))

    return rendered


def missing_context(endpoint: EndpointSpec, context: dict[str, str | None]) -> list[str]:
    """Return required context keys that are missing."""
    missing = []

    for key in endpoint.required_context:
        if not context.get(key):
            missing.append(key)

    return missing


def summarize_payload(payload: Any) -> dict[str, Any]:
    """
    Summarize response structure without storing the full payload.

    This is useful for data audit without downloading/saving too much data.
    """
    summary: dict[str, Any] = {
        "payload_type": type(payload).__name__,
        "top_level_keys": None,
        "data_type": None,
        "data_keys": None,
        "data_length": None,
        "api_status": None,
        "api_message": None,
    }

    if isinstance(payload, dict):
        summary["top_level_keys"] = list(payload.keys())
        summary["api_status"] = payload.get("status")
        summary["api_message"] = payload.get("message")

        data = payload.get("data")

        if isinstance(data, dict):
            summary["data_type"] = "dict"
            summary["data_keys"] = list(data.keys())
            summary["data_length"] = len(data)

        elif isinstance(data, list):
            summary["data_type"] = "list"
            summary["data_length"] = len(data)

            if data and isinstance(data[0], dict):
                summary["data_keys"] = list(data[0].keys())

        elif data is not None:
            summary["data_type"] = type(data).__name__

    elif isinstance(payload, list):
        summary["data_type"] = "list"
        summary["data_length"] = len(payload)

        if payload and isinstance(payload[0], dict):
            summary["data_keys"] = list(payload[0].keys())

    return summary


def audit_endpoint(
    session: requests.Session,
    base_url: str,
    endpoint: EndpointSpec,
    context: dict[str, str | None],
    timeout: int,
    save_responses: bool,
    responses_dir: Path,
) -> dict[str, Any]:
    """Audit one endpoint and return a structured result."""
    missing = missing_context(endpoint, context)

    result: dict[str, Any] = {
        "name": endpoint.name,
        "category": endpoint.category,
        "priority": endpoint.priority,
        "method": endpoint.method,
        "path_template": endpoint.path_template,
        "url": None,
        "params": endpoint.params,
        "status": None,
        "skipped": False,
        "skip_reason": None,
        "http_status_code": None,
        "elapsed_seconds": None,
        "json_valid": False,
        "api_status": None,
        "api_message": None,
        "payload_type": None,
        "top_level_keys": None,
        "data_type": None,
        "data_keys": None,
        "data_length": None,
        "response_size_chars": None,
        "error": None,
    }

    if missing:
        result["status"] = "skipped"
        result["skipped"] = True
        result["skip_reason"] = f"missing required context: {', '.join(missing)}"
        return result

    path = render_path(endpoint.path_template, {k: v for k, v in context.items() if v})
    url = f"{base_url}{path}"
    result["url"] = url

    start = time.perf_counter()

    try:
        response = session.get(url, params=endpoint.params, timeout=timeout)
        elapsed = time.perf_counter() - start

        result["elapsed_seconds"] = round(elapsed, 3)
        result["http_status_code"] = response.status_code
        result["response_size_chars"] = len(response.text)

        try:
            payload = response.json()
            result["json_valid"] = True
            payload_summary = summarize_payload(payload)

            result.update(payload_summary)

            if response.status_code == 200:
                if isinstance(payload, dict) and payload.get("status") == "success":
                    result["status"] = "success"
                elif isinstance(payload, dict) and payload.get("status"):
                    result["status"] = f"api_{payload.get('status')}"
                else:
                    result["status"] = "http_200_json_no_api_status"
            else:
                result["status"] = f"http_{response.status_code}"

            if save_responses:
                response_file = responses_dir / f"{endpoint.priority:02d}_{endpoint.name}.json"
                with response_file.open("w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2, default=str)

        except ValueError:
            result["json_valid"] = False
            result["status"] = f"http_{response.status_code}_non_json"
            result["error"] = "Response is not valid JSON"

            if save_responses:
                response_file = responses_dir / f"{endpoint.priority:02d}_{endpoint.name}.txt"
                response_file.write_text(response.text, encoding="utf-8")

    except requests.exceptions.RequestException as exc:
        elapsed = time.perf_counter() - start
        result["elapsed_seconds"] = round(elapsed, 3)
        result["status"] = "request_error"
        result["error"] = str(exc)

    return result


def get_endpoint_specs() -> list[EndpointSpec]:
    """
    Endpoint list derived from docs/endpoints.md.

    Some endpoints require example IDs. If those IDs are not provided
    through CLI arguments, the endpoint is skipped and documented.
    """
    return [
        # 1. Inventario e identidad de fuentes
        EndpointSpec("sources", "inventory", 1, "GET", "/sources", params={"numPerPage": 1}),
        EndpointSpec("source_detail", "inventory", 2, "GET", "/sources/{source_id}", ["source_id"]),
        EndpointSpec("candidates", "inventory", 3, "GET", "/candidates", params={"numPerPage": 1}),
        EndpointSpec("candidate_detail", "inventory", 4, "GET", "/candidates/{candidate_id}", ["candidate_id"]),
        EndpointSpec("source_exists", "inventory", 5, "GET", "/source_exists/{source_id}", ["source_id"]),

        # 2. Fotometría
        EndpointSpec("source_photometry_flux", "photometry", 6, "GET", "/sources/{source_id}/photometry", ["source_id"], {"format": "flux"}),
        EndpointSpec("source_photometry_mag", "photometry", 6, "GET", "/sources/{source_id}/photometry", ["source_id"], {"format": "mag"}),
        EndpointSpec("source_phot_stat", "photometry", 7, "GET", "/sources/{source_id}/phot_stat", ["source_id"]),
        EndpointSpec("photometry_detail", "photometry", 8, "GET", "/photometry/{photometry_id}", ["photometry_id"]),
        EndpointSpec("photometry_range", "photometry", 9, "GET", "/photometry/range"),
        EndpointSpec("photometric_series_detail", "photometry", 10, "GET", "/photometric_series/{photometric_series_id}", ["photometric_series_id"]),

        # 3. Espectroscopia
        EndpointSpec("source_spectra", "spectroscopy", 11, "GET", "/sources/{source_id}/spectra", ["source_id"]),
        EndpointSpec("spectrum_detail", "spectroscopy", 12, "GET", "/spectrum/{spectrum_id}", ["spectrum_id"]),
        EndpointSpec("spectrum_list", "spectroscopy", 13, "GET", "/spectrum", params={"numPerPage": 1}),
        EndpointSpec("spectrum_range", "spectroscopy", 14, "GET", "/spectrum/range"),

        # 4. Clasificaciones y taxonomías
        EndpointSpec("source_classifications", "classifications", 15, "GET", "/sources/{source_id}/classifications", ["source_id"]),
        EndpointSpec("classification_detail", "classifications", 16, "GET", "/classification/{classification_id}", ["classification_id"]),
        EndpointSpec("classification_list", "classifications", 17, "GET", "/classification", params={"numPerPage": 1}),
        EndpointSpec("taxonomy_list", "classifications", 18, "GET", "/taxonomy"),
        EndpointSpec("taxonomy_detail", "classifications", 19, "GET", "/taxonomy/{taxonomy_id}", ["taxonomy_id"]),

        # 5. Comentarios, anotaciones y tags
        EndpointSpec("resource_comments", "comments_annotations_tags", 20, "GET", "/{resource_type}/{resource_id}/comments", ["resource_type", "resource_id"]),
        EndpointSpec("resource_comment_detail", "comments_annotations_tags", 21, "GET", "/{resource_type}/{resource_id}/comments/{comment_id}", ["resource_type", "resource_id", "comment_id"]),
        EndpointSpec("resource_annotations", "comments_annotations_tags", 22, "GET", "/{resource_type}/{resource_id}/annotations", ["resource_type", "resource_id"]),
        EndpointSpec("resource_annotation_detail", "comments_annotations_tags", 23, "GET", "/{resource_type}/{resource_id}/annotations/{annotation_id}", ["resource_type", "resource_id", "annotation_id"]),
        EndpointSpec("objtag", "comments_annotations_tags", 24, "GET", "/objtag"),
        EndpointSpec("objtagoption", "comments_annotations_tags", 25, "GET", "/objtagoption"),

        # 6. Contexto astronómico y catálogos
        EndpointSpec("source_tns", "astronomical_context", 26, "GET", "/sources/{source_id}/tns", ["source_id"]),
        EndpointSpec("source_position", "astronomical_context", 27, "GET", "/sources/{source_id}/position", ["source_id"]),
        EndpointSpec("source_offsets", "astronomical_context", 28, "GET", "/sources/{source_id}/offsets", ["source_id"]),
        EndpointSpec("source_color_mag", "astronomical_context", 29, "GET", "/sources/{source_id}/color_mag", ["source_id"]),
        EndpointSpec("galaxy_catalog", "astronomical_context", 30, "GET", "/galaxy_catalog/{catalog_name}", ["catalog_name"]),
        EndpointSpec("spatial_catalog_list", "astronomical_context", 31, "GET", "/spatial_catalog"),
        EndpointSpec("spatial_catalog_detail", "astronomical_context", 32, "GET", "/spatial_catalog/{catalog_id}", ["catalog_id"]),

        # 7. GCN y multimessenger
        EndpointSpec("gcn_event_list", "gcn_multimessenger", 33, "GET", "/gcn_event", params={"numPerPage": 1}),
        EndpointSpec("gcn_event_detail_by_dateobs", "gcn_multimessenger", 34, "GET", "/gcn_event/{dateobs}", ["dateobs"]),
        EndpointSpec("sources_in_gcn", "gcn_multimessenger", 35, "GET", "/sources_in_gcn/{dateobs}", ["dateobs"]),
        EndpointSpec("source_in_gcn_detail", "gcn_multimessenger", 36, "GET", "/sources_in_gcn/{dateobs}/{source_id}", ["dateobs", "source_id"]),
        EndpointSpec("associated_gcns", "gcn_multimessenger", 37, "GET", "/associated_gcns/{source_id}", ["source_id"]),
        EndpointSpec("gcn_observation_plan_requests", "gcn_multimessenger", 38, "GET", "/gcn_event/{gcnevent_id}/observation_plan_requests", ["gcnevent_id"]),
        EndpointSpec("gcn_survey_efficiency", "gcn_multimessenger", 39, "GET", "/gcn_event/{gcnevent_id}/survey_efficiency", ["gcnevent_id"]),
        EndpointSpec("gcn_catalog_query", "gcn_multimessenger", 40, "GET", "/gcn_event/{gcnevent_id}/catalog_query", ["gcnevent_id"]),
        EndpointSpec("gcn_notice_download", "gcn_multimessenger", 41, "GET", "/gcn_event/{dateobs}/notice/{notice_id}/download", ["dateobs", "notice_id"]),

        # 8. Localizaciones y observabilidad
        EndpointSpec("localization_by_dateobs_name", "localization_observability", 42, "GET", "/localization/{dateobs}/name/{localization_name}", ["dateobs", "localization_name"]),
        EndpointSpec("localization_download", "localization_observability", 43, "GET", "/localization/{dateobs}/name/{localization_name}/download", ["dateobs", "localization_name"]),
        EndpointSpec("localization_observability", "localization_observability", 44, "GET", "/localization/{localization_id}/observability", ["localization_id"]),
        EndpointSpec("source_observability", "localization_observability", 45, "GET", "/sources/{source_id}/observability", ["source_id"]),

        # 9. Follow-up y planificación observacional
        EndpointSpec("followup_request_list", "followup_planning", 46, "GET", "/followup_request", params={"numPerPage": 1}),
        EndpointSpec("followup_request_detail", "followup_planning", 47, "GET", "/followup_request/{followup_request_id}", ["followup_request_id"]),
        EndpointSpec("photometry_request_detail", "followup_planning", 48, "GET", "/photometry_request/{photometry_request_id}", ["photometry_request_id"]),
        EndpointSpec("observation_plan_list", "followup_planning", 49, "GET", "/observation_plan", params={"numPerPage": 1}),
        EndpointSpec("observation_plan_detail", "followup_planning", 50, "GET", "/observation_plan/{observation_plan_request_id}", ["observation_plan_request_id"]),
        EndpointSpec("observation_list", "followup_planning", 51, "GET", "/observation", params={"numPerPage": 1}),

        # 10. Imágenes y contexto visual
        EndpointSpec("thumbnail_detail", "images_visual_context", 52, "GET", "/thumbnail/{thumbnail_id}", ["thumbnail_id"]),
        EndpointSpec("thumbnail_path", "images_visual_context", 53, "GET", "/thumbnailPath"),
        EndpointSpec("source_finder", "images_visual_context", 54, "GET", "/sources/{source_id}/finder", ["source_id"]),

        # 11. Servicios de análisis
        EndpointSpec("analysis_service_list", "analysis_services", 55, "GET", "/analysis_service"),
        EndpointSpec("analysis_service_detail", "analysis_services", 56, "GET", "/analysis_service/{analysis_service_id}", ["analysis_service_id"]),
        EndpointSpec("resource_analysis_list", "analysis_services", 57, "GET", "/{analysis_resource_type}/analysis", ["analysis_resource_type"]),
        EndpointSpec("resource_analysis_detail", "analysis_services", 58, "GET", "/{analysis_resource_type}/analysis/{analysis_id}", ["analysis_resource_type", "analysis_id"]),

        # 12. Metadatos operacionales
        EndpointSpec("groups_list", "operational_metadata", 59, "GET", "/groups"),
        EndpointSpec("group_detail", "operational_metadata", 60, "GET", "/groups/{group_id}", ["group_id"]),
        EndpointSpec("source_groups", "operational_metadata", 61, "GET", "/sources/{source_id}/groups", ["source_id"]),
        EndpointSpec("instrument_list", "operational_metadata", 62, "GET", "/instrument"),
        EndpointSpec("instrument_detail", "operational_metadata", 63, "GET", "/instrument/{instrument_id}", ["instrument_id"]),
        EndpointSpec("telescope_list", "operational_metadata", 64, "GET", "/telescope"),
        EndpointSpec("telescope_detail", "operational_metadata", 65, "GET", "/telescope/{telescope_id}", ["telescope_id"]),
        EndpointSpec("filters_list", "operational_metadata", 66, "GET", "/filters"),
        EndpointSpec("filter_detail", "operational_metadata", 67, "GET", "/filters/{filter_id}", ["filter_id"]),
        EndpointSpec("streams_list", "operational_metadata", 68, "GET", "/streams"),
        EndpointSpec("config", "operational_metadata", 69, "GET", "/config"),
    ]
def sanitize_label(label: str) -> str:
    """Convert a human-readable run label into a safe folder-name fragment."""
    return (
        label.strip()
        .lower()
        .replace(" ", "_")
        .replace("/", "_")
        .replace("\\", "_")
    )

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit availability of SkyPortal API endpoints."
    )

    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"SkyPortal API base URL. Default: {DEFAULT_BASE_URL}",
    )

    parser.add_argument(
        "--output-dir",
        default="data/raw/skyportal/endpoint_audit",
        help="Base output directory. Default: data/raw/skyportal/endpoint_audit",
    )
    parser.add_argument(
        "--run-label",
        default=None,
        help="Optional semantic label for the run, e.g. initial, full, source_level.",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=20,
        help="Request timeout in seconds. Default: 20",
    )

    parser.add_argument(
        "--sleep",
        type=float,
        default=0.2,
        help="Sleep time between requests in seconds. Default: 0.2",
    )

    parser.add_argument(
        "--save-responses",
        action="store_true",
        help="Save full endpoint responses. Disabled by default.",
    )

    parser.add_argument(
        "--category",
        default=None,
        help="Audit only one endpoint category, e.g. inventory, photometry, classifications.",
    )

    # Common sample identifiers
    parser.add_argument("--source-id", default=None, help="Example SkyPortal source ID.")
    parser.add_argument("--candidate-id", default=None, help="Example candidate ID.")
    parser.add_argument("--resource-type", default="sources", help="Resource type for comments/annotations. Default: sources.")
    parser.add_argument("--resource-id", default=None, help="Resource ID for comments/annotations. Defaults to source ID if omitted.")

    # Optional detailed identifiers
    parser.add_argument("--photometry-id", default=None)
    parser.add_argument("--photometric-series-id", default=None)
    parser.add_argument("--spectrum-id", default=None)
    parser.add_argument("--classification-id", default=None)
    parser.add_argument("--taxonomy-id", default=None)
    parser.add_argument("--comment-id", default=None)
    parser.add_argument("--annotation-id", default=None)

    # Catalog / GCN / localization
    parser.add_argument("--catalog-name", default=None)
    parser.add_argument("--catalog-id", default=None)
    parser.add_argument("--dateobs", default=None, help="Example GCN dateobs.")
    parser.add_argument("--gcnevent-id", default=None)
    parser.add_argument("--notice-id", default=None)
    parser.add_argument("--localization-name", default=None)
    parser.add_argument("--localization-id", default=None)

    # Follow-up / observation / images / analysis / operational metadata
    parser.add_argument("--followup-request-id", default=None)
    parser.add_argument("--photometry-request-id", default=None)
    parser.add_argument("--observation-plan-request-id", default=None)
    parser.add_argument("--thumbnail-id", default=None)
    parser.add_argument("--analysis-service-id", default=None)
    parser.add_argument("--analysis-resource-type", default=None)
    parser.add_argument("--analysis-id", default=None)
    parser.add_argument("--group-id", default=None)
    parser.add_argument("--instrument-id", default=None)
    parser.add_argument("--telescope-id", default=None)
    parser.add_argument("--filter-id", default=None)

    return parser.parse_args()


def build_context(args: argparse.Namespace) -> dict[str, str | None]:
    """Build context dictionary used to render endpoint path templates."""
    resource_id = args.resource_id or args.source_id

    return {
        "source_id": args.source_id,
        "candidate_id": args.candidate_id,
        "resource_type": args.resource_type,
        "resource_id": resource_id,
        "photometry_id": args.photometry_id,
        "photometric_series_id": args.photometric_series_id,
        "spectrum_id": args.spectrum_id,
        "classification_id": args.classification_id,
        "taxonomy_id": args.taxonomy_id,
        "comment_id": args.comment_id,
        "annotation_id": args.annotation_id,
        "catalog_name": args.catalog_name,
        "catalog_id": args.catalog_id,
        "dateobs": args.dateobs,
        "gcnevent_id": args.gcnevent_id,
        "notice_id": args.notice_id,
        "localization_name": args.localization_name,
        "localization_id": args.localization_id,
        "followup_request_id": args.followup_request_id,
        "photometry_request_id": args.photometry_request_id,
        "observation_plan_request_id": args.observation_plan_request_id,
        "thumbnail_id": args.thumbnail_id,
        "analysis_service_id": args.analysis_service_id,
        "analysis_resource_type": args.analysis_resource_type,
        "analysis_id": args.analysis_id,
        "group_id": args.group_id,
        "instrument_id": args.instrument_id,
        "telescope_id": args.telescope_id,
        "filter_id": args.filter_id,
    }


def main() -> None:
    args = parse_args()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if args.run_label:
        label = sanitize_label(args.run_label)
        run_name = f"endpoint_audit_{label}_{timestamp}"
    else:
        run_name = f"endpoint_audit_{timestamp}"

    run_dir = Path(args.output_dir) / run_name
    run_dir.mkdir(parents=True, exist_ok=True)

    responses_dir = run_dir / "responses"
    if args.save_responses:
        responses_dir.mkdir(parents=True, exist_ok=True)

    setup_logging(run_dir)

    token = get_token()

    session = requests.Session()
    session.headers.update({"Authorization": f"token {token}"})

    endpoints = get_endpoint_specs()

    if args.category:
        endpoints = [ep for ep in endpoints if ep.category == args.category]

    context = build_context(args)

    logging.info("Starting endpoint audit")
    logging.info("Base URL: %s", args.base_url)
    logging.info("Number of endpoints to audit: %s", len(endpoints))
    logging.info("Output directory: %s", run_dir)

    results: list[dict[str, Any]] = []

    for endpoint in endpoints:
        logging.info("Auditing [%s] %s", endpoint.category, endpoint.name)

        result = audit_endpoint(
            session=session,
            base_url=args.base_url.rstrip("/"),
            endpoint=endpoint,
            context=context,
            timeout=args.timeout,
            save_responses=args.save_responses,
            responses_dir=responses_dir,
        )

        results.append(result)

        if result["skipped"]:
            logging.info("Skipped %s: %s", endpoint.name, result["skip_reason"])
        else:
            logging.info(
                "Result %s: %s | HTTP %s",
                endpoint.name,
                result["status"],
                result["http_status_code"],
            )

        time.sleep(args.sleep)

    json_file = run_dir / "endpoint_status.json"
    csv_file = run_dir / "endpoint_status.csv"

    with json_file.open("w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)

    df = pd.DataFrame(results)
    df.to_csv(csv_file, index=False)

    summary = {
        "run_id": run_name,
        "run_label": args.run_label,
        "total": len(results),
        "success": int((df["status"] == "success").sum()),
        "skipped": int((df["status"] == "skipped").sum()),
        "http_errors": int(df["status"].astype(str).str.startswith("http_").sum()),
        "request_errors": int((df["status"] == "request_error").sum()),
        "output_dir": str(run_dir),
    }

    summary_file = run_dir / "summary.json"
    with summary_file.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    logging.info("Audit complete")
    logging.info("Summary: %s", summary)
    logging.info("Saved CSV to %s", csv_file)
    logging.info("Saved JSON to %s", json_file)


if __name__ == "__main__":
    main()
