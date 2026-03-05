# Force Kill (kill -9) 导致残留进程问题

## 问题描述

当使用 `kill -9` 强制关闭 gns3server 进程后，重新启动 gns3server 会出现以下错误：

### 1. Dynamips VM 创建失败
```
ERROR gns3server.api.routes.compute:133 Compute node error: Dynamips error when running command 'vm create "R1" 1 c7200
': unable to create VM instance 'R1'
```

### 2. project_id 为 "undefined" 的验证错误
```
ERROR gns3server.api.server:208 Request validation error in /v3/projects/undefined/nodes/{node_id} (PUT):
1 validation error:
  {'type': 'uuid_parsing', 'loc': ('path', 'project_id'), 'msg': 'Input should be a valid UUID, invalid character: expected an optional prefix of `urn:uuid:` followed by [0-9a-fA-F-], found `u` at 1', 'input': 'undefined', ...}
```

### 3. TCP 端口仍在使用的警告
```
WARNING gns3server.compute.project:355 Project d672144c-4de9-4a97-a23d-307ddc3ab9b1 has TCP ports still in use: {5001}
```

## 根本原因

使用 `kill -9` 强制终止 gns3server 进序时，gns3server 没有机会正确清理其启动的子进程，导致以下残留进程仍在运行：

- **Dynamips hypervisor 进程** (dynamips)
- **VPCS 虚拟 PC 进程** (vpcs)
- **Docker 容器**（虽然在日志中显示被移除，但可能有些状态未清理）
- **其他模拟器进程**

这些残留进程会：
1. 占用相同的端口号和资源 ID
2. 保持旧的 socket 连接
3. 导致新启动的 gns3server 无法重新分配相同资源

## 解决方案

### 方法 1：手动清理残留进程（推荐）

在强制关闭 gns3server 后，查找并清理残留进程：

```bash
# 查找 dynamips 进程
ps aux | grep dynamips

# 查找 vpcs 进程
ps aux | grep vpcs

# 终止残留进程
killall dynamips
killall vpcs
```

### 方法 2：使用 pkill 清理相关进程

```bash
# 清理所有 GNS3 相关进程
pkill -9 dynamips
pkill -9 vpcs
pkill -6 ubridge
```

### 方法 3：重启前检查

在重新启动 gns3server 之前，确保没有残留进程：

```bash
# 检查是否有残留的 GNS3 进程
ps aux | grep -E "(dynamips|vpcs|ubridge|gns3)" | grep -v grep
```

## 预防措施

### 1. 使用正确的关闭方法

优先使用以下方法关闭 gns3server，而不是 `kill -9`：

```bash
# 如果使用 systemd
sudo systemctl stop gns3server

# 如果直接运行
# 按 Ctrl+C 或使用正常的 kill 信号
kill <gns3server-pid>
```

### 2. 使用 SIGTERM 而不是 SIGKILL

```bash
# 先尝试正常终止（允许进程清理）
kill -15 <gns3server-pid>

# 等待几秒，如果进程仍在运行，再使用 kill -9
sleep 3
if ps -p <gns3server-pid> > /dev/null; then
    kill -9 <gns3server-pid>
fi
```

### 3. 实现自动清理脚本

可以创建一个启动脚本来检查并清理残留进程：

```bash
#!/bin/bash
# cleanup_before_start.sh

# 检查并清理残留的 dynamips 进程
if pgrep -f dynamips > /dev/null; then
    echo "发现残留的 dynamips 进程，正在清理..."
    killall -9 dynamips
fi

# 检查并清理残留的 vpcs 进程
if pgrep -f vpcs > /dev/null; then
    echo "发现残留的 vpcs 进程，正在清理..."
    killall -9 vpcs
fi

# 等待端口释放
sleep 1

# 启动 gns3server
gns3server
```

## 技术细节

### 为什么 kill -9 会导致这个问题？

1. **SIGKILL 信号无法被捕获**：进程无法捕获或忽略 SIGKILL 信号，因此没有机会执行清理代码
2. **子进程成为孤儿进程**：父进程被强制终止后，子进程被 init/PID 1 接管，但它们不知道父进程已死
3. **资源未释放**：socket、端口、文件锁等资源没有被正确释放
4. **状态不一致**：gns3server 的内部状态（如端口分配、ID 分配）被清除，但实际资源仍被占用

### 涉及的代码位置

- **Dynamips 进程管理**：`gns3server/compute/dynamips/`
- **端口分配和跟踪**：`gns3server/compute/project.py:355`
- **节点更新 API**：`gns3server/api/routes/controller/nodes.py:230`

## 相关问题

- [ ] 考虑在 gns3server 启动时自动检测并清理残留进程
- [ ] 添加进程健康检查机制
- [ ] 实现更健壮的端口和 ID 重用逻辑
- [ ] 添加残留进程检测和警告
