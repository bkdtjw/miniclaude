from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from backend.core.s07_task_system.errors import TaskSchedulerError
from backend.core.s07_task_system.models import ScheduledTask
from backend.core.s07_task_system.schedule_utils import cron_matches, minute_key
from backend.core.s07_task_system.store import TaskStore


class TaskScheduler:
    def __init__(self, store: TaskStore, executor: object, check_interval: float = 30.0) -> None:
        self._store = store
        self._executor = executor
        self._check_interval = check_interval
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._active_runs: set[str] = set()
        self._triggered_minutes: dict[str, str] = {}
        self._run_tasks: set[asyncio.Task[str]] = set()

    async def start(self) -> None:
        try:
            if self._running:
                return
            self._running = True
            self._task = asyncio.create_task(self._loop())
        except Exception as exc:
            raise TaskSchedulerError("TASK_SCHEDULER_START_ERROR", str(exc)) from exc

    async def stop(self) -> None:
        try:
            self._running = False
            if self._task is not None:
                self._task.cancel()
                await asyncio.gather(self._task, return_exceptions=True)
                self._task = None
            for task in list(self._run_tasks):
                task.cancel()
            if self._run_tasks:
                await asyncio.gather(*self._run_tasks, return_exceptions=True)
            self._run_tasks.clear()
        except Exception as exc:
            raise TaskSchedulerError("TASK_SCHEDULER_STOP_ERROR", str(exc)) from exc

    async def run_task_now(self, task_id: str) -> str:
        try:
            task = await self._store.get_task(task_id)
            if task is None:
                raise TaskSchedulerError("TASK_NOT_FOUND", f"任务不存在：{task_id}")
            if task.id in self._active_runs:
                raise TaskSchedulerError("TASK_ALREADY_RUNNING", f"任务正在执行：{task_id}")
            return await self._execute_task(task, None, raise_on_error=True)
        except TaskSchedulerError:
            raise
        except Exception as exc:
            raise TaskSchedulerError("TASK_RUN_NOW_ERROR", str(exc)) from exc

    def _should_run(self, task: ScheduledTask, now: datetime) -> bool:
        if not task.enabled or task.id in self._active_runs:
            return False
        current_minute = minute_key(task, now)
        if self._triggered_minutes.get(task.id) == current_minute:
            return False
        return cron_matches(task, now)

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._check_due_tasks()
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            await asyncio.sleep(self._check_interval)

    async def _check_due_tasks(self) -> None:
        now = datetime.now(timezone.utc)
        tasks = await self._store.list_tasks()
        for task in tasks:
            if not self._should_run(task, now):
                continue
            current_minute = minute_key(task, now)
            self._triggered_minutes[task.id] = current_minute
            background = asyncio.create_task(self._execute_task(task, current_minute))
            background.add_done_callback(self._run_tasks.discard)
            self._run_tasks.add(background)

    async def _execute_task(
        self,
        task: ScheduledTask,
        current_minute: str | None,
        raise_on_error: bool = False,
    ) -> str:
        self._active_runs.add(task.id)
        if current_minute is not None:
            self._triggered_minutes[task.id] = current_minute
        try:
            result = await self._executor.execute(task)
            await self._store.update_run_status(task.id, "success", result[:500])
            return result
        except asyncio.CancelledError:
            await self._store.update_run_status(task.id, "error", "任务被取消")
            raise
        except Exception as exc:
            message = str(getattr(exc, "message", exc))
            await self._store.update_run_status(task.id, "error", message[:500])
            if raise_on_error:
                raise TaskSchedulerError("TASK_EXECUTION_ERROR", message) from exc
            return ""
        finally:
            self._active_runs.discard(task.id)


__all__ = ["TaskScheduler"]
