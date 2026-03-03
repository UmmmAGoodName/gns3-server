"""
Model Factory for GNS3-Copilot Agent

This module provides factory functions to create fresh LLM model instances.
Configuration is loaded from the llm_model_configs system via connector_factory.
"""

import logging
import os
from typing import Any, Optional
from uuid import UUID

from langchain.chat_models import init_chat_model

from gns3_copilot.gns3_client import get_llm_config

logger = logging.getLogger(__name__)


def _load_llm_config(
    user_id: Optional[UUID] = None,
    jwt_token: Optional[str] = None,
    llm_config: Optional[dict[str, Any]] = None,
) -> dict[str, str]:
    """
    Load model configuration from llm_config dict or fetch from llm_model_configs system.

    Priority order:
    1. Provided llm_config dictionary (highest priority)
    2. Fetch from llm_model_configs system via connector_factory (requires user_id and jwt_token)
    3. Environment variables (fallback for backward compatibility)

    Args:
        user_id: User UUID for fetching config from database
        jwt_token: JWT token for API authentication
        llm_config: Optional configuration dictionary to use directly

    Returns:
        Dictionary containing model configuration.
    """
    # Priority 1: Use provided llm_config dictionary
    if llm_config:
        logger.info("Using provided llm_config dictionary")
        return {
            "model_name": llm_config.get("model", ""),
            "model_provider": llm_config.get("provider", ""),
            "api_key": llm_config.get("api_key", ""),
            "base_url": llm_config.get("base_url", ""),
            "temperature": str(llm_config.get("temperature", "0")),
        }

    # Priority 2: Fetch from llm_model_configs system via connector_factory
    if user_id and jwt_token:
        logger.info(f"Fetching LLM config from database for user {user_id}")
        config = get_llm_config(user_id=user_id, jwt_token=jwt_token)

        if config:
            logger.info(
                f"Successfully loaded LLM config from database: "
                f"provider={config.get('provider')}, model={config.get('model')}"
            )
            return {
                "model_name": config.get("model", ""),
                "model_provider": config.get("provider", ""),
                "api_key": config.get("api_key", ""),
                "base_url": config.get("base_url", ""),
                "temperature": str(config.get("temperature", "0")),
            }
        else:
            logger.warning(
                f"No LLM config found in database for user {user_id}, falling back to environment variables"
            )

    # Priority 3: Fallback to environment variables
    logger.info("Loading LLM config from environment variables (fallback)")
    return {
        "model_name": os.getenv("MODEL_NAME", ""),
        "model_provider": os.getenv("MODE_PROVIDER", ""),
        "api_key": os.getenv("MODEL_API_KEY", ""),
        "base_url": os.getenv("BASE_URL", ""),
        "temperature": os.getenv("TEMPERATURE", "0"),
    }


def create_base_model(
    user_id: Optional[UUID] = None,
    jwt_token: Optional[str] = None,
    llm_config: Optional[dict[str, Any]] = None,
) -> Any:
    """
    Create a fresh base LLM model instance.

    Configuration priority:
    1. llm_config dictionary (if provided)
    2. Fetch from llm_model_configs system via connector_factory (if user_id and jwt_token provided)
    3. Environment variables (fallback)

    Args:
        user_id: User UUID for fetching config from database
        jwt_token: JWT token for API authentication
        llm_config: Optional configuration dictionary to use directly

    Returns:
        Any: A new LLM model instance configured with current settings.
              The actual type depends on the provider (e.g., ChatOpenAI, etc.).

    Raises:
        ValueError: If required configuration fields are missing or invalid.
    """
    env_vars = _load_llm_config(user_id, jwt_token, llm_config)

    # Log the loaded configuration (mask sensitive data)
    logger.info(
        "Creating base model: name=%s, provider=%s, base_url=%s, temperature=%s",
        env_vars["model_name"],
        env_vars["model_provider"],
        env_vars["base_url"] if env_vars["base_url"] else "default",
        env_vars["temperature"],
    )

    # Validate required fields
    if not env_vars["model_name"]:
        raise ValueError("MODEL_NAME environment variable is required")

    if not env_vars["model_provider"]:
        raise ValueError("MODE_PROVIDER environment variable is required")

    try:
        model = init_chat_model(
            env_vars["model_name"],
            model_provider=env_vars["model_provider"],
            api_key=env_vars["api_key"],
            base_url=env_vars["base_url"],
            temperature=env_vars["temperature"],
            configurable_fields="any",
            config_prefix="foo",
        )

        logger.info("Base model created successfully")
        return model

    except Exception as e:
        logger.error("Failed to create base model: %s", e)
        raise RuntimeError(f"Failed to create base model: {e}") from e


def create_title_model(
    user_id: Optional[UUID] = None,
    jwt_token: Optional[str] = None,
    llm_config: Optional[dict[str, Any]] = None,
) -> Any:
    """
    Create a fresh title generation model instance.

    This creates a model instance suitable for generating conversation titles.
    It uses the same configuration as the base model but with a higher temperature
    for more creative output.

    Configuration priority:
    1. llm_config dictionary (if provided)
    2. Fetch from llm_model_configs system via connector_factory (if user_id and jwt_token provided)
    3. Environment variables (fallback)

    Args:
        user_id: User UUID for fetching config from database
        jwt_token: JWT token for API authentication
        llm_config: Optional configuration dictionary to use directly

    Returns:
        Any: A new LLM model instance for title generation.
              The actual type depends on the provider.

    Raises:
        ValueError: If required configuration fields are missing or invalid.
    """
    env_vars = _load_llm_config(user_id, jwt_token, llm_config)

    logger.info(
        "Creating title model: name=%s, provider=%s, base_url=%s, temperature=1.0",
        env_vars["model_name"],
        env_vars["model_provider"],
        env_vars["base_url"] if env_vars["base_url"] else "default",
    )

    # Validate required fields
    if not env_vars["model_name"]:
        raise ValueError("MODEL_NAME environment variable is required")

    if not env_vars["model_provider"]:
        raise ValueError("MODE_PROVIDER environment variable is required")

    try:
        model = init_chat_model(
            env_vars["model_name"],
            model_provider=env_vars["model_provider"],
            api_key=env_vars["api_key"],
            base_url=env_vars["base_url"],
            temperature="1.0",  # Higher temperature for more creative titles
            configurable_fields="any",
            config_prefix="foo",
        )

        logger.info("Title model created successfully")
        return model

    except Exception as e:
        logger.error("Failed to create title model: %s", e)
        raise RuntimeError(f"Failed to create title model: {e}") from e


def create_model_with_tools(
    model: Any,
    tools: list[Any],
) -> Any:
    """
    Bind tools to a model instance.

    Args:
        model: The base model instance.
        tools: List of tools to bind to the model.

    Returns:
        Any: A model instance with tools bound (type varies by provider).

    Raises:
        RuntimeError: If tool binding fails.
    """
    try:
        model_with_tools = model.bind_tools(tools)
        logger.info("Model bound with %d tools successfully", len(tools))
        return model_with_tools
    except Exception as e:
        logger.error("Failed to bind tools to model: %s", e)
        raise RuntimeError(f"Failed to bind tools to model: {e}") from e


def create_base_model_with_tools(
    tools: list[Any],
    user_id: Optional[UUID] = None,
    jwt_token: Optional[str] = None,
    llm_config: Optional[dict[str, Any]] = None,
) -> Any:
    """
    Create a fresh base model instance with tools bound.

    This is a convenience function that combines creating the base model
    and binding tools to it.

    Configuration priority:
    1. llm_config dictionary (if provided)
    2. Fetch from llm_model_configs system via connector_factory (if user_id and jwt_token provided)
    3. Environment variables (fallback)

    Args:
        tools: List of tools to bind to the model.
        user_id: User UUID for fetching config from database
        jwt_token: JWT token for API authentication
        llm_config: Optional configuration dictionary to use directly

    Returns:
        Any: A new model instance with tools bound (type varies by provider).

    Raises:
        ValueError: If required configuration fields are missing.
        RuntimeError: If model creation or tool binding fails.
    """
    base_model = create_base_model(user_id, jwt_token, llm_config)
    return create_model_with_tools(base_model, tools)
