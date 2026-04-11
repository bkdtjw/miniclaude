from __future__ import annotations

from datetime import datetime, timedelta, timezone

from zoneinfo import ZoneInfo

from backend.core.s07_task_system.models import ScheduledTask

WEEKDAY_NAMES = {
    "0": "周日",
    "1": "周一",
    "2": "周二",
    "3": "周三",
    "4": "周四",
    "5": "周五",
    "6": "周六",
    "7": "周日",
}


def get_task_zone(task: ScheduledTask) -> ZoneInfo:
    return ZoneInfo(task.timezone)


def to_task_time(task: ScheduledTask, when: datetime) -> datetime:
    aware = when if when.tzinfo is not None else when.replace(tzinfo=timezone.utc)
    return aware.astimezone(get_task_zone(task))


def task_minute(task: ScheduledTask, when: datetime) -> datetime:
    return to_task_time(task, when).replace(second=0, microsecond=0)


def cron_matches(task: ScheduledTask, when: datetime) -> bool:
    from croniter import croniter

    current = task_minute(task, when)
    previous = current - timedelta(minutes=1)
    next_run = croniter(task.cron, previous).get_next(datetime)
    if next_run.tzinfo is None:
        next_run = next_run.replace(tzinfo=current.tzinfo)
    return next_run == current


def get_next_run_at(task: ScheduledTask, when: datetime | None = None) -> datetime:
    from croniter import croniter

    reference = to_task_time(task, when or datetime.now(timezone.utc))
    next_run = croniter(task.cron, reference).get_next(datetime)
    return next_run if next_run.tzinfo is not None else next_run.replace(tzinfo=reference.tzinfo)


def minute_key(task: ScheduledTask, when: datetime) -> str:
    return task_minute(task, when).isoformat(timespec="minutes")


def describe_cron(cron: str) -> str:
    fields = cron.split()
    if len(fields) != 5:
        return cron
    minute, hour, day, month, weekday = fields
    if day == "*" and month == "*" and weekday == "*":
        if minute == "*" and hour == "*":
            return "每分钟"
        if minute.isdigit() and hour.isdigit():
            return f"每天 {int(hour):02d}:{int(minute):02d}"
    if day == "*" and month == "*" and weekday in WEEKDAY_NAMES and minute.isdigit() and hour.isdigit():
        return f"{WEEKDAY_NAMES[weekday]} {int(hour):02d}:{int(minute):02d}"
    return cron


def summarize_task(task: ScheduledTask, when: datetime | None = None) -> str:
    next_run = get_next_run_at(task, when)
    status = task.last_run_status or "idle"
    return (
        f"[{task.id}] {task.name} | {describe_cron(task.cron)} | "
        f"下次执行：{next_run.strftime('%Y-%m-%d %H:%M')} | 状态：{status}"
    )


def format_task_list(tasks: list[ScheduledTask], when: datetime | None = None) -> str:
    if not tasks:
        return "当前没有定时任务。"
    lines = ["当前定时任务："]
    for index, task in enumerate(tasks, start=1):
        lines.append(f"  {index}. {summarize_task(task, when)}")
    return "\n".join(lines)


__all__ = [
    "cron_matches",
    "describe_cron",
    "format_task_list",
    "get_next_run_at",
    "minute_key",
    "summarize_task",
    "task_minute",
    "to_task_time",
]
