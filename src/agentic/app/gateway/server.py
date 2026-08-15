import logging

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect

from agentic.app.gateway.adapters import (
    InboundMessage,
    OutboundMessage,
)
from agentic.app.gateway.adapters.websockets import WebSocketConnectionManager
from agentic.app.gateway.config import Gateway

logger = logging.getLogger(__name__)

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

    @app.post("/webhook/forward")
    async def generic_webhook(request: Request):
        payload = await request.json()
        outbound_message  = OutboundMessage.model_validate(payload)
        return await gateway.deliver_to_channel(outbound_message)

    return app
