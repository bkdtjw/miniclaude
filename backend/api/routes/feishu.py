from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from backend.adapters.feishu_client import FeishuClient, FeishuClientConfig
from backend.api.routes.feishu_handler import FeishuMessageHandler, FeishuMessageHandlerDeps
from backend.api.routes.feishu_security import (
    FeishuSecurityConfig,
    FeishuSecurityError,
    build_request_context,
    parse_callback_payload,
)
from backend.api.routes.mcp import mcp_server_manager
from backend.api.routes.providers import provider_manager
from backend.common import AgentError
from backend.config.settings import settings as app_settings
from backend.core.s01_agent_loop import ChannelRuntime, ChannelSessionDeps, ChannelSessionService
from backend.schemas.feishu import FeishuEventEnvelope
from backend.storage import SessionStore

router = APIRouter(prefix="/api/feishu", tags=["feishu"])


def _to_http_error(exc: AgentError) -> HTTPException:
    status_code = 401 if isinstance(exc, FeishuSecurityError) else 500
    return HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "message": exc.message},
    )


def _get_handler(request: Request) -> FeishuMessageHandler:
    existing = getattr(request.app.state, "feishu_handler", None)
    if existing is not None:
        return existing
    store = getattr(request.app.state, "session_store", None)
    if not isinstance(store, SessionStore):
        raise HTTPException(
            status_code=500,
            detail={"code": "FEISHU_STORE_MISSING", "message": "Session store is not ready"},
        )
    handler = FeishuMessageHandler(
        FeishuMessageHandlerDeps(
            feishu_client=FeishuClient(
                FeishuClientConfig(
                    app_id=app_settings.feishu_app_id,
                    app_secret=app_settings.feishu_app_secret,
                )
            ),
            session_service=ChannelSessionService(
                ChannelSessionDeps(
                    mcp_server_manager=mcp_server_manager,
                    provider_manager=provider_manager,
                    runtime=ChannelRuntime(
                        model=app_settings.default_model,
                        workspace=str(Path.cwd()),
                    ),
                    store=store,
                )
            ),
        )
    )
    request.app.state.feishu_handler = handler
    return handler


@router.post("/event")
async def feishu_event(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    try:
        context = build_request_context(await request.body(), request.headers)
        payload = parse_callback_payload(
            context,
            FeishuSecurityConfig(
                encrypt_key=app_settings.feishu_encrypt_key,
                verification_token=app_settings.feishu_verification_token,
            ),
        )
        envelope = FeishuEventEnvelope.model_validate(payload)
        if envelope.challenge:
            return {"challenge": envelope.challenge}
        background_tasks.add_task(_get_handler(request).handle_event, envelope)
        return {"code": 0, "message": "ok"}
    except AgentError as exc:
        raise _to_http_error(exc) from exc


__all__ = ["router"]
