from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# Task names used by ModelRouter
TASK_AGENT = "agent"
TASK_AUXILIARY = "auxiliary"
TASK_STRUCTURED = "structured"

# Aliases mapped to auxiliary in router
TASK_ALIASES: dict[str, str] = {
    "title_generation": TASK_AUXILIARY,
}


@dataclass
class ModelRequest:
    '''提供商无关的模型调用请求,用于封装模型调用请求的参数
    
    task: 任务名称,用于根据任务名称选择模型和提供商
    messages: 消息列表
    model: 模型名称
    tools: 工具列表
    stream: 是否流式
    max_tokens: 最大令牌数
    temperature: 温度
    response_format: 响应格式
    metadata: 元数据，用于传递额外信息，最终会合并到extra_body中
    '''

    task: str
    messages: list[dict[str, Any]]
    model: str | None = None
    tools: list[dict[str, Any]] | None = None
    stream: bool = False
    max_tokens: int | None = None
    temperature: float | None = None
    response_format: Any | None = None  # Pydantic model class for structured output
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResolvedRoute:
    """Output of ModelRouter.resolve — concrete provider + API kwargs."""

    provider_id: str
    model: str
    extra_body: dict[str, Any] = field(default_factory=dict)
    include_stream_usage: bool = False


@dataclass
class ModelResponse:
    '''非流式完成结果，封装OpenAI SDK响应'''

    raw: Any
    usage: Any = None

    @property
    def choices(self) -> Any:
        return self.raw.choices

    @property
    def message(self) -> Any:
        return self.raw.choices[0].message


@dataclass
class ToolCallDelta:
    index: int
    id: str | None = None
    type: str | None = None
    function_name: str | None = None
    function_arguments: str | None = None


@dataclass
class ModelStreamEvent:
    """Normalized streaming chunk (optional; native OpenAI chunks pass through)."""

    content_delta: str | None = None
    refusal_delta: str | None = None
    tool_call_deltas: list[ToolCallDelta] | None = None
    finish_reason: str | None = None
    usage: Any = None
    raw_chunk: Any = None  # when set, consumers may use native OpenAI chunk
