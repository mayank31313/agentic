import asyncio
import json
import logging
import os
import re
import subprocess

import jinja2
from cndi.annotations import Autowired, Bean
from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend, LocalShellBackend
from langchain.chat_models import init_chat_model
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool, StructuredTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_tavily import TavilySearch
from pydantic import BaseModel, Field

from agentic.app.common.middleware import ToolNotifierMiddleware
from agentic.app.config import AgenticConfig, ToolConfig, AgentConfig

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
        tool_config = self.tools_config.get(name)
        if not tool_config:
            logger.warning(f"Tool not found hence skipping {name}")
            return
        if not tool_config.enabled:
            logger.info(f"Tool {name} is disabled; skipping registration")
            return

        func = callback(tool_config)
        self.register_tool(name, func)

    def register_tool(self, name, func):
        self.tools[name] = func
        logger.debug(f"Tool Registered {name}")

    def get_tools(self, tool_names: list[str], deniel_tool_names=None) -> list[BaseTool]:
        if deniel_tool_names is None:
            deniel_tool_names = {}
        tools = set()
        for tool_name in tool_names:
            if tool_name in self.tools:
                tools.add(tool_name)
                continue

            for tool in self.tools:
                if re.match(tool_name, tool) and tool_name not in deniel_tool_names:
                    tools.add(tool)

        return list(self.tools[x] for x in tools)


@Bean()
def getToolsRegistry(agentic_config: AgenticConfig) -> ToolsRegistry:
    registry = ToolsRegistry(agentic_config)
    mcp_servers = json.loads(jinja2.Template(json.dumps(agentic_config.mcpServers)).render(env=os.environ))

    mcp_client = MultiServerMCPClient(mcp_servers, tool_name_prefix=True)
    for mcp_tool in asyncio.run(mcp_client.get_tools()):
        registry.register_tool(mcp_tool.name, mcp_tool)
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

class SubAgentInput(BaseModel):
    input: str = Field(description="The task or question to hand off to this sub-agent")


def agent_as_tool(agent, name: str, description: str) -> StructuredTool:
    """Wrap a compiled (deep) agent graph as a LangChain tool."""

    def _run(input: str) -> str:
        result = agent.invoke({"messages": [{"role": "user", "content": input}]})
        return result["messages"][-1].content

    async def _arun(input: str) -> str:
        result = await agent.ainvoke({"messages": [{"role": "user", "content": input}]})
        return result["messages"][-1].content

    return StructuredTool.from_function(
        func=_run,
        coroutine=_arun,
        name=name,
        description=description,
        args_schema=SubAgentInput,
    )

@tool
def get_date_time() -> str:
    "Get the current date and time in ISO format with the day of the week."
    from datetime import datetime

    date_object = datetime.now()
    day_name = date_object.strftime("%A")
    return f"{date_object.isoformat()} ({day_name})"

@Autowired()
def set_common_tools(
    tool_registry: ToolsRegistry,
    agentic_config: AgenticConfig,
    tool_notifier_middleware: ToolNotifierMiddleware,
):

    @tool
    def send_message(message: str, config: RunnableConfig) -> str:
        "Send a message to a specified channel (e.g., Telegram) and return the status."
        # Here you would implement the actual sending logic using a Telegram bot API
        # For demonstration, we'll just log the message and return a success status.
        logger.info(f"Sending message to Telegram chat: {message}")
        return "Message sent to Telegram chat"

    @tool
    def list_available_tools() -> list[str]:
        "List all available tools in the registry"
        tools = []
        for key, tool in tool_registry.tools.items():
            tools.append(f"{key}: {tool.description}")
        return tools

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

    def tavily_search_tool(config: ToolConfig):
        tavily_search = TavilySearch(
            max_results=5,
            topic="general",
            tavily_api_key=config.api_key.resolve(),
        )
        return tavily_search.as_tool()

    def create_agent(agent_config: AgentConfig):
        model_config = agent_config.agent_model_config
        model = init_chat_model(
            model=model_config.model,
            base_url=model_config.base_url,
            api_key=model_config.api_key
            if type(model_config.api_key) is str
            else model_config.api_key.resolve(),
        )

        tools_ = tool_registry.get_tools(list(map(lambda x: x.name, agent_config.tools)))
        logger.info(f"Creating agent {agent_config.name} with tools: {[tool.name for tool in tools_]}")
        agent = create_deep_agent(
            model=model,
            backend=CompositeBackend(default=FilesystemBackend(root_dir="./workspace", virtual_mode=True),
                         routes={
                             "/workspace/": FilesystemBackend(root_dir="./workspace", virtual_mode=True),
            }),
            system_prompt=agent_config.instructions,
            tools=tools_ or [],
            middleware=[tool_notifier_middleware]
        )
        return agent

    tool_registry.add_tool("tavily_search", tavily_search_tool)

    @tool
    def agentic_run_agentic_cli(sub_command: str) -> str:
        """Run a command in the agentic CLI and return its output. Only allows sub_commands use --help for more information.

        You MUST use this tool for ANY interaction with the Agentic Config
        (`resources/agentic.json` / `AgenticConfig`) or an agent's config
        (`workspace/agents/<name>/instructions.md` / `AgentConfig`) — e.g.
        getting, setting, or otherwise inspecting or mutating config values
        (`agentic config get/set ...`), and listing, validating, creating,
        or updating agents (`agentic agents list/validate/write/update ...`).
        Never edit `resources/agentic.json` or
        `workspace/agents/<name>/instructions.md` directly with a file-write
        tool; always go through this CLI so changes are schema-validated.
        Run with `--help` on any sub_command to see its full usage first.
        """
        try:
            result = subprocess.run(
                f"uv run agentic {sub_command}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]\n{result.stderr}"
            return output.strip() or "(command produced no output)"
        except subprocess.TimeoutExpired:
            return "Error: command timed out after 30s"
        except Exception as e:
            return f"Error running command: {e}"

    tool_registry.register_tool("agentic_run_agentic_cli", agentic_run_agentic_cli)
    tool_registry.register_tool("run_shell_command", run_shell_command)
    tool_registry.register_tool("swamp_sub_agent", swamp_sub_agent)
    tool_registry.register_tool("list_available_tools", list_available_tools)
    tool_registry.register_tool("send_message", send_message)
    tool_registry.register_tool("get_date_time", get_date_time)

    agents_path = os.path.join(agentic_config.workspace, 'agents')
    agent_dirs = filter(lambda x: x != 'main' and os.path.isdir(os.path.join(agents_path, x)), os.listdir(agents_path))
    for agent_dir in agent_dirs:
        agent_config = agentic_config.get_agent(agent_dir)
        agent = create_agent(agent_config)

        tool_registry.register_tool(agent_config.name, agent_as_tool(
            agent,
            name=agent_config.name,
            description=agent_config.description,  # or a dedicated `description` field
        ))