import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Callable

from agent.core.multimodal import sanitize_messages_for_log
from agent.hook.schema import WrapModelCallHook


def _jsonable_chunk(chunk: Any) -> Any:
    if hasattr(chunk, "model_dump"):
        return chunk.model_dump()
    return str(chunk)


class ModelRawIOLogHook(WrapModelCallHook):
    """记录模型请求与流式 chunk 到 ``data/logs/model_io``（与 WrapLoop 一致：透传迭代器）。"""

    def invoke(
        self,
        context: Any,
        *,
        call_next: Callable[
            [list[dict[str, Any]], list[dict[str, Any]]],
            Iterator[Any],
        ],
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> Iterator[Any]:
        session_id = str(getattr(context, "session_id", None) or "unknown_session")
        state = context.state

        logs_dir = Path("data/logs/model_io") / session_id
        logs_dir.mkdir(parents=True, exist_ok=True)

        ts = time.strftime("%Y%m%d_%H%M%S")
        millis = int((time.time() % 1) * 1000)
        base_name = f"model_raw_{ts}_{millis:03d}"

        input_path = logs_dir / f"{base_name}_input.json"
        output_path = logs_dir / f"{base_name}_output_chunks.jsonl"

        input_payload = {
            "messages": sanitize_messages_for_log(messages),
            "tools": tools,
            "session_id": getattr(context, "session_id", None),
            "turn_count": getattr(state, "turn_count", None),
            "timestamp": ts,
        }
        input_path.write_text(
            json.dumps(input_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        chunks: list[Any] = []
        try:
            for chunk in call_next(messages, tools):
                chunks.append(chunk)
                yield chunk
        finally:
            with output_path.open("w", encoding="utf-8") as fp:
                for ch in chunks:
                    fp.write(json.dumps(_jsonable_chunk(ch), ensure_ascii=False))
                    fp.write("\n")
