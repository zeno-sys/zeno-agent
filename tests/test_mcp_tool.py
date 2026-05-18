"""MCP 工具测试：发现、状态查询与 dispatch。

依赖本地 MCP 服务器配置（~/.hermes/config.yaml）。
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

from agent.mcp.mcp_tool import discover_mcp_tools, get_mcp_status, _MCP_AVAILABLE
from agent.tool.registry import registry





@pytest.fixture(scope="module")
def mcp_tool_names() -> list[str]:
    """发现并注册所有 MCP 工具，返回工具名列表。"""
    names = discover_mcp_tools()
    return names


def test_discover_mcp_tools_returns_list(mcp_tool_names: list[str]) -> None:
    """discover_mcp_tools 应返回列表（空或有元素）。"""
    assert isinstance(mcp_tool_names, list)
    print(f"\nDiscovered MCP tools: {mcp_tool_names}")


def test_get_mcp_status_structure() -> None:
    """get_mcp_status 应返回标准结构的状态列表。"""
    status = get_mcp_status()
    assert isinstance(status, list)
    for s in status:
        assert "name" in s
        assert "transport" in s
        assert "tools" in s
        assert "connected" in s
    print(f"\nMCP status: {json.dumps(status, ensure_ascii=False, indent=2)}")


def test_mcp_tools_registered_in_registry(mcp_tool_names: list[str]) -> None:
    """发现的工具应在 registry 中可查询 schema。"""
    if not mcp_tool_names:
        pytest.skip("No MCP tools discovered")

    all_schemas = registry.get_tool_schema()
    assert isinstance(all_schemas, list)

    for name in mcp_tool_names:
        schema = registry.get_tool_schema(name)
        assert schema is not None
        assert schema.get("type") == "function"
        assert schema.get("function", {}).get("name") == name

    print(f"\nRegistered MCP tools count: {len(mcp_tool_names)}")


def test_mcp_tool_dispatch_word_server_create_empty_txt(mcp_tool_names: list[str]) -> None:
    tool_name = "mcp_word_server_create_empty_txt"
    if tool_name not in mcp_tool_names:
        pytest.skip(f"Tool {tool_name} not available in this environment")

    result = registry.dispatch(tool_name, {"filename": "example"})
    data: dict[str, Any] = json.loads(result)

    # 即使失败也应返回结构化 JSON（含 error 字段）
    assert isinstance(data, dict)
    print(f"\nDispatch result for {tool_name}: {json.dumps(data, ensure_ascii=False, indent=2)}")
