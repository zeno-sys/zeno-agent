from __future__ import annotations

from typing import Any, Iterator, Literal, TypedDict

RunEvent = dict[str, Any]


class AIMessageEvent(TypedDict):
    event: Literal["ai"]
    data: str


class ToolCallData(TypedDict):
    tool_call_id: str
    tool_name: str
    tool_input: dict[str, Any]


class ToolCallEvent(TypedDict):
    event: Literal["tool_call"]
    data: ToolCallData


class ToolResultData(TypedDict):
    tool_call_id: str
    tool_name: str
    tool_result: str


class ToolResultEvent(TypedDict):
    event: Literal["tool_result"]
    data: ToolResultData


def send_ai_message(content: str) -> Iterator[RunEvent]:
    """流式或整块助手文本片段（通常每个 chunk 为模型输出的一个 token）。"""
    yield AIMessageEvent(event="ai", data=content)


def send_tool_call(tool_call_id: str, tool_name: str, tool_input: dict[str, Any]) -> Iterator[RunEvent]:
    yield ToolCallEvent(
        event="tool_call",
        data=ToolCallData(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            tool_input=tool_input,
        ),
    )


def send_tool_result(tool_call_id: str, tool_name: str, result: str) -> Iterator[RunEvent]:
    yield ToolResultEvent(
        event="tool_result",
        data=ToolResultData(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            tool_result=result,
        ),
    )
