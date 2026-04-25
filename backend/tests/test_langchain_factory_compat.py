from __future__ import annotations

from types import SimpleNamespace

from langchain_core.messages import AIMessage, ToolMessage

from deerflow.utils.langchain_factory_compat import patch_langchain_factory_for_missing_ai_guard


def test_patch_langchain_factory_for_missing_ai_guard_replaces_buggy_helper():
    def buggy_fetch(messages):
        last_ai_index: int
        last_ai_message: AIMessage

        for index in range(len(messages) - 1, -1, -1):
            if isinstance(messages[index], AIMessage):
                last_ai_index = index
                last_ai_message = messages[index]
                break

        tool_messages = [message for message in messages[last_ai_index + 1 :] if isinstance(message, ToolMessage)]
        return last_ai_message, tool_messages

    factory_module = SimpleNamespace(_fetch_last_ai_and_tool_messages=buggy_fetch)

    patched = patch_langchain_factory_for_missing_ai_guard(factory_module)

    assert patched is True
    assert factory_module._fetch_last_ai_and_tool_messages([]) == (None, [])

    ai_message = AIMessage(content="", tool_calls=[])
    tool_message = ToolMessage(content="ok", tool_call_id="call-1")
    last_ai_message, tool_messages = factory_module._fetch_last_ai_and_tool_messages([ai_message, tool_message])

    assert last_ai_message == ai_message
    assert tool_messages == [tool_message]
