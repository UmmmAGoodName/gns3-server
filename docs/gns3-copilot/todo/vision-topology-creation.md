# Vision-Based Topology Creation

**Document Status**: Design Phase
**Priority**: High
**Created**: 2026-03-09
**Related Docs**:
- [AI Chat API Design](../ai-chat-api-design.md)
- [GNS3 Templates API](../../compute/templates_api.md)
- [FlowNet-Lab Vision Recognition](../../../../FlowNet-Lab/backend/api/v1/vision.py)

---

## Table of Contents

- [Overview](#overview)
- [Problem Description](#problem-description)
- [Requirements Analysis](#requirements-analysis)
- [Solution Design](#solution-design)
- [Implementation Steps](#implementation-steps)
- [Code Changes Checklist](#code-changes-checklist)
- [Testing Plan](#testing-plan)
- [Risk Assessment](#risk-assessment)

---

## Overview

This feature enables users to create GNS3 topologies by uploading network topology images. The system uses vision language models (VLM) to analyze the image and generate structured topology data, then uses LLM to map the recognized devices to GNS3 templates and create the topology automatically.

### Workflow

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 1. User uploads topology image (base64 or file)                         │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 2. Vision Model Analysis (Qwen-VL / GPT-4V / Claude 3.5 Sonnet)        │
│    - Analyze image structure                                            │
│    - Identify devices (routers, switches, hosts, etc.)                  │
│    - Identify connections between devices                               │
│    - Extract interface and IP information (if visible)                  │
│    - Return structured JSON topology                                    │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 3. LLM Processing & Template Mapping                                    │
│    - Get available GNS3 device templates from project                   │
│    - Map recognized device types to appropriate GNS3 templates          │
│    - Handle user preferences (specific device models, etc.)             │
│    - Generate deployment plan                                           │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 4. Topology Creation via Agent Tools                                    │
│    - Create nodes using mapped templates                                │
│    - Create links between nodes                                         │
│    - Configure interfaces (if IP info available)                        │
│    - Optional: Auto-start nodes                                         │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 5. Return Result                                                        │
│    - Created topology information                                       │
│    - Node list with template mappings                                   │
│    - Link list                                                          │
│    - Configuration summary                                              │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Problem Description

### Current Limitations

1. **Manual Topology Creation**: Users must manually create nodes and links in GNS3 UI
2. **Time-Consuming**: Creating complex topologies with many devices is tedious
3. **Error-Prone**: Manual configuration can lead to mistakes (wrong connections, missing interfaces)
4. **No Visual Import**: Existing topology diagrams cannot be automatically imported

### User Scenarios

**Scenario 1: Lab Replication**
```
User has a network topology diagram from:
- Textbook or course material
- Network documentation
- Exam scenario
- Online reference

User wants to quickly recreate this topology in GNS3 for practice
```

**Scenario 2: Migration from Other Tools**
```
User has topology designs from:
- Packet Tracer
- VIRL
- Network visualization tools
- Drawn diagrams (Visio, draw.io)

User wants to import into GNS3
```

**Scenario 3: Rapid Prototyping**
```
Network architect designs topology in visual tool
Wants to quickly test in GNS3 without manual recreation
```

---

## Requirements Analysis

### Functional Requirements

1. **Image Input Support**
   - Accept base64 encoded image data
   - Support common image formats (PNG, JPG, JPEG, GIF, BMP, WebP)
   - Maximum image size: 10MB (configurable)

2. **Vision Model Support**
   - Support multiple vision language models:
     - Qwen-VL (qwen-vl-max, qwen3-vl-plus, qwen3-vl-flash)
     - OpenAI GPT-4V / GPT-4o
     - Anthropic Claude 3.5 Sonnet (vision capable)
   - User can select which model to use
   - Graceful fallback if model unavailable

3. **Topology Recognition Output**
   Structured JSON format:
   ```json
   {
     "topology_name": "Topology name",
     "description": "Brief description",
     "devices": [
       {
         "id": "unique_id",
         "name": "device_name",
         "type": "router|switch|host|server|cloud|firewall",
         "model": "device_model_if_visible",
         "position": {"x": 0, "y": 0}
       }
     ],
     "links": [
       {
         "id": "unique_id",
         "source_device": "device_name",
         "source_interface": "interface_name",
         "target_device": "device_name",
         "target_interface": "interface_name",
         "link_type": "ethernet|serial"
       }
     ],
     "interfaces": [
       {
         "device": "device_name",
         "interface": "interface_name",
         "ip_address": "ip_address",
         "subnet_mask": "subnet_mask"
       }
     ],
     "summary": {
       "total_devices": 0,
       "total_links": 0,
       "device_types": {"router": 0, "switch": 0, "host": 0, "other": 0}
     }
   }
   ```

4. **Template Mapping**
   - Automatically map recognized device types to GNS3 templates
   - User can override template mappings
   - Support user-specified device model preferences
   - Handle cases where suitable template not found

5. **Topology Creation**
   - Create nodes using mapped templates
   - Create links between nodes
   - Preserve relative device positions (if available)
   - Optional: Auto-start nodes after creation

6. **User Preferences**
   - Specify preferred device models per device type
   - Choose whether to auto-start nodes
   - Configure default link types

### Non-Functional Requirements

1. **Performance**
   - Vision analysis should complete within 30 seconds
   - Topology creation should complete within 60 seconds (for ~20 devices)

2. **Reliability**
   - Handle vision model errors gracefully
   - Validate recognized topology before creation
   - Provide clear error messages

3. **Security**
   - Validate image size and format
   - Sanitize file names
   - Rate limiting to prevent abuse

4. **Extensibility**
   - Easy to add new vision models
   - Support custom device type mappings
   - Pluggable template selection strategy

---

## Solution Design

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         API Layer                                       │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ POST /v3/projects/{project_id}/chat/vision-topology               │ │
│  │  - Accepts image (base64 or file reference)                       │ │
│  │  - Accepts optional preferences (device models, auto-start, etc.)  │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Vision Model Layer                                   │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ VisionModelFactory                                                │ │
│  │  - Creates appropriate vision model based on config               │ │
│  │  - Supports: Qwen-VL, OpenAI, Anthropic                           │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ BaseVisionModel (abstract)                                        │ │
│  │  - recognize_topology(image_base64, prompt) -> dict               │ │
│  │                                                                     │ │
│  │ QwenVisionModel                                                    │ │
│  │ OpenAIVisionModel                                                  │ │
│  │ AnthropicVisionModel                                               │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Agent Layer                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ Vision Topology Agent (LangGraph)                                  │ │
│  │  - Analyzes recognized topology                                    │ │
│  │  - Gets available GNS3 templates                                   │ │
│  │  - Maps device types to templates                                  │ │
│  │  - Generates creation plan                                         │ │
│  │  - Executes creation via tools                                     │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ Tools:                                                             │ │
│  │  - get_gns3_templates (existing)                                  │ │
│  │  - create_node (existing)                                         │ │
│  │  - create_link (existing)                                         │ │
│  │  - start_node (existing)                                          │ │
│  │  - map_device_to_template (new)                                   │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    GNS3 Controller API                                  │
│  - Creates nodes in project                                           │
│  - Creates links between nodes                                        │
│  - Configures interfaces                                              │
└─────────────────────────────────────────────────────────────────────────┘
```

### API Design

#### New Endpoint

**POST** `/v3/projects/{project_id}/vision-topology`

**Request Body:**
```json
{
  "image_base64": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA...",
  "custom_prompt": "Optional custom prompt for vision model",
  "preferences": {
    "vision_model": "qwen-vl-max",
    "device_models": {
      "router": "c3740",
      "switch": "vEOS",
      "host": "vpcs",
      "server": "docker-alpine"
    },
    "auto_start": false,
    "default_link_type": "ethernet"
  }
}
```

**Response:**
```json
{
  "recognized_topology": {
    "topology_name": "OSPF Three Router Topology",
    "description": "Three routers connected in triangle",
    "devices": [...],
    "links": [...],
    "interfaces": [...],
    "summary": {...}
  },
  "template_mappings": {
    "R1": {"template_id": "c3740", "template_name": "Cisco 3740"},
    "R2": {"template_id": "c3740", "template_name": "Cisco 3740"},
    "R3": {"template_id": "c3740", "template_name": "Cisco 3740"}
  },
  "created_nodes": [
    {"node_id": "...", "name": "R1", "template_id": "...", "position": {"x": 100, "y": 100}},
    ...
  ],
  "created_links": [
    {"link_id": "...", "source_node": "...", "target_node": "..."},
    ...
  ],
  "configuration_summary": {
    "total_nodes_created": 3,
    "total_links_created": 3,
    "nodes_started": 0
  }
}
```

#### Alternative: Integrate with Chat API

**POST** `/v3/projects/{project_id}/chat/vision`

Same endpoint as `/stream`, but accepts `image_base64` field:

```json
{
  "message": "Create this topology in GNS3",
  "image_base64": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA...",
  "session_id": "optional-session-id",
  "preferences": {
    "device_models": {...}
  }
}
```

Returns SSE stream with:
- `vision_start`: Vision analysis started
- `vision_progress`: Analysis progress updates
- `vision_result`: Recognized topology data
- `creation_start`: Topology creation started
- `node_created`: Individual node creation events
- `link_created`: Individual link creation events
- `done`: Creation complete

### Component Design

#### 1. Vision Model Layer

**File**: `gns3server/agent/gns3_copilot/vision/models.py`

```python
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class BaseVisionModel(ABC):
    """Abstract base class for vision models."""

    def __init__(self, api_key: str, model_name: str):
        self.api_key = api_key
        self.model_name = model_name

    @abstractmethod
    async def recognize_topology(
        self,
        image_base64: str,
        prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Recognize network topology from image.

        Args:
            image_base64: Base64 encoded image or data URL
            prompt: Optional custom prompt

        Returns:
            Dictionary with topology data (devices, links, interfaces, summary)

        Raises:
            RuntimeError: If recognition fails
        """
        pass


class QwenVisionModel(BaseVisionModel):
    """Qwen-VL vision model implementation."""

    async def recognize_topology(
        self,
        image_base64: str,
        prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        # Implementation using DashScope SDK
        # (migrated from FlowNet-Lab)
        pass


class OpenAIVisionModel(BaseVisionModel):
    """OpenAI GPT-4V / GPT-4o vision model implementation."""

    async def recognize_topology(
        self,
        image_base64: str,
        prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        # Implementation using OpenAI SDK
        pass


class AnthropicVisionModel(BaseVisionModel):
    """Anthropic Claude 3.5 Sonnet vision model implementation."""

    async def recognize_topology(
        self,
        image_base64: str,
        prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        # Implementation using Anthropic SDK
        pass


class VisionModelFactory:
    """Factory for creating vision models."""

    @staticmethod
    def create_model(
        provider: str,
        api_key: str,
        model_name: Optional[str] = None
    ) -> BaseVisionModel:
        """
        Create a vision model instance.

        Args:
            provider: Model provider (qwen, openai, anthropic)
            api_key: API key for the provider
            model_name: Specific model name (optional, uses default if None)

        Returns:
            BaseVisionModel instance

        Raises:
            ValueError: If provider is not supported
        """
        models = {
            "qwen": (QwenVisionModel, model_name or "qwen3-vl-plus"),
            "openai": (OpenAIVisionModel, model_name or "gpt-4o"),
            "anthropic": (AnthropicVisionModel, model_name or "claude-3-5-sonnet-20241022"),
        }

        if provider not in models:
            raise ValueError(f"Unsupported vision model provider: {provider}")

        model_class, default_model = models[provider]
        return model_class(api_key, model_name or default_model)
```

#### 2. Vision Topology Agent

**File**: `gns3server/agent/gns3_copilot/agent/vision_topology_agent.py`

```python
from langgraph.graph import StateGraph, END
from typing import Dict, Any, List

class VisionTopologyAgent:
    """Agent for creating GNS3 topologies from vision recognition results."""

    def __init__(self, project_id: str, compute_service):
        self.project_id = project_id
        self.compute_service = compute_service

    async def create_topology_from_vision(
        self,
        recognized_topology: Dict[str, Any],
        preferences: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create GNS3 topology from recognized vision data.

        Args:
            recognized_topology: Topology data from vision model
            preferences: User preferences (device models, auto-start, etc.)

        Returns:
            Creation result with nodes, links, and summary
        """
        # Step 1: Get available templates
        templates = await self._get_available_templates()

        # Step 2: Map devices to templates
        device_mappings = await self._map_devices_to_templates(
            recognized_topology["devices"],
            templates,
            preferences.get("device_models", {})
        )

        # Step 3: Create nodes
        created_nodes = []
        for device in recognized_topology["devices"]:
            mapping = device_mappings[device["name"]]
            node = await self._create_node(device, mapping)
            created_nodes.append(node)

        # Step 4: Create links
        created_links = []
        for link in recognized_topology["links"]:
            link_result = await self._create_link(link, created_nodes)
            created_links.append(link_result)

        # Step 5: Optionally start nodes
        if preferences.get("auto_start", False):
            await self._start_nodes(created_nodes)

        return {
            "recognized_topology": recognized_topology,
            "template_mappings": device_mappings,
            "created_nodes": created_nodes,
            "created_links": created_links,
            "configuration_summary": {
                "total_nodes_created": len(created_nodes),
                "total_links_created": len(created_links),
                "nodes_started": len(created_nodes) if preferences.get("auto_start") else 0
            }
        }

    async def _get_available_templates(self) -> Dict[str, Any]:
        """Get available GNS3 templates for the project."""
        # Use existing GNS3 API
        pass

    async def _map_devices_to_templates(
        self,
        devices: List[Dict[str, Any]],
        templates: Dict[str, Any],
        user_preferences: Dict[str, str]
    ) -> Dict[str, Dict[str, str]]:
        """
        Map recognized devices to GNS3 templates.

        Args:
            devices: List of recognized devices
            templates: Available GNS3 templates
            user_preferences: User's preferred device models

        Returns:
            Mapping of device names to template IDs
        """
        # Use LLM to intelligently map device types to templates
        # Consider user preferences, available templates, device types
        pass

    async def _create_node(
        self,
        device: Dict[str, Any],
        template_mapping: Dict[str, str]
    ) -> Dict[str, Any]:
        """Create a GNS3 node from device and template mapping."""
        # Use existing GNS3 create node API
        pass

    async def _create_link(
        self,
        link: Dict[str, Any],
        nodes: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Create a GNS3 link between nodes."""
        # Use existing GNS3 create link API
        pass

    async def _start_nodes(self, nodes: List[Dict[str, Any]]):
        """Start all nodes."""
        # Use existing GNS3 start node API
        pass
```

#### 3. API Endpoint

**File**: `gns3server/api/routes/controller/vision.py`

```python
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

router = APIRouter(tags=["vision"])

class VisionTopologyRequest(BaseModel):
    """Request model for vision-based topology creation."""
    image_base64: str
    custom_prompt: Optional[str] = None
    preferences: Optional[Dict[str, Any]] = None


@router.post("/vision-topology")
async def create_topology_from_vision(
    project_id: str,
    request: VisionTopologyRequest,
    current_user = Depends(get_current_active_user)
):
    """
    Create GNS3 topology from network topology image.

    Accepts a base64 encoded image and automatically creates
    the topology using vision recognition and Agent tools.
    """
    try:
        # Step 1: Initialize vision model
        vision_model = VisionModelFactory.create_model(
            provider=request.preferences.get("vision_model", "qwen"),
            api_key=await _get_vision_api_key(current_user, request.preferences),
            model_name=request.preferences.get("model_name")
        )

        # Step 2: Recognize topology
        recognized_topology = await vision_model.recognize_topology(
            image_base64=request.image_base64,
            prompt=request.custom_prompt
        )

        # Step 3: Create topology via agent
        agent = VisionTopologyAgent(project_id, compute_service)
        result = await agent.create_topology_from_vision(
            recognized_topology=recognized_topology,
            preferences=request.preferences or {}
        )

        return result

    except Exception as e:
        logger.error(f"Failed to create topology from vision: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

### Template Mapping Strategy

#### Default Device Type Mappings

| Recognized Type | Default GNS3 Template | Alternative Templates |
|-----------------|----------------------|----------------------|
| router          | c3740 (Cisco 3740)   | c7200, vIOS-L2       |
| switch          | vEOS (VeOS)          | vIOS-L2, OVS        |
| host / PC       | vpcs                 | docker-alpine       |
| server          | docker-alpine        | docker-ubuntu       |
| firewall        | asav                 | none                |
| cloud           | cloud                | none                |

#### LLM-Based Template Selection

For more intelligent mapping:

```
Prompt to LLM:
"""
Given the following information:

1. Recognized device: {name}, type: {type}, model: {model_if_visible}
2. Available GNS3 templates: {list_of_available_templates}
3. User preferences: {user_preferred_models}

Select the most appropriate template and explain reasoning.

Return JSON:
{
  "template_id": "...",
  "template_name": "...",
  "reasoning": "Why this template was selected"
}
"""
```

### Detailed Deployment Workflow (Based on FlowNet-Lab)

#### Step-by-Step Process

```
1. Analyze Vision Result
   ├─ Extract topology name
   ├─ Identify all devices (names, types, models)
   ├─ Identify all connections
   └─ Note any special requirements

2. Check Existing Projects
   └─ Call list_gns3_projects to avoid duplicates

3. Get Available Templates
   └─ Call get_gns3_templates to see what's available
       └─ Returns: [{"name": "...", "template_id": "...", "template_type": "..."}, ...]

4. Map Devices to Templates
   ├─ Use user preferences if specified
   ├─ Use default mappings for recognized types
   └─ Fallback to LLM-assisted selection

5. Create All Nodes (Single Batch Call)
   ├─ Use create_gns3_node with all nodes at once
   ├─ Position nodes in grid layout (min 250px apart)
   └─ Example positions:
       (-400, -200)  (-100, -200)  (200, -200)
       (-400, 0)      (-100, 0)     (200, 0)
       (-400, 200)    (-100, 200)   (200, 200)

6. Read Topology for Port Names
   ├─ Call gns3_topology_reader with project_id
   ├─ Extract actual port names from created nodes
   └─ CRITICAL: Port names vary by template
       └─ Cisco: Ethernet0/0, GigabitEthernet0/0
       └─ VPCS: Ethernet0
       └─ Docker: eth0, eth1

7. Update Node Names
   └─ Call update_gns3_node_name to assign meaningful names (R1, R2, SW1, PC1)

8. Create Links Using Actual Port Names
   ├─ Call create_gns3_link for each connection
   ├─ Use port names from topology reader (Step 6)
   └─ NEVER guess port names - always use topology data

9. Optionally Start Nodes
   └─ Call start_gns3_node_quick to send start commands
```

#### Critical Deployment Rules

1. **Always get templates first** before creating nodes
2. **Create all nodes in one call** for efficiency
3. **Get topology before creating links** to obtain actual port names
4. **Position nodes properly** - minimum 250 pixels apart
5. **Use actual port names from topology** when creating links:
   - Port names vary by template type
   - Examples: Ethernet0/0, GigabitEthernet0/0, eth0
   - Never guess - always use topology data
6. **Match device types to templates correctly**

#### Node Positioning Strategy

Grid layout pattern from FlowNet-Lab:

```python
def calculate_node_positions(device_count):
    """Calculate grid positions for nodes with minimum 250px spacing."""
    positions = []
    cols = min(4, device_count)  # Max 4 columns
    x_offset = 300  # 250px spacing + margin
    y_offset = 200  # Vertical spacing

    start_x = -(cols - 1) * x_offset // 2
    start_y = -((device_count + cols - 1) // cols - 1) * y_offset // 2

    for i, device in enumerate(devices):
        row = i // cols
        col = i % cols
        x = start_x + col * x_offset
        y = start_y + row * y_offset
        positions.append({"x": x, "y": y})

    return positions
```

---

## Implementation Steps

| Phase | Step | Task | File(s) | Difficulty | Priority |
|-------|------|------|---------|------------|----------|
| 1 | 1.1 | Create base vision model classes | `agent/gns3_copilot/vision/models.py` | ⭐⭐ Medium | P0 |
| 1 | 1.2 | Implement QwenVisionModel | `agent/gns3_copilot/vision/models.py` | ⭐⭐ Medium | P0 |
| 1 | 1.3 | Implement OpenAIVisionModel | `agent/gns3_copilot/vision/models.py` | ⭐⭐ Medium | P1 |
| 1 | 1.4 | Implement AnthropicVisionModel | `agent/gns3_copilot/vision/models.py` | ⭐⭐ Medium | P1 |
| 2 | 2.1 | Create VisionTopologyAgent | `agent/gns3_copilot/agent/vision_topology_agent.py` | ⭐⭐⭐ High | P0 |
| 2 | 2.2 | Implement template mapping logic | `agent/gns3_copilot/agent/vision_topology_agent.py` | ⭐⭐⭐ High | P0 |
| 2 | 2.3 | Implement node/link creation | `agent/gns3_copilot/agent/vision_topology_agent.py` | ⭐⭐ Medium | P0 |
| 3 | 3.1 | Create API endpoint | `api/routes/controller/vision.py` | ⭐⭐ Medium | P0 |
| 3 | 3.2 | Add request/response schemas | `schemas/controller/vision.py` | ⭐ Low | P0 |
| 3 | 3.3 | Integrate with existing auth | `api/routes/controller/vision.py` | ⭐ Low | P0 |
| 4 | 4.1 | Add vision API key to LLM config | `db/models/llm_model_configs.py` | ⭐⭐ Medium | P1 |
| 4 | 4.2 | Update user config UI | (Frontend) | ⭐⭐⭐ High | P2 |
| 5 | 5.1 | Add unit tests | `tests/test_vision_models.py` | ⭐⭐ Medium | P1 |
| 5 | 5.2 | Add integration tests | `tests/test_vision_topology.py` | ⭐⭐⭐ High | P2 |
| 6 | 6.1 | Update API documentation | `docs/gns3-copilot/` | ⭐ Low | P1 |

---

## Code Migration from FlowNet-Lab

### Files to Migrate

| FlowNet-Lab File | gns3-server Destination | Modifications Needed |
|------------------|------------------------|---------------------|
| `src/gns3_copilot/agent/qwen_vision_model.py` | `agent/gns3_copilot/vision/models.py` | Refactor into class, add async support |
| `backend/api/v1/vision.py` | `api/routes/controller/vision.py` | Adapt to GNS3 architecture, add Agent integration |
| `src/gns3_copilot/agent/model_factory.py` | `agent/gns3_copilot/vision/__init__.py` | Update factory pattern |

### Key Modifications

1. **Remove Dependencies**
   - FlowNet-Lab specific config loading
   - Custom logging setup (use gns3server logger)

2. **Add Dependencies**
   - GNS3 Controller API client
   - GNS3 database models
   - Existing Agent tools

3. **Update Configuration**
   - Use gns3server's config system
   - Store vision API keys in user LLM config

4. **Add Error Handling**
   - GNS3-specific error codes
   - Integration with GNS3 project status checks

---

## Testing Plan

### Unit Tests

#### 1. Vision Model Tests

- **Test 1.1**: Qwen-VL model initialization
  - Valid API key → success
  - Invalid API key → error
  - Missing API key → error

- **Test 1.2**: Topology recognition
  - Valid topology image → structured JSON
  - Invalid image → graceful error
  - Malformed JSON response → error handling

#### 2. Template Mapping Tests

- **Test 2.1**: Default template mapping
  - Router → c3740
  - Switch → vEOS
  - Host → vpcs

- **Test 2.2**: User preference override
  - User prefers different router model → use preference

- **Test 2.3**: Unknown device type
  - Unknown type → default or error

#### 3. Agent Tests

- **Test 3.1**: Node creation
  - Single device → single node created
  - Multiple devices → multiple nodes created

- **Test 3.2**: Link creation
  - Valid link → link created between nodes

- **Test 3.3**: Full topology
  - 3 routers, 3 links → complete topology created

### Integration Tests

#### 1. End-to-End Tests

- **Test 1.1**: Simple topology
  - 2 routers, 1 link → verify creation

- **Test 1.2**: Complex topology
  - 5+ devices, multiple links → verify creation

- **Test 1.3**: With IP configuration
  - Topology with visible IPs → verify interface config

#### 2. Error Handling Tests

- **Test 2.1**: Invalid image
  - Corrupted base64 → 400 error

- **Test 2.2**: Project not opened
  - Closed project → 403 error

- **Test 2.3**: Vision model failure
  - API error → graceful degradation

### Performance Tests

- **Test 1**: Vision analysis time
  - Should complete within 30 seconds

- **Test 2**: Topology creation time
  - 20 devices should create within 60 seconds

---

## Risk Assessment

### Technical Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Vision model API rate limits | High | Medium | Implement rate limiting, queue system |
| Poor recognition accuracy | High | Medium | Support multiple vision models, user verification step |
| Template mapping failures | Medium | Medium | LLM-assisted mapping, user override options |
| Large image handling | Medium | Low | Size limits, image optimization |
| Vision API key management | High | Low | Encrypt storage, per-user keys |

### Business Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| User expectation mismatch | High | Medium | Clear documentation, example images |
| Cost of vision APIs | Medium | Medium | Usage tracking, cost warnings |
| Complex topology failures | Medium | High | Incremental creation, rollback support |

---

## Future Enhancements

### Phase 2 Features

1. **Multi-Image Support**
   - Stitch multiple images together
   - Handle multi-page diagrams

2. **Handwriting Recognition**
   - Read handwritten labels and notes
   - Extract configuration commands

3. **Optical Character Recognition (OCR)**
   - Extract IP addresses, subnet masks
   - Read configuration snippets

4. **Interactive Verification**
   - Show recognized topology for user confirmation
   - Allow manual corrections before creation

5. **Template Suggestions**
   - Suggest alternative templates
   - Show compatibility warnings

6. **Configuration Generation**
   - Generate basic device configurations
   - Apply common network protocols

### Phase 3 Features

1. **Topology Comparison**
   - Compare created topology with original image
   - Highlight differences

2. **Auto-Configuration**
   - Configure routing protocols based on topology
   - Set up IP addressing schemes

3. **Learning from User Corrections**
   - Learn from user template preference changes
   - Improve mapping suggestions over time

---

## References

- [FlowNet-Lab Vision Recognition](../../../../FlowNet-Lab/backend/api/v1/vision.py)
- [Qwen-VL Documentation](https://help.aliyun.com/zh/dashscope/developer-reference/vl-plus-api)
- [OpenAI Vision API](https://platform.openai.com/docs/guides/vision)
- [Anthropic Claude Vision](https://docs.anthropic.com/claude/docs/vision)
- [GNS3 Templates API](../../compute/templates_api.md)

---

**Document Version**: 1.0
**Last Updated**: 2026-03-09
**Target Version**: TBD

---

## License

**Copyright © 2025 Yue Guobin (岳国宾)**

This work is licensed under the [Creative Commons Attribution-ShareAlike 4.0
International License (CC BY-SA 4.0)](https://creativecommons.org/licenses/by-sa/4.0/).

![CC BY-SA 4.0](https://i.creativecommons.org/l/by-sa/4.0/88x31.png)

### Summary

You are free to:

- **Share** — Copy and redistribute the material in any medium or format
- **Adapt** — Remix, transform, and build upon the material for any purpose

Under the following terms:

- **Attribution** — You must give appropriate credit to **Yue Guobin (岳国宾)**, provide
  a link to the license, and indicate if changes were made.
- **ShareAlike** — If you remix, transform, or build upon the material, you must
  distribute your contributions under the **same license** (CC BY-SA 4.0).

Full license text: [DESIGN_DOCS_LICENSE](../DESIGN_DOCS_LICENSE.md)
