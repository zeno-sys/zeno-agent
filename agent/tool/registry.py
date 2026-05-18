from agent.tool.schema import OpenAIFunctionSchema, OpenAIToolSchema, ToolEntry
import threading
from collections.abc import Sequence
from typing import Any, Callable
import json
import logging

logger = logging.getLogger(__name__)


def _coerce_openai_tool_schema(schema: dict[str, Any] | OpenAIToolSchema) -> OpenAIToolSchema:
    if isinstance(schema, OpenAIToolSchema):
        return schema
    if schema.get("type") == "function" and isinstance(schema.get("function"), dict):
        return OpenAIToolSchema.model_validate(schema)
    return OpenAIToolSchema(
        type="function",
        function=OpenAIFunctionSchema.model_validate(schema),
    )


class ToolRegistry:
    """Agent工具注册中心"""

    def __init__(self):
        self._tools: dict[str, ToolEntry] = {}
        self._lock = threading.RLock()

    def get_entry(self, name: str) -> ToolEntry | None:
        with self._lock:
            return self._tools.get(name)

    def get_toolset_for_tool(self, name: str) -> str | None:
        """返回工具所属的工具集，或None。"""
        entry = self.get_entry(name)
        return entry.toolset if entry else None

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        *,
        name: str,
        toolset: str,
        schema: dict[str, Any] | OpenAIToolSchema,
        handler: Callable,
        check_fn: Callable | None = None,
        requires_env: list[str] | None = None,
        is_async: bool = False,
        description: str = "",
        emoji: str = "",
        max_result_size_chars: int | float | None = None,
    ) -> None:
        """注册一个工具"""
        tool_schema = _coerce_openai_tool_schema(schema)
        entry = ToolEntry(
            name=name,
            toolset=toolset,
            tool_schema=tool_schema,
            handler=handler,
            check_fn=check_fn,
            requires_env=requires_env or [],
            is_async=is_async,
            description=description if description else tool_schema.function.description,
            emoji=emoji,
            max_result_size_chars=max_result_size_chars,
        )
        with self._lock:
            self._tools[name] = entry
    def deregister(self, name: str) -> None:
        with self._lock:
            self._tools.pop(name, None)     
    

    # ------------------------------------------------------------------
    # Schema retrieval
    # ------------------------------------------------------------------
    def get_tool_schema(self, name: str | None = None) -> dict | list[dict]:
        with self._lock:
            if name is None:
                return [tool.tool_schema.model_dump() for tool in self._tools.values()]
            else:
                return self._tools[name].tool_schema.model_dump()

    def get_tool_schema_by_toolset(
        self, toolsets: str | Sequence[str]
    ) -> list[dict]:
        """Return OpenAI tool schema dicts for tools in the given toolset(s)."""
        if isinstance(toolsets, str):
            wanted = {toolsets}
        else:
            wanted = set(toolsets)
        with self._lock:
            return [
                tool.tool_schema.model_dump()
                for tool in self._tools.values()
                if tool.toolset in wanted
            ]

    def get_tool_handler(self, name: str | None = None) -> Callable:
        with self._lock:
            if name is None:
                return {name: tool.handler for name, tool in self._tools.items()}
            else:
                return self._tools[name].handler
    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def dispatch(self, name: str, args: dict, extra_args: dict = {}) -> str:
        """Execute a tool handler by name.

        Args:
            name: 工具名称
            args: 大模型生成的工具调用参数
            extra_args: 工具调用时需要的额外参数（非大模型生成的参数，而是保证系统运行的必要参数），如各种上下文信息，回调函数等

        Returns:
            str: 工具调用结果
        """
        entry = self.get_entry(name)
        if not entry:
            return json.dumps({"error": f"Unknown tool: {name}"})
        try:
            if entry.is_async:
                from model_tools import _run_async
                # 在新线程的中的 event loop 里跑 async 函数
                return _run_async(entry.handler(args, extra_args))
            return entry.handler(args, extra_args)
        except Exception as e:
            logger.exception("Tool %s dispatch error: %s", name, e)
            return json.dumps({"error": f"Tool execution failed: {type(e).__name__}: {e}"})

    async def dispatch_async(self, name: str, args: dict, extra_args: dict = {}) -> str:
        """Execute a tool handler on the **current** event loop.

        Async handlers (``is_async``) are awaited directly; sync handlers
        are invoked like :meth:`dispatch`. Error JSON matches :meth:`dispatch`.

        Use inside ``async def`` routes or agents when you must share one loop
        (cached httpx / AsyncOpenAI, FastAPI request scope, etc.).
        """
        entry = self.get_entry(name)
        if not entry:
            return json.dumps({"error": f"Unknown tool: {name}"})
        try:
            if entry.is_async:
                return await entry.handler(args, extra_args)
            return entry.handler(args, extra_args)
        except Exception as e:
            logger.exception("Tool %s dispatch_async error: %s", name, e)
            return json.dumps({"error": f"Tool execution failed: {type(e).__name__}: {e}"})


# Module-level singleton
registry = ToolRegistry()

