import json
import logging

from cndi.annotations import Component
from cndi.annotations.events import EventBus
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command, Interrupt

from agentic import AgenticConfig
from agentic.app.agents import AgentRegistry, get_main_agent
from agentic.app.common import InterruptEvent
from agentic.app.common.middleware import ToolNotifierMiddleware
from agentic.app.common.tools import ToolsRegistry
from agentic.app.config import AgentConfig
from agentic.app.observability import get_langfuse_handler

logger = logging.getLogger(__name__)


@Component
class AgenticBot:
    def __init__(
        self,
        agenticConfig: AgenticConfig,
        tool_notifier_middleware: ToolNotifierMiddleware,
        event_bus: EventBus,
        tool_registry: ToolsRegistry,
        agent_registry: AgentRegistry,
    ):
        self.middelwares = [tool_notifier_middleware]
        self.max_approvals = 5
        self.agenticConfig = agenticConfig
        self.agentConfig: AgentConfig = agenticConfig.get_agent('main')
        self.tool_registry = tool_registry
        self.agent_registry = agent_registry
        self.event_bus = event_bus
        self.agent = None
        self.content_ids = set()
        self.langfuse_handler = get_langfuse_handler()
        if self.agentConfig.agent_model_config is None:
            self.agentConfig.agent_model_config = next(
                filter(
                    lambda x: x.model_id == self.agentConfig.model_id,
                    agenticConfig.models,
                )
            )

    def initialise_agent(self):
        runnable_tools, approvable_tools = [], []
        for tool_config in self.agentConfig.tools:
            if tool_config.require_approval:
                approvable_tools.append(tool_config)

        tools = list(
            filter(
                lambda x: x.name not in self.agentConfig.denied_tools,
                self.tool_registry.tools.values(),
            )
        )

        if len(tools) > 0:
            logger.info(f"Available tools in context {list(map(lambda x: x.name, tools))}")

        self.agent = get_main_agent(
            agent_config=self.agentConfig,
            tools=tools,
            tools_need_approval=approvable_tools,
            middlewares=self.middelwares,
        )

        self.agent_registry.register_agent(self.agentConfig.name, self.agent)

    async def invoke_agent(self, message, chat_id, message_id, channel_metadata: dict={}):
        channel_name = channel_metadata.get("channel_name", "websocket")

        config = {"configurable": {"thread_id": f"{channel_name}::{chat_id}"}, "callbacks": [self.langfuse_handler]}
        if message.startswith("$decision"):
            _, decision = message.split(" ")
            output = await self.agent.ainvoke(
                Command(resume={"decisions": [dict(type=decision)]}), config=config
            )
        else:
            output = await self.agent.ainvoke(dict(messages=message), config=config)

        if "__interrupt__" in output:
            interrupt_data: list[Interrupt] = output["__interrupt__"]
            review_configs = interrupt_data[0].value["review_configs"]
            action_requests = interrupt_data[0].value["action_requests"]

            keyboard_buttons = [
                [f"$decision {decision}"]
                for decision in review_configs[0]["allowed_decisions"]
            ]
            logger.info(interrupt_data)

            return [
                InterruptEvent(
                    text=f"""Tool Called Request Interrupt
Tool Name: {action_requests[0]["name"]}
Args: {action_requests[0]["args"]}""",
                    interrupt=interrupt_data[0],
                    chat_id=chat_id,
                    message_id=message_id,
                    metadata=dict(
                        action_requests=action_requests,
                        review_configs=review_configs,
                        keyboard_buttons=keyboard_buttons,
                    ),
                ).model_dump(mode="json")
            ]

        # Extract and send response
        response_text = list()
        for message in output["messages"]:
            logger.info(f"[Chat {chat_id}] Agent response: {message}")
            if message.id in self.content_ids:
                logger.debug(
                    f"[Chat {chat_id}] Skipping duplicate message ID: {message.id}"
                )
                continue
            self.content_ids.add(message.id)
            if (
                type(message) == ToolMessage
                and type(message.content) == str
                and message.content.startswith("json:")
            ):
                contents = json.loads(message.content[5:])
                for content in contents:
                    response_text.append(content)
            if type(message) == AIMessage and message.content != "":
                content = dict(text=message.content, type="text")
                response_text.append(content)
            if type(message) in [list, tuple]:
                for content in message.content:
                    if type(content) == dict:
                        response_text.append(content)

        return response_text
