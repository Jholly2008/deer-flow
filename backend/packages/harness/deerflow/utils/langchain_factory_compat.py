"""Compatibility helpers for known LangChain factory regressions."""

from __future__ import annotations

import logging
from typing import Any, cast

from langchain_core.messages import AIMessage, AnyMessage, ToolMessage

logger = logging.getLogger(__name__)

_PATCH_MARKER = "__deerflow_fetch_last_ai_patch__"


def _patched_fetch_last_ai_and_tool_messages(
    messages: list[AnyMessage],
) -> tuple[AIMessage | None, list[ToolMessage]]:
    for index in range(len(messages) - 1, -1, -1):
        if isinstance(messages[index], AIMessage):
            last_ai_message = cast("AIMessage", messages[index])
            tool_messages = [message for message in messages[index + 1 :] if isinstance(message, ToolMessage)]
            return last_ai_message, tool_messages

    return None, []


setattr(_patched_fetch_last_ai_and_tool_messages, _PATCH_MARKER, True)


def patch_langchain_factory_for_missing_ai_guard(factory_module: Any | None = None) -> bool:
    """Patch buggy LangChain builds that crash when no AIMessage is present.

    Some environments ship a ``langchain.agents.factory`` implementation whose
    ``_fetch_last_ai_and_tool_messages`` helper raises ``UnboundLocalError``
    instead of returning ``(None, [])`` when the current state lacks an
    ``AIMessage``. DeerFlow can legitimately hit that branch after tool-node
    state reductions, so we patch the helper at import time when needed.
    """

    if factory_module is None:
        import langchain.agents.factory as factory_module

    current = getattr(factory_module, "_fetch_last_ai_and_tool_messages", None)
    if current is None:
        logger.warning("LangChain compatibility patch skipped because _fetch_last_ai_and_tool_messages is missing.")
        return False

    if getattr(current, _PATCH_MARKER, False):
        return False

    needs_patch = False
    try:
        result = current([])
        needs_patch = result != (None, [])
    except UnboundLocalError:
        needs_patch = True
    except Exception:
        # Unknown behavior: leave the installed implementation untouched.
        needs_patch = False

    if not needs_patch:
        return False

    setattr(factory_module, "_fetch_last_ai_and_tool_messages", _patched_fetch_last_ai_and_tool_messages)
    logger.info("Applied DeerFlow compatibility patch for langchain.agents.factory._fetch_last_ai_and_tool_messages.")
    return True
