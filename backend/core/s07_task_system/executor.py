from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from backend.adapters.provider_manager import ProviderManager
from backend.config.settings import Settings
from backend.core.s01_agent_loop import AgentLoop
from backend.core.s02_tools import ToolRegistry
from backend.core.s02_tools.builtin import register_builtin_tools
from backend.core.s02_tools.builtin.feishu_notify import create_feishu_notify_tool
from backend.core.s02_tools.mcp import MCPToolBridge
from backend.core.s07_task_system.errors import TaskExecutorError
from backend.core.s07_task_system.models import ScheduledTask
from backend.core.system_prompt import build_system_prompt
from backend.common.types import AgentConfig

DEFAULT_EXECUTION_TIMEOUT = 300.0


class TaskExecutorDeps(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    provider_manager: ProviderManager
    mcp_manager: object
    settings: Settings
    workspace: str = ""
    provider_id: str = ""
    model: str = ""


class TaskExecutor:
    def __init__(self, deps: TaskExecutorDeps, timeout_seconds: float = DEFAULT_EXECUTION_TIMEOUT) -> None:
        self._deps = deps
        self._timeout_seconds = timeout_seconds

    async def execute(self, task: ScheduledTask) -> str:
        try:
            provider_id = task.provider_id or self._deps.provider_id or None
            model_name = task.model or self._deps.model or self._deps.settings.default_model
            workspace = task.workspace or self._deps.workspace
            adapter = await self._deps.provider_manager.get_adapter(provider_id)
            registry = ToolRegistry()
            register_builtin_tools(
                registry,
                workspace or None,
                mode="auto",
                adapter=adapter,
                default_model=model_name,
                feishu_webhook_url=self._deps.settings.feishu_webhook_url or None,
                feishu_secret=self._deps.settings.feishu_webhook_secret or None,
                youtube_api_key=self._deps.settings.youtube_api_key or None,
                youtube_proxy_url=self._deps.settings.youtube_proxy_url or None,
                twitter_username=self._deps.settings.twitter_username or None,
                twitter_email=self._deps.settings.twitter_email or None,
                twitter_password=self._deps.settings.twitter_password or None,
                twitter_proxy_url=self._deps.settings.twitter_proxy_url or None,
                twitter_cookies_file=self._deps.settings.twitter_cookies_file or None,
            )
            bridge = MCPToolBridge(self._deps.mcp_manager, registry)
            await bridge.sync_all()
            loop = AgentLoop(
                config=AgentConfig(
                    model=model_name,
                    provider=provider_id or self._deps.settings.default_provider,
                    system_prompt=build_system_prompt(workspace or None),
                ),
                adapter=adapter,
                tool_registry=registry,
            )
            response = await asyncio.wait_for(loop.run(task.prompt), timeout=self._timeout_seconds)
            content = response.content.strip()
            if task.output.save_markdown:
                await self._save_markdown(task, content, workspace)
            if task.notify.feishu:
                await self._send_feishu(task, content)
            return content
        except asyncio.TimeoutError as exc:
            raise TaskExecutorError("TASK_EXECUTION_TIMEOUT", "定时任务执行超时") from exc
        except TaskExecutorError:
            raise
        except Exception as exc:
            raise TaskExecutorError("TASK_EXECUTION_ERROR", str(exc)) from exc

    async def _save_markdown(self, task: ScheduledTask, content: str, workspace: str) -> None:
        try:
            directory = self._resolve_output_dir(task, workspace)
            directory.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            filename = task.output.filename_template.format(
                task_id=task.id,
                task_name=_safe_name(task.name),
                timestamp=timestamp,
            )
            target = directory / filename
            await asyncio.to_thread(target.write_text, f"# {task.name}\n\n{content}\n", encoding="utf-8")
        except Exception as exc:
            raise TaskExecutorError("TASK_OUTPUT_ERROR", str(exc)) from exc

    async def _send_feishu(self, task: ScheduledTask, content: str) -> None:
        webhook_url = task.notify.feishu_webhook_url or self._deps.settings.feishu_webhook_url
        if not webhook_url:
            return
        _, executor = create_feishu_notify_tool(
            webhook_url,
            self._deps.settings.feishu_webhook_secret or None,
        )
        result = await executor({"title": task.notify.feishu_title or task.name, "content": content})
        if result.is_error:
            raise TaskExecutorError("TASK_FEISHU_ERROR", result.output)

    def _resolve_output_dir(self, task: ScheduledTask, workspace: str) -> Path:
        root = Path(workspace).resolve() if workspace else Path.cwd()
        output_dir = Path(task.output.directory) if task.output.directory else Path("reports") / "scheduled_tasks"
        return output_dir if output_dir.is_absolute() else root / output_dir


def _safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value).strip("_") or "task"


__all__ = ["TaskExecutor", "TaskExecutorDeps"]
