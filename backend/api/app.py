"""FastAPI application factory."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.common.errors import AgentError
from backend.storage import SessionStore, init_db


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    from backend.api.routes.mcp import mcp_server_manager
    from backend.api.routes.providers import provider_manager
    from backend.config.settings import settings as app_settings
    from backend.core.s07_task_system import TaskRuntimeDeps, create_task_tooling

    try:
        await init_db()
        app.state.session_store = SessionStore()
        app.state.task_tooling = create_task_tooling(
            TaskRuntimeDeps(
                provider_manager=provider_manager,
                mcp_manager=mcp_server_manager,
                settings=app_settings,
            )
        )
        await app.state.task_tooling.scheduler.start()
        yield
    except Exception as exc:  # noqa: BLE001
        raise AgentError("APP_LIFESPAN_ERROR", str(exc)) from exc
    finally:
        try:
            task_tooling = getattr(app.state, "task_tooling", None)
            if task_tooling is not None:
                await task_tooling.scheduler.stop()
            await mcp_server_manager.disconnect_all()
        except Exception as exc:  # noqa: BLE001
            raise AgentError("APP_SHUTDOWN_ERROR", str(exc)) from exc


def create_app() -> FastAPI:
    from backend.api.routes import chat_completions, mcp, providers, sessions, websocket
    from backend.config.settings import settings as app_settings

    app = FastAPI(title="Agent Studio", version="0.1.0", lifespan=_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(chat_completions.router)
    app.include_router(websocket.router)
    app.include_router(sessions.router)
    app.include_router(providers.router)
    app.include_router(mcp.router)
    if app_settings.feishu_app_id and app_settings.feishu_app_secret:
        from backend.api.routes import feishu

        app.include_router(feishu.router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        try:
            return {"status": "ok"}
        except Exception as exc:  # noqa: BLE001
            raise AgentError("HEALTHCHECK_ERROR", str(exc)) from exc

    return app
