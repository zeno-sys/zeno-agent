"""OpenAI-compatible multimodal (image) helpers for user messages."""

from __future__ import annotations

import base64
import os
import re
from pathlib import Path
from typing import Any, Sequence

from constants import get_workspace_path
from utils.image_compress import read_image_bytes_for_upload

SUPPORTED_IMAGE_MIME: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

_IMAGE_TOKEN_RE = re.compile(r"@image\s+", re.IGNORECASE)

_DEFAULT_MAX_IMAGE_BYTES = 4 * 1024 * 1024
_DEFAULT_MAX_IMAGES_PER_TURN = 4


class ImageAttachmentParseError(ValueError):
    """User-facing failure when parsing ``@image`` attachments."""


def max_image_bytes() -> int:
    raw = os.getenv("MULTIMODAL_MAX_IMAGE_BYTES", "").strip()
    if not raw:
        return _DEFAULT_MAX_IMAGE_BYTES
    try:
        return max(1, int(raw))
    except ValueError:
        return _DEFAULT_MAX_IMAGE_BYTES


def max_images_per_turn() -> int:
    raw = os.getenv("MULTIMODAL_MAX_IMAGES_PER_TURN", "").strip()
    if not raw:
        return _DEFAULT_MAX_IMAGES_PER_TURN
    try:
        return max(1, int(raw))
    except ValueError:
        return _DEFAULT_MAX_IMAGES_PER_TURN


def mime_for_image_path(path: Path) -> str | None:
    return SUPPORTED_IMAGE_MIME.get(path.suffix.lower())


def resolve_image_path(raw: str, *, base_dir: Path | None = None) -> Path:
    """Resolve a user-supplied path relative to workspace (then cwd)."""
    p = Path(raw.strip().strip('"').strip("'"))
    if p.is_absolute():
        return p.resolve()
    root = base_dir if base_dir is not None else get_workspace_path()
    candidate = (root / p).resolve()
    if candidate.exists():
        return candidate
    return (Path.cwd() / p).resolve()


def load_image_as_data_url(path: Path) -> str:
    mime = mime_for_image_path(path)
    if mime is None:
        raise ValueError(f"不支持的图片格式: {path.suffix or '(无扩展名)'}")
    payload = read_image_bytes_for_upload(
        path, max_bytes=max_image_bytes(), mime=mime
    )
    data = base64.standard_b64encode(payload.data).decode("ascii")
    return f"data:{payload.mime};base64,{data}"


def image_url_part(data_url: str) -> dict[str, Any]:
    return {"type": "image_url", "image_url": {"url": data_url}}


def text_part(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def is_openai_content_part(block: Any) -> bool:
    if not isinstance(block, dict):
        return False
    kind = block.get("type")
    if kind == "text":
        return isinstance(block.get("text"), str)
    if kind == "image_url":
        url = (block.get("image_url") or {}).get("url")
        return isinstance(url, str) and bool(url)
    return False


def is_openai_multimodal_content(content: Any) -> bool:
    if not isinstance(content, list):
        return False
    if not content:
        return False
    return all(is_openai_content_part(p) for p in content)


def content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and "text" in block:
                parts.append(str(block["text"]))
            elif "text" in block:
                parts.append(str(block["text"]))
        return "\n".join(parts)
    if content is None:
        return ""
    return str(content)


def build_openai_user_content(
    text: str,
    image_paths: Sequence[Path] = (),
) -> str | list[dict[str, Any]]:
    paths = list(image_paths)
    if not paths:
        return text
    if len(paths) > max_images_per_turn():
        raise ValueError(
            f"单轮最多附带 {max_images_per_turn()} 张图片，当前 {len(paths)} 张"
        )
    parts: list[dict[str, Any]] = []
    if text.strip():
        parts.append(text_part(text))
    for path in paths:
        parts.append(image_url_part(load_image_as_data_url(path)))
    if not parts:
        return text
    if len(parts) == 1 and parts[0].get("type") == "text":
        return str(parts[0]["text"])
    return parts


def mcp_content_blocks_to_openai_parts(blocks: Sequence[Any]) -> list[dict[str, Any]]:
    """Convert MCP sampling content blocks to OpenAI multimodal parts."""
    parts: list[dict[str, Any]] = []
    for block in blocks:
        if hasattr(block, "text"):
            parts.append(text_part(block.text))
        elif hasattr(block, "data") and hasattr(block, "mimeType"):
            parts.append(
                image_url_part(f"data:{block.mimeType};base64,{block.data}")
            )
    return parts


def merge_openai_content(
    prev: Any,
    curr: Any,
) -> str | list[dict[str, Any]]:
    """Merge two user/assistant contents for normalize_messages (text before images)."""
    prev_parts = _content_as_parts(prev)
    curr_parts = _content_as_parts(curr)
    merged = _merge_parts(prev_parts, curr_parts)
    if len(merged) == 1 and merged[0].get("type") == "text":
        return str(merged[0]["text"])
    if not merged:
        return ""
    if all(p.get("type") == "text" for p in merged):
        return "\n".join(str(p["text"]) for p in merged)
    return merged


def _content_as_parts(content: Any) -> list[dict[str, Any]]:
    if isinstance(content, str):
        return [text_part(content)] if content else []
    if isinstance(content, list) and is_openai_multimodal_content(content):
        return list(content)
    if content is None:
        return []
    return [text_part(str(content))]


def _merge_parts(
    prev: list[dict[str, Any]],
    curr: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not prev:
        return list(curr)
    if not curr:
        return list(prev)

    out = list(prev)
    for block in curr:
        if block.get("type") == "text" and out and out[-1].get("type") == "text":
            out[-1] = text_part(f"{out[-1]['text']}\n{block['text']}")
        else:
            out.append(block)
    return out


def _parse_quoted_path_segment(rest: str, start: int) -> tuple[str, int]:
    quote = rest[start]
    if quote not in ('"', "'"):
        raise ValueError("内部错误: 期望引号路径")
    i = start + 1
    chars: list[str] = []
    while i < len(rest):
        ch = rest[i]
        if ch == quote:
            return "".join(chars), i + 1
        # Only escape the closing quote; keep Windows backslashes (e.g. C:\Users\...)
        if ch == "\\" and i + 1 < len(rest) and rest[i + 1] == quote:
            chars.append(rest[i + 1])
            i += 2
            continue
        chars.append(ch)
        i += 1
    raise ImageAttachmentParseError("@image 路径引号未闭合")


def _is_resolved_image_file(path: Path) -> bool:
    return path.is_file() and mime_for_image_path(path) is not None


def _parse_path_segment_greedy(
    rest: str,
    start: int,
    *,
    base_dir: Path | None,
) -> tuple[str, int] | None:
    """Parse one path after ``@image``; supports spaces (e.g. Windows ``Saved Pictures``).

    Returns ``None`` when the segment is not a resolvable image path (e.g. trailing user text).
    """
    if start >= len(rest):
        return None

    if rest[start] in ('"', "'"):
        raw, end = _parse_quoted_path_segment(rest, start)
        resolved = resolve_image_path(raw, base_dir=base_dir)
        if not _is_resolved_image_file(resolved):
            raise ImageAttachmentParseError(f"图片不存在或格式不支持: {raw}")
        return raw, end

    tail = rest[start:]
    end_candidates = [len(tail)]
    for j, ch in enumerate(tail):
        if ch in " \t":
            end_candidates.append(j)
        elif ch == "@" and j > 0:
            end_candidates.append(j)
            break

    for end in sorted(set(end_candidates), reverse=True):
        candidate = tail[:end].strip()
        if not candidate:
            continue
        resolved = resolve_image_path(candidate, base_dir=base_dir)
        if _is_resolved_image_file(resolved):
            return candidate, start + end

    m = re.match(r"[^\s@]+", tail)
    if m:
        raw = m.group(0)
        resolved = resolve_image_path(raw, base_dir=base_dir)
        if _is_resolved_image_file(resolved):
            return raw, start + m.end()

    return None


def _extract_image_path_strings(
    rest: str,
    *,
    base_dir: Path | None,
) -> tuple[list[str], int]:
    """Return raw path strings and number of characters consumed from ``rest``."""
    paths: list[str] = []
    pos = 0
    n = len(rest)
    while pos < n:
        while pos < n and rest[pos] in " \t":
            pos += 1
        if pos >= n or rest[pos] == "@":
            break
        parsed = _parse_path_segment_greedy(rest, pos, base_dir=base_dir)
        if parsed is None:
            break
        raw, pos = parsed
        paths.append(raw)
    return paths, pos


_IMAGE_PATH_HINT = (
    "无法识别 @image 后的图片路径。请提供存在的 PNG/JPEG/WebP/GIF 文件；"
    '路径含空格时请用引号包裹，例如 @image "C:\\my photos\\a.png"'
)


def parse_image_attachments(
    text: str,
    *,
    base_dir: Path | None = None,
) -> tuple[str, tuple[Path, ...]]:
    """Extract ``@image path ...`` tokens; return cleaned text and resolved paths."""
    if not _IMAGE_TOKEN_RE.search(text):
        return text, ()

    image_paths: list[Path] = []
    segments: list[str] = []
    pos = 0
    for match in _IMAGE_TOKEN_RE.finditer(text):
        segments.append(text[pos : match.start()])
        rest = text[match.end() :]
        raw_paths, consumed = _extract_image_path_strings(rest, base_dir=base_dir)
        if not raw_paths:
            raise ImageAttachmentParseError(_IMAGE_PATH_HINT)
        for raw in raw_paths:
            image_paths.append(resolve_image_path(raw, base_dir=base_dir))
        pos = match.end() + consumed

    segments.append(text[pos:])
    cleaned = "".join(segments).strip()
    if len(image_paths) > max_images_per_turn():
        raise ValueError(
            f"单轮最多附带 {max_images_per_turn()} 张图片，当前 {len(image_paths)} 张"
        )
    return cleaned, tuple(image_paths)


def validate_image_paths(paths: Sequence[Path]) -> list[str]:
    """Validate attachments; return user-facing notes (e.g. auto-compression)."""
    notes: list[str] = []
    for path in paths:
        mime = mime_for_image_path(path)
        if mime is None:
            raise ValueError(f"不支持的图片格式: {path.suffix or '(无扩展名)'}")
        result = read_image_bytes_for_upload(
            path, max_bytes=max_image_bytes(), mime=mime
        )
        if result.compressed:
            notes.append(
                f"图片已自动压缩: {path.name} "
                f"({result.original_bytes} → {len(result.data)} bytes)"
            )
    return notes


def sanitize_message_for_log(msg: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with truncated data URLs in content (for model_io logs)."""
    out = dict(msg)
    if "content" not in out:
        return out
    content = out["content"]
    if isinstance(content, list):
        out["content"] = [_sanitize_part(p) for p in content]
    return out


def sanitize_messages_for_log(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [sanitize_message_for_log(m) for m in messages]


def _sanitize_part(part: Any) -> Any:
    if not isinstance(part, dict):
        return part
    if part.get("type") != "image_url":
        return part
    url = (part.get("image_url") or {}).get("url", "")
    if not isinstance(url, str) or not url.startswith("data:"):
        return part
    head, _, _ = url.partition(",")
    return {
        "type": "image_url",
        "image_url": {"url": f"{head},<base64 truncated>"},
    }
