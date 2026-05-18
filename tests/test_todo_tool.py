"""todo_tool 工具：TodoStore 功能测试（原 todo_tool.py __main__）"""

import json

import pytest

from agent.tool.registry import registry
from tools.todo_tool import TodoStore, todo_tool, TODO_SCHEMA


def test_todo_store_basic_operations() -> None:
    """测试 TodoStore 基础读写功能"""
    store = TodoStore()

    # 写入任务
    store.write([
        {"id": "1", "content": "分析需求文档", "status": "completed"},
        {"id": "2", "content": "设计数据库结构", "status": "in_progress"},
        {"id": "3", "content": "编写 API 接口", "status": "pending"},
    ])

    items = store.read()
    assert len(items) == 3
    assert items[0]["id"] == "1"
    assert items[0]["status"] == "completed"
    assert items[1]["status"] == "in_progress"
    assert items[2]["status"] == "pending"


def test_todo_store_merge_update() -> None:
    """测试 merge=True 模式更新现有任务"""
    store = TodoStore()

    # 初始任务
    store.write([
        {"id": "1", "content": "任务1", "status": "pending"},
        {"id": "2", "content": "任务2", "status": "pending"},
    ])

    # 使用 merge 更新任务 2 并添加新任务
    store.write([
        {"id": "2", "content": "任务2已更新", "status": "completed"},
        {"id": "3", "content": "任务3", "status": "in_progress"},
    ], merge=True)

    items = store.read()
    assert len(items) == 3

    # 任务 1 应保持不变
    item1 = next(i for i in items if i["id"] == "1")
    assert item1["status"] == "pending"

    # 任务 2 应被更新
    item2 = next(i for i in items if i["id"] == "2")
    assert item2["status"] == "completed"
    assert item2["content"] == "任务2已更新"

    # 任务 3 是新添加的
    item3 = next(i for i in items if i["id"] == "3")
    assert item3["status"] == "in_progress"


def test_todo_store_replace_mode() -> None:
    """测试 merge=False 替换整个列表"""
    store = TodoStore()

    store.write([
        {"id": "1", "content": "旧任务", "status": "completed"},
        {"id": "2", "content": "旧任务2", "status": "pending"},
    ])

    # 替换模式：清空旧列表
    store.write([
        {"id": "A", "content": "全新任务", "status": "pending"},
    ], merge=False)

    items = store.read()
    assert len(items) == 1
    assert items[0]["id"] == "A"


def test_todo_store_format_for_injection() -> None:
    """测试 format_for_injection 只返回活跃任务"""
    store = TodoStore()

    store.write([
        {"id": "1", "content": "已完成任务", "status": "completed"},
        {"id": "2", "content": "活跃任务", "status": "pending"},
        {"id": "3", "content": "进行中任务", "status": "in_progress"},
        {"id": "4", "content": "已取消任务", "status": "cancelled"},
    ])

    injected = store.format_for_injection()
    assert injected is not None
    # 只包含 pending 和 in_progress 任务
    assert "已完成任务" not in injected
    assert "已取消任务" not in injected
    assert "活跃任务" in injected
    assert "进行中任务" in injected


def test_todo_store_empty_injection() -> None:
    """测试没有活跃任务时返回 None"""
    store = TodoStore()

    store.write([
        {"id": "1", "content": "已完成", "status": "completed"},
    ])

    injected = store.format_for_injection()
    assert injected is None


def test_todo_tool_function() -> None:
    """测试 todo_tool 函数 JSON 输出"""
    store = TodoStore()

    store.write([
        {"id": "1", "content": "任务1", "status": "completed"},
        {"id": "2", "content": "任务2", "status": "pending"},
    ])

    result = todo_tool(store=store)
    data = json.loads(result)

    assert "todos" in data
    assert "summary" in data
    assert data["summary"]["total"] == 2
    assert data["summary"]["completed"] == 1
    assert data["summary"]["pending"] == 1
    assert data["summary"]["in_progress"] == 0


def test_todo_tool_without_store() -> None:
    """测试未提供 store 时返回错误"""
    result = todo_tool(store=None)
    data = json.loads(result)
    assert "error" in data


def test_todo_schema_structure() -> None:
    """测试 TODO_SCHEMA 结构正确"""
    assert "name" in TODO_SCHEMA
    assert TODO_SCHEMA["name"] == "todo"
    assert "parameters" in TODO_SCHEMA
    assert "properties" in TODO_SCHEMA["parameters"]
