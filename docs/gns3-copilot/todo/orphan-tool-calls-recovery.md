# TODO: 修复孤儿 Tool Calls 导致的 Checkpoint 状态不一致

## 问题描述

当 LangGraph agent 在执行过程中异常终止（如服务被强制关闭、进程崩溃等），可能导致 checkpoint 中保存了包含 `tool_calls` 的 `AIMessage`，但没有对应的 `ToolMessage`。这种状态不一致会导致后续对话恢复时出现错误。

### 术语说明

- **孤儿 tool_calls**：`AIMessage` 中包含 `tool_calls` 字段，但消息列表中没有对应的 `ToolMessage`
- **Checkpoint**：LangGraph 用于持久化对话状态的机制
- **状态不一致**：checkpoint 中的消息状态不符合预期的消息对（AIMessage + ToolMessage）

---

## 触发场景

### 场景 1：进程异常终止（主要问题）

```
执行流程：
用户消息 → llm_call → AIMessage(tool_calls) → [Checkpoint 保存]
                                                    ↓
                                            [进程崩溃/服务关闭]
                                                    ↓
                                            tool_node 未执行
                                                    ↓
                                            Checkpoint 中：
                                            - AIMessage (有 tool_calls) ✅
                                            - ToolMessage ❌ 缺失
```

**触发条件：**
- LLM 返回包含 tool_calls 的响应
- Checkpoint 已保存 AIMessage
- 在 tool_node 执行前服务被关闭（kill -9、Ctrl+C、崩溃等）

### 场景 2：达到最大调用次数（已处理）

当前代码通过 `recursion_limit_continue` 函数在 tool_node **执行后**检查剩余步数：

```python
def recursion_limit_continue(state: MessagesState) -> Literal["llm_call", END]:
    last_message = state["messages"][-1]
    if isinstance(last_message, ToolMessage):
        if state["remaining_steps"] < 4:
            return END
        return "llm_call"
    return END
```

**执行流程：**
```
remaining_steps = 5
llm_call → AIMessage(tool_calls) → remaining_steps = 4
         ↓
    should_continue → tool_node（因为有 tool_calls）
         ↓
    tool_node → ToolMessage → remaining_steps = 3
         ↓
    recursion_limit_continue → remaining_steps < 4 → END ✅
```

**结论：** 场景 2 不会产生孤儿 tool_calls，因为 tool_node 总是会执行并生成 ToolMessage。

---

## 修复方案

### 核心思路

在 `stream_chat` 开始时，对于已存在的会话，检测并修复孤儿 tool_calls。

### 修复策略

**策略 A：清除 tool_calls（推荐）**

创建一个新的 `AIMessage`，内容与原消息相同，但不包含 `tool_calls` 字段。

**优点：**
- 简单、干净
- 不会影响后续对话
- 用户可以重新提问

**缺点：**
- 丢失了 LLM 原本的意图（但已经崩溃了，无法恢复）

---

## 实现代码

### 1. 添加修复方法（`agent_service.py`）

```python
async def _fix_orphan_tool_calls(self, graph, config: dict, session_id: str):
    """
    检测并修复孤儿 tool_calls（AIMessage有tool_calls但没有对应ToolMessage）。

    当进程在 tool_node 执行前崩溃时会产生孤儿 tool_calls。

    使用 LangGraph 的 aupdate_state API，安全地创建新的 checkpoint 版本。
    """
    try:
        # 1. 读取当前状态
        state = await graph.aget_state(config)
        if not state or not state.values.get("messages"):
            return

        messages = state.values["messages"]
        last_message = messages[-1]

        # 2. 检测孤儿 tool_calls
        if not (hasattr(last_message, "tool_calls") and last_message.tool_calls):
            return

        # 检查是否有对应的 ToolMessage
        has_tool_message = any(isinstance(m, ToolMessage) for m in messages)

        if has_tool_message:
            return

        log.warning("检测到孤儿 tool_calls: session=%s, 将清除", session_id)

        # 3. 创建修复后的消息（不含 tool_calls）
        from langchain.messages import AIMessage
        fixed_message = AIMessage(
            content=last_message.content,
            id=getattr(last_message, "id", None)
        )

        # 4. 使用 LangGraph API 更新状态（创建新 checkpoint）
        await graph.aupdate_state(config, {"messages": [fixed_message]})

        log.info("孤儿 tool_calls 已修复: session=%s", session_id)

    except Exception as e:
        log.error("修复孤儿 tool_calls 失败: %s", e, exc_info=True)
```

### 2. 在 `stream_chat` 中调用（`agent_service.py`）

在获取 graph 之后、开始 stream 之前添加修复逻辑：

```python
async def stream_chat(
    self,
    message: str,
    session_id: str,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    jwt_token: Optional[str] = None,
    mode: str = "text",
    llm_config: Optional[Dict[str, Any]] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    # ... 现有代码 ...

    # Get or create chat session
    repo = ChatSessionsRepository(self._checkpointer_conn)
    session = await repo.get_session_by_thread(session_id)
    is_new_session = session is None

    if is_new_session:
        # Create new session
        session = await repo.create_session(...)
        log.debug("Created new chat session: thread_id=%s", session_id)

    # ... 设置 context variables ...

    # Build config
    config = {
        "configurable": {
            "thread_id": session_id,
            "project_id": project_id,
        },
        "metadata": {
            "user_id": user_id,
        },
    }

    # Build inputs
    inputs = {
        "messages": [HumanMessage(content=message, id=str(uuid4()))],
        "llm_calls": 0,
        "remaining_steps": 20,
        "mode": mode,
    }

    # Get the compiled graph
    graph = await self._get_graph()

    # 🔧 修复状态：对于已存在的会话，检查并修复孤儿 tool_calls
    if not is_new_session:
        await self._fix_orphan_tool_calls(graph, config, session_id)

    log.debug("LangGraph graph obtained, starting stream")

    # ... 继续现有代码 ...
```

### 3. 需要添加的 import

确保 `agent_service.py` 中有以下 import：

```python
from langchain.messages import ToolMessage  # 用于检测 ToolMessage 类型
```

---

## 对 Checkpoint 数据库的影响

### LangGraph Checkpoint 机制

LangGraph 的 checkpoint 是**版本化**的，每次状态更新会创建新记录：

```
checkpoints 表结构：
- thread_id
- checkpoint_id (递增的版本号)
- checkpoint (序列化的状态数据)
- metadata
- ...
```

### 安全性分析

| 方面 | 影响 | 说明 |
|------|------|------|
| **原始数据** | 保留不变 | `aupdate_state` 创建新版本，不覆盖历史 |
| **数据库结构** | 完全兼容 | 使用 LangGraph 原生 API，不会破坏结构 |
| **并发安全** | 内置保护 | LangGraph 有锁机制处理并发访问 |
| **存储开销** | 很小 | 只增加一条 checkpoint 记录（约几 KB） |
| **可回滚性** | 支持 | 可回滚到修复前的任何版本 |

### 为什么不直接操作数据库

**❌ 危险方式：**
```python
# 直接修改数据库 - 破坏性强
await conn.execute(
    "UPDATE checkpoints SET checkpoint = ? WHERE ...",
    [modified_json]
)
```

**问题：**
- 可能破坏序列化格式
- 不创建新版本，覆盖历史
- 可能导致数据库锁定或损坏
- 违反 LangGraph 的设计原则

**✅ 安全方式：**
```python
# 使用 LangGraph 的 aupdate_state
await graph.aupdate_state(config, {"messages": [fixed_message]})
```

---

## 测试方法

### 方法 1：模拟崩溃测试（推荐）

利用强制关闭服务来模拟崩溃场景：

```
步骤：
1. 启动 GNS3 服务
2. 发送一个会触发 tool_calls 的消息（例如查询拓扑）
3. 观察日志，等待看到 AIMessage 返回（有 tool_calls）
4. 在 tool_node 执行完成前，强制关闭服务：
   - 方式 1: kill -9 <pid>
   - 方式 2: Ctrl+C (如果支持)
5. 重启 GNS3 服务
6. 使用同一个 session_id 继续对话
7. 观察日志，应该看到：
   - "检测到孤儿 tool_calls: session=xxx, 将清除"
   - "孤儿 tool_calls 已修复: session=xxx"
8. 验证对话可以正常进行
```

### 方法 2：单元测试

直接构造孤儿 tool_calls 状态来测试修复逻辑：

```python
# tests/test_agent_service.py

import pytest
from langchain.messages import AIMessage, HumanMessage, ToolMessage

@pytest.mark.asyncio
async def test_fix_orphan_tool_calls():
    """测试孤儿 tool_calls 修复逻辑"""
    from gns3server.agent.gns3_copilot.agent_service import AgentService

    # 创建测试用的 agent service
    service = AgentService("/tmp/test_project")
    await service._get_checkpointer()

    graph = await service._get_graph()
    config = {"configurable": {"thread_id": "test_session"}}

    # 构造孤儿状态：先添加正常消息
    await graph.aupdate_state(
        config,
        {
            "messages": [
                HumanMessage(content="测试消息", id="msg_1"),
                AIMessage(
                    content="让我帮你查一下",
                    id="msg_2",
                    tool_calls=[{
                        "id": "call_123",
                        "name": "get_topology",
                        "args": {"project_id": "test"}
                    }]
                )
                # 注意：没有对应的 ToolMessage
            ],
            "llm_calls": 1,
            "remaining_steps": 20
        }
    )

    # 调用修复逻辑
    await service._fix_orphan_tool_calls(graph, config, "test_session")

    # 验证修复结果
    state = await graph.aget_state(config)
    last_message = state.values["messages"][-1]

    # 应该不再有 tool_calls
    assert not hasattr(last_message, "tool_calls") or not last_message.tool_calls
    assert last_message.content == "让我帮你查一下"

    # 清理
    await service.close()

@pytest.mark.asyncio
async def test_no_fix_when_normal():
    """测试正常状态不会被误修复"""
    from gns3server.agent.gns3_copilot.agent_service import AgentService

    service = AgentService("/tmp/test_project")
    await service._get_checkpointer()

    graph = await service._get_graph()
    config = {"configurable": {"thread_id": "test_session_2"}}

    # 构造正常状态：有完整的 AIMessage + ToolMessage 对
    await graph.aupdate_state(
        config,
        {
            "messages": [
                HumanMessage(content="测试消息", id="msg_1"),
                AIMessage(
                    content="让我帮你查一下",
                    id="msg_2",
                    tool_calls=[{
                        "id": "call_123",
                        "name": "get_topology",
                        "args": {"project_id": "test"}
                    }]
                ),
                ToolMessage(
                    content="拓扑信息：...",
                    tool_call_id="call_123",
                    name="get_topology",
                    id="msg_3"
                )
            ],
            "llm_calls": 1,
            "remaining_steps": 20
        }
    )

    # 记录原始消息数量
    state_before = await graph.aget_state(config)
    msg_count_before = len(state_before.values["messages"])

    # 调用修复逻辑
    await service._fix_orphan_tool_calls(graph, config, "test_session_2")

    # 验证状态未改变
    state_after = await graph.aget_state(config)
    msg_count_after = len(state_after.values["messages"])

    assert msg_count_before == msg_count_after  # 不应该添加新消息
    last_message = state_after.values["messages"][-1]
    assert isinstance(last_message, ToolMessage)  # 最后一条还是 ToolMessage

    # 清理
    await service.close()
```

### 方法 3：增强日志和监控

即使无法主动触发，也可以在生产环境验证修复逻辑是否生效：

```python
# 在 _fix_orphan_tool_calls 中添加详细日志
log.warning("检测到孤儿 tool_calls: session=%s", session_id)
log.info("原始消息: tool_calls=%d, content=%s",
         len(last_message.tool_calls),
         last_message.content[:100])
log.info("修复后: tool_calls=%d",
         len(fixed_message.tool_calls) if hasattr(fixed_message, "tool_calls") else 0)
```

---

## 文件修改清单

### 需要修改的文件

1. **`gns3server/agent/gns3_copilot/agent_service.py`**
   - 添加 `_fix_orphan_tool_calls` 方法
   - 在 `stream_chat` 方法中调用修复逻辑

### 需要添加的测试文件（可选）

2. **`tests/test_agent_service.py`**（新建或添加到现有测试文件）
   - `test_fix_orphan_tool_calls()` - 测试孤儿 tool_calls 修复
   - `test_no_fix_when_normal()` - 测试正常状态不被误修复

---

## 实施步骤

1. ✅ 创建待办文档（当前文档）
2. ⬜ 在 `agent_service.py` 中添加 `_fix_orphan_tool_calls` 方法
3. ⬜ 在 `stream_chat` 中调用修复逻辑
4. ⬜ 使用模拟崩溃方法测试修复效果
5. ⬜ 添加单元测试（可选）
6. ⬜ 更新相关文档（如有必要）

---

## 相关代码文件

- **主要修改文件**: `gns3server/agent/gns3_copilot/agent_service.py`
- **相关文件**: `gns3server/agent/gns3_copilot/agent/gns3_copilot.py`
- **测试文件**: `tests/test_agent_service.py` (待创建)

---

## 参考文档

- [LangGraph Checkpointer 文档](https://langchain-ai.github.io/langgraph/concepts/low_level/#checkpointer)
- [LangGraph State Management](https://langchain-ai.github.io/langgraph/concepts/low_level/#state)
- [GNS3-Copilot AI Chat API 设计](../ai-chat-api-design.md)
