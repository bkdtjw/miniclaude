from __future__ import annotations

import json
import re
from collections import deque

from pydantic import BaseModel, ConfigDict

from backend.common import AgentError
from backend.common.types import Message
from backend.core.s01_agent_loop import ChannelTurnRequest
from backend.schemas.feishu import FeishuEventEnvelope, FeishuMessageEvent, FeishuReplyRequest

AT_TAG_PATTERN = re.compile(r"<at[^>]*>.*?</at>")
UNSUPPORTED_MESSAGE = "Only text messages are supported right now."


class FeishuMessageHandlerError(AgentError):
    pass


class FeishuMessageHandlerDeps(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    feishu_client: object
    session_service: object


class FeishuMessageHandler:
    def __init__(self, deps: FeishuMessageHandlerDeps) -> None:
        self._deps = deps
        self._event_ids: set[str] = set()
        self._event_order: deque[str] = deque()
        self._max_event_ids = 1024

    async def handle_event(self, envelope: FeishuEventEnvelope) -> None:
        try:
            if envelope.challenge or envelope.header.event_type != "im.message.receive_v1":
                return
            event_id = envelope.header.event_id.strip()
            if event_id and self._seen(event_id):
                return
            event = FeishuMessageEvent.model_validate(envelope.event or {})
            if event.sender.sender_type and event.sender.sender_type != "user":
                return
            message = event.message
            if message.message_type != "text":
                await self._reply_text(message.message_id, UNSUPPORTED_MESSAGE)
                return
            text = self._extract_text(message.content)
            if not text:
                return
            result = await self._deps.session_service.run_turn(
                ChannelTurnRequest(
                    channel_key=self._build_channel_key(envelope, event),
                    message=text,
                )
            )
            await self._reply_text(message.message_id, result.content)
        except AgentError:
            return
        except Exception:
            return

    def _seen(self, event_id: str) -> bool:
        if event_id in self._event_ids:
            return True
        self._event_ids.add(event_id)
        self._event_order.append(event_id)
        if len(self._event_order) > self._max_event_ids:
            expired = self._event_order.popleft()
            self._event_ids.discard(expired)
        return False

    def _build_channel_key(
        self,
        envelope: FeishuEventEnvelope,
        event: FeishuMessageEvent,
    ) -> str:
        tenant_key = envelope.header.tenant_key or event.sender.tenant_key or "default"
        return f"feishu:{tenant_key}:{event.message.chat_id}"

    def _extract_text(self, content: str) -> str:
        try:
            payload = json.loads(content or "{}")
            text = str(payload.get("text", "")).strip()
            normalized = AT_TAG_PATTERN.sub(" ", text)
            return " ".join(normalized.split())
        except Exception as exc:  # noqa: BLE001
            raise FeishuMessageHandlerError("FEISHU_TEXT_PARSE_ERROR", str(exc)) from exc

    async def _reply_text(self, message_id: str, content: str) -> Message | None:
        try:
            if not message_id:
                return None
            await self._deps.feishu_client.reply_message(
                FeishuReplyRequest(message_id=message_id, content=content)
            )
            return Message(role="assistant", content=content)
        except AgentError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise FeishuMessageHandlerError("FEISHU_REPLY_ERROR", str(exc)) from exc


__all__ = [
    "FeishuMessageHandler",
    "FeishuMessageHandlerDeps",
    "FeishuMessageHandlerError",
    "UNSUPPORTED_MESSAGE",
]
