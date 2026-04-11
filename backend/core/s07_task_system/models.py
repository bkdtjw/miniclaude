from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator
from zoneinfo import ZoneInfo

from backend.common.types import generate_id

DEFAULT_TASK_TIMEZONE = "Asia/Shanghai"
DEFAULT_FILENAME_TEMPLATE = "{task_id}-{timestamp}.md"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _task_id() -> str:
    return f"task_{generate_id()}"


class NotifyConfig(BaseModel):
    feishu: bool = True
    feishu_webhook_url: str = ""
    feishu_title: str = ""


class OutputConfig(BaseModel):
    save_markdown: bool = False
    directory: str = ""
    filename_template: str = DEFAULT_FILENAME_TEMPLATE


class ScheduledTask(BaseModel):
    id: str = Field(default_factory=_task_id)
    name: str
    cron: str
    timezone: str = DEFAULT_TASK_TIMEZONE
    prompt: str
    notify: NotifyConfig = Field(default_factory=NotifyConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    enabled: bool = True
    workspace: str = ""
    provider_id: str = ""
    model: str = ""
    created_at: datetime = Field(default_factory=_utc_now)
    last_run_at: datetime | None = None
    last_run_status: str = ""
    last_run_output: str = ""

    @field_validator("name", "prompt")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("字段不能为空")
        return text

    @field_validator("cron")
    @classmethod
    def _validate_cron(cls, value: str) -> str:
        cron = value.strip()
        if not cron:
            raise ValueError("cron 不能为空")
        try:
            from croniter import croniter
        except ImportError as exc:  # pragma: no cover
            raise ValueError("croniter 未安装") from exc
        if not croniter.is_valid(cron):
            raise ValueError("cron 表达式无效")
        return cron

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str) -> str:
        timezone_name = value.strip() or DEFAULT_TASK_TIMEZONE
        try:
            ZoneInfo(timezone_name)
        except Exception as exc:
            raise ValueError("时区无效") from exc
        return timezone_name


__all__ = [
    "DEFAULT_FILENAME_TEMPLATE",
    "DEFAULT_TASK_TIMEZONE",
    "NotifyConfig",
    "OutputConfig",
    "ScheduledTask",
]
