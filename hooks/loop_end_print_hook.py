from dataclasses import asdict
from typing import Any

from agent.hook.schema import LoopEndHook
from utils.pretty_print import print_ai_output, print_end_state, print_run_event_stream_done


class LoopEndPrintHook(LoopEndHook):
    """Loop结束时打印最后一轮输出和状态。"""

    def invoke(self,context: Any) -> None:
        state = context.state
        print_run_event_stream_done()
        if getattr(state, "transition_reason", None) == "api_error":
            print_ai_output(
                "抱歉，刚刚和模型服务通信失败了（可能是网络抖动、限流或服务暂时不可用）。"
                "你可以稍后重试，或精简输入后再试一次。"
            )
            print_end_state(asdict(state))
            return
        print_end_state(asdict(state))
