from __future__ import annotations

import argparse
import os
from collections.abc import Sequence

from backend.common.errors import AgentError, LLMError
from backend.core.s07_task_system import format_task_list

from .console_helpers import (
    HELP_TEXT,
    _find_model_owner,
    _find_provider,
    _format_provider_lines,
    _read_multiline_input,
)
from .display import CliPrinter
from .models import CliArgs, CliCommand, CliCommandResult, CliError, CliSession, SessionUpdate
from .session import rebuild_session, run_request


def parse_args(argv: Sequence[str] | None = None) -> CliArgs:
    parser = argparse.ArgumentParser(prog="miniclaude", description="Agent Studio CLI")
    parser.add_argument("-w", "--workspace", default=os.getcwd(), help="workspace path")
    parser.add_argument("-m", "--model", default=None, help="model name")
    parser.add_argument("-p", "--provider", default=None, help="provider id or name")
    parser.add_argument("--mcp-config", default=None, help="path to MCP server config")
    parser.add_argument(
        "--permission-mode",
        choices=["readonly", "auto", "full"],
        default="auto",
        help="tool permission mode",
    )
    namespace = parser.parse_args(list(argv) if argv is not None else None)
    return CliArgs(
        workspace=os.path.abspath(namespace.workspace),
        model=namespace.model,
        provider=namespace.provider,
        permission_mode=namespace.permission_mode,
        mcp_config=os.path.abspath(namespace.mcp_config) if namespace.mcp_config else None,
    )


def parse_command(raw_command: str) -> CliCommand:
    stripped = raw_command.strip()
    parts = stripped.split(maxsplit=1)
    return CliCommand(name=parts[0].lower(), argument=parts[1].strip() if len(parts) > 1 else "")


async def handle_command(
    session: CliSession, command: CliCommand, printer: CliPrinter
) -> CliCommandResult:
    try:
        if command.name in {"/exit", "/quit"}:
            printer.print_info("bye.")
            return CliCommandResult(session=session, should_exit=True)
        if command.name == "/help":
            printer.print_info(HELP_TEXT)
            return CliCommandResult(session=session)
        if command.name == "/tools":
            printer.print_tools(session)
            return CliCommandResult(session=session)
        if command.name == "/tasks":
            if session.task_tooling is None:
                printer.print_info("[error] 定时任务系统未初始化。")
                return CliCommandResult(session=session)
            if command.argument.startswith("run "):
                task_id = command.argument.split(maxsplit=1)[1].strip()
                if not task_id:
                    printer.print_info("[error] 请提供任务 ID。")
                    return CliCommandResult(session=session)
                result = await session.task_tooling.scheduler.run_task_now(task_id)
                printer.print_info(result or f"[info] 任务 {task_id} 已执行。")
                return CliCommandResult(session=session)
            tasks = await session.task_tooling.store.list_tasks()
            printer.print_info(format_task_list(tasks))
            return CliCommandResult(session=session)
        if command.name == "/clear":
            session.loop.reset()
            printer.print_info("[info] 对话历史已清空。")
            return CliCommandResult(session=session)
        if command.name == "/provider":
            providers = await session.manager.list_all()
            if not command.argument:
                printer.print_info(_format_provider_lines(providers, session.state.provider_id))
                return CliCommandResult(session=session)
            target = _find_provider(providers, command.argument)
            if target is None:
                printer.print_info(f"[error] provider 不存在: {command.argument}")
                return CliCommandResult(session=session)
            if target.id == session.state.provider_id:
                printer.print_info(f"[info] 当前 provider 已是 {target.name}")
                return CliCommandResult(session=session)
            updated = await rebuild_session(
                session,
                SessionUpdate(
                    provider=target.id,
                    model=target.default_model,
                    preserve_history=True,
                    clear_provider_metadata=True,
                ),
            )
            printer.print_info(
                "\n".join(
                    [
                        f"[info] 已切换到 provider {target.name}",
                        f"       model: {updated.state.model}",
                        "       models: "
                        + ", ".join(target.available_models or [target.default_model]),
                        "       history: preserved, provider metadata cleared",
                    ]
                )
            )
            return CliCommandResult(session=updated)
        if command.name == "/model":
            if not command.argument:
                printer.print_info(f"[info] 当前模型: {session.state.model}")
                return CliCommandResult(session=session)
            providers = await session.manager.list_all()
            owner = _find_model_owner(providers, command.argument)
            if owner is not None and owner.id != session.state.provider_id:
                printer.print_info(
                    "\n".join(
                        [
                            "[!] 当前 provider 是 "
                            f"{session.state.provider_name}，模型 {command.argument} "
                            "不在其可用模型列表中。",
                            f"    请先用 /provider {owner.name} 切换到 {owner.name} provider。",
                        ]
                    )
                )
                return CliCommandResult(session=session)
            if (
                session.state.available_models
                and command.argument not in session.state.available_models
            ):
                printer.print_info(f"[error] 当前 provider 不支持模型: {command.argument}")
                return CliCommandResult(session=session)
            updated = await rebuild_session(
                session,
                SessionUpdate(model=command.argument, preserve_history=True),
            )
            printer.print_info(f"[info] 已切换到模型 {updated.state.model}，对话历史已保留。")
            return CliCommandResult(session=updated)
        if command.name == "/workspace":
            if not command.argument:
                printer.print_info(f"[info] 当前工作目录: {session.state.workspace}")
                return CliCommandResult(session=session)
            updated = await rebuild_session(
                session,
                SessionUpdate(workspace=command.argument.strip().strip("\"'")),
            )
            printer.print_info(
                f"[info] 已切换工作目录到 {updated.state.workspace}，对话历史已清空。"
            )
            return CliCommandResult(session=updated)
        printer.print_info("[error] 未知命令，输入 /help 查看可用命令。")
        return CliCommandResult(session=session)
    except (CliError, AgentError, LLMError):
        raise
    except Exception as exc:
        raise CliError("CLI_COMMAND_ERROR", str(exc)) from exc


async def run_repl(session: CliSession, printer: CliPrinter) -> None:
    try:
        current_session = session
        printer.print_welcome(current_session)
        while True:
            user_input = _read_multiline_input(printer)
            if user_input is None:
                printer.print_info("bye.")
                return
            if not user_input:
                continue
            if user_input.startswith("/"):
                result = await handle_command(current_session, parse_command(user_input), printer)
                current_session = result.session
                if result.should_exit:
                    return
                continue
            try:
                await run_request(current_session, user_input)
            except CliError as exc:
                printer.print_info(f"[error] {exc.message}")
            except (AgentError, LLMError):
                continue
    except (CliError, AgentError, LLMError):
        raise
    except Exception as exc:
        raise CliError("CLI_REPL_ERROR", str(exc)) from exc


__all__ = ["_read_multiline_input", "handle_command", "parse_args", "parse_command", "run_repl"]
