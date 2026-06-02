"""Reusable loader for versioned SkyPortal runtime configuration."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml

from .paths import project_root


class ConfigError(ValueError):
    """Raised when the config file is missing or structurally invalid."""


@dataclass(frozen=True)
class SkyPortalAuthConfig:
    token_env_var: str


@dataclass(frozen=True)
class SkyPortalApiConfig:
    base_url: str
    auth: SkyPortalAuthConfig


@dataclass(frozen=True)
class PathsConfig:
    raw_root: str
    endpoint_audit: str
    inventory: str
    source_bundles: str


@dataclass(frozen=True)
class HttpDefaults:
    timeout_seconds: int
    max_retries: int


@dataclass(frozen=True)
class AuditDefaults:
    timeout_seconds: int
    sleep_seconds: float


@dataclass(frozen=True)
class AuditSampleContext:
    source_id: str | None
    candidate_id: str | None
    resource_type: str
    resource_id: str | None
    dateobs: str | None


@dataclass(frozen=True)
class AuditConfig:
    defaults: AuditDefaults
    sample_context: AuditSampleContext


@dataclass(frozen=True)
class InventoryDefaults:
    num_per_page: int
    start_page: int
    max_pages: int
    timeout_seconds: int
    max_retries: int
    sleep_seconds: float


@dataclass(frozen=True)
class InventoryProfile:
    name: str
    description: str
    run_label: str
    max_pages: int
    query_template: str | None
    query_params: dict[str, str]


@dataclass(frozen=True)
class InventoryConfig:
    defaults: InventoryDefaults
    shared_query_params: dict[str, dict[str, str]]
    profiles: dict[str, InventoryProfile]


@dataclass(frozen=True)
class SkyPortalConfig:
    source_path: Path
    version: int
    skyportal: SkyPortalApiConfig
    paths: PathsConfig
    http_defaults: HttpDefaults
    audit: AuditConfig
    inventory: InventoryConfig


@dataclass(frozen=True)
class ResolvedInventoryProfile:
    name: str
    description: str
    run_label: str
    output_dir: str
    num_per_page: int
    start_page: int
    max_pages: int
    timeout_seconds: int
    max_retries: int
    sleep_seconds: float
    query_params: dict[str, str]


def default_skyportal_config_path() -> Path:
    """Return the canonical config path for the current project layout."""
    return project_root() / "configs" / "extraction" / "skyportal.yaml"


def load_skyportal_config(config_path: str | Path | None = None) -> SkyPortalConfig:
    """Load, validate, and normalize the shared SkyPortal config."""
    path = Path(config_path) if config_path is not None else default_skyportal_config_path()
    path = path.resolve()

    if not path.exists():
        raise ConfigError(f"SkyPortal config file not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)

    if not isinstance(raw, dict):
        raise ConfigError(f"Expected top-level YAML mapping in {path}")

    version = _require_int(raw, "version")

    skyportal_raw = _require_mapping(raw, "skyportal")
    auth_raw = _require_mapping(skyportal_raw, "auth", parent_path="skyportal")

    paths_raw = _require_mapping(raw, "paths")
    http_raw = _require_mapping(raw, "http_defaults")
    audit_raw = _require_mapping(raw, "audit")
    audit_defaults_raw = _require_mapping(audit_raw, "defaults", parent_path="audit")
    audit_sample_raw = _require_mapping(audit_raw, "sample_context", parent_path="audit")

    inventory_raw = _require_mapping(raw, "inventory")
    inventory_defaults_raw = _require_mapping(
        inventory_raw,
        "defaults",
        parent_path="inventory",
    )
    shared_query_params = _require_mapping(
        inventory_raw,
        "shared_query_params",
        parent_path="inventory",
    )
    profiles_raw = _require_mapping(inventory_raw, "profiles", parent_path="inventory")

    config = SkyPortalConfig(
        source_path=path,
        version=version,
        skyportal=SkyPortalApiConfig(
            base_url=_require_str(skyportal_raw, "base_url", parent_path="skyportal").rstrip("/"),
            auth=SkyPortalAuthConfig(
                token_env_var=_require_str(auth_raw, "token_env_var", parent_path="skyportal.auth")
            ),
        ),
        paths=PathsConfig(
            raw_root=_require_str(paths_raw, "raw_root", parent_path="paths"),
            endpoint_audit=_require_str(paths_raw, "endpoint_audit", parent_path="paths"),
            inventory=_require_str(paths_raw, "inventory", parent_path="paths"),
            source_bundles=_require_str(paths_raw, "source_bundles", parent_path="paths"),
        ),
        http_defaults=HttpDefaults(
            timeout_seconds=_require_int(http_raw, "timeout_seconds", parent_path="http_defaults"),
            max_retries=_require_int(http_raw, "max_retries", parent_path="http_defaults"),
        ),
        audit=AuditConfig(
            defaults=AuditDefaults(
                timeout_seconds=_require_int(
                    audit_defaults_raw,
                    "timeout_seconds",
                    parent_path="audit.defaults",
                ),
                sleep_seconds=_require_float(
                    audit_defaults_raw,
                    "sleep_seconds",
                    parent_path="audit.defaults",
                ),
            ),
            sample_context=AuditSampleContext(
                source_id=_optional_str(
                    audit_sample_raw,
                    "source_id",
                    parent_path="audit.sample_context",
                ),
                candidate_id=_optional_str(
                    audit_sample_raw,
                    "candidate_id",
                    parent_path="audit.sample_context",
                ),
                resource_type=_require_str(
                    audit_sample_raw,
                    "resource_type",
                    parent_path="audit.sample_context",
                ),
                resource_id=_optional_str(
                    audit_sample_raw,
                    "resource_id",
                    parent_path="audit.sample_context",
                ),
                dateobs=_optional_str(
                    audit_sample_raw,
                    "dateobs",
                    parent_path="audit.sample_context",
                ),
            ),
        ),
        inventory=InventoryConfig(
            defaults=InventoryDefaults(
                num_per_page=_require_int(
                    inventory_defaults_raw,
                    "num_per_page",
                    parent_path="inventory.defaults",
                ),
                start_page=_require_int(
                    inventory_defaults_raw,
                    "start_page",
                    parent_path="inventory.defaults",
                ),
                max_pages=_require_int(
                    inventory_defaults_raw,
                    "max_pages",
                    parent_path="inventory.defaults",
                ),
                timeout_seconds=_require_int(
                    inventory_defaults_raw,
                    "timeout_seconds",
                    parent_path="inventory.defaults",
                ),
                max_retries=_require_int(
                    inventory_defaults_raw,
                    "max_retries",
                    parent_path="inventory.defaults",
                ),
                sleep_seconds=_require_float(
                    inventory_defaults_raw,
                    "sleep_seconds",
                    parent_path="inventory.defaults",
                ),
            ),
            shared_query_params=_normalize_query_templates(shared_query_params),
            profiles=_build_inventory_profiles(profiles_raw),
        ),
    )

    _validate_runtime_defaults(config)
    _validate_inventory_profiles(config)
    return config


def resolve_inventory_profile(
    config: SkyPortalConfig,
    profile_name: str,
) -> ResolvedInventoryProfile:
    """Resolve one named inventory profile into effective runtime values."""
    try:
        profile = config.inventory.profiles[profile_name]
    except KeyError as exc:
        available = ", ".join(sorted(config.inventory.profiles))
        raise ConfigError(
            f"Unknown inventory profile '{profile_name}'. Available profiles: {available}"
        ) from exc

    template_params: dict[str, str] = {}

    if profile.query_template is not None:
        try:
            template_params = config.inventory.shared_query_params[profile.query_template]
        except KeyError as exc:
            raise ConfigError(
                f"Inventory profile '{profile.name}' references missing query template "
                f"'{profile.query_template}'"
            ) from exc

    effective_query_params = {
        **template_params,
        **profile.query_params,
    }

    defaults = config.inventory.defaults

    return ResolvedInventoryProfile(
        name=profile.name,
        description=profile.description,
        run_label=profile.run_label,
        output_dir=config.paths.inventory,
        num_per_page=defaults.num_per_page,
        start_page=defaults.start_page,
        max_pages=profile.max_pages,
        timeout_seconds=defaults.timeout_seconds,
        max_retries=defaults.max_retries,
        sleep_seconds=defaults.sleep_seconds,
        query_params=effective_query_params,
    )


def merge_cli_overrides(
    base_config: ResolvedInventoryProfile,
    cli_args: Any,
) -> ResolvedInventoryProfile:
    """Apply CLI overrides on top of a resolved inventory profile."""
    run_label = _get_override(cli_args, "run_label")
    output_dir = _get_override(cli_args, "output_dir")
    num_per_page = _get_override(cli_args, "num_per_page")
    start_page = _get_override(cli_args, "start_page")
    max_pages = _get_override(cli_args, "max_pages")
    timeout_seconds = _get_override(cli_args, "timeout_seconds", "timeout")
    max_retries = _get_override(cli_args, "max_retries")
    sleep_seconds = _get_override(cli_args, "sleep_seconds", "sleep")
    query_params_override = _get_override(cli_args, "query_params")

    if num_per_page is not None and num_per_page <= 0:
        raise ConfigError("CLI override num_per_page must be positive")

    if start_page is not None and start_page <= 0:
        raise ConfigError("CLI override start_page must be positive")

    if max_pages is not None and max_pages < 0:
        raise ConfigError("CLI override max_pages must be >= 0")

    if timeout_seconds is not None and timeout_seconds <= 0:
        raise ConfigError("CLI override timeout_seconds must be positive")

    if max_retries is not None and max_retries <= 0:
        raise ConfigError("CLI override max_retries must be positive")

    if sleep_seconds is not None and sleep_seconds < 0:
        raise ConfigError("CLI override sleep_seconds must be >= 0")

    merged_query_params = dict(base_config.query_params)
    if query_params_override is not None:
        merged_query_params.update(
            _normalize_query_mapping(
                query_params_override,
                dotted_path="cli_args.query_params",
            )
        )

    return replace(
        base_config,
        run_label=run_label or base_config.run_label,
        output_dir=output_dir or base_config.output_dir,
        num_per_page=num_per_page if num_per_page is not None else base_config.num_per_page,
        start_page=start_page if start_page is not None else base_config.start_page,
        max_pages=max_pages if max_pages is not None else base_config.max_pages,
        timeout_seconds=(
            timeout_seconds
            if timeout_seconds is not None
            else base_config.timeout_seconds
        ),
        max_retries=max_retries if max_retries is not None else base_config.max_retries,
        sleep_seconds=(
            float(sleep_seconds)
            if sleep_seconds is not None
            else base_config.sleep_seconds
        ),
        query_params=merged_query_params,
    )


def _build_inventory_profiles(raw_profiles: dict[str, Any]) -> dict[str, InventoryProfile]:
    profiles: dict[str, InventoryProfile] = {}

    for profile_name, profile_raw in raw_profiles.items():
        if not isinstance(profile_raw, dict):
            raise ConfigError(
                f"Expected mapping for inventory.profiles.{profile_name}, "
                f"got {type(profile_raw).__name__}"
            )

        query_template = profile_raw.get("query_template")
        if query_template is not None and not isinstance(query_template, str):
            raise ConfigError(
                f"Expected string or null for inventory.profiles.{profile_name}.query_template"
            )

        query_params = profile_raw.get("query_params", {})
        if not isinstance(query_params, dict):
            raise ConfigError(
                f"Expected mapping for inventory.profiles.{profile_name}.query_params"
            )

        profiles[profile_name] = InventoryProfile(
            name=profile_name,
            description=_require_str(
                profile_raw,
                "description",
                parent_path=f"inventory.profiles.{profile_name}",
            ),
            run_label=_require_str(
                profile_raw,
                "run_label",
                parent_path=f"inventory.profiles.{profile_name}",
            ),
            max_pages=_require_int(
                profile_raw,
                "max_pages",
                parent_path=f"inventory.profiles.{profile_name}",
            ),
            query_template=query_template,
            query_params=_normalize_query_mapping(
                query_params,
                dotted_path=f"inventory.profiles.{profile_name}.query_params",
            ),
        )

    return profiles


def _normalize_query_templates(raw_templates: dict[str, Any]) -> dict[str, dict[str, str]]:
    templates: dict[str, dict[str, str]] = {}

    for template_name, template_raw in raw_templates.items():
        templates[template_name] = _normalize_query_mapping(
            template_raw,
            dotted_path=f"inventory.shared_query_params.{template_name}",
        )

    return templates


def _normalize_query_mapping(raw_mapping: Any, dotted_path: str) -> dict[str, str]:
    if not isinstance(raw_mapping, dict):
        raise ConfigError(f"Expected mapping for {dotted_path}")

    normalized: dict[str, str] = {}

    for key, value in raw_mapping.items():
        if not isinstance(key, str):
            raise ConfigError(f"Expected string key in {dotted_path}")
        if not isinstance(value, str):
            raise ConfigError(
                f"Expected string value for {dotted_path}.{key}, got {type(value).__name__}"
            )
        normalized[key] = value

    return normalized


def _validate_inventory_profiles(config: SkyPortalConfig) -> None:
    if not config.inventory.profiles:
        raise ConfigError("Expected at least one inventory profile in inventory.profiles")

    for profile in config.inventory.profiles.values():
        if profile.max_pages < 0:
            raise ConfigError(
                f"inventory profile '{profile.name}' has invalid max_pages={profile.max_pages}"
            )
        if profile.query_template and (
            profile.query_template not in config.inventory.shared_query_params
        ):
            raise ConfigError(
                f"inventory profile '{profile.name}' references unknown query template "
                f"'{profile.query_template}'"
            )


def _validate_runtime_defaults(config: SkyPortalConfig) -> None:
    if config.http_defaults.timeout_seconds <= 0:
        raise ConfigError("http_defaults.timeout_seconds must be positive")
    if config.http_defaults.max_retries <= 0:
        raise ConfigError("http_defaults.max_retries must be positive")

    if config.audit.defaults.timeout_seconds <= 0:
        raise ConfigError("audit.defaults.timeout_seconds must be positive")
    if config.audit.defaults.sleep_seconds < 0:
        raise ConfigError("audit.defaults.sleep_seconds must be >= 0")

    if config.inventory.defaults.num_per_page <= 0:
        raise ConfigError("inventory.defaults.num_per_page must be positive")
    if config.inventory.defaults.start_page <= 0:
        raise ConfigError("inventory.defaults.start_page must be positive")
    if config.inventory.defaults.max_pages < 0:
        raise ConfigError("inventory.defaults.max_pages must be >= 0")
    if config.inventory.defaults.timeout_seconds <= 0:
        raise ConfigError("inventory.defaults.timeout_seconds must be positive")
    if config.inventory.defaults.max_retries <= 0:
        raise ConfigError("inventory.defaults.max_retries must be positive")
    if config.inventory.defaults.sleep_seconds < 0:
        raise ConfigError("inventory.defaults.sleep_seconds must be >= 0")


def _require_mapping(
    mapping: dict[str, Any],
    key: str,
    parent_path: str | None = None,
) -> dict[str, Any]:
    value = mapping.get(key)
    dotted_path = _join_path(parent_path, key)

    if not isinstance(value, dict):
        raise ConfigError(f"Expected mapping for {dotted_path}")

    return value


def _require_str(
    mapping: dict[str, Any],
    key: str,
    parent_path: str | None = None,
) -> str:
    value = mapping.get(key)
    dotted_path = _join_path(parent_path, key)

    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"Expected non-empty string for {dotted_path}")

    return value


def _optional_str(
    mapping: dict[str, Any],
    key: str,
    parent_path: str | None = None,
) -> str | None:
    value = mapping.get(key)
    dotted_path = _join_path(parent_path, key)

    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigError(f"Expected string or null for {dotted_path}")

    return value


def _require_int(
    mapping: dict[str, Any],
    key: str,
    parent_path: str | None = None,
) -> int:
    value = mapping.get(key)
    dotted_path = _join_path(parent_path, key)

    if not isinstance(value, int) or isinstance(value, bool):
        raise ConfigError(f"Expected integer for {dotted_path}")

    return value


def _require_float(
    mapping: dict[str, Any],
    key: str,
    parent_path: str | None = None,
) -> float:
    value = mapping.get(key)
    dotted_path = _join_path(parent_path, key)

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"Expected numeric value for {dotted_path}")

    return float(value)


def _require_bool(
    mapping: dict[str, Any],
    key: str,
    parent_path: str | None = None,
) -> bool:
    value = mapping.get(key)
    dotted_path = _join_path(parent_path, key)

    if not isinstance(value, bool):
        raise ConfigError(f"Expected boolean for {dotted_path}")

    return value


def _join_path(parent_path: str | None, key: str) -> str:
    if not parent_path:
        return key
    return f"{parent_path}.{key}"


def _get_override(source: Any, *names: str) -> Any:
    for name in names:
        if isinstance(source, dict) and name in source:
            return source[name]
        if hasattr(source, name):
            return getattr(source, name)
    return None
