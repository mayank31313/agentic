import asyncio

from cndi.annotations import Component
from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect

from agentic.app.bot import AgenticBot
from agentic.app.gateway.adapters import AdapterRegistry, OutboundMessage, InboundMessage


@Component
class Gateway:
    def __init__(self, agentic_bot: AgenticBot):
        self.agentic_bot = agentic_bot
        self.chat_id_map = dict()

    async def route_to_backend(self, message: InboundMessage):
        self.chat_id_map[message.chat_id] = message.channel
        chat_id = message.chat_id
        message_id = message.message_id
        return await self.agentic_bot.invoke_agent(message.text,
                                                   chat_id=chat_id,
                                                   message_id=message_id, channel_metadata={})

    async def deliver_to_channel(self, message: OutboundMessage):
        channel = self.chat_id_map[message.chat_id]
        adapter = AdapterRegistry.get(channel)
        await adapter.send(message)

def get_adapter_gateway(gateway: Gateway) -> FastAPI:
    app = FastAPI()

    @app.post("/webhook/{chat_id}/send")
    async def send_message(chat_id: str, message: OutboundMessage):
        message.chat_id = chat_id
        await gateway.deliver_to_channel(message)
        return {"ok": True}

    @app.post("/webhook/{channel_name}")
    async def generic_webhook(channel_name: str, request: Request):
        adapter = AdapterRegistry.get(channel_name)

        if not await adapter.verify_webhook(request):
            raise HTTPException(status_code=403, detail="Invalid signature")

        payload = await request.json()
        inbound = adapter.parse_inbound(payload)
        if inbound is None:
            return {"ok": True}  # not a message we care about (e.g. read receipt)

        await gateway.route_to_backend(inbound)
        return {"ok": True}

    return app