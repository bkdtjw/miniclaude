from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from backend.core.s07_task_system import ScheduledTask, describe_cron


class AddTaskArgs(BaseModel):
    name: str
    cron: str
    prompt: str
    timezone: str = "Asia/Shanghai"
    notify_feishu: bool = True
    feishu_webhook_url: str = ""
    feishu_title: str = ""
    save_markdown: bool = False
    output_directory: str = ""
    filename_template: str = "{task_id}-{timestamp}.md"
    enabled: bool = True


class UpdateTaskArgs(BaseModel):
    task_id: str
    name: str | None = None
    cron: str | None = None
    prompt: str | None = None
    timezone: str | None = None
    notify_feishu: bool | None = None
    feishu_webhook_url: str | None = None
    feishu_title: str | None = None
    save_markdown: bool | None = None
    output_directory: str | None = None
    filename_template: str | None = None
    enabled: bool | None = None


class TaskIdArgs(BaseModel):
    task_id: str


def format_task_confirmation(title: str, task: ScheduledTask) -> str:
    return (
        f"{title}：\n"
        f"  名称：{task.name}\n"
        f"  时间：{describe_cron(task.cron)}（{task.timezone}）\n"
        f"  通知：{'飞书' if task.notify.feishu else '关闭'}\n"
        f"  任务ID：{task.id}"
    )


def nested_values(**kwargs: Any) -> dict[str, Any]:
    return {key: value for key, value in kwargs.items() if value is not None}


__all__ = [
    "AddTaskArgs",
    "TaskIdArgs",
    "UpdateTaskArgs",
    "format_task_confirmation",
    "nested_values",
]
