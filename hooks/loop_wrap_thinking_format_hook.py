from collections.abc import Iterator
from typing import Any, Callable

from agent.hook.schema import WrapLoopHook

_THINKING_OPEN = "<think>"
_THINKING_CLOSE = "</think>"

_DIM = "\033[2m"
_RESET = "\033[0m"
_GREEN = "\033[92m"


def _split_partial_tag(text: str, tag: str) -> tuple[str, str]:
    """将文本拆为可安全输出部分与可能构成标签前缀的尾部。"""
    for i in range(min(len(text), len(tag) - 1), 0, -1):
        if tag.startswith(text[-i:]):
            return text[:-i], text[-i:]
    return text, ""


def _thinking_frame_open() -> str:
    return f"{_RESET}\n{_DIM}╭ thinking start\n{_RESET}{_DIM}"


def _thinking_frame_close() -> str:
    return f"{_RESET}\n{_DIM}╰ thinking end{_RESET}{_GREEN}\n"


def _thinking_content(chunk: str) -> str:
    return f"{_DIM}{chunk}"


class _ThinkingStreamParser:
    """跨 chunk 解析 <think> 标签，无标签时原样透传。"""

    def __init__(self) -> None:
        self._buf = ""
        self._in_thinking = False
        self._thinking_opened = False

    def feed(self, chunk: str) -> list[str]:
        self._buf += chunk
        outputs: list[str] = []

        while self._buf:
            if not self._in_thinking:
                idx = self._buf.find(_THINKING_OPEN)
                if idx == -1:
                    safe, self._buf = _split_partial_tag(self._buf, _THINKING_OPEN)
                    if safe:
                        outputs.append(safe)
                    break

                before = self._buf[:idx]
                if before:
                    outputs.append(before)
                self._buf = self._buf[idx + len(_THINKING_OPEN) :]
                self._in_thinking = True
                self._thinking_opened = False
                continue

            idx = self._buf.find(_THINKING_CLOSE)
            if idx == -1:
                safe, self._buf = _split_partial_tag(self._buf, _THINKING_CLOSE)
                if safe:
                    if not self._thinking_opened:
                        outputs.append(_thinking_frame_open())
                        self._thinking_opened = True
                    outputs.append(_thinking_content(safe))
                break

            thinking_part = self._buf[:idx]
            if not self._thinking_opened:
                outputs.append(_thinking_frame_open())
                self._thinking_opened = True
            if thinking_part:
                outputs.append(_thinking_content(thinking_part))
            outputs.append(_thinking_frame_close())
            self._buf = self._buf[idx + len(_THINKING_CLOSE) :]
            self._in_thinking = False
            self._thinking_opened = False

        return outputs

    def flush(self) -> list[str]:
        if not self._buf:
            return []

        outputs: list[str] = []
        if self._in_thinking:
            if not self._thinking_opened:
                outputs.append(_thinking_frame_open())
            outputs.append(_thinking_content(self._buf))
            outputs.append(_thinking_frame_close())
        else:
            outputs.append(self._buf)

        self._buf = ""
        self._in_thinking = False
        self._thinking_opened = False
        return outputs


class LoopWrapThinkingFormatHook(WrapLoopHook):
    """将 <think> 内容框起来标注为思考，无标签时原样透传。"""

    def invoke(
        self,
        context: Any,
        call_next: Callable[[], Iterator[Any]],
    ) -> Iterator[Any]:
        parser = _ThinkingStreamParser()
        for ev in call_next():
            if ev.get("event") != "ai":
                yield ev
                continue

            data = ev.get("data")
            if not isinstance(data, str) or not data:
                yield ev
                continue

            for chunk in parser.feed(data):
                yield {"event": "ai", "data": chunk}

        for chunk in parser.flush():
            yield {"event": "ai", "data": chunk}
