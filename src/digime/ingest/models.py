from datetime import datetime

from pydantic import BaseModel


class RawMessage(BaseModel):
    platform: str
    conversation_id: str
    sender_id: str
    text: str
    sent_at: datetime


class ReplyExample(BaseModel):
    platform: str
    conversation_id: str
    incoming_context: list[str]
    your_reply: str
    sent_at: datetime

