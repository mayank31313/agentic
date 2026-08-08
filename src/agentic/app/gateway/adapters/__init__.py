from abc import ABC, abstractmethod

import httpx
from pydantic import BaseModel, Field
from typing import Optional
import time

class InboundMessage(BaseModel):
    message_id: str
    channel: str
    chat_id: str
    user_id: str
    text: str
    timestamp: float = time.time()
    raw: dict = Field(default=dict)
    metadata: dict = Field(default=dict)

class OutboundMessage(BaseModel):
    channel: str
    chat_id: str
    text: str
    reply_to_message_id: Optional[str] = None
    metadata: dict = Field(default=dict)


class ChannelAdapter(ABC):
    """Every channel (Telegram, Slack, WhatsApp, future ones) implements this."""

    name: str  # e.g. "telegram" — must be unique, used for routing

    @abstractmethod
    async def verify_webhook(self, request) -> bool:
        """Validate signature/secret. Return False to reject the request."""
        ...

    def parse_inbound(self, payload: dict) -> Optional[InboundMessage]:
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
    async def send(self, message: OutboundMessage) -> None:
        """Send a reply back out through this channel's API."""
        ...

class AdapterRegistry:
    _adapters: dict[str, ChannelAdapter] = {}

    @classmethod
    def register(cls, adapter: ChannelAdapter):
        cls._adapters[adapter.name] = adapter

    @classmethod
    def get(cls, name: str) -> ChannelAdapter:
        if name not in cls._adapters:
            raise ValueError(f"No adapter registered for channel '{name}'")
        return cls._adapters[name]

    @classmethod
    def all(cls) -> dict[str, ChannelAdapter]:
        return cls._adapters