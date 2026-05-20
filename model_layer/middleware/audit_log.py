from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from model_layer.middleware.base import ModelMiddleware
from model_layer.types import ModelRequest, ModelResponse, ResolvedRoute


def _jsonable_chunk(chunk: Any) -> Any:
    if hasattr(chunk, "model_dump"):
        return chunk.model_dump()
    return str(chunk)


class AuditLogMiddleware(ModelMiddleware):
    """Optional file audit log (similar to ModelRawIOLogHook)."""

    def __init__(self, logs_root: str | Path = "data/logs/model_layer") -> None:
        self._logs_root = Path(logs_root)

    def wrap_complete(
        self,
        req: ModelRequest,
        route: ResolvedRoute,
        call_next: Callable[[], ModelResponse],
    ) -> ModelResponse:
        session_id = str(req.metadata.get("session_id") or "unknown_session")
        logs_dir = self._logs_root / session_id
        logs_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        (logs_dir / f"complete_{ts}_{req.task}_input.json").write_text(
            json.dumps(
                {"task": req.task, "model": route.model, "messages": req.messages},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        resp = call_next()
        (logs_dir / f"complete_{ts}_{req.task}_output.json").write_text(
            json.dumps(
                _jsonable_chunk(resp.raw) if hasattr(resp.raw, "model_dump") else str(resp.raw),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return resp

    def wrap_stream(
        self,
        req: ModelRequest,
        route: ResolvedRoute,
        call_next: Callable[[], Iterator[Any]],
    ) -> Iterator[Any]:
        session_id = str(req.metadata.get("session_id") or "unknown_session")
        logs_dir = self._logs_root / session_id
        logs_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        millis = int((time.time() % 1) * 1000)
        base = f"stream_{ts}_{millis:03d}_{req.task}"
        (logs_dir / f"{base}_input.json").write_text(
            json.dumps(
                {
                    "task": req.task,
                    "model": route.model,
                    "messages": req.messages,
                    "tools": req.tools,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        out_path = logs_dir / f"{base}_chunks.jsonl"
        chunks: list[Any] = []
        try:
            for chunk in call_next():
                chunks.append(chunk)
                yield chunk
        finally:
            with out_path.open("w", encoding="utf-8") as fp:
                for ch in chunks:
                    fp.write(json.dumps(_jsonable_chunk(ch), ensure_ascii=False))
                    fp.write("\n")
