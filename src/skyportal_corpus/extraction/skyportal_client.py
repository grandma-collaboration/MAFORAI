"""Shared HTTP client helpers for the current SkyPortal workflow."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

import requests

if TYPE_CHECKING:
    from ..core.config import SkyPortalConfig


@dataclass(frozen=True)
class JsonRequestMetadata:
    """Structured metadata for one JSON API request."""

    url: str
    params: dict[str, Any]
    http_status_code: int | None
    elapsed_seconds: float | None
    json_valid: bool
    api_status: str | None
    api_message: str | None
    response_size_chars: int | None
    error: str | None

    def as_dict(self) -> dict[str, Any]:
        """Return a dict form that is convenient for manifests and logs."""
        return {
            "url": self.url,
            "params": self.params,
            "http_status_code": self.http_status_code,
            "elapsed_seconds": self.elapsed_seconds,
            "json_valid": self.json_valid,
            "api_status": self.api_status,
            "api_message": self.api_message,
            "response_size_chars": self.response_size_chars,
            "error": self.error,
        }


def load_dotenv_if_available() -> None:
    """Load `.env` if python-dotenv is available."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass


def get_api_token(token_env_var: str = "SKYPORTAL_API_TOKEN") -> str:
    """Read the SkyPortal API token from environment variables."""
    load_dotenv_if_available()

    token = os.getenv(token_env_var)
    if not token:
        raise ValueError(
            f"{token_env_var} is not set. "
            "Export it manually or create a local .env file."
        )

    return token


def create_authenticated_session(
    token: str | None = None,
    token_env_var: str = "SKYPORTAL_API_TOKEN",
) -> requests.Session:
    """Create a requests session with SkyPortal token authentication."""
    resolved_token = token or get_api_token(token_env_var=token_env_var)

    session = requests.Session()
    session.headers.update({"Authorization": f"token {resolved_token}"})
    return session


def build_api_url(base_url: str, path: str) -> str:
    """Build one API URL from a base URL and an endpoint path."""
    clean_base = base_url.rstrip("/")
    clean_path = path if path.startswith("/") else f"/{path}"
    return f"{clean_base}{clean_path}"


def parse_json_response(
    response: requests.Response,
    *,
    url: str,
    params: dict[str, Any] | None = None,
    elapsed_seconds: float | None = None,
) -> tuple[Any | None, JsonRequestMetadata]:
    """Parse one HTTP response and summarize basic JSON/API status fields."""
    metadata = JsonRequestMetadata(
        url=url,
        params=dict(params or {}),
        http_status_code=response.status_code,
        elapsed_seconds=round(elapsed_seconds, 3) if elapsed_seconds is not None else None,
        json_valid=False,
        api_status=None,
        api_message=None,
        response_size_chars=len(response.text) if response.text is not None else 0,
        error=None,
    )

    try:
        payload = response.json()
    except ValueError:
        return None, replace(metadata, error="Response is not valid JSON")

    api_status = payload.get("status") if isinstance(payload, dict) else None
    api_message = payload.get("message") if isinstance(payload, dict) else None

    normalized = replace(
        metadata,
        json_valid=True,
        api_status=api_status,
        api_message=api_message,
    )

    if response.status_code == 200:
        return payload, normalized

    return payload, replace(
        normalized,
        error=(
            f"HTTP {response.status_code}: "
            f"{api_message if api_message else 'unknown'}"
        ),
    )


def get_json_with_retries(
    session: requests.Session,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    timeout_seconds: int = 30,
    max_retries: int = 3,
    retry_backoff_seconds: float = 2.0,
    logger: logging.Logger | None = None,
) -> tuple[Any | None, JsonRequestMetadata]:
    """Perform one GET request with retries and basic JSON/HTTP error handling."""
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if max_retries <= 0:
        raise ValueError("max_retries must be positive")
    if retry_backoff_seconds < 0:
        raise ValueError("retry_backoff_seconds must be >= 0")

    request_params = dict(params or {})
    active_logger = logger or logging.getLogger(__name__)

    metadata = JsonRequestMetadata(
        url=url,
        params=request_params,
        http_status_code=None,
        elapsed_seconds=None,
        json_valid=False,
        api_status=None,
        api_message=None,
        response_size_chars=None,
        error=None,
    )

    for attempt in range(1, max_retries + 1):
        start = time.perf_counter()

        try:
            response = session.get(url, params=request_params, timeout=timeout_seconds)
            elapsed = time.perf_counter() - start

            payload, response_metadata = parse_json_response(
                response,
                url=url,
                params=request_params,
                elapsed_seconds=elapsed,
            )

            if response.status_code == 200 and response_metadata.json_valid:
                return payload, response_metadata

            metadata = response_metadata
            active_logger.warning(
                "HTTP/JSON error on attempt %s/%s: %s",
                attempt,
                max_retries,
                response_metadata.error,
            )

        except requests.exceptions.RequestException as exc:
            elapsed = time.perf_counter() - start
            metadata = JsonRequestMetadata(
                url=url,
                params=request_params,
                http_status_code=None,
                elapsed_seconds=round(elapsed, 3),
                json_valid=False,
                api_status=None,
                api_message=None,
                response_size_chars=None,
                error=str(exc),
            )
            active_logger.warning(
                "Request failed on attempt %s/%s: %s",
                attempt,
                max_retries,
                exc,
            )

        if attempt < max_retries:
            time.sleep(retry_backoff_seconds * attempt)

    return None, metadata


@dataclass
class SkyPortalClient:
    """Small wrapper around a token-authenticated SkyPortal session."""

    base_url: str
    session: requests.Session
    default_timeout_seconds: int = 30
    default_max_retries: int = 3
    retry_backoff_seconds: float = 2.0

    @classmethod
    def from_config(
        cls,
        config: "SkyPortalConfig",
        *,
        token: str | None = None,
    ) -> "SkyPortalClient":
        """Create a client from the shared SkyPortal config."""
        return cls(
            base_url=config.skyportal.base_url,
            session=create_authenticated_session(
                token=token,
                token_env_var=config.skyportal.auth.token_env_var,
            ),
            default_timeout_seconds=config.http_defaults.timeout_seconds,
            default_max_retries=config.http_defaults.max_retries,
        )

    def get_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        timeout_seconds: int | None = None,
        max_retries: int | None = None,
        retry_backoff_seconds: float | None = None,
        logger: logging.Logger | None = None,
    ) -> tuple[Any | None, JsonRequestMetadata]:
        """Perform a GET request relative to the configured base URL."""
        url = build_api_url(self.base_url, path)
        return get_json_with_retries(
            session=self.session,
            url=url,
            params=params,
            timeout_seconds=(
                timeout_seconds
                if timeout_seconds is not None
                else self.default_timeout_seconds
            ),
            max_retries=(
                max_retries
                if max_retries is not None
                else self.default_max_retries
            ),
            retry_backoff_seconds=(
                retry_backoff_seconds
                if retry_backoff_seconds is not None
                else self.retry_backoff_seconds
            ),
            logger=logger,
        )
