"""Expand ``/command [args]`` user input into model-facing prompts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

from agent.command.command_utils import CommandSpec, discover_commands, is_help_command
from agent.core.multimodal import parse_image_attachments

_SLASH_INPUT_RE = re.compile(
    r"^/([\w-]+)(?:\s+([\s\S]*))?$",
)
_ARGUMENTS_PLACEHOLDER = "$ARGUMENTS"


@dataclass(frozen=True)
class ResolvedUserInput:
    """Result of parsing a user message that may start with ``/``."""

    content: str
    image_paths: tuple[Path, ...] = ()
    is_command: bool = False
    command_name: Optional[str] = None
    is_help: bool = False
    unknown_command: Optional[str] = None
    skip_model: bool = False


@lru_cache(maxsize=1)
def _cached_commands() -> Dict[str, CommandSpec]:
    return discover_commands()


def refresh_commands_cache() -> None:
    _cached_commands.cache_clear()


def format_commands_help() -> str:
    commands = _cached_commands()
    if not commands:
        return (
            "There are no available commands. You can add "
            "`<name>.md` 文件。"
        )
    lines = ["Available commands (trigger with `/command_name`):", ""]
    for name in sorted(commands):
        spec = commands[name]
        desc = spec.description or "(No description)"
        lines.append(f"  /{name} — {desc}")
    lines.append("")
    lines.append(
        "Usage: `/command_name` (only load command description); "
        "`/command_name your question` (description and user question are separated); "
        "If the body contains $ARGUMENTS, it will be replaced with the text after the command name."
    )
    return "\n".join(lines)


def _finalize_resolved(
    content: str,
    *,
    is_command: bool = False,
    command_name: Optional[str] = None,
    is_help: bool = False,
    unknown_command: Optional[str] = None,
    skip_model: bool = False,
) -> ResolvedUserInput:
    text, image_paths = parse_image_attachments(content)
    return ResolvedUserInput(
        content=text,
        image_paths=image_paths,
        is_command=is_command,
        command_name=command_name,
        is_help=is_help,
        unknown_command=unknown_command,
        skip_model=skip_model,
    )


def _expand_body(command_name: str, body: str, arguments: str) -> str:
    text = body.strip()
    args = arguments.strip()
    if _ARGUMENTS_PLACEHOLDER in text:
        return text.replace(_ARGUMENTS_PLACEHOLDER, args)
    if not args:
        return text
    return (
        f"The user triggered the slash command `/{command_name}`.\n"
        "Please follow the instructions in the <Command Description> to impose constraints on your response; "
        "the <User Message> represents the user's actual question or task for this round and should take priority in your reply.\n\n"
        f"<Command Description>\n{text}\n</Command Description>\n\n"
        f"<User Message>\n{args}\n</User Message>"
    )


def resolve_user_input(raw: str, *, refresh: bool = False) -> ResolvedUserInput:
    """解析用户文本；将斜杠命令展开为提示内容。"""
    text = raw.strip()
    if not text.startswith("/"):
        return _finalize_resolved(raw)

    match = _SLASH_INPUT_RE.match(text)
    if not match:
        return _finalize_resolved(raw)

    command_name = match.group(1)
    arguments = match.group(2) or ""

    if is_help_command(command_name):
        return _finalize_resolved(
            format_commands_help(),
            is_command=True,
            command_name=command_name,
            is_help=True,
            skip_model=True,
        )

    if refresh:
        refresh_commands_cache()
    commands = _cached_commands()
    spec = commands.get(command_name)
    if spec is None:
        hint = format_commands_help()
        return _finalize_resolved(
            f"Unknown command `/{command_name}`.\n\n{hint}",
            is_command=True,
            command_name=command_name,
            unknown_command=command_name,
            skip_model=True,
        )

    expanded = _expand_body(command_name, spec.body, arguments)
    return _finalize_resolved(
        expanded,
        is_command=True,
        command_name=command_name,
    )
