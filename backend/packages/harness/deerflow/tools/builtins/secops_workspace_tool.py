"""SecOps workspace tools backed by the business service."""

from __future__ import annotations

import json
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


def _parse_jsonish(value: Any) -> Any:
    if value is None or value == "":
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _normalize_alert(alert: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(alert)
    normalized["aiAnalysis"] = _parse_jsonish(normalized.get("aiAnalysis"))
    normalized["defaultParams"] = _parse_jsonish(normalized.get("defaultParams"))
    return normalized


def _normalize_execution(record: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(record)
    for key in ("params", "externalPayload", "executionPlan", "executionReport", "logs"):
        normalized[key] = _parse_jsonish(normalized.get(key))
    return normalized


def _get_latest_non_empty(records: list[dict[str, Any]], field: str) -> Any:
    for record in records:
        value = record.get(field)
        if value not in (None, "", [], {}):
            return value
    return None


def _format_http_error(prefix: str, error: Exception) -> str:
    if isinstance(error, httpx.HTTPStatusError):
        response = error.response
        return f"{prefix}: biz-service returned HTTP {response.status_code} for {response.request.url}"
    return f"{prefix}: {error}"


def fetch_alert_workspace_context(alert_id: str, *, base_url: str | None = None, timeout: float = DEFAULT_HTTP_TIMEOUT_SECONDS) -> dict[str, Any]:
    resolved_base_url = (base_url or _resolve_biz_service_base_url()).rstrip("/")
    alert_url = f"{resolved_base_url}/api/biz/alerts/{alert_id}"
    executions_url = f"{resolved_base_url}/api/biz/executions"

    with httpx.Client(timeout=timeout) as client:
        alert_response = client.get(alert_url)
        alert_response.raise_for_status()
        alert = _normalize_alert(alert_response.json())

        execution_load_error = None
        recent_executions: list[dict[str, Any]] = []
        try:
            executions_response = client.get(executions_url)
            executions_response.raise_for_status()
            recent_executions = [
                _normalize_execution(record)
                for record in executions_response.json()
                if str(record.get("alertId")) == str(alert_id)
            ]
        except Exception as error:  # noqa: BLE001
            execution_load_error = _format_http_error("Failed to load execution records", error)

    return {
        "ok": True,
        "alertId": str(alert_id),
        "alert": alert,
        "recentExecutions": recent_executions,
        "executionCount": len(recent_executions),
        "latestExecutionPlan": _get_latest_non_empty(recent_executions, "executionPlan"),
        "latestExecutionReport": _get_latest_non_empty(recent_executions, "executionReport"),
        "executionLoadError": execution_load_error,
    }


@tool("get_alert_workspace_context", parse_docstring=True)
def get_alert_workspace_context_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    alert_id: str | None = None,
) -> dict[str, Any]:
    """Load the authoritative alert workspace context from SecOps biz-service.

    Use this tool when you need the latest persisted business data for the active alert.
    It returns the alert detail, parsed AI analysis/default params, recent execution records,
    and the latest persisted execution plan/report when available.

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
