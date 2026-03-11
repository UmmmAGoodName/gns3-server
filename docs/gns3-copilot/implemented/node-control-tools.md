# Node Control Tools

## Overview

GNS3-Copilot provides tools for controlling the lifecycle of network devices in GNS3 projects. These tools enable AI agents to start, stop, suspend, and manage nodes as part of automated lab management workflows.

## Available Tools

### GNS3StartNodeTool

**Tool Name:** `start_gns3_node`

**Description:** Starts one or multiple nodes in a GNS3 project with progress tracking and status monitoring.

**Input:**
```json
{
  "project_id": "uuid-of-project",
  "node_ids": ["uuid-of-node-1", "uuid-of-node-2"]
}
```

**Output:**
```json
{
  "project_id": "...",
  "total_nodes": 2,
  "successful": 2,
  "failed": 0,
  "nodes": [
    {"node_id": "...", "name": "...", "status": "started"},
    {"node_id": "...", "name": "...", "status": "started"}
  ]
}
```

**Features:**
- Batch start multiple nodes
- Progress bar with visual feedback
- Automatic status verification
- Comprehensive error handling
- ~140s base wait time + 10s per additional node

**Use Cases:**
- Automated lab deployment
- Multi-node topology initialization
- Lab startup automation

### GNS3StartNodeQuickTool

**Tool Name:** `start_gns3_node_quick`

**Description:** Starts nodes in a GNS3 project WITHOUT waiting for startup completion. Suitable for automated deployment workflows where long waits would cause HTTP timeouts.

**Input:**
```json
{
  "project_id": "uuid-of-project",
  "node_ids": ["uuid-of-node-1", "uuid-of-node-2"]
}
```

**Output:**
```json
{
  "project_id": "...",
  "total_nodes": 2,
  "successful": 2,
  "failed": 0,
  "nodes": [
    {"node_id": "...", "name": "...", "status": "started"}
  ],
  "note": "Start commands sent. Nodes are booting in background. Check node status later."
}
```

**Features:**
- Sends start commands immediately
- No waiting for startup completion
- Returns initial status
- Prevents HTTP timeouts in automated workflows

**Use Cases:**
- Automated CI/CD pipelines
- Bulk node deployment
- Workflows requiring immediate return

### GNS3StopNodeTool ✨

**Tool Name:** `stop_gns3_node`

**Description:** Stops one or multiple nodes in a GNS3 project.

**Input:**
```json
{
  "project_id": "uuid-of-project",
  "node_ids": ["uuid-of-node-1", "uuid-of-node-2"]
}
```

**Output:**
```json
{
  "project_id": "...",
  "total_nodes": 2,
  "successful": 2,
  "failed": 0,
  "nodes": [
    {"node_id": "...", "name": "...", "status": "stopped"},
    {"node_id": "...", "name": "...", "status": "stopped"}
  ]
}
```

**Features:**
- Batch stop multiple nodes
- Immediate API response (no waiting)
- Automatic status verification
- Comprehensive error handling
- Synchronous operation

**Use Cases:**
- Lab shutdown automation
- Resource management
- Energy-saving workflows
- Test cleanup procedures

**Implementation Details:**
- Calls `POST /projects/{project_id}/nodes/{node_id}/stop`
- Verifies node existence before stopping
- Retrieves updated status after stop command
- Returns detailed results for each node

### GNS3SuspendNodeTool ✨

**Tool Name:** `suspend_gns3_node`

**Description:** Suspends one or multiple nodes in a GNS3 project. Suspended nodes preserve their state in memory and can be quickly resumed.

**Input:**
```json
{
  "project_id": "uuid-of-project",
  "node_ids": ["uuid-of-node-1", "uuid-of-node-2"]
}
```

**Output:**
```json
{
  "project_id": "...",
  "total_nodes": 2,
  "successful": 2,
  "failed": 0,
  "nodes": [
    {"node_id": "...", "name": "...", "status": "suspended"},
    {"node_id": "...", "name": "...", "status": "suspended"}
  ],
  "note": "Suspended nodes preserve their state in memory. Use resume to continue where you left off."
}
```

**Features:**
- Batch suspend multiple nodes
- Preserves device state in memory
- Immediate API response (no waiting)
- Fast resume capability
- Automatic status verification
- Comprehensive error handling

**Use Cases:**
- Temporary lab pause (continue later)
- Save experimental state
- Quick context switching
- Resource optimization without losing work

**Key Benefits:**
- **Fast Resume**: Resumes in seconds vs. minutes for full restart
- **State Preservation**: All configurations, connections, and runtime state saved
- **Resource Efficiency**: Pauses devices without releasing memory
- **Lab Snapshots**: Save intermediate states for later analysis

**Implementation Details:**
- Calls `POST /projects/{project_id}/nodes/{node_id}/suspend`
- Verifies node existence before suspending
- Retrieves updated status after suspend command
- Returns detailed results for each node
- Node name can be changed while suspended (unlike started state)

**State Comparison:**

| Operation | Result | Recovery Time | State Preserved? | Resource Usage |
|-----------|--------|---------------|------------------|----------------|
| **Stop** | Powered off | Slow (full boot) | ❌ No | Minimal |
| **Suspend** | Paused | Fast (seconds) | ✅ Yes | Medium (memory) |
| **Start** | Running | N/A | N/A | High |

**When to Use Suspend vs Stop:**

```python
# ✅ Use SUSPEND when:
# - Taking a break and continuing later today
# - Need to test something else temporarily
# - Want to preserve complex configuration state
# - Quick switching between lab scenarios

# ✅ Use STOP when:
# - Done with the lab for now
# - Need to free up system resources
# - Finishing a complete test session
# - Won't need the lab for a while
```

## Technical Implementation

### Module Structure

```
gns3server/agent/gns3_copilot/tools_v2/
├── gns3_start_node.py     # Start tools
├── gns3_stop_node.py      # Stop tool
└── gns3_suspend_node.py   # Suspend tool
```

### API Integration

The tools use the `Node` class from `custom_gns3fy`:

```python
from gns3server.agent.gns3_copilot.gns3_client import Node

# Start node
node.start()

# Stop node
node.stop()

# Suspend node
node.suspend()
```

### Progress Tracking

**GNS3StartNodeTool** includes visual progress bar:

```
Starting 3 node(s), please wait...
[===========>                      ] 35.0%
```

**Progress Calculation:**
- Base duration: 140 seconds
- Extra duration: 10 seconds per additional node
- Formula: `total_duration = 140 + max(0, node_count - 1) * 10`

**GNS3StopNodeTool** does not include progress tracking:
- Stop operations are typically fast (< 5 seconds)
- Immediate API response provides status feedback
- No need for progress indication

**GNS3SuspendNodeTool** does not include progress tracking:
- Suspend operations are typically fast (< 10 seconds)
- Immediate API response provides status feedback
- No need for progress indication

## Node State Transitions

```
                    ┌─────────┐
                    │ Stopped │◀─────── stop()
                    └────┬────┘
                         │
                         │ start()
                         ▼
                   ┌──────────┐
                   │ Started  │───suspend()───▶ Suspended
                   └──────────┘                          │
                      ▲      │                          │
                      │      │ stop()                   │ resume()
                      └──────┴──────────────────────────┘
```

**State Change Allowed Operations:**

| Current State | Can Start? | Can Stop? | Can Suspend? | Can Rename? |
|---------------|------------|-----------|---------------|--------------|
| **Stopped**   | ✅ Yes     | ❌ No      | ❌ No         | ✅ Yes       |
| **Started**   | ❌ No      | ✅ Yes     | ✅ Yes        | ❌ No*       |
| **Suspended** | ✅ Yes     | ✅ Yes     | ❌ No         | ✅ Yes       |

*Except special node types: cloud, nat, ethernet_switch, ethernet_hub, frame_relay_switch, atm_switch

## Copilot Mode Integration

### Teaching Assistant Mode

**Tools Available:**
- `GNS3StartNodeTool` - For diagnostics requiring started nodes

**Capabilities:**
- READ-ONLY diagnostic tools
- Cannot stop or suspend nodes (prevents disruption of active labs)

### Lab Automation Assistant Mode

**Tools Available:**
- `GNS3StartNodeTool` - Full lab deployment
- `GNS3StopNodeTool` - Full lab shutdown
- `GNS3SuspendNodeTool` - Lab pause with state preservation ✨
- `GNS3StartNodeQuickTool` - Fast automated deployment

**Capabilities:**
- Full diagnostic and configuration tools
- Complete lab lifecycle management (start/stop/suspend)
- Automated workflows with state preservation
- Lab snapshot capabilities for later resumption

## Usage Examples

### Example 1: Start Nodes with Progress

```python
from gns3server.agent.gns3_copilot.tools_v2 import GNS3StartNodeTool

tool = GNS3StartNodeTool()
result = tool._run(json.dumps({
    "project_id": "abc-123-def",
    "node_ids": ["node-1", "node-2", "node-3"]
}))

# Output includes progress bar and final status
```

### Example 2: Quick Start for CI/CD

```python
from gns3server.agent.gns3_copilot.tools_v2 import GNS3StartNodeQuickTool

tool = GNS3StartNodeQuickTool()
result = tool._run(json.dumps({
    "project_id": "abc-123-def",
    "node_ids": ["node-1"]
}))

# Immediate return without waiting
```

### Example 3: Stop Nodes

```python
from gns3server.agent.gns3_copilot.tools_v2 import GNS3StopNodeTool

tool = GNS3StopNodeTool()
result = tool._run(json.dumps({
    "project_id": "abc-123-def",
    "node_ids": ["node-1", "node-2"]
}))

# Immediate return with stop status
```

### Example 4: Automated Lab Lifecycle

```python
# Lab deployment
start_tool = GNS3StartNodeQuickTool()
start_result = start_tool._run(json.dumps({
    "project_id": project_id,
    "node_ids": all_node_ids
}))

# ... Run tests ...

# Lab shutdown
stop_tool = GNS3StopNodeTool()
stop_result = stop_tool._run(json.dumps({
    "project_id": project_id,
    "node_ids": all_node_ids
}))
```

### Example 5: Lab Pause and Resume ✨

```python
from gns3server.agent.gns3_copilot.tools_v2 import GNS3SuspendNodeTool

# Start lab
start_tool = GNS3StartNodeTool()
start_result = start_tool._run(json.dumps({
    "project_id": project_id,
    "node_ids": all_node_ids
}))

# ... Configure devices ...
# ... Run some tests ...

# Suspend lab (preserves all state)
suspend_tool = GNS3SuspendNodeTool()
suspend_result = suspend_tool._run(json.dumps({
    "project_id": project_id,
    "node_ids": all_node_ids
}))
# Nodes suspended - state preserved in memory

# ... Take a break, work on something else ...

# Resume lab (quick recovery)
start_result = start_tool._run(json.dumps({
    "project_id": project_id,
    "node_ids": all_node_ids
}))
# Back to previous state in seconds!
```

### Example 6: Suspend While Renaming Nodes ✨

```python
from gns3server.agent.gns3_copilot.tools_v2 import (
    GNS3SuspendNodeTool,
    GNS3UpdateNodeNameTool
)

# Suspend nodes first (allows renaming)
suspend_tool = GNS3SuspendNodeTool()
suspend_result = suspend_tool._run(json.dumps({
    "project_id": project_id,
    "node_ids": node_ids
}))

# Now rename nodes (possible while suspended!)
rename_tool = GNS3UpdateNodeNameTool()
rename_result = rename_tool._run(json.dumps({
    "project_id": project_id,
    "nodes": [
        {"node_id": "node-1", "new_name": "Router-Primary"},
        {"node_id": "node-2", "new_name": "Router-Backup"}
    ]
}))

# Resume when ready
# Note: Cannot rename while started, but CAN rename while suspended!
```

## Error Handling

All tools include comprehensive error handling:

### Missing Required Fields

```json
{
  "error": "Missing required fields: project_id and node_ids."
}
```

### Invalid Input Type

```json
{
  "error": "node_ids must be a list."
}
```

### Node Not Found

```json
{
  "node_id": "uuid",
  "name": "N/A",
  "status": "error",
  "error": "Node not found"
}
```

### Connection Error

```json
{
  "error": "Failed to connect to GNS3 server. Please check your configuration."
}
```

## Security Considerations

### Access Control

- Both tools respect GNS3's built-in access control
- Requires valid GNS3 server authentication
- Project-level permissions apply

### Audit Logging

All operations are logged:
```python
logger.info("Starting %d nodes in project %s...", len(node_ids), project_id)
logger.info("Stop command sent for node %s (%s)", node_id, node.name)
logger.info("Suspend command sent for node %s (%s)", node_id, node.name)
```

### Mode-Based Restrictions

- **Teaching Assistant Mode**:
  - Can start nodes
  - Cannot stop, suspend (prevents disruption of active labs)

- **Lab Automation Assistant Mode**:
  - Can start, stop, and suspend nodes (full lifecycle control)
  - Complete lab management including state preservation

## Performance Characteristics

| Operation | Typical Duration | Wait Time | Progress | State Preserved |
|-----------|-----------------|-----------|----------|-----------------|
| Start (normal) | 60-180s | ~140s base | Yes | N/A |
| Start (quick) | < 1s | 0s | No | N/A |
| Stop | < 5s | 0s | No | ❌ No |
| Suspend | < 10s | 0s | No | ✅ Yes |

**Notes:**
- Stop operations are significantly faster than start operations
- Suspend is slightly slower than stop but preserves state
- Stop/Suspend do not require progress tracking (immediate feedback)
- Start duration depends on node type (router, switch, PC, etc.)
- Suspend provides fast resume capability compared to full start

## Future Enhancements

### Planned Features

- [ ] **Resume Tool**: Explicit resume operation for suspended nodes
- [ ] **Restart Tool**: Combined stop + start operation
- [ ] **Bulk Status Check**: Query multiple nodes without stopping
- [ ] **Conditional Stop/Suspend**: Operate only if node is in specific state
- [ ] **Graceful Shutdown**: Send halt commands before stopping

### Potential Improvements

- [ ] Progress tracking for long suspend operations (rare but possible)
- [ ] Concurrent suspend operations (parallel API calls)
- [ ] Suspend node groups by name pattern
- [ ] Dependency-aware suspend (suspend in dependency order)
- [ ] Auto-suspend after idle timeout
- [ ] State snapshots (save multiple suspend states)

## Related Documentation

- [Chat API](./chat-api.md) - Session management and SSE
- [Command Security](./command-security.md) - Security framework
- [LLM Model Configs](./llm-model-configs.md) - Model configuration

---

_Implementation Date: 2026-03-11_

_Status: ✅ Implemented and Available in Lab Automation Assistant Mode_
