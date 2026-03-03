"""
Prompts module for FlowNet-Lab.

This package contains system prompts and prompt loading utilities for
the FlowNet-Lab AI agent. It supports multiple language proficiency
levels and English language prompts.
"""

from .linux_specialist_prompt import LINUX_SPECIALIST_PROMPT
from .prompt_loader import load_system_prompt
from .title_prompt import TITLE_PROMPT
from .experiment_deploy_prompt import EXPERIMENT_DEPLOY_SYSTEM_PROMPT

# Dynamic version management
try:
    from importlib.metadata import version

    __version__ = version("gns3-copilot")
except Exception:
    __version__ = "unknown"

__author__ = "Guobin Yue"
__description__ = "AI-powered network automation assistant for GNS3"
__url__ = "https://github.com/yueguobin/gns3-copilot"

__all__ = [
    "load_system_prompt",
    "TITLE_PROMPT",
    "LINUX_SPECIALIST_PROMPT",
    "EXPERIMENT_DEPLOY_SYSTEM_PROMPT",
]
