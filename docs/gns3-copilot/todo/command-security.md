# 命令安全配置

## 概述

GNS3-Copilot 包含一个命令安全验证系统，用于防止在实验室环境中执行潜在危险或不合适的命令。这有助于：

- **防止安全告警**：`traceroute` 等命令可能触发安全监控系统
- **保护实验室设备**：危险命令（泛洪 ping、debug）可能压垮或崩溃设备
- **保持安全性**：在教学环境中尤其重要

## 默认禁止的命令

### 全局禁止命令（所有工具）

| 模式 | 描述 | 原因 |
|------|------|------|
| `traceroute` | 网络路由跟踪 | 可能触发安全告警并产生大量流量 |
| `tracepath` | 网络路由跟踪 | 类似 traceroute |
| `tracert` | Windows traceroute | 类似 traceroute |
| `ping.*-f` | 泛洪 ping | 可能压垮实验室设备 |
| `ping.*\s+count\s+\d{3,}` | 大量 ping | 过量的 ping 流量 |
| `^debug\s+` | 调试命令 | 可能崩溃或 destabilize 设备 |
| `^test\s+` | 测试命令 | 可能影响设备稳定性 |

### 工具特定限制

**诊断工具**（仅允许诊断/show 命令）：
- `conf t` / `configure terminal` - 配置模式
- `end` / `exit` - 配置模式命令

**VPCS 工具**：
- `traceroute` - VPCS 路由跟踪

## 用户配置

### 覆盖默认规则

要允许默认禁止的特定命令，创建 `command_security_override.json` 文件：

```json
{
  "allowed_commands": [
    "traceroute"
  ]
}
```

### 添加额外的禁止命令

要添加自己的限制：

```json
{
  "forbidden_commands": [
    "my_dangerous_command",
    "another_pattern.*"
  ]
}
```

### 完整示例

```json
{
  "allowed_commands": [
    "traceroute"
  ],
  "forbidden_commands": [
    "show running-config"
  ]
}
```

## 配置文件位置

覆盖文件将在以下位置查找（按顺序）：

1. `/etc/gns3-server/command_security_override.json`（系统级）
2. `<项目目录>/command_security_override.json`（项目级）

找到的第一个文件将被使用。

## 安全级别

虽然没有明确的"安全级别"，但默认配置设计为适合大多数实验室和教学场景：

- **教学安全**：默认阻止危险命令
- **灵活可配置**：用户可以根据需要覆盖
- **透明可审计**：所有限制都有文档说明

## 使用示例

### 示例 1：允许 Traceroute

**文件：`command_security_override.json`**
```json
{
  "allowed_commands": [
    "traceroute"
  ]
}
```

### 示例 2：阻止特定命令

**文件：`command_security_override.json`**
```json
{
  "forbidden_commands": [
    "show running-config"
  ]
}
```

### 示例 3：允许所有命令（不推荐）

**文件：`command_security_override.json`**
```json
{
  "allowed_commands": [
    ".*"
  ]
}
```

**警告**：这将禁用所有安全限制，不推荐。

## 实现细节

### 配置文件

- **默认配置**：`gns3server/agent/gns3_copilot/config/command_security.json`
- **用户覆盖**：`command_security_override.json`（用户创建）

### 组件

1. **配置加载器** (`utils/command_security_config.py`)
   - 加载默认和用户配置
   - 合并允许/禁止模式
   - 提供编译后的正则表达式模式

2. **命令验证器** (`utils/command_validator.py`)
   - 根据安全规则验证命令
   - 返回清晰的错误消息
   - 集成到现有工具中

### 集成位置

安全验证已集成到：

- **诊断工具** (`display_tools_nornir.py`)
- **配置工具** (`config_tools_nornir.py`)
- **VPCS 工具** (`vpcs_tools_telnetlib3.py`)

## 故障排除

### 命令被意外阻止

如果看到错误消息 `"Command not allowed: traceroute"`：

1. 检查命令是否在默认禁止列表中
2. 创建覆盖文件，在 `allowed_commands` 中添加该命令
3. 重启 GNS3 服务器

### 覆盖文件不工作

1. 验证文件位置是否正确
2. 检查 JSON 语法是否有效
3. 检查服务器日志中的加载错误

## 安全考虑

### 为什么禁止这些命令？

- **Traceroute**：生成大量数据包，可能触发 IDS/IPS
- **泛洪 ping**：可能对实验室设备进行 DoS 攻击
- **调试命令**：可能崩溃或 destabilize 生产设备
- **诊断工具中的配置命令**：防止意外的配置更改

### 最佳实践

1. **教学环境**：使用默认配置（安全）
2. **个人实验室**：考虑你真正需要什么
3. **类似生产环境**：保持限制启用
4. **始终审查**：在允许命令之前了解为什么它被阻止

## 未来增强

可能的未来改进（尚未实现）：

- [ ] 每项目配置文件
- [ ] 通过 GNS3 Web UI 配置
- [ ] 被阻止命令的审计日志
- [ ] 可配置的安全预设（strict/standard/loose）
- [ ] 基于时间的限制（例如，上课时间禁止危险命令）

## 反馈和问题

如果你：

- 发现默认应该阻止的命令
- 由于合法使用场景需要允许命令
- 有改进安全的建议

请在 GitHub 上提交 issue：https://github.com/yueguobin/gns3-copilot/issues

## 相关文档

- [工具实现](../gns3-copilot/tools_v2/README.md)
- [安全策略](../../SECURITY.md)
- [贡献指南](../../CONTRIBUTING.md)
