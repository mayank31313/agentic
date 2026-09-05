import asyncio
import json
import logging
import os
import re
import shlex
import subprocess
from typing import Literal

import jinja2
from cndi.annotations import Autowired, Bean
from deepagents import create_deep_agent, FilesystemPermission
from deepagents.backends import CompositeBackend, FilesystemBackend, LocalShellBackend
from langchain.chat_models import init_chat_model
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool, StructuredTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_tavily import TavilySearch
from pydantic import BaseModel, Field

from agentic.app.agents import AgentRegistry
from agentic.app.common.custom_tools import CustomToolLoader, create_custom_tool as _write_custom_tool_files
from agentic.app.common.custom_tools import update_custom_tool as _update_custom_tool_files
from agentic.app.common.middleware import ToolNotifierMiddleware
from agentic.app.config import AgenticConfig, ToolConfig, AgentConfig

logger = logging.getLogger(__name__)

# Curly/smart quotes that LLMs sometimes emit instead of straight ASCII
# quotes. shlex only understands straight quotes, so a smart quote reads as
# a literal character and the *next* straight quote it hits looks unbalanced
# to the parser. Normalizing these before parsing avoids a confusing
# "unbalanced quotes" error for what is really a smart-quote typo.
_SMART_QUOTE_MAP = str.maketrans(
    {
        "\u2018": "'",  # left single quote
        "\u2019": "'",  # right single quote
        "\u201c": '"',  # left double quote
        "\u201d": '"',  # right double quote
    }
)


def split_agentic_cli_command(sub_command: str) -> list[str]:
    """Parse ``sub_command`` into an argv list using POSIX shell quoting.

    Extracted as a standalone, side-effect-free function so the quoting
    behaviour (including the smart-quote normalization and the unbalanced
    quotes failure mode) can be unit tested without constructing the full
    tool registry.

    Raises:
        ValueError: if ``sub_command`` cannot be parsed as valid POSIX shell
            syntax (e.g. unbalanced quotes). The error message always
            includes the offending ``sub_command`` so it can be diagnosed
            from the tool's error output alone.
    """
    normalized = sub_command.translate(_SMART_QUOTE_MAP)
    try:
        return shlex.split(normalized, posix=True)
    except ValueError as e:
        raise ValueError(
            f"{e} (sub_command received: {sub_command!r}). Tip: if a single-quoted "
            "value contains an apostrophe (e.g. \"don't\"), it will prematurely "
            "close the quote — reword the text or use \\' escaping instead."
        ) from e


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

    def reload_mcp_tools(self, mcp_servers: dict) -> list[str]:
        """Re-fetch tools from the configured MCP servers and (re-)register
        them. Safe to call repeatedly (e.g. after adding a new MCP server or
        a new tool on an already-running MCP server) without restarting the
        bot process.
        """
        rendered = json.loads(jinja2.Template(json.dumps(mcp_servers)).render(env=os.environ))
        mcp_client = MultiServerMCPClient(rendered, tool_name_prefix=True)
        registered = []
        for mcp_tool in asyncio.run(mcp_client.get_tools()):
            self.register_tool(mcp_tool.name, mcp_tool)
            registered.append(mcp_tool.name)
        return registered

    def reload_custom_tools(self, agentic_config: "AgenticConfig") -> list[str]:
        """Re-scan `<workspace>/custom_tools/` and (re-)register any custom
        tools authored via `create_custom_tool` (see
        `agentic.app.common.custom_tools`)."""
        loader = CustomToolLoader(agentic_config.workspace)
        registered = []
        for tool in loader.load_all():
            self.register_tool(tool.name, tool)
            registered.append(tool.name)
        return registered

    def refresh(
        self,
        agentic_config: AgenticConfig,
        tool_notifier_middleware: ToolNotifierMiddleware | None = None,
    ) -> dict[str, list[str]]:
        """Refresh every dynamic tool source (MCP servers, workspace
        sub-agents, agent-authored custom tools) without a full process
        restart. Returns a summary of what was (re-)registered per source.

        NOTE: this only refreshes the *registry*. The compiled agent graph
        (`get_main_agent`) still needs to be rebuilt — see
        `AgenticBot.reload_tools` — for the change to actually be usable in
        a running conversation, and rebuilding drops in-flight conversation
        state (a fresh in-memory checkpointer is created).
        """
        summary = {"mcp": self.reload_mcp_tools(agentic_config.mcpServers)}
        if tool_notifier_middleware is not None:
            summary["agents"] = register_workspace_sub_agents(
                self, agentic_config, tool_notifier_middleware
            )
        else:
            summary["agents"] = []
        summary["custom"] = self.reload_custom_tools(agentic_config)
        return summary


@Bean()
def getToolsRegistry(agentic_config: AgenticConfig) -> ToolsRegistry:
    registry = ToolsRegistry(agentic_config)
    registry.reload_mcp_tools(agentic_config.mcpServers)
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


def _create_sub_agent(agent_config: AgentConfig, tool_registry: "ToolsRegistry", tool_notifier_middleware):
    """Compile a `workspace/agents/<name>/` config into a runnable deep agent."""
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
    agent_skill_paths = set()
    routes = {}
    for skill_config in agent_config.skills:
        logger.info(
            f"Adding skill route for {skill_config.virtual_path} at path {skill_config.path}"
        )
        routes[skill_config.virtual_path] = FilesystemBackend(
            root_dir=skill_config.path, virtual_mode=True
        )
        agent_skill_paths.add(skill_config.virtual_path)

    agent = create_deep_agent(
        model=model,
        backend=CompositeBackend(
            default=FilesystemBackend(root_dir="./workspace", virtual_mode=True),
            routes=routes,
        ),
        skills=list(agent_skill_paths),
        system_prompt=agent_config.instructions,
        tools=tools_ or [],
        middleware=[tool_notifier_middleware],
    )
    return agent


def register_workspace_sub_agents(
    tool_registry: ToolsRegistry,
    agentic_config: AgenticConfig,
    tool_notifier_middleware: ToolNotifierMiddleware | None = None,
    agent_registry: AgentRegistry | None = None,
) -> list[str]:
    """(Re-)discover `workspace/agents/<name>/` (excluding "main") and
    register each as a callable tool wrapping a compiled sub-agent graph.

    Safe to call again at any time (e.g. after a new agent was written via
    `agentic agents write`) — this only refreshes the `ToolsRegistry`; see
    `AgenticBot.reload_tools`/`agentic tools reload` to make a newly
    registered sub-agent tool usable in a running bot process.
    """
    agents_path = os.path.join(agentic_config.workspace, "agents")
    if not os.path.isdir(agents_path):
        return []

    registered = []
    agent_dirs = filter(
        lambda x: x != "main" and os.path.isdir(os.path.join(agents_path, x)),
        os.listdir(agents_path),
    )
    for agent_dir in agent_dirs:
        agent_config = agentic_config.get_agent(agent_dir)
        agent = _create_sub_agent(agent_config, tool_registry, tool_notifier_middleware)
        tool_registry.register_tool(
            agent_config.name,
            agent_as_tool(
                agent,
                name=agent_config.name,
                description=agent_config.description,
            ),
        )
        if agent_registry is not None:
            agent_registry.register_agent(agent_config.name, agent)
        registered.append(agent_config.name)
    return registered


@Autowired()
def set_common_tools(
    tool_registry: ToolsRegistry,
    agentic_config: AgenticConfig,
    tool_notifier_middleware: ToolNotifierMiddleware,
    agent_registry: AgentRegistry,
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


    tool_registry.add_tool("tavily_search", tavily_search_tool)

    AGENTIC_CLI_GROUPS = {"agents", "config", "mcp", "message", "run", "tools"}

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

        IMPORTANT — command groups are PLURAL: `agents`, `config`, `mcp`,
        `message`. The agent commands are `agentic agents write/update/
        validate/list/run/schema`. There is NO `agentic agent ...`
        (singular) command; do not guess that form.

        IMPORTANT — quoting: `sub_command` is parsed with POSIX/bash-style
        shell quoting (via `shlex`), NOT the host OS shell, and is then
        executed directly as an argument list (no shell involved). Always
        quote JSON payloads with single quotes exactly like a bash command
        line, e.g.:

            agents write weather_reporter --config '{"workspace_dir": "./workspace", "name": "weather_reporter", "description": "...", "model_id": "..."}' --instructions '# Weather Reporter\\n\\nYou are ...'

        This is interpreted the same way regardless of the underlying OS,
        so quoting rules never need to change between platforms.

        WARNING — apostrophes inside single-quoted values (e.g. "don't")
        will prematurely close the quote and cause an "unbalanced quotes"
        error. Avoid contractions/possessives inside single-quoted JSON
        strings, or escape them as \\' if you must use them.
        """
        try:
            args = split_agentic_cli_command(sub_command)
        except ValueError as e:
            return f"Error: sub_command could not be parsed: {e}"

        if not args:
            return "Error: sub_command is empty."

        if args[0] not in AGENTIC_CLI_GROUPS:
            return (
                f"Error: unknown command group '{args[0]}'. Valid top-level "
                f"groups are: {', '.join(sorted(AGENTIC_CLI_GROUPS))} (note: "
                "it is 'agents' plural, not 'agent')."
            )

        try:
            result = subprocess.run(
                ["uv", "run", "agentic", *args],
                shell=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]\n{result.stderr}"
            return output.strip() or "(command produced no output)"
        except subprocess.TimeoutExpired:
            return "Error: command timed out after 30s"
        except FileNotFoundError as e:
            return f"Error: could not locate the 'uv' executable on PATH: {e}"
        except Exception as e:
            return f"Error running command: {e}"

    tool_registry.register_tool("agentic_run_agentic_cli", agentic_run_agentic_cli)
    tool_registry.register_tool("run_shell_command", run_shell_command)
    tool_registry.register_tool("swamp_sub_agent", swamp_sub_agent)
    tool_registry.register_tool("list_available_tools", list_available_tools)
    tool_registry.register_tool("send_message", send_message)
    tool_registry.register_tool("get_date_time", get_date_time)

    class CreateCustomToolInput(BaseModel):
        name: str = Field(description="snake_case name for the new tool; must be unique")
        description: str = Field(description="What the tool does; shown to the LLM when deciding to use it")
        kind: Literal["python", "docker"] = Field(
            description="'python' for a sandboxed script (stdlib-only, subprocess-executed); "
                        "'docker' for a containerized script (stronger isolation, needs a Dockerfile)"
        )
        tool_args: dict[str, str] = Field(
            default_factory=dict,
            description="Mapping of argument name -> type (string|integer|number|boolean|array|object) "
                        "that the CREATED tool will accept when it is later called. This is NOT a "
                        "wrapper for this tool's own arguments — pass name/description/kind/etc. as "
                        "top-level fields, not nested inside this one.",
        )
        python_source_path: str | None = Field(
            default=None,
            description="Required for kind='python'. Workspace-relative path to a file YOU must write "
                        "first (with your filesystem write tool) defining a top-level `run(**kwargs)` "
                        "function, using only stdlib modules (json, math, re, datetime, itertools, "
                        "statistics, textwrap, typing, decimal, collections, string, random, uuid, "
                        "dataclasses, enum, functools). No file/network/subprocess/os access is allowed. "
                        "Do NOT pass source code content directly — write it to a file and pass the path.",
        )
        dockerfile_path: str | None = Field(
            default=None,
            description="Required for kind='docker'. Workspace-relative path to a Dockerfile you already "
                        "wrote. Do NOT pass Dockerfile content directly.",
        )
        entrypoint_path: str | None = Field(
            default=None,
            description="Required for kind='docker'. Workspace-relative path to the container's "
                        "entrypoint script you already wrote; it reads a JSON object of args from stdin "
                        "and writes the result to stdout. Do NOT pass script content directly.",
        )
        network_access: bool = Field(default=False, description="Docker kind only: allow container network access.")
        timeout_seconds: int = Field(default=30)

    def _create_custom_tool_impl(
        name: str,
        description: str,
        kind: str,
        tool_args: dict[str, str] = {},
        python_source_path: str | None = None,
        dockerfile_path: str | None = None,
        entrypoint_path: str | None = None,
        network_access: bool = False,
        timeout_seconds: int = 30,
    ) -> str:
        "Author and register a brand-new tool at runtime. Requires human approval; see docstring on the registered tool."
        try:
            _write_custom_tool_files(
                workspace=agentic_config.workspace,
                name=name,
                description=description,
                kind=kind,
                tool_args=tool_args,
                python_source_path=python_source_path,
                dockerfile_path=dockerfile_path,
                entrypoint_path=entrypoint_path,
                network_access=network_access,
                timeout_seconds=timeout_seconds,
            )
        except ValueError as e:
            return f"Error: could not create tool '{name}': {e}"

        tool_registry.reload_custom_tools(agentic_config)
        return (
            f"Custom tool '{name}' ({kind}) created and registered in the tool registry. "
            "It will require human approval on EVERY call until a human runs "
            f"'agentic tools custom approve {name}'. Ask a human to run 'agentic tools reload' "
            "(or restart the bot) to make it callable in a running session — note this resets "
            "in-flight conversation state, so it's best done between conversations rather than "
            "mid-task."
        )

    create_custom_tool_langchain_tool = StructuredTool.from_function(
        func=_create_custom_tool_impl,
        name="create_custom_tool",
        description=(
            "Author and register a brand-new tool (a sandboxed Python script or a Dockerized "
            "script) when no existing tool covers a need.\n\n"
            "IMPORTANT — call shape: pass name, description, kind, python_source_path (or "
            "dockerfile_path/entrypoint_path), tool_args, etc. as TOP-LEVEL keys of this tool's "
            "arguments object. Do NOT nest them inside a generic 'args'/'arguments' wrapper key — "
            "'tool_args' is only the (optional) schema for the arguments the NEW tool you are "
            "creating will accept when it is later called, not a container for this call's own "
            "parameters.\n\n"
            "REQUIRED WORKFLOW — do this before calling this tool:\n"
            "1. Use your filesystem WRITE tool to write the source (kind='python': one .py file "
            "defining `run(**kwargs)`; kind='docker': a Dockerfile + entrypoint script) into the "
            "workspace.\n"
            "2. Optionally use your filesystem READ tool to read the file(s) back and confirm the "
            "content is exactly what you intended.\n"
            "3. Call this tool with the workspace-relative path(s) to those file(s) — "
            "python_source_path, or dockerfile_path + entrypoint_path.\n\n"
            "This tool does NOT accept inline source code or long string content as arguments, and "
            "it verifies every required file exists in the workspace before doing anything else — "
            "if you skip step 1, it fails fast with a clear list of exactly which file(s) are "
            "missing. ALWAYS requires human approval to run, and the tool it creates will also "
            "require approval on every call until a human explicitly reviews and promotes it via "
            "'agentic tools custom approve <name>'. Prefer kind='python' for pure-logic helpers "
            "(no file/network/system access); use kind='docker' when the tool genuinely needs "
            "extra dependencies or stronger isolation."
        ),
        args_schema=CreateCustomToolInput,
    )
    tool_registry.register_tool("create_custom_tool", create_custom_tool_langchain_tool)

    class UpdateCustomToolInput(BaseModel):
        name: str = Field(description="Name of the existing custom tool to update (must already exist)")
        description: str | None = Field(
            default=None, description="New description; omit to leave unchanged."
        )
        tool_args: dict[str, str] | None = Field(
            default=None,
            description="New mapping of argument name -> type (string|integer|number|boolean|array|"
                        "object) for the tool's own arguments; omit to leave unchanged. This is NOT a "
                        "wrapper for this call's own parameters — pass name/description/etc. as "
                        "top-level fields, not nested inside this one.",
        )
        python_source_path: str | None = Field(
            default=None,
            description="Only for an existing kind='python' tool. Workspace-relative path to a file YOU "
                        "must write first (with your filesystem write tool) containing the FULL new "
                        "`run(**kwargs)` source (it replaces the previous source entirely). Omit to "
                        "leave the existing source unchanged. Do NOT pass source code content directly.",
        )
        dockerfile_path: str | None = Field(
            default=None,
            description="Only for an existing kind='docker' tool. Workspace-relative path to the FULL "
                        "new Dockerfile you already wrote; omit to leave unchanged. Do NOT pass "
                        "Dockerfile content directly.",
        )
        entrypoint_path: str | None = Field(
            default=None,
            description="Only for an existing kind='docker' tool. Workspace-relative path to the FULL "
                        "new entrypoint script you already wrote; omit to leave unchanged. Do NOT pass "
                        "script content directly.",
        )
        network_access: bool | None = Field(default=None, description="Docker kind only; omit to leave unchanged.")
        timeout_seconds: int | None = Field(default=None, description="Omit to leave unchanged.")

    def _update_custom_tool_impl(
        name: str,
        description: str | None = None,
        tool_args: dict[str, str] | None = None,
        python_source_path: str | None = None,
        dockerfile_path: str | None = None,
        entrypoint_path: str | None = None,
        network_access: bool | None = None,
        timeout_seconds: int | None = None,
    ) -> str:
        "Edit/update an existing agent-authored custom tool's metadata and/or source. Requires human re-approval; see docstring on the registered tool."
        try:
            _update_custom_tool_files(
                workspace=agentic_config.workspace,
                name=name,
                description=description,
                tool_args=tool_args,
                python_source_path=python_source_path,
                dockerfile_path=dockerfile_path,
                entrypoint_path=entrypoint_path,
                network_access=network_access,
                timeout_seconds=timeout_seconds,
            )
        except ValueError as e:
            return f"Error: could not update tool '{name}': {e}"

        tool_registry.reload_custom_tools(agentic_config)
        return (
            f"Custom tool '{name}' updated. Because it was edited, it now requires human "
            f"approval on EVERY call again, even if it was previously approved — a human must "
            f"review the change (agentic tools custom inspect {name}) and re-run "
            f"'agentic tools custom approve {name}'. Ask a human to run 'agentic tools reload' "
            "(or restart the bot) to make the update take effect in a running session — note "
            "this resets in-flight conversation state, so it's best done between conversations "
            "rather than mid-task."
        )

    update_custom_tool_langchain_tool = StructuredTool.from_function(
        func=_update_custom_tool_impl,
        name="update_custom_tool",
        description=(
            "Edit/update a custom tool you (or another agent) previously created with "
            "create_custom_tool — e.g. to fix a bug, change its description/argument schema, "
            "or adjust its timeout/network access. Only the fields you pass are changed; omit "
            "everything else to leave it as-is.\n\n"
            "IMPORTANT — call shape: pass name plus whichever fields you're changing as "
            "TOP-LEVEL keys of this tool's arguments object; do not nest them under a generic "
            "'args'/'arguments' wrapper key.\n\n"
            "REQUIRED WORKFLOW when changing source — do this before calling this tool:\n"
            "1. Use your filesystem WRITE tool to write the FULL new source (it replaces the "
            "previous source entirely, it is not a diff/patch) into the workspace.\n"
            "2. Optionally read the file back to confirm its content.\n"
            "3. Call this tool with the workspace-relative path to that file — "
            "python_source_path for kind='python', or dockerfile_path/entrypoint_path for "
            "kind='docker'.\n\n"
            "This tool does NOT accept inline source code or long string content as arguments. "
            "You cannot change a tool's 'kind' (python vs docker) or 'name' this way — remove "
            "and re-create it instead. ANY update — even metadata-only — resets the tool's "
            "approval gate, so it will require human approval on every call again until a "
            "human reviews and re-promotes it via 'agentic tools custom approve <name>'."
        ),
        args_schema=UpdateCustomToolInput,
    )
    tool_registry.register_tool("update_custom_tool", update_custom_tool_langchain_tool)

    register_workspace_sub_agents(tool_registry, agentic_config, tool_notifier_middleware, agent_registry)
    tool_registry.reload_custom_tools(agentic_config)
