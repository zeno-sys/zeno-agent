from typing import Any

from agent.hook.schema import PostToolUseHook, ToolHookOutput
from utils.pretty_print import print_tool_result


class ToolResultPrintHook(PostToolUseHook):
    """优雅打印工具结果"""

    def invoke(
        self,
        context: Any,
        *,
        tool_call: dict[str, Any],
        result: Any,
    ) -> ToolHookOutput:
        tool_call_id = tool_call.get("id") or ""
        output = result if isinstance(result, str) else str(result)
        # print(result)
        return ToolHookOutput(allowed=True, maybe_output=output)
