from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from backend.adapters.base import LLMAdapter
from backend.common.types import LLMResponse, Message, ProviderConfig, ProviderType, StreamChunk
from backend.core.s01_agent_loop import ChannelRuntime, ChannelSessionDeps, ChannelSessionService, ChannelTurnRequest


class FakeAdapter(LLMAdapter):
    def __init__(self) -> None:
        self.requests: list[list[str]] = []

    async def test_connection(self) -> bool:
        return True

    async def complete(self, request: Any) -> LLMResponse:
        self.requests.append([message.content for message in request.messages])
        return LLMResponse(content=f"echo:{request.messages[-1].content}")

    def stream(self, request: Any) -> AsyncIterator[StreamChunk]:
        if False:
            yield StreamChunk(type="done")


class FakeProviderManager:
    def __init__(self, adapter: FakeAdapter) -> None:
        self._adapter = adapter

    async def get_default(self) -> ProviderConfig:
        return ProviderConfig(
            id="provider_a",
            name="Default",
            provider_type=ProviderType.ANTHROPIC,
            base_url="https://example.com",
            default_model="demo-model",
        )

    async def get_adapter(self, provider_id: str | None = None) -> FakeAdapter:
        return self._adapter


class FakeSessionStore:
    def __init__(self) -> None:
        self.sessions: dict[str, Any] = {}
        self.created_ids: list[str] = []

    async def create(self, session: Any, title: str = "", workspace: str = "") -> Any:
        self.sessions[session.id] = session
        self.created_ids.append(session.id)
        return session

    async def get(self, session_id: str) -> Any:
        return self.sessions.get(session_id)

    async def save_messages(self, session_id: str, messages: list[Message]) -> None:
        current = self.sessions[session_id]
        self.sessions[session_id] = current.model_copy(
            update={"messages": [item.model_copy(deep=True) for item in messages]}
        )


@pytest.mark.asyncio
async def test_channel_session_service_reuses_chat_context_and_isolates_channels() -> None:
    adapter = FakeAdapter()
    service = ChannelSessionService(
        ChannelSessionDeps(
            provider_manager=FakeProviderManager(adapter),
            runtime=ChannelRuntime(model="demo-model"),
            store=FakeSessionStore(),
        )
    )
    first = await service.run_turn(ChannelTurnRequest(channel_key="feishu:tenant:chat-a", message="first"))
    second = await service.run_turn(ChannelTurnRequest(channel_key="feishu:tenant:chat-a", message="second"))
    third = await service.run_turn(ChannelTurnRequest(channel_key="feishu:tenant:chat-b", message="other"))
    assert first.content == "echo:first"
    assert second.content == "echo:second"
    assert third.content == "echo:other"
    assert adapter.requests[1][-2:] == ["echo:first", "second"]
    assert adapter.requests[2][-1] == "other"
