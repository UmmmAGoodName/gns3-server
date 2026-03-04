# GNS3 Copilot Agent Chat API 实现方案

## 概述

本文档描述了如何在 GNS3 Server 中实现 AI Chat API，使客户端能够通过 RESTful API 与 GNS3 Copilot Agent 进行交互。

## 背景

### 现有组件

- **GNS3 Copilot Agent**: 位于 `gns3server/agent/gns3_copilot/`，使用 LangGraph 实现的网络自动化助手
- **LLM 配置管理**: 已有 `llm_model_configs` 系统，支持用户/用户组的 LLM 配置
- **API 框架**: 使用 FastAPI，已有的路由结构在 `gns3server/api/routes/controller/`

### 参考实现

FlowNet-Lab 项目 (`/home/yueguobin/myCode/GNS3/FlowNet-Lab`) 已有完整的 Chat API 实现，可作为参考：

- Backend: `backend/api/v1/chat.py`
- Agent Service: `backend/core/agent.py`

## 架构设计

### 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (Client)                        │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐│
│   │ ChatInput   │  │ MessageList │  │ ConversationSidebar    ││
│   └──────┬──────┘  └──────┬──────┘  └───────────┬─────────────┘│
│          │                 │                      │              │
│          └─────────────────┼──────────────────────┘              │
│                            ▼                                     │
│                    chatService.ts                                │
│                    (SSE Streaming)                               │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                     HTTP POST /api/v1/chat/stream
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      GNS3 Server (Backend)                      │
│                                                                 │
│   ┌─────────────────────────────────────────────────────────┐  │
│   │              FastAPI Application                        │  │
│   │  ┌─────────────────────────────────────────────────┐   │  │
│   │  │           Chat API Routes                       │   │  │
│   │  │  POST /v3/chat/stream                          │   │  │
│   │  │  GET  /v3/chat/history/{session_id}            │   │  │
│   │  │  GET  /v3/chat/sessions                        │   │  │
│   │  │  POST /v3/chat/sessions                        │   │  │
│   │  │  DELETE /v3/chat/sessions/{session_id}        │   │  │
│   │  └─────────────────────────────────────────────────┘   │  │
│   └──────────────────────────┬───────────────────────────────┘  │
│                              │                                   │
│                              ▼                                   │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │              ProjectAgentManager                        │   │
│   │  (管理每个项目的 Agent Service 实例)                     │   │
│   └──────────────────────────┬───────────────────────────────┘  │
│                              │                                   │
│   ┌──────────────────────────┼───────────────────────────────┐  │
│   │                          ▼                               │  │
│   │   ┌─────────────────────────────────────────────┐       │  │
│   │   │            AgentService                     │       │  │
│   │   │  - SQLiteSaver (项目级 checkpoint)          │       │  │
│   │   │  - LangGraph Agent                         │       │  │
│   │   └─────────────────────┬───────────────────────┘       │  │
│   │                          │                               │  │
│   │                          ▼                               │  │
│   │   ┌─────────────────────────────────────────────┐       │  │
│   │   │         LangGraph Agent (gns3_copilot)      │       │  │
│   │   │  llm_call → should_continue → tool_node    │       │  │
│   │   └─────────────────────────────────────────────┘       │  │
│   │                                                       │  │
│   └───────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  GNS3 Project Directory                         │
│                                                                 │
│   {project.path}/                                               │
│   ├── .gns3-copilot/                                           │
│   │   └── checkpoint.db  (SQLite - LangGraph 状态存储)        │
│   ├── project-files/                                           │
│   │   ├── nodes/                                               │
│   │   └── captures/                                            │
│   └── project.gns3                                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 项目级 Checkpoint 设计

**核心思路**: 每个 GNS3 项目有独立的 checkpoint 数据库，实现项目级别的会话隔离。

```
project_path/.gns3-copilot/checkpoint.db
```

使用 LangGraph 的 `AsyncSqliteSaver` 作为 checkpointer（推荐异步方式）。

### 生产级实现（推荐）

以下实现包含连接管理、项目切换、资源清理等完整功能：

```python
import os
import logging
from typing import Optional
import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

log = logging.getLogger(__name__)


class CheckpointerManager:
    """Checkpointer 管理器（项目级）"""

    def __init__(self, controller):
        """
        Args:
            controller: GNS3 Controller 实例
        """
        self.controller = controller
        self._checkpointer: Optional[AsyncSqliteSaver] = None
        self._checkpointer_conn: Optional[aiosqlite.Connection] = None
        self._project_checkpoint_path: Optional[str] = None

    async def _get_checkpointer(self, project_id: str) -> AsyncSqliteSaver:
        """
        获取或创建 SQLite checkpointer for a specific project.

        Args:
            project_id: GNS3 project ID

        Returns:
            AsyncSqliteSaver instance
        """
        log.debug("Getting checkpointer for project %s", project_id)

        # Get the project to find its directory
        project = self.controller.get_project(project_id)
        if not project:
            log.error("Project %s not found in controller", project_id)
            raise ValueError(f"Project {project_id} not found")

        # Create checkpoint file in the project directory
        checkpointer_path = os.path.join(project.path, ".gns3-copilot", "copilot_checkpoints.db")
        os.makedirs(os.path.dirname(checkpointer_path), exist_ok=True)
        log.debug("Checkpoint path: %s", checkpointer_path)

        # Store the path for reference
        self._project_checkpoint_path = checkpointer_path

        # Check if we already created a checkpointer for this project
        if self._checkpointer and self._project_checkpoint_path == checkpointer_path:
            log.debug("Reusing existing checkpointer")
            return self._checkpointer

        # Create new checkpointer using AsyncSqliteSaver
        log.debug("Creating new async checkpointer at %s", checkpointer_path)

        # Close existing connection if switching projects
        if self._checkpointer_conn:
            try:
                await self._checkpointer_conn.close()
                log.debug("Closed previous checkpointer connection")
            except Exception as e:
                log.warning("Error closing old checkpointer connection: %s", e)

        # Create new connection
        conn = await aiosqlite.connect(checkpointer_path)
        # Enable WAL mode for better concurrent performance
        await conn.execute("PRAGMA journal_mode=WAL;")
        self._checkpointer_conn = conn  # Save connection reference to prevent GC
        self._checkpointer = AsyncSqliteSaver(conn)

        # CRITICAL: Initialize database schema
        await self._checkpointer.setup()

        log.info("Project async checkpointer created and initialized at %s", checkpointer_path)

        return self._checkpointer

    async def close(self):
        """关闭 checkpointer 连接"""
        if self._checkpointer_conn:
            try:
                await self._checkpointer_conn.close()
                log.debug("Checkpointer connection closed")
            except Exception as e:
                log.warning("Error closing checkpointer connection: %s", e)
            finally:
                self._checkpointer_conn = None
                self._checkpointer = None
```

### 关键设计要点

| 功能 | 说明 |
|------|------|
| **连接复用** | 同项目复用已有 checkpointer，避免重复创建 |
| **项目切换** | 切换项目时自动关闭旧连接，防止连接泄漏 |
| **GC 防护** | 保存 `self._checkpointer_conn` 引用，防止连接被垃圾回收 |
| **Schema 初始化** | 调用 `await self._checkpointer.setup()` 初始化数据库表结构 |
| **WAL 模式** | 启用 WAL 模式提升并发写入性能 |
| **资源清理** | `close()` 方法确保连接正确关闭 |
| **日志记录** | 完整的调试日志，便于问题排查 |

### 注意事项
- 需要安装 `aiosqlite` 包
- 必须在异步环境中使用
- 切换项目时自动关闭旧连接
- 应用关闭时应调用 `close()` 清理资源

**依赖**:
```
langgraph-checkpoint-sqlite>=3.0.1
aiosqlite
```

## 文件结构

需要创建/修改以下文件：

```
gns3server/
├── agent/gns3_copilot/
│   ├── agent_service.py           # [新建] AgentService 封装
│   └── project_agent_manager.py   # [新建] 项目级 Agent 管理器
├── api/routes/controller/
│   ├── chat.py                    # [新建] Chat API 路由
│   └── __init__.py                # [修改] 注册 chat router
├── schemas/controller/
│   └── chat.py                    # [新建] Chat Request/Response 模型
└── docs/
    └── ai-chat-api-design.md      # [本文档]
```

## 用户认证信息传递机制

### 背景

GNS3 Copilot Agent 需要获取用户的 LLM 配置信息，这需要：
1. **user_id**: 用于从数据库获取用户专属的 LLM 配置
2. **jwt_token**: 用于调用 GNS3 API 时进行身份验证

`model_factory.py` 已支持这些参数：

```python
def create_base_model(
    user_id: Optional[UUID] = None,
    jwt_token: Optional[str] = None,
    llm_config: Optional[dict[str, Any]] = None,
) -> Any:
    # 优先级：
    # 1. 提供的 llm_config 字典
    # 2. 从数据库获取 (需要 user_id 和 jwt_token)
    # 3. 环境变量 (回退)
```

### 传递机制

使用 **LangGraph 的 config 参数** 传递用户信息：

```
┌─────────────────────────────────────────────────────────────┐
│                    LangGraph Config                         │
│  {                                                          │
│    "configurable": {                                        │
│      "thread_id": "session-xxx",     # 会话 ID             │
│      "user_id": "user-uuid",        # 用户 ID             │
│      "jwt_token": "eyJxxx..."       # JWT Token           │
│    }                                                        │
│  }                                                          │
└─────────────────────────────────────────────────────────────┘
```

### 实现步骤

#### 1. 修改 gns3_copilot.py 中的 llm_call 函数

```python
# gns3server/agent/gns3_copilot/agent/gns3_copilot.py

def llm_call(state: dict, config: dict = None):
    """LLM decides whether to call a tool or not"""

    # 从 config 中获取用户信息
    configurable = config.get("configurable", {}) if config else {}
    user_id = configurable.get("user_id")
    jwt_token = configurable.get("jwt_token")

    # ... 原有逻辑 ...

    # 传递 user_id 和 jwt_token 给 model factory
    model_with_tools = create_base_model_with_tools(
        tools,
        user_id=user_id,
        jwt_token=jwt_token
    )

    return {
        "messages": [model_with_tools.invoke(full_messages)],
        "llm_calls": state.get("llm_calls", 0) + 1,
        "topology_info": topology_info,
    }
```

#### 2. 修改 generate_title 函数（同样需要传递）

```python
def generate_title(state: MessagesState, config: dict = None) -> dict:
    """Generate conversation title"""

    configurable = config.get("configurable", {}) if config else {}
    user_id = configurable.get("user_id")
    jwt_token = configurable.get("jwt_token")

    # ... 使用 user_id 和 jwt_token ...
```

#### 3. 在 AgentService.stream_chat 中构建 config

```python
# gns3server/agent/gns3_copilot/agent_service.py

async def stream_chat(
    self,
    message: str,
    session_id: str,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    jwt_token: Optional[str] = None,
    mode: str = "text"
) -> AsyncGenerator[Dict[str, Any], None]:

    # 构建包含用户信息的 config
    config = {
        "configurable": {
            "thread_id": session_id,
            "user_id": user_id,
            "jwt_token": jwt_token,
        }
    }

    # 流式处理时传递 config
    async for event in self.graph.astream_events(inputs, config=config, version="v2"):
        # ...
```

#### 4. 在 API 路由中获取并传递用户信息

```python
# gns3server/api/routes/controller/chat.py

from fastapi import Request

@router.post("/stream")
async def stream_chat(
    request: ChatRequest,
    current_user = Depends(get_current_active_user)
):
    # 获取 JWT token
    auth_header = request.headers.get("Authorization")
    jwt_token = auth_header.replace("Bearer ", "") if auth_header else None

    # 获取 user_id
    user_id = str(current_user.user_id)

    # 传递用户信息给 AgentService
    agent_service = agent_manager.get_agent(request.project_id, project_path)

    async def generate():
        async for chunk in agent_service.stream_chat(
            message=request.message,
            session_id=session_id,
            project_id=request.project_id,
            user_id=user_id,          # 传递 user_id
            jwt_token=jwt_token,     # 传递 jwt_token
            mode=request.mode
        ):
            # ...
```

### 完整数据流

```
1. 前端发起请求 (带 Authorization: Bearer <token>)

2. FastAPI get_current_active_user 验证并返回 User 对象

3. 从 Header 获取 JWT token

4. 构建 LangGraph config:
   {
     "configurable": {
       "thread_id": session_id,
       "user_id": user_id,
       "jwt_token": jwt_token
     }
   }

5. AgentService.stream_chat() 传递 config 给 astream_events()

6. llm_call() / generate_title() 从 config 获取用户信息

7. create_base_model() 使用 user_id 从数据库获取 LLM 配置
```

## 消息格式定义 (参考 FlowNet-Lab)

### 概述

Chat API 使用 Server-Sent Events (SSE) 进行流式传输，消息格式分为：
- **请求格式** (ChatRequest)
- **响应格式** (ChatResponse)
- **消息类型** (Message Types)

### 1. 请求格式 (ChatRequest)

```python
class ChatRequest(BaseModel):
    """Chat 请求模型"""
    message: str                           # 用户消息内容
    session_id: Optional[str] = None       # 会话 ID (可选，不提供则自动创建)
    project_id: str                        # GNS3 项目 ID
    stream: bool = True                    # 是否启用流式响应
    temperature: Optional[float] = None     # LLM 温度参数
    mode: Literal["text"] = "text"         # 交互模式
```

### 2. 响应格式 (ChatResponse)

```python
class OpenAIToolCall(BaseModel):
    """工具调用信息 (OpenAI 兼容格式)"""
    id: str
    type: Literal["function"] = "function"
    function: Dict[str, Any]  # {"name": "...", "arguments": {...}}


class ChatResponse(BaseModel):
    """流式响应模型"""
    type: Literal[
        "content",      # AI 文本内容
        "tool_call",    # 工具调用请求
        "tool_start",   # 工具开始执行
        "tool_end",     # 工具执行完成
        "error",        # 错误信息
        "done",         # 流结束
        "heartbeat"     # 心跳保活
    ]
    content: Optional[str] = None              # 文本内容 (type=content)
    message_id: Optional[str] = None            # 消息 ID
    tool_call: Optional[OpenAIToolCall] = None # 工具调用 (type=tool_call)
    tool_name: Optional[str] = None            # 工具名称 (type=tool_start/end)
    tool_output: Optional[str] = None          # 工具输出 (type=tool_end)
    error: Optional[str] = None                # 错误信息 (type=error)
    session_id: Optional[str] = None           # 会话 ID (type=heartbeat/done)
```

### 3. SSE 消息示例

#### 3.1 文本内容 (content)

```json
{"type": "content", "content": "Hello! How can I help you with your network today?"}
```

#### 3.2 工具调用 (tool_call)

```json
{
  "type": "tool_call",
  "tool_call": {
    "id": "call_abc123",
    "type": "function",
    "function": {
      "name": "GNS3TopologyTool",
      "arguments": {"project_id": "550e8400-e29b-41d4-a716-446655440000"}
    }
  }
}
```

#### 3.3 工具开始执行 (tool_start)

```json
{"type": "tool_start", "tool_name": "GNS3TopologyTool", "session_id": "xxx"}
```

#### 3.4 工具执行完成 (tool_end)

```json
{
  "type": "tool_end",
  "tool_name": "GNS3TopologyTool",
  "tool_output": "{\"nodes\": [{\"name\": \"Router1\", ...}], \"links\": [...]}"
}
```

#### 3.5 错误 (error)

```json
{"type": "error", "error": "Session not found", "session_id": "xxx"}
```

#### 3.6 完成 (done)

```json
{"type": "done", "session_id": "xxx"}
```

#### 3.7 心跳 (heartbeat)

```json
{"type": "heartbeat", "session_id": "xxx"}
```

**作用**: 保持 SSE 连接活跃，防止代理服务器/负载均衡器因超时断开连接。

**实现机制**:

```python
# 使用 asyncio.wait 实现超时检测
heartbeat_interval = 15.0  # 配置的心跳间隔（秒）

done, pending = await asyncio.wait(
    [next_event_task],
    timeout=heartbeat_interval
)

if done:
    # 收到事件，正常处理
    event = next_event_task.result()
    # ...
else:
    # 超时 - 发送心跳，保持连接
    yield {"type": "heartbeat", "session_id": session_id}
    # 继续等待下一个事件
```

**配置项** (可选):

```python
# 可通过配置控制
heartbeat_interval = 15.0   # 心跳间隔（秒），0 表示禁用
heartbeat_enabled = True     # 是否启用
```

**前端处理**:

- 前端收到 `heartbeat` 类型消息时可以忽略
- 主要用于维持连接，不需要渲染任何内容

### 4. 前端处理逻辑

前端 (`useChat.ts`) 根据 `type` 字段进行不同处理：

| type | 处理逻辑 |
|------|----------|
| `content` | 追加到当前 AI 消息内容 |
| `tool_call` | 创建 tool_call 类型的消息，显示工具调用信息 |
| `tool_start` | 可选：显示工具开始执行的状态 |
| `tool_end` | 创建 tool_result 类型的消息，显示工具执行结果 |
| `error` | 显示错误信息 |
| `done` | 标记流结束 |
| `heartbeat` | 忽略（保活信号） |

### 5. 会话历史格式 (ConversationHistory)

```python
class OpenAIMessage(BaseModel):
    """消息模型 (用于历史记录)"""
    id: str
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    name: Optional[str] = None           # 工具消息的名称
    tool_call_id: Optional[str] = None    # 工具消息关联的 tool_call ID
    tool_calls: Optional[List[OpenAIToolCall]] = None  # 助手消息的工具调用
    metadata: Dict[str, Any] = {}
    created_at: str


class ConversationHistory(BaseModel):
    """会话历史模型"""
    thread_id: str
    title: str
    messages: List[OpenAIMessage]
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    llm_calls: int = 0
```

## 核心实现

### 1. Chat Schemas

**文件**: `gns3server/schemas/controller/chat.py`

```python
from pydantic import BaseModel
from typing import Optional, List, Dict, Any, Literal

class ChatRequest(BaseModel):
    """Chat 请求模型"""
    message: str
    session_id: Optional[str] = None
    project_id: str
    stream: bool = True
    temperature: Optional[float] = None
    mode: Literal["text"] = "text"


class ChatResponse(BaseModel):
    """Chat 流式响应模型"""
    type: Literal["content", "tool_call", "tool_start", "tool_end", "error", "done", "heartbeat"]
    content: Optional[str] = None
    tool_call: Optional[Dict[str, Any]] = None
    tool_name: Optional[str] = None
    tool_output: Optional[str] = None
    error: Optional[str] = None
    session_id: Optional[str] = None


class ConversationHistory(BaseModel):
    """会话历史模型"""
    thread_id: str
    title: str
    messages: List[Dict[str, Any]]
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ChatSession(BaseModel):
    """会话模型"""
    session_id: str
    title: str
    project_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
```

### 2. AgentService

**文件**: `gns3server/agent/gns3_copilot/agent_service.py`

```python
"""
GNS3 Copilot Agent Service
为每个项目提供独立的 Agent 实例，使用项目目录的 SQLite 作为 checkpoint（异步版本）
"""

import os
import uuid
import logging
from typing import AsyncGenerator, Dict, List, Any, Optional
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
import aiosqlite

from gns3_copilot.agent.gns3_copilot import agent_builder

log = logging.getLogger(__name__)


class AgentService:
    """项目级 Agent Service（异步版本）"""

    def __init__(self, project_path: str, controller=None):
        """
        Args:
            project_path: GNS3 项目目录路径
            controller: GNS3 Controller 实例（可选，用于获取项目信息）
        """
        self.project_path = project_path
        self.controller = controller

        # 创建 checkpoint 目录
        self.checkpoint_dir = os.path.join(project_path, ".gns3-copilot")
        os.makedirs(self.checkpoint_dir, exist_ok=True)

        self._checkpointer: Optional[AsyncSqliteSaver] = None
        self._checkpointer_conn: Optional[aiosqlite.Connection] = None
        self._project_checkpoint_path: Optional[str] = None
        self._graph = None
        self._model_with_tools = None

    async def _get_checkpointer(self) -> AsyncSqliteSaver:
        """
        获取或创建 SQLite checkpointer。

        Returns:
            AsyncSqliteSaver instance
        """
        log.debug("Getting checkpointer for project at %s", self.project_path)

        # Create checkpoint file in the project directory
        checkpointer_path = os.path.join(self.checkpoint_dir, "copilot_checkpoints.db")
        log.debug("Checkpoint path: %s", checkpointer_path)

        # Store the path for reference
        self._project_checkpoint_path = checkpointer_path

        # Check if we already created a checkpointer for this project
        if self._checkpointer and self._project_checkpoint_path == checkpointer_path:
            log.debug("Reusing existing checkpointer")
            return self._checkpointer

        # Create new checkpointer using AsyncSqliteSaver
        log.debug("Creating new async checkpointer at %s", checkpointer_path)

        # Close existing connection if switching projects
        if self._checkpointer_conn:
            try:
                await self._checkpointer_conn.close()
                log.debug("Closed previous checkpointer connection")
            except Exception as e:
                log.warning("Error closing old checkpointer connection: %s", e)

        # Create new connection
        conn = await aiosqlite.connect(checkpointer_path)
        # Enable WAL mode for better concurrent performance
        await conn.execute("PRAGMA journal_mode=WAL;")
        self._checkpointer_conn = conn  # Save connection reference to prevent GC
        self._checkpointer = AsyncSqliteSaver(conn)

        # CRITICAL: Initialize database schema
        await self._checkpointer.setup()

        log.info("Project async checkpointer created and initialized at %s", checkpointer_path)

        return self._checkpointer

    def _get_model_with_tools(self):
        """
        Get model with tools bound.
        """
        if self._model_with_tools is None:
            log.debug("Binding tools to model...")
            from gns3server.agent.gns3_copilot.model_factory import create_base_model_with_tools
            from gns3server.agent.gns3_copilot.tools import get_tools

            model = self._create_model()
            tools = get_tools()
            self._model_with_tools = model.bind_tools(tools)
            log.info("Model bound with %d tools", len(tools))
        return self._model_with_tools

    def _create_model(self):
        """创建基础模型"""
        from gns3server.agent.gns3_copilot.model_factory import create_base_model
        return create_base_model()

    @property
    async def checkpointer(self) -> AsyncSqliteSaver:
        """获取 SQLite checkpointer"""
        if self._checkpointer is None:
            return await self._get_checkpointer()
        return self._checkpointer

    @property
    async def graph(self):
        """获取或编译 LangGraph"""
        if self._graph is None:
            checkpointer = await self.checkpointer
            self._graph = agent_builder.compile(checkpointer=checkpointer)
        return self._graph

    async def close(self):
        """关闭连接"""
        if self._checkpointer_conn:
            try:
                await self._checkpointer_conn.close()
                log.debug("Checkpointer connection closed")
            except Exception as e:
                log.warning("Error closing checkpointer connection: %s", e)
            finally:
                self._checkpointer_conn = None
                self._checkpointer = None
                self._graph = None
                self._model_with_tools = None

    async def stream_chat(
        self,
        message: str,
        session_id: str,
        project_id: Optional[str] = None,
        user_id: Optional[str] = None,
        jwt_token: Optional[str] = None,
        mode: str = "text"
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """流式处理 chat 请求"""

        # 构建 config，包含用户认证信息
        config = {
            "configurable": {
                "thread_id": session_id,
                "user_id": user_id,
                "jwt_token": jwt_token,
            }
        }

        # 获取项目信息
        project_info = None
        if project_id:
            try:
                from gns3server.controller import Controller
                controller = Controller.instance()
                project = controller.projects.get(project_id)
                if project:
                    project_info = (
                        project.name,
                        project.id,
                        len(project.nodes),
                        len(project.links),
                        project.status
                    )
            except Exception:
                pass

        # 构建输入
        inputs = {
            "messages": [HumanMessage(content=message)],
            "llm_calls": 0,
            "remaining_steps": 20,
            "mode": mode,
        }

        if project_info:
            inputs["selected_project"] = project_info

        # 流式处理
        try:
            async for event in self.graph.astream_events(inputs, config=config, version="v2"):
                chunk = self._convert_event_to_chunk(event)
                if chunk:
                    yield chunk

            yield {"type": "done", "session_id": session_id}

        except Exception as e:
            yield {"type": "error", "error": str(e), "session_id": session_id}

    def _convert_event_to_chunk(self, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """将 LangGraph 事件转换为 API 响应块"""
        event_type = event.get("event", "")

        if event_type == "on_chat_model_stream":
            content = event.get("data", {}).get("chunk", {}).get("content", "")
            if content:
                return {"type": "content", "content": content}

        elif event_type == "on_tool_start":
            return {
                "type": "tool_start",
                "tool_name": event.get("name", ""),
                "session_id": self.session_id
            }

        elif event_type == "on_tool_end":
            return {
                "type": "tool_end",
                "tool_name": event.get("name", ""),
                "tool_output": event.get("data", {}).get("output", ""),
                "session_id": self.session_id
            }

        return None

    async def get_history(self, session_id: str, limit: int = 100) -> Dict[str, Any]:
        """获取会话历史"""
        config = {"configurable": {"thread_id": session_id}}

        try:
            state = await self.graph.aget_state(config)
            if state and "messages" in state.values:
                messages = []
                for msg in state.values["messages"][-limit:]:
                    messages.append({
                        "type": type(msg).__name__,
                        "content": msg.content if hasattr(msg, 'content') else str(msg)
                    })

                title = state.values.get("conversation_title", "New Conversation")

                return {
                    "thread_id": session_id,
                    "title": title,
                    "messages": messages
                }
        except Exception:
            pass

        return {
            "thread_id": session_id,
            "title": "New Conversation",
            "messages": []
        }

    def close(self):
        """关闭连接"""
        if self._checkpointer:
            self._checkpointer.conn.close()
```

### 3. ProjectAgentManager

**文件**: `gns3server/agent/gns3_copilot/project_agent_manager.py`

```python
"""
Project Agent Manager
管理每个项目的 Agent Service 实例（单例模式）
"""

import os
from typing import Dict, Optional
from threading import Lock

from gns3server.agent.gns3_copilot.agent_service import AgentService


class ProjectAgentManager:
    """项目级 Agent 管理器"""

    _instance = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._agents: Dict[str, AgentService] = {}
        return cls._instance

    def get_agent(self, project_id: str, project_path: str) -> AgentService:
        """
        获取或创建项目的 Agent Service
        """
        key = project_id

        with self._lock:
            if key not in self._agents:
                self._agents[key] = AgentService(project_path)
            return self._agents[key]

    def remove_agent(self, project_id: str):
        """移除项目的 Agent Service"""
        key = project_id

        with self._lock:
            if key in self._agents:
                self._agents[key].close()
                del self._agents[key]

    def close_all(self):
        """关闭所有 Agent"""
        with self._lock:
            for agent in self._agents.values():
                agent.close()
            self._agents.clear()


# 全局单例
_project_agent_manager: Optional[ProjectAgentManager] = None


def get_project_agent_manager() -> ProjectAgentManager:
    """获取项目 Agent 管理器"""
    global _project_agent_manager
    if _project_agent_manager is None:
        _project_agent_manager = ProjectAgentManager()
    return _project_agent_manager
```

### 4. Chat API Routes

**文件**: `gns3server/api/routes/controller/chat.py`

```python
"""
Chat API endpoints
"""

import json
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, status, Request
from fastapi.responses import StreamingResponse

from gns3server.schemas.controller.chat import (
    ChatRequest, ChatResponse, ConversationHistory, ChatSession
)
from gns3server.agent.gns3_copilot.project_agent_manager import get_project_agent_manager
from gns3server.controller import Controller
from gns3server.controller.controller_error import ControllerNotFoundError
from gns3server.api.routes.controller.dependencies.authentication import get_current_active_user


router = APIRouter()


@router.post("/stream")
async def stream_chat(
    request: ChatRequest,
    http_request: Request,
    current_user = Depends(get_current_active_user)
):
    """流式 Chat API"""

    # 验证项目
    project_path = None
    if request.project_id:
        try:
            controller = Controller.instance()
            project = controller.projects.get(request.project_id)
            if not project:
                raise ControllerNotFoundError(f"Project '{request.project_id}' not found")
            project_path = project.path
        except ControllerNotFoundError:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid project: {e}")

    if not project_path:
        raise HTTPException(status_code=400, detail="project_id is required")

    # 获取用户认证信息
    user_id = str(current_user.user_id)

    # 获取 JWT token (从 Authorization header)
    auth_header = http_request.headers.get("Authorization", "")
    jwt_token = auth_header.replace("Bearer ", "") if auth_header else None

    # 获取 Agent Service
    agent_manager = get_project_agent_manager()
    agent_service = agent_manager.get_agent(request.project_id, project_path)

    session_id = request.session_id or str(uuid.uuid4())

    async def generate():
        try:
            async for chunk in agent_service.stream_chat(
                message=request.message,
                session_id=session_id,
                project_id=request.project_id,
                user_id=user_id,
                jwt_token=jwt_token,
                mode=request.mode
            ):
                try:
                    validated = ChatResponse(**chunk)
                    yield f"data: {json.dumps(validated.model_dump(exclude_none=True), ensure_ascii=False)}\n\n"
                except Exception:
                    pass

            yield f"data: {json.dumps({'type': 'done', 'session_id': session_id})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/history/{session_id}")
async def get_history(
    session_id: str,
    project_id: str,
    limit: int = 100,
    current_user = Depends(get_current_active_user)
):
    """获取会话历史"""

    controller = Controller.instance()
    project = controller.projects.get(project_id)
    if not project:
        raise ControllerNotFoundError(f"Project '{project_id}' not found")

    agent_manager = get_project_agent_manager()
    agent_service = agent_manager.get_agent(project_id, project.path)

    history = await agent_service.get_history(session_id, limit)
    return history
```

### 5. 注册路由

**文件**: `gns3server/api/routes/controller/__init__.py`

添加 chat router 注册：

```python
from . import chat

# ... 其他 router ...

router.include_router(
    chat.router,
    prefix="/chat",
    tags=["Chat"]
)
```

## API 端点

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/v3/chat/stream` | 流式 Chat（主要接口） |
| GET | `/v3/chat/history/{session_id}?project_id=xxx` | 获取会话历史 |

## SSE 消息格式

```json
// 内容块
{"type": "content", "content": "Hello!"}

// 工具开始
{"type": "tool_start", "tool_name": "GNS3TopologyTool", "session_id": "xxx"}

// 工具结束
{"type": "tool_end", "tool_name": "GNS3TopologyTool", "tool_output": "...", "session_id": "xxx"}

// 完成
{"type": "done", "session_id": "xxx"}

// 错误
{"type": "error", "error": "Error message", "session_id": "xxx"}
```

## 项目生命周期集成

在项目打开/关闭时，需要管理 Agent Service 实例：

```python
# 项目打开时
project_agent_manager.get_agent(project_id, project.path)

# 项目关闭时
project_agent_manager.remove_agent(project_id)
```

可以监听项目事件或使用信号机制实现。

## 依赖项

确保以下包已安装：

- `langchain` >= 0.3.0
- `langgraph` >= 0.2.0
- `langchain-core`
- `sqlalchemy` (LangGraph 依赖)

## 参考资料

- [LangGraph Checkpoint Documentation](https://langchain-ai.github.io/langgraph/how-tos/checkpointers/)
- [FlowNet-Lab Chat API](file:///home/yueguobin/myCode/GNS3/FlowNet-Lab/backend/api/v1/chat.py)
- [FlowNet-Lab Agent Service](file:///home/yueguobin/myCode/GNS3/FlowNet-Lab/backend/core/agent.py)
