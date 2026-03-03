"""
GNS3 Connector Factory Module

This module provides factory functions for creating Gns3Connector instances.
It creates appropriately configured connectors using JWT token authentication.

The URL resolution strategy follows a priority order:
1. Explicitly provided URL parameter
2. Runtime configuration from Controller.instance().compute("local")
3. Static configuration from Config.instance().settings.Server
4. Fallback to localhost:3080

Main Functions:
    get_gns3_connector: Create a Gns3Connector with JWT token

Example:
    from gns3_copilot.gns3_client import get_gns3_connector

    # Auto-detect URL from Controller or Config
    connector = get_gns3_connector(jwt_token="your_token")
    if connector:
        # Use connector to interact with GNS3 server
        projects = connector.projects

Authentication:
    - JWT token based authentication
"""

import logging
from typing import Optional

from gns3_copilot.gns3_client.custom_gns3fy import Gns3Connector

logger = logging.getLogger(__name__)

# Fallback default URL
DEFAULT_GNS3_URL = "http://127.0.0.1:3080"


def _get_url_from_controller() -> Optional[str]:
    """Try to get GNS3 server URL from running Controller instance.

    Returns:
        URL string if successful, None otherwise
    """
    try:
        from gns3server.controller import Controller

        controller = Controller.instance()
        local_compute = controller.get_compute("local")

        url = f"{local_compute.protocol}://{local_compute.host}:{local_compute.port}"
        logger.debug(
            "Got GNS3 URL from Controller: %s (protocol=%s, host=%s, port=%s)",
            url,
            local_compute.protocol,
            local_compute.host,
            local_compute.port,
        )
        return url
    except ImportError as e:
        logger.debug("Cannot import Controller: %s", str(e))
        return None
    except AttributeError as e:
        logger.debug("Controller instance not available: %s", str(e))
        return None
    except KeyError as e:
        logger.debug("Local compute not found in Controller: %s", str(e))
        return None
    except Exception as e:
        logger.warning("Unexpected error getting URL from Controller: %s", str(e))
        return None


def _get_url_from_config() -> Optional[str]:
    """Try to get GNS3 server URL from Config settings.

    Returns:
        URL string if successful, None otherwise
    """
    try:
        from gns3server.config import Config

        server_config = Config.instance().settings.Server
        url = f"{server_config.protocol.value}://{server_config.host}:{server_config.port}"
        logger.debug(
            "Got GNS3 URL from Config: %s (protocol=%s, host=%s, port=%s)",
            url,
            server_config.protocol.value,
            server_config.host,
            server_config.port,
        )
        return url
    except ImportError as e:
        logger.debug("Cannot import Config: %s", str(e))
        return None
    except AttributeError as e:
        logger.debug("Config settings not available: %s", str(e))
        return None
    except Exception as e:
        logger.warning("Unexpected error getting URL from Config: %s", str(e))
        return None


def get_gns3_connector(jwt_token: str, url: Optional[str] = None) -> Optional[Gns3Connector]:
    """Create and return a Gns3Connector instance with JWT authentication.

    URL Resolution Strategy (in order):
        1. Explicitly provided `url` parameter
        2. Runtime configuration from Controller.instance().compute("local")
        3. Static configuration from Config.instance().settings.Server
        4. Fallback to DEFAULT_GNS3_URL (http://127.0.0.1:3080)

    Args:
        jwt_token: JWT token for authentication
        url: GNS3 server URL (optional, auto-detected if not provided)

    Returns:
        Gns3Connector instance if parameters are valid, None otherwise

    Example:
        # Auto-detect URL from Controller or Config
        connector = get_gns3_connector(jwt_token="your_jwt_token")

        # Or specify custom URL
        connector = get_gns3_connector(
            jwt_token="your_jwt_token",
            url="http://custom-server:3080"
        )

        if connector:
            projects = connector.projects
        else:
            logger.error("Failed to create GNS3 connector")
    """
    try:
        # Validate JWT token
        if not jwt_token:
            logger.error("JWT token parameter is required")
            return None

        # Resolve URL with fallback strategy
        if url is None:
            logger.debug("No URL provided, attempting auto-detection...")

            # Strategy 1: Try to get from running Controller
            url = _get_url_from_controller()
            if url:
                logger.info("Using GNS3 server URL from Controller: %s", url)
            else:
                # Strategy 2: Fall back to Config
                logger.debug("Controller not available, trying Config...")
                url = _get_url_from_config()
                if url:
                    logger.info("Using GNS3 server URL from Config: %s", url)
                else:
                    # Strategy 3: Use default fallback
                    logger.debug("Config not available, using default URL")
                    url = DEFAULT_GNS3_URL
                    logger.warning(
                        "Using fallback default URL: %s. "
                        "This may not be correct if your GNS3 server is configured differently. "
                        "Consider providing the URL explicitly or ensuring gns3server is running.",
                        url
                    )
        else:
            logger.info("Using explicitly provided GNS3 server URL: %s", url)

        # Validate URL
        if not url:
            logger.error("Failed to resolve GNS3 server URL")
            return None

        # Create connector
        logger.debug("Creating Gns3Connector with URL=%s", url)
        connector = Gns3Connector(
            url=url,
            jwt_token=jwt_token,
            api_version=3,
        )
        logger.info("Successfully created Gns3Connector for URL: %s", url)
        return connector

    except Exception as e:
        logger.error("Failed to create Gns3Connector: %s", str(e), exc_info=True)
        return None
