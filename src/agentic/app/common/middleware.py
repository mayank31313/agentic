import logging

from cndi.annotations import Component
from langchain.agents.middleware import AgentMiddleware
from langgraph.prebuilt.tool_node import ToolCallRequest

from agentic.app.gateway.adapters import OutboundMessageReply, OutboundMessage, AdapterRegistry

logger = logging.getLogger(__name__)

@Component
class ToolNotifierMiddleware(AgentMiddleware):
    """Sends a Telegram message before and after every tool call."""

    def __init__(self,):
        super().__init__()

    async def send_message(self, text: str, channel, chat_id) -> OutboundMessageReply:
        outbound_message = OutboundMessage(
            channel=channel,
            text=text,
            chat_id=chat_id,
            metadata={
                "type": "text"
            }
        )

        channel_adapter = AdapterRegistry.get(outbound_message.channel)
        return await channel_adapter.invoke_webhook(outbound_message)

    async def delete_sent_message(self, message: OutboundMessageReply, message_id: str):
        try:
            outbound_message = OutboundMessage(
                channel=message.channel,
                text="",
                chat_id=message.chat_id,
                metadata={
                    "type": "action",
                    "document_action": "delete",
                    "message_id": message_id
                }
            )

            channel_adapter = AdapterRegistry.get(outbound_message.channel)
            return await channel_adapter.invoke_webhook(outbound_message)
        except Exception as e:
            logger.error(f"[telegram delete] failed to send: {e}")

    async def awrap_tool_call(self, request: ToolCallRequest, handler):
        thread_id = request.runtime.config.get("configurable", {}).get("thread_id")

        if not thread_id:
            logger.warning(f"Channel name or chat id is missing in the request: {request}")
            return await handler(request)
        channel_name, separator, chat_id = thread_id.partition("::")
        if not separator or not channel_name or not chat_id:
            logger.warning(f"Malformed thread_id '{thread_id}' in request: {request}")
            return await handler(request)
        tool_name = request.tool_call["name"]
        tool_args = request.tool_call["args"]
        logger.info(f"🔧 Calling tool: {tool_name} Args: {tool_args}")
        message = await self.send_message(
            f"🔧 Calling tool: {tool_name}\nArgs: {tool_args}", channel_name, chat_id
        )
        response = await handler(request)  # actually runs the tool
        logger.info(f"🔧 Tool Response: {response}")
        await self.delete_sent_message(message, message_id=message.message_id)

        return response
