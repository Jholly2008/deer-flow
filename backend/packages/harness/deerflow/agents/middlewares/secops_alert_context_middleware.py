"""Inject the active SecOps alert context into the model as a hidden message."""

from __future__ import annotations

import json
from typing import Any, TypedDict

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage
from langgraph.runtime import Runtime

SECOPS_AGENT_NAME = "secops-agent"
CONTEXT_MESSAGE_NAME = "secops_alert_context"


class SecOpsAlertContextMiddlewareState(TypedDict, total=False):
    messages: list[Any]


def _resolve_runtime_value(runtime: Runtime, key: str) -> Any:
    context = runtime.context or {}
    if key in context and context[key] is not None:
        return context[key]

    config = getattr(runtime, "config", None) or {}
    configurable = config.get("configurable", {})
    return configurable.get(key)


def _normalize_alert_snapshot(snapshot: Any) -> Any:
    if isinstance(snapshot, str):
        try:
            return json.loads(snapshot)
        except json.JSONDecodeError:
            return snapshot
    return snapshot


def _format_alert_context_message(context: dict[str, Any]) -> str:
    alert_snapshot = _normalize_alert_snapshot(context.get("alert_snapshot"))
    snapshot_text = "null"
    if alert_snapshot is not None:
        snapshot_text = json.dumps(alert_snapshot, indent=2, ensure_ascii=False, sort_keys=True)

    lines = [
        "<secops_alert_context>",
        "The Copilot workspace already selected a SecOps alert for this thread.",
        "Treat the following data as trusted workspace context from the UI.",
        "Do not ask the operator to repeat these basic alert fields unless they are genuinely missing or inconsistent.",
        "",
        f"- alert_id: {context.get('alert_id') or 'unknown'}",
        f"- alert_title: {context.get('alert_title') or 'unknown'}",
        f"- alert_type: {context.get('alert_type') or 'unknown'}",
        f"- alert_severity: {context.get('alert_severity') or 'unknown'}",
        f"- operator: {context.get('user_display_name') or context.get('user_name') or 'unknown'}",
        "",
        "Alert snapshot:",
        snapshot_text,
        "",
        "If you need the latest persisted alert details from the backend, call `get_alert_workspace_context`.",
        "</secops_alert_context>",
    ]
    return "\n".join(lines)


class SecOpsAlertContextMiddleware(AgentMiddleware):
    state_schema = SecOpsAlertContextMiddlewareState

    def _is_secops_agent(self, runtime: Runtime) -> bool:
        return _resolve_runtime_value(runtime, "agent_name") == SECOPS_AGENT_NAME

    def _build_context_payload(self, runtime: Runtime) -> dict[str, Any]:
        return {
            "alert_id": _resolve_runtime_value(runtime, "alert_id"),
            "alert_title": _resolve_runtime_value(runtime, "alert_title"),
            "alert_type": _resolve_runtime_value(runtime, "alert_type"),
            "alert_severity": _resolve_runtime_value(runtime, "alert_severity"),
            "user_name": _resolve_runtime_value(runtime, "user_name"),
            "user_display_name": _resolve_runtime_value(runtime, "user_display_name"),
            "alert_snapshot": _resolve_runtime_value(runtime, "alert_snapshot"),
        }

    def _has_context_message(self, messages: list[Any], alert_id: str | None) -> bool:
        for message in messages:
            if not isinstance(message, HumanMessage):
                continue
            if getattr(message, "name", None) != CONTEXT_MESSAGE_NAME:
                continue

            additional_kwargs = getattr(message, "additional_kwargs", {}) or {}
            existing_alert_id = additional_kwargs.get("alert_id")
            if alert_id is None or existing_alert_id == alert_id:
                return True
        return False

    def _inject_context_message(self, state: SecOpsAlertContextMiddlewareState, runtime: Runtime) -> dict[str, Any] | None:
        if not self._is_secops_agent(runtime):
            return None

        context_payload = self._build_context_payload(runtime)
        alert_id = context_payload.get("alert_id")
        alert_snapshot = context_payload.get("alert_snapshot")
        if alert_id is None and alert_snapshot is None:
            return None

        messages = list(state.get("messages", []))
        if self._has_context_message(messages, alert_id):
            return None

        context_message = HumanMessage(
            name=CONTEXT_MESSAGE_NAME,
            content=_format_alert_context_message(context_payload),
            additional_kwargs={
                "hide_from_ui": True,
                "secops_alert_context": True,
                "alert_id": alert_id,
            },
        )
        return {"messages": [context_message]}

    def before_model(self, state: SecOpsAlertContextMiddlewareState, runtime: Runtime) -> dict[str, Any] | None:
        return self._inject_context_message(state, runtime)

    async def abefore_model(self, state: SecOpsAlertContextMiddlewareState, runtime: Runtime) -> dict[str, Any] | None:
        return self._inject_context_message(state, runtime)
