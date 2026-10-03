from pydantic import BaseModel

from agentic.app.common import MessageAction, MessageType


class TelegramMessageMetadata(BaseModel):
    message_id: str
    action: MessageAction
    type: MessageType

