from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
import tempfile
from types import SimpleNamespace
from uuid import uuid4

from backend.adapters.base import LLMAdapter
from backend.adapters.provider_manager import ProviderManager
from backend.common.types import LLMRequest, LLMResponse, ProviderConfig, ProviderType, StreamChunk
from backend.core.s02_tools.mcp import MCPServerManager
from backend.core.s07_task_system import ScheduledTask


class FakeAdapter(LLMAdapter):
    async def test_connection(self) -> bool:
        return True

    async def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(content=f"fake:{request.messages[-1].content}")

    async def stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        if False:
            yield StreamChunk(type="done")


class FakeProviderManager(ProviderManager):
    def __init__(self) -> None:
        self._adapter = FakeAdapter()

    async def get_adapter(self, provider_id: str | None = None) -> LLMAdapter:
        return self._adapter


class FakeBridge:
    def __init__(self, server_manager: MCPServerManager, registry: object) -> None:
        self.server_manager = server_manager
        self.registry = registry

    async def sync_all(self) -> int:
        return 0


class FakeLoop:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs

    async def run(self, prompt: str) -> SimpleNamespace:
        return SimpleNamespace(content=f"done:{prompt}")


class RecordingExecutor:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.event = asyncio.Event()

    async def execute(self, task: ScheduledTask) -> str:
        self.calls.append(task.id)
        self.event.set()
        return f"ran:{task.name}"


def make_mcp_manager(tmp_path: Path) -> MCPServerManager:
    config_path = tmp_path / f"{uuid4().hex}.json"
    config_path.write_text(json.dumps({"servers": []}), encoding="utf-8")
    return MCPServerManager(config_path=str(config_path))


def make_task(name: str = "日报", cron: str = "0 7 * * *") -> ScheduledTask:
    return ScheduledTask(name=name, cron=cron, prompt="hello")


def provider_config() -> ProviderConfig:
    return ProviderConfig(
        id="provider-1",
        name="Fake",
        provider_type=ProviderType.OPENAI_COMPAT,
        base_url="https://example.com",
        api_key="",
        default_model="fake-model",
    )


def make_temp_dir() -> Path:
    root = Path(__file__).resolve().parents[1] / ".tmp_task_system"
    root.mkdir(exist_ok=True)
    return Path(tempfile.mkdtemp(dir=root))


__all__ = [
    "FakeBridge",
    "FakeLoop",
    "FakeProviderManager",
    "RecordingExecutor",
    "make_mcp_manager",
    "make_task",
    "make_temp_dir",
    "provider_config",
]
