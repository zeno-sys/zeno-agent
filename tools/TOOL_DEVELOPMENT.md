# 工具开发指南

本文档介绍如何定义工具、注册到工具注册表，以及通过 `dispatch` 执行时如何解析参数。

---

## 核心概念

工具系统采用**三层架构**：

```
┌─────────────────┐
│   工具定义层     │  ← 你开发的工具（如 clarify_tool.py）
│  (handler实现)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   注册表层       │  ← registry.py 统一管理
│  (schema/注册)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   执行层         │  ← dispatch / dispatch_async
│  (参数解析/调用) │
└─────────────────┘
```

---

## 第一步：定义工具函数

工具函数没有固定的参数签名要求，你可以根据业务需要定义任意参数。比如：

```python
def clarify_tool(
    question: str,
    choices: Optional[List[str]] = None,
    callback: Optional[Callable] = None,
) -> str:
    """
    澄清工具 - 向用户提问获取反馈。

    Args:
        question: 问题文本（大模型生成）
        choices: 选项列表（大模型生成，可选）
        callback: 用户交互回调（系统注入）

    Returns:
        str: JSON 格式的工具执行结果
    """
    if callback is None:
        return json.dumps({"error": "No callback provided"}, ensure_ascii=False)

    user_response = callback(question, choices)

    return json.dumps({
        "question": question,
        "user_response": user_response,
    }, ensure_ascii=False)
```

**参数分类**：

| 参数类型 | 来源 | 典型命名 | 说明 |
|----------|------|----------|------|
| LLM 参数 | 大模型生成 | `question`, `choices`, `action` | 与用户意图相关的业务参数 |
| 系统参数 | 运行时注入 | `callback`, `store` | 系统上下文、回调函数、存储实例等 |

**设计原则**：
- 工具函数专注业务逻辑，不关心参数如何从 `dispatch` 传递过来
- 参数映射在注册时通过 lambda 表达式完成
- 大模型只能控制 LLM 参数，无法控制系统参数

---

## 第二步：定义 OpenAI Schema

每个工具都需要定义符合 OpenAI Function Calling 格式的 schema：

```python
MY_TOOL_SCHEMA = {
    "name": "my_tool",           # 工具名称（唯一标识）
    "description": "工具的描述，说明功能和使用场景...",
    "parameters": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "问题描述，告诉大模型这个参数的用途"
            },
            "choices": {
                "type": "array",
                "items": {"type": "string"},
                "description": "选项列表"
            }
        },
        "required": ["question"]   # 必填参数列表
    }
}
```

### Schema 要素

| 字段 | 说明 |
|------|------|
| `name` | 工具唯一标识符，与注册时一致 |
| `description` | 大模型选择工具的依据，描述清楚功能和使用场景 |
| `parameters.properties` | 定义每个参数的类型和描述 |
| `parameters.required` | 必填参数，大模型必须提供这些值 |

---

## 第三步：注册工具

在 `tools/__init__.py` 的 `register_all_tools()` 函数中注册。

`registry.register()` 接收的 `handler` 必须符合**通用执行器签名**：`(args: dict, extra_args: dict) -> str`。

如果你的工具函数有自定义参数签名，使用 **lambda 表达式** 进行参数映射：

```python
from tools.clarify_tool import CLARIFY_SCHEMA, clarify_tool, check_clarify_requirements

registry.register(
    name="clarify",
    toolset="clarify",
    schema=CLARIFY_SCHEMA,
    # 通过 lambda 将通用执行器的 (args, extra_args) 映射到工具函数的具名参数
    handler=lambda args, extra_args: clarify_tool(
        question=args.get("question", ""),       # 从 args 提取大模型参数
        choices=args.get("choices"),
        callback=extra_args.get("callback")),    # 从 extra_args 提取系统参数
    check_fn=check_clarify_requirements,
    emoji="❓",
)
```

### 参数映射示例

| 工具函数签名 | 注册时的 lambda 映射 |
|-------------|---------------------|
| `clarify_tool(question, choices, callback)` | `lambda args, extra_args: clarify_tool(args.get("question"), args.get("choices"), extra_args.get("callback"))` |
| `todo_tool(todos, merge, store)` | `lambda args, extra_args: todo_tool(args.get("todos"), args.get("merge", False), extra_args.get("store"))` |
| `memory_tool(action, target, content, store)` | `lambda args, extra_args: memory_tool(args.get("action"), args.get("target", "memory"), args.get("content"), extra_args.get("store"))` |

**关键理解**：
- `dispatch` 调用 `handler(args, extra_args)`（固定签名）
- `handler` 通过 lambda 将两个字典映射到你的工具函数参数
- 工具函数本身完全独立，不关心 dispatch 的存在

---

## 第四步：执行工具（Dispatch）

通过注册表执行工具有两种方式：

### 同步执行：dispatch

```python
from agent.tool.registry import registry

# 大模型生成的参数
tool_args = {
    "question": "你想做什么？",
    "choices": ["选项A", "选项B"]
}

# 系统注入的额外参数
extra_args = {
    "callback": my_callback_function,  # 用户交互回调
    "store": some_store_instance       # 存储实例等
}

# 执行工具
result = registry.dispatch("clarify", tool_args, extra_args)
print(result)  # 返回 JSON 字符串
```

### 异步执行：dispatch_async

```python
result = await registry.dispatch_async("clarify", tool_args, extra_args)
```

### dispatch 参数解析流程

```
registry.dispatch(name, args, extra_args)
         │
         ▼
    ┌─────────────┐
    │ 查找工具     │ 通过 name 找到 ToolEntry
    └──────┬──────┘
           │
           ▼
    ┌─────────────┐
    │ 调用 handler │ entry.handler(args, extra_args)
    │             │ 传入两个字典参数
    └──────┬──────┘
           │
           ▼
    ┌─────────────┐
    │ 返回结果     │ JSON 字符串
    └─────────────┘
```

---

## 完整示例：Clarify Tool

```python
#!/usr/bin/env python3
"""Clarify Tool - 交互式澄清工具"""

import json
from typing import List, Optional, Callable

MAX_CHOICES = 4

# ------------------- 工具实现 -------------------

def clarify_tool(
    question: str,
    choices: Optional[List[str]] = None,
    callback: Optional[Callable] = None,
) -> str:
    """向用户提问，获取澄清或决策。"""
    if not question or not question.strip():
        return json.dumps({"error": "Question text is required."}, ensure_ascii=False)

    if callback is None:
        return json.dumps(
            {"error": "Clarify tool is not available in this execution context."},
            ensure_ascii=False,
        )

    user_response = callback(question, choices)

    return json.dumps({
        "question": question,
        "choices_offered": choices,
        "user_response": str(user_response).strip(),
    }, ensure_ascii=False)


def check_clarify_requirements() -> bool:
    """检查工具前置条件。"""
    return True


# ------------------- OpenAI Schema -------------------

CLARIFY_SCHEMA = {
    "name": "clarify",
    "description": (
        "向用户提问以获取澄清、反馈或决策。支持多选题和开放式问题。\n"
        "使用场景：任务歧义时需要用户选择处理方式、询问反馈、重要决策等。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "向用户展示的问题文本",
            },
            "choices": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": MAX_CHOICES,
                "description": "最多 4 个答案选项，省略则变为开放式问题",
            },
        },
        "required": ["question"],
    },
}


# ------------------- 注册（在 __init__.py 中） -------------------

# from agent.tool.registry import registry
# registry.register(
#     name="clarify",
#     toolset="clarify",
#     schema=CLARIFY_SCHEMA,
#     handler=lambda args, extra_args: clarify_tool(
#         question=args.get("question", ""),
#         choices=args.get("choices"),
#         callback=extra_args.get("callback")),
#     check_fn=check_clarify_requirements,
#     emoji="❓",
# )


# ------------------- 本地测试 -------------------

if __name__ == "__main__":
    # 模拟 callback 实现
    def mock_callback(question, choices):
        print(f"🤖: {question}")
        if choices:
            for i, c in enumerate(choices, 1):
                print(f"  {i}. {c}")
        return "选项A"

    # 模拟 dispatch 调用
    from agent.tool.registry import registry
    registry.register(...)

    args = {"question": "你想做什么？", "choices": ["选项A", "选项B"]}
    extra = {"callback": mock_callback}

    result = registry.dispatch("clarify", args, extra)
    print(result)
```

---

## 参数解析最佳实践

### 1. 参数提取模式

```python
# ✅ 推荐：使用 .get() 并提供默认值
question = args.get("question", "")
merge = args.get("merge", False)

# ⚠️ 注意：不要用 [] 访问，避免 KeyError
# question = args["question"]  # 如果大模型没提供会报错
```

### 2. 必需参数验证

```python
if not question or not question.strip():
    return json.dumps({"error": "Question is required"}, ensure_ascii=False)
```

### 3. 类型转换

```python
# 大模型可能传入字符串数字，需要转换
limit = int(args.get("limit", 10))
```

### 4. extra_args 检查

```python
# 对于必须依赖外部资源的工具
callback = extra_args.get("callback")
if callback is None:
    return json.dumps(
        {"error": "This tool requires a callback but none was provided"},
        ensure_ascii=False
    )
```

---

## 工具开发 checklist

- [ ] 定义工具处理函数，接收 `(args, extra_args)` 两个参数
- [ ] 定义符合 OpenAI 格式的 schema
- [ ] 在 `tools/__init__.py` 中注册工具
- [ ] 使用 `args.get()` 安全提取大模型参数
- [ ] 使用 `extra_args.get()` 获取系统注入的上下文
- [ ] 返回 JSON 字符串格式的结果
- [ ] 处理错误情况，返回包含 `"error"` 字段的 JSON
- [ ] 提供 `check_fn` 前置检查函数（可选）
- [ ] 本地测试通过 `if __name__ == "__main__":` 块

---

## 参考现有工具

| 工具 | 功能 | 关键参数 |
|------|------|----------|
| `clarify_tool.py` | 用户交互 | `callback` (extra_args) |
| `todo_tool.py` | 任务管理 | `store` (extra_args) |
| `memory_tool.py` | 持久化记忆 | `store` (extra_args) |
| `internet_search.py` | 网络搜索 | API key (env) |
