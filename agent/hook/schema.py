from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from collections.abc import Iterator
from typing import Any, Callable

class HookEvent(str, Enum):
    '''钩子事件类型'''

    # tool hook
    PRE_TOOL_USE = "PreToolUse"
    WRAP_TOOL_CALL = "WrapToolCall"
    POST_TOOL_USE = "PostToolUse"

    # session hook
    SESSION_START = "SessionStart"
    SESSION_END = "SessionEnd"

    # loop hook
    LOOP_START = "LoopStart"
    WRAP_LOOP = "WrapLoop"
    LOOP_END = "LoopEnd"
    
    # model hook
    PRE_MODEL_CALL = "PreModelCall"
    WRAP_MODEL_CALL = "WrapModelCall"
    POST_MODEL_CALL = "PostModelCall"
    
    
# base hook
class BaseHook(ABC):
    EVENT_NAME: HookEvent | None = None

    @property
    def event(self) -> HookEvent:
        if self.EVENT_NAME is None:
            raise ValueError("EVENT_NAME is not set")
        return self.EVENT_NAME

    @abstractmethod
    def invoke(
        self,
        state: Any,    # 状态（固定位置参数）
        context: Any,  # 上下文（固定位置参数）
        *args: Any,    # 接收所有额外的位置参数
        **kwargs: Any, # 接收所有额外的关键字参数
    ) -> Any:
        pass

# -------------------------------------------- tool hook --------------------------------------------

# tool hook output
@dataclass
class ToolHookOutput:
    allowed: bool
    maybe_output: str | None = None


class PreToolUseHook(BaseHook):
    EVENT_NAME = HookEvent.PRE_TOOL_USE

    @abstractmethod
    def invoke(
        self,
        context: Any,
        *,
        tool_call: dict[str, Any],
    ) -> ToolHookOutput | None:
        ...

class WrapToolCallHook(BaseHook):
    EVENT_NAME = HookEvent.WRAP_TOOL_CALL

    @abstractmethod
    def invoke(
        self,
        context: Any,
        *,
        tool_call_id: str,
        name: str,
        tool_input: dict[str, Any],
    ) -> None:
        """在发出工具调用事件、执行 dispatch 之前触发；用于日志或旁路逻辑。"""
        ...

class PostToolUseHook(BaseHook):
    EVENT_NAME = HookEvent.POST_TOOL_USE

    @abstractmethod
    def invoke(
        self,
        context: Any,
        *,
        tool_call: dict[str, Any],
        result: Any,
    ) -> ToolHookOutput | None:
        pass

# -------------------------------------------- session hook --------------------------------------------
class SessionStartHook(BaseHook):
    EVENT_NAME = HookEvent.SESSION_START

    @abstractmethod
    def invoke(self,context: Any) -> Any:
        ...

class SessionEndHook(BaseHook):
    EVENT_NAME = HookEvent.SESSION_END
    @abstractmethod
    def invoke(self,context: Any) -> Any:
        ...

# -------------------------------------------- loop hook --------------------------------------------
class LoopStartHook(BaseHook):
    EVENT_NAME = HookEvent.LOOP_START

    @abstractmethod
    def invoke(self,context: Any) -> Any:
        ...


class LoopEndHook(BaseHook):
    EVENT_NAME = HookEvent.LOOP_END

    @abstractmethod
    def invoke(self,context: Any) -> Any:
        ...


class WrapLoopHook(BaseHook):
    EVENT_NAME = HookEvent.WRAP_LOOP

    @abstractmethod
    def invoke(
        self,
        context: Any,
        call_next: Callable[[], Iterator[Any]],
    ) -> Iterator[Any]:
        """环绕主循环；通过 ``yield from call_next()`` 边跑边转发事件，保持流式输出。"""
        ...

# -------------------------------------------- model hook --------------------------------------------
@dataclass
class ModelHookOutput:
    """``HookManager.run_pre_model_call`` 的聚合结果。"""

    allowed: bool
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]]
    maybe_output: str | None = None


@dataclass
class PostModelCallPayload:
    """PostModelCall 在「流已跑完、assistant 条还没写入 history」这一刻拿到的一份快照。

    拆成多个字段是为了常见用途互不耦合——钩子可以只读其中几项，或只改写
    ``model_output_messages``：

    - ``model_input_messages``：本轮实际发给模型的消息列表（含 system）；做用量估算、审计对账。
    - ``tools``：本轮随请求带的 tools schema；审计「当时模型能看到哪些工具」。
    - ``finish_reason``：API 报告的结束原因（如 ``stop`` / ``tool_calls``）；与循环是否继续工具有关。
    - ``usage``：若网关返回 token 统计则在此；否则常为 ``None``。计费类钩子只碰它即可。
    - ``model_output_messages``：已从 chunk 拼好的本轮模型输出侧消息（通常为单条 ``{"role":"assistant", ...}``）；钩子可返回新 dict 替换后再 ``append``。
    """

    model_input_messages: list[dict[str, Any]]
    tools: list[dict[str, Any]]
    finish_reason: str | None
    usage: Any
    model_output_messages: dict[str, Any]


class PreModelCallHook(BaseHook):
    EVENT_NAME = HookEvent.PRE_MODEL_CALL

    @abstractmethod
    def invoke(
        self,
        context: Any,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ModelHookOutput | None:
        """与 :class:`PreToolUseHook` 相同：仅返回 :class:`ToolHookOutput` 或 ``None``。

        ``None``：不拦截；可在入参 ``messages`` / ``tools`` 上**原地**改写后再进入后续阶段。

        ``ModelHookOutput(allowed=False, maybe_output=...)``：拦截本次模型调用。
        """
        ...


class PostModelCallHook(BaseHook):
    EVENT_NAME = HookEvent.POST_MODEL_CALL

    @abstractmethod
    def invoke(
        self,
        context: Any,
        *,
        payload: PostModelCallPayload,
    ) -> dict[str, Any] | None:
        """流结束、尚未写入 ``state.messages`` 时调用。

        返回 ``None`` 保留当前 ``payload.model_output_messages``；返回新的输出侧消息 dict
        则替换之（多钩子按注册顺序链式覆盖）。
        """
        ...


class WrapModelCallHook(BaseHook):
    EVENT_NAME = HookEvent.WRAP_MODEL_CALL

    @abstractmethod
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
        """环绕单次模型流式调用，语义对齐 :class:`WrapLoopHook`。

        内层 ``call_next(messages, tools)`` 返回 **chunk 迭代器**（如 OpenAI 的 stream）；
        外层应 ``yield from call_next(...)`` 或在此之上做 tee / 变换，以保持上游流式消费。
        """
        ...