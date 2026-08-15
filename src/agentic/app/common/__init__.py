from enum import Enum

from langgraph.types import Interrupt
from pydantic import BaseModel, Field

INTERRUPT_EVENT = "interrupt_event"


class InterruptEvent(BaseModel):
    interrupt: Interrupt
    text: str
    chat_id: str
    message_id: str
    metadata: dict
    type: str = Field(default=INTERRUPT_EVENT)

class MessageAction(str, Enum):
    REPLY = "reply"
    EDIT = "edit"
    DELETE = "delete"
    SEND = "send"

class MessageType(str, Enum):
    TEXT = "text"
    ACTION = "action"
    PHOTO = "photo"