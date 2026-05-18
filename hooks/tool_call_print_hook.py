import json
from typing import Any

from agent.hook.schema import PreToolUseHook, ToolHookOutput
from utils.pretty_print import print_tool_call


class ToolCallPrintHook(PreToolUseHook):
    """优雅打印工具调用信息"""

    def invoke(
        self,
        context: Any,
        *,
        tool_call: dict[str, Any],
    ) -> ToolHookOutput:
        fn = tool_call.get("function") or {}
        tool_name = fn.get("name") or ""
        tool_call_id = tool_call.get("id") or ""
        raw_args = fn.get("arguments") or ""
        try:
            tool_input = json.loads(raw_args) if raw_args else {}
        except json.JSONDecodeError:
            tool_input = {}
        # print(tool_call)
        return ToolHookOutput(allowed=True, maybe_output=None)
