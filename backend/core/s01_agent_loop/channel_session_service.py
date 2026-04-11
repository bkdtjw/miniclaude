from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict

from backend.common import AgentError
from backend.common.types import AgentConfig, Message, Session, SessionConfig
from backend.config.settings import settings as app_settings
from backend.core.s02_tools import ToolRegistry
from backend.core.s02_tools.builtin import PermissionMode, register_builtin_tools
from backend.core.s02_tools.mcp import MCPToolBridge
from backend.core.system_prompt import build_system_prompt
from .agent_loop import AgentLoop


class ChannelSessionError(AgentError):
    pass


class ChannelRuntime(BaseModel):
    model: str
    permission_mode: PermissionMode = "readonly"
    provider_id: str | None = None
    workspace: str | None = None


class ChannelTurnRequest(BaseModel):
    channel_key: str
    message: str


class ChannelSessionDeps(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    mcp_server_manager: object | None = None
    provider_manager: object
    runtime: ChannelRuntime
    store: object


class ChannelLoopState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    bridge: MCPToolBridge | None = None
    loop: AgentLoop
    session_id: str


class ChannelSessionService:
    def __init__(self, deps: ChannelSessionDeps) -> None:
        self._deps = deps
        self._locks: dict[str, asyncio.Lock] = {}
        self._states: dict[str, ChannelLoopState] = {}

    async def run_turn(self, request: ChannelTurnRequest) -> Message:
        try:
            lock = self._locks.setdefault(request.channel_key, asyncio.Lock())
            async with lock:
                state = await self._get_or_create_state(request.channel_key)
                if state.bridge is not None and state.bridge.needs_sync():
                    await state.bridge.sync_if_needed()
                result = await state.loop.run(request.message)
                await self._deps.store.save_messages(state.session_id, state.loop.messages)
                return result
        except AgentError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ChannelSessionError("CHANNEL_RUN_ERROR", str(exc)) from exc

    async def _get_or_create_state(self, channel_key: str) -> ChannelLoopState:
        try:
            if channel_key in self._states:
                return self._states[channel_key]
            session_id = hashlib.md5(channel_key.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]
            provider_id = await self._resolve_provider_id()
            system_prompt = build_system_prompt(self._deps.runtime.workspace)
            adapter = await self._deps.provider_manager.get_adapter(provider_id)
            registry = ToolRegistry()
            register_builtin_tools(
                registry,
                self._deps.runtime.workspace,
                mode=self._deps.runtime.permission_mode,
                adapter=adapter,
                default_model=self._deps.runtime.model,
                feishu_webhook_url=app_settings.feishu_webhook_url or None,
                feishu_secret=app_settings.feishu_webhook_secret or None,
                youtube_api_key=app_settings.youtube_api_key or None,
                youtube_proxy_url=app_settings.youtube_proxy_url or None,
                twitter_username=app_settings.twitter_username or None,
                twitter_email=app_settings.twitter_email or None,
                twitter_password=app_settings.twitter_password or None,
                twitter_proxy_url=app_settings.twitter_proxy_url or None,
                twitter_cookies_file=app_settings.twitter_cookies_file or None,
            )
            bridge = await self._build_bridge(registry)
            loop = AgentLoop(
                config=AgentConfig(model=self._deps.runtime.model, system_prompt=system_prompt),
                adapter=adapter,
                tool_registry=registry,
            )
            record = await self._deps.store.get(session_id)
            if record is None:
                await self._deps.store.create(
                    Session(
                        id=session_id,
                        config=SessionConfig(
                            model=self._deps.runtime.model,
                            provider=provider_id,
                            system_prompt=system_prompt,
                        ),
                        created_at=datetime.now(UTC),
                    ),
                    title=channel_key,
                    workspace=self._deps.runtime.workspace or "",
                )
            else:
                loop._messages = self._restore_messages(record.messages, system_prompt)  # noqa: SLF001
            state = ChannelLoopState(bridge=bridge, loop=loop, session_id=session_id)
            self._states[channel_key] = state
            return state
        except AgentError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ChannelSessionError("CHANNEL_STATE_ERROR", str(exc)) from exc

    async def _build_bridge(self, registry: ToolRegistry) -> MCPToolBridge | None:
        try:
            if self._deps.mcp_server_manager is None:
                return None
            bridge = MCPToolBridge(self._deps.mcp_server_manager, registry)
            await bridge.sync_all()
            return bridge
        except AgentError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ChannelSessionError("CHANNEL_BRIDGE_ERROR", str(exc)) from exc

    async def _resolve_provider_id(self) -> str:
        try:
            if self._deps.runtime.provider_id:
                return self._deps.runtime.provider_id
            default_provider = await self._deps.provider_manager.get_default()
            if default_provider is None:
                raise ChannelSessionError("CHANNEL_PROVIDER_MISSING", "Default provider is not configured")
            return default_provider.id
        except AgentError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ChannelSessionError("CHANNEL_PROVIDER_ERROR", str(exc)) from exc

    def _restore_messages(self, messages: list[Message], system_prompt: str) -> list[Message]:
        restored = [Message(role="system", content=system_prompt)]
        for message in messages:
            if message.role != "system":
                restored.append(message.model_copy(deep=True))
        return restored


__all__ = [
    "ChannelRuntime",
    "ChannelSessionDeps",
    "ChannelSessionError",
    "ChannelSessionService",
    "ChannelTurnRequest",
]
