import importlib

import httpx

mock_auth_tool_module = importlib.import_module("deerflow.tools.builtins.secops_mock_auth_tool")


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
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url, headers=None):
        self.calls.append(("GET", url, headers))
        return self._responses[("GET", url)]

    def post(self, url, json=None, headers=None):
        self.calls.append(("POST", url, json, headers))
        return self._responses[("POST", url)]


def _run_tool(tool, **kwargs):
    coroutine = getattr(tool, "coroutine", None)
    if coroutine is not None:
        import asyncio

        return asyncio.run(coroutine(**kwargs))
    return tool.func(**kwargs)


def test_get_mock_auth_user_context_returns_user_and_sessions(monkeypatch):
    base_url = "http://mock-backend.local"
    login_url = f"{base_url}/api/mock/auth/login"
    users_url = f"{base_url}/api/mock/auth/users"
    sessions_url = f"{base_url}/api/mock/auth/sessions"
    fake_client = _FakeClient(
        {
            ("POST", login_url): _FakeResponse({"token": "mock-token"}, method="POST", url=login_url),
            ("GET", users_url): _FakeResponse({"users": [{"username": "test", "disabled": False}]}, method="GET", url=users_url),
            ("GET", sessions_url): _FakeResponse(
                {"sessions": [{"sessionId": "session-1", "username": "test"}]},
                method="GET",
                url=sessions_url,
            ),
        }
    )

    monkeypatch.setattr(mock_auth_tool_module, "_resolve_mock_backend_base_url", lambda: base_url)
    monkeypatch.setattr(mock_auth_tool_module.httpx, "Client", lambda timeout: fake_client)

    result = _run_tool(mock_auth_tool_module.get_mock_auth_user_context, username="test")

    assert result["ok"] is True
    assert result["userExists"] is True
    assert result["disabled"] is False
    assert result["sessions"] == [{"sessionId": "session-1", "username": "test"}]


def test_kick_mock_auth_user_sessions_kicks_all_matching_sessions(monkeypatch):
    base_url = "http://mock-backend.local"
    login_url = f"{base_url}/api/mock/auth/login"
    sessions_url = f"{base_url}/api/mock/auth/sessions"
    kick_one_url = f"{base_url}/api/mock/auth/sessions/session-1/kick"
    kick_two_url = f"{base_url}/api/mock/auth/sessions/session-2/kick"
    fake_client = _FakeClient(
        {
            ("POST", login_url): _FakeResponse({"token": "mock-token"}, method="POST", url=login_url),
            ("GET", sessions_url): _FakeResponse(
                {
                    "sessions": [
                        {"sessionId": "session-1", "username": "test"},
                        {"sessionId": "session-2", "username": "test"},
                        {"sessionId": "session-9", "username": "admin"},
                    ]
                },
                method="GET",
                url=sessions_url,
            ),
            ("POST", kick_one_url): _FakeResponse({"sessionId": "session-1"}, method="POST", url=kick_one_url),
            ("POST", kick_two_url): _FakeResponse({"sessionId": "session-2"}, method="POST", url=kick_two_url),
        }
    )

    monkeypatch.setattr(mock_auth_tool_module, "_resolve_mock_backend_base_url", lambda: base_url)
    monkeypatch.setattr(mock_auth_tool_module.httpx, "Client", lambda timeout: fake_client)

    result = _run_tool(mock_auth_tool_module.kick_mock_auth_user_sessions, username="test")

    assert result["ok"] is True
    assert result["kickedSessionCount"] == 2
    assert result["kickedSessionIds"] == ["session-1", "session-2"]


def test_disable_mock_auth_user_returns_final_disabled_state(monkeypatch):
    base_url = "http://mock-backend.local"
    login_url = f"{base_url}/api/mock/auth/login"
    disable_url = f"{base_url}/api/mock/auth/users/test/disable"
    fake_client = _FakeClient(
        {
            ("POST", login_url): _FakeResponse({"token": "mock-token"}, method="POST", url=login_url),
            ("POST", disable_url): _FakeResponse(
                {"username": "test", "disabled": True},
                method="POST",
                url=disable_url,
            ),
        }
    )

    monkeypatch.setattr(mock_auth_tool_module, "_resolve_mock_backend_base_url", lambda: base_url)
    monkeypatch.setattr(mock_auth_tool_module.httpx, "Client", lambda timeout: fake_client)

    result = _run_tool(mock_auth_tool_module.disable_mock_auth_user, username="test")

    assert result["ok"] is True
    assert result["disabled"] is True
