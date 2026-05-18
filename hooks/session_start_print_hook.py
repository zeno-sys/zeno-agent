from typing import Any

from agent.hook.schema import SessionStartHook
from utils.pretty_print import print_session_start


class SessionStartPrintHook(SessionStartHook):
    """会话开始时打印欢迎语。"""

    def invoke(self,context: Any) -> None:
        session_id = getattr(context, "session_id", "unknown_session")
        print_session_start(str(session_id))
