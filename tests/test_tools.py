"""Unit tests for agentic.app.common.tools helpers.

These target ``split_agentic_cli_command`` in isolation, since the full
tool registry (``register_common_tools`` and friends) pulls in heavy
optional dependencies (deepagents, langchain_mcp_adapters, etc.) that
aren't needed to exercise the CLI argument quoting logic.
"""

import pytest

from agentic.app.common.tools import split_agentic_cli_command


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


