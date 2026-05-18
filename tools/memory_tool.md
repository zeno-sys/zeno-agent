# Memory Tool 详解

## 概述

Memory Tool 是一个持久化的策展式记忆系统，为 AI Agent 提供**跨会话保持**的有限容量文件支持的记忆功能。它允许 Agent 在多次对话之间保存和检索重要信息，避免用户重复说明同样的事情。

---

## 核心设计哲学

### 双重存储模式


| 存储         | 文件       |             | 用途                              |     |
| ---------- | -------- | ----------- | ------------------------------- | --- |
| **Memory** |          | `MEMORY.md` | Agent 的个人笔记：环境事实、项目规范、工具特性、经验教训 |     |
|            | **User** | `USER.md`   | 用户信息：偏好、沟通风格、期望、工作习惯            |     |


### 冻结快照模式 (Frozen Snapshot Pattern)

这是 Memory Tool 的关键设计：

- **系统提示注入**：会话开始时，记忆内容作为**冻结快照**注入系统提示
- **会话中写入**：立即持久化到磁盘，但**不会**更新系统提示
- **目的**：保持前缀缓存 (prefix cache) 稳定，提升性能
- **刷新时机**：下一次会话启动时加载最新状态

```
会话开始 → 加载 MEMORY.md + USER.md → 注入系统提示 (冻结)
                                         ↓
    会话中写入 → 更新磁盘文件 ──→ 不影响当前系统提示
                                         ↓
    下次会话开始 ←───────────────── 加载最新内容
```

---

## 技术规格

### 存储限制


| 存储类型   | 字符限制     | 默认配置                     |
| ------ | -------- | ------------------------ |
| Memory | 2,200 字符 | `memory_char_limit=2200` |
| User   | 1,375 字符 | `user_char_limit=1375`   |


> **为什么用字符而非 Token？** 字符计数与模型无关，确保跨不同 LLM 的一致性。

### 条目分隔符

```python
ENTRY_DELIMITER = "\n§\n"  # 使用 § (section sign) 作为条目分隔符
```

条目可以是多行文本，通过 `§` 符号分隔。

---

## API 接口

### 主函数：`memory_tool()`

```python
def memory_tool(
    action: str,           # 操作类型
    target: str = "memory", # 存储目标: "memory" | "user"
    content: str = None,    # 条目内容 (add/replace 必需)
    old_text: str = None,  # 用于定位条目的子串 (replace/remove 必需)
    store: Optional[MemoryStore] = None,  # 存储实例
) -> str:  # 返回 JSON 格式结果
```

### 支持的 Action


| Action    | 描述     | 必需参数                  |
| --------- | ------ | --------------------- |
| `add`     | 添加新条目  | `content`             |
| `replace` | 替换现有条目 | `old_text`, `content` |
| `remove`  | 删除条目   | `old_text`            |


### 使用示例

```python
# 添加记忆
memory_tool(
    action="add",
    target="memory",
    content="项目使用 Poetry 管理依赖，Python 版本要求 3.11+"
)

# 更新用户信息
memory_tool(
    action="add",
    target="user",
    content="用户偏好简洁的回答，避免冗长解释"
)

# 替换条目（使用子串匹配）
memory_tool(
    action="replace",
    target="memory",
    old_text="Poetry",
    content="项目使用 uv 管理依赖，Python 版本要求 3.12+"
)

# 删除条目
memory_tool(
    action="remove",
    target="user",
    old_text="简洁"
)
```

---

## 核心类：MemoryStore

### 初始化

```python
store = MemoryStore(
    memory_char_limit=2200,  # Memory 存储字符限制
    user_char_limit=1375     # User 存储字符限制
)
store.load_from_disk()  # 从磁盘加载并创建冻结快照
```

### 双状态管理

```python
class MemoryStore:
    def __init__(self, ...):
        # 活跃状态 - 会话中可变
        self.memory_entries: List[str] = []
        self.user_entries: List[str] = []
        
        # 冻结快照 - 仅用于系统提示
        self._system_prompt_snapshot: Dict[str, str] = {"memory": "", "user": ""}
```

### 冻结快照获取

冻结快照（Frozen Snapshot）是 Memory Tool 的核心机制，用于系统提示注入。

#### 获取方式

```python
from tools.memory_tool import MemoryStore

store = MemoryStore()
store.load_from_disk()  # 加载时自动捕获冻结快照

# 获取 memory 快照
memory_block = store.format_for_system_prompt("memory")

# 获取 user 快照  
user_block = store.format_for_system_prompt("user")
```

#### 重要特性

1. **只在 `load_from_disk()` 时捕获**
   - 快照在加载时冻结，反映磁盘文件状态
   - 后续通过 `add/replace/remove` 修改的条目**不会**反映在快照中
   - 下次会话启动时，新的 `load_from_disk()` 会刷新快照

2. **返回格式**（带容量指示器的格式块）
   ```
   ══════════════════════════════════════════════
   MEMORY (your personal notes) [24% — 122/500 chars]
   ══════════════════════════════════════════════
   项目使用 uv 管理依赖，Python 版本要求 3.12+
   §
   用户的代码库使用 Pydantic v2...
   ```

3. **空状态返回 `None`**
   - 如果加载时没有条目，返回 `None` 而非空字符串
   - 调用方应检查返回值再使用

#### 双状态对比

| 状态 | 获取方法 | 时效性 | 用途 |
|------|---------|--------|------|
| **冻结快照** | `format_for_system_prompt()` | 会话开始时固定 | 系统提示注入 |
| **活跃状态** | `store.memory_entries` | 实时更新 | 工具响应、写入磁盘 |

### 关键方法


| 方法                                       | 用途             |
| ---------------------------------------- | -------------- |
| `load_from_disk()`                       | 从文件加载并创建系统提示快照 |
| `add(target, content)`                   | 添加条目（带容量检查）    |
| `replace(target, old_text, new_content)` | 子串匹配替换         |
| `remove(target, old_text)`               | 子串匹配删除         |
| `format_for_system_prompt(target)`       | 获取冻结快照用于系统提示   |
| `save_to_disk(target)`                   | 持久化到文件         |


---

## 文件存储结构

### 存储位置

```python
def get_memory_dir() -> Path:
    return get_hermes_home() / "memories"
```

文件存储在 `HERMES_HOME/memories/` 目录下：

- `MEMORY.md` - Agent 笔记
- `USER.md` - 用户画像
- `*.lock` - 文件锁（用于并发控制）

### 文件格式示例

**MEMORY.md:**

```markdown
项目使用 uv 管理依赖，Python 版本要求 3.12+
§
用户的代码库使用 Pydantic v2，避免使用已弃用的 .dict() 方法
§
运行测试使用: pytest -xvs tests/
```

**USER.md:**

```markdown
用户偏好简洁的回答，避免冗长解释
§
用户是高级工程师，不需要基础概念解释
§
用户的时区是 UTC+8
```

---

## 并发控制

### 文件锁定机制

支持跨平台文件锁定（Unix/Windows）：

```python
# Unix: fcntl.flock
# Windows: msvcrt.locking

@contextmanager
def _file_lock(path: Path):
    lock_path = path.with_suffix(path.suffix + ".lock")
    # 获取独占锁，确保读-修改-写操作的原子性
```

### 原子写入

使用临时文件 + 原子重命名，避免写入过程中的数据损坏：

```python
def _write_file(path: Path, entries: List[str]):
    # 1. 写入临时文件
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    
    # 2. 原子替换
    os.replace(tmp_path, str(path))
```

---

## 安全防护

### 内容扫描

所有写入的内容都会经过安全扫描，防止提示注入和数据渗出：

```python
_MEMORY_THREAT_PATTERNS = [
    # 提示注入
    (r'ignore\s+(previous|all|above|prior)\s+instructions', "prompt_injection"),
    (r'you\s+are\s+now\s+', "role_hijack"),
    (r'disregard\s+(your|all|any)\s+(instructions|rules|guidelines)', "disregard_rules"),
    
    # 数据渗出
    (r'curl\s+[^\n]*\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD)', "exfil_curl"),
    (r'wget\s+[^\n]*\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD)', "exfil_wget"),
    
    # 持久化后门
    (r'authorized_keys', "ssh_backdoor"),
]

_INVISIBLE_CHARS = {
    '\u200b', '\u200c', '\u200d',  # 零宽字符
    '\ufeff',  # BOM
}
```

### 扫描流程

```
用户请求写入 → _scan_memory_content() → 通过 → 写入存储
                         ↓
                    发现威胁 → 返回错误，阻止写入
```

---

## OpenAI Function Calling Schema

### 工具定义

```json
{
  "name": "memory",
  "description": "Save durable information to persistent memory...",
  "parameters": {
    "type": "object",
    "properties": {
      "action": {
        "type": "string",
        "enum": ["add", "replace", "remove"]
      },
      "target": {
        "type": "string",
        "enum": ["memory", "user"]
      },
      "content": { "type": "string" },
      "old_text": { "type": "string" }
    },
    "required": ["action", "target"]
  }
}
```

### 何时保存（行为指导）

工具描述中包含了行为指导：

**应该保存的场景：**

- 用户纠正你或说"记住这个"/"下次别这样"
- 用户分享偏好、习惯或个人细节（姓名、角色、时区、编码风格）
- 你发现环境信息（操作系统、已安装工具、项目结构）
- 你学到特定于该用户的约定、API 特性或工作流
- 识别出将来会话中有用的稳定事实

**优先级排序：**

```
用户偏好和纠正 > 环境事实 > 程序性知识
```

**不应该保存：**

- 任务进度、会话结果、已完成工作日志
- 临时的 TODO 状态（使用 `session_search` 从转录中检索）
- 微不足道/明显的信息
- 容易重新发现的内容
- 原始数据转储

---

## 返回格式

### 成功响应

```json
{
  "success": true,
  "target": "memory",
  "entries": ["条目1", "条目2", "..."],
  "usage": "45% — 990/2,200 chars",
  "entry_count": 3,
  "message": "Entry added."
}
```

### 错误响应

```json
{
  "success": false,
  "error": "Memory at 2,100/2,200 chars. Adding this entry (150 chars) would exceed the limit.",
  "current_entries": ["..."],
  "usage": "2,100/2,200"
}
```

### 多重匹配错误

```json
{
  "success": false,
  "error": "Multiple entries matched 'Python'. Be more specific.",
  "matches": [
    "项目使用 Python 3.11...",
    "Python 编码规范要求..."
  ]
}
```

---

## 系统集成

### 工具注册

```python
from tools.registry import registry, tool_error

registry.register(
    name="memory",
    toolset="memory",
    schema=MEMORY_SCHEMA,
    handler=lambda args, **kw: memory_tool(...),
    check_fn=check_memory_requirements,
    emoji="🧠",
)
```

### 系统提示注入格式

```
══════════════════════════════════════════════
MEMORY (your personal notes) [45% — 990/2,200 chars]
══════════════════════════════════════════════
项目使用 uv 管理依赖，Python 版本要求 3.12+
§
用户的代码库使用 Pydantic v2...

══════════════════════════════════════════════
USER PROFILE (who the user is) [30% — 410/1,375 chars]
══════════════════════════════════════════════
用户偏好简洁的回答...
§
用户的时区是 UTC+8
```

---

## 使用建议

### 最佳实践

1. **主动保存**：不要等到用户要求才保存重要信息
2. **保持简洁**：记忆有容量限制，只保存真正有价值的信息
3. **使用子串匹配**：replace/remove 时使用足够独特的子串避免歧义
4. **定期清理**：删除过时或不再相关的条目
5. **分类存储**：用户信息放 `user`，技术知识放 `memory`

### 内容优化

**好的记忆条目：**

```
用户偏好简洁的回答，避免冗长解释
```

**不好的记忆条目：**

```
在2024年1月15日的会话中，用户让我记住他喜欢简洁的回答，因为他觉得太长的回答很烦人，浪费时间...
```

---

## 总结

Memory Tool 通过精心设计的**双存储 + 冻结快照**模式，为 AI Agent 提供了：

1. **持久性** - 跨会话保持记忆
2. **安全性** - 注入/渗出防护扫描
3. **可靠性** - 文件锁 + 原子写入
4. **性能** - 冻结快照保持前缀缓存稳定
5. **有限性** - 容量限制强制策展式记忆

这是 Agent 个性化和上下文连续性的基础设施。