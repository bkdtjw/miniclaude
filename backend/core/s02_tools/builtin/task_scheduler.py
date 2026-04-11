from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from backend.common.types import ToolDefinition, ToolExecuteFn, ToolParameterSchema, ToolResult
from backend.core.s07_task_system import (
    NotifyConfig,
    OutputConfig,
    ScheduledTask,
    TaskTooling,
    format_task_list,
)
from .task_scheduler_support import (
    AddTaskArgs,
    TaskIdArgs,
    UpdateTaskArgs,
    format_task_confirmation,
    nested_values,
)


def create_task_tools(tooling: TaskTooling) -> list[tuple[ToolDefinition, ToolExecuteFn]]:
    return [
        _create_add_task_tool(tooling),
        _create_list_tasks_tool(tooling),
        _create_update_task_tool(tooling),
        _create_remove_task_tool(tooling),
        _create_run_task_now_tool(tooling),
    ]


def _create_add_task_tool(tooling: TaskTooling) -> tuple[ToolDefinition, ToolExecuteFn]:
    definition = ToolDefinition(
        name="add_scheduled_task",
        description="创建一个新的定时任务。",
        category="shell",
        parameters=ToolParameterSchema(
            properties={
                "name": {"type": "string", "description": "任务名称"},
                "cron": {"type": "string", "description": "cron 表达式"},
                "prompt": {"type": "string", "description": "执行 prompt"},
                "timezone": {"type": "string", "description": "时区，默认 Asia/Shanghai"},
                "notify_feishu": {"type": "boolean", "description": "是否发送飞书"},
                "save_markdown": {"type": "boolean", "description": "是否保存 Markdown"},
            },
            required=["name", "cron", "prompt"],
        ),
    )

    async def execute(args: dict[str, Any]) -> ToolResult:
        try:
            params = AddTaskArgs.model_validate(args)
            task = ScheduledTask(
                name=params.name,
                cron=params.cron,
                prompt=params.prompt,
                timezone=params.timezone,
                notify=NotifyConfig(
                    feishu=params.notify_feishu,
                    feishu_webhook_url=params.feishu_webhook_url,
                    feishu_title=params.feishu_title,
                ),
                output=OutputConfig(
                    save_markdown=params.save_markdown,
                    directory=params.output_directory,
                    filename_template=params.filename_template,
                ),
                enabled=params.enabled,
                workspace=tooling.workspace,
                provider_id=tooling.provider_id,
                model=tooling.model,
            )
            saved = await tooling.store.add_task(task)
            return ToolResult(output=format_task_confirmation("已创建定时任务", saved))
        except ValidationError as exc:
            return ToolResult(output=exc.errors()[0].get("msg", "参数错误"), is_error=True)
        except Exception as exc:
            return ToolResult(output=str(exc), is_error=True)

    return definition, execute


def _create_list_tasks_tool(tooling: TaskTooling) -> tuple[ToolDefinition, ToolExecuteFn]:
    definition = ToolDefinition(
        name="list_scheduled_tasks",
        description="列出当前所有定时任务。",
        category="shell",
        parameters=ToolParameterSchema(),
    )

    async def execute(_: dict[str, Any]) -> ToolResult:
        try:
            return ToolResult(output=format_task_list(await tooling.store.list_tasks()))
        except Exception as exc:
            return ToolResult(output=str(exc), is_error=True)

    return definition, execute


def _create_update_task_tool(tooling: TaskTooling) -> tuple[ToolDefinition, ToolExecuteFn]:
    definition = ToolDefinition(
        name="update_scheduled_task",
        description="更新已有定时任务。",
        category="shell",
        parameters=ToolParameterSchema(
            properties={"task_id": {"type": "string", "description": "任务 ID"}},
            required=["task_id"],
        ),
    )

    async def execute(args: dict[str, Any]) -> ToolResult:
        try:
            params = UpdateTaskArgs.model_validate(args)
            updated = await tooling.store.update_task(
                params.task_id,
                **{
                    key: value
                    for key, value in {
                        "name": params.name,
                        "cron": params.cron,
                        "prompt": params.prompt,
                        "timezone": params.timezone,
                        "enabled": params.enabled,
                        "notify": nested_values(
                            feishu=params.notify_feishu,
                            feishu_webhook_url=params.feishu_webhook_url,
                            feishu_title=params.feishu_title,
                        ),
                        "output": nested_values(
                            save_markdown=params.save_markdown,
                            directory=params.output_directory,
                            filename_template=params.filename_template,
                        ),
                    }.items()
                    if value not in (None, {})
                },
            )
            if updated is None:
                return ToolResult(output=f"任务不存在：{params.task_id}", is_error=True)
            return ToolResult(output=format_task_confirmation("已更新任务", updated))
        except ValidationError as exc:
            return ToolResult(output=exc.errors()[0].get("msg", "参数错误"), is_error=True)
        except Exception as exc:
            return ToolResult(output=str(exc), is_error=True)

    return definition, execute


def _create_remove_task_tool(tooling: TaskTooling) -> tuple[ToolDefinition, ToolExecuteFn]:
    definition = ToolDefinition(
        name="remove_scheduled_task",
        description="删除一个定时任务。",
        category="shell",
        parameters=ToolParameterSchema(
            properties={"task_id": {"type": "string", "description": "任务 ID"}},
            required=["task_id"],
        ),
    )

    async def execute(args: dict[str, Any]) -> ToolResult:
        try:
            params = TaskIdArgs.model_validate(args)
            removed = await tooling.store.remove_task(params.task_id)
            if not removed:
                return ToolResult(output=f"任务不存在：{params.task_id}", is_error=True)
            return ToolResult(output=f"已删除定时任务 {params.task_id}")
        except ValidationError as exc:
            return ToolResult(output=exc.errors()[0].get("msg", "参数错误"), is_error=True)
        except Exception as exc:
            return ToolResult(output=str(exc), is_error=True)

    return definition, execute


def _create_run_task_now_tool(tooling: TaskTooling) -> tuple[ToolDefinition, ToolExecuteFn]:
    definition = ToolDefinition(
        name="run_scheduled_task_now",
        description="立即执行一个定时任务。",
        category="shell",
        parameters=ToolParameterSchema(
            properties={"task_id": {"type": "string", "description": "任务 ID"}},
            required=["task_id"],
        ),
    )

    async def execute(args: dict[str, Any]) -> ToolResult:
        try:
            params = TaskIdArgs.model_validate(args)
            result = await tooling.scheduler.run_task_now(params.task_id)
            return ToolResult(output=result or f"任务 {params.task_id} 已执行")
        except ValidationError as exc:
            return ToolResult(output=exc.errors()[0].get("msg", "参数错误"), is_error=True)
        except Exception as exc:
            return ToolResult(output=str(exc), is_error=True)

    return definition, execute
__all__ = ["create_task_tools"]
