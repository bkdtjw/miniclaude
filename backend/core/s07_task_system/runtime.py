from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from backend.adapters.provider_manager import ProviderManager
from backend.config.settings import Settings
from backend.core.s07_task_system.executor import TaskExecutor, TaskExecutorDeps
from backend.core.s07_task_system.scheduler import TaskScheduler
from backend.core.s07_task_system.store import TaskStore


class TaskRuntimeDeps(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    provider_manager: ProviderManager
    mcp_manager: object
    settings: Settings
    workspace: str = ""
    provider_id: str = ""
    model: str = ""


class TaskTooling(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    store: TaskStore
    scheduler: TaskScheduler
    executor: TaskExecutor
    workspace: str = ""
    provider_id: str = ""
    model: str = ""

    def with_context(self, workspace: str = "", provider_id: str = "", model: str = "") -> TaskTooling:
        return self.model_copy(
            update={
                "workspace": workspace,
                "provider_id": provider_id,
                "model": model,
            }
        )


def create_task_tooling(deps: TaskRuntimeDeps) -> TaskTooling:
    store = TaskStore()
    executor = TaskExecutor(
        TaskExecutorDeps(
            provider_manager=deps.provider_manager,
            mcp_manager=deps.mcp_manager,
            settings=deps.settings,
            workspace=deps.workspace,
            provider_id=deps.provider_id,
            model=deps.model,
        )
    )
    scheduler = TaskScheduler(store=store, executor=executor)
    return TaskTooling(
        store=store,
        scheduler=scheduler,
        executor=executor,
        workspace=deps.workspace,
        provider_id=deps.provider_id,
        model=deps.model,
    )


__all__ = ["TaskRuntimeDeps", "TaskTooling", "create_task_tooling"]
