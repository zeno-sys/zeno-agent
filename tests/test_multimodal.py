"""Tests for multimodal user content helpers."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from agent.command.command_resolver import resolve_user_input
from agent.core.multimodal import (
    build_openai_user_content,
    content_to_text,
    is_openai_multimodal_content,
    load_image_as_data_url,
    merge_openai_content,
    parse_image_attachments,
    sanitize_message_for_log,
)
from agent.core.user_input import UserInput, user_input_to_message
from utils.normalize_messages import normalize_messages_openai


def test_content_to_text_from_parts() -> None:
    parts = [
        {"type": "text", "text": "hello"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
    ]
    assert content_to_text(parts) == "hello"


def test_build_openai_user_content_text_only() -> None:
    assert build_openai_user_content("hi", ()) == "hi"


def test_build_openai_user_content_with_image(tmp_path: Path) -> None:
    img = tmp_path / "a.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    content = build_openai_user_content("describe", [img])
    assert isinstance(content, list)
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_load_image_rejects_when_compression_impossible(
    tmp_path: Path, monkeypatch
) -> None:
    from PIL import Image

    monkeypatch.setenv("MULTIMODAL_MAX_IMAGE_BYTES", "1")
    img = tmp_path / "big.png"
    Image.new("RGB", (128, 128), color=(9, 9, 9)).save(img, format="PNG")
    with pytest.raises(ValueError, match="压缩后仍超过上限"):
        load_image_as_data_url(img)


def test_parse_image_attachments(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    img = tmp_path / "pic.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    text, paths = parse_image_attachments(f"看看 @image {img.name}")
    assert text == "看看"
    assert len(paths) == 1
    assert paths[0].resolve() == img.resolve()


def test_parse_image_windows_path_with_spaces(tmp_path: Path) -> None:
    nested = tmp_path / "Saved Pictures"
    nested.mkdir()
    img = nested / "DSC00103.JPG"
    img.write_bytes(b"\xff\xd8\xff\xd9")
    win_path = str(img).replace("/", "\\")
    text, paths = parse_image_attachments(f"分析 @image {win_path}")
    assert text == "分析"
    assert len(paths) == 1
    assert paths[0].resolve() == img.resolve()


def test_parse_image_quoted_path_with_spaces(tmp_path: Path) -> None:
    nested = tmp_path / "my photos"
    nested.mkdir()
    img = nested / "a.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    text, paths = parse_image_attachments(f'看 @image "{img}"')
    assert text == "看"
    assert paths[0].resolve() == img.resolve()


def test_resolve_user_input_strips_image_tokens(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    img = tmp_path / "x.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    resolved = resolve_user_input(f"问题 @image {img.name}")
    assert resolved.content == "问题"
    assert len(resolved.image_paths) == 1


def test_user_input_to_message(tmp_path: Path) -> None:
    img = tmp_path / "z.webp"
    img.write_bytes(b"RIFF")
    msg = user_input_to_message(UserInput(text="q", image_paths=(img,)))
    assert msg["role"] == "user"
    assert isinstance(msg["content"], list)


def test_normalize_preserves_multimodal_list() -> None:
    parts = [
        {"type": "text", "text": "see"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA=="}},
    ]
    out = normalize_messages_openai([{"role": "user", "content": parts}])
    assert is_openai_multimodal_content(out[0]["content"])
    assert out[0]["content"][1]["image_url"]["url"].startswith("data:image/png")


def test_normalize_merges_str_and_multimodal_user() -> None:
    parts = [
        {"type": "text", "text": "second"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA=="}},
    ]
    out = normalize_messages_openai(
        [
            {"role": "user", "content": "first"},
            {"role": "user", "content": parts},
        ]
    )
    assert len(out) == 1
    merged = out[0]["content"]
    assert isinstance(merged, list)
    assert "first" in merged[0]["text"]
    assert "second" in content_to_text(merged)


def test_merge_openai_content_strings() -> None:
    assert merge_openai_content("a", "b") == "a\nb"


def test_sanitize_message_for_log() -> None:
    msg = {
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + "A" * 100}},
        ],
    }
    safe = sanitize_message_for_log(msg)
    assert "<base64 truncated>" in safe["content"][0]["image_url"]["url"]
