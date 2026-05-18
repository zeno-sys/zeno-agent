"""backend_file_tools：registry 分发与 FilesystemBackend 集成（临时目录隔离）。"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from agent.tool.registry import registry
from backends.filesystem import FilesystemBackend
from agent.core.context import AgentContext
from agent.run_cli import _tool_dispatch_extra_args
from tools import register_all_tools
from tools.backend_file_tools import set_filesystem_backend


def _step(banner: str) -> None:
    print(f"--------------------------------{banner}--------------------------------")


@pytest.fixture
def isolated_backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """临时根目录 + virtual_mode，避免污染工作区。"""
    monkeypatch.chdir(tmp_path)
    backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)
    set_filesystem_backend(backend)
    yield backend
    set_filesystem_backend(None)


@pytest.fixture(autouse=True)
def _register_tools():
    register_all_tools()


def test_registry_has_backend_file_tools() -> None:
    _step("检查 8 个 backend_file 工具已注册")
    names = {
        "list_directory",
        "read_file",
        "grep_files",
        "glob_files",
        "write_file",
        "edit_file",
        "upload_files",
        "download_files",
    }
    for name in names:
        entry = registry.get_entry(name)
        assert entry is not None, name
        assert entry.toolset == "backend_file", name
        print(f"  ok: {name} toolset={entry.toolset}")


def test_dispatch_write_read_edit(isolated_backend: FilesystemBackend) -> None:
    _step("write_file → read_file → edit_file")
    write_raw = registry.dispatch(
        "write_file",
        {"file_path": "/notes.txt", "content": "alpha\nNEEDLE\n"},
        {},
    )
    write_data = json.loads(write_raw)
    print(f"  write: {write_data}")
    assert write_data.get("ok") is True

    read_raw = registry.dispatch(
        "read_file",
        {"file_path": "/notes.txt", "offset": 0, "limit": 10},
        {},
    )
    read_data = json.loads(read_raw)
    print(f"  read lines preview: {read_data['content'][:80]!r}...")
    assert "NEEDLE" in read_data["content"]

    edit_raw = registry.dispatch(
        "edit_file",
        {
            "file_path": "/notes.txt",
            "old_string": "NEEDLE",
            "new_string": "MARK",
        },
        {},
    )
    edit_data = json.loads(edit_raw)
    print(f"  edit: {edit_data}")
    assert edit_data.get("ok") is True
    assert edit_data.get("occurrences") == 1


def test_dispatch_list_glob_grep(isolated_backend: FilesystemBackend) -> None:
    _step("准备多文件并测试 list / glob / grep")
    isolated_backend.write("/sub/a.txt", "TODO one\n")
    isolated_backend.write("/sub/b.txt", "TODO two\n")

    ls_raw = registry.dispatch("list_directory", {"path": "/sub"}, {})
    ls_data = json.loads(ls_raw)
    print(f"  ls items: {[i['path'] for i in ls_data['items']]}")
    assert len(ls_data["items"]) >= 2

    glob_raw = registry.dispatch("glob_files", {"pattern": "**/*.txt", "path": "/"}, {})
    glob_data = json.loads(glob_raw)
    paths = {i["path"] for i in glob_data["items"]}
    print(f"  glob paths: {paths}")
    assert "/sub/a.txt" in paths

    grep_raw = registry.dispatch("grep_files", {"pattern": "TODO", "path": "/sub"}, {})
    grep_data = json.loads(grep_raw)
    print(f"  grep matches: {len(grep_data['matches'])}")
    assert len(grep_data["matches"]) == 2


def test_extra_args_injects_context_backend(isolated_backend: FilesystemBackend) -> None:
    _step("AgentContext.filesystem_backend 经 _tool_dispatch_extra_args 注入")
    ctx = AgentContext()
    ctx.filesystem_backend = isolated_backend
    extra = _tool_dispatch_extra_args(ctx, "read_file")
    print(f"  extra keys: {list(extra.keys())}")
    assert extra.get("filesystem_backend") is isolated_backend
    assert "filesystem_backend" not in _tool_dispatch_extra_args(ctx, "todo")


def test_dispatch_upload_download(isolated_backend: FilesystemBackend) -> None:
    _step("upload_files / download_files 往返")
    payload = b"\x00\x01binary"
    b64 = base64.b64encode(payload).decode("ascii")
    up_raw = registry.dispatch(
        "upload_files",
        {
            "files": [
                {
                    "path": "/uploads/bin.dat",
                    "content": b64,
                    "content_encoding": "base64",
                }
            ]
        },
        {},
    )
    up_data = json.loads(up_raw)
    print(f"  upload: {up_data['results']}")
    assert up_data["results"][0]["error"] is None

    down_raw = registry.dispatch("download_files", {"paths": ["/uploads/bin.dat"]}, {})
    down_data = json.loads(down_raw)
    got = base64.b64decode(down_data["results"][0]["content_base64"])
    print(f"  download bytes len: {len(got)}")
    assert got == payload
