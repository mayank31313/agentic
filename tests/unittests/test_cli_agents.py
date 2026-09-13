"""Unit tests for the `agentic agents` CLI commands.

Focused on `agents show`, the read-only command used by the
`agent_creator` meta-agent to fetch an existing agent's exact current
JSON header + instructions body before constructing a targeted
`agents update` edit (see `workspace/agents/agent_creator/instructions.md`).
"""

import json

import pytest
from click.testing import CliRunner

from agentic.cli.agents import agents

AGENTIC_JSON = {
    "workspace": "./workspace",
    "models": [
        {
            "model": "openai:nvidia/nemotron-3-super-120b-a12b",
            "model_id": "custom-nemotron-3-super-120b-a12b",
            "context_window": 128000,
            "base_url": "https://integrate.api.nvidia.com/v1",
            "api_key": {"env_key": "NVIDIA_API_KEY"},
        }
    ],
    "mcpServers": {},
}


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    """Set up a temp workspace with one existing agent + an agentic.json."""
    monkeypatch.chdir(tmp_path)

    config_path = tmp_path / "agentic.json"
    config_path.write_text(json.dumps(AGENTIC_JSON), encoding="utf-8")

    agent_dir = tmp_path / "workspace" / "agents" / "sample_agent"
    agent_dir.mkdir(parents=True)
    header = {
        "workspace_dir": "./workspace",
        "name": "sample_agent",
        "description": "A sample agent for tests",
        "model_id": "custom-nemotron-3-super-120b-a12b",
        "tools": [],
        "denied_tools": ["execute_code"],
        "skills": [],
    }
    body = "# Sample Agent — System Prompt\n\nYou are a sample agent.\n"
    (agent_dir / "instructions.md").write_text(
        json.dumps(header, indent=2) + "\n---\n" + body, encoding="utf-8"
    )

    return {"config_path": str(config_path), "agent_dir": agent_dir, "body": body, "header": header}


def test_show_prints_header_and_instructions(workspace):
    runner = CliRunner()
    result = runner.invoke(agents, ["show", "sample_agent", workspace["config_path"]])

    assert result.exit_code == 0, result.output
    assert "--- CONFIG" in result.output
    assert "--- INSTRUCTIONS ---" in result.output
    assert '"name": "sample_agent"' in result.output
    assert workspace["body"].strip() in result.output


def test_show_does_not_modify_the_file(workspace):
    runner = CliRunner()
    agent_path = workspace["agent_dir"] / "instructions.md"
    before = agent_path.read_text(encoding="utf-8")

    result = runner.invoke(agents, ["show", "sample_agent", workspace["config_path"]])

    assert result.exit_code == 0, result.output
    after = agent_path.read_text(encoding="utf-8")
    assert before == after


def test_show_missing_agent_errors(workspace):
    runner = CliRunner()
    result = runner.invoke(agents, ["show", "does_not_exist", workspace["config_path"]])

    assert result.exit_code != 0
    assert "not found" in result.output

