---
name: port-scanning-responder
description: Use this skill when the current alert type is `port-scanning` or `Port scanning`. Treats all port scanning alerts as false positives and marks them as processed without further action.
---

# Port Scanning Responder

## When to Use

Load this skill only when the active alert type is `port-scanning` or `Port scanning`.

## Execution Contract

- All port scanning alerts are treated as false positives by default.
- No investigation or containment action is required.
- The alert must be marked as `processed` immediately.

## SOP

1. Call `get_alert_workspace_context` to confirm the `alert_id` and alert type.
2. Confirm the alert type is `port-scanning` or `Port scanning`. If not, stop and explain the mismatch.
3. Call `update_alert_status(status="processed")`.
4. Summarize that the port scanning alert has been classified as a false positive and marked as processed without further action.
