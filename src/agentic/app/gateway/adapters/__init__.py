import time
from abc import ABC, abstractmethod
from typing import Union

from pydantic import BaseModel, Field

from agentic.app.gateway.adapters.telegram.config import TelegramMessageMetadata


class InboundMessage(BaseModel):
    message_id: str
    channel: str
    chat_id: str
    user_id: str
    text: str
    timestamp: float = time.time()
    raw: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)

class OutboundMessageReply(BaseModel):
    message_id: str
    channel: str
    chat_id: str
    metadata: dict = Field(default_factory=dict)


class OutboundMessage(BaseModel):
    channel: str
    chat_id: str
    text: str
    reply_to_message_id: str | None = None
    metadata: Union[TelegramMessageMetadata, dict] = Field(default_factory=dict, union_mode='left_to_right')

    def to_reply(self, message_id: str, metadata: dict={}) -> OutboundMessageReply:
        return OutboundMessageReply(
            message_id=message_id,
            channel=self.channel,
            chat_id=self.chat_id,
            metadata=metadata,
        )

class ChannelAdapter(ABC):
    """Every channel (Telegram, Slack, WhatsApp, future ones) implements this."""

    name: str  # e.g. "telegram" — must be unique, used for routing

    @abstractmethod
    async def verify_webhook(self, request) -> bool:
        """Validate signature/secret. Return False to reject the request."""
        ...

    def parse_inbound(self, payload: dict) -> InboundMessage | None:
        """Convert the channel's raw payload into a normalized InboundMessage.
        Return None for events that aren't actual user messages (e.g. delivery receipts)."""

        msg = payload.get("message", {})
        if "text" not in msg:
            return None
        return InboundMessage(
            message_id=str(msg["message_id"]),
            channel=self.name,
            chat_id=str(msg["chat"]["id"]),
            user_id=str(msg["from"]["id"]),
            text=msg["text"],
            raw=payload,
        )

    @abstractmethod
    async def invoke_webhook(self, message: OutboundMessage) -> OutboundMessageReply:
        """Process the incoming webhook request and return an InboundMessage."""
        ...

    @abstractmethod
    async def send(self, message: OutboundMessage) -> OutboundMessageReply:
        """Send a reply back out through this channel's API."""
        ...

class AdapterRegistry:
    _adapters: dict[str, ChannelAdapter] = {}

    @staticmethod
    def register(adapter: ChannelAdapter):
        AdapterRegistry._adapters[adapter.name] = adapter

    @staticmethod
    def get(name: str) -> ChannelAdapter:
        if name not in AdapterRegistry._adapters:
            raise ValueError(f"No adapter registered for channel '{name}'")
        return AdapterRegistry._adapters[name]

    @staticmethod
    def all() -> dict[str, ChannelAdapter]:
        return AdapterRegistry._adapters
