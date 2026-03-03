"""
Application Configuration Manager for FlowNet-Lab.

This module provides a unified interface for managing application configuration
stored in SQLite database. It includes default values for all configuration
items and helper functions for reading and saving configuration.

Functions:
    get_config(key, default=None): Retrieve a configuration value with default
    set_config(key, value): Save a configuration value to database
    get_all_config(): Retrieve all configuration values
    init_config(): Initialize database with default values

Constants:
    DEFAULT_CONFIG: Dictionary containing all configuration keys and their defaults
"""

import logging
from typing import Any

from gns3_copilot.utils.config_db import (
    clear_all,
    get_all_values,
    get_value,
    init_db,
    set_value,
)

logger = logging.getLogger(__name__)

# Default configuration values for all application settings
DEFAULT_CONFIG: dict[str, str] = {
    # GNS3 Server Configuration
    #"GNS3_SERVER_HOST": "",
    #"GNS3_SERVER_URL": "http://127.0.0.1:3080/",
    #"API_VERSION": "3",
    #"GNS3_SERVER_USERNAME": "",
    #"GNS3_SERVER_PASSWORD": "",
    #"GNS3_SERVER_JWT_TOKEN": "",
    # Model Configuration
    "MODE_PROVIDER": "openai",
    "MODEL_NAME": "gpt-4",
    "MODEL_API_KEY": "",
    "BASE_URL": "",
    "TEMPERATURE": "0.0",
    # Voice Configuration
    #"VOICE": "False",
    # Linux Telnet Configuration
    "LINUX_TELNET_USERNAME": "",
    "LINUX_TELNET_PASSWORD": "",
    # Prompt Configuration
    #"ENGLISH_LEVEL": "Normal Prompt",
    # Reading Page Configuration
    #"CALIBRE_SERVER_URL": "",
    #"READING_NOTES_DIR": "notes",
    # UI Configuration
    #"CONTAINER_HEIGHT": "1200",
    #"ZOOM_SCALE_TOPOLOGY": "0.8",
    # Other Settings
    #"LANGUAGE": "zh",
    # DashScope API Configuration
    #"DASHSCOPE_API_KEY": "",
    # DashScope STT (Speech-to-Text) Configuration
    #"DASHSCOPE_STT_MODEL": "fun-asr-realtime",
    #"DASHSCOPE_STT_FORMAT": "wav",
    #"DASHSCOPE_STT_SAMPLE_RATE": "16000",
    #"DASHSCOPE_STT_LANGUAGE_HINTS": "zh,en",
    # DashScope TTS (Text-to-Speech) Configuration
    #"DASHSCOPE_TTS_MODEL": "cosyvoice-v3-flash",
    #"DASHSCOPE_TTS_VOICE": "longanyang",
    #"DASHSCOPE_TTS_FORMAT": "mp3",
    #"DASHSCOPE_TTS_VOLUME": "50",
    #"DASHSCOPE_TTS_SPEECH_RATE": "1.0",
    #"DASHSCOPE_TTS_PITCH_RATE": "1.0",
}


def _get_default(key: str) -> str | None:
    """Get the default value for a configuration key.

    Args:
        key: Configuration key

    Returns:
        Default value if key exists, None otherwise
    """
    return DEFAULT_CONFIG.get(key)


def get_config(key: str, default: str | None = None) -> str:
    """Retrieve a configuration value from the database.

    If the key doesn't exist in the database, it will use the default value
    from DEFAULT_CONFIG. If the key is not in DEFAULT_CONFIG either, it will
    use the provided default parameter.

    Args:
        key: The configuration key to retrieve
        default: Fallback default value if key not in DEFAULT_CONFIG

    Returns:
        The configuration value as a string

    Example:
        >>> get_config("GNS3_SERVER_URL")
        'http://127.0.0.1:3080/'

        >>> get_config("CUSTOM_KEY", "default_value")
        'default_value'
    """
    # Get default value from DEFAULT_CONFIG or use provided default
    default_value = default if default is not None else _get_default(key)

    # Retrieve value from database
    value = get_value(key, default_value)

    if value is None:
        return default_value if default_value is not None else ""

    # Ensure value is a string
    return str(value) if value else default_value if default_value else ""


def set_config(key: str, value: str) -> bool:
    """Save a configuration value to the database.

    Args:
        key: The configuration key to save
        value: The configuration value to store

    Returns:
        True if save was successful, False otherwise

    Example:
        >>> set_config("GNS3_SERVER_URL", "http://192.168.1.100:3080")
        True
    """
    return set_value(key, value)


def get_all_config() -> dict[str, str]:
    """Retrieve all configuration values from the database.

    Returns:
        Dictionary with all configuration key-value pairs

    Example:
        >>> config = get_all_config()
        >>> print(config["GNS3_SERVER_URL"])
        'http://127.0.0.1:3080/'
    """
    return get_all_values()


def init_config() -> None:
    """Initialize the configuration database with default values.

    This function initializes the database and populates it with default
    values for all configuration keys. If a key already exists in the
    database, its value will not be overwritten.

    This should be called once at application startup.

    Example:
        >>> init_config()
        # Database is now initialized with default values
    """
    try:
        # Initialize database and create tables
        init_db()

        # Set default values for all keys (only if not already set)
        for key, default_value in DEFAULT_CONFIG.items():
            existing_value = get_value(key)
            if existing_value is None:
                set_value(key, default_value)

        logger.info(
            "Configuration database initialized with %d keys", len(DEFAULT_CONFIG)
        )
    except Exception as e:
        logger.error("Failed to initialize configuration: %s", e)
        raise


def reset_config() -> None:
    """Reset all configuration to default values.

    This function clears all existing configuration values and
    restores them to defaults defined in DEFAULT_CONFIG.

    Example:
        >>> reset_config()
        # All configuration values are now set to defaults
    """
    try:
        # Clear all existing values
        clear_all()

        # Re-initialize with defaults
        init_config()

        logger.info("Configuration reset to defaults")
    except Exception as e:
        logger.error("Failed to reset configuration: %s", e)
        raise
