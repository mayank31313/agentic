import logging

from cndi.annotations import Component
from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect

from agentic.app.bot import AgenticBot
from agentic.app.gateway.adapters import (
    AdapterRegistry,
    OutboundMessage,
    InboundMessage,
)
from agentic.app.gateway.adapters.websockets import WebSocketConnectionManager

logger = logging.getLogger(__name__)


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
        await adapter.send(message)


def get_adapter_gateway(
    gateway: Gateway, connection_manager: WebSocketConnectionManager
) -> FastAPI:
    app = FastAPI()

    @app.websocket("/ws/{chat_id}")
    async def websocket_endpoint(websocket: WebSocket, chat_id: str):
        await websocket.accept()
        await connection_manager.connect(chat_id, websocket)
        try:
            while True:
                data = await websocket.receive_text()
                inbound_message = InboundMessage(
                    message_id="websocket",
                    channel="websocket",
                    chat_id=chat_id,
                    user_id=chat_id,
                    text=data,
                )
                response = await gateway.route_to_backend(inbound_message)
                outbound_message = OutboundMessage(
                    chat_id=chat_id,
                    text="AGENT",
                    channel="websocket",
                    metadata=dict(response=response),
                )
                await gateway.deliver_to_channel(outbound_message)

        except WebSocketDisconnect:
            logger.error(f"WebSocket disconnected for chat_id: {chat_id}")

        await connection_manager.disconnect(chat_id)

    @app.get("/health")
    async def health_check():
        return {"status": "ok"}

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
