from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / ".deer-flow" / "agents" / "secops-agent" / "config.yaml"
SKILL_PATH = REPO_ROOT.parent / "skills" / "custom" / "secops" / "mock-illegal-login-responder" / "SKILL.md"
EXTERNAL_TICKET_SKILL_PATH = REPO_ROOT.parent / "skills" / "custom" / "secops" / "mock-external-ticket-responder" / "SKILL.md"


def test_secops_agent_does_not_explicitly_restrict_skills():
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))

    assert "skills" not in config


def test_mock_illegal_login_skill_documents_required_sop():
    content = SKILL_PATH.read_text(encoding="utf-8")

    for fragment in [
        "mock-user-illegal-login",
        "test",
        "get_alert_workspace_context",
        "get_mock_auth_user_context",
        "sourceIp",
        "commonIp",
        "update_alert_status",
        "kick_mock_auth_user_sessions",
        "disable_mock_auth_user",
        "processed",
        "failed",
    ]:
        assert fragment in content


def test_mock_external_ticket_skill_documents_both_branches():
    content = EXTERNAL_TICKET_SKILL_PATH.read_text(encoding="utf-8")

    for fragment in [
        "mock-external-ticket-remediation",
        "create_mock_ticket",
        "get_mock_ticket_external_status",
        "update_alert_status",
        "processing",
        "processed",
        "failed",
        "Do not create a new ticket",
    ]:
        assert fragment in content
