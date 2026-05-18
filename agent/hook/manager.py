from collections.abc import Iterator
from typing import Any, Callable

from agent.hook.schema import *

class HookManager:

    def __init__(self) -> None:
        # 每种 hook 事件都维护独立列表，执行顺序即注册顺序
        self.pre_tool_use_hooks: list[PreToolUseHook] = []
        self.post_tool_use_hooks: list[PostToolUseHook] = []
        self.session_start_hooks: list[SessionStartHook] = []
        self.session_end_hooks: list[SessionEndHook] = []
        self.loop_start_hooks: list[LoopStartHook] = []
        self.loop_end_hooks: list[LoopEndHook] = []
        self.wrap_loop_hooks: list[WrapLoopHook] = []
        self.pre_model_call_hooks: list[PreModelCallHook] = []
        self.post_model_call_hooks: list[PostModelCallHook] = []
        self.wrap_model_call_hooks: list[WrapModelCallHook] = []
        self.wrap_tool_call_hooks: list[WrapToolCallHook] = []

        self._hooks_by_event: dict[HookEvent, list[BaseHook]] = {
            HookEvent.PRE_TOOL_USE: self.pre_tool_use_hooks,
            HookEvent.POST_TOOL_USE: self.post_tool_use_hooks,
            HookEvent.SESSION_START: self.session_start_hooks,
            HookEvent.SESSION_END: self.session_end_hooks,
            HookEvent.LOOP_START: self.loop_start_hooks,
            HookEvent.LOOP_END: self.loop_end_hooks,
            HookEvent.WRAP_LOOP: self.wrap_loop_hooks,
            HookEvent.PRE_MODEL_CALL: self.pre_model_call_hooks,
            HookEvent.POST_MODEL_CALL: self.post_model_call_hooks,
            HookEvent.WRAP_MODEL_CALL: self.wrap_model_call_hooks,
            HookEvent.WRAP_TOOL_CALL: self.wrap_tool_call_hooks,
        }

    def register(self, hook: BaseHook) -> None:
        event: HookEvent = hook.event
        if event not in self._hooks_by_event:
            raise ValueError(f"Unknown hook event: {event}")
        self._hooks_by_event[event].append(hook)

    def run_pre_model_call(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        context: Any,
    ) -> ModelHookOutput:
        for hook in self.pre_model_call_hooks:
            result = hook.invoke(
                context=context,
                messages=messages,
                tools=tools,
            )
            if result is None:
                continue
            if not result.allowed:
                return ModelHookOutput(
                    allowed=False,
                    messages=messages,
                    tools=tools,
                    maybe_output=result.maybe_output,
                )
        return ModelHookOutput(
            allowed=True,
            messages=messages,
            tools=tools,
            maybe_output=None,
        )

    def run_session_start(self,context: Any) -> None:
        for hook in self.session_start_hooks:
            hook.invoke(context=context)

    def run_session_end(self,context: Any) -> None:
        for hook in self.session_end_hooks:
            hook.invoke(context=context)

    def run_loop_start(self,context: Any) -> None:
        for hook in self.loop_start_hooks:
            hook.invoke(context=context)

    def run_loop_end(self,context: Any) -> None:
        for hook in self.loop_end_hooks:
            hook.invoke(context=context)

    def run_wrap_loop(
        self,
        loop_invoke: Callable[[], Iterator[Any]],
        context: Any,
    ) -> Iterator[Any]:
        call_chain = loop_invoke
        for hook in reversed(self.wrap_loop_hooks):
            next_call = call_chain

            def _wrap(
                _hook: WrapLoopHook = hook,
                _next: Callable[[], Iterator[Any]] = next_call,
            ) -> Iterator[Any]:
                return _hook.invoke(
                    context=context,
                    call_next=_next,
                )

            call_chain = _wrap
        yield from call_chain()

    def run_wrap_model_call(
        self,
        model_invoke: Callable[[list[dict[str, Any]], list[dict[str, Any]]], Any],
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        context: Any,
    ) -> Any:
        """自外向内包裹 ``model_invoke``，与 :meth:`run_wrap_loop` 相同的外层先注册先执行。

        ``model_invoke(messages, tools)`` 须返回 **可迭代 chunk 流**（如 OpenAI stream）；
        各 :class:`WrapModelCallHook` 应 ``yield from call_next(...)`` 保持流式语义。
        """
        call_chain = model_invoke
        for hook in reversed(self.wrap_model_call_hooks):
            next_call = call_chain

            def _wrap(
                current_messages: list[dict[str, Any]],
                current_tools: list[dict[str, Any]],
                _hook: WrapModelCallHook = hook,
                _next: Callable[[list[dict[str, Any]], list[dict[str, Any]]], Any] = next_call,
            ) -> Any:
                return _hook.invoke(
                    context=context,
                    call_next=_next,
                    messages=current_messages,
                    tools=current_tools,
                )

            call_chain = _wrap
        return call_chain(messages, tools)

    def run_post_model_call(
        self,
        *,
        context: Any,
        payload: PostModelCallPayload,
    ) -> dict[str, Any]:
        """在 assistant 消息写入 ``state.messages`` 之前调用，可链式改写 ``payload.model_output_messages``。"""
        for hook in self.post_model_call_hooks:
            result = hook.invoke(context=context, payload=payload)
            if result is not None:
                payload.model_output_messages = result
        return payload.model_output_messages

    def run_pre_tool_use(
        self,
        context: Any,
        *,
        tool_call: dict[str, Any],
    ) -> ToolHookOutput:
        for hook in self.pre_tool_use_hooks:
            result = hook.invoke(context=context, tool_call=tool_call)
            if result is None:
                continue
            if not result.allowed:
                return result
        return ToolHookOutput(allowed=True, maybe_output=None)

    def run_wrap_tool_call(
        self,
        context: Any,
        *,
        tool_call_id: str,
        name: str,
        tool_input: dict[str, Any],
    ) -> None:
        for hook in self.wrap_tool_call_hooks:
            hook.invoke(
                context=context,
                tool_call_id=tool_call_id,
                name=name,
                tool_input=tool_input,
            )

    def run_post_tool_use(
        self,
        context: Any,
        *,
        tool_call: dict[str, Any],
        result: Any,
    ) -> Any:
        current: Any = result
        for hook in self.post_tool_use_hooks:
            hook_result = hook.invoke(
                context=context,
                tool_call=tool_call,
                result=current,
            )
            if hook_result is None:
                continue
            if not hook_result.allowed:
                if hook_result.maybe_output is not None:
                    current = hook_result.maybe_output
                break
            if hook_result.maybe_output is not None:
                current = hook_result.maybe_output
        return current

if __name__ == "__main__":
    hook_manager = HookManager()

    class PreToolUseHook1(PreToolUseHook):
        def invoke(self, context: Any, *, tool_call: dict[str, Any]) -> ToolHookOutput:
            print(f"PreToolUseHook: {tool_call}, {context}")
            return ToolHookOutput(allowed=True, maybe_output=None)

    class PreToolUseHook2(PreToolUseHook):
        def invoke(self, context: Any, *, tool_call: dict[str, Any]) -> ToolHookOutput:
            print(f"PreToolUseHook: {tool_call}, {context}")
            return ToolHookOutput(allowed=False, maybe_output=None)

    hook_manager.register(PreToolUseHook1())
    hook_manager.register(PreToolUseHook2())

    sample_call = {
        "id": "call-1",
        "type": "function",
        "function": {"name": "tool_name", "arguments": "{}"},
    }
    results = hook_manager.run_pre_tool_use(context="context", tool_call=sample_call)
    print(results)
