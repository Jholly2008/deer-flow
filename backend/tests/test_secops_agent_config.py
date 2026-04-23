from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / ".deer-flow" / "agents" / "secops-agent" / "config.yaml"
SKILL_PATH = REPO_ROOT.parent / "skills" / "custom" / "secops" / "mock-illegal-login-responder" / "SKILL.md"


def test_secops_agent_enables_only_mock_illegal_login_skill():
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))

    assert config["skills"] == ["mock-illegal-login-responder"]


def test_mock_illegal_login_skill_documents_required_sop():
    content = SKILL_PATH.read_text(encoding="utf-8")

    for fragment in [
        "mock-user-illegal-login",
        "test",
        "get_alert_workspace_context",
        "get_mock_auth_user_context",
        "update_alert_status",
        "kick_mock_auth_user_sessions",
        "disable_mock_auth_user",
        "processed",
        "failed",
    ]:
        assert fragment in content
