import logging
from typing import Any

from langchain.tools import BaseTool

from gns3_copilot.gns3_client import Project, get_gns3_connector

# Configure logging
logger = logging.getLogger(__name__)


class GNS3ProjectOpen(BaseTool):
    """
    Tool to open or close a GNS3 project by project_id.

    This tool connects to GNS3 server and opens or closes the specified project.
    It returns the project status and details after the operation.
    """

    name: str = "open_gns3_project"
    description: str = """
    Opens or closes a GNS3 project by its project_id.

    Input parameters:
    - project_id: The unique UUID identifier of project (required)
    - open: Set to True to open the project (default: False)
    - close: Set to True to close the project (default: False)

    Note: Exactly one of 'open' or 'close' must be set to True.

    Returns: Project operation status and detailed information including:
    - success: Whether the operation succeeded
    - operation: "open" or "close"
    - project: Project details (name, project_id, status, etc.)
    - message: Status message

    Example output (open):
        {
            "success": true,
            "operation": "open",
            "project": {
                "project_id": "ff8e059c-c33d-47f4-bc11-c7dda8a1d500",
                "name": "mylab",
                "status": "opened"
            },
            "message": "Project 'mylab' opened successfully"
        }

    Example output (close):
        {
            "success": true,
            "operation": "close",
            "project": {
                "project_id": "ff8e059c-c33d-47f4-bc11-c7dda8a1d500",
                "name": "mylab",
                "status": "closed"
            },
            "message": "Project 'mylab' closed successfully"
        }
    """

    def _run(self, tool_input: Any = None, run_manager: Any = None) -> dict:
        """
        Execute project open or close operation.

        Args:
            tool_input: Dictionary containing project_id, open, or close
            run_manager: Run manager for tool execution (optional)

        Returns:
            Dictionary with operation result and project details
        """
        # Log received input
        logger.info("Received input: %s", tool_input)

        try:
            # Validate input
            if not tool_input or "project_id" not in tool_input:
                return {
                    "success": False,
                    "error": "Missing required parameter: project_id",
                }

            project_id = tool_input["project_id"]
            should_open = tool_input.get("open", False)
            should_close = tool_input.get("close", False)

            # Validate that exactly one of open or close is True
            if should_open and should_close:
                return {
                    "success": False,
                    "error": "Cannot set both 'open' and 'close' to True. "
                    "Please specify only one operation.",
                }

            if not should_open and not should_close:
                return {
                    "success": False,
                    "error": "Either 'open' or 'close' must be set to True.",
                }

            # Initialize Gns3Connector using factory function
            logger.info("Connecting to GNS3 server...")
            server = get_gns3_connector()

            if server is None:
                logger.error("Failed to create GNS3 connector")
                return {
                    "success": False,
                    "error": "Failed to connect to GNS3 server. Please check your configuration.",
                }

            # Create project instance and retrieve project details
            project = Project(project_id=project_id, connector=server)
            project.get(get_nodes=False, get_links=False, get_stats=False)

            # Check if project was found
            if not project.name:
                return {
                    "success": False,
                    "error": f"Project with ID '{project_id}' not found",
                }

            # Perform the requested operation
            operation = None
            if should_open:
                project.open()
                operation = "open"
                action_message = "opened"
            else:  # should_close
                project.close()
                operation = "close"
                action_message = "closed"

            # Prepare result
            result = {
                "success": True,
                "operation": operation,
                "project": {
                    "project_id": project.project_id,
                    "name": project.name,
                    "status": project.status,
                },
                "message": f"Project '{project.name}' {action_message} successfully",
            }

            # Log result
            logger.info("Project operation result: %s", result)

            # Return success with project details
            return result

        except Exception as e:
            logger.error("Error operating on GNS3 project: %s", str(e))
            return {
                "success": False,
                "error": f"Failed to operate on GNS3 project: {str(e)}",
            }
