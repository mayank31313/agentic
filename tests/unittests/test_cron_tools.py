from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from agentic.app.scheduler.tools import (
    SubAgentConfig,
    check_agent_exists,
    get_cron_tools,
)


@pytest.mark.parametrize("name", ["main", "trip_planner", "agent-2", " main "])
def test_valid_agent_names(name):
    assert SubAgentConfig(agent_name=name).agent_name == name.strip()


@pytest.mark.parametrize(
    "name", ["", "   ", "../etc", "a/b", "a\\b", "bad name", "agent.md"]
)
def test_invalid_agent_names_rejected(name):
    with pytest.raises(ValidationError):
        SubAgentConfig(agent_name=name)


def test_check_agent_exists():
    config = SimpleNamespace(list_agent_names=lambda: ["main", "trip_planner"])
    assert check_agent_exists(config, "main") is None
    assert check_agent_exists(None, "anything") is None
    error = check_agent_exists(config, "ghost")
    assert "ghost" in error and "main, trip_planner" in error


def test_create_cron_tool_rejects_unknown_agent(tmp_path, monkeypatch):
    monkeypatch.setenv("CRON_SCHEDULE_FILENAME", str(tmp_path / "cron.json"))
    config = SimpleNamespace(list_agent_names=lambda: ["main"])
    create_tool = get_cron_tools(event_bus=None, agentic_config=config)[0]

    result = create_tool.invoke(
        {
            "cron_settings": {"task": "t", "cron_expression": "0 9 * * *", "name": "n"},
            "sub_agent_config": {"agent_name": "ghost"},
        }
    )

    assert "does not exist" in result
    assert not (tmp_path / "cron.json").exists()

