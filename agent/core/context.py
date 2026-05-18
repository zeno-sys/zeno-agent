from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from agent.hook.manager import HookManager
from tools.memory_tool import MemoryStore
from tools.todo_tool import TodoStore

if TYPE_CHECKING:
    from backends.base import BackendProtocol

@dataclass
class AgentState:
    '''单轮循环状态'''
    messages: list = None                   # 最小循环状态：历史消息、回合次数以及继续循环的原因。
    turn_count: int = 1                     # 回合次数
    transition_reason: str | None = None    # 继续循环的原因

    def to_dict(self) -> dict:
        return {
            "messages": self.messages or [],
            "turn_count": self.turn_count,
            "transition_reason": self.transition_reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AgentState":
        return cls(
            messages=list(data.get("messages") or []),
            turn_count=int(data.get("turn_count", 1)),
            transition_reason=data.get("transition_reason"),
        )


@dataclass
class AgentContext:
    '''跨会话共享上下文'''
    state: AgentState = None                       # 单轮推理级上下文
    session_id: str | None = None                  # 跨会话共享会话ID
    hook_manager: HookManager | None = None        # 跨会话共享 Hook 管理器
    # 内置工具依赖（通过 registry.dispatch 的 extra_args["store"] 注入）
    todo_store: TodoStore = None                         # tools.todo_tool.TodoStore
    memory_store: MemoryStore = None                       # tools.memory_tool.MemoryStore
    # 交互式澄清工具依赖（通过 registry.dispatch 的 extra_args["callback"] 注入）
    clarify_callback: Callable[[str, Sequence[str] | None], str] | None = None
    # 文件后端（BackendProtocol；默认 FilesystemBackend，经 extra_args 注入 backend_file 工具集）
    filesystem_backend: BackendProtocol | None = None

