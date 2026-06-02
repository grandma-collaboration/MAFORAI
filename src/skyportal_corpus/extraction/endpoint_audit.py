"""Operational logic for SkyPortal endpoint-availability audits."""

from __future__ import annotations

import argparse
import csv
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from ..core import (
    build_run_output_dir,
    endpoint_audit_output_dir,
    load_skyportal_config,
)
from .skyportal_client import SkyPortalClient, build_api_url


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


def setup_endpoint_audit_logging(output_dir: Path) -> None:
    """Configure logging to console and file for one audit run."""
    log_file = output_dir / "endpoint_audit.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )


def safe_path_value(value: str) -> str:
    """URL-encode one path component safely."""
    return quote(str(value), safe="")


def render_path(path_template: str, context: dict[str, str]) -> str:
    """Render an endpoint path by replacing placeholders with context values."""
    rendered = path_template

    for key, value in context.items():
        rendered = rendered.replace("{" + key + "}", safe_path_value(value))

    return rendered


def missing_context(endpoint: EndpointSpec, context: dict[str, str | None]) -> list[str]:
    """Return required context keys that are missing."""
    missing: list[str] = []

    for key in endpoint.required_context:
        if not context.get(key):
            missing.append(key)

    return missing


def summarize_payload(payload: Any) -> dict[str, Any]:
    """Summarize response structure without storing the full payload."""
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


def save_results_csv(path: Path, results: list[dict[str, Any]]) -> None:
    """Save audit results to CSV without requiring pandas."""
    if not results:
        path.write_text("", encoding="utf-8")
        return

    fieldnames = list(results[0].keys())

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)


def build_summary(
    *,
    run_name: str,
    run_label: str | None,
    config_file: Path,
    base_url: str,
    run_dir: Path,
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build aggregate metrics for one audit run."""
    statuses = [str(result.get("status")) for result in results]

    return {
        "run_id": run_name,
        "run_label": run_label,
        "config_file": str(config_file),
        "base_url": base_url,
        "total": len(results),
        "success": sum(status == "success" for status in statuses),
        "skipped": sum(status == "skipped" for status in statuses),
        "http_errors": sum(status.startswith("http_") for status in statuses),
        "request_errors": sum(status == "request_error" for status in statuses),
        "output_dir": str(run_dir),
    }


def audit_endpoint(
    session: requests.Session,
    base_url: str,
    endpoint: EndpointSpec,
    context: dict[str, str | None],
    timeout: int,
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
    url = build_api_url(base_url, path)
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
            result.update(summarize_payload(payload))

            if response.status_code == 200:
                if isinstance(payload, dict) and payload.get("status") == "success":
                    result["status"] = "success"
                elif isinstance(payload, dict) and payload.get("status"):
                    result["status"] = f"api_{payload.get('status')}"
                else:
                    result["status"] = "http_200_json_no_api_status"
            else:
                result["status"] = f"http_{response.status_code}"

        except ValueError:
            result["json_valid"] = False
            result["status"] = f"http_{response.status_code}_non_json"
            result["error"] = "Response is not valid JSON"

    except requests.exceptions.RequestException as exc:
        elapsed = time.perf_counter() - start
        result["elapsed_seconds"] = round(elapsed, 3)
        result["status"] = "request_error"
        result["error"] = str(exc)

    return result


def get_endpoint_specs() -> list[EndpointSpec]:
    """Return the current audited endpoint list."""
    return [
        EndpointSpec("sources", "inventory", 1, "GET", "/sources", params={"numPerPage": 1}),
        EndpointSpec("source_detail", "inventory", 2, "GET", "/sources/{source_id}", ["source_id"]),
        EndpointSpec("candidates", "inventory", 3, "GET", "/candidates", params={"numPerPage": 1}),
        EndpointSpec("candidate_detail", "inventory", 4, "GET", "/candidates/{candidate_id}", ["candidate_id"]),
        EndpointSpec("source_exists", "inventory", 5, "GET", "/source_exists/{source_id}", ["source_id"]),
        EndpointSpec("source_photometry_flux", "photometry", 6, "GET", "/sources/{source_id}/photometry", ["source_id"], {"format": "flux"}),
        EndpointSpec("source_photometry_mag", "photometry", 6, "GET", "/sources/{source_id}/photometry", ["source_id"], {"format": "mag"}),
        EndpointSpec("source_phot_stat", "photometry", 7, "GET", "/sources/{source_id}/phot_stat", ["source_id"]),
        EndpointSpec("photometry_detail", "photometry", 8, "GET", "/photometry/{photometry_id}", ["photometry_id"]),
        EndpointSpec("photometry_range", "photometry", 9, "GET", "/photometry/range"),
        EndpointSpec("photometric_series_detail", "photometry", 10, "GET", "/photometric_series/{photometric_series_id}", ["photometric_series_id"]),
        EndpointSpec("source_spectra", "spectroscopy", 11, "GET", "/sources/{source_id}/spectra", ["source_id"]),
        EndpointSpec("spectrum_detail", "spectroscopy", 12, "GET", "/spectrum/{spectrum_id}", ["spectrum_id"]),
        EndpointSpec("spectrum_list", "spectroscopy", 13, "GET", "/spectrum", params={"numPerPage": 1}),
        EndpointSpec("spectrum_range", "spectroscopy", 14, "GET", "/spectrum/range"),
        EndpointSpec("source_classifications", "classifications", 15, "GET", "/sources/{source_id}/classifications", ["source_id"]),
        EndpointSpec("classification_detail", "classifications", 16, "GET", "/classification/{classification_id}", ["classification_id"]),
        EndpointSpec("classification_list", "classifications", 17, "GET", "/classification", params={"numPerPage": 1}),
        EndpointSpec("taxonomy_list", "classifications", 18, "GET", "/taxonomy"),
        EndpointSpec("taxonomy_detail", "classifications", 19, "GET", "/taxonomy/{taxonomy_id}", ["taxonomy_id"]),
        EndpointSpec("resource_comments", "comments_annotations_tags", 20, "GET", "/{resource_type}/{resource_id}/comments", ["resource_type", "resource_id"]),
        EndpointSpec("resource_comment_detail", "comments_annotations_tags", 21, "GET", "/{resource_type}/{resource_id}/comments/{comment_id}", ["resource_type", "resource_id", "comment_id"]),
        EndpointSpec("resource_annotations", "comments_annotations_tags", 22, "GET", "/{resource_type}/{resource_id}/annotations", ["resource_type", "resource_id"]),
        EndpointSpec("resource_annotation_detail", "comments_annotations_tags", 23, "GET", "/{resource_type}/{resource_id}/annotations/{annotation_id}", ["resource_type", "resource_id", "annotation_id"]),
        EndpointSpec("objtag", "comments_annotations_tags", 24, "GET", "/objtag"),
        EndpointSpec("objtagoption", "comments_annotations_tags", 25, "GET", "/objtagoption"),
        EndpointSpec("source_tns", "astronomical_context", 26, "GET", "/sources/{source_id}/tns", ["source_id"]),
        EndpointSpec("source_position", "astronomical_context", 27, "GET", "/sources/{source_id}/position", ["source_id"]),
        EndpointSpec("source_offsets", "astronomical_context", 28, "GET", "/sources/{source_id}/offsets", ["source_id"]),
        EndpointSpec("source_color_mag", "astronomical_context", 29, "GET", "/sources/{source_id}/color_mag", ["source_id"]),
        EndpointSpec("galaxy_catalog", "astronomical_context", 30, "GET", "/galaxy_catalog/{catalog_name}", ["catalog_name"]),
        EndpointSpec("spatial_catalog_list", "astronomical_context", 31, "GET", "/spatial_catalog"),
        EndpointSpec("spatial_catalog_detail", "astronomical_context", 32, "GET", "/spatial_catalog/{catalog_id}", ["catalog_id"]),
        EndpointSpec("gcn_event_list", "gcn_multimessenger", 33, "GET", "/gcn_event", params={"numPerPage": 1}),
        EndpointSpec("gcn_event_detail_by_dateobs", "gcn_multimessenger", 34, "GET", "/gcn_event/{dateobs}", ["dateobs"]),
        EndpointSpec("sources_in_gcn", "gcn_multimessenger", 35, "GET", "/sources_in_gcn/{dateobs}", ["dateobs"]),
        EndpointSpec("source_in_gcn_detail", "gcn_multimessenger", 36, "GET", "/sources_in_gcn/{dateobs}/{source_id}", ["dateobs", "source_id"]),
        EndpointSpec("associated_gcns", "gcn_multimessenger", 37, "GET", "/associated_gcns/{source_id}", ["source_id"]),
        EndpointSpec("gcn_observation_plan_requests", "gcn_multimessenger", 38, "GET", "/gcn_event/{gcnevent_id}/observation_plan_requests", ["gcnevent_id"]),
        EndpointSpec("gcn_survey_efficiency", "gcn_multimessenger", 39, "GET", "/gcn_event/{gcnevent_id}/survey_efficiency", ["gcnevent_id"]),
        EndpointSpec("gcn_catalog_query", "gcn_multimessenger", 40, "GET", "/gcn_event/{gcnevent_id}/catalog_query", ["gcnevent_id"]),
        EndpointSpec("gcn_notice_download", "gcn_multimessenger", 41, "GET", "/gcn_event/{dateobs}/notice/{notice_id}/download", ["dateobs", "notice_id"]),
        EndpointSpec("localization_by_dateobs_name", "localization_observability", 42, "GET", "/localization/{dateobs}/name/{localization_name}", ["dateobs", "localization_name"]),
        EndpointSpec("localization_download", "localization_observability", 43, "GET", "/localization/{dateobs}/name/{localization_name}/download", ["dateobs", "localization_name"]),
        EndpointSpec("localization_observability", "localization_observability", 44, "GET", "/localization/{localization_id}/observability", ["localization_id"]),
        EndpointSpec("source_observability", "localization_observability", 45, "GET", "/sources/{source_id}/observability", ["source_id"]),
        EndpointSpec("followup_request_list", "followup_planning", 46, "GET", "/followup_request", params={"numPerPage": 1}),
        EndpointSpec("followup_request_detail", "followup_planning", 47, "GET", "/followup_request/{followup_request_id}", ["followup_request_id"]),
        EndpointSpec("photometry_request_detail", "followup_planning", 48, "GET", "/photometry_request/{photometry_request_id}", ["photometry_request_id"]),
        EndpointSpec("observation_plan_list", "followup_planning", 49, "GET", "/observation_plan", params={"numPerPage": 1}),
        EndpointSpec("observation_plan_detail", "followup_planning", 50, "GET", "/observation_plan/{observation_plan_request_id}", ["observation_plan_request_id"]),
        EndpointSpec("observation_list", "followup_planning", 51, "GET", "/observation", params={"numPerPage": 1}),
        EndpointSpec("thumbnail_detail", "images_visual_context", 52, "GET", "/thumbnail/{thumbnail_id}", ["thumbnail_id"]),
        EndpointSpec("thumbnail_path", "images_visual_context", 53, "GET", "/thumbnailPath"),
        EndpointSpec("source_finder", "images_visual_context", 54, "GET", "/sources/{source_id}/finder", ["source_id"]),
        EndpointSpec("analysis_service_list", "analysis_services", 55, "GET", "/analysis_service"),
        EndpointSpec("analysis_service_detail", "analysis_services", 56, "GET", "/analysis_service/{analysis_service_id}", ["analysis_service_id"]),
        EndpointSpec("resource_analysis_list", "analysis_services", 57, "GET", "/{analysis_resource_type}/analysis", ["analysis_resource_type"]),
        EndpointSpec("resource_analysis_detail", "analysis_services", 58, "GET", "/{analysis_resource_type}/analysis/{analysis_id}", ["analysis_resource_type", "analysis_id"]),
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


def build_context(
    args: argparse.Namespace,
    sample_context: Any,
) -> dict[str, str | None]:
    """Build context dictionary used to render endpoint path templates."""
    source_id = args.source_id or sample_context.source_id
    candidate_id = args.candidate_id or sample_context.candidate_id
    resource_type = args.resource_type or sample_context.resource_type
    resource_id = args.resource_id or sample_context.resource_id or source_id
    dateobs = args.dateobs or sample_context.dateobs

    return {
        "source_id": source_id,
        "candidate_id": candidate_id,
        "resource_type": resource_type,
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
        "dateobs": dateobs,
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


def run_endpoint_audit(args: argparse.Namespace) -> None:
    """Run one endpoint-availability audit from parsed CLI args."""
    config = load_skyportal_config(args.config)
    effective_base_url = (args.base_url or config.skyportal.base_url).rstrip("/")
    effective_output_dir = args.output_dir or str(endpoint_audit_output_dir(config))
    effective_timeout = (
        args.timeout
        if args.timeout is not None
        else config.audit.defaults.timeout_seconds
    )
    effective_sleep = (
        args.sleep
        if args.sleep is not None
        else config.audit.defaults.sleep_seconds
    )

    if effective_timeout <= 0:
        raise ValueError("--timeout must be positive")

    if effective_sleep < 0:
        raise ValueError("--sleep must be >= 0")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if args.run_label:
        label = sanitize_label(args.run_label)
        run_name = f"endpoint_audit_{label}_{timestamp}"
    else:
        run_name = f"endpoint_audit_{timestamp}"

    run_dir = build_run_output_dir(effective_output_dir, run_name)
    run_dir.mkdir(parents=True, exist_ok=True)

    setup_endpoint_audit_logging(run_dir)

    client = SkyPortalClient.from_config(config)
    client.base_url = effective_base_url

    endpoints = get_endpoint_specs()

    if args.category:
        endpoints = [endpoint for endpoint in endpoints if endpoint.category == args.category]

    context = build_context(args, config.audit.sample_context)

    logging.info("Starting endpoint audit")
    logging.info("Config file: %s", config.source_path)
    logging.info("Base URL: %s", effective_base_url)
    logging.info("Number of endpoints to audit: %s", len(endpoints))
    logging.info("Output directory: %s", run_dir)

    results: list[dict[str, Any]] = []

    for endpoint in endpoints:
        logging.info("Auditing [%s] %s", endpoint.category, endpoint.name)

        result = audit_endpoint(
            session=client.session,
            base_url=client.base_url,
            endpoint=endpoint,
            context=context,
            timeout=effective_timeout,
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

        time.sleep(effective_sleep)

    json_file = run_dir / "endpoint_status.json"
    csv_file = run_dir / "endpoint_status.csv"

    with json_file.open("w", encoding="utf-8") as handle:
        json.dump(results, handle, ensure_ascii=False, indent=2, default=str)

    save_results_csv(csv_file, results)

    summary = build_summary(
        run_name=run_name,
        run_label=args.run_label,
        config_file=config.source_path,
        base_url=effective_base_url,
        run_dir=run_dir,
        results=results,
    )

    summary_file = run_dir / "summary.json"
    with summary_file.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)

    logging.info("Audit complete")
    logging.info("Summary: %s", summary)
    logging.info("Saved CSV to %s", csv_file)
    logging.info("Saved JSON to %s", json_file)
