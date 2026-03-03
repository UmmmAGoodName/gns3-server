# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This file is part of FlowNet-Lab.
#
# FlowNet-Lab is free software: you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# FlowNet-Lab is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License along
# with FlowNet-Lab. If not, see <https://www.gnu.org/licenses/>.

"""
Experiment Deployment Agent

A LangGraph-based agent for automated GNS3 experiment deployment.
Parses experiment plans and deploys complete GNS3 lab environments.
"""

import operator
from typing import Annotated, TypedDict, Any

from langchain.messages import AnyMessage, SystemMessage, HumanMessage, AIMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.managed.is_last_step import RemainingSteps

import logging

from gns3_copilot.agent.model_factory import create_base_model_with_tools
from gns3_copilot.prompts.experiment_deploy_prompt import EXPERIMENT_DEPLOY_SYSTEM_PROMPT
from gns3_copilot.tools_v2 import (
    GNS3TemplateTool,
    GNS3CreateNodeTool,
    GNS3LinkTool,
    GNS3StartNodeQuickTool,
    GNS3UpdateNodeNameTool,
)
from gns3_copilot.gns3_client import GNS3ProjectCreate, GNS3ProjectList, GNS3TopologyTool

logger = logging.getLogger(__name__)

# Create tool instances - use existing GNS3ProjectCreate directly
tools = [
    GNS3ProjectList(),  # List existing projects to avoid duplicates
    GNS3TemplateTool(),
    GNS3ProjectCreate(),  # Use existing tool directly
    GNS3CreateNodeTool(),
    GNS3TopologyTool(),  # Get topology to see actual port names
    GNS3LinkTool(),
    GNS3UpdateNodeNameTool(),
    GNS3StartNodeQuickTool(),  # Use quick start to avoid HTTP timeouts
]

tools_by_name = {tool.name: tool for tool in tools}

logger.info(f"Experiment Deploy Agent initialized with {len(tools)} tools")
logger.debug(f"Available tools: {[tool.name for tool in tools]}")


# Define state
class ExperimentDeployState(TypedDict):
    """
    Experiment deployment agent state.

    Attributes:
        messages: Conversation messages
        llm_calls: Number of LLM calls made
        remaining_steps: Remaining steps before recursion limit
        deployment_result: Final deployment result summary
    """
    messages: Annotated[list[AnyMessage], operator.add]
    llm_calls: int
    remaining_steps: RemainingSteps
    deployment_result: dict[str, Any] | None


# LLM call node
def llm_call(state: dict):
    """LLM decides whether to call a tool or respond"""
    messages = state.get("messages", [])

    # Skip if no messages
    if not messages:
        return {"messages": []}

    # Get model with tools
    model = create_base_model_with_tools(tools)

    # Invoke model
    response = model.invoke(messages)

    # Increment LLM call counter
    llm_calls = state.get("llm_calls", 0) + 1
    logger.info(f"LLM call #{llm_calls}: {type(response).__name__}")

    return {
        "messages": [response],
        "llm_calls": llm_calls,
    }


# Tool execution node
def tool_execute(state: dict):
    """Performs the tool call"""

    result = []
    for tool_call in state["messages"][-1].tool_calls:
        tool = tools_by_name[tool_call["name"]]
        observation = tool.invoke(tool_call["args"])
        result.append(ToolMessage(
            content=observation,
            tool_call_id=tool_call["id"],
            name=tool_call["name"]
        ))
    return {"messages": result}


# Routing function
def should_continue(state: dict):
    """Decide whether to continue or end"""
    messages = state.get("messages", [])

    if not messages:
        return END

    last_message = messages[-1]

    # Continue if last message has tool calls
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tool_execute"

    # End if last message is a regular text response
    return END


# Build the graph
def build_experiment_deploy_agent():
    """Build the experiment deployment agent graph"""

    # Create state graph
    workflow = StateGraph(ExperimentDeployState)

    # Add nodes
    workflow.add_node("llm_call", llm_call)
    workflow.add_node("tool_execute", tool_execute)

    # Set entry point
    workflow.add_edge(START, "llm_call")

    # Add conditional edges
    workflow.add_conditional_edges(
        "llm_call",
        should_continue,
        {
            "tool_execute": "tool_execute",
            END: END,
        },
    )

    # Add edge back to LLM after tool execution
    workflow.add_edge("tool_execute", "llm_call")

    # Compile without checkpointer (experiment deploy is stateless)
    graph = workflow.compile()

    logger.info("Experiment Deploy Agent graph compiled successfully")
    return graph


# Singleton instance
_experiment_deploy_agent_graph = None


def get_experiment_deploy_agent():
    """Get or create the experiment deploy agent graph"""
    global _experiment_deploy_agent_graph
    if _experiment_deploy_agent_graph is None:
        _experiment_deploy_agent_graph = build_experiment_deploy_agent()
    return _experiment_deploy_agent_graph


async def deploy_experiment_from_plan(
    plan_content: str,
) -> Any:
    """
    Deploy an experiment from plan content using the agent.

    Args:
        plan_content: The experiment plan content

    Yields:
        Agent execution updates
    """
    agent = get_experiment_deploy_agent()

    # Create system message
    system_msg = SystemMessage(content=EXPERIMENT_DEPLOY_SYSTEM_PROMPT)

    # Create human message with the plan
    human_msg = HumanMessage(content=f"""
Please deploy the following GNS3 experiment:

{plan_content}

Follow the deployment workflow and use the available tools to create the complete lab environment.
""")

    # Initial state
    initial_state = {
        "messages": [system_msg, human_msg],
        "llm_calls": 0,
        "deployment_result": None,
    }

    # Stream agent execution (no config needed, stateless)
    async for event in agent.astream(initial_state):
        yield event

        # Extract and yield deployment updates
        if "messages" in event:
            messages = event["messages"]
            for msg in messages:
                if isinstance(msg, ToolMessage):
                    # Parse tool result and yield as update
                    try:
                        import json
                        result = json.loads(msg.content)
                        yield {"type": "tool_result", "tool": msg.name, "result": result}
                    except:
                        pass
