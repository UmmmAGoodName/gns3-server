# Runtime LLM Config Override

**Document Status**: Design Phase
**Priority**: Medium
**Created**: 2026-03-09
**Related Docs**:
- [AI Chat API Design](../ai-chat-api-design.md)
- [LLM Model Configs API](../llm-model-configs-api.md)
- [User-Selectable Group Default Config](./user-selectable-group-default-config.md)

---

## Table of Contents

- [Problem Description](#problem-description)
- [Requirements Analysis](#requirements-analysis)
- [Solution Design](#solution-design)
- [Implementation Steps](#implementation-steps)
- [Code Changes Checklist](#code-changes-checklist)
- [Testing Plan](#testing-plan)
- [Risk Assessment](#risk-assessment)

---

## Problem Description

### Current Behavior

Currently, the Chat API always uses the user's default LLM configuration from the database. Users cannot:
1. Select a different saved configuration for a specific request
2. Temporarily override certain parameters (e.g., use a different model, adjust temperature) for a single request

### User Scenarios

**Scenario 1: Quick Model Testing**
```
User has multiple configs:
- "GPT-4o" (default)
- "Claude 3.5 Sonnet"
- "Gemini Pro"

User wants to test the same prompt on Claude 3.5 without changing default
```

**Scenario 2: Temporary Parameter Adjustment**
```
User's default config:
- model: "gpt-4o"
- temperature: 0.7

User wants to try a more creative response (temperature=1.2) for this request only
```

**Scenario 3: Cost Optimization**
```
User's default config:
- model: "gpt-4o" (expensive)

User wants to use "gpt-4o-mini" for this simple request
```

### Current Limitation

**File**: `gns3server/api/routes/controller/chat.py:122`

```python
# Always gets user's default config
llm_config = await get_user_llm_config_full(str(user_id), app)
```

No way to specify alternative config or override parameters at request time.

---

## Requirements Analysis

### Functional Requirements

1. **Select Saved Configuration**
   - User can specify `llm_config_id` to use a different saved config
   - Must be a config owned by the user or inherited from their group
   - Validation: If config_id is invalid or inaccessible, return error

2. **Override LLM Parameters**
   - Support temporary override of common LLM parameters:
     - `model`: Model name (e.g., "gpt-4o", "claude-3-5-sonnet-20241022")
     - `temperature`: Sampling temperature (0.0-2.0)
     - `max_tokens`: Maximum tokens to generate
     - `top_p`: Nucleus sampling parameter
     - (Additional provider-specific parameters as needed)
   - Overrides apply only to the current request
   - Original config in database is NOT modified

3. **Parameter Precedence**
   ```
   Request Overrides > Database Config > Provider Defaults
   ```

4. **Backward Compatibility**
   - All new parameters are optional
   - Existing requests without new parameters work unchanged

### Non-Functional Requirements

1. **Security**
   - API key from selected config remains secure
   - Users can only select their accessible configs
   - Overrides are logged for audit

2. **Performance**
   - Minimal overhead for config retrieval and validation
   - No database write for temporary overrides

3. **Maintainability**
   - Clear code structure for override logic
   - Easy to add new overridable parameters in the future

---

## Solution Design

### API Schema Changes

**File**: `gns3server/schemas/controller/chat.py`

```python
class LLMConfigOverride(BaseModel):
    """Temporary LLM configuration overrides for a single request."""

    model: Optional[str] = Field(
        None,
        description="Override the model name (e.g., 'gpt-4o', 'claude-3-5-sonnet-20241022'). "
                    "Provider and API key still come from the selected or default config."
    )
    temperature: Optional[float] = Field(
        None,
        ge=0.0,
        le=2.0,
        description="Override sampling temperature (0.0-2.0). "
                    "Lower values make output more deterministic, higher values more random."
    )
    max_tokens: Optional[int] = Field(
        None,
        ge=1,
        description="Override maximum tokens to generate in the response."
    )
    top_p: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Override nucleus sampling parameter (0.0-1.0)."
    )


class ChatRequest(BaseModel):
    """Chat request model."""

    message: str = Field(..., description="User message content")
    session_id: Optional[str] = Field(None, description="Session ID (auto-generated if not provided)")
    stream: bool = Field(default=True, description="Enable streaming response")

    # NEW: LLM Configuration Selection
    llm_config_id: Optional[str] = Field(
        None,
        description="LLM configuration ID to use for this request. "
                    "Must be a config owned by the user or inherited from their group. "
                    "If not provided, uses the user's default LLM config."
    )

    # NEW: Runtime Parameter Overrides
    llm_config_override: Optional[LLMConfigOverride] = Field(
        None,
        description="Temporary overrides for LLM parameters. "
                    "These overrides apply only to this request and do not modify the stored config. "
                    "Overrides take precedence over the selected/default config values."
    )

    mode: Literal["text"] = Field(default="text", description="Interaction mode")
```

### Configuration Resolution Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 1. API Layer (chat.py)                                                  │
│    POST /v3/projects/{project_id}/chat/stream                          │
│    ChatRequest {                                                        │
│      message,                                                           │
│      llm_config_id?,                    # Select config                  │
│      llm_config_override?: {            # Override params               │
│        model?, temperature?, max_tokens?, top_p?                        │
│      }                                                                  │
│    }                                                                    │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 2. Config Resolution (get_llm_config_for_request)                       │
│                                                                         │
│    if llm_config_id provided:                                          │
│      → Get specific config by ID                                       │
│      → Validate: user must have access (own or inherited group)        │
│      → If invalid: return 403 Forbidden                                 │
│    else:                                                                │
│      → Get user's default config (current behavior)                    │
│                                                                         │
│    Decrypt API key from resolved config                                │
│    Apply llm_config_override (if provided)                              │
│      → Override fields: model, temperature, max_tokens, top_p           │
│                                                                         │
│    Result: {                                                            │
│      provider, api_key, model*, temperature*, max_tokens*, top_p*, ...  │
│    }                                                                    │
│      (* = overridden if provided)                                       │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 3. Agent Execution (agent_service.py)                                   │
│    Set ContextVars with resolved and overridden config                  │
│    Proceed with normal Agent flow                                       │
└─────────────────────────────────────────────────────────────────────────┘
```

### Implementation Details

#### File: `gns3server/db/tasks.py`

Add new function `get_llm_config_for_request`:

```python
async def get_llm_config_for_request(
    user_id: str,
    app: FastAPI,
    config_id: Optional[str] = None,
    overrides: Optional[dict] = None
) -> Optional[dict]:
    """
    Get LLM configuration for a specific request with optional overrides.

    Args:
        user_id: User UUID
        app: FastAPI application instance
        config_id: Optional specific config ID to use
        overrides: Optional dict of parameter overrides (model, temperature, etc.)

    Returns:
        Dictionary with LLM configuration (with overrides applied) or None if not found.

    Raises:
        ValueError: If config_id is specified but not accessible to user
    """
    from uuid import UUID
    from gns3server.db.repositories.llm_model_configs import LLMModelConfigsRepository
    from gns3server.utils.encryption import decrypt, is_encrypted

    try:
        user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id

        async with AsyncSession(app.state._db_engine, expire_on_commit=False) as session:
            repo = LLMModelConfigsRepository(session)

            # Step 1: Resolve base config
            if config_id:
                # User specified a config - validate access
                config_uuid = UUID(config_id) if isinstance(config_id, str) else config_id

                # Get all accessible configs for user
                effective = await repo.get_user_effective_configs(
                    user_uuid,
                    current_user_id=user_uuid,
                    current_user_is_superadmin=False
                )

                accessible_config_ids = {c["config_id"] for c in effective["configs"]}

                if config_uuid not in accessible_config_ids:
                    log.warning(
                        f"User {user_id} attempted to use inaccessible config {config_id}"
                    )
                    raise ValueError(f"Config {config_id} is not accessible to user")

                # Get the config (bypass API key hiding since this is system-level)
                config_record = await repo.get_user_config(config_uuid)
                if not config_record:
                    log.error(f"Config {config_id} not found in database")
                    return None

                source = "user_selected"

            else:
                # Use user's default config
                result = await repo.get_user_effective_configs(
                    user_uuid,
                    current_user_id=user_uuid,
                    current_user_is_superadmin=False
                )

                if not result or not result.get("default_config"):
                    log.warning(f"No default LLM configuration found for user {user_id}")
                    return None

                default_config = result["default_config"]
                config_id_str = default_config["config_id"]
                config_record = await repo.get_user_config(UUID(config_id_str))

                if not config_record:
                    log.error(f"Default config {config_id_str} not found in database")
                    return None

                source = "default"

            # Step 2: Decrypt API key
            config_data = config_record.config.copy()
            inherited_from_config_id = config_record.inherited_from_config_id

            # Handle shadow configs - get API key from parent
            if inherited_from_config_id:
                parent_config = await repo.get_group_config(inherited_from_config_id)
                if parent_config and "api_key" in parent_config.config:
                    try:
                        encrypted_key = parent_config.config["api_key"]
                        if encrypted_key and is_encrypted(encrypted_key):
                            config_data["api_key"] = decrypt(encrypted_key)
                        else:
                            config_data["api_key"] = encrypted_key
                    except Exception as e:
                        log.error(f"Failed to decrypt inherited API key: {e}")
                        return None
            else:
                # Regular config - decrypt directly
                if "api_key" in config_data and config_data["api_key"]:
                    try:
                        if is_encrypted(config_data["api_key"]):
                            config_data["api_key"] = decrypt(config_data["api_key"])
                    except Exception as e:
                        log.error(f"Failed to decrypt API key: {e}")
                        return None

            # Step 3: Apply overrides
            if overrides:
                if overrides.get("model"):
                    config_data["model"] = overrides["model"]
                    log.info(f"Model override applied: {overrides['model']}")
                if overrides.get("temperature") is not None:
                    config_data["temperature"] = overrides["temperature"]
                    log.info(f"Temperature override applied: {overrides['temperature']}")
                if overrides.get("max_tokens") is not None:
                    config_data["max_tokens"] = overrides["max_tokens"]
                    log.info(f"Max tokens override applied: {overrides['max_tokens']}")
                if overrides.get("top_p") is not None:
                    config_data["top_p"] = overrides["top_p"]
                    log.info(f"Top-p override applied: {overrides['top_p']}")

            # Step 4: Build final config dict
            llm_config = {
                "config_id": str(config_record.config_id),
                "name": config_record.name,
                "model_type": str(config_record.model_type),
                "source": source,
                "user_id": str(config_record.user_id) if config_record.user_id else None,
                "group_id": str(config_record.group_id) if config_record.group_id else None,
                "inherited_from": str(inherited_from_config_id) if inherited_from_config_id else None,
                **config_data
            }

            # Validate required fields
            if not llm_config.get("provider"):
                log.error(f"LLM config missing 'provider' field: {config_record.config_id}")
                return None

            if not llm_config.get("model"):
                log.error(f"LLM config missing 'model' field: {config_record.config_id}")
                return None

            if not llm_config.get("api_key"):
                log.error(f"LLM config missing 'api_key' field: {config_record.config_id}")
                return None

            log.info(
                f"Retrieved LLM config for user {user_id}: "
                f"provider={llm_config.get('provider')}, model={llm_config.get('model')}, "
                f"source={source}, overrides_applied={bool(overrides)}"
            )

            return llm_config

    except ValueError:
        raise  # Re-raise validation errors
    except Exception as e:
        log.error(f"Failed to retrieve LLM config for user {user_id}: {e}", exc_info=True)
        return None
```

#### File: `gns3server/api/routes/controller/chat.py`

Modify the stream endpoint to use new function:

```python
@router.post("/stream", response_model=SkipValidation[ChatResponse])
async def stream_chat(
    project_id: str,
    request: ChatRequest,
    current_user: schemas.User = Depends(get_current_active_user),
):
    """Stream chat responses from the GNS3 Copilot Agent."""

    # ... existing project validation code ...

    # NEW: Resolve LLM config with overrides
    overrides = None
    if request.llm_config_override:
        overrides = request.llm_config_override.model_dump(exclude_none=True)

    try:
        llm_config = await get_llm_config_for_request(
            user_id=str(current_user.user_id),
            app=app,
            config_id=request.llm_config_id,
            overrides=overrides
        )
    except ValueError as e:
        raise HTTPException(
            status_code=403,
            detail=str(e)
        )

    if not llm_config:
        raise HTTPException(
            status_code=400,
            detail="LLM configuration not found or not accessible. Please configure an LLM model first."
        )

    # ... rest of existing code with llm_config ...

    # Set ContextVars
    set_current_jwt_token(jwt_token)
    set_current_llm_config(llm_config)

    # ... continue with Agent flow ...
```

---

## Implementation Steps

| Step | Task | File(s) | Difficulty | Priority |
|------|------|---------|------------|----------|
| 1 | Add `LLMConfigOverride` schema | `schemas/controller/chat.py` | ⭐ Low | P0 |
| 2 | Add `llm_config_id` and `llm_config_override` to `ChatRequest` | `schemas/controller/chat.py` | ⭐ Low | P0 |
| 3 | Implement `get_llm_config_for_request` function | `db/tasks.py` | ⭐⭐ Medium | P0 |
| 4 | Modify `stream_chat` endpoint to use new function | `api/routes/controller/chat.py` | ⭐ Low | P0 |
| 5 | Update API documentation | `docs/gns3-copilot/ai-chat-api-design.md` | ⭐ Low | P1 |
| 6 | Add unit tests for config resolution logic | `tests/` | ⭐⭐ Medium | P1 |
| 7 | Add integration tests for override scenarios | `tests/` | ⭐⭐ Medium | P2 |

---

## Usage Examples

### Example 1: Select Different Config

```bash
# Use a specific saved config instead of default
curl -X POST http://localhost:3080/v3/projects/{project_id}/chat/stream \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Explain OSPF configuration",
    "llm_config_id": "123e4567-e89b-12d3-a456-426614174000"
  }'
```

### Example 2: Override Model Only

```bash
# Use default config but with a different model
curl -X POST http://localhost:3080/v3/projects/{project_id}/chat/stream \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Configure OSPF on all routers",
    "llm_config_override": {
      "model": "gpt-4o-mini"
    }
  }'
```

### Example 3: Override Temperature

```bash
# Use default config but with higher temperature for creativity
curl -X POST http://localhost:3080/v3/projects/{project_id}/chat/stream \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Write a creative network scenario",
    "llm_config_override": {
      "temperature": 1.2,
      "top_p": 0.95
    }
  }'
```

### Example 4: Select Config + Override Parameters

```bash
# Use specific config and override multiple parameters
curl -X POST http://localhost:3080/v3/projects/{project_id}/chat/stream \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Analyze network topology",
    "llm_config_id": "123e4567-e89b-12d3-a456-426614174000",
    "llm_config_override": {
      "model": "claude-3-5-sonnet-20241022",
      "temperature": 0.3,
      "max_tokens": 4096
    }
  }'
```

### Example 5: Error Case - Inaccessible Config

```bash
# Attempting to use another user's config returns 403
curl -X POST http://localhost:3080/v3/projects/{project_id}/chat/stream \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Test",
    "llm_config_id": "00000000-0000-0000-0000-000000000000"
  }'

# Response:
# {
#   "detail": "Config 00000000-0000-0000-0000-000000000000 is not accessible to user"
# }
```

---

## Code Changes Checklist

### Files to Modify

| File Path | Change Type | Description |
|-----------|-------------|-------------|
| `gns3server/schemas/controller/chat.py` | Modify | Add `LLMConfigOverride` model and new fields to `ChatRequest` |
| `gns3server/db/tasks.py` | Add | Add `get_llm_config_for_request` function |
| `gns3server/api/routes/controller/chat.py` | Modify | Use `get_llm_config_for_request` with error handling |
| `docs/gns3-copilot/ai-chat-api-design.md` | Modify | Update API documentation with new parameters |

### New Files

| File Path | Description |
|-----------|-------------|
| N/A | No new files (all changes are modifications) |

---

## Testing Plan

### Unit Tests

#### 1. Test `get_llm_config_for_request`

- **Test 1.1**: Use default config (no config_id)
  - Input: `config_id=None, overrides=None`
  - Expected: Returns user's default config

- **Test 1.2**: Use specific user config
  - Input: Valid `config_id` owned by user
  - Expected: Returns specified config

- **Test 1.3**: Use inherited group config
  - Input: Valid `config_id` from user's group
  - Expected: Returns specified config with API key from parent

- **Test 1.4**: Use inaccessible config
  - Input: `config_id` from another user
  - Expected: Raises `ValueError`

- **Test 1.5**: Apply model override
  - Input: `overrides={"model": "gpt-4o-mini"}`
  - Expected: Returns config with `model="gpt-4o-mini"`

- **Test 1.6**: Apply temperature override
  - Input: `overrides={"temperature": 1.5}`
  - Expected: Returns config with `temperature=1.5`

- **Test 1.7**: Apply multiple overrides
  - Input: `overrides={"model": "x", "temperature": 0.5, "max_tokens": 1000}`
  - Expected: Returns config with all overrides applied

- **Test 1.8**: Invalid config_id
  - Input: Non-existent `config_id`
  - Expected: Returns `None`

### Integration Tests

#### 1. API Endpoint Tests

- **Test 1.1**: Request without new parameters (backward compatibility)
  - Expected: Works exactly as before

- **Test 1.2**: Request with `llm_config_id` only
  - Expected: Uses specified config

- **Test 1.3**: Request with `llm_config_override` only
  - Expected: Uses default config with overrides

- **Test 1.4**: Request with both `llm_config_id` and `llm_config_override`
  - Expected: Uses specified config with overrides

- **Test 1.5**: Request with inaccessible `llm_config_id`
  - Expected: Returns 403 Forbidden

- **Test 1.6**: Override validation (temperature out of range)
  - Input: `temperature=3.0` (exceeds max 2.0)
  - Expected: Returns 422 Validation Error

#### 2. Agent Integration Tests

- **Test 2.1**: Agent uses overridden config correctly
  - Verify LLM is called with overridden parameters

- **Test 2.2**: Multiple concurrent requests with different configs
  - Verify no cross-contamination between requests

---

## Risk Assessment

### Technical Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Config retrieval performance degradation | Medium | Low | Cache frequently used configs, optimize queries |
| Override validation bypass | High | Low | Pydantic validation for all override fields |
| API key leakage in logs | High | Low | Ensure API key is never logged, use [REDACTED] |
| Incorrect config precedence | Medium | Low | Clear documentation and thorough testing |

### Security Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| User accessing another user's config | High | Low | Validate config accessibility before use |
| Privilege escalation via config_id | High | Low | Strict access control validation |
| API key exposure via override | Low | Low | API key cannot be overridden (not in schema) |

### Compatibility Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Existing clients break | High | Low | All new fields are optional, default behavior unchanged |
| UI doesn't support new fields | Low | Medium | UI can ignore new fields, phased rollout |

---

## Security Considerations

### Access Control

1. **Config Access Validation**
   - User can only specify configs they own or inherited from their group
   - Validation happens before API key decryption
   - 403 Forbidden error for inaccessible configs

2. **Immutable Fields**
   - `api_key` cannot be overridden (not in `LLMConfigOverride`)
   - `provider` cannot be overridden (requires different API key handling)
   - Only safe parameters can be overridden

3. **Audit Logging**
   - Log all override operations with user_id, config_id, and override values
   - Do not log API keys (use [REDACTED] placeholder)

### Parameter Validation

| Parameter | Validation | Rationale |
|-----------|------------|-----------|
| `llm_config_id` | Must be valid UUID, accessible to user | Prevent injection attacks |
| `model` | String, max length 255 | Prevent oversized strings |
| `temperature` | 0.0 ≤ value ≤ 2.0 | LLM API limits |
| `max_tokens` | ≥ 1 | Prevent negative/zero values |
| `top_p` | 0.0 ≤ value ≤ 1.0 | LLM API limits |

---

## Future Enhancements

### Phase 2 Features

1. **Additional Override Parameters**
   - `frequency_penalty`: Token frequency penalty
   - `presence_penalty`: Token presence penalty
   - `stop`: Stop sequences
   - Provider-specific parameters (e.g., OpenAI functions)

2. **Config Templates**
   - Predefined override templates (e.g., "creative", "precise", "fast")
   - Users can save and reuse override combinations

3. **Usage Statistics**
   - Track which configs are most commonly used
   - Track which overrides are most commonly applied
   - Provide insights for default config optimization

4. **Config Recommendations**
   - Suggest optimal config based on request content
   - Auto-select cost-effective config for simple queries

---

## Related Features

- [User-Selectable Group Default Config](./user-selectable-group-default-config.md) - Setting default config
- [Runtime Agent Parameters](./runtime-agent-params.md) - Controlling Agent execution behavior
- [LLM Model Configs API](../llm-model-configs-api.md) - Managing saved configurations

---

## References

- [AI Chat API Design](../ai-chat-api-design.md)
- [Pydantic Field Validation](https://docs.pydantic.dev/latest/concepts/fields/)
- FastAPI Request Handling: https://fastapi.tiangolo.com/tutorial/body/

---

## Discussion Points

### Open Questions

1. **Should we allow `provider` override?**
   - Pro: More flexibility (e.g., switch from OpenAI to Anthropic)
   - Con: Requires different API key handling, more complex
   - **Recommendation**: No - keep it simple for now

2. **Should overrides be visible in response metadata?**
   - Pro: User knows which config/overrides were used
   - Con: Increases response size
   - **Recommendation**: Add to session metadata, not SSE messages

3. **Should we support parameter shortcuts?**
   - Example: `"mode": "fast"` instead of specifying all parameters
   - **Recommendation**: Future enhancement via templates

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
