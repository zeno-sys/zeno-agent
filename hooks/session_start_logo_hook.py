from typing import Any

from agent.hook.schema import SessionStartHook
from utils.pretty_print import print_session_logo


class SessionStartLogoHook(SessionStartHook):
    """会话开始时打印 Zeno Agent Logo。"""

    def invoke(self,context: Any) -> None:
        print_session_logo()
