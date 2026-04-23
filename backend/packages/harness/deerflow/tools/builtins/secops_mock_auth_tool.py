"""SecOps tools for the mock auth backend."""

from __future__ import annotations

import os
from typing import Any

import httpx
from langchain.tools import tool

DEFAULT_HTTP_TIMEOUT_SECONDS = 10.0
SECOPS_MOCK_BACKEND_URL_ENV = "SECOPS_MOCK_BACKEND_URL"
SECOPS_MOCK_AUTH_USERNAME_ENV = "SECOPS_MOCK_AUTH_USERNAME"
SECOPS_MOCK_AUTH_PASSWORD_ENV = "SECOPS_MOCK_AUTH_PASSWORD"
DEFAULT_SECOPS_MOCK_BACKEND_URL = "http://localhost:8082"
DEFAULT_SECOPS_DOCKER_MOCK_BACKEND_URL = "http://host.docker.internal:8082"
DEFAULT_SECOPS_MOCK_AUTH_USERNAME = "admin"
DEFAULT_SECOPS_MOCK_AUTH_PASSWORD = "111111"
AUTH_HEADER = "X-Mock-Auth-Token"


def _is_running_in_docker() -> bool:
    return os.path.exists("/.dockerenv")


def _resolve_mock_backend_base_url() -> str:
    configured = os.getenv(SECOPS_MOCK_BACKEND_URL_ENV)
    if configured:
        return configured.rstrip("/")
    if _is_running_in_docker():
        return DEFAULT_SECOPS_DOCKER_MOCK_BACKEND_URL
    return DEFAULT_SECOPS_MOCK_BACKEND_URL


def _resolve_operator_credentials() -> tuple[str, str]:
    return (
        os.getenv(SECOPS_MOCK_AUTH_USERNAME_ENV, DEFAULT_SECOPS_MOCK_AUTH_USERNAME),
        os.getenv(SECOPS_MOCK_AUTH_PASSWORD_ENV, DEFAULT_SECOPS_MOCK_AUTH_PASSWORD),
    )


def _login(client: httpx.Client, base_url: str) -> str:
    username, password = _resolve_operator_credentials()
    response = client.post(
        f"{base_url}/api/mock/auth/login",
        json={"username": username, "password": password},
    )
    response.raise_for_status()
    payload = response.json()
    token = payload.get("token")
    if not isinstance(token, str) or not token.strip():
        raise ValueError("mock auth login did not return a token")
    return token


def _auth_headers(token: str) -> dict[str, str]:
    return {AUTH_HEADER: token}


def _format_http_error(prefix: str, error: Exception) -> str:
    if isinstance(error, httpx.HTTPStatusError):
        response = error.response
        return f"{prefix}: mock backend returned HTTP {response.status_code} for {response.request.url}"
    return f"{prefix}: {error}"


@tool("get_mock_auth_user_context", parse_docstring=True)
def get_mock_auth_user_context(username: str) -> dict[str, Any]:
    """Load the current mock-auth state for one username.

    Args:
        username: Target username in the mock auth system.
    """
    base_url = _resolve_mock_backend_base_url()
    try:
        with httpx.Client(timeout=DEFAULT_HTTP_TIMEOUT_SECONDS) as client:
            token = _login(client, base_url)
            users = client.get(f"{base_url}/api/mock/auth/users", headers=_auth_headers(token))
            users.raise_for_status()
            sessions = client.get(f"{base_url}/api/mock/auth/sessions", headers=_auth_headers(token))
            sessions.raise_for_status()

        user = next((item for item in users.json().get("users", []) if item.get("username") == username), None)
        active_sessions = [item for item in sessions.json().get("sessions", []) if item.get("username") == username]
        return {
            "ok": True,
            "username": username,
            "userExists": user is not None,
            "disabled": bool(user.get("disabled")) if user else False,
            "commonIp": str(user.get("commonIp") or "") if user else "",
            "sessions": active_sessions,
        }
    except Exception as error:  # noqa: BLE001
        return {
            "ok": False,
            "username": username,
            "error": _format_http_error("Failed to load mock auth user context", error),
        }


@tool("kick_mock_auth_user_sessions", parse_docstring=True)
def kick_mock_auth_user_sessions(username: str) -> dict[str, Any]:
    """Kick every active mock-auth session for one username.

    Args:
        username: Target username in the mock auth system.
    """
    base_url = _resolve_mock_backend_base_url()
    try:
        with httpx.Client(timeout=DEFAULT_HTTP_TIMEOUT_SECONDS) as client:
            token = _login(client, base_url)
            sessions_response = client.get(f"{base_url}/api/mock/auth/sessions", headers=_auth_headers(token))
            sessions_response.raise_for_status()
            matching_sessions = [
                item for item in sessions_response.json().get("sessions", [])
                if item.get("username") == username
            ]

            kicked_ids: list[str] = []
            for session in matching_sessions:
                session_id = str(session["sessionId"])
                kick_response = client.post(
                    f"{base_url}/api/mock/auth/sessions/{session_id}/kick",
                    headers=_auth_headers(token),
                )
                kick_response.raise_for_status()
                kicked_ids.append(session_id)

        return {
            "ok": True,
            "username": username,
            "kickedSessionCount": len(kicked_ids),
            "kickedSessionIds": kicked_ids,
        }
    except Exception as error:  # noqa: BLE001
        return {
            "ok": False,
            "username": username,
            "error": _format_http_error("Failed to kick mock auth user sessions", error),
        }


@tool("disable_mock_auth_user", parse_docstring=True)
def disable_mock_auth_user(username: str) -> dict[str, Any]:
    """Disable one mock-auth user after session containment.

    Args:
        username: Target username in the mock auth system.
    """
    base_url = _resolve_mock_backend_base_url()
    try:
        with httpx.Client(timeout=DEFAULT_HTTP_TIMEOUT_SECONDS) as client:
            token = _login(client, base_url)
            response = client.post(
                f"{base_url}/api/mock/auth/users/{username}/disable",
                headers=_auth_headers(token),
            )
            response.raise_for_status()
            user = response.json()

        return {
            "ok": True,
            "username": username,
            "disabled": bool(user.get("disabled")),
            "user": user,
        }
    except Exception as error:  # noqa: BLE001
        return {
            "ok": False,
            "username": username,
            "error": _format_http_error("Failed to disable mock auth user", error),
        }
