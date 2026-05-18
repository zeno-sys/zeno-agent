"""BackendProtocol-backed file tools for the agent registry."""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any

from agent.tool.registry import registry
from backends.base import (
    DOWNLOAD_FILES_SCHEMA,
    EDIT_FILE_SCHEMA,
    BackendProtocol,
    FileDownloadResponse,
    FileUploadResponse,
    GLOB_FILES_SCHEMA,
    GREP_FILES_SCHEMA,
    LS_INFO_SCHEMA,
    READ_FILE_SCHEMA,
    UPLOAD_FILES_SCHEMA,
    WRITE_FILE_SCHEMA,
    EditResult,
    WriteResult,
)
from backends.filesystem import FilesystemBackend
from constants import get_workspace_path

logger = logging.getLogger(__name__)

BACKEND_FILE_TOOLSET = "backend_file"

_default_backend: BackendProtocol | None = None


def tool_error(message: str) -> str:
    return json.dumps({"error": message}, ensure_ascii=False)


def create_file_backend(
    root_dir: str | Path | None = None,
    *,
    virtual_mode: bool = True,
) -> BackendProtocol:
    """Create the default file backend (FilesystemBackend) for a session."""
    return FilesystemBackend(
        root_dir=root_dir if root_dir is not None else get_workspace_path(),
        virtual_mode=virtual_mode,
    )


def create_filesystem_backend(
    root_dir: str | Path | None = None,
    *,
    virtual_mode: bool = True,
) -> BackendProtocol:
    """Alias for :func:`create_file_backend` (default implementation)."""
    return create_file_backend(root_dir=root_dir, virtual_mode=virtual_mode)


def get_file_backend() -> BackendProtocol:
    """Return the process-wide default backend (lazy init fallback)."""
    global _default_backend
    if _default_backend is None:
        _default_backend = create_file_backend()
    return _default_backend


def get_filesystem_backend() -> BackendProtocol:
    """Alias for :func:`get_file_backend`."""
    return get_file_backend()


def set_file_backend(backend: BackendProtocol | None) -> None:
    """Override or clear the process-wide fallback backend (tests)."""
    global _default_backend
    _default_backend = backend


def set_filesystem_backend(backend: BackendProtocol | None) -> None:
    """Alias for :func:`set_file_backend`."""
    set_file_backend(backend)


def _backend_from_extra(extra_args: dict[str, Any]) -> BackendProtocol:
    injected = extra_args.get("filesystem_backend")
    if isinstance(injected, BackendProtocol):
        return injected
    return get_file_backend()


def _backend_error_text(text: str) -> bool:
    return text.startswith("Error") or text.startswith("error")


def _serialize_write(result: WriteResult) -> dict[str, Any]:
    return {k: v for k, v in asdict(result).items() if v is not None}


def _serialize_edit(result: EditResult) -> dict[str, Any]:
    return {k: v for k, v in asdict(result).items() if v is not None}


def _serialize_upload(responses: list[FileUploadResponse]) -> list[dict[str, Any]]:
    return [asdict(r) for r in responses]


def _serialize_download(responses: list[FileDownloadResponse]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in responses:
        item: dict[str, Any] = {"path": r.path, "error": r.error}
        if r.content is not None:
            item["content_base64"] = base64.b64encode(r.content).decode("ascii")
        else:
            item["content_base64"] = None
        out.append(item)
    return out


def _decode_upload_item(item: dict[str, Any]) -> tuple[str, bytes]:
    path = item.get("path", "")
    if not path or not isinstance(path, str):
        raise ValueError("Each file entry requires a string 'path'")
    content = item.get("content", "")
    if not isinstance(content, str):
        raise ValueError("'content' must be a string")
    encoding = item.get("content_encoding", "utf8")
    if encoding == "base64":
        return path, base64.b64decode(content, validate=True)
    if encoding == "utf8":
        return path, content.encode("utf-8")
    raise ValueError(f"Unsupported content_encoding: {encoding!r}")


def _handle_list_directory(args: dict[str, Any], extra_args: dict[str, Any]) -> str:
    path = args.get("path")
    if not path:
        return tool_error("list_directory: missing required field 'path'")
    backend = _backend_from_extra(extra_args)
    items = backend.ls_info(path)
    return json.dumps({"items": items}, ensure_ascii=False)


def _handle_read_file(args: dict[str, Any], extra_args: dict[str, Any]) -> str:
    file_path = args.get("file_path")
    if not file_path:
        return tool_error("read_file: missing required field 'file_path'")
    offset = int(args.get("offset", 0))
    limit = int(args.get("limit", 2000))
    backend = _backend_from_extra(extra_args)
    text = backend.read(file_path, offset=offset, limit=limit)
    if _backend_error_text(text):
        return tool_error(text)
    return json.dumps({"content": text}, ensure_ascii=False)


def _handle_grep_files(args: dict[str, Any], extra_args: dict[str, Any]) -> str:
    pattern = args.get("pattern")
    if not pattern:
        return tool_error("grep_files: missing required field 'pattern'")
    backend = _backend_from_extra(extra_args)
    result = backend.grep_raw(
        pattern,
        path=args.get("path"),
        glob=args.get("file_glob"),
    )
    if isinstance(result, str):
        return tool_error(result)
    return json.dumps({"matches": result}, ensure_ascii=False)


def _handle_glob_files(args: dict[str, Any], extra_args: dict[str, Any]) -> str:
    pattern = args.get("pattern")
    if not pattern:
        return tool_error("glob_files: missing required field 'pattern'")
    backend = _backend_from_extra(extra_args)
    items = backend.glob_info(pattern, path=args.get("path", "/"))
    return json.dumps({"items": items}, ensure_ascii=False)


def _handle_write_file(args: dict[str, Any], extra_args: dict[str, Any]) -> str:
    file_path = args.get("file_path")
    if not file_path:
        return tool_error("write_file: missing required field 'file_path'")
    if "content" not in args:
        return tool_error("write_file: missing required field 'content'")
    if not isinstance(args["content"], str):
        return tool_error(f"write_file: 'content' must be a string, got {type(args['content']).__name__}")
    backend = _backend_from_extra(extra_args)
    result = backend.write(file_path, args["content"])
    payload = _serialize_write(result)
    if result.error:
        return json.dumps({"ok": False, **payload}, ensure_ascii=False)
    return json.dumps({"ok": True, **payload}, ensure_ascii=False)


def _handle_edit_file(args: dict[str, Any], extra_args: dict[str, Any]) -> str:
    file_path = args.get("file_path")
    if not file_path:
        return tool_error("edit_file: missing required field 'file_path'")
    if "old_string" not in args or "new_string" not in args:
        return tool_error("edit_file: requires 'old_string' and 'new_string'")
    backend = _backend_from_extra(extra_args)
    result = backend.edit(
        file_path,
        args["old_string"],
        args["new_string"],
        replace_all=bool(args.get("replace_all", False)),
    )
    payload = _serialize_edit(result)
    if result.error:
        return json.dumps({"ok": False, **payload}, ensure_ascii=False)
    return json.dumps({"ok": True, **payload}, ensure_ascii=False)


def _handle_upload_files(args: dict[str, Any], extra_args: dict[str, Any]) -> str:
    raw_files = args.get("files")
    if not raw_files or not isinstance(raw_files, list):
        return tool_error("upload_files: missing required field 'files' (non-empty array)")
    try:
        files = [_decode_upload_item(item) for item in raw_files]
    except (ValueError, TypeError) as e:
        return tool_error(f"upload_files: {e}")
    backend = _backend_from_extra(extra_args)
    responses = backend.upload_files(files)
    return json.dumps({"results": _serialize_upload(responses)}, ensure_ascii=False)


def _handle_download_files(args: dict[str, Any], extra_args: dict[str, Any]) -> str:
    paths = args.get("paths")
    if not paths or not isinstance(paths, list):
        return tool_error("download_files: missing required field 'paths' (non-empty array)")
    backend = _backend_from_extra(extra_args)
    responses = backend.download_files(paths)
    return json.dumps({"results": _serialize_download(responses)}, ensure_ascii=False)


_BACKEND_TOOL_SPECS: list[tuple[dict[str, Any], Any, str]] = [
    (LS_INFO_SCHEMA, _handle_list_directory, "📂"),
    (READ_FILE_SCHEMA, _handle_read_file, "📖"),
    (GREP_FILES_SCHEMA, _handle_grep_files, "🔍"),
    (GLOB_FILES_SCHEMA, _handle_glob_files, "📁"),
    (WRITE_FILE_SCHEMA, _handle_write_file, "✍️"),
    (EDIT_FILE_SCHEMA, _handle_edit_file, "🔧"),
    (UPLOAD_FILES_SCHEMA, _handle_upload_files, "⬆️"),
    (DOWNLOAD_FILES_SCHEMA, _handle_download_files, "⬇️"),
]


def register_backend_file_tools() -> None:
    """Register BackendProtocol file tools on the global registry."""
    for schema, handler, emoji in _BACKEND_TOOL_SPECS:
        name = schema["name"]
        registry.register(
            name=name,
            toolset=BACKEND_FILE_TOOLSET,
            schema=schema,
            handler=handler,
            emoji=emoji,
            max_result_size_chars=100_000 if name == "read_file" else None,
        )
    logger.debug("Registered %d backend file tools", len(_BACKEND_TOOL_SPECS))
