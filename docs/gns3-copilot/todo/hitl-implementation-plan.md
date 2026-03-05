# GNS3 Copilot HITL 功能实现方案

## 概述

本文档详细描述了 GNS3 Copilot 中 Human-in-the-Loop (HITL) 功能的完整实现方案。HITL 功能允许在执行敏感操作（如设备配置）前要求用户确认，提高系统安全性。

## 目标

- 在执行配置工具前要求用户确认
- 支持单个和批量工具确认
- 提供清晰的工具执行预览
- 保持现有功能完全兼容

## 核心设计

### 流程图

```
用户消息 → LLM → 工具调用决策
                      ↓
              检测是否需要确认
              ↙              ↘
         需要 HITL        直接执行
              ↓                ↓
         暂停，等待前端    执行工具
              ↓                ↓
         用户确认/拒绝      返回结果
              ↓
         执行已确认的工具
              ↓
         返回结果
```

### 架构分层

```
┌─────────────────────────────────────────┐
│         Frontend (Web UI)                │
│  - 显示确认对话框                          │
│  - 列出待确认的工具                         │
│  - 处理用户确认/拒绝操作                    │
└─────────────────────────────────────────┘
                  ↕ SSE/HTTP
┌─────────────────────────────────────────┐
│         API Layer (FastAPI)              │
│  - /hitl/status: 获取待确认工具            │
│  - /hitl/confirm: 确认执行                │
│  - /hitl/reject: 拒绝执行                 │
└─────────────────────────────────────────┘
                  ↕
┌─────────────────────────────────────────┐
│      AgentService (状态管理)              │
│  - 管理 HITL 状态                        │
│  - 处理确认/拒绝逻辑                       │
│  - checkpoint 持久化                      │
└─────────────────────────────────────────┘
                  ↕
┌─────────────────────────────────────────┐
│      LangGraph Agent (工作流)            │
│  - llm_call: LLM 调用                    │
│  - check_hitl: 检查是否需要确认            │
│  - hitl_confirmation: 等待确认            │
│  - conditional_execution: 条件执行        │
└─────────────────────────────────────────┘
```

## 实现改动

### 1. LangGraph Agent 层

#### 文件：`gns3server/agent/gns3_copilot/agent/gns3_copilot.py`

##### 改动 1.1：扩展 MessagesState

**位置**：第 98-124 行

```python
# 扩展状态定义，添加 HITL 相关字段
class MessagesState(TypedDict):
    """GNS3-Copilot 对话状态管理类"""

    messages: Annotated[list[AnyMessage], operator.add]
    llm_calls: int
    remaining_steps: RemainingSteps
    conversation_title: str | None
    topology_info: dict | None

    # 新增：HITL 相关字段
    pending_tool_calls: list[dict]      # 等待确认的工具调用列表
    hitl_confirmation_required: bool     # 是否需要用户确认
    hitl_session_id: str | None          # HITL 会话唯一标识
    confirmed_tool_calls: list[dict]     # 用户已确认的工具调用
    rejected_tool_calls: list[dict]      # 用户拒绝的工具调用
```

**改动影响**：
- checkpoint 数据库中新增 5 个字段
- 现有状态读取代码需要兼容新字段

##### 改动 1.2：添加 HITL 检测节点

**位置**：在 `generate_title` 函数后添加（约第 310 行）

```python
# 需要确认的工具列表
HITL_TOOLS = {
    "execute_multiple_device_config_commands",
    # 可根据需要添加：
    # "delete_node",
    # "start_gns3_node",
}

DANGEROUS_PATTERNS = [
    "reload", "reboot", "write erase", "erase startup-config",
    "factory reset", "format", "delete", "no ip routing"
]


def _is_dangerous_config(tool_name: str, tool_args: dict) -> bool:
    """检测配置是否包含危险命令"""
    if tool_name == "execute_multiple_device_config_commands":
        device_configs = tool_args.get("device_configs", [])
        for device in device_configs:
            commands = device.get("config_commands", [])
            for cmd in commands:
                cmd_lower = cmd.lower()
                if any(pattern in cmd_lower for pattern in DANGEROUS_PATTERNS):
                    return True
    return False


def check_hitl_requirement(state: MessagesState) -> dict:
    """
    检查工具调用是否需要用户确认 (HITL)

    Returns:
        dict: 包含 pending_tool_calls 和 hitl_confirmation_required 的状态更新
    """
    last_message = state["messages"][-1]

    # 如果最后一条消息没有工具调用，直接返回
    if not hasattr(last_message, 'tool_calls') or not last_message.tool_calls:
        return {"hitl_confirmation_required": False}

    pending_tools = []

    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]

        # 只处理需要 HITL 的工具
        if tool_name in HITL_TOOLS:
            # 检查是否为危险操作
            is_dangerous = _is_dangerous_config(tool_name, tool_args)

            tool_info = {
                "tool_call_id": tool_call["id"],
                "tool_name": tool_name,
                "tool_args": tool_args,
                "danger_level": "high" if is_dangerous else "medium"
            }

            # 添加描述信息
            if tool_name == "execute_multiple_device_config_commands":
                device_count = len(tool_args.get("device_configs", []))
                tool_info["description"] = f"配置 {device_count} 个设备"

            pending_tools.append(tool_info)
            logger.info("HITL: Tool '%s' requires confirmation (danger_level=%s)",
                       tool_name, tool_info["danger_level"])

    if pending_tools:
        logger.info("HITL: %d tools require confirmation", len(pending_tools))
        return {
            "pending_tool_calls": pending_tools,
            "hitl_confirmation_required": True,
            "hitl_session_id": str(uuid4())
        }

    return {"hitl_confirmation_required": False}
```

##### 改动 1.3：修改 should_continue 路由

**位置**：第 337-370 行

```python
def should_continue(
    state: MessagesState,
) -> Literal["conditional_tool_execution", "hitl_confirmation", "title_generator_node", END]:
    """
    LLM 响应后的路由决策

    Returns:
        Literal: 路由到下一个节点
    """
    last_message = state["messages"][-1]
    current_title = state.get("conversation_title")

    # LLM 请求工具调用
    if last_message.tool_calls:
        # 检查是否需要 HITL 确认
        if state.get("hitl_confirmation_required"):
            logger.info("Routing to hitl_confirmation node")
            return "hitl_confirmation"

        logger.info("Routing to conditional_tool_execution node")
        return "conditional_tool_execution"

    # 首次交互完成，生成标题
    if current_title in [None, "New Conversation"]:
        return "title_generator_node"

    return END
```

**关键变更**：
- 原路由 `"tool_node"` 改为 `"conditional_tool_execution"`
- 新增 `"hitl_confirmation"` 路由
- 路由名称变更，需要同步更新所有引用

##### 改动 1.4：添加 HITL 确认等待节点

**位置**：在 `should_continue` 函数后添加

```python
def hitl_confirmation_node(state: MessagesState) -> dict:
    """
    HITL 确认节点 - 暂停执行，等待用户确认

    这是一个特殊的节点，它不执行任何操作，只是保持状态。
    实际的确认流程由 API 层处理。

    工作原理：
    1. 节点被调用时，状态中包含 pending_tool_calls
    2. LangGraph 保存状态到 checkpoint
    3. 执行流程暂停，等待外部状态更新
    4. 用户通过 API 确认/拒绝后，状态被更新
    5. 从 checkpoint 恢复并继续执行

    Returns:
        dict: 空字典，保持状态不变
    """
    logger.info("HITL: Pausing for user confirmation (session_id=%s)",
               state.get("hitl_session_id"))

    # 返回空字典，保持状态不变
    # 状态将在用户确认后通过 API 更新
    return {}
```

##### 改动 1.5：添加条件执行节点

**位置**：在 `hitl_confirmation_node` 函数后添加

```python
def conditional_tool_execution(state: MessagesState) -> dict:
    """
    条件工具执行节点 - 根据用户确认决定是否执行工具

    这个节点替代原来的 tool_node，增加了：
    1. 只执行用户确认的工具
    2. 处理用户拒绝的工具
    3. 更新 HITL 状态

    Returns:
        dict: 包含执行结果和状态更新的字典
    """
    confirmed_calls = state.get("confirmed_tool_calls", [])
    rejected_calls = state.get("rejected_tool_calls", [])

    logger.info("HITL: Executing %d confirmed tools, %d rejected",
               len(confirmed_calls), len(rejected_calls))

    # 处理用户拒绝的工具
    if rejected_calls:
        rejected_names = [c["tool_name"] for c in rejected_calls]
        rejection_msg = (
            f"用户拒绝了以下操作: {', '.join(rejected_names)}。\n"
            f"请提供替代方案或解释不执行这些操作的原因。"
        )

        # 添加系统消息通知 LLM
        return {
            "messages": [SystemMessage(content=rejection_msg)],
            "pending_tool_calls": [],
            "hitl_confirmation_required": False,
            "confirmed_tool_calls": [],
            "rejected_tool_calls": []
        }

    # 执行已确认的工具
    if not confirmed_calls:
        logger.warning("HITL: No confirmed tools to execute")
        return {
            "pending_tool_calls": [],
            "hitl_confirmation_required": False
        }

    results = []
    for tool_call_dict in confirmed_calls:
        tool_call_id = tool_call_dict["tool_call_id"]
        tool_name = tool_call_dict["tool_name"]
        tool_args = tool_call_dict["tool_args"]

        logger.info("Executing confirmed tool: %s", tool_name)

        tool = tools_by_name[tool_name]
        try:
            observation = tool.invoke(tool_args)
            results.append(ToolMessage(
                content=observation,
                tool_call_id=tool_call_id,
                name=tool_name
            ))
            logger.debug("Tool %s completed successfully", tool_name)
        except Exception as e:
            logger.error("Tool %s failed: %s", tool_name, e, exc_info=True)
            results.append(ToolMessage(
                content=f"Error: {str(e)}",
                tool_call_id=tool_call_id,
                name=tool_name
            ))

    # 清理 HITL 状态
    return {
        "messages": results,
        "pending_tool_calls": [],
        "hitl_confirmation_required": False,
        "confirmed_tool_calls": [],
        "rejected_tool_calls": []
    }
```

**关键变更**：
- 替代原 `tool_node` 函数
- 增加确认逻辑处理
- 支持部分确认、部分拒绝

##### 改动 1.6：更新 LangGraph 构建流程

**位置**：第 393-427 行

```python
# 构建工作流
agent_builder = StateGraph(MessagesState)

# 添加节点
agent_builder.add_node("llm_call", llm_call)
agent_builder.add_node("hitl_confirmation", hitl_confirmation_node)
agent_builder.add_node("conditional_tool_execution", conditional_tool_execution)
agent_builder.add_node("title_generator_node", generate_title)

# 添加边：START → llm_call
agent_builder.add_edge(START, "llm_call")

# 添加边：LLM 后的条件路由
agent_builder.add_conditional_edges(
    "llm_call",
    should_continue,
    {
        "hitl_confirmation": "hitl_confirmation",          # 需要 HITL 确认
        "conditional_tool_execution": "conditional_tool_execution",  # 直接执行
        "title_generator_node": "title_generator_node",   # 生成标题
        END: END                                         # 结束对话
    },
)

# HITL 确认节点是特殊的，它需要等待外部状态更新
# 状态更新后，下一轮调用将从 checkpoint 恢复并继续
# 这个循环通过 API 触发新的 graph.ainvoke() 调用完成

# 添加边：条件执行后继续 LLM 调用
agent_builder.add_conditional_edges(
    "conditional_tool_execution",
    recursion_limit_continue,
    {
        "llm_call": "llm_call",
        END: END
    },
)

# 添加边：标题生成后结束
agent_builder.add_edge("title_generator_node", END)
```

**工作流图**：
```
START → llm_call → should_continue
                     ↓
        ┌────────────┼────────────┐
        ↓            ↓            ↓
hitl_confirmation  conditional  title_generator
(等待 API)      _execution         ↓
        └────────────┴────────────→ END
```

#### 文件：`gns3server/agent/gns3_copilot/agent_service.py`

##### 改动 2.1：添加 HITL 事件处理

**位置**：第 333-376 行的 `_convert_event_to_chunk` 函数

```python
def _convert_event_to_chunk(self, event: Dict[str, Any], session_id: str) -> Optional[Dict[str, Any]]:
    """
    转换 LangGraph 事件为 API 响应块

    支持 HITL 事件类型
    """
    event_type = event.get("event", "")
    data = event.get("data", {})

    if event_type == "on_chat_model_stream":
        chunk = data.get("chunk", {})
        content = getattr(chunk, "content", "")
        if content:
            return {"type": "content", "content": content}

    elif event_type == "on_tool_start":
        return {
            "type": "tool_start",
            "tool_name": event.get("name", ""),
            "session_id": session_id
        }

    elif event_type == "on_tool_end":
        output = data.get("output", "")
        if not isinstance(output, str):
            output = str(output)
        return {
            "type": "tool_end",
            "tool_name": event.get("name", ""),
            "tool_output": output,
            "session_id": session_id
        }

    # 新增：HITL 确认要求事件
    elif event_type == "hitl_required":
        return {
            "type": "hitl_required",
            "pending_tools": data.get("pending_tool_calls", []),
            "hitl_session_id": data.get("hitl_session_id"),
            "timeout": 300,  # 5分钟超时
            "session_id": session_id
        }

    return None
```

**注意**：实际实现中，HITL 事件不是通过 LangGraph 的 `astream_events` 触发的，而是通过状态查询实现的。因此，此函数主要用于处理工具执行事件。

---

### 2. API 层

#### 文件：`gns3server/api/routes/controller/chat.py`

##### 改动 2.1：添加 HITL 端点

**位置**：在文件末尾添加（约第 325 行后）

```python
from gns3server import schemas
from typing import List


# =============================================================================
# HITL (Human-in-the-Loop) 端点
# =============================================================================

@router.get(
    "/sessions/{session_id}/hitl-status",
    response_model=schemas.HITLStatusResponse,
    summary="获取 HITL 状态",
    description="获取当前会话中待确认的工具列表"
)
async def get_hitl_status(
    session_id: str,
    project: Project = Depends(dep_project),
    current_user: schemas.User = Depends(get_current_active_user),
) -> schemas.HITLStatusResponse:
    """
    获取 HITL 状态

    返回当前会话中等待用户确认的工具调用列表。
    前端应定期轮询此端点以检查是否有新的待确认工具。
    """
    if project.status != "opened":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Project must be opened. Current status: {project.status}"
        )

    agent_manager = await get_project_agent_manager()
    agent_service = await agent_manager.get_agent(str(project.id), project.path)

    # 从 checkpoint 获取状态
    config = {"configurable": {"thread_id": session_id}}
    state = await agent_service._graph.aget_state(config)

    if not state or not state.values:
        return schemas.HITLStatusResponse(
            status="idle",
            pending_tools=[],
            hitl_session_id=None,
            session_id=session_id
        )

    values = state.values
    pending_tools = values.get("pending_tool_calls", [])
    hitl_session_id = values.get("hitl_session_id")

    # 转换为 Schema 格式
    pending_tool_schemas = []
    for tool in pending_tools:
        pending_tool_schemas.append(schemas.PendingTool(
            tool_call_id=tool["tool_call_id"],
            tool_name=tool["tool_name"],
            tool_args=tool["tool_args"],
            danger_level=tool.get("danger_level", "medium"),
            description=tool.get("description", "")
        ))

    return schemas.HITLStatusResponse(
        status="waiting" if pending_tool_schemas else "idle",
        pending_tools=pending_tool_schemas,
        hitl_session_id=hitl_session_id,
        session_id=session_id
    )


@router.post(
    "/sessions/{session_id}/hitl/confirm",
    response_model=schemas.HITLConfirmationResponse,
    summary="确认执行工具",
    description="用户确认执行一个或多个待确认的工具"
)
async def confirm_tool_execution(
    session_id: str,
    request: schemas.HITLConfirmationRequest,
    project: Project = Depends(dep_project),
    current_user: schemas.User = Depends(get_current_active_user),
) -> schemas.HITLConfirmationResponse:
    """
    确认执行工具

    用户可以选择：
    - confirm_all=true: 确认所有待确认的工具
    - tool_call_ids=[...]: 确认指定的工具

    确认后，工具将被执行，结果将通过 SSE 流返回。
    """
    if project.status != "opened":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Project must be opened. Current status: {project.status}"
        )

    agent_manager = await get_project_agent_manager()
    agent_service = await agent_manager.get_agent(str(project.id), project.path)

    config = {"configurable": {"thread_id": session_id}}
    state = await agent_service._graph.aget_state(config)

    if not state or not state.values:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found"
        )

    values = state.values
    pending_tools = values.get("pending_tool_calls", [])

    if not pending_tools:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending tools to confirm"
        )

    # 根据请求选择要确认的工具
    confirmed_tools = []
    if request.confirm_all:
        confirmed_tools = pending_tools
    elif request.tool_call_ids:
        confirmed_tools = [t for t in pending_tools if t["tool_call_id"] in request.tool_call_ids]
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must specify either confirm_all=true or tool_call_ids"
        )

    if not confirmed_tools:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No tools matched the confirmation criteria"
        )

    # 更新状态：标记为已确认
    await agent_service._graph.aupdate_state(
        config,
        {
            "confirmed_tool_calls": confirmed_tools,
            "pending_tool_calls": [],
            "hitl_confirmation_required": False
        }
    )

    # 继续执行流程
    try:
        new_state = await agent_service._graph.ainvoke(None, config)
    except Exception as e:
        logger.error("Error continuing graph execution: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error executing tools: {str(e)}"
        )

    return schemas.HITLConfirmationResponse(
        status="confirmed",
        confirmed_count=len(confirmed_tools),
        message=f"已确认 {len(confirmed_tools)} 个工具执行"
    )


@router.post(
    "/sessions/{session_id}/hitl/reject",
    response_model=schemas.HITLConfirmationResponse,
    summary="拒绝执行工具",
    description="用户拒绝执行一个或多个待确认的工具"
)
async def reject_tool_execution(
    session_id: str,
    request: schemas.HITLRejectionRequest,
    project: Project = Depends(dep_project),
    current_user: schemas.User = Depends(get_current_active_user),
) -> schemas.HITLConfirmationResponse:
    """
    拒绝执行工具

    用户可以选择：
    - reject_all=true: 拒绝所有待确认的工具
    - tool_call_ids=[...]: 拒绝指定的工具
    - reason: 拒绝原因（将反馈给 LLM）

    拒绝后，LLM 将收到通知并可以提供替代方案。
    """
    if project.status != "opened":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Project must be opened. Current status: {project.status}"
        )

    agent_manager = await get_project_agent_manager()
    agent_service = await agent_manager.get_agent(str(project.id), project.path)

    config = {"configurable": {"thread_id": session_id}}

    rejected_tools = []
    if request.reject_all:
        state = await agent_service._graph.aget_state(config)
        if state and state.values:
            rejected_tools = state.values.get("pending_tool_calls", [])
    elif request.tool_call_ids:
        state = await agent_service._graph.aget_state(config)
        if state and state.values:
            pending = state.values.get("pending_tool_calls", [])
            rejected_tools = [t for t in pending if t["tool_call_id"] in request.tool_call_ids]

    if not rejected_tools:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending tools to reject"
        )

    # 更新状态：标记为已拒绝
    await agent_service._graph.aupdate_state(
        config,
        {
            "rejected_tool_calls": rejected_tools,
            "pending_tool_calls": [],
            "hitl_confirmation_required": False
        }
    )

    # 继续执行流程，LLM 将收到拒绝通知
    try:
        new_state = await agent_service._graph.ainvoke(None, config)
    except Exception as e:
        logger.error("Error continuing graph execution: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing rejection: {str(e)}"
        )

    rejected_names = [t["tool_name"] for t in rejected_tools]
    return schemas.HITLConfirmationResponse(
        status="rejected",
        confirmed_count=0,
        message=f"已拒绝 {len(rejected_tools)} 个工具执行: {', '.join(rejected_names)}"
    )
```

---

### 3. Schema 层

#### 文件：`gns3server/schemas/controller/chat.py`

##### 改动 3.1：添加 HITL 相关的 Pydantic 模型

**位置**：在文件末尾添加（约第 112 行后）

```python
class PendingTool(BaseModel):
    """待确认的工具信息"""
    tool_call_id: str = Field(..., description="工具调用的唯一 ID")
    tool_name: str = Field(..., description="工具名称")
    tool_args: Dict[str, Any] = Field(..., description="工具参数")
    danger_level: Literal["low", "medium", "high"] = Field(
        default="medium",
        description="危险等级"
    )
    description: Optional[str] = Field(None, description="工具执行的描述")


class HITLStatusResponse(BaseModel):
    """HITL 状态响应"""
    status: Literal["idle", "waiting", "confirmed", "rejected"] = Field(
        ...,
        description="当前状态"
    )
    pending_tools: List[PendingTool] = Field(
        default_factory=list,
        description="待确认的工具列表"
    )
    hitl_session_id: Optional[str] = Field(
        None,
        description="HITL 会话 ID"
    )
    session_id: str = Field(..., description="聊天会话 ID")


class HITLConfirmationRequest(BaseModel):
    """HITL 确认请求"""
    confirm_all: bool = Field(
        default=False,
        description="是否确认所有待确认的工具"
    )
    tool_call_ids: Optional[List[str]] = Field(
        None,
        description="要确认的工具调用 ID 列表"
    )


class HITLRejectionRequest(BaseModel):
    """HITL 拒绝请求"""
    reject_all: bool = Field(
        default=False,
        description="是否拒绝所有待确认的工具"
    )
    tool_call_ids: Optional[List[str]] = Field(
        None,
        description="要拒绝的工具调用 ID 列表"
    )
    reason: Optional[str] = Field(
        None,
        description="拒绝原因（将反馈给 LLM）"
    )


class HITLConfirmationResponse(BaseModel):
    """HITL 确认响应"""
    status: Literal["confirmed", "rejected"] = Field(
        ...,
        description="操作状态"
    )
    confirmed_count: int = Field(
        ...,
        description="已确认的工具数量"
    )
    message: str = Field(..., description="响应消息")
```

**同时更新 `__init__.py` 导出**：

```python
# 文件：gns3server/schemas/__init__.py

# 添加到导入列表
from .controller.chat import (
    # ... 现有导入 ...
    PendingTool,
    HITLStatusResponse,
    HITLConfirmationRequest,
    HITLRejectionRequest,
    HITLConfirmationResponse,
)
```

---

### 4. 文件改动汇总

| 文件路径 | 改动类型 | 行数变化 | 风险等级 |
|---------|---------|----------|----------|
| `gns3_copilot.py` | 修改/新增 | +200 行 | 🟡 中 |
| `agent_service.py` | 修改 | +10 行 | 🟢 低 |
| `chat.py` (API) | 新增 | +150 行 | 🟢 低 |
| `chat.py` (Schema) | 新增 | +50 行 | 🟢 低 |
| **总计** | - | **+410 行** | - |

---

## 数据库变更

### Checkpoint 表结构

**表名**：`checkpoints` (LangGraph 自动管理)

**新增字段**（通过 MessagesState 扩展自动添加）：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `pending_tool_calls` | TEXT (JSON) | 待确认的工具调用列表 |
| `hitl_confirmation_required` | BOOLEAN | 是否需要 HITL 确认 |
| `hitl_session_id` | TEXT | HITL 会话 ID |
| `confirmed_tool_calls` | TEXT (JSON) | 已确认的工具调用 |
| `rejected_tool_calls` | TEXT (JSON) | 已拒绝的工具调用 |

**迁移说明**：
- LangGraph 自动处理新的 state 字段
- 无需手动执行数据库迁移
- 现有 checkpoint 向后兼容

---

## API 规范

### 1. 获取 HITL 状态

**端点**：`GET /v3/projects/{project_id}/chat/sessions/{session_id}/hitl-status`

**响应示例**：
```json
{
    "status": "waiting",
    "pending_tools": [
        {
            "tool_call_id": "call_abc123",
            "tool_name": "execute_multiple_device_config_commands",
            "tool_args": {
                "project_id": "xxx",
                "device_configs": [
                    {
                        "device_name": "R1",
                        "config_commands": ["interface gig0/0", "ip address 10.0.0.1/24"]
                    }
                ]
            },
            "danger_level": "medium",
            "description": "配置 1 个设备"
        }
    ],
    "hitl_session_id": "hitl_12345",
    "session_id": "chat_session_id"
}
```

### 2. 确认执行

**端点**：`POST /v3/projects/{project_id}/chat/sessions/{session_id}/hitl/confirm`

**请求体**：
```json
{
    "confirm_all": true,
    "tool_call_ids": null
}
```

**或指定工具**：
```json
{
    "confirm_all": false,
    "tool_call_ids": ["call_abc123", "call_def456"]
}
```

**响应示例**：
```json
{
    "status": "confirmed",
    "confirmed_count": 2,
    "message": "已确认 2 个工具执行"
}
```

### 3. 拒绝执行

**端点**：`POST /v3/projects/{project_id}/chat/sessions/{session_id}/hitl/reject`

**请求体**：
```json
{
    "reject_all": true,
    "reason": "配置有误，需要重新规划"
}
```

**响应示例**：
```json
{
    "status": "rejected",
    "confirmed_count": 0,
    "message": "已拒绝 1 个工具执行: execute_multiple_device_config_commands"
}
```

---

## 前端集成指南

### 1. 检测 HITL 状态

```javascript
// 定期轮询 HITL 状态
async function pollHITLStatus(sessionId) {
    const response = await fetch(
        `/api/v3/projects/${projectId}/chat/sessions/${sessionId}/hitl-status`
    );
    const status = await response.json();

    if (status.status === 'waiting' && status.pending_tools.length > 0) {
        showConfirmationDialog(status);
    }
}

// 每 2 秒轮询一次
setInterval(() => pollHITLStatus(sessionId), 2000);
```

### 2. 显示确认对话框

```javascript
function showConfirmationDialog(hitlStatus) {
    const { pending_tools, hitl_session_id } = hitlStatus;

    const dialog = document.createElement('div');
    dialog.className = 'hitl-confirmation-dialog';

    let html = `
        <h3>⚠️ 需要确认以下操作</h3>
        <div class="pending-tools">
    `;

    pending_tools.forEach(tool => {
        const icon = tool.danger_level === 'high' ? '🔴' : '🟡';
        html += `
            <div class="tool-item">
                <span class="danger-icon">${icon}</span>
                <span class="tool-name">${tool.tool_name}</span>
                <span class="tool-description">${tool.description}</span>
            </div>
        `;
    });

    html += `
        </div>
        <div class="actions">
            <button onclick="confirmAll('${hitl_session_id}')">全部确认</button>
            <button onclick="rejectAll('${hitl_session_id}')">全部拒绝</button>
        </div>
    `;

    dialog.innerHTML = html;
    document.body.appendChild(dialog);
}

async function confirmAll(sessionId) {
    const response = await fetch(
        `/api/v3/projects/${projectId}/chat/sessions/${sessionId}/hitl/confirm`,
        {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ confirm_all: true })
        }
    );

    if (response.ok) {
        closeDialog();
        // 继续监听 SSE 流以获取执行结果
    }
}

async function rejectAll(sessionId) {
    const response = await fetch(
        `/api/v3/projects/${projectId}/chat/sessions/${sessionId}/hitl/reject`,
        {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reject_all: true, reason: '用户取消操作' })
        }
    );

    if (response.ok) {
        closeDialog();
    }
}
```

---

## 测试计划

### 单元测试

```python
import pytest
from gns3server.agent.gns3_copilot.agent.gns3_copilot import (
    check_hitl_requirement,
    _is_dangerous_config
)

def test_dangerous_config_detection():
    """测试危险命令检测"""
    tool_args = {
        "device_configs": [{
            "config_commands": ["reload", "write erase"]
        }]
    }

    assert _is_dangerous_config("execute_multiple_device_config_commands", tool_args) == True

def test_safe_config_detection():
    """测试安全命令检测"""
    tool_args = {
        "device_configs": [{
            "config_commands": ["interface gig0/0", "ip address 10.0.0.1/24"]
        }]
    }

    assert _is_dangerous_config("execute_multiple_device_config_commands", tool_args) == False

def test_hitl_requirement_check():
    """测试 HITL 需求检查"""
    state = {
        "messages": [
            HumanMessage(content="配置路由器"),
            AIMessage(
                content="",
                tool_calls=[{
                    "id": "call_123",
                    "name": "execute_multiple_device_config_commands",
                    "args": {"project_id": "test"}
                }]
            )
        ]
    }

    result = check_hitl_requirement(state)

    assert result["hitl_confirmation_required"] == True
    assert len(result["pending_tool_calls"]) == 1
```

### 集成测试

```python
import pytest
from fastapi.testclient import TestClient

def test_hitl_flow():
    """测试完整的 HITL 流程"""
    client = TestClient(app)

    # 1. 开始聊天
    response = client.post(
        f"/v3/projects/{project_id}/chat/stream",
        json={"message": "配置所有路由器"}
    )

    # 2. 检查 HITL 状态
    status = client.get(f"/v3/projects/{project_id}/chat/sessions/{session_id}/hitl-status")
    assert status.json()["status"] == "waiting"
    assert len(status.json()["pending_tools"]) > 0

    # 3. 确认执行
    confirm = client.post(
        f"/v3/projects/{project_id}/chat/sessions/{session_id}/hitl/confirm",
        json={"confirm_all": True}
    )
    assert confirm.json()["status"] == "confirmed"
```

---

## 部署步骤

### 第一阶段：基础架构（1-2 天）

1. ✅ 扩展 MessagesState
2. ✅ 实现 check_hitl_requirement 节点
3. ✅ 实现 hitl_confirmation_node 和 conditional_tool_execution
4. ✅ 更新 LangGraph 工作流
5. ✅ 单元测试

**验证**：现有功能不受影响

### 第二阶段：API 端点（1 天）

1. ✅ 添加 HITL 状态查询端点
2. ✅ 添加确认/拒绝端点
3. ✅ 添加 Schema 定义
4. ✅ API 测试

**验证**：API 可正常调用

### 第三阶段：前端集成（2-3 天）

1. ✅ 实现轮询逻辑
2. ✅ 显示确认对话框
3. ✅ 处理确认/拒绝操作
4. ✅ 显示执行结果

**验证**：端到端流程可用

### 第四阶段：优化和增强（1-2 天）

1. ✅ 添加危险命令分级
2. ✅ 实现超时处理
3. ✅ 添加操作日志
4. ✅ 性能优化

**验证**：生产就绪

---

## 参数修改功能（扩展）

### 功能概述

除了"确认/拒绝"外，HITL 还支持用户修改即将执行的命令参数，然后将修改反馈给 LLM，由 LLM 理解并按新参数执行。

### 完整流程

```
LLM 生成命令 A
       ↓
  HITL 确认暂停
       ↓
   显示给用户
       ↓
┌─────────┼─────────┐
│         │         │
直接确认   拒绝    修改为B
│         │         │
执行A    反馈LLM  反馈(A→B)给LLM
                  ↓
              LLM理解修改
                  ↓
              生成新tool call
                  ↓
              执行B
```

### 对话示例

```
用户: 配置 R1 的 gig0/0 接口为 10.0.0.1/24

LLM: 我将为您配置 R1 的接口。

HITL: ⚠️ 需要确认以下操作
     工具: execute_multiple_device_config_commands
     参数: {
       "device_configs": [{
         "device_name": "R1",
         "config_commands": [
           "interface gig0/0",
           "ip address 10.0.0.1 255.255.255.0"
         ]
       }]
     }

用户: [修改参数]
     ip address 10.0.0.1 255.255.255.0
     → ip address 192.168.1.1 255.255.255.0
     [保存并执行]

系统反馈给 LLM:
     用户修改了即将执行的命令参数：
     工具: execute_multiple_device_config_commands
     R1:
       原命令: ['interface gig0/0', 'ip address 10.0.0.1 255.255.255.0']
       修改为: ['interface gig0/0', 'ip address 192.168.1.1 255.255.255.0']
     请按照修改后的参数执行。

LLM: 明白，我将使用修改后的 IP 地址 192.168.1.1/24 来配置 R1 的 gig0/0 接口。

[工具执行 execute_multiple_device_config_commands with modified args]

LLM: 已完成配置，R1 的 gig0/0 接口已配置为 192.168.1.1/24。
```

### 实现要点

#### 1. 状态扩展

在 `MessagesState` 中添加：

```python
# 用户修改的字段
user_modified_args: dict | None  # 结构:
# {
#     "tool_call_id": str,
#     "original_args": dict,
#     "modified_args": dict
# }
```

#### 2. API 扩展

新增端点：`POST /v3/projects/{project_id}/chat/sessions/{session_id}/hitl/modify`

**请求体**：
```python
{
    "tool_call_id": "call_abc123",
    "modified_args": {
        # 修改后的完整参数
    }
}
```

**响应**：
```python
{
    "status": "modified",
    "modification_summary": "显示参数差异",
    "message": "已将修改反馈给 AI"
}
```

#### 3. 后端处理流程

1. 接收修改后的参数
2. 生成参数差异摘要
3. 添加 HumanMessage 到对话，说明用户的修改
4. 清除 `pending_tool_calls` 和 `hitl_confirmation_required`
5. 设置 `user_modified_args`（用于触发 LLM 重新生成）
6. 继续执行，LLM 看到用户的修改后，生成新的 tool call
7. 执行新的 tool call

#### 4. 前端实现要点

**界面组件**：
- 显示原始参数和编辑区域
- 提供参数差异高亮（原值 vs 新值）
- 支持 JSON 格式验证
- 保存修改并执行按钮

**交互流程**：
1. 用户点击"修改参数"按钮
2. 展开参数编辑区域，显示原始 JSON
3. 用户在文本框中编辑 JSON
4. 实时验证 JSON 格式
5. 点击"保存并执行"提交修改
6. 系统反馈修改摘要并继续执行

**用户体验**：
- 对于配置工具，可以提供更友好的命令行界面而非纯 JSON
- 高亮显示修改的部分（红色删除线、绿色新增）
- 提供参数预设模板
- 显示修改前后的对比视图

### 关键代码位置

**文件**：`gns3_copilot.py`

增强 `conditional_tool_execution` 函数，检测 `user_modified_args`：

```python
def conditional_tool_execution(state: MessagesState) -> dict:
    """条件工具执行节点（支持用户修改）"""

    # 处理用户修改的情况
    if state.get("user_modified_args"):
        # LLM 已通过 HumanMessage 收到用户修改
        # 清除标记，让 LLM 重新生成 tool call
        return {
            "user_modified_args": None,
            "pending_tool_calls": [],
            "hitl_confirmation_required": False
        }

    # ... 其他处理逻辑
```

**参数差异生成**：

```python
def _generate_modification_summary(tool_name: str, original: dict, modified: dict) -> str:
    """生成参数修改摘要"""

    if tool_name == "execute_multiple_device_config_commands":
        # 特殊处理配置工具，逐命令对比
        orig_devices = original.get("device_configs", [])
        mod_devices = modified.get("device_configs", [])

        summary = []
        for orig, mod in zip(orig_devices, mod_devices):
            device = orig.get("device_name", "")
            orig_cmds = orig.get("config_commands", [])
            mod_cmds = mod.get("config_commands", [])

            if orig_cmds != mod_cmds:
                summary.append(f"\n{device}:")
                for oc, mc in zip(orig_cmds, mod_cmds):
                    if oc != mc:
                        summary.append(f"  - {oc}")
                        summary.append(f"  + {mc}")

        return "\n".join(summary) if summary else "无修改"

    # 其他工具的通用处理
    # ...
```

### 安全考虑

#### 参数验证

- 验证修改后的参数结构是否完整
- 检查必填字段是否存在
- 验证参数值是否在合法范围内

#### 危险命令二次确认

即使修改后，某些命令仍需二次确认：
- `erase startup-config`
- `reload`
- `format flash:`

### 测试用例

**场景**：用户修改配置命令

1. LLM 生成配置命令：`ip address 10.0.0.1 255.255.255.0`
2. 用户修改为：`ip address 192.168.1.1 255.255.255.0`
3. 系统反馈修改摘要
4. LLM 理解并确认使用新 IP
5. 执行工具，使用修改后的参数
6. 验证配置结果

---

## 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 破坏现有功能 | 低 | 高 | 完整的回归测试 |
| 状态不一致 | 中 | 中 | checkpoint 验证 |
| 性能影响 | 低 | 低 | 异步处理 |
| 前端集成问题 | 中 | 中 | 详细的前端文档 |

---

## 回滚计划

如需回滚：

1. 移除 HITL 相关节点
2. 恢复原始 `should_continue` 和 `tool_node`
3. 删除新增的 API 端点
4. checkpoint 中的新字段会被自动忽略

**回滚时间**：约 30 分钟

---

## 后续增强

1. **批量操作优化**：支持选择性确认部分工具
2. **操作历史**：记录所有 HITL 操作
3. **自动审批**：对低风险操作设置自动审批规则
4. **多用户协作**：支持多人审批流程
5. **模板管理**：保存常用配置为模板

---

## 参考文档

- [LangGraph Interrupts](https://langchain-ai.github.io/langgraph/concepts/low_level/#interruption)
- [GNS3 Copilot 架构](./ai-chat-api-design.md)
- [工具响应格式标准](./tool-response-format-standard.md)

---

**文档版本**：v1.0
**创建日期**：2026-03-04
**作者**：GNS3 Development Team
