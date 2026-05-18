"""测试 ``/`` 斜杠命令的发现与展开。"""

from pathlib import Path

from agent.command.command_resolver import (
    format_commands_help,
    refresh_commands_cache,
    resolve_user_input,
)
from agent.command.command_utils import discover_commands, load_command, parse_command_file


def _step(banner: str, payload: str) -> None:
    print(f"--------------------------------{banner}--------------------------------")
    print(payload)


def test_parse_command_file_cursor_header(tmp_path: Path) -> None:
    path = tmp_path / "create-tests.md"
    path.write_text(
        "# create-tests\n\n在 tests 下写 pytest。\n",
        encoding="utf-8",
    )
    spec = parse_command_file(path, path.read_text(encoding="utf-8"))
    _step("parse header", f"name={spec.name!r}, body={spec.body!r}")
    assert spec.name == "create-tests"
    assert "pytest" in spec.body


def test_resolve_say_hello_builtin() -> None:
    refresh_commands_cache()
    commands = discover_commands()
    _step("discovered", ", ".join(sorted(commands)) or "(empty)")
    assert "say_hello" in commands

    resolved = resolve_user_input("/say_hello", refresh=True)
    _step("expanded", resolved.content)
    assert resolved.is_command
    assert resolved.command_name == "say_hello"
    assert "Hello" in resolved.content
    assert not resolved.skip_model


def test_resolve_with_arguments_structured(tmp_path: Path, monkeypatch) -> None:
    commands_dir = tmp_path / "commands"
    commands_dir.mkdir()
    (commands_dir / "say_hello.md").write_text(
        "请在每次回答问题前，都加上 Hello。\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    refresh_commands_cache()

    resolved = resolve_user_input("/say_hello 这个命令里写的啥", refresh=True)
    _step("structured expanded", resolved.content)
    assert "<命令说明>" in resolved.content
    assert "<用户消息>" in resolved.content
    assert "这个命令里写的啥" in resolved.content
    assert "Hello" in resolved.content
    assert "用户补充" not in resolved.content


def test_resolve_with_arguments(tmp_path: Path, monkeypatch) -> None:
    commands_dir = tmp_path / "commands"
    commands_dir.mkdir()
    (commands_dir / "echo.md").write_text(
        "重复用户输入：$ARGUMENTS\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    refresh_commands_cache()

    resolved = resolve_user_input("/echo 你好世界", refresh=True)
    _step("echo expanded", resolved.content)
    assert resolved.content == "重复用户输入：你好世界"


def test_help_lists_commands() -> None:
    refresh_commands_cache()
    resolved = resolve_user_input("/help", refresh=True)
    _step("help output", resolved.content[:200])
    assert resolved.is_help
    assert resolved.skip_model
    assert "say_hello" in resolved.content or "可用命令" in resolved.content


def test_unknown_command(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    refresh_commands_cache()
    resolved = resolve_user_input("/not-a-real-cmd", refresh=True)
    _step("unknown", resolved.content.splitlines()[0])
    assert resolved.unknown_command == "not-a-real-cmd"
    assert resolved.skip_model


def test_plain_input_unchanged() -> None:
    resolved = resolve_user_input("普通问题")
    assert resolved.content == "普通问题"
    assert not resolved.is_command


def test_format_commands_help_non_empty() -> None:
    refresh_commands_cache()
    text = format_commands_help()
    _step("help text", text.splitlines()[0])
    assert "命令" in text
