"""Discover and load slash commands from ``commands/`` and compatible dirs."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from agent.skill.skill_utils import parse_frontmatter

logger = logging.getLogger(__name__)

_FRAMEWORK_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_COMMANDS_DIR = _FRAMEWORK_ROOT / "commands"
_CURSOR_COMMANDS_DIRNAME = ".cursor/commands"
_HELP_COMMANDS = frozenset({"help", "commands"})


@dataclass(frozen=True)
class CommandSpec:
    name: str
    body: str
    description: str
    source_path: Path


def get_commands_dirs() -> List[Path]:
    """Return command scan roots in override order (later wins on name collision)."""
    cwd = Path.cwd()
    dirs: List[Path] = []
    if _DEFAULT_COMMANDS_DIR.is_dir():
        dirs.append(_DEFAULT_COMMANDS_DIR)
    project_commands = cwd / "commands"
    if project_commands.is_dir() and project_commands.resolve() != _DEFAULT_COMMANDS_DIR.resolve():
        dirs.append(project_commands)
    cursor_commands = cwd / _CURSOR_COMMANDS_DIRNAME
    if cursor_commands.is_dir():
        dirs.append(cursor_commands)
    return dirs


def _first_line_title(body: str) -> tuple[Optional[str], str]:
    """Parse optional Cursor-style ``# command-name`` header."""
    lines = body.splitlines()
    if not lines:
        return None, body
    first = lines[0].strip()
    match = re.match(r"^#\s+([\w-]+)\s*$", first)
    if not match:
        return None, body
    rest = "\n".join(lines[1:]).lstrip("\n")
    return match.group(1), rest


def _first_non_empty_line(body: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return ""


def parse_command_file(path: Path, raw: str) -> CommandSpec:
    frontmatter, body = parse_frontmatter(raw)
    header_name, body = _first_line_title(body)
    name = str(frontmatter.get("name") or header_name or path.stem).strip()
    description = str(frontmatter.get("description") or "").strip()
    if not description:
        description = _first_non_empty_line(body)
    if len(description) > 200:
        description = description[:197] + "..."
    return CommandSpec(
        name=name,
        body=body.strip(),
        description=description,
        source_path=path,
    )


def load_command(path: Path) -> Optional[CommandSpec]:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.debug("Failed to read command file %s: %s", path, exc)
        return None
    try:
        return parse_command_file(path, raw)
    except Exception as exc:
        logger.debug("Failed to parse command file %s: %s", path, exc)
        return None


def discover_commands() -> Dict[str, CommandSpec]:
    """Scan all command directories; later directories override same name."""
    commands: Dict[str, CommandSpec] = {}
    for root in get_commands_dirs():
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*.md")):
            spec = load_command(path)
            if spec and spec.name:
                commands[spec.name] = spec
    return commands


def is_help_command(name: str) -> bool:
    return name.lower() in _HELP_COMMANDS
