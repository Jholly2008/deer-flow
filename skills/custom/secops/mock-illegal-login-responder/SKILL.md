---
name: mock-illegal-login-responder
description: Use this skill when the current alert type is `mock-user-illegal-login` and the operator wants the workspace to execute the mock-auth containment SOP against user `test`.
---

# Mock Illegal Login Responder

## When to Use

Load this skill only when the active alert is `mock-user-illegal-login` or the operator explicitly asks to execute that alert's SOP.

## Execution Contract

- The demo target user is always `test`.
- Do not claim success without tool-confirmed outputs.
- If the alert type does not match `mock-user-illegal-login`, stop and explain the mismatch.
- Use `alert.sourceIp` from `get_alert_workspace_context` and `commonIp` from `get_mock_auth_user_context` to decide whether the login is actually anomalous.
- If any required remediation step fails after processing starts, call `update_alert_status` with `failed` before concluding.

## SOP

1. If the thread is alert-bound, call `get_alert_workspace_context` to confirm the `alert_id` and alert type.
2. Confirm the alert type is `mock-user-illegal-login`.
3. Read `alert.sourceIp`. If `sourceIp` is missing, stop and explain that the abnormal-login judgement cannot be completed.
4. Call `get_mock_auth_user_context(username="test")` and capture the current disabled state, `commonIp`, and active sessions.
5. If `commonIp` is missing, stop and explain that the abnormal-login judgement cannot be completed.
6. Compare `alert.sourceIp` with `commonIp`.
7. If `alert.sourceIp` matches `commonIp`, treat the login as not anomalous, call `update_alert_status(status="processed")`, and summarize that no containment was required.
8. If `alert.sourceIp` differs from `commonIp`, call `update_alert_status(status="processing")`.
9. Call `kick_mock_auth_user_sessions(username="test")`.
10. Call `disable_mock_auth_user(username="test")`.
11. If both required actions succeeded, call `update_alert_status(status="processed")`.
12. If either required action failed, call `update_alert_status(status="failed")`.
13. Summarize the source IP, common IP, whether the login was anomalous, the kicked session count, the final disabled state, and any residual risk.
