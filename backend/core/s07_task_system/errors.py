from __future__ import annotations

from backend.common.errors import AgentError


class TaskSystemError(AgentError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code=code, message=message)


class TaskStoreError(TaskSystemError):
    pass


class TaskSchedulerError(TaskSystemError):
    pass


class TaskExecutorError(TaskSystemError):
    pass


__all__ = [
    "TaskExecutorError",
    "TaskSchedulerError",
    "TaskStoreError",
    "TaskSystemError",
]
