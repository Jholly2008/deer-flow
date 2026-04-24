"""SecOps mock ticket tools backed by biz-service and mock/backend."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
from langchain.tools import ToolRuntime, tool
from langgraph.typing import ContextT

from deerflow.agents.thread_state import ThreadState
from deerflow.tools.builtins.secops_workspace_tool import (
    DEFAULT_HTTP_TIMEOUT_SECONDS,
    _format_http_error,
    _resolve_alert_id,
    _resolve_biz_service_base_url,
)

SECOPS_MOCK_BACKEND_URL_ENV = "SECOPS_MOCK_BACKEND_URL"
DEFAULT_SECOPS_MOCK_BACKEND_URL = "http://localhost:8082"
DEFAULT_SECOPS_DOCKER_MOCK_BACKEND_URL = "http://host.docker.internal:8082"


def _is_running_in_docker() -> bool:
    return os.path.exists("/.dockerenv")


def _resolve_mock_backend_base_url() -> str:
    configured = os.getenv(SECOPS_MOCK_BACKEND_URL_ENV)
    if configured:
        return configured.rstrip("/")
    if _is_running_in_docker():
        return DEFAULT_SECOPS_DOCKER_MOCK_BACKEND_URL
    return DEFAULT_SECOPS_MOCK_BACKEND_URL


def _resolve_thread_id(runtime: ToolRuntime[ContextT, ThreadState]) -> str | None:
    if runtime.context and runtime.context.get("thread_id"):
        return str(runtime.context["thread_id"])

    config = getattr(runtime, "config", None)
    configurable = config.get("configurable", {}) if config else {}
    if configurable.get("thread_id"):
        return str(configurable["thread_id"])

    return None


def _resolve_agent_name(runtime: ToolRuntime[ContextT, ThreadState]) -> str:
    if runtime.context and runtime.context.get("agent_name"):
        return str(runtime.context["agent_name"])

    config = getattr(runtime, "config", None)
    configurable = config.get("configurable", {}) if config else {}
    return str(configurable.get("agent_name", "secops-agent"))


def _resolve_alert_type(runtime: ToolRuntime[ContextT, ThreadState]) -> str:
    if runtime.context and runtime.context.get("alert_type"):
        return str(runtime.context["alert_type"])

    config = getattr(runtime, "config", None)
    configurable = config.get("configurable", {}) if config else {}
    return str(configurable.get("alert_type", "mock-external-ticket-remediation"))


def _format_mock_http_error(prefix: str, error: Exception) -> str:
    if isinstance(error, httpx.HTTPStatusError):
        response = error.response
        return f"{prefix}: mock backend returned HTTP {response.status_code} for {response.request.url}"
    return f"{prefix}: {error}"


@tool("create_mock_ticket", parse_docstring=True)
def create_mock_ticket_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    title: str | None = None,
    alert_id: str | None = None,
) -> dict[str, Any]:
    """Create one callback-tracked mock ticket for the active alert thread.

    Args:
        title: Optional ticket title. If omitted, the tool derives a title from the alert.
        alert_id: Optional alert ID. If omitted, the tool uses the alert bound to the current thread.
    """
    resolved_alert_id = _resolve_alert_id(runtime, alert_id)
    resolved_thread_id = _resolve_thread_id(runtime)
    if resolved_alert_id is None:
        return {
            "ok": False,
            "error": "Missing alert_id. Provide an explicit alert_id or run inside an alert-bound thread.",
        }
    if resolved_thread_id is None:
        return {
            "ok": False,
            "alertId": str(resolved_alert_id),
            "error": "Missing thread_id. Callback continuation requires the original alert thread id.",
        }

    agent_name = _resolve_agent_name(runtime)
    alert_type = _resolve_alert_type(runtime)
    continuation_payload = {
        "continuation": {
            "threadId": resolved_thread_id,
            "agentName": agent_name,
            "alertId": str(resolved_alert_id),
            "alertType": alert_type,
            "uiApp": "dashboard-workspace",
            "continuationDispatchedAt": None,
            "continuationRunId": None,
        }
    }

    bootstrap_url = f"{_resolve_biz_service_base_url()}/api/biz/remediation/executions/bootstrap"
    ticket_url = f"{_resolve_mock_backend_base_url()}/api/mock/tickets"
    ticket_title = title or f"{alert_type} #{resolved_alert_id}"

    try:
        with httpx.Client(timeout=DEFAULT_HTTP_TIMEOUT_SECONDS) as client:
            bootstrap_response = client.post(
                bootstrap_url,
                json={
                    "alertId": str(resolved_alert_id),
                    "actionType": alert_type,
                    "operator": agent_name,
                    "initialMessage": "Preparing external ticket handoff",
                    "externalPayload": json.dumps(continuation_payload),
                },
            )
            bootstrap_response.raise_for_status()
            bootstrap_body = bootstrap_response.json()

            ticket_response = client.post(
                ticket_url,
                json={
                    "jobId": bootstrap_body["jobId"],
                    "alertId": str(resolved_alert_id),
                    "title": ticket_title,
                    "trackingMode": "callback",
                    "operator": agent_name,
                    "externalPayload": json.dumps(continuation_payload),
                },
            )
            ticket_response.raise_for_status()
            ticket_body = ticket_response.json()
    except Exception as error:  # noqa: BLE001
        if isinstance(error, httpx.HTTPStatusError) and "mock" in str(error.request.url):
            formatted_error = _format_mock_http_error("Failed to create mock ticket", error)
        else:
            formatted_error = _format_http_error("Failed to create mock ticket", error)
        return {
            "ok": False,
            "alertId": str(resolved_alert_id),
            "error": formatted_error,
        }

    return {
        "ok": True,
        "alertId": str(resolved_alert_id),
        "threadId": resolved_thread_id,
        "jobId": str(bootstrap_body["jobId"]),
        "executionId": str(bootstrap_body["executionId"]),
        "ticketId": str(ticket_body["ticketId"]),
        "externalTaskId": str(ticket_body["externalTaskId"]),
        "status": str(ticket_body["status"]),
    }


@tool("get_mock_ticket_external_status", parse_docstring=True)
def get_mock_ticket_external_status_tool(external_task_id: str) -> dict[str, Any]:
    """Load the current state for one mock external ticket.

    Args:
        external_task_id: The external task id returned by `create_mock_ticket`.
    """
    status_url = f"{_resolve_mock_backend_base_url()}/api/mock/tickets/external-status/{external_task_id}"
    try:
        with httpx.Client(timeout=DEFAULT_HTTP_TIMEOUT_SECONDS) as client:
            response = client.get(status_url)
            response.raise_for_status()
            body = response.json()
    except Exception as error:  # noqa: BLE001
        return {
            "ok": False,
            "externalTaskId": external_task_id,
            "error": _format_mock_http_error("Failed to load mock ticket external status", error),
        }

    return {
        "ok": True,
        "externalTaskId": external_task_id,
        "status": body.get("status"),
        "message": body.get("message"),
        "payload": body.get("payload"),
    }
