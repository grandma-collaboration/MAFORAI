"""Shared path helpers for the current project layout."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import SkyPortalConfig


def project_root() -> Path:
    """Return the repository root from the src package location."""
    return Path(__file__).resolve().parents[3]


def resolve_project_path(path_value: str | Path) -> Path:
    """Resolve a project-relative path against the repository root."""
    path = Path(path_value)
    if path.is_absolute():
        return path
    return project_root() / path


def raw_root_dir(config: "SkyPortalConfig") -> Path:
    """Return the raw SkyPortal root directory as an absolute path."""
    return resolve_project_path(config.paths.raw_root)


def inventory_output_dir(config: "SkyPortalConfig") -> Path:
    """Return the inventory base output directory as an absolute path."""
    return resolve_project_path(config.paths.inventory)


def endpoint_audit_output_dir(config: "SkyPortalConfig") -> Path:
    """Return the endpoint-audit base output directory as an absolute path."""
    return resolve_project_path(config.paths.endpoint_audit)


def source_bundles_output_dir(config: "SkyPortalConfig") -> Path:
    """Return the reserved source-bundle directory as an absolute path."""
    return resolve_project_path(config.paths.source_bundles)


def build_run_output_dir(base_output_dir: str | Path, run_name: str) -> Path:
    """Build one run directory under a base output directory."""
    return resolve_project_path(base_output_dir) / run_name
