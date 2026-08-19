from cndi.annotations import Component
from fastapi import WebSocket

from agentic.app.gateway.adapters import (
    AdapterRegistry,
    ChannelAdapter,
    OutboundMessage, OutboundMessageReply,
)


@Component
class WebSocketConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, chat_id: str, websocket: WebSocket):
        self.active_connections[chat_id] = websocket

    def disconnect(self, chat_id: str):
        if chat_id in self.active_connections:
            del self.active_connections[chat_id]

    async def send_personal_message(self, chat_id: str, message: OutboundMessage) -> OutboundMessageReply | None:
        if chat_id in self.active_connections:
            await self.active_connections[chat_id].send_json(
                message.model_dump(mode="json")
            )
            return message.to_reply(message_id="test_message", metadata={})
        return None
    async def broadcast(self, message: OutboundMessage):
        for chat_id, connection in self.active_connections.items():
            await self.send_personal_message(chat_id, message)


@Component
class WebSocketsAdapter(ChannelAdapter):
    name = "websocket"

    def __init__(self, websocket_connection_manager: WebSocketConnectionManager):
        self.connection_manager = websocket_connection_manager
        AdapterRegistry.register(self)

    async def verify_webhook(self, request) -> bool:
        """Validate signature/secret. Return False to reject the request."""
        return True

    async def invoke_webhook(self, message: OutboundMessage) -> OutboundMessageReply:
        """Process the incoming webhook request and return an InboundMessage."""
        metadata = message.metadata if isinstance(message.metadata, dict) else message.metadata.model_dump()
        if metadata.get("type") == "action" and metadata.get("document_action") == "delete":
            return message.to_reply(message_id="test_message", metadata={"deleted": False})
        return await self.send(message)
    async def send(self, message: OutboundMessage) -> OutboundMessageReply:
        return await self.connection_manager.send_personal_message(message.chat_id, message)
