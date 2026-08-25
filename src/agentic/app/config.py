import json
import logging
import os.path
from typing import Any, Optional

from pydantic import BaseModel, Field, BaseConfig


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


class AgentToolConfig(BaseModel):
    name: str = Field(description="Tool name")
    require_approval: bool = Field(
        description="If tool needs human in loop for approval"
    )
    approval_text: str | None = Field(
        default=None, description="Text to show when requesting approval"
    )

class ToolConfig(BaseModel):
    name: str = Field(description="Tool name")
    enabled: bool = Field(default=False, description="Whether the tool is enabled")
    api_key: FromEnv = Field(default=None)

class SkillsConfig(BaseModel):
    path: str
    virtual_path: str = Field(
        description="Virtual path for the skill, if different from the name"
    )


class ModelConfig(BaseModel):
    model: str = Field(
        description="Model name with provider, e.g., openai:gemma-4-e2b-it"
    )
    model_id: str = Field(description="Model ID for the model, e.g., gemma-4-e2b-it")
    base_url: str = Field(
        default_factory=lambda: os.getenv(
            "OPENAI_API_BASE", "https://integrate.api.nvidia.com/v1"
        )
    )
    api_key: str | FromEnv = Field(
        default_factory=lambda: FromEnv(env_key="OPENAI_API_KEY"),
        union_mode="left_to_right",
    )
    context_window: int = Field(default=128000)


class AgentConfig(BaseModel):
    system_prompt_path: Optional[str] = Field(None)
    workspace_dir: str
    name: str
    description: str
    model_id: str
    tools: tuple[AgentToolConfig, ...] | None = Field(default_factory=lambda x: None if x is None else AgentToolConfig.model_validate(json.loads(x) if isinstance(x, str) else x),)
    denied_tools: tuple[str, ...] | None = Field(default_factory=tuple)
    skills: list[SkillsConfig] | None = Field(
        default_factory=lambda x: None if x is None else SkillsConfig.model_validate(json.loads(x) if isinstance(x, str) else x), description="List of skills path"
    )
    agent_model_config: Optional[ModelConfig] = Field(None, description="Agent model config")
    instructions: Optional[str] = Field(default=None)

    @staticmethod
    def load(path, agentic_config: AgenticConfig) -> AgentConfig:
        with open(path, "r", encoding="utf-8") as agent_file:
            content = agent_file.read()
            # Split on the *first* bare "---" only: the JSON header and the
            # markdown body are separated by exactly one such line, but the
            # markdown body itself may legitimately contain "---" (e.g. when
            # documenting this very file format), so a naive split("---")
            # would break on those.
            if "\n---\n" in content:
                config, instructions = content.split("\n---\n", 1)
            else:
                config, instructions = content.split("---", 1)
            configs = json.loads(config)
            return AgentConfig(**configs, instructions=instructions,
                               agent_model_config=agentic_config.get_model(configs.get('model_id')))

    def dump(self, path):
        skip_flags = ("system_prompt_path", "instructions", "agent_model_config")
        file_contents = []
        with open(path, 'w', encoding="utf-8") as file:
            configs = self.model_dump(mode='json', exclude=set(skip_flags))

            file_contents.append(json.dumps(configs, indent=2) + "\n")
            file_contents.append("---\n")
            file_contents.append(self.instructions)

            file.writelines(file_contents)

class AgenticConfig(BaseModel):
    workspace: str
    mcpServers: dict[str, dict] = Field(description="MCP Server configuration")
    models: list[ModelConfig] = Field(description="List of models")
    tools: tuple[ToolConfig] = Field(default_factory=tuple, description="List of tools")

    def get_tool(self, tool_name: str):
        return next(filter(lambda x: x.enabled and x.name == tool_name, self.tools))

    def get_model(self, model_id: str) -> ModelConfig | None:
        for model in self.models:
            if model.model_id == model_id:
                return model
        return None

    def get_agent(self, name: str) -> AgentConfig:
        agent_file  = f"{self.workspace}/agents/{name}/instructions.md"
        if os.path.exists(agent_file):
            return AgentConfig.load(agent_file, self)
        else:
            raise FileNotFoundError(f"Agent {name} not found on path {agent_file}")

    def list_agent_names(self) -> list[str]:
        """Discover agent names from the `<workspace>/agents/*/instructions.md` layout.

        This is the single source of truth for available agents (see
        `docs/creating-agents-and-skills.md`) — there is no separate
        `agents` list in the JSON config.
        """
        agents_dir = os.path.join(self.workspace, "agents")
        if not os.path.isdir(agents_dir):
            return []

        names = []
        for entry in sorted(os.listdir(agents_dir)):
            agent_dir = os.path.join(agents_dir, entry)
            instructions_path = os.path.join(agent_dir, "instructions.md")
            if os.path.isdir(agent_dir) and os.path.isfile(instructions_path):
                names.append(entry)
        return names

    def list_agents(self) -> list[tuple[str, "AgentConfig | None", Exception | None]]:
        """Load every agent found by `list_agent_names`.

        Returns a list of `(name, agent_config_or_none, error_or_none)`
        tuples so callers (e.g. the CLI) can report per-agent failures
        without aborting the whole listing.
        """
        results = []
        for name in self.list_agent_names():
            try:
                results.append((name, self.get_agent(name), None))
            except Exception as e:  # noqa: BLE001 - surfaced to caller, not swallowed
                results.append((name, None, e))
        return results

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
