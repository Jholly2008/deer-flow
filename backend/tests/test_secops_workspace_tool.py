import importlib
from types import SimpleNamespace

import httpx

import deerflow.tools.tools as tools_module

workspace_tool_module = importlib.import_module("deerflow.tools.builtins.secops_workspace_tool")


class _FakeResponse:
    def __init__(self, payload, *, url: str, status_code: int = 200):
        self._payload = payload
        self.url = url
        self.status_code = status_code
        self.request = httpx.Request("GET", url)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=self.request,
                response=httpx.Response(self.status_code, request=self.request),
            )


class _FakeClient:
    def __init__(self, responses):
        self._responses = responses
        self.requested_urls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url):
        self.requested_urls.append(url)
        return self._responses[url]


def _runtime(*, alert_id=None):
    context = {}
    if alert_id is not None:
        context["alert_id"] = alert_id
    return SimpleNamespace(context=context, config={})


def _run_tool(**kwargs):
    coroutine = getattr(workspace_tool_module.get_alert_workspace_context_tool, "coroutine", None)
    if coroutine is not None:
        import asyncio

        return asyncio.run(coroutine(**kwargs))
    return workspace_tool_module.get_alert_workspace_context_tool.func(**kwargs)


def test_workspace_tool_uses_runtime_alert_id_and_aggregates_context(monkeypatch):
    base_url = "http://biz-service.local"
    alert_id = "1017"
    executions_url = f"{base_url}/api/biz/executions"
    alert_url = f"{base_url}/api/biz/alerts/{alert_id}"

    fake_client = _FakeClient(
        {
            alert_url: _FakeResponse(
                {
                    "id": alert_id,
                    "type": "Brute force attack",
                    "aiAnalysis": '{"summary":"Brute force confirmed"}',
                    "defaultParams": '{"host":"10.0.0.25"}',
                },
                url=alert_url,
            ),
            executions_url: _FakeResponse(
                [
                    {
                        "alertId": alert_id,
                        "executionPlan": '{"steps":["block IP"]}',
                        "executionReport": "Blocked attacker IP",
                        "params": '{"sourceIp":"45.155.205.233"}',
                    },
                    {
                        "alertId": "1001",
                        "executionPlan": "ignore other alert",
                    },
                ],
                url=executions_url,
            ),
        }
    )

    monkeypatch.setattr(workspace_tool_module, "_resolve_biz_service_base_url", lambda: base_url)
    monkeypatch.setattr(workspace_tool_module.httpx, "Client", lambda timeout: fake_client)

    result = _run_tool(runtime=_runtime(alert_id=alert_id), alert_id=None)

    assert result["ok"] is True
    assert result["alertId"] == alert_id
    assert result["alert"]["aiAnalysis"]["summary"] == "Brute force confirmed"
    assert result["alert"]["defaultParams"]["host"] == "10.0.0.25"
    assert len(result["recentExecutions"]) == 1
    assert result["recentExecutions"][0]["params"]["sourceIp"] == "45.155.205.233"
    assert result["latestExecutionPlan"]["steps"] == ["block IP"]
    assert result["latestExecutionReport"] == "Blocked attacker IP"


def test_workspace_tool_prefers_explicit_alert_id(monkeypatch):
    base_url = "http://biz-service.local"
    alert_url = f"{base_url}/api/biz/alerts/2001"
    executions_url = f"{base_url}/api/biz/executions"
    fake_client = _FakeClient(
        {
            alert_url: _FakeResponse({"id": "2001", "type": "Phishing"}, url=alert_url),
            executions_url: _FakeResponse([], url=executions_url),
        }
    )

    monkeypatch.setattr(workspace_tool_module, "_resolve_biz_service_base_url", lambda: base_url)
    monkeypatch.setattr(workspace_tool_module.httpx, "Client", lambda timeout: fake_client)

    result = _run_tool(runtime=_runtime(alert_id="1017"), alert_id="2001")

    assert result["ok"] is True
    assert result["alertId"] == "2001"


def test_workspace_tool_returns_error_when_alert_id_missing():
    result = _run_tool(runtime=_runtime(alert_id=None), alert_id=None)

    assert result["ok"] is False
    assert "alert_id" in result["error"]


def test_workspace_tool_returns_partial_success_when_execution_query_fails(monkeypatch):
    base_url = "http://biz-service.local"
    alert_id = "1017"
    alert_url = f"{base_url}/api/biz/alerts/{alert_id}"
    executions_url = f"{base_url}/api/biz/executions"
    fake_client = _FakeClient(
        {
            alert_url: _FakeResponse({"id": alert_id, "type": "Malware"}, url=alert_url),
            executions_url: _FakeResponse([], url=executions_url, status_code=503),
        }
    )

    monkeypatch.setattr(workspace_tool_module, "_resolve_biz_service_base_url", lambda: base_url)
    monkeypatch.setattr(workspace_tool_module.httpx, "Client", lambda timeout: fake_client)

    result = _run_tool(runtime=_runtime(alert_id=alert_id), alert_id=None)

    assert result["ok"] is True
    assert result["executionLoadError"] is not None
    assert result["recentExecutions"] == []


def test_resolve_biz_service_base_url_prefers_docker_host_inside_container(monkeypatch):
    monkeypatch.delenv(workspace_tool_module.SECOPS_BIZ_SERVICE_URL_ENV, raising=False)
    monkeypatch.setattr(workspace_tool_module, "_is_running_in_docker", lambda: True)

    result = workspace_tool_module._resolve_biz_service_base_url()

    assert result == workspace_tool_module.DEFAULT_SECOPS_DOCKER_BIZ_SERVICE_URL


def test_get_available_tools_includes_secops_workspace_tool_only_for_secops_agent(monkeypatch):
    fake_model_config = SimpleNamespace(supports_vision=False)
    fake_app_config = SimpleNamespace(
        tools=[],
        skill_evolution=SimpleNamespace(enabled=False),
        tool_search=SimpleNamespace(enabled=False),
        models=[SimpleNamespace(name="test-model")],
        get_model_config=lambda name: fake_model_config,
    )

    monkeypatch.setattr(tools_module, "get_app_config", lambda: fake_app_config)
    monkeypatch.setattr(tools_module, "is_host_bash_allowed", lambda config: True)

    secops_names = [tool.name for tool in tools_module.get_available_tools(include_mcp=False, model_name="test-model", subagent_enabled=False, agent_name="secops-agent")]
    default_names = [tool.name for tool in tools_module.get_available_tools(include_mcp=False, model_name="test-model", subagent_enabled=False, agent_name=None)]

    assert "get_alert_workspace_context" in secops_names
    assert "get_alert_workspace_context" not in default_names
