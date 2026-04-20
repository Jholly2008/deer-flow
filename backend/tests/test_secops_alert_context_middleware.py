from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage

from deerflow.agents.middlewares.secops_alert_context_middleware import (
    CONTEXT_MESSAGE_NAME,
    SECOPS_AGENT_NAME,
    SecOpsAlertContextMiddleware,
)


def _runtime(*, context=None, configurable=None):
    return SimpleNamespace(
        context=context or {},
        config={"configurable": configurable or {}},
    )


def test_before_model_injects_hidden_alert_context_for_secops_agent():
    middleware = SecOpsAlertContextMiddleware()
    state = {"messages": [HumanMessage(content="Please investigate this alert.")]}

    result = middleware.before_model(
        state,
        _runtime(
            context={
                "agent_name": SECOPS_AGENT_NAME,
                "alert_id": "1017",
                "alert_title": "Brute force attack",
                "alert_type": "BruteForce",
                "alert_severity": "critical",
                "user_name": "analyst-1",
                "alert_snapshot": {
                    "id": "1017",
                    "sourceIp": "45.155.205.233",
                    "destIp": "43.153.11.8",
                },
            }
        ),
    )

    assert result is not None
    assert len(result["messages"]) == 1

    injected = result["messages"][0]
    assert isinstance(injected, HumanMessage)
    assert injected.name == CONTEXT_MESSAGE_NAME
    assert injected.additional_kwargs["hide_from_ui"] is True
    assert injected.additional_kwargs["secops_alert_context"] is True
    assert injected.additional_kwargs["alert_id"] == "1017"
    assert "Brute force attack" in injected.content
    assert "45.155.205.233" in injected.content
    assert "get_alert_workspace_context" in injected.content


def test_before_model_skips_non_secops_agent():
    middleware = SecOpsAlertContextMiddleware()
    state = {"messages": [HumanMessage(content="hello")]}

    result = middleware.before_model(
        state,
        _runtime(context={"agent_name": "default", "alert_id": "1017"}),
    )

    assert result is None


def test_before_model_skips_duplicate_context_for_same_alert():
    middleware = SecOpsAlertContextMiddleware()
    state = {
        "messages": [
            HumanMessage(content="Investigate"),
            HumanMessage(
                name=CONTEXT_MESSAGE_NAME,
                content="existing context",
                additional_kwargs={
                    "hide_from_ui": True,
                    "secops_alert_context": True,
                    "alert_id": "1017",
                },
            ),
        ]
    }

    result = middleware.before_model(
        state,
        _runtime(context={"agent_name": SECOPS_AGENT_NAME, "alert_id": "1017"}),
    )

    assert result is None


def test_before_model_uses_configurable_fallback_when_runtime_context_missing():
    middleware = SecOpsAlertContextMiddleware()
    state = {"messages": [HumanMessage(content="Investigate")]}

    result = middleware.before_model(
        state,
        _runtime(
            configurable={
                "agent_name": SECOPS_AGENT_NAME,
                "alert_id": "1004",
                "alert_title": "Malware beaconing",
                "alert_snapshot": {"id": "1004", "severity": "high"},
            }
        ),
    )

    assert result is not None
    injected = result["messages"][0]
    assert "1004" in injected.content
    assert "Malware beaconing" in injected.content


@pytest.mark.anyio
async def test_abefore_model_matches_sync_behavior():
    middleware = SecOpsAlertContextMiddleware()
    state = {"messages": [HumanMessage(content="Investigate")]}
    runtime = _runtime(context={"agent_name": SECOPS_AGENT_NAME, "alert_id": "1012"})

    result = await middleware.abefore_model(state, runtime)

    assert result is not None
    assert result["messages"][0].name == CONTEXT_MESSAGE_NAME
