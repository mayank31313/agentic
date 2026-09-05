import importlib.util
import sys
from types import SimpleNamespace
from pathlib import Path
import types
from unittest.mock import AsyncMock

import pytest


def _ensure_module(name: str, *, package: bool = False):
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        if package:
            module.__path__ = []
        sys.modules[name] = module
    return module


def _load_middleware_module():
    _ensure_module("agentic", package=True)
    _ensure_module("agentic.app", package=True)
    _ensure_module("agentic.app.common", package=True)
    _ensure_module("agentic.app.gateway", package=True)

    annotations = _ensure_module("cndi.annotations")
    annotations.Component = lambda cls: cls

    langchain_middleware = _ensure_module("langchain.agents.middleware")
    langchain_middleware.AgentMiddleware = type("AgentMiddleware", (), {})

    tool_node = _ensure_module("langgraph.prebuilt.tool_node")
    tool_node.ToolCallRequest = object

    adapters = _ensure_module("agentic.app.gateway.adapters")

    class OutboundMessageReply:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class OutboundMessage:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class AdapterRegistry:
        @staticmethod
        def get(name: str):
            raise AssertionError("AdapterRegistry.get should not be called in these tests")

    adapters.OutboundMessageReply = OutboundMessageReply
    adapters.OutboundMessage = OutboundMessage
    adapters.AdapterRegistry = AdapterRegistry

    module_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "agentic"
        / "app"
        / "common"
        / "middleware.py"
    )
    spec = importlib.util.spec_from_file_location("tool_middleware_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


middleware_module = _load_middleware_module()
ToolNotifierMiddleware = middleware_module.ToolNotifierMiddleware
OutboundMessageReply = middleware_module.OutboundMessageReply


@pytest.mark.asyncio
async def test_awrap_tool_call_skips_malformed_thread_id():
    middleware = ToolNotifierMiddleware()
    middleware.send_message = AsyncMock()
    handler = AsyncMock(return_value="ok")
    request = SimpleNamespace(
        runtime=SimpleNamespace(config={"configurable": {"thread_id": "telegram"}}),
        tool_call={"name": "test_tool", "args": {"value": 1}},
    )

    response = await middleware.awrap_tool_call(request, handler)

    assert response == "ok"
    handler.assert_awaited_once_with(request)
    middleware.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_awrap_tool_call_accepts_thread_id_with_additional_delimiters():
    middleware = ToolNotifierMiddleware()
    middleware.send_message = AsyncMock(
        return_value=OutboundMessageReply(
            message_id="1", channel="telegram", chat_id="chat::sub"
        )
    )
    middleware.delete_sent_message = AsyncMock()
    handler = AsyncMock(return_value="ok")
    request = SimpleNamespace(
        runtime=SimpleNamespace(
            config={"configurable": {"thread_id": "telegram::chat::sub"}}
        ),
        tool_call={"name": "test_tool", "args": {"value": 1}},
    )

    response = await middleware.awrap_tool_call(request, handler)

    assert response == "ok"
    middleware.send_message.assert_awaited_once_with(
        "🔧 Calling tool: test_tool\nArgs: {'value': 1}", "telegram", "chat::sub"
    )
    middleware.delete_sent_message.assert_awaited_once()
