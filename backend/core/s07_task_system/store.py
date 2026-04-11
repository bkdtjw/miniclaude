from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from backend.core.s07_task_system.errors import TaskStoreError
from backend.core.s07_task_system.models import ScheduledTask


class _TaskPayload(BaseModel):
    tasks: list[ScheduledTask] = Field(default_factory=list)


class TaskStore:
    def __init__(self, path: str | None = None) -> None:
        self._path = Path(path) if path else self._default_path()
        self._lock = asyncio.Lock()
        self._tasks: dict[str, ScheduledTask] = {}
        self._last_mtime: float | None = None
        self._load_from_file(force=True)

    async def list_tasks(self) -> list[ScheduledTask]:
        try:
            async with self._lock:
                self._load_from_file()
                return [task.model_copy(deep=True) for task in self._tasks.values()]
        except Exception as exc:
            raise TaskStoreError("TASK_STORE_LIST_ERROR", str(exc)) from exc

    async def get_task(self, task_id: str) -> ScheduledTask | None:
        try:
            async with self._lock:
                self._load_from_file()
                task = self._tasks.get(task_id)
                return task.model_copy(deep=True) if task is not None else None
        except Exception as exc:
            raise TaskStoreError("TASK_STORE_GET_ERROR", str(exc)) from exc

    async def add_task(self, task: ScheduledTask) -> ScheduledTask:
        try:
            async with self._lock:
                self._load_from_file()
                if task.id in self._tasks:
                    raise TaskStoreError("TASK_EXISTS", f"任务已存在：{task.id}")
                self._tasks[task.id] = task.model_copy(deep=True)
                self._save_to_file()
                return self._tasks[task.id].model_copy(deep=True)
        except TaskStoreError:
            raise
        except Exception as exc:
            raise TaskStoreError("TASK_STORE_ADD_ERROR", str(exc)) from exc

    async def update_task(self, task_id: str, **kwargs: Any) -> ScheduledTask | None:
        try:
            async with self._lock:
                self._load_from_file()
                task = self._tasks.get(task_id)
                if task is None:
                    return None
                updated = self._merge_update(task, kwargs)
                self._tasks[task_id] = updated
                self._save_to_file()
                return updated.model_copy(deep=True)
        except Exception as exc:
            raise TaskStoreError("TASK_STORE_UPDATE_ERROR", str(exc)) from exc

    async def remove_task(self, task_id: str) -> bool:
        try:
            async with self._lock:
                self._load_from_file()
                removed = self._tasks.pop(task_id, None)
                if removed is None:
                    return False
                self._save_to_file()
                return True
        except Exception as exc:
            raise TaskStoreError("TASK_STORE_REMOVE_ERROR", str(exc)) from exc

    async def update_run_status(self, task_id: str, status: str, output: str) -> None:
        try:
            await self.update_task(
                task_id,
                last_run_at=datetime_now_utc(),
                last_run_status=status,
                last_run_output=output,
            )
        except Exception as exc:
            raise TaskStoreError("TASK_STORE_RUN_STATUS_ERROR", str(exc)) from exc

    def _default_path(self) -> Path:
        return Path(__file__).resolve().parents[2] / "config" / "scheduled_tasks.json"

    def _load_from_file(self, force: bool = False) -> None:
        self._ensure_file()
        mtime = self._path.stat().st_mtime
        if not force and self._last_mtime is not None and mtime <= self._last_mtime:
            return
        payload = _TaskPayload.model_validate(json.loads(self._path.read_text(encoding="utf-8")))
        self._tasks = {task.id: task for task in payload.tasks}
        self._last_mtime = mtime

    def _save_to_file(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = _TaskPayload(tasks=list(self._tasks.values()))
        self._path.write_text(
            json.dumps(payload.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._last_mtime = self._path.stat().st_mtime

    def _ensure_file(self) -> None:
        if self._path.exists():
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text('{"tasks": []}\n', encoding="utf-8")

    def _merge_update(self, task: ScheduledTask, updates: dict[str, Any]) -> ScheduledTask:
        payload = task.model_dump()
        for key, value in updates.items():
            if value is None:
                continue
            if key in {"notify", "output"} and isinstance(value, dict):
                payload[key] = {**payload.get(key, {}), **value}
                continue
            payload[key] = value
        return ScheduledTask.model_validate(payload)


def datetime_now_utc() -> Any:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


__all__ = ["TaskStore"]
