import json
import os
from pathlib import Path
from typing import Any, Generator, Iterator, Literal
import time

from dotenv import load_dotenv

import sys; sys.path.insert(0, '.')
from agent.core.context import AgentContext
from agent.core.context import AgentState
from agent.core.run_events import (
    RunEvent,
    send_ai_message,
    send_tool_call,
    send_tool_result,
)
from agent.core.system_prompt import SystemPromptBuilder
from agent.tool.registry import registry as tool_registry
from model_layer import ModelRequest, get_default_model_client
from utils.normalize_messages import normalize_messages_openai
from agent.command import resolve_user_input
from agent.core.multimodal import ImageAttachmentParseError, validate_image_paths
from agent.core.user_input import UserInput, user_input_to_message
from utils.pretty_print import (
    print_clarify_prompt,
    print_command_invoked,
    print_run_event,
    print_run_event_stream_done,
    user_input_prompt,
)
from hooks import *
from agent.hook.manager import HookManager
from agent.hook.schema import PostModelCallPayload

load_dotenv()

from tools import register_all_tools

register_all_tools()

FinishReason = Literal["stop", "length", "tool_calls", "content_filter", "function_call"]

def _tool_dispatch_extra_args(context: AgentContext, tool_name: str) -> dict[str, Any]:
    """为需要依赖注入的工具构造 extra_args（与 tools/__init__.py 中 handler 约定一致）。"""
    extra: dict[str, Any] = {}
    if tool_name == "todo" and context.todo_store is not None:
        extra["store"] = context.todo_store
    elif tool_name == "memory" and context.memory_store is not None:
        extra["store"] = context.memory_store
    elif tool_name == "clarify" and context.clarify_callback is not None:
        extra["callback"] = context.clarify_callback

    if context.filesystem_backend is not None:
        from tools.backend_file_tools import BACKEND_FILE_TOOLSET

        if tool_registry.get_toolset_for_tool(tool_name) == BACKEND_FILE_TOOLSET:
            extra["filesystem_backend"] = context.filesystem_backend

    return extra


def run_one_turn(context: AgentContext) -> Generator[RunEvent, None, bool]:
    """执行一个回合，产出流式事件；结束时通过 `return` 告知是否继续多轮工具循环。"""

    state = context.state
    hook_manager = context.hook_manager

    # 1. 构建系统提示词
    builder = SystemPromptBuilder(
        workdir=Path.cwd(),
        model=os.getenv("MODEL_NAME"),
    )
    system_prompt = builder.build()

    # 2. 规范化消息
    state.messages[:] = normalize_messages_openai(state.messages)

    # 3. 构建模型输入消息与工具 schema，经 PreModelCall 可改写
    model_input_messages = [{"role": "system", "content": system_prompt}] + state.messages
    tool_schema = tool_registry.get_tool_schema()

    pre_gate = hook_manager.run_pre_model_call(
        model_input_messages,
        tool_schema,
        context,
    )
    if not pre_gate.allowed:
        maybe_output = pre_gate.maybe_output or "Model call denied by hook"
        yield from send_ai_message(maybe_output)
        state.messages.append({"role": "assistant", "content": maybe_output})
        state.transition_reason = "stop"
        return False

    messages, tools = pre_gate.messages, pre_gate.tools

    def _open_chat_stream(
        msgs: list[dict[str, Any]],
        tls: list[dict[str, Any]],
        model: str | None = os.getenv("MODEL_NAME"),
    ) -> Any:
        model_req = ModelRequest(
            task="agent",
            messages=msgs,
            tools=tls,
            model=model,
            stream=True,
            metadata={"session_id": context.session_id},
        )
        return get_default_model_client().stream(model_req)

    stream = hook_manager.run_wrap_model_call(
        _open_chat_stream,
        messages,
        tools,
        context,
    )

    content_parts: list[str] = []
    tool_call_slots: dict[int, dict[str, Any]] = {}
    finish_reason: FinishReason | None = None
    last_usage: Any = None

    for chunk in stream:
        u = getattr(chunk, "usage", None)
        if u is not None:
            last_usage = u
        if not chunk.choices:
            continue
        choice = chunk.choices[0]
        if choice.finish_reason is not None:
            finish_reason = choice.finish_reason  # type: ignore[assignment]
        delta = choice.delta
        if delta is None:
            continue
        if delta.content:
            content_parts.append(delta.content)
            yield from send_ai_message(delta.content)
        if delta.refusal:  # 模型生成的拒绝说明文案
            refusal_text = str(delta.refusal)
            content_parts.append(refusal_text)
            yield from send_ai_message(refusal_text)

        # 模型调用的工具聚合信息
        if delta.tool_calls:
            for dtc in delta.tool_calls:
                i = dtc.index
                # 初始化工具调用槽位
                slot = tool_call_slots.setdefault(
                    i,
                    {
                        "id": "",
                        "type": "function",
                        "function": {"name": "", "arguments": ""},
                    },
                )
                if dtc.id:
                    slot["id"] = dtc.id
                if dtc.type:
                    slot["type"] = dtc.type
                if dtc.function:
                    if dtc.function.name:
                        slot["function"]["name"] += dtc.function.name
                    if dtc.function.arguments:
                        slot["function"]["arguments"] += dtc.function.arguments

    if finish_reason is None:
        finish_reason = "stop"

    # 构建完整的消息，用于添加到历史消息中
    assistant_msg: dict[str, Any] = {"role": "assistant"}
    full_content = "".join(content_parts)
    if full_content:
        assistant_msg["content"] = full_content
    if tool_call_slots:
        assistant_msg["tool_calls"] = [
            tool_call_slots[k] for k in sorted(tool_call_slots.keys())
        ]
    
    # 模型后置钩子支持修改模型返回消息（注意到这一步消息已经流式返回给用户了，这里修改仅对模型下次调用有关）
    post_payload = PostModelCallPayload(
        model_input_messages=messages,
        tools=tools,
        finish_reason=finish_reason,
        usage=last_usage,
        model_output_messages=assistant_msg,
    )
    hook_manager.run_post_model_call(
        context=context,
        payload=post_payload,
    )

    # 4. 将模型返回消息的内容添加到历史消息中
    state.messages.append(assistant_msg)

    if finish_reason not in ["tool_calls", "function_call"]:
        state.transition_reason = finish_reason
        return False

    # 模型调用的工具
    tool_calls: list[dict[str, Any]] = assistant_msg.get("tool_calls") or []

    if not tool_calls:
        state.transition_reason = None
        return False

    # 5. 执行工具调用
    results: list[dict] = []
    for tool_call in tool_calls:
        if tool_call.get("type") != "function":
            continue
        if not isinstance(tool_call.get("function"), dict):
            tool_call["function"] = {}
        fn = tool_call["function"]
        name = fn.get("name") or ""
        raw_args = fn.get("arguments") or ""
        tool_call_id = tool_call.get("id") or ""
        try:
            tool_input = json.loads(raw_args) if raw_args else {}
        except json.JSONDecodeError as e:
            err = f"Invalid JSON arguments: {raw_args}. Error: {e}"
            # 坏掉的 arguments 不能留在 history 里，否则上游下一轮解析 tool_calls 会 400
            fn["arguments"] = "{}"
            yield from send_tool_call(tool_call_id, name, {})
            yield from send_tool_result(tool_call_id, name, err)
            results.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": err,
                }
            )
            continue
        
        pre = hook_manager.run_pre_tool_use(context=context, tool_call=tool_call)

        # 检测是否被阻止执行
        if not pre.allowed:
            block_msg = pre.maybe_output or "Tool execution denied by hook"
            yield from send_tool_call(tool_call_id, name, tool_input)
            yield from send_tool_result(tool_call_id, name, block_msg)
            results.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": block_msg,
                }
            )
            continue

        yield from send_tool_call(tool_call_id, name, tool_input)
        
        result = tool_registry.dispatch(
            name, tool_input, _tool_dispatch_extra_args(context, name)
        )

        result = hook_manager.run_post_tool_use(
            context=context,
            tool_call=tool_call,
            result=result,
        )

        yield from send_tool_result(tool_call_id, name, result)
        results.append({"role": "tool", "tool_call_id": tool_call_id, "content": result})

    # 将工具调用结果添加到历史消息中
    state.messages.extend(results)

    # 回合次数加1
    state.turn_count += 1

    # 继续循环的原因设置为工具调用结果
    state.transition_reason = "tool_result"
    return True


def _iter_run_loop_core(context: AgentContext) -> Iterator[RunEvent]:
    while True:
        should_continue: bool = yield from run_one_turn(context)
        if not should_continue:
            break


def run_loop(context: AgentContext) -> Iterator[RunEvent]:
    """执行 Agent 多轮循环，以事件流形式产出（便于 CLI、SSE 等消费端）。"""
    hook_manager = context.hook_manager

    # If no hooks are registered, execute the loop directly
    if not hook_manager:
        yield from _iter_run_loop_core(context)  # 直接转发主循环的事件
        return

    # 执行LoopStart Hook
    hook_manager.run_loop_start(context=context)

    # 如果注册了WrapLoop Hook，则执行WrapLoop Hook（边跑边转发，保持流式）
    try:
        if hook_manager.wrap_loop_hooks:
            yield from hook_manager.run_wrap_loop(
                loop_invoke=lambda: _iter_run_loop_core(context),
                context=context,
            )
        else:
            yield from _iter_run_loop_core(context)
    finally:
        # 执行LoopEnd Hook
        hook_manager.run_loop_end(context=context)


def _new_session_id() -> str:
    """默认会话 ID：``YYYYMMDD_HHMMSS_mmm``，按字典序即时间先后。"""
    ts = time.strftime("%Y%m%d_%H%M%S")
    millis = int((time.time() % 1) * 1000)
    return f"{ts}_{millis:03d}"


if __name__ == "__main__":

    target_session_id = "" # TODO 需要实现从命令行传入会话ID
    history = []
    state = AgentState(messages=history)
    session_id = target_session_id.strip() or _new_session_id()

        
    # 构建上下文
    context = AgentContext()
    context.session_id = session_id
    context.state = state

    from tools.backend_file_tools import create_file_backend
    from tools.memory_tool import MemoryStore
    from tools.todo_tool import TodoStore

    context.todo_store = TodoStore()
    context.memory_store = MemoryStore()
    context.memory_store.load_from_disk()
    context.filesystem_backend = create_file_backend()

    def _cli_clarify_callback(question: str, choices: list[str] | None) -> str:
        print_clarify_prompt(question, choices)
        return input(user_input_prompt()).strip()

    context.clarify_callback = _cli_clarify_callback

    # 注册Hook
    context.hook_manager = HookManager()
    context.hook_manager.register(ModelPrePromptGuardHook())
    context.hook_manager.register(ModelRawIOLogHook())
    context.hook_manager.register(SessionStartLogoHook())
    context.hook_manager.register(SessionStartPrintHook())
    context.hook_manager.register(SessionEndPrintHook())
    context.hook_manager.register(LoopEndPrintHook())
    context.hook_manager.register(LoopWrapThinkingFormatHook())
    context.hook_manager.register(LoopEndRecommendQuestionsHook())
    context.hook_manager.register(ToolCallPrintHook())
    context.hook_manager.register(ToolResultPrintHook())

    context.hook_manager.run_session_start(context=context)
    print("提示: 可在输入中使用 @image <路径> 附带图片 (PNG/JPEG/WebP/GIF)")

    # # 发现并注册所有 MCP 工具
    # from agent.mcp.mcp_tool import discover_mcp_tools
    # discover_mcp_tools()

    while True:

        query = input(user_input_prompt())

        if query.strip().lower() in ("q", "exit", ""):
            break

        try:
            resolved = resolve_user_input(query)
        except ImageAttachmentParseError as exc:
            print(f"图片附件: {exc}")
            continue
        if resolved.is_command and resolved.command_name:
            if not resolved.is_help and not resolved.unknown_command:
                print_command_invoked(resolved.command_name)
        if resolved.skip_model:
            print(resolved.content)
            continue

        if resolved.image_paths:
            try:
                for note in validate_image_paths(resolved.image_paths):
                    print(note)
            except (OSError, ValueError) as exc:
                print(f"图片附件错误: {exc}")
                continue

        ui = UserInput(text=resolved.content, image_paths=resolved.image_paths)
        history.append(user_input_to_message(ui))

        for event in run_loop(context):
            print_run_event(event)
        print_run_event_stream_done()

    context.hook_manager.run_session_end(context=context)