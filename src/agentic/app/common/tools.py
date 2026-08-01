import asyncio
import subprocess
from typing import List

from cndi.annotations import Autowired
from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend, LocalShellBackend
from langchain_core.tools import tool, BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_tavily import TavilySearch
from pydantic import BaseModel, Field

from app.channels.telegram import ToolsRegistry
from app.config import AgenticConfig


class SubAgentDetails(BaseModel):
    system_prompt: str = Field(description="System prompt instructions that agent should follow, use role play to make agent behave in certain way")
    task: str = Field(description="Task to swamp subagent")
    context: str = Field(description="Required context and information to complete the task")

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
def set_common_tools(tool_registry: ToolsRegistry,
                     agentic_config: AgenticConfig):
    tavily_search = TavilySearch(
        max_results=5,
        topic="general"
    )

    @tool
    def swamp_sub_agent(sub_agent_details: SubAgentDetails):
        "Tool to swamp a sub agent to reserve context"
        main_agent_config = agentic_config.get_agent('main')
        if not main_agent_config:
            raise ValueError("Main agent configuration not found in agentic config.")

        sub_agent = create_deep_agent(
            model=main_agent_config.model,
            backend=CompositeBackend(
                default=FilesystemBackend(root_dir="./workspace", virtual_mode=True),
                routes={
                    "/images/": FilesystemBackend(root_dir="./images", virtual_mode=True),
                    "/skills/": LocalShellBackend(root_dir="./skills", virtual_mode=True,
                                                  env={"PATH": "/usr/bin:/bin"}),
                },
            ),
            skills=['/skills/'],
            system_prompt=sub_agent_details.system_prompt,
        )

        messages = sub_agent.invoke(dict(
            messages=f"""You are required to complete the task: {sub_agent_details.task}\n\nHere is the full information required to complete the task\n\n{sub_agent_details.context}"""))[
            'messages']
        return messages[-1]


    if agentic_config.mcpServers:
        client = MultiServerMCPClient(agentic_config.mcpServers)
        tools: List[BaseTool] = asyncio.run(client.get_tools())
        for mcp_tool in tools:
            tool_registry.register_tool(mcp_tool.name, mcp_tool)


    tool_registry.register_tool('tavily_search', tavily_search.as_tool())
    tool_registry.register_tool('run_shell_command', run_shell_command)
    tool_registry.register_tool('swamp_sub_agent', swamp_sub_agent)