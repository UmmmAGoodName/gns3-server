# GNS3 AI Copilot Documentation

This directory contains design documentation, implementation guides, and future plans for the GNS3 AI Copilot feature.

## Directory Structure

```
docs/gns3-copilot/
├── README.md                    # This file
├── implemented/                 # Implemented features and designs
│   ├── chat-api.md             # Chat API design (SSE, session management)
│   ├── llm-model-configs.md    # LLM model configuration system
│   ├── command-security.md     # Command security and filtering
│   └── context-window-management.md  # Context window optimization
├── todo/                        # Planned features and designs
│   ├── jinja2-config-templates-system.md        # Config template system
│   ├── config-templates-implementation-guide.md # Template implementation
│   ├── ai-prompting-for-config-templates.md     # AI prompts for templates
│   ├── acl-web-ui-implementation-guide.md       # ACL/ACL Web UI
│   ├── hitl-implementation-plan.md              # HITL (Human-in-the-Loop)
│   ├── vision-topology-creation.md              # Vision-based topology
│   └── ...                                          # More planned features
└── guides/                      # User and developer guides (TBD)
```

## Implemented Features

### Chat API (`implemented/chat-api.md`)
The core Chat API that enables AI-powered conversations within GNS3 projects.

**Key Features:**
- Server-Sent Events (SSE) for streaming responses
- Project-level session isolation
- Session management (CRUD operations)
- Statistics tracking (messages, tokens, LLM calls)
- User-level LLM configuration

**Status:** ✅ Implemented

### LLM Model Configs (`implemented/llm-model-configs.md`)
Multi-level LLM model configuration system.

**Key Features:**
- System-wide defaults
- Group-level configurations
- User-level overrides
- Runtime parameter adjustment
- Model provider abstraction

**Status:** ✅ Implemented

### Command Security (`implemented/command-security.md`)
Security framework for AI-generated commands.

**Key Features:**
- Command filtering and validation
- Dangerous operation detection
- HITL (Human-in-the-Loop) confirmations
- Audit logging

**Status:** ✅ Implemented

### Context Window Management (`implemented/context-window-management.md`)
Optimization strategies for handling large project contexts.

**Key Features:**
- Intelligent content filtering
- Token usage optimization
- Summary generation
- Context compression

**Status:** ✅ Implemented

## Planned Features

### Jinja2 Configuration Templates (`todo/jinja2-config-templates-system.md`)
Template-based configuration generation system.

**Planned Features:**
- Vendor-specific templates (Cisco, Juniper, Huawei, etc.)
- JSON schema validation
- AI generates structured data → Templates render configs
- Multi-vendor support

**Status:** 📋 Design Complete, Implementation Pending

### ACL Web UI (`todo/acl-web-ui-implementation-guide.md`)
Web-based ACL (Access Control List) management interface.

**Status:** 📋 Design Complete

### HITL Implementation (`todo/hitl-implementation-plan.md`)
Enhanced Human-in-the-Loop confirmation workflows.

**Status:** 📋 Design Complete

### Vision Topology Creation (`todo/vision-topology-creation.md`)
Create network topologies from images/diagrams.

**Status:** 📋 Design Complete

## Contributing

When adding new documentation:

1. **Design Phase:** Add new documents to `todo/`
2. **Implementation:** Move to `implemented/` when feature is complete
3. **Naming:**
   - `todo/`: Use descriptive names like `{feature}-implementation-guide.md`
   - `implemented/`: Use concise names like `{feature}.md`

## Document Status Legend

| Status | Description |
|--------|-------------|
| ✅ Implemented | Feature is fully implemented and deployed |
| 📋 Design Complete | Design is done, awaiting implementation |
| 🚧 In Progress | Currently being implemented |
| 💡 Proposed | Initial idea or proposal |

## Related Documentation

- [GNS3 Server API Documentation](https://api.gns3.com/)
- [GNS3 Web UI Documentation](https://docs.gns3.com/)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)

## Quick Links

- **Current Feature Branch:** `feature/ai-copilot-bridge`
- **Main Branch:** `master`
- **Issue Tracker:** [GitHub Issues](https://github.com/GNS3/gns3-server/issues)

---

_Last updated: 2026-03-10_
