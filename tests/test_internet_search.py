"""internet_search 工具：注册、schema 与 dispatch（原 internet_search.py __main__）。"""

import json
import os

import pytest

from agent.tool.registry import registry
from tools import register_all_tools


@pytest.fixture(scope="module", autouse=True)
def _register_tools() -> None:
    print("register_all_tools")
    register_all_tools()


def test_internet_search_tool_schema() -> None:
    schema = registry.get_tool_schema("internet_search")
    dumped = json.dumps(schema, ensure_ascii=False, indent=2)
    assert "internet_search" in dumped
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "internet_search"
    print(dumped)


@pytest.mark.skipif(not os.getenv("TAVILY_API_KEY"), reason="TAVILY_API_KEY not set")
def test_internet_search_dispatch() -> None:
    result = registry.dispatch("internet_search", {"query": "Python"})
    data = json.loads(result)
    assert "error" not in data
    print(data)
