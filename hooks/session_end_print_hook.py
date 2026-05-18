from typing import Any

from agent.hook.schema import SessionEndHook
from utils.pretty_print import print_session_end


class SessionEndPrintHook(SessionEndHook):
    """会话结束时打印结束语。"""

    def invoke(self,context: Any) -> None:
        session_id = getattr(context, "session_id", "unknown_session")
        print_session_end(str(session_id))
