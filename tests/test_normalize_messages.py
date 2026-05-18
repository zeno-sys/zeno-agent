"""normalize_messages_openai 行为说明与回归测试。

为什么需要补全缺失的工具调用响应？
因为如果 AI 说「我用工具 A」，但对话历史中没有工具 A 的结果，AI 会困惑「我刚才调用工具了吗？结果是什么？」

为什么需要合并连续的同角色消息？
理想情况下：user → assistant → user → assistant → …
可能一些意外情况：user → user → assistant → assistant → … 不利于 AI 理解对话上下文；
合并为 user → assistant → … 更有利于理解。
"""

from __future__ import annotations

import json
from typing import Any

from utils.normalize_messages import normalize_messages_openai

_CONTENT_PREVIEW = 80


def _step(banner: str) -> None:
    print(f"--------------------------------{banner}--------------------------------")


def _preview(text: str, *, limit: int = _CONTENT_PREVIEW) -> str:
    one_line = text.replace("\n", "\\n")
    if len(one_line) <= limit:
        return one_line
    return one_line[: limit - 3] + "..."


def _print_messages(label: str, messages: list[dict[str, Any]]) -> None:
    print(f"  [{label}] 条数: {len(messages)}")
    if not messages:
        print("  (空列表)")
        return
    roles = " → ".join(m.get("role", "?") for m in messages)
    print(f"  角色序列: {roles}")
    for i, msg in enumerate(messages):
        role = msg.get("role", "?")
        line = f"  [{i}] role={role}"
        if "content" in msg and msg["content"] is not None:
            line += f'  content="{_preview(str(msg["content"]))}"'
        if msg.get("tool_calls"):
            names = []
            for tc in msg["tool_calls"]:
                fn = (tc or {}).get("function") or {}
                arg_raw = fn.get("arguments", "")
                arg_note = "(empty)" if arg_raw in ("", None) else _preview(str(arg_raw), limit=40)
                names.append(f'{fn.get("name", "?")}(args={arg_note})')
            line += f"  tool_calls=[{', '.join(names)}]"
        if "tool_call_id" in msg:
            line += f'  tool_call_id={msg["tool_call_id"]}'
        print(line)


def test_merge_consecutive_same_role_messages() -> None:
    _step("准备输入：连续同角色消息")
    messages = [
        {"role": "user", "content": "你好"},
        {"role": "user", "content": "今天天气怎么样"},
        {"role": "assistant", "content": "我来查一下"},
        {"role": "assistant", "content": "需要您提供位置"},
    ]
    _print_messages("输入", messages)

    _step("执行 normalize_messages_openai")
    out = normalize_messages_openai(messages)

    _step("结果摘要")
    _print_messages("输出", out)
    print("  期望: 4 条 → 2 条；同角色 content 用换行拼接")

    assert len(out) == 2, out
    assert out[0]["content"] == "你好\n今天天气怎么样", out[0]
    assert out[1]["content"] == "我来查一下\n需要您提供位置", out[1]
    print("  断言通过: 合并条数与拼接内容正确")


def test_multimodal_content_not_stringified() -> None:
    parts = [
        {"type": "text", "text": "图"},
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,/9j/4AAQ"}},
    ]
    out = normalize_messages_openai([{"role": "user", "content": parts}])
    assert isinstance(out[0]["content"], list)
    assert out[0]["content"][0]["type"] == "text"


def test_inserts_placeholder_when_tool_response_missing() -> None:
    _step("准备输入：assistant 有 tool_calls 但缺少 tool 响应")
    incomplete_messages = [
        {"role": "user", "content": "请查看当前目录"},
        {
            "role": "assistant",
            "content": "我来帮你查看当前目录",
            "tool_calls": [
                {
                    "id": "call_abc123",
                    "type": "function",
                    "function": {
                        "name": "run_command",
                        "arguments": json.dumps({"command": "ls -la"}),
                    },
                }
            ],
        },
        # 缺少 tool 角色对工具调用的响应
        {"role": "user", "content": "然后看看有什么文件"},
    ]
    _print_messages("输入", incomplete_messages)
    print("  缺失: call_abc123 对应的 role=tool 消息")

    _step("执行 normalize_messages_openai")
    out = normalize_messages_openai(incomplete_messages)

    _step("结果摘要")
    _print_messages("输出", out)
    tool_msgs = [m for m in out if m["role"] == "tool"]
    if tool_msgs:
        print(f"  补全占位: tool_call_id={tool_msgs[0].get('tool_call_id')}")
        print(f"  占位 content: {tool_msgs[0].get('content')!r}")

    assert [m["role"] for m in out] == ["user", "assistant", "tool", "user"], out
    assert len(tool_msgs) == 1, out
    assert tool_msgs[0]["tool_call_id"] == "call_abc123", tool_msgs[0]
    assert tool_msgs[0]["content"] == "(cancelled)", tool_msgs[0]
    print("  断言通过: 已插入 (cancelled) 占位且角色序列为 user→assistant→tool→user")


def test_tool_call_empty_arguments_becomes_empty_object_json() -> None:
    """流式聚合常见 arguments==""；上游按 JSON 解析时会报 Expecting value。"""
    _step("准备输入：arguments 为空字符串")
    messages = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": "x",
            "tool_calls": [
                {
                    "id": "call_t1",
                    "type": "function",
                    "function": {"name": "todo", "arguments": ""},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_t1", "content": "{}"},
    ]
    _print_messages("输入", messages)
    print('  原始 arguments: "" (空串)')

    _step("执行 normalize_messages_openai")
    out = normalize_messages_openai(messages)

    _step("结果摘要")
    tc = out[1]["tool_calls"][0]
    fixed_args = tc["function"]["arguments"]
    print(f"  规范化后 arguments: {fixed_args!r}")
    print("  期望: '{}' (合法空 JSON 对象)")

    assert fixed_args == "{}", tc
    print("  断言通过: 空 arguments 已变为 {}")


def test_tool_call_malformed_arguments_becomes_empty_object_json() -> None:
    bad = '{"todos": "plan_init", "content": "x", "status": "pending"], "merge": false}'
    _step("准备输入：arguments 为非法 JSON")
    messages = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": "x",
            "tool_calls": [
                {
                    "id": "call_bad",
                    "type": "function",
                    "function": {"name": "todo", "arguments": bad},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_bad", "content": "err"},
    ]
    _print_messages("输入", messages)
    print(f"  原始 arguments 预览: {_preview(bad, limit=60)}")
    try:
        json.loads(bad)
        print("  (意外) 原始串可被 json.loads 解析")
    except json.JSONDecodeError as e:
        print(f"  json.loads 失败（符合预期）: {e}")

    _step("执行 normalize_messages_openai")
    out = normalize_messages_openai(messages)

    _step("结果摘要")
    fixed_args = out[1]["tool_calls"][0]["function"]["arguments"]
    print(f"  规范化后 arguments: {fixed_args!r}")
    print("  期望: '{}' (损坏 JSON 回退为空对象)")

    assert fixed_args == "{}", out[1]["tool_calls"][0]
    print("  断言通过: 畸形 arguments 已变为 {}")
