from typing import Any

from agent.core.multimodal import content_to_text
from agent.hook.schema import ModelHookOutput, PreModelCallHook

# 子串匹配（不区分大小写）：越狱 / 无视系统类常见说法，按需自行增删
_DEFAULT_BLOCKED_SUBSTRINGS: tuple[str, ...] = (
    "ignore the system",
    "ignore system",
    "ignore previous instructions",
    "ignore all previous",
    "disregard your instructions",
    "developer mode",
    "jailbreak",
    "dan mode",
    "忽略系统",
    "忽略以上",
    "无视系统",
    "不要遵守系统",
    "绕过安全",
    "越狱",
)


def _latest_user_text(messages: list[dict[str, Any]]) -> str:
    """只取列表中最后一条 user 消息（本轮最新用户输入）。"""
    for m in reversed(messages):
        if m.get("role") == "user":
            return content_to_text(m.get("content"))
    return ""


class ModelPrePromptGuardHook(PreModelCallHook):
    """模型调用前仅检查本轮最后一条 user 消息，命中简单危险子串则拦截。"""

    def __init__(
        self,
        blocked_substrings: tuple[str, ...] | None = None,
        *,
        refusal_message: str = "检测到疑似越狱或无视系统指令的内容，本次请求已被拦截。",
    ) -> None:
        self._blocked = blocked_substrings or _DEFAULT_BLOCKED_SUBSTRINGS
        self._refusal = refusal_message

    def invoke(
        self,
        context: Any,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ModelHookOutput | None:
        haystack = _latest_user_text(messages).lower()
        for needle in self._blocked:
            if needle.lower() in haystack:
                return ModelHookOutput(
                    allowed=False,
                    messages=messages,
                    tools=tools,
                    maybe_output=self._refusal,
                )
        return None
