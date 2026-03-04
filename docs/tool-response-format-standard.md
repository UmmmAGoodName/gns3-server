# GNS3 Copilot Tool Response Format Standard

## 概述

本文档定义了 GNS3 Copilot 工具的标准响应格式，确保所有工具返回统一的数据结构，便于前端处理和美化显示。

## 标准响应格式

### 顶层结构

所有工具应返回以下标准格式：

```python
{
    "success": bool,           # 整体操作是否成功
    "total": int,              # 总操作数量
    "successful": int,         # 成功数量
    "failed": int,             # 失败数量
    "data": list[dict],       # 详细结果列表
    "error": str,             # 全局错误信息（可选，操作完全失败时）
    "metadata": dict          # 元数据（可选）
}
```

**字段说明**：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `success` | `bool` | 是 | 整体操作是否成功（`failed == 0` 时为 `True`） |
| `total` | `int` | 是 | 处理的项目总数 |
| `successful` | `int` | 是 | 成功的项目数量 |
| `failed` | `int` | 是 | 失败的项目数量 |
| `data` | `list[dict]` | 是 | 每个项目的详细结果 |
| `error` | `str` | 否 | 全局错误消息（当整个操作失败时） |
| `metadata` | `dict` | 否 | 元数据（时间戳、执行时间等） |

### 单个项目格式

`data` 数组中的每个项目应遵循以下格式：

```python
{
    "id": str,                 # 设备/节点/链接 ID
    "name": str,               # 人类可读的名称
    "status": "success" | "failed",  # 项目状态
    "result": str,             # 成功时的结果或输出
    "error": str               # 失败时的错误信息
}
```

**字段说明**：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `id` | `str` | 是 | 设备/节点/链接的唯一标识符 |
| `name` | `str` | 是 | 人类可读的名称 |
| `status` | `str` | 是 | `"success"` 或 `"failed"` |
| `result` | `str` | 条件 | 状态为 `success` 时的输出 |
| `error` | `str` | 条件 | 状态为 `failed` 时的错误信息 |

## 示例

### 成功响应示例

```python
# 执行多个设备的显示命令
{
    "success": True,
    "total": 3,
    "successful": 2,
    "failed": 1,
    "data": [
        {
            "id": "R1",
            "name": "Router1",
            "status": "success",
            "result": "Cisco IOS Software...\nRouter1# show version\n..."
        },
        {
            "id": "R2",
            "name": "Router2",
            "status": "success",
            "result": "Cisco IOS Software...\nRouter2# show version\n..."
        },
        {
            "id": "R3",
            "name": "Router3",
            "status": "failed",
            "error": "Connection refused"
        }
    ],
    "metadata": {
        "tool_name": "execute_multiple_device_commands",
        "execution_time": 5.2
    }
}
```

### 完全失败示例

```python
# 整个操作失败（如参数错误）
{
    "success": False,
    "total": 0,
    "successful": 0,
    "failed": 0,
    "data": [],
    "error": "Invalid project_id format",
    "metadata": {
        "tool_name": "execute_multiple_device_commands"
    }
}
```

### 单个设备操作示例

```python
# 操作单个设备
{
    "success": True,
    "total": 1,
    "successful": 1,
    "failed": 0,
    "data": [
        {
            "id": "PC1",
            "name": "VPCS-1",
            "status": "success",
            "result": "IP configuration updated: 192.168.1.10/24"
        }
    ],
    "metadata": {}
}
```

## 使用标准化函数

在 `gns3server.agent.gns3_copilot.utils` 模块中提供了 `normalize_tool_response` 函数，用于将各种格式转换为标准格式：

```python
from gns3server.agent.gns3_copilot.utils import normalize_tool_response

# 标准化工具响应
normalized = normalize_tool_response(raw_response, tool_name="my_tool")
```

该函数支持：
- 列表格式（`[{...}, {...}]`）
- 字典格式（`{"nodes": [...]}`）
- 字符串格式（自动解析 JSON/Python literal）
- 混合格式（兼容旧工具）

## 兼容性

### 向后兼容

`normalize_tool_response` 函数设计为向后兼容，可以处理现有工具的各种格式：

- `status` / `error` 字段
- `output` / `result` 字段
- `device_name` / `name` 字段
- `total_nodes` / `total` 字段

### 推荐的迁移策略

1. **新工具**：直接返回标准格式
2. **现有工具**：保持不变，使用 `normalize_tool_response` 标准化
3. **前端**：依赖标准格式处理显示

## 前端集成建议

### 渲染逻辑

```javascript
function renderToolResponse(response) {
    if (!response.success) {
        // 显示全局错误
        showError(response.error);
        return;
    }

    // 显示统计摘要
    showSummary(response.total, response.successful, response.failed);

    // 渲染每个项目
    response.data.forEach(item => {
        if (item.status === 'success') {
            showSuccess(item.name, item.result);
        } else {
            showError(item.name, item.error);
        }
    });
}
```

### 状态图标

| 状态 | 图标建议 | 颜色 |
|------|----------|------|
| `success` | ✓ 绿色 | 绿色 |
| `failed` | ✗ 红色 | 红色 |
| `unknown` | ? 灰色 | 灰色 |

## 版本控制

当前标准版本：`v1.0`

格式变更时，应更新 `metadata.version` 字段，前端据此适配。

## 参考

- 实现：`gns3server/agent/gns3_copilot/utils/parse_tool_content.py`
- 消息转换：`gns3server/agent/gns3_copilot/utils/message_converters.py`
- 工具示例：`gns3server/agent/gns3_copilot/tools_v2/`
