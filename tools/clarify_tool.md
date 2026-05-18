# Clarify Tool 澄清工具文档

## 概述

Clarify Tool 是一个交互式澄清工具，允许 AI Agent 向用户提出结构化的多选题或开放式问题，以获取反馈、确认或决策。

---

## 核心功能

### 1. 两种提问模式

| 模式 | 说明 | 使用场景 |
|------|------|----------|
| **多选题** | 提供最多 4 个预设选项，UI 会自动添加第 5 个"其他（自行输入）"选项 | 需要用户在多个方案中选择 |
| **开放式** | 不预设选项，用户自由输入回答 | 需要详细描述或创意性回答 |

### 2. 跨平台支持

- **CLI 模式**：使用方向键导航选择
- **消息平台**：显示为编号列表供选择

---

## 函数签名

```python
def clarify_tool(
    question: str,
    choices: Optional[List[str]] = None,
    callback: Optional[Callable] = None,
) -> str
```

### 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `question` | `str` | ✅ | 要向用户展示的问题文本 |
| `choices` | `List[str]` | ❌ | 最多 4 个预设答案选项 |
| `callback` | `Callable` | ❌ | 平台提供的回调函数，处理实际 UI 交互 |

### 返回值

返回 JSON 字符串，包含以下字段：

```json
{
  "question": "问题文本",
  "choices_offered": ["选项1", "选项2"],
  "user_response": "用户的回答"
}
```

---

## 使用场景

### ✅ 何时使用 Clarify Tool

1. **任务存在歧义** - 需要用户选择处理方式
2. **需要反馈** - 询问任务结果（"效果如何？"）
3. **保存技能/更新记忆** - 询问是否保存新创建的技能
4. **有意义的权衡决策** - 用户需要参与的重要决策

### ❌ 何时不使用

- 简单的危险命令确认（由终端工具处理）
- 低风险的决策（AI 应自行做出合理默认选择）

---

## 配置常量

```python
MAX_CHOICES = 4  # 最多预设选项数量（UI 会自动添加第 5 个"其他"选项）
```

---

## OpenAI Function Calling Schema

```python
CLARIFY_SCHEMA = {
    "name": "clarify",
    "description": "向用户提问以获取澄清、反馈或决策...",
    "parameters": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "向用户展示的问题"
            },
            "choices": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 4,
                "description": "最多 4 个答案选项，省略则变为开放式问题"
            }
        },
        "required": ["question"]
    }
}
```

---

## 代码示例

### 示例 1：多选题模式

```python
from tools.clarify_tool import clarify_tool

# 定义回调函数（通常由平台注入）
def user_callback(question, choices):
    print(f"🤖: {question}")
    for i, choice in enumerate(choices, 1):
        print(f"  {i}. {choice}")
    print("  5. 其他（自行输入）")
    return input("请选择（1-5）或输入自定义回答：")

# 调用工具
result = clarify_tool(
    question="您希望如何处理这个文件？",
    choices=["覆盖", "重命名", "跳过"],
    callback=user_callback
)

print(result)
# 输出：
# {"question": "您希望如何处理这个文件？", "choices_offered": ["覆盖", "重命名", "跳过"], "user_response": "重命名"}
```

### 示例 2：开放式问题

```python
result = clarify_tool(
    question="请详细描述您期望的功能：",
    callback=user_callback
)

print(result)
# 输出：
# {"question": "请详细描述您期望的功能：", "choices_offered": null, "user_response": "我需要一个自动化的数据处理流程..."}
```

### 示例 3：询问反馈

```python
result = clarify_tool(
    question="刚才的任务执行效果如何？",
    choices=["完全符合预期", "需要微调", "结果不正确"],
    callback=user_callback
)
```

---

## 工具注册信息

| 属性 | 值 |
|------|-----|
| 名称 | `clarify` |
| 工具集 | `clarify` |
| 图标 | ❓ |
| 检查函数 | `check_clarify_requirements()`（始终返回 True） |

---

## 错误处理

| 错误情况 | 返回结果 |
|----------|----------|
| 问题文本为空 | `{"error": "Question text is required."}` |
| 选项格式错误 | `{"error": "choices must be a list of strings."}` |
| 回调函数未提供 | `{"error": "Clarify tool is not available in this execution context."}` |
| 回调执行异常 | `{"error": "Failed to get user input: {exc}"}` |

---

## 架构说明

```
┌─────────────────┐
│  clarify_tool   │  ← 本模块（定义 schema、验证、调度）
│   (本文件)      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   callback()    │  ← 平台层提供（cli.py / gateway/run.py）
│                 │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   用户界面      │  ← CLI 或消息平台渲染
│   (UI Layer)    │
└─────────────────┘
```

---

## 注意事项

1. **选项限制**：预设选项最多 4 个，UI 会自动添加第 5 个"其他"选项
2. **空选项处理**：如果传入空列表，会自动转为开放式问题
3. **回调注入**：实际的用户交互由平台层（CLI/网关）通过回调函数注入
4. **返回格式**：始终返回 JSON 字符串，便于解析和日志记录

---

## 设计理念

**一句话概括**：`callback` 是用于**接收用户输入**的函数接口。

Clarify Tool 采用**分层架构**设计：

- **本模块**：负责定义 schema、参数验证、调度逻辑
- **平台层**（`cli.py` / `gateway`）：负责提供实际的用户交互

两者通过 `callback` 回调函数解耦：

```
┌─────────────────┐
│  clarify_tool   │  ← 本模块
│  (schema/验证)  │
└────────┬────────┘
         │ 调用 callback(question, choices)
         ▼
┌─────────────────┐
│   平台层         │  ← cli.py / gateway
│  (UI 交互实现)   │
└────────┬────────┘
         │ 返回用户输入
         ▼
┌─────────────────┐
│   用户          │
└─────────────────┘
```

总之，callback就用用于接收用户输入的。

这种设计的好处：
- **跨平台复用**：同一套工具逻辑可以在 CLI、Web、消息平台等不同环境使用
- **职责分离**：工具开发者专注业务逻辑，平台开发者专注交互实现
- **便于测试**：可以注入 mock callback 进行单元测试

在 Agent 框架中，`callback` 由 `cli.py` 或 `gateway/run.py` 自动注入，无需手动提供。
