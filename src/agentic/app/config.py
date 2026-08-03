import logging
import os.path
from typing import List, Tuple, Dict, Optional, Any, Union
from pydantic import BaseModel, Field

class FromEnv(BaseModel):
    env_key: str = Field(description="Environment variable key to fetch the value from")

    def resolve(self) -> str:
        """Resolve the value from the environment variable."""
        env_value = os.getenv(self.env_key)
        if env_value is None:
            raise ValueError(f"Environment variable '{self.env_key}' is not set.")
        return env_value

    def __str__(self):
        return self.resolve()

class ToolConfig(BaseModel):
    name: str = Field(description='Tool name')
    require_approval: bool = Field(description='If tool needs human in loop for approval')
    approval_text: Optional[str] = Field(default=None, description="Text to show when requesting approval")
class SkillsConfig(BaseModel):
    path: str
    virtual_path: str = Field(description="Virtual path for the skill, if different from the name")

class ModelConfig(BaseModel):
    model: str = Field(description="Model name with provider, e.g., openai:gemma-4-e2b-it")
    model_id: str = Field(description="Model ID for the model, e.g., gemma-4-e2b-it")
    base_url: str = Field(
        default_factory=lambda: os.getenv("OPENAI_API_BASE", "https://integrate.api.nvidia.com/v1")
    )
    api_key: Union[str, FromEnv] = Field(
        default_factory=lambda: FromEnv(env_key="OPENAI_API_KEY"), union_mode='left_to_right'
    )
    context_window: int = Field(default=128000)

class AgentConfig(BaseModel):
    system_prompt_path: str
    workspace_dir: str
    name: str
    model_id: str
    tools: Optional[Tuple[ToolConfig, ...]] = Field(default_factory=tuple)
    denied_tools: Optional[Tuple[str, ...]] = Field(default_factory=tuple)
    skills: Optional[List[SkillsConfig]] = Field(default_factory=tuple, description="List of skills path")
    agent_model_config: Optional[ModelConfig] = Field(default=None, description="Model configuration for the agent")

class AgenticConfig(BaseModel):
    workspace: str
    agents: list[AgentConfig] = Field(description="List of agents")
    mcpServers: Dict[str, dict] = Field(description="MCP Server configuration")
    models: list[ModelConfig] = Field(description="List of models")


    def get_agent(self, name: str) -> Optional[AgentConfig]:
        for agent in self.agents:
            if agent.name == name:
                return agent
        return None


logger = logging.getLogger(__name__)

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
