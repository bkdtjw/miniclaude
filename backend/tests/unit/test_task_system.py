from __future__ import annotations

from pathlib import Path
import asyncio

import pytest

from backend.common.types import ToolResult
from backend.config.settings import settings
from backend.core.s02_tools.builtin.task_scheduler import create_task_tools
from backend.core.s07_task_system import (
    NotifyConfig,
    OutputConfig,
    ScheduledTask,
    TaskExecutor,
    TaskExecutorDeps,
    TaskScheduler,
    TaskStore,
    TaskTooling,
)
from backend.core.s07_task_system import executor as executor_module
from .task_system_test_support import (
    FakeBridge,
    FakeLoop,
    FakeProviderManager,
    RecordingExecutor,
    make_mcp_manager,
    make_task,
    make_temp_dir,
    provider_config,
)


@pytest.mark.asyncio
async def test_task_store_crud() -> None:
    tmp_path = make_temp_dir()
    store = TaskStore(str(tmp_path / "tasks.json"))
    task = await store.add_task(make_task())
    assert len(await store.list_tasks()) == 1
    updated = await store.update_task(task.id, name="晚报", notify={"feishu": False})
    assert updated is not None and updated.name == "晚报"
    assert updated.notify.feishu is False
    await store.update_run_status(task.id, "success", "ok")
    assert (await store.get_task(task.id)).last_run_status == "success"  # type: ignore[union-attr]
    assert await store.remove_task(task.id) is True
    assert await store.get_task(task.id) is None


def test_task_scheduler_should_run_respects_timezone() -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    tmp_path = make_temp_dir()
    scheduler = TaskScheduler(TaskStore(str(tmp_path / "tasks.json")), RecordingExecutor())
    task = make_task()
    assert scheduler._should_run(task, datetime(2026, 4, 10, 23, 0, tzinfo=ZoneInfo("UTC"))) is True
    assert scheduler._should_run(task, datetime(2026, 4, 10, 23, 1, tzinfo=ZoneInfo("UTC"))) is False


@pytest.mark.asyncio
async def test_task_executor_execute_saves_markdown_and_sends_feishu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tmp_path = make_temp_dir()
    sent: list[dict[str, str]] = []

    def fake_feishu_tool(url: str, secret: str | None) -> tuple[object, object]:
        async def execute(args: dict[str, str]) -> ToolResult:
            sent.append({"url": url, "secret": secret or "", **args})
            return ToolResult(output="ok")

        return object(), execute

    monkeypatch.setattr(executor_module, "AgentLoop", FakeLoop)
    monkeypatch.setattr(executor_module, "MCPToolBridge", FakeBridge)
    monkeypatch.setattr(executor_module, "create_feishu_notify_tool", fake_feishu_tool)
    provider = provider_config()
    executor = TaskExecutor(
        TaskExecutorDeps(
            provider_manager=FakeProviderManager(),
            mcp_manager=make_mcp_manager(tmp_path),
            settings=settings,
            workspace=str(tmp_path),
            provider_id=provider.id,
            model=provider.default_model,
        ),
        timeout_seconds=1.0,
    )
    task = make_task()
    task.notify = NotifyConfig(feishu=True, feishu_webhook_url="https://example.com/hook")
    task.output = OutputConfig(save_markdown=True)
    result = await executor.execute(task)
    files = list((tmp_path / "reports" / "scheduled_tasks").glob("*.md"))
    assert result == "done:hello"
    assert files and "日报" in files[0].read_text(encoding="utf-8")
    assert sent[0]["title"] == "日报"


@pytest.mark.asyncio
async def test_scheduler_short_interval_runs_only_once_per_minute() -> None:
    tmp_path = make_temp_dir()
    store = TaskStore(str(tmp_path / "tasks.json"))
    executor = RecordingExecutor()
    scheduler = TaskScheduler(store=store, executor=executor, check_interval=0.1)
    task = await store.add_task(make_task(name="短测", cron="* * * * *"))
    await scheduler.start()
    await asyncio.wait_for(executor.event.wait(), timeout=2.0)
    await asyncio.sleep(0.3)
    await scheduler.stop()
    assert executor.calls == [task.id]
    assert (await store.get_task(task.id)).last_run_status == "success"  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_task_tools_cover_add_list_update_run_and_remove() -> None:
    tmp_path = make_temp_dir()
    store = TaskStore(str(tmp_path / "tasks.json"))
    scheduler = TaskScheduler(store=store, executor=RecordingExecutor(), check_interval=0.1)
    tooling = TaskTooling(
        store=store,
        scheduler=scheduler,
        executor=TaskExecutor(
            TaskExecutorDeps(
                provider_manager=FakeProviderManager(),
                mcp_manager=make_mcp_manager(tmp_path),
                settings=settings,
            )
        ),
        workspace=str(tmp_path),
        provider_id="provider-1",
        model="fake-model",
    )
    tool_map = {definition.name: executor for definition, executor in create_task_tools(tooling)}
    added = await tool_map["add_scheduled_task"]({"name": "测试", "cron": "* * * * *", "prompt": "ping"})
    task = (await store.list_tasks())[0]
    listed = await tool_map["list_scheduled_tasks"]({})
    updated = await tool_map["update_scheduled_task"]({"task_id": task.id, "name": "测试2"})
    ran = await tool_map["run_scheduled_task_now"]({"task_id": task.id})
    removed = await tool_map["remove_scheduled_task"]({"task_id": task.id})
    assert "任务ID" in added.output and task.id in listed.output
    assert "测试2" in updated.output and "ran:测试2" in ran.output
    assert removed.is_error is False
