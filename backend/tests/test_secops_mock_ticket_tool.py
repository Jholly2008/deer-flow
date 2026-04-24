import asyncio
import importlib
from types import SimpleNamespace

import httpx

ticket_tool_module = importlib.import_module("deerflow.tools.builtins.secops_mock_ticket_tool")


class _FakeResponse:
    def __init__(self, payload, *, method: str, url: str, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.request = httpx.Request(method, url)

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
        self.posts = []
        self.gets = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, json):
        self.posts.append((url, json))
        return self._responses[("POST", url)]

    def get(self, url):
        self.gets.append(url)
        return self._responses[("GET", url)]


def _runtime(*, alert_id="1020", alert_type="mock-external-ticket-remediation", thread_id="thread-1"):
    context = {"alert_id": alert_id, "alert_type": alert_type}
    configurable = {"thread_id": thread_id, "agent_name": "secops-agent"}
    return SimpleNamespace(context=context, config={"configurable": configurable})


def _run(tool, **kwargs):
    coroutine = getattr(tool, "coroutine", None)
    if coroutine is not None:
        return asyncio.run(coroutine(**kwargs))
    return tool.func(**kwargs)


def test_create_mock_ticket_bootstraps_execution_then_creates_callback_ticket(monkeypatch):
    biz_base = "http://biz-service.local"
    mock_base = "http://mock.local"
    bootstrap_url = f"{biz_base}/api/biz/remediation/executions/bootstrap"
    create_url = f"{mock_base}/api/mock/tickets"

    fake_client = _FakeClient(
        {
            ("POST", bootstrap_url): _FakeResponse(
                {"executionId": "exec-1", "jobId": "job-1", "result": "running"},
                method="POST",
                url=bootstrap_url,
            ),
            ("POST", create_url): _FakeResponse(
                {"ticketId": "MT-1", "executionId": "exec-1", "externalTaskId": "ext-1", "status": "processing"},
                method="POST",
                url=create_url,
            ),
        }
    )

    monkeypatch.setattr(ticket_tool_module, "_resolve_biz_service_base_url", lambda: biz_base)
    monkeypatch.setattr(ticket_tool_module, "_resolve_mock_backend_base_url", lambda: mock_base)
    monkeypatch.setattr(ticket_tool_module.httpx, "Client", lambda timeout: fake_client)

    result = _run(
        ticket_tool_module.create_mock_ticket_tool,
        runtime=_runtime(),
        title="External remediation ticket",
        alert_id=None,
    )

    assert result["ok"] is True
    assert result["jobId"] == "job-1"
    assert result["ticketId"] == "MT-1"
    assert fake_client.posts[0][1]["alertId"] == "1020"
    assert "thread-1" in fake_client.posts[0][1]["externalPayload"]
    assert fake_client.posts[1][1]["trackingMode"] == "callback"


def test_create_mock_ticket_requires_thread_id():
    result = _run(
        ticket_tool_module.create_mock_ticket_tool,
        runtime=_runtime(thread_id=None),
        title="External remediation ticket",
        alert_id="1020",
    )

    assert result["ok"] is False
    assert "thread_id" in result["error"]


def test_get_mock_ticket_external_status_reads_mock_backend(monkeypatch):
    mock_base = "http://mock.local"
    status_url = f"{mock_base}/api/mock/tickets/external-status/ext-1"
    fake_client = _FakeClient(
        {
            ("GET", status_url): _FakeResponse(
                {"status": "success", "message": "done", "payload": {"ticketId": "MT-1"}},
                method="GET",
                url=status_url,
            )
        }
    )

    monkeypatch.setattr(ticket_tool_module, "_resolve_mock_backend_base_url", lambda: mock_base)
    monkeypatch.setattr(ticket_tool_module.httpx, "Client", lambda timeout: fake_client)

    result = _run(ticket_tool_module.get_mock_ticket_external_status_tool, external_task_id="ext-1")

    assert result["ok"] is True
    assert result["status"] == "success"
    assert result["payload"]["ticketId"] == "MT-1"
