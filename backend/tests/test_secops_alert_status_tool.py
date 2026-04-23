import importlib
from types import SimpleNamespace

import httpx

workspace_tool_module = importlib.import_module("deerflow.tools.builtins.secops_workspace_tool")


class _FakeResponse:
    def __init__(self, payload, *, url: str, status_code: int = 200):
        self._payload = payload
        self.url = url
        self.status_code = status_code
        self.request = httpx.Request("PATCH", url)

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
        self.patched = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def patch(self, url, json):
        self.patched.append((url, json))
        return self._responses[url]


def _runtime(*, alert_id=None):
    context = {}
    if alert_id is not None:
        context["alert_id"] = alert_id
    return SimpleNamespace(context=context, config={})


def _run_status_tool(**kwargs):
    coroutine = getattr(workspace_tool_module.update_alert_status_tool, "coroutine", None)
    if coroutine is not None:
        import asyncio

        return asyncio.run(coroutine(**kwargs))
    return workspace_tool_module.update_alert_status_tool.func(**kwargs)


def test_update_alert_status_uses_runtime_alert_id(monkeypatch):
    base_url = "http://biz-service.local"
    alert_url = f"{base_url}/api/biz/alerts/1019/status"
    fake_client = _FakeClient(
        {
            alert_url: _FakeResponse(
                {"id": "1019", "status": "processing"},
                url=alert_url,
            )
        }
    )

    monkeypatch.setattr(workspace_tool_module, "_resolve_biz_service_base_url", lambda: base_url)
    monkeypatch.setattr(workspace_tool_module.httpx, "Client", lambda timeout: fake_client)

    result = _run_status_tool(runtime=_runtime(alert_id="1019"), alert_id=None, status="processing")

    assert result["ok"] is True
    assert result["status"] == "processing"
    assert fake_client.patched == [(alert_url, {"status": "processing"})]


def test_update_alert_status_rejects_unsupported_status():
    result = _run_status_tool(runtime=_runtime(alert_id="1019"), alert_id=None, status="pending")

    assert result["ok"] is False
    assert "processing" in result["error"]
