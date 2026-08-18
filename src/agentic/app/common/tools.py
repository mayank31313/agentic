import asyncio
import json
import logging
import os
import subprocess

import jinja2
from cndi.annotations import Autowired, Bean
from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend, LocalShellBackend
from langchain_core.tools import BaseTool, tool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_tavily import TavilySearch
from pydantic import BaseModel, Field

from agentic.app.agents import AgentRegistry
from agentic.app.config import AgenticConfig, ToolConfig

logger = logging.getLogger(__name__)


class SubAgentDetails(BaseModel):
    system_prompt: str = Field(
        description="System prompt instructions that agent should follow, use role play to make agent behave in certain way"
    )
    task: str = Field(description="Task to swamp subagent")
    context: str = Field(
        description="Required context and information to complete the task"
    )


class ToolsRegistry:
    def __init__(self, agentic_config: AgenticConfig):
        self.tools = dict()
        self.tools_config = dict((tool_config.name, tool_config) for tool_config in agentic_config.tools)

    def add_tool(self, name, callback):
        if name in self.tools_config:
            for n, tool_config in self.tools_config.items():
                if tool_config.enabled:
                    func = callback(tool_config)
                    self.register_tool(name, func)
                    return
        else:
            logger.warning(f"Tool not found hence skipping {name}")

    def register_tool(self, name, func):
        self.tools[name] = func
        logger.debug(f"Tool Registered {name}")

    def get_tools(self, tool_names: list[str]) -> list[BaseTool]:
        tools = []
        for tool_name in tool_names:
            tools.append(self.tools[tool_name])

        return tools


@Bean()
def getToolsRegistry(agentic_config: AgenticConfig) -> ToolsRegistry:
    registry = ToolsRegistry(agentic_config)
    return registry


@tool
def run_shell_command(command: str) -> str:
    "Run a shell command and return its output. If the command fails, return the error message."
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=30
        )
        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr}"
        return output.strip() or "(command produced no output)"
    except subprocess.TimeoutExpired:
        return "Error: command timed out after 30s"
    except Exception as e:
        return f"Error running command: {e}"


@Autowired()
def set_common_tools(
    tool_registry: ToolsRegistry,
    agentic_config: AgenticConfig,
    agent_registry: AgentRegistry,
):

    @tool
    def send_message(message: str) -> str:
        "Send a message to a specified channel (e.g., Telegram) and return the status."
        # Here you would implement the actual sending logic using a Telegram bot API
        # For demonstration, we'll just log the message and return a success status.
        logger.info(f"Sending message to Telegram chat: {message}")
        return "Message sent to Telegram chat"

    @tool
    def list_registered_agents() -> list[str]:
        "List all registered agents in the registry"
        return list(agent_registry.agents.keys())

    @tool
    def list_available_tools() -> list[str]:
        "List all available tools in the registry"
        return list(tool_registry.tools.keys())

    @tool
    def swamp_sub_agent(sub_agent_details: SubAgentDetails):
        "Tool to swamp a sub agent to reserve context"
        main_agent_config = agentic_config.get_agent("main")
        if not main_agent_config:
            raise ValueError("Main agent configuration not found in agentic config.")

        sub_agent = create_deep_agent(
            model=main_agent_config.model,
            backend=CompositeBackend(
                default=FilesystemBackend(root_dir="./workspace", virtual_mode=True),
                routes={
                    "/images/": FilesystemBackend(
                        root_dir="./images", virtual_mode=True
                    ),
                    "/skills/": LocalShellBackend(
                        root_dir="./skills",
                        virtual_mode=True,
                        env={"PATH": "/usr/bin:/bin"},
                    ),
                },
            ),
            skills=["/skills/"],
            system_prompt=sub_agent_details.system_prompt,
        )

        messages = sub_agent.invoke(
            dict(
                messages=f"""You are required to complete the task: {sub_agent_details.task}\n\nHere is the full information required to complete the task\n\n{sub_agent_details.context}"""
            )
        )["messages"]
        return messages[-1]

    if agentic_config.mcpServers:
        mcpServers = json.loads(jinja2.Template(json.dumps(agentic_config.mcpServers))
         .render(env=os.environ))
        client = MultiServerMCPClient(mcpServers)
        tools: list[BaseTool] = asyncio.run(client.get_tools())
        for mcp_tool in tools:
            tool_registry.register_tool(mcp_tool.name, mcp_tool)

    def tavily_search_tool(config: ToolConfig):
        tavily_search = TavilySearch(
            max_results=5,
            topic="general",
            tavily_api_key=config.api_key.resolve(),
        )
        return tavily_search.as_tool()

    tool_registry.add_tool("tavily_search", tavily_search_tool)

    tool_registry.register_tool("run_shell_command", run_shell_command)
    tool_registry.register_tool("swamp_sub_agent", swamp_sub_agent)
    tool_registry.register_tool("list_available_tools", list_available_tools)
    tool_registry.register_tool("send_message", send_message)
    tool_registry.register_tool("list_registered_agents", list_registered_agents)
