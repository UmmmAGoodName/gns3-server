"""
Prompt loader for GNS3 Copilot.

This module provides utilities for loading system prompts.
"""

import logging
import os

from .base_prompt import SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def load_system_prompt() -> str:
    """
    Load the system prompt for GNS3 Copilot.

    In the future, this can be extended to support multiple prompt variants
    based on environment variables (e.g., ENGLISH_LEVEL).

    Returns:
        str: The system prompt string.
    """
    # For now, just return the base system prompt
    # Future enhancement: Load different prompts based on ENGLISH_LEVEL env var
    # english_level = os.getenv("ENGLISH_LEVEL", "native")
    return SYSTEM_PROMPT
