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

import pytest


# Names of every module this loader fakes out, so `agentic.app.common.tools`
# can be exec'd standalone without pulling in heavy optional deps
# (deepagents, langchain_mcp_adapters, etc.) or a real agentic config.
#
# Every one of these is faked with a plain `MagicMock` rather than a real
# import or a hand-written stub object/lambda: `tools.py` only *uses* these
# names as decorators (`@Bean()`, `@Autowired()`, `@tool`), type hints
# (`AgentRegistry | None`), or classes it calls at call time (e.g.
# `StructuredTool.from_function(...)`) — none of that is exercised by the
# functions actually under test here (`split_agentic_cli_command`,
# `register_workspace_sub_agents`), and `MagicMock` auto-generates whatever
# attribute/callable/magic-method (`__or__` for the `X | None` unions,
# `__call__` for decorators, etc.) is accessed, so there is nothing to wire
# up by hand.
#
# IMPORTANT: several of these (e.g. "agentic.app.config",
# "agentic.app.common.custom_tools") are *real* modules that other test
# files (test_cli_agents.py, test_custom_tools.py) import and use as-is.
# If this module happens to be imported/collected in the same pytest
# session (pytest imports every collected test file up front, regardless
# of run order), naively fetching an already-imported real module from
# `sys.modules` and overwriting its attributes in place would permanently
# replace e.g. the real `AgenticConfig`/`update_custom_tool` with fakes for
# the rest of the session, breaking unrelated tests. To avoid that, every
# fake module below is installed fresh via `sys.modules[name] = MagicMock()`
# (never mutating a pre-existing module object), and the previous
# `sys.modules` state is restored once this module has finished loading.
_FAKE_MODULE_NAMES = (
    "agentic",
    "agentic.app",
    "agentic.app.common",
    "cndi.annotations",
    "deepagents",
    "deepagents.backends",
    "langchain.chat_models",
    "langchain_core.runnables",
    "langchain_core.tools",
    "langchain_mcp_adapters.client",
    "langchain_tavily",
    "agentic.app.agents",
    "agentic.app.common.custom_tools",
    "agentic.app.common.middleware",
    "agentic.app.config",
)


def _load_common_tools_module():
    # Snapshot whatever's currently in sys.modules for every name we're
    # about to fake, so it can be restored afterward instead of clobbered.
    originals = {name: sys.modules.get(name) for name in _FAKE_MODULE_NAMES}

    for name in _FAKE_MODULE_NAMES:
        sys.modules[name] = MagicMock(name=name)

    try:

        module_path = (
            Path(__file__).resolve().parents[2]
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
    finally:
        # Restore sys.modules exactly as it was before this function ran,
        # regardless of success/failure, so real modules imported by other
        # test files are never left pointing at these fakes.
        for name, original in originals.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


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
