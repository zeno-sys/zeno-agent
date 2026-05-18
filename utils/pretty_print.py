import json
from typing import Any

_RESET = "\033[0m"
_DIM = "\033[2m"
_GREEN = "\033[92m"
_CYAN = "\033[36m"

# run_loop 事件流里「助手流式输出」是否已打开 ANSI 颜色（跨多次 print_run_event 调用）
_run_event_ai_active = False


def print_run_event_stream_done() -> None:
    """一轮 run_loop 消费结束后调用：结束助手流式颜色并换行（若仍在流式输出中）。"""
    global _run_event_ai_active
    if _run_event_ai_active:
        print(_RESET, flush=True)
        _run_event_ai_active = False


def user_input_prompt() -> str:
    """供 `input()` 使用：新起一行、带 user 角色标记，再显示提示符。"""
    return f"\n{_DIM}╭ user{_RESET}\n{_CYAN}>> {_RESET}"


def print_command_invoked(command_name: str) -> None:
    """CLI：用户触发 ``/command`` 时的简短提示。"""
    print(f"{_DIM}╭ command /{command_name}{_RESET}", flush=True)


def _clarify_question_lines(question: str, choices: list[str] | None) -> list[str]:
    """问题与选项的纯文本行（供提问框与结果框复用）。"""
    lines: list[str] = []
    for line in question.splitlines() or ["(empty)"]:
        lines.append(line)
    if choices:
        lines.append("")
        lines.append("可选：")
        for i, c in enumerate(choices, 1):
            lines.append(f"  {i}. {c}")
    return lines


def print_clarify_prompt(question: str, choices: list[str] | None) -> None:
    """CLI 澄清：与 tool_call 一致的框线排版，便于在事件流中一眼区分。"""
    yellow = "\033[93m"
    reset = "\033[0m"
    print(f"{yellow}┌─ 需要澄清{reset}", flush=True)
    for line in _clarify_question_lines(question, choices):
        print(f"{yellow}│ {line}{reset}", flush=True)
    print(f"{yellow}└────────────{reset}", flush=True)
    print(f"{_DIM}（可输入序号、选项原文或自由回答）{_RESET}", flush=True)


def format_clarify_tool_result(raw: str) -> str | None:
    """将 clarify 工具返回的 JSON 格式化为问答摘要；非 clarify 载荷返回 None。"""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or "user_response" not in payload:
        return None

    question = str(payload.get("question", "")).strip()
    choices_raw = payload.get("choices_offered")
    choices: list[str] | None = None
    if isinstance(choices_raw, list):
        choices = [str(c).strip() for c in choices_raw if str(c).strip()]
        if not choices:
            choices = None

    lines: list[str] = []
    if question or choices:
        lines.extend(_clarify_question_lines(question, choices))
    user_response = str(payload.get("user_response", "")).strip() or "(empty)"
    if lines:
        lines.append("")
    lines.append(f"答：{user_response}")
    return "\n".join(lines)


def print_clarify_result(tool_call_id: str, rendered: str) -> None:
    yellow = "\033[93m"
    reset = "\033[0m"
    print(f"{yellow}┌─ 澄清结果{reset}")
    print(f"{yellow}│ id: {tool_call_id}{reset}")
    for line in rendered.splitlines():
        print(f"{yellow}│ {line}{reset}")
    print(f"{yellow}└────────────{reset}")


def print_run_event(ev: dict[str, Any]) -> None:
    """为 `run_loop` 产出的 RunEvent 做终端着色与排版（与 print_tool_call / print_tool_result 风格一致）。"""
    global _run_event_ai_active
    kind = ev.get("event")
    data = ev.get("data")

    if kind == "ai":
        if not isinstance(data, str) or not data:
            return
        if not _run_event_ai_active:
            print(f"{_DIM}╭ assistant{_RESET}{_GREEN}", end="", flush=True)
            _run_event_ai_active = True
        print(data, end="", flush=True)
        return

    if _run_event_ai_active:
        print(_RESET, flush=True)
        _run_event_ai_active = False

    if kind == "tool_call" and isinstance(data, dict):
        raw_in = data.get("tool_input")
        tool_input: dict[str, object] = raw_in if isinstance(raw_in, dict) else {}
        print_tool_call(
            tool_name=str(data.get("tool_name", "")),
            tool_input=tool_input,
            tool_call_id=str(data.get("tool_call_id", "")),
        )
        return

    if kind == "tool_result" and isinstance(data, dict):
        tool_call_id = str(data.get("tool_call_id", ""))
        output = str(data.get("tool_result", ""))
        tool_name = str(data.get("tool_name", ""))
        if tool_name == "todo":
            rendered = format_todo_tool_result(output)
            if rendered is not None:
                print_todo_result(tool_call_id, rendered)
                return
        if tool_name == "clarify":
            rendered = format_clarify_tool_result(output)
            if rendered is not None:
                print_clarify_result(tool_call_id, rendered)
                return
        print_tool_result(tool_call_id, output)
        return


def print_ai_output(content: str) -> None:
    green = "\033[92m"
    reset = "\033[0m"

    print(f"{green}┌─ AI{reset}")
    for line in content.splitlines() or ["(empty)"]:
        print(f"{green}│ {line}{reset}")
    print(f"{green}└────────────{reset}")
    print()

def format_todo_tool_result(raw: str) -> str | None:
    """将 todo 工具返回的 JSON 格式化为 Markdown 风格任务列表；非 todo 载荷返回 None。"""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or "todos" not in payload:
        return None
    todos = payload.get("todos")
    if not isinstance(todos, list):
        return None
    if not todos:
        return "No session plan yet."

    markers = {
        "pending": "[ ]",
        "in_progress": "[>]",
        "completed": "[x]",
        "cancelled": "[~]",
    }
    lines: list[str] = []
    for item in todos:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status", "pending")).strip().lower()
        marker = markers.get(status, "[?]")
        content = str(item.get("content", "")).strip() or "(no description)"
        line = f"{marker} {content}"
        active_form = item.get("active_form")
        if status == "in_progress" and active_form:
            line += f" ({active_form})"
        lines.append(line)
    completed = sum(
        1 for item in todos if isinstance(item, dict) and item.get("status") == "completed"
    )
    lines.append(f"\n({completed}/{len(todos)} completed)")
    return "\n".join(lines)


def print_todo_result(tool_call_id: str, rendered: str) -> None:
    blue = "\033[94m"
    reset = "\033[0m"
    print(f"{blue}┌─ todo{reset}")
    print(f"{blue}│ id: {tool_call_id}{reset}")
    for line in rendered.splitlines():
        print(f"{blue}│ {line}{reset}")
    print(f"{blue}└────────────{reset}")


def print_tool_call(tool_name: str, tool_input: dict[str, object], tool_call_id: str) -> None:
    blue = "\033[94m"
    reset = "\033[0m"
    args_pretty = json.dumps(tool_input, ensure_ascii=False, indent=2)
    print(f"{blue}┌─ tool call{reset}")
    print(f"{blue}│ id:   {tool_call_id}{reset}")
    print(f"{blue}│ name: {tool_name}{reset}")
    print(f"{blue}│ args:{reset}")
    for line in args_pretty.splitlines():
        print(f"{blue}│   {line}{reset}")
    print(f"{blue}└────────────{reset}")

def print_tool_result(tool_call_id: str, output: str, preview_length: int = 400) -> None:
    blue = "\033[94m"
    reset = "\033[0m"
    preview = output[:preview_length]
    print(f"{blue}┌─ tool result{reset}")
    print(f"{blue}│ id: {tool_call_id}{reset}")
    print(f"{blue}│ content preview:{reset}")
    for line in preview.splitlines() or ["(empty)"]:
        print(f"{blue}│   {line}{reset}")
    if len(output) > len(preview):
        print(f"{blue}│   ... ({len(output) - len(preview)} more chars){reset}")
    print(f"{blue}└────────────{reset}")

def print_session_start(session_id: str) -> None:
    green = "\033[92m"
    reset = "\033[0m"
    print(f"{green}欢迎来到会话 {session_id}，输入 q / exit / 空行可退出。{reset}")

def print_session_logo() -> None:
    purple = "\033[95m"
    cyan = "\033[96m"
    reset = "\033[0m"
    logo_lines = [
        " _______  _______  __    _  _______ ",
        "|       ||       ||  |  | ||       |",
        "|____   ||    ___||   |_| ||   _   |",
        " ____|  ||   |___ |       ||  | |  |",
        "| ______||    ___||  _    ||  |_|  |",
        "| |_____ |   |___ | | |   ||       |",
        "|_______||_______||_|  |__||_______|",
        "",
        "            Zeno Agent",
        "      Think clearly, act reliably.",
    ]
    width = max(len(line) for line in logo_lines)
    top = f"┌{'─' * (width + 2)}┐"
    bottom = f"└{'─' * (width + 2)}┘"
    print(f"{purple}{top}{reset}")
    for line in logo_lines:
        print(f"{purple}│ {cyan}{line.ljust(width)}{purple} │{reset}")
    print(f"{purple}{bottom}{reset}")

def print_session_end(session_id: str) -> None:
    yellow = "\033[93m"
    reset = "\033[0m"
    print(f"{yellow}会话 {session_id} 已结束，感谢使用。{reset}")

def print_recommended_questions(questions: list[str], max_count: int = 3) -> None:
    cyan = "\033[96m"
    reset = "\033[0m"
    print(f"{cyan}下一轮推荐问题：{reset}")
    for i, question in enumerate(questions[:max_count], start=1):
        print(f"{cyan}{i}. {question}{reset}")

def print_end_state(meta: dict[str, object]) -> None:
    cyan = "\033[95m"
    reset = "\033[0m"
    messages = meta.get("messages")
    messages_len = len(messages) if isinstance(messages, list) else messages
    print(
        f"{cyan}[end_state]{reset} "
        f"turn_count={meta.get('turn_count')} | "
        f"transition_reason={meta.get('transition_reason')} | "
        f"messages_len={messages_len}"
    )
    print()