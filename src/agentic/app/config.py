import json
import logging
import os.path
from typing import List, Tuple, Dict, Optional, Any

from cndi.annotations import Bean
from cndi.env import getContextEnvironment
from pydantic import BaseModel, Field

from app.constants import AGENTIC_FILE_NAME_PROP

class ToolConfig(BaseModel):
    name: str = Field(description='Tool name')
    require_approval: bool = Field(description='If tool needs human in loop for approval')
    approval_text: Optional[str] = Field(default=None, description="Text to show when requesting approval")

class AgentConfig(BaseModel):
    system_prompt_path: str
    workspace_dir: str
    name: str
    model: str
    context_window: int = Field(default=128000)
    tools: Optional[Tuple[ToolConfig, ...]] = Field(default_factory=tuple)
    denied_tools: Optional[Tuple[str, ...]] = Field(default_factory=tuple)
    base_url: str = Field(
        default_factory=lambda: os.getenv("OPENAI_API_BASE", "https://integrate.api.nvidia.com/v1")
    )
    api_key: str = Field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY")
    )

class Skillsconfig(BaseModel):
    name: str
    path: str


class AgenticConfig(BaseModel):
    workspace: str
    agents: list[AgentConfig] = Field(description="List of agents")
    mcpServers: Dict[str, dict] = Field(description="MCP Server configuration")
    skills: Optional[List[Skillsconfig]] = Field(default_factory=list, description="List of skills")

    def get_agent(self, name: str) -> Optional[AgentConfig]:
        for agent in self.agents:
            if agent.name == name:
                return agent
        return None


logger = logging.getLogger(__name__)

@Bean()
def getAgenticConfig() -> AgenticConfig:
    filename = getContextEnvironment(AGENTIC_FILE_NAME_PROP)
    try:
        if os.path.exists(filename):
            with open(filename, "r") as config_json:
                return AgenticConfig.model_validate(json.load(config_json))
    except Exception as e:
        pass
    with open(filename, "w") as config_json:
        agentic = AgenticConfig(
            workspace="./workspace",
            agents=[
                AgentConfig(
                    system_prompt_path="AGENTS.md",
                    workspace_dir="./workspace",
                    name="main",
                    model="openai:nvidia/nemotron-3-super-120b-a12b",
                    base_url="https://integrate.api.nvidia.com/v1",
                    tools=tuple([ToolConfig(name='run_shell_command', require_approval=True, approval_text="This tool needs approval to run"),
                                 ToolConfig(name='generate_image', require_approval=False),
                                 ToolConfig(name='swamp_sub_agent', require_approval=False)]),
                    denied_tools=tuple([])
                )
            ],
            mcpServers={
                "alice_mcps": {
                    "url": "http://localhost:8811/sse",
                    "transport": "sse",
                    "headers": {
                        "Authorization": "Bearer 6s4uic0iosrjefufic7hiiuv6jp9qtm0a6fk5qg4x7565nng59"
                    }
                }
            }
        )

        json.dump(agentic.model_dump(mode="json"), fp=config_json, indent=4)

    return agentic


class UpdateJsonConfigRequest(BaseModel):
    key_path: str = Field(
        ...,
        description="Dot-separated path to the field to update, e.g. 'db.host' for "
                    "a nested key, or 'servers.0.port' for an index into a list.",
    )
    value: Any = Field(..., description="The new value to set at the given key path.")


def get_nested(data: dict, path: str) -> Any:
    """Get a value at a dot-path like 'db.host' or 'servers.0.port' (numeric = list index)."""
    keys = path.split(".")
    current = data
    for key in keys:
        if isinstance(current, list):
            current = current[int(key)]
        else:
            current = current[key]
    return current


def set_nested(data: dict, path: str, value: Any) -> None:
    """Set a value at a dot-path, creating intermediate dicts as needed."""
    keys = path.split(".")
    current = data
    for key in keys[:-1]:
        if isinstance(current, list):
            current = current[int(key)]
        else:
            if key not in current or not isinstance(current[key], (dict, list)):
                current[key] = {}
            current = current[key]

    last_key = keys[-1]
    if isinstance(current, list):
        current[int(last_key)] = value
    else:
        current[last_key] = value
