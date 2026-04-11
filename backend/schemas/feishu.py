from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class FeishuTokenState(BaseModel):
    token: str = ""
    expires_at: float = 0.0


class FeishuSendRequest(BaseModel):
    receive_id: str
    content: str
    msg_type: Literal["text", "post"] = "text"


class FeishuReplyRequest(BaseModel):
    message_id: str
    content: str
    msg_type: Literal["text", "post"] = "text"


class FeishuMessage(BaseModel):
    chat_id: str = ""
    content: str = ""
    message_id: str = ""
    message_type: str = ""


class FeishuSenderId(BaseModel):
    open_id: str = ""
    union_id: str = ""
    user_id: str = ""


class FeishuSender(BaseModel):
    sender_id: FeishuSenderId = Field(default_factory=FeishuSenderId)
    sender_type: str = ""
    tenant_key: str = ""


class FeishuEventHeader(BaseModel):
    create_time: str = ""
    event_id: str = ""
    event_type: str = ""
    tenant_key: str = ""


class FeishuMessageEvent(BaseModel):
    mentions: list[dict[str, Any]] = Field(default_factory=list)
    message: FeishuMessage = Field(default_factory=FeishuMessage)
    sender: FeishuSender = Field(default_factory=FeishuSender)


class FeishuEventEnvelope(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    challenge: str = ""
    header: FeishuEventHeader = Field(default_factory=FeishuEventHeader)
    event: dict[str, Any] | None = None
    schema_version: str = Field(default="", alias="schema")
    token: str = ""


__all__ = [
    "FeishuEventEnvelope",
    "FeishuEventHeader",
    "FeishuMessage",
    "FeishuMessageEvent",
    "FeishuReplyRequest",
    "FeishuSendRequest",
    "FeishuSender",
    "FeishuSenderId",
    "FeishuTokenState",
]
