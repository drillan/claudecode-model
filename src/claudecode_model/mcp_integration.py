"""MCP integration utilities for pydantic-ai toolsets.

This module provides functions to convert pydantic-ai tools to
Claude Agent SDK MCP server format.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine, Sequence
from typing import Protocol, TypedDict, runtime_checkable

from claude_agent_sdk import SdkMcpTool, create_sdk_mcp_server, tool
from claude_agent_sdk.types import McpSdkServerConfig

from claudecode_model.types import JsonValue

logger = logging.getLogger(__name__)


class ToolDefinition(TypedDict):
    """Tool definition extracted from pydantic-ai toolset."""

    name: str
    description: str
    input_schema: dict[str, JsonValue]
    function: Callable[..., Coroutine[object, object, object]] | None


@runtime_checkable
class PydanticAITool(Protocol):
    """Protocol for pydantic-ai tool interface.

    Attributes:
        name: Tool name (must be non-empty).
        description: Tool description.
        parameters_json_schema: JSON schema for tool parameters.
        function: Optional async callable that implements the tool logic.
                  If not provided, the tool wrapper will raise an error.
    """

    name: str
    description: str
    parameters_json_schema: dict[str, JsonValue]
    function: Callable[..., Coroutine[object, object, object]] | None


@runtime_checkable
class AgentToolset(Protocol):
    """Protocol for pydantic-ai Agent toolset (e.g., _AgentFunctionToolset).

    This protocol matches pydantic-ai's internal _AgentFunctionToolset structure,
    allowing direct use of agent._function_toolset without extracting tools.

    Attributes:
        tools: Dictionary mapping tool names to PydanticAITool objects.
    """

    tools: dict[str, PydanticAITool]


class ToolValidationError(ValueError):
    """Error raised when tool validation fails."""

    pass


def extract_tools_from_toolsets(
    toolsets: Sequence[PydanticAITool] | None,
) -> list[ToolDefinition]:
    """Extract tool definitions from pydantic-ai toolsets.

    Args:
        toolsets: Sequence of pydantic-ai tool objects or None.

    Returns:
        List of tool definitions with name, description, and input_schema.

    Raises:
        ToolValidationError: If a tool has an empty name.
    """
    if toolsets is None:
        return []

    result: list[ToolDefinition] = []
    for t in toolsets:
        # Validate tool name
        if not t.name or not t.name.strip():
            raise ToolValidationError(
                "Tool name cannot be empty. Each tool must have a non-empty name."
            )

        tool_def: ToolDefinition = {
            "name": t.name,
            "description": t.description,
            "input_schema": t.parameters_json_schema,
            "function": getattr(t, "function", None),
        }
        result.append(tool_def)
    return result


ToolWrapperFunc = Callable[
    [dict[str, object]], Coroutine[object, object, dict[str, object]]
]


def create_tool_wrapper(
    tool_name: str,
    original_function: Callable[..., Coroutine[object, object, object]],
) -> ToolWrapperFunc:
    """Create an async wrapper function for a pydantic-ai tool.

    This function creates a wrapper that:
    1. Calls the original function with provided arguments
    2. Formats the result in MCP-compatible format
    3. Logs and re-raises any exceptions

    Args:
        tool_name: Name of the tool (used for logging).
        original_function: The async function to wrap.

    Returns:
        An async function that takes a dict of arguments and returns MCP-format response.
    """

    async def wrapper(args: dict[str, object]) -> dict[str, object]:
        """Wrapper that delegates to original pydantic-ai tool function."""
        try:
            result = await original_function(**args)
            return {"content": [{"type": "text", "text": str(result)}]}
        except Exception as e:
            logger.error(
                "Tool '%s' execution failed: %s",
                tool_name,
                str(e),
                exc_info=True,
            )
            raise

    return wrapper


def convert_tool_definition(tool_def: ToolDefinition) -> SdkMcpTool[dict[str, object]]:
    """Convert a tool definition to SdkMcpTool format.

    Args:
        tool_def: Tool definition with name, description, input_schema, and function.

    Returns:
        SdkMcpTool instance compatible with create_sdk_mcp_server.

    Raises:
        ToolValidationError: If the tool has no function registered.
    """
    original_function = tool_def.get("function")
    tool_name = tool_def["name"]

    if original_function is None:
        raise ToolValidationError(
            f"Tool '{tool_name}' has no function registered. "
            "Each tool must have a callable function."
        )

    wrapper = create_tool_wrapper(tool_name, original_function)

    return tool(tool_name, tool_def["description"], tool_def["input_schema"])(wrapper)


MCP_SERVER_NAME = "pydantic_tools"


def create_mcp_server_from_tools(
    name: str = MCP_SERVER_NAME,
    toolsets: Sequence[PydanticAITool] | None = None,
    version: str = "1.0.0",
) -> McpSdkServerConfig:
    """Create an MCP server from pydantic-ai toolsets.

    Args:
        name: Server name (used as prefix in mcp__<name>__<tool>).
              Defaults to MCP_SERVER_NAME ("pydantic_tools").
        toolsets: Sequence of pydantic-ai tool objects.
        version: Server version string.

    Returns:
        McpSdkServerConfig for use with ClaudeAgentOptions.mcp_servers.

    Raises:
        ToolValidationError: If any tool has an empty name or no function.
    """
    tool_defs = extract_tools_from_toolsets(toolsets)
    sdk_tools = [convert_tool_definition(td) for td in tool_defs]

    return create_sdk_mcp_server(
        name=name,
        version=version,
        tools=sdk_tools if sdk_tools else None,
    )
