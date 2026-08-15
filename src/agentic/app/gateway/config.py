from cndi.annotations import Component

from agentic.app.bot import AgenticBot
from agentic.app.gateway.adapters import InboundMessage, OutboundMessage, AdapterRegistry


@Component
class Gateway:
    def __init__(self, agentic_bot: AgenticBot):
        self.agentic_bot = agentic_bot
        self.chat_id_map = dict()

    async def route_to_backend(self, message: InboundMessage):
        self.chat_id_map[message.chat_id] = message.channel
        chat_id = message.chat_id
        message_id = message.message_id
        return await self.agentic_bot.invoke_agent(
            message.text, chat_id=chat_id, message_id=message_id, channel_metadata={}
        )

    async def deliver_to_channel(self, message: OutboundMessage):
        channel = self.chat_id_map[message.chat_id]
        adapter = AdapterRegistry.get(channel)
        return await adapter.send(message)
