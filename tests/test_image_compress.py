"""Tests for utils.image_compress."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from utils.image_compress import read_image_bytes_for_upload


def _make_large_jpeg(path: Path, size: tuple[int, int] = (2400, 1800)) -> None:
    img = Image.new("RGB", size, color=(120, 80, 200))
    img.save(path, format="JPEG", quality=95)


def test_read_image_passthrough_small_file(tmp_path: Path) -> None:
    img = tmp_path / "small.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    result = read_image_bytes_for_upload(img, max_bytes=10_000)
    assert not result.compressed
    assert result.mime == "image/png"
    assert result.original_bytes == img.stat().st_size


def test_read_image_compresses_oversized_jpeg(tmp_path: Path) -> None:
    img = tmp_path / "large.jpg"
    _make_large_jpeg(img)
    assert img.stat().st_size > 50_000
    result = read_image_bytes_for_upload(img, max_bytes=50_000)
    assert result.compressed
    assert result.mime == "image/jpeg"
    assert len(result.data) <= 50_000
    assert result.original_bytes == img.stat().st_size


def test_read_image_compress_via_multimodal_loader(
    tmp_path: Path, monkeypatch
) -> None:
    from agent.core.multimodal import load_image_as_data_url

    monkeypatch.setenv("MULTIMODAL_MAX_IMAGE_BYTES", "40000")
    img = tmp_path / "big.jpg"
    _make_large_jpeg(img, size=(3200, 2400))
    assert img.stat().st_size > 40_000
    url = load_image_as_data_url(img)
    assert url.startswith("data:image/")
    assert len(url) < img.stat().st_size * 2


def test_read_image_fails_when_limit_impossible(tmp_path: Path) -> None:
    img = tmp_path / "tiny.png"
    Image.new("RGB", (64, 64), color=(1, 2, 3)).save(img, format="PNG")
    with pytest.raises(ValueError, match="压缩后仍超过上限"):
        read_image_bytes_for_upload(img, max_bytes=1)
