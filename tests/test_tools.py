"""Unit tests for common tool helpers.

These target ``split_agentic_cli_command`` in isolation, since the full
tool registry (``register_common_tools`` and friends) pulls in heavy
optional dependencies (deepagents, langchain_mcp_adapters, etc.) that
aren't needed to exercise the CLI argument quoting logic.
"""

import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock
import types

import pytest


def _ensure_module(name: str, *, package: bool = False):
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        if package:
            module.__path__ = []
        sys.modules[name] = module
    return module


def _load_common_tools_module():
    _ensure_module("agentic", package=True)
    _ensure_module("agentic.app", package=True)
    _ensure_module("agentic.app.common", package=True)

    annotations = _ensure_module("cndi.annotations")
    annotations.Autowired = lambda *args, **kwargs: (lambda obj: obj)
    annotations.Bean = lambda *args, **kwargs: (lambda obj: obj)

    deepagents = _ensure_module("deepagents")
    deepagents.create_deep_agent = lambda *args, **kwargs: None
    deepagents.FilesystemPermission = type("FilesystemPermission", (), {})

    backends = _ensure_module("deepagents.backends")
    dummy_backend = type("DummyBackend", (), {})
    backends.CompositeBackend = dummy_backend
    backends.FilesystemBackend = dummy_backend
    backends.LocalShellBackend = dummy_backend

    chat_models = _ensure_module("langchain.chat_models")
    chat_models.init_chat_model = lambda *args, **kwargs: None

    runnables = _ensure_module("langchain_core.runnables")
    runnables.RunnableConfig = dict

    tools_module = _ensure_module("langchain_core.tools")
    tools_module.BaseTool = type("BaseTool", (), {})
    tools_module.tool = lambda func: func

    class StructuredTool:
        @staticmethod
        def from_function(**kwargs):
            return kwargs

    tools_module.StructuredTool = StructuredTool

    client_module = _ensure_module("langchain_mcp_adapters.client")
    client_module.MultiServerMCPClient = type("MultiServerMCPClient", (), {})

    tavily_module = _ensure_module("langchain_tavily")
    tavily_module.TavilySearch = type("TavilySearch", (), {})

    agents_module = _ensure_module("agentic.app.agents")
    agents_module.AgentRegistry = type("AgentRegistry", (), {})

    custom_tools_module = _ensure_module("agentic.app.common.custom_tools")
    custom_tools_module.CustomToolLoader = type("CustomToolLoader", (), {})
    custom_tools_module.create_custom_tool = lambda *args, **kwargs: None
    custom_tools_module.update_custom_tool = lambda *args, **kwargs: None

    middleware_module = _ensure_module("agentic.app.common.middleware")
    middleware_module.ToolNotifierMiddleware = type("ToolNotifierMiddleware", (), {})

    config_module = _ensure_module("agentic.app.config")
    config_module.AgenticConfig = type("AgenticConfig", (), {})
    config_module.ToolConfig = type("ToolConfig", (), {})
    config_module.AgentConfig = type("AgentConfig", (), {})

    module_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "agentic"
        / "app"
        / "common"
        / "tools.py"
    )
    spec = importlib.util.spec_from_file_location("common_tools_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


common_tools = _load_common_tools_module()
split_agentic_cli_command = common_tools.split_agentic_cli_command


def test_split_simple_command():
    assert split_agentic_cli_command("agents list") == ["agents", "list"]


def test_split_single_quoted_json_payload():
    args = split_agentic_cli_command(
        "agents write foo --config '{\"name\": \"foo\"}'"
    )
    assert args == ["agents", "write", "foo", "--config", '{"name": "foo"}']


def test_smart_quotes_are_normalized():
    # Curly/smart quotes an LLM might emit instead of straight quotes.
    args = split_agentic_cli_command("agents write foo --config \u2018{}\u2019")
    assert args == ["agents", "write", "foo", "--config", "{}"]


def test_unbalanced_quotes_raise_value_error_with_context():
    bad_command = "agents write foo --config '{\"name\": \"foo\"}"
    with pytest.raises(ValueError) as exc_info:
        split_agentic_cli_command(bad_command)

    message = str(exc_info.value)
    assert "sub_command received" in message
    assert repr(bad_command) in message


def test_apostrophe_inside_single_quotes_raises_helpful_error():
    # A contraction like "don't" prematurely closes the single-quoted
    # value, which is the real-world trigger for this failure mode.
    bad_command = "agents write foo --instructions 'don't touch this'"
    with pytest.raises(ValueError) as exc_info:
        split_agentic_cli_command(bad_command)

    assert "apostrophe" in str(exc_info.value)


def test_register_workspace_sub_agents_allows_missing_agent_registry(monkeypatch, tmp_path):
    agent_dir = tmp_path / "agents" / "writer"
    agent_dir.mkdir(parents=True)

    tool_registry = SimpleNamespace(register_tool=MagicMock())
    agent = object()

    monkeypatch.setattr(common_tools, "_create_sub_agent", lambda *args: agent)
    monkeypatch.setattr(
        common_tools,
        "agent_as_tool",
        lambda agent, name, description: f"tool:{name}:{description}",
    )

    registered = common_tools.register_workspace_sub_agents(
        tool_registry,
        SimpleNamespace(
            workspace=str(tmp_path),
            get_agent=lambda name: SimpleNamespace(name=name, description=f"{name} desc"),
        ),
    )

    assert registered == ["writer"]
    tool_registry.register_tool.assert_called_once_with(
        "writer", "tool:writer:writer desc"
    )
