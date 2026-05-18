"""将本地图片压缩到指定体积上限，供多模态上传（base64 data URL）使用。

支持格式：PNG、JPEG、WebP、GIF（动图仅取首帧再压缩）。

主要 API
--------
- :func:`read_image_bytes_for_upload` — 读取文件；超过 ``max_bytes`` 时自动缩放/重编码
- :func:`max_image_dimension` — 读取压缩时最长边上限（环境变量）
- :class:`ImageBytesResult` — 返回体：``data``、``mime``、``compressed``、``original_bytes``

环境变量（可选）
----------------
- ``MULTIMODAL_MAX_IMAGE_DIMENSION`` — 压缩时最长边像素，默认 4096
- 体积上限由调用方传入（CLI/多模态侧通常用 ``MULTIMODAL_MAX_IMAGE_BYTES``，默认 4MB）

框架内用法
----------
``agent.core.multimodal.load_image_as_data_url`` 与 ``validate_image_paths`` 已调用本模块；
同一轮校验与建消息会命中 LRU 缓存，不会对同一张图重复压缩。

独立调用示例
------------
::

    from pathlib import Path

    from utils.image_compress import read_image_bytes_for_upload

    path = Path("photo.jpg")
    result = read_image_bytes_for_upload(path, max_bytes=4 * 1024 * 1024)

    if result.compressed:
        print(
            f"已压缩 {path.name}: "
            f"{result.original_bytes} → {len(result.data)} bytes, mime={result.mime}"
        )

    # 拼 OpenAI 风格 data URL
    import base64

    b64 = base64.standard_b64encode(result.data).decode("ascii")
    data_url = f"data:{result.mime};base64,{b64}"
"""

from __future__ import annotations

import functools
import io
import os
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps

# MIME suffix -> (PIL format name, default output MIME when re-encoding)
_FORMAT_BY_SUFFIX: dict[str, tuple[str, str]] = {
    ".png": ("PNG", "image/png"),
    ".jpg": ("JPEG", "image/jpeg"),
    ".jpeg": ("JPEG", "image/jpeg"),
    ".webp": ("WEBP", "image/webp"),
    ".gif": ("GIF", "image/gif"),
}

_DEFAULT_MAX_DIMENSION = 4096


@dataclass(frozen=True, slots=True)
class ImageBytesResult:
    data: bytes
    mime: str
    compressed: bool
    original_bytes: int


def max_image_dimension() -> int:
    raw = os.getenv("MULTIMODAL_MAX_IMAGE_DIMENSION", "").strip()
    if not raw:
        return _DEFAULT_MAX_DIMENSION
    try:
        return max(64, int(raw))
    except ValueError:
        return _DEFAULT_MAX_DIMENSION


def read_image_bytes_for_upload(
    path: Path,
    *,
    max_bytes: int,
    mime: str | None = None,
) -> ImageBytesResult:
    """Read image bytes, compressing when ``path`` exceeds ``max_bytes``.

    Args:
        path: Local image file.
        max_bytes: Maximum allowed payload size in bytes.
        mime: Optional MIME (e.g. ``image/jpeg``); inferred from suffix when omitted.

    Raises:
        FileNotFoundError: Path is not a file.
        ValueError: Unsupported format or cannot compress under ``max_bytes``.
    """
    if not path.is_file():
        raise FileNotFoundError(f"图片不存在: {path}")

    out_mime = mime or _mime_from_path(path)
    if out_mime is None:
        raise ValueError(f"不支持的图片格式: {path.suffix or '(无扩展名)'}")

    st = path.stat()
    return _read_image_bytes_cached(
        str(path.resolve()),
        st.st_mtime_ns,
        st.st_size,
        max_bytes,
        out_mime,
    )


@functools.lru_cache(maxsize=32)
def _read_image_bytes_cached(
    path_str: str,
    mtime_ns: int,
    file_size: int,
    max_bytes: int,
    mime: str,
) -> ImageBytesResult:
    path = Path(path_str)
    original = path.read_bytes()
    original_size = len(original)
    if original_size <= max_bytes:
        return ImageBytesResult(
            data=original,
            mime=mime,
            compressed=False,
            original_bytes=original_size,
        )

    suffix = path.suffix.lower()
    if suffix not in _FORMAT_BY_SUFFIX:
        raise ValueError(f"不支持的图片格式: {path.suffix or '(无扩展名)'}")

    compressed_data, out_mime = _compress_image_bytes(
        original,
        suffix=suffix,
        max_bytes=max_bytes,
    )
    return ImageBytesResult(
        data=compressed_data,
        mime=out_mime,
        compressed=True,
        original_bytes=original_size,
    )


def _mime_from_path(path: Path) -> str | None:
    entry = _FORMAT_BY_SUFFIX.get(path.suffix.lower())
    return entry[1] if entry else None


def _compress_image_bytes(
    raw: bytes,
    *,
    suffix: str,
    max_bytes: int,
) -> tuple[bytes, str]:
    img = Image.open(io.BytesIO(raw))
    img = ImageOps.exif_transpose(img)

    if suffix == ".gif" and getattr(img, "n_frames", 1) > 1:
        img.seek(0)

    max_dim = max_image_dimension()
    w, h = img.size
    scale = min(1.0, max_dim / max(w, h, 1))

    for _ in range(24):
        working = _resize(img, scale)
        for data, mime in _encode_candidates(working, suffix):
            if len(data) <= max_bytes:
                return data, mime
        scale *= 0.75
        if scale < 0.05:
            break

    raise ValueError(
        f"图片压缩后仍超过上限 ({max_bytes} bytes)，请换更小分辨率或提高 "
        f"MULTIMODAL_MAX_IMAGE_BYTES"
    )


def _resize(img: Image.Image, scale: float) -> Image.Image:
    if scale >= 0.999:
        return img.copy()
    w, h = img.size
    nw = max(1, int(w * scale))
    nh = max(1, int(h * scale))
    return img.resize((nw, nh), Image.Resampling.LANCZOS)


def _encode_candidates(
    img: Image.Image,
    suffix: str,
) -> list[tuple[bytes, str]]:
    """Try encodings from lossless-ish to smaller lossy variants."""
    out: list[tuple[bytes, str]] = []

    if suffix == ".png":
        out.append(_save_png(img))
        out.append(_save_webp(img, quality=80))
        out.extend(_save_jpeg_variants(_to_rgb(img)))
        return out

    if suffix in (".jpg", ".jpeg"):
        out.extend(_save_jpeg_variants(_to_rgb(img)))
        return out

    if suffix == ".webp":
        for q in (85, 70, 55, 40):
            out.append(_save_webp(img, quality=q))
        out.extend(_save_jpeg_variants(_to_rgb(img)))
        return out

    if suffix == ".gif":
        out.append(_save_gif(img))
        out.extend(_save_jpeg_variants(_to_rgb(img)))
        return out

    out.extend(_save_jpeg_variants(_to_rgb(img)))
    return out


def _to_rgb(img: Image.Image) -> Image.Image:
    if img.mode == "RGB":
        return img
    if img.mode in ("RGBA", "LA") or (
        img.mode == "P" and "transparency" in img.info
    ):
        base = Image.new("RGB", img.size, (255, 255, 255))
        rgba = img.convert("RGBA")
        base.paste(rgba, mask=rgba.split()[-1])
        return base
    if img.mode == "P":
        return img.convert("RGB")
    return img.convert("RGB")


def _save_png(img: Image.Image) -> tuple[bytes, str]:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue(), "image/png"


def _save_webp(img: Image.Image, *, quality: int) -> tuple[bytes, str]:
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=quality, method=4)
    return buf.getvalue(), "image/webp"


def _save_gif(img: Image.Image) -> tuple[bytes, str]:
    buf = io.BytesIO()
    frame = img.convert("P", palette=Image.Palette.ADAPTIVE, colors=256)
    frame.save(buf, format="GIF", optimize=True)
    return buf.getvalue(), "image/gif"


def _save_jpeg_variants(rgb: Image.Image) -> list[tuple[bytes, str]]:
    variants: list[tuple[bytes, str]] = []
    for quality in (85, 75, 65, 55, 45, 35, 25):
        buf = io.BytesIO()
        rgb.save(buf, format="JPEG", quality=quality, optimize=True)
        variants.append((buf.getvalue(), "image/jpeg"))
    return variants
