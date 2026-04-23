"""SecOps workspace tools backed by the business service."""

from __future__ import annotations

import os
from typing import Any

import httpx
from langchain.tools import ToolRuntime, tool
from langgraph.typing import ContextT

from deerflow.agents.thread_state import ThreadState

SECOPS_BIZ_SERVICE_URL_ENV = "SECOPS_BIZ_SERVICE_URL"
DEFAULT_SECOPS_BIZ_SERVICE_URL = "http://localhost:8080"
DEFAULT_SECOPS_DOCKER_BIZ_SERVICE_URL = "http://host.docker.internal:8080"
DEFAULT_HTTP_TIMEOUT_SECONDS = 10.0
ALLOWED_ALERT_STATUSES = {"processing", "processed", "failed"}


def _is_running_in_docker() -> bool:
    return os.path.exists("/.dockerenv")


def _resolve_biz_service_base_url() -> str:
    configured = os.getenv(SECOPS_BIZ_SERVICE_URL_ENV)
    if configured:
        return configured.rstrip("/")
    if _is_running_in_docker():
        return DEFAULT_SECOPS_DOCKER_BIZ_SERVICE_URL
    return DEFAULT_SECOPS_BIZ_SERVICE_URL


def _resolve_alert_id(runtime: ToolRuntime[ContextT, ThreadState], alert_id: str | None) -> str | None:
    if alert_id:
        return alert_id

    if runtime.context and runtime.context.get("alert_id"):
        return str(runtime.context["alert_id"])

    config = getattr(runtime, "config", None)
    configurable = config.get("configurable", {}) if config else {}
    if configurable.get("alert_id"):
        return str(configurable["alert_id"])

    return None


def _format_http_error(prefix: str, error: Exception) -> str:
    if isinstance(error, httpx.HTTPStatusError):
        response = error.response
        return f"{prefix}: biz-service returned HTTP {response.status_code} for {response.request.url}"
    return f"{prefix}: {error}"


def fetch_alert_workspace_context(alert_id: str, *, base_url: str | None = None, timeout: float = DEFAULT_HTTP_TIMEOUT_SECONDS) -> dict[str, Any]:
    resolved_base_url = (base_url or _resolve_biz_service_base_url()).rstrip("/")
    alert_url = f"{resolved_base_url}/api/biz/alerts/{alert_id}"

    with httpx.Client(timeout=timeout) as client:
        alert_response = client.get(alert_url)
        alert_response.raise_for_status()
        alert = alert_response.json()

    return {
        "ok": True,
        "alertId": str(alert_id),
        "alert": alert,
    }


def patch_alert_status(
    alert_id: str,
    status: str,
    *,
    base_url: str | None = None,
    timeout: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    normalized_status = status.strip().lower()
    if normalized_status not in ALLOWED_ALERT_STATUSES:
        raise ValueError("status must be one of processing, processed, failed")

    resolved_base_url = (base_url or _resolve_biz_service_base_url()).rstrip("/")
    status_url = f"{resolved_base_url}/api/biz/alerts/{alert_id}/status"

    with httpx.Client(timeout=timeout) as client:
        response = client.patch(status_url, json={"status": normalized_status})
        response.raise_for_status()
        alert = response.json()

    return {
        "ok": True,
        "alertId": str(alert_id),
        "status": normalized_status,
        "alert": alert,
    }


@tool("get_alert_workspace_context", parse_docstring=True)
def get_alert_workspace_context_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    alert_id: str | None = None,
) -> dict[str, Any]:
    """Load the authoritative alert workspace context from SecOps biz-service.

    Use this tool when you need the latest persisted business data for the active alert.
    It returns the current alert detail from biz-service without local reshaping.

    Args:
        alert_id: Optional alert ID. If omitted, the tool uses the alert bound to the current thread context.
    """
    resolved_alert_id = _resolve_alert_id(runtime, alert_id)
    if resolved_alert_id is None:
        return {
            "ok": False,
            "error": "Missing alert_id. Provide an explicit alert_id or run this tool inside a Copilot thread already bound to an alert.",
        }

    try:
        return fetch_alert_workspace_context(resolved_alert_id)
    except Exception as error:  # noqa: BLE001
        return {
            "ok": False,
            "alertId": str(resolved_alert_id),
            "error": _format_http_error("Failed to load alert workspace context", error),
        }


@tool("update_alert_status", parse_docstring=True)
def update_alert_status_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    status: str,
    alert_id: str | None = None,
) -> dict[str, Any]:
    """Update the current alert status in SecOps biz-service.

    Use this tool after an external action changes the remediation state.

    Args:
        status: One of processing, processed, failed.
        alert_id: Optional alert ID. If omitted, the tool uses the alert bound to the current workspace thread.
    """
    resolved_alert_id = _resolve_alert_id(runtime, alert_id)
    if resolved_alert_id is None:
        return {
            "ok": False,
            "error": "Missing alert_id. Provide an explicit alert_id or run this tool inside a workspace thread already bound to an alert.",
        }

    try:
        return patch_alert_status(resolved_alert_id, status)
    except ValueError as error:
        return {
            "ok": False,
            "alertId": str(resolved_alert_id),
            "error": str(error),
        }
    except Exception as error:  # noqa: BLE001
        return {
            "ok": False,
            "alertId": str(resolved_alert_id),
            "error": _format_http_error("Failed to update alert status", error),
        }
