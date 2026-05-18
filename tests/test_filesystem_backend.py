"""FilesystemBackend：读写、编辑、列表、glob、grep、上传下载（临时目录隔离）。"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

import pytest

from backends.base import EditResult, FileDownloadResponse, FileUploadResponse, WriteResult
from backends.filesystem import FilesystemBackend
from backends.utils import EMPTY_CONTENT_WARNING

_CONTENT_PREVIEW = 72


def _step(banner: str) -> None:
    print(f"--------------------------------{banner}--------------------------------")


def _preview(text: str, *, limit: int = _CONTENT_PREVIEW) -> str:
    one_line = str(text).replace("\n", "\\n")
    if len(one_line) <= limit:
        return one_line
    return one_line[: limit - 3] + "..."


def _print_root(label: str, root: Path) -> None:
    print(f"  [{label}] {root.resolve()}")


def _print_write_result(title: str, result: WriteResult) -> None:
    print(f"  {title}:")
    if result.error:
        print(f"    error: {_preview(result.error, limit=120)}")
    else:
        print(f"    path: {result.path}")
        print(f"    files_update: {result.files_update}")


def _print_edit_result(title: str, result: EditResult) -> None:
    print(f"  {title}:")
    if result.error:
        print(f"    error: {_preview(result.error, limit=120)}")
    else:
        print(f"    path: {result.path}, occurrences: {result.occurrences}")


def _print_file_infos(label: str, items: list[dict[str, Any]]) -> None:
    print(f"  [{label}] 共 {len(items)} 项")
    for i, info in enumerate(items[:8]):
        path = info.get("path", "?")
        is_dir = info.get("is_dir", False)
        size = info.get("size", "-")
        print(f"    [{i}] path={path!r} is_dir={is_dir} size={size}")
    if len(items) > 8:
        print(f"    ... 其余 {len(items) - 8} 项略")


def _print_grep_matches(label: str, matches: list[dict[str, Any]] | str) -> None:
    if isinstance(matches, str):
        print(f"  [{label}] 字符串结果: {_preview(matches)}")
        return
    print(f"  [{label}] 命中 {len(matches)} 处")
    for i, m in enumerate(matches[:6]):
        print(f"    [{i}] {m.get('path')}:{m.get('line')}  {_preview(m.get('text', ''), limit=50)}")
    if len(matches) > 6:
        print(f"    ... 其余 {len(matches) - 6} 处略")


def _print_upload_responses(responses: list[FileUploadResponse]) -> None:
    print(f"  上传响应 {len(responses)} 条")
    for i, r in enumerate(responses):
        status = "ok" if r.error is None else r.error
        print(f"    [{i}] path={r.path!r}  status={status}")


def _print_download_responses(responses: list[FileDownloadResponse]) -> None:
    print(f"  下载响应 {len(responses)} 条")
    for i, r in enumerate(responses):
        if r.error:
            print(f"    [{i}] path={r.path!r}  error={r.error}")
        else:
            preview = r.content[:40] if r.content else b""
            print(f"    [{i}] path={r.path!r}  bytes={len(r.content or b'')}  preview={preview!r}")


def _seed_workspace(root: Path) -> None:
    """在临时根下创建可预测的目录树。"""
    (root / "notes.txt").write_text("alpha line\nbeta NEEDLE here\ngamma\n", encoding="utf-8")
    (root / "empty.txt").write_text("", encoding="utf-8")
    sub = root / "sub"
    sub.mkdir()
    (sub / "a.txt").write_text("hello from sub\n", encoding="utf-8")
    (sub / "b.py").write_text("print('NEEDLE in py')\n", encoding="utf-8")


@pytest.fixture
def virtual_root(tmp_path: Path) -> Path:
    root = tmp_path / "fs_root"
    root.mkdir()
    _seed_workspace(root)
    _step("fixture：虚拟模式临时根")
    _print_root("virtual_root", root)
    return root


@pytest.fixture
def virtual_backend(virtual_root: Path) -> FilesystemBackend:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return FilesystemBackend(root_dir=virtual_root, virtual_mode=True)


@pytest.fixture
def legacy_backend(virtual_root: Path) -> FilesystemBackend:
    return FilesystemBackend(root_dir=virtual_root, virtual_mode=False)


def test_virtual_write_read_edit(virtual_backend: FilesystemBackend, virtual_root: Path) -> None:
    """虚拟路径：写入新文件 → 带行号读取 → 单次替换编辑。"""
    backend = virtual_backend

    _step("write 新文件 /new/hello.txt")
    write_res = backend.write("/new/hello.txt", "line one\nline two\n")
    _print_write_result("write", write_res)
    assert write_res.error is None, write_res
    assert write_res.path == "/new/hello.txt"

    _step("read 前 2 行（带行号）")
    text = backend.read("/new/hello.txt", offset=0, limit=2)
    print(f"  read 预览:\n{_preview(text, limit=200)}")
    assert "line one" in text
    assert "\tline one" in text  # cat -n 风格：行号 + 制表符 + 正文

    _step("edit 替换 line two → line 2")
    edit_res = backend.edit("/new/hello.txt", "line two", "line 2")
    _print_edit_result("edit", edit_res)
    assert edit_res.error is None, edit_res
    assert edit_res.occurrences == 1

    after = (virtual_root / "new" / "hello.txt").read_text(encoding="utf-8")
    print(f"  磁盘内容: {_preview(after)}")
    assert "line 2" in after
    assert "line two" not in after
    print("  断言通过: 虚拟路径读写编辑一致")


def test_write_refuses_existing_file(virtual_backend: FilesystemBackend) -> None:
    _step("对已存在文件再次 write")
    res = virtual_backend.write("/notes.txt", "overwrite")
    _print_write_result("write", res)
    assert res.error is not None
    assert "already exists" in res.error
    print("  断言通过: 拒绝覆盖已有文件")


def test_read_not_found_and_offset(virtual_backend: FilesystemBackend) -> None:
    _step("read 不存在的路径")
    missing = virtual_backend.read("/no/such/file.txt")
    print(f"  结果: {_preview(missing)}")
    assert "not found" in missing.lower()

    _step("read offset 超出文件行数")
    over = virtual_backend.read("/notes.txt", offset=99, limit=10)
    print(f"  结果: {_preview(over)}")
    assert "exceeds file length" in over
    print("  断言通过: 缺失文件与越界 offset 返回明确错误")


def test_read_empty_file(virtual_backend: FilesystemBackend) -> None:
    _step("read 空文件")
    msg = virtual_backend.read("/empty.txt")
    print(f"  结果: {_preview(msg)}")
    assert msg == EMPTY_CONTENT_WARNING
    print("  断言通过: 空文件返回标准提醒文案")


def test_edit_ambiguous_without_replace_all(virtual_backend: FilesystemBackend) -> None:
    _step("edit 多处匹配且 replace_all=False")
    res = virtual_backend.edit("/notes.txt", "a", "X", replace_all=False)
    _print_edit_result("edit", res)
    assert res.error is not None
    print("  断言通过: 多匹配时要求 replace_all 或唯一匹配")


def test_edit_replace_all(virtual_backend: FilesystemBackend, virtual_root: Path) -> None:
    _step("edit replace_all 替换所有 NEEDLE")
    res = virtual_backend.edit("/notes.txt", "NEEDLE", "MARK", replace_all=True)
    _print_edit_result("edit", res)
    assert res.error is None, res
    assert res.occurrences is not None and res.occurrences >= 1
    content = (virtual_root / "notes.txt").read_text(encoding="utf-8")
    print(f"  更新后: {_preview(content)}")
    assert "NEEDLE" not in content
    assert "MARK" in content
    print("  断言通过: replace_all 生效")


def test_ls_info_virtual_paths(virtual_backend: FilesystemBackend) -> None:
    _step("ls_info 根目录 /")
    root_items = virtual_backend.ls_info("/")
    _print_file_infos("根目录", root_items)
    paths = {item["path"] for item in root_items}
    assert "/notes.txt" in paths
    dir_paths = [i["path"] for i in root_items if i.get("is_dir")]
    print(f"  子目录条目: {dir_paths}")
    assert "/sub/" in dir_paths

    _step("ls_info 子目录 /sub")
    sub_items = virtual_backend.ls_info("/sub")
    _print_file_infos("sub", sub_items)
    sub_paths = {i["path"] for i in sub_items}
    assert "/sub/a.txt" in sub_paths
    assert "/sub/b.py" in sub_paths
    print("  断言通过: 虚拟路径列表与种子数据一致")


def test_glob_info_virtual_mode(virtual_backend: FilesystemBackend) -> None:
    _step("glob **/*.txt")
    matches = virtual_backend.glob_info("**/*.txt", path="/")
    _print_file_infos("glob", matches)
    paths = {m["path"] for m in matches}
    assert "/notes.txt" in paths
    assert "/sub/a.txt" in paths
    print("  断言通过: glob 命中 txt 文件")


def test_grep_raw_literal(virtual_backend: FilesystemBackend) -> None:
    _step("grep_raw 字面量 NEEDLE")
    matches = virtual_backend.grep_raw("NEEDLE", path="/")
    _print_grep_matches("grep", matches)
    assert isinstance(matches, list)
    assert len(matches) >= 1
    texts = " ".join(m.get("text", "") for m in matches)
    assert "NEEDLE" in texts
    print("  断言通过: grep 至少一处命中 NEEDLE")


def test_upload_download_roundtrip(virtual_backend: FilesystemBackend, virtual_root: Path) -> None:
    _step("upload_files 二进制写入 /uploads/bin.dat")
    payload = b"\x00\x01hello"
    up = virtual_backend.upload_files([("/uploads/bin.dat", payload)])
    _print_upload_responses(up)
    assert up[0].error is None, up

    _step("download_files 读回")
    down = virtual_backend.download_files(["/uploads/bin.dat"])
    _print_download_responses(down)
    assert down[0].error is None, down
    assert down[0].content == payload

    on_disk = (virtual_root / "uploads" / "bin.dat").read_bytes()
    print(f"  磁盘字节数: {len(on_disk)}")
    assert on_disk == payload
    print("  断言通过: 上传下载往返一致")


def test_virtual_mode_blocks_traversal(virtual_backend: FilesystemBackend) -> None:
    _step("虚拟模式禁止 .. 路径")
    with pytest.raises(ValueError, match="traversal"):
        virtual_backend._resolve_path("/../etc/passwd")
    print("  _resolve_path(/../...) → ValueError")

    _step("upload 带 .. 的路径")
    bad = virtual_backend.upload_files([("/../escape.txt", b"x")])
    _print_upload_responses(bad)
    assert bad[0].error == "invalid_path"
    print("  断言通过: 路径穿越被拦截")


def test_glob_pattern_traversal_rejected(virtual_backend: FilesystemBackend) -> None:
    _step("glob 模式含 .. 应抛 ValueError")
    with pytest.raises(ValueError, match="traversal"):
        virtual_backend.glob_info("../**/*.txt", path="/")
    print("  断言通过: glob 模式穿越被拒绝")


def test_legacy_mode_absolute_and_relative(legacy_backend: FilesystemBackend, virtual_root: Path) -> None:
    """非虚拟模式：相对路径落在 root_dir 下，绝对路径按系统解析。"""
    _step("legacy write 相对路径 rel.txt")
    rel_path = "rel.txt"
    res = legacy_backend.write(rel_path, "legacy content\n")
    _print_write_result("write", res)
    assert res.error is None, res
    assert (virtual_root / "rel.txt").is_file()

    _step("legacy read 相对路径")
    text = legacy_backend.read(rel_path)
    print(f"  read: {_preview(text)}")
    assert "legacy content" in text

    _step("legacy ls_info 使用目录绝对路径")
    items = legacy_backend.ls_info(str(virtual_root))
    _print_file_infos("ls", items)
    abs_paths = {i["path"] for i in items}
    assert any("notes.txt" in p for p in abs_paths)
    print("  断言通过: legacy 模式相对/绝对路径可用")


def test_download_errors(virtual_backend: FilesystemBackend) -> None:
    _step("download 不存在 / 目录")
    responses = virtual_backend.download_files(["/missing.dat", "/sub"])
    _print_download_responses(responses)
    assert responses[0].error == "file_not_found"
    # Windows 上对目录 os.open 可能返回 permission_denied 而非 is_directory
    assert responses[1].error in ("is_directory", "permission_denied"), responses[1]
    print(f"  目录下载错误码: {responses[1].error}（平台相关）")
    print("  断言通过: 下载错误码符合预期")
