from __future__ import annotations

from collections.abc import Generator
from typing import Any

from fastapi.testclient import TestClient
import pytest

from backend.adapters.feishu_client import FeishuClient, FeishuClientConfig
from backend.api.app import create_app
from backend.api.routes import mcp as mcp_routes
from backend.api.routes.feishu_handler import (
    FeishuMessageHandler,
    FeishuMessageHandlerDeps,
    UNSUPPORTED_MESSAGE,
)
from backend.common.types import MCPServerStatus, Message
from backend.config.settings import settings
from backend.schemas.feishu import FeishuEventEnvelope, FeishuReplyRequest

class FakeMCPManager:
    async def disconnect_all(self) -> None:
        return None

    async def list_servers(self) -> list[MCPServerStatus]:
        return []


class FakeRouteHandler:
    def __init__(self) -> None:
        self.events: list[FeishuEventEnvelope] = []

    async def handle_event(self, envelope: FeishuEventEnvelope) -> None:
        self.events.append(envelope)


class FakeSessionService:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def run_turn(self, request: Any) -> Message:
        self.messages.append(request.message)
        return Message(role="assistant", content=f"reply:{request.message}")


class FakeFeishuClient:
    def __init__(self) -> None:
        self.replies: list[FeishuReplyRequest] = []

    async def reply_message(self, request: FeishuReplyRequest) -> dict[str, Any]:
        self.replies.append(request)
        return {"message_id": request.message_id}


class FakeResponse:
    def __init__(self, status_code: int, data: dict[str, Any]) -> None:
        self.status_code = status_code
        self._data = data

    def json(self) -> dict[str, Any]:
        return self._data


class FakeAsyncClient:
    calls: list[dict[str, Any]] = []

    def __init__(self, timeout: float, trust_env: bool) -> None:
        self.timeout = timeout
        self.trust_env = trust_env

    async def __aenter__(self) -> FakeAsyncClient:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    async def post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> FakeResponse:
        self.calls.append({"url": url, "json": json, "headers": headers})
        return FakeResponse(
            200,
            {"code": 0, "data": {"tenant_access_token": "tenant-token", "expire": 7200}},
        )


@pytest.fixture
def feishu_client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    settings.feishu_app_id = "cli_a"
    settings.feishu_app_secret = "secret_a"
    settings.feishu_verification_token = "verify-token"

    async def _noop_init_db() -> None:
        return None

    monkeypatch.setattr("backend.api.app.init_db", _noop_init_db)
    monkeypatch.setattr(mcp_routes, "mcp_server_manager", FakeMCPManager())
    with TestClient(create_app()) as client:
        yield client


def _message_event(event_id: str, sender_type: str = "user", message_type: str = "text") -> dict[str, Any]:
    return {
        "token": "verify-token",
        "schema": "2.0",
        "header": {
            "event_id": event_id,
            "event_type": "im.message.receive_v1",
            "tenant_key": "tenant-a",
        },
        "event": {
            "sender": {"sender_type": sender_type, "tenant_key": "tenant-a"},
            "message": {
                "chat_id": "oc_123",
                "message_id": "om_123",
                "message_type": message_type,
                "content": '{"text":"<at user_id=\\"ou_1\\"></at> hello world"}',
            },
        },
    }


def test_feishu_route_not_mounted_without_app_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _noop_init_db() -> None:
        return None

    monkeypatch.setattr("backend.api.app.init_db", _noop_init_db)
    monkeypatch.setattr(mcp_routes, "mcp_server_manager", FakeMCPManager())
    with TestClient(create_app()) as client:
        response = client.post("/api/feishu/event", json={"challenge": "x"})
    assert response.status_code == 404


def test_feishu_challenge(feishu_client: TestClient) -> None:
    response = feishu_client.post(
        "/api/feishu/event",
        json={"challenge": "challenge-123", "type": "url_verification", "token": "verify-token"},
    )
    assert response.status_code == 200
    assert response.json() == {"challenge": "challenge-123"}


def test_feishu_route_dispatches_background_handler(feishu_client: TestClient) -> None:
    handler = FakeRouteHandler()
    feishu_client.app.state.feishu_handler = handler
    response = feishu_client.post("/api/feishu/event", json=_message_event("evt-route"))
    assert response.status_code == 200
    assert response.json() == {"code": 0, "message": "ok"}
    assert len(handler.events) == 1
    assert handler.events[0].header.event_id == "evt-route"


@pytest.mark.asyncio
async def test_feishu_handler_deduplicates_events() -> None:
    session_service = FakeSessionService()
    feishu_client = FakeFeishuClient()
    handler = FeishuMessageHandler(
        FeishuMessageHandlerDeps(
            feishu_client=feishu_client,
            session_service=session_service,
        )
    )
    envelope = FeishuEventEnvelope.model_validate(_message_event("evt-dedupe"))
    await handler.handle_event(envelope)
    await handler.handle_event(envelope)
    assert session_service.messages == ["hello world"]
    assert [item.content for item in feishu_client.replies] == ["reply:hello world"]


@pytest.mark.asyncio
async def test_feishu_handler_ignores_bot_messages() -> None:
    handler = FeishuMessageHandler(
        FeishuMessageHandlerDeps(
            feishu_client=FakeFeishuClient(),
            session_service=FakeSessionService(),
        )
    )
    await handler.handle_event(FeishuEventEnvelope.model_validate(_message_event("evt-bot", sender_type="bot")))
    assert handler._event_ids == {"evt-bot"}  # noqa: SLF001


@pytest.mark.asyncio
async def test_feishu_handler_replies_for_non_text_messages() -> None:
    feishu_client = FakeFeishuClient()
    handler = FeishuMessageHandler(
        FeishuMessageHandlerDeps(
            feishu_client=feishu_client,
            session_service=FakeSessionService(),
        )
    )
    await handler.handle_event(FeishuEventEnvelope.model_validate(_message_event("evt-image", message_type="image")))
    assert [item.content for item in feishu_client.replies] == [UNSUPPORTED_MESSAGE]


@pytest.mark.asyncio
async def test_feishu_client_caches_tenant_token(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeAsyncClient.calls = []
    monkeypatch.setattr("backend.adapters.feishu_client.httpx.AsyncClient", FakeAsyncClient)
    client = FeishuClient(FeishuClientConfig(app_id="cli_a", app_secret="secret_a"))
    assert await client.get_tenant_token() == "tenant-token"
    assert await client.get_tenant_token() == "tenant-token"
    assert len(FakeAsyncClient.calls) == 1
